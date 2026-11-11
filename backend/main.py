"""Clip Studio: local-only API, durable projects and cancellable media jobs."""
import csv
import io
import ipaddress
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import queue
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from PIL import Image, ImageDraw, ImageFont

load_dotenv(encoding='utf-8-sig')
ROOT = Path(os.getenv('CLIP_WORKSPACE', 'workspace')).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
for folder in ('uploads', 'exports', 'jobs'):
    (ROOT / folder).mkdir(exist_ok=True)
DB = ROOT / 'studio.sqlite3'
def db():
    con = sqlite3.connect(DB, timeout=20)
    con.execute('PRAGMA journal_mode=WAL')
    return con
with db() as c:
    c.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS metrics (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    for jid, raw in c.execute('SELECT id,data FROM jobs').fetchall():
        data = json.loads(raw)
        if data['status'] in ('queued', 'running'):
            data.update(status='error', error='El servidor se reinició. Puedes reintentar el trabajo.')
            c.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data), jid))

app = FastAPI(title='Clip Studio', version='0.1.0')
app.mount('/media/uploads', StaticFiles(directory=ROOT/'uploads'), name='uploads')
app.mount('/media/exports', StaticFiles(directory=ROOT/'exports'), name='exports')
processes = {}
cancellations = {}
render_lock = threading.Lock()
work_queue = queue.Queue()
queue_started = False
queue_start_lock = threading.Lock()
production_workers = {}
visible_records = lambda request, rows: rows
def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return uuid.uuid4().hex
def put(table, data):
    with db() as c: c.execute(f'INSERT OR REPLACE INTO {table} VALUES (?,?)', (data['id'], json.dumps(data, ensure_ascii=False)))
    return data
def get(table, key):
    with db() as c: row = c.execute(f'SELECT data FROM {table} WHERE id=?', (key,)).fetchone()
    if not row: raise HTTPException(404, 'No encontrado')
    return json.loads(row[0])
def all_rows(table):
    with db() as c: return [json.loads(r[0]) for r in c.execute(f'SELECT data FROM {table} ORDER BY rowid DESC')]
def ffmpeg():
    configured = os.getenv('FFMPEG_PATH') or shutil.which('ffmpeg')
    if configured: return configured
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()
def file_path(name):
    if not name or Path(name).name != name: raise ValueError('Archivo inválido')
    p = ROOT / 'uploads' / name
    if not p.is_file(): raise ValueError('Recurso no encontrado')
    return p
def font(size):
    candidates = ['C:/Windows/Fonts/arialbd.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']
    return next((ImageFont.truetype(p, size) for p in candidates if Path(p).exists()), ImageFont.load_default(size=size))

class Scene(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str = Field(default_factory=uid)
    text: str = Field(max_length=3000)
    overlay: str = Field(default='', max_length=300)
    duration: float = Field(default=6, ge=1, le=120)
    color: str = '#173c38'
    asset: str = ''
    audio: str = ''
    originalAudio: bool = False
    captions: list[dict] = Field(default_factory=list)
    start: float = Field(default=0, ge=0)
    zoom: float = Field(default=1, ge=1, le=3)
    x: float = Field(default=.5, ge=0, le=1)
    verified: bool = False
class Project(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str = Field(default_factory=uid,pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    title: str = Field(default='Sin título', max_length=150)
    scenes: list[Scene] = Field(default_factory=list, max_length=100)
    template: str = 'Documental'
    sources: list[dict] = Field(default_factory=list)
    hooks: list[str] = Field(default_factory=list)
    description: str = ''
    review: str = ''
    brand: str = '#b9e977'
    font: str = 'Arial'
    logo: str = ''
    voiceVolume: float = Field(default=1, ge=0, le=2)
    musicVolume: float = Field(default=.15, ge=0, le=1)
    music: str = ''
    updated: str = ''
class Create(BaseModel):
    text: str = Field(min_length=3, max_length=30000)
    mode: str = 'script'
    duration: int = Field(default=30, ge=5, le=300)
    template: str = 'Documental'
    audience: str = 'Público general'
    tone: str = 'Claro y cercano'
    sources: list[dict] = Field(default_factory=list)
class Brand(BaseModel):
    color: str = Field(default='#b9e977',pattern=r'^#[a-fA-F0-9]{6}$')
    font: str = 'Arial'
    logo: str = ''
@app.get('/api/brand')
def brand_profile():
    with db() as c: row=c.execute('SELECT data FROM settings WHERE id=?',('brand',)).fetchone()
    return json.loads(row[0]) if row else Brand().model_dump()
@app.put('/api/brand')
def save_brand(req: Brand): return put('settings',{'id':'brand',**req.model_dump()})

@app.get('/api/health')
def health():
    import importlib.util
    remote=os.getenv('CLIP_REMOTE','false').lower()=='true'
    return {'local': not remote,'remote':remote,'applicationUrl':os.getenv('CLIP_PUBLIC_URL') or os.getenv('RENDER_EXTERNAL_URL',''), 'ffmpeg': bool(ffmpeg()), 'piper': bool(os.getenv('PIPER_MODEL')) and importlib.util.find_spec('piper') is not None,
            'ollama': bool(os.getenv('OLLAMA_MODEL')), 'whisper': importlib.util.find_spec('faster_whisper') is not None,
            'external': os.getenv('EXTERNAL_ENABLED', 'true') == 'true', 'workspace': 'Almacenamiento privado del servidor' if remote else str(ROOT)}
@app.get('/api/projects')
def projects(request:Request): return visible_records(request,all_rows('projects'))
@app.get('/api/projects/{key}')
def project(key: str): return get('projects', key)
@app.put('/api/projects/{key}')
def save(key: str, p: Project):
    if key != p.id: raise HTTPException(400, 'ID inválido')
    data = p.model_dump(); data['updated'] = now()
    return put('projects', data)
@app.post('/api/create')
def create(req: Create):
    text = req.text
    if req.mode == 'topic':
        if not os.getenv('OLLAMA_MODEL'): raise HTTPException(409, 'Configura OLLAMA_MODEL o cambia a Guion y pega tu texto. No se han inventado datos.')
        try:
            r = httpx.post(os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434') + '/api/generate', timeout=180,
                json={'model': os.environ['OLLAMA_MODEL'], 'stream': False, 'format': 'json',
                      'prompt': f'Escribe un guion original en español de {req.duration} segundos para {req.audience}, tono {req.tone}. Tema: {text}. No inventes citas ni cifras. Devuelve JSON con title y scenes: lista de objetos text y overlay. Las afirmaciones se revisarán.'})
            r.raise_for_status(); generated = json.loads(r.json()['response'])
            scenes = [Scene(text=s['text'], overlay=s.get('overlay', '')).model_dump() for s in generated['scenes']]
            title = generated['title']
        except Exception as e: raise HTTPException(502, f'Ollama no disponible o respuesta inválida: {str(e)[:160]}')
    else:
        parts = [s.strip() for s in re.split(r'\n\s*\n|(?<=[.!?])\s+', text) if s.strip()]
        scenes = [Scene(text=s, overlay=' '.join(s.split()[:8]), duration=max(2, len(s.split()) / 2.5)).model_dump() for s in parts[:50]]
        title = ' '.join(text.split()[:9])[:100]
    palette={'Documental':['#173c38','#4a392a','#263d50'],'Podcast':['#333044','#242a3b'],'Noticias':['#153e5c','#263f64'],'Educativo':['#38543d','#405b57'],'Sin rostro':['#282b35','#3d384e']}.get(req.template,['#173c38','#263d50'])
    for i,s in enumerate(scenes): s['color']=palette[i%len(palette)]
    hooks = [f'¿Qué necesitas saber sobre {title.lower()}?', f'Por qué importa: {title}', f'Una pregunta pendiente: {title}']
    brand=brand_profile()
    return save_project(Project(title=title, scenes=scenes, sources=req.sources, hooks=hooks, template=req.template,brand=brand['color'],font=brand['font'],logo=brand['logo'],
        description=f'{title}\n\nUna explicación para abrir la conversación. #EnEspañol'))
def save_project(p):
    data = p.model_dump(); data['updated'] = now(); return put('projects', data)

@app.post('/api/upload')
async def upload(request:Request,file: UploadFile = File(...),clientId:str=Form(default='')):
    remote=os.getenv('CLIP_REMOTE','false').lower()=='true'
    if clientId:
        if 'production_protect' in globals():production_protect(request,{'clientId':clientId})
        get('clients',clientId)
    if remote and production_principal(request)['role']=='collaborator' and not clientId:raise HTTPException(403,'Selecciona primero un espacio de cliente autorizado antes de subir el recurso.')
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in ('.mp4', '.mov', '.mkv', '.webm', '.wav', '.mp3', '.m4a', '.png', '.jpg', '.jpeg'):
        raise HTTPException(400, 'Formato no admitido')
    name = uid() + suffix; p = ROOT / 'uploads' / name
    size = 0
    try:
        with p.open('wb') as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                limit=max(1,min(1024,int(os.getenv('CLIP_MAX_UPLOAD_MB','1024'))))*1024**2
                if size > limit: raise ValueError(f'El archivo supera el límite de {limit//1024**2} MB configurado en este servidor')
                out.write(chunk)
        if suffix in ('.png', '.jpg', '.jpeg'):
            with Image.open(p) as im: im.verify()
        else:
            test = subprocess.run([ffmpeg(), '-v', 'error', '-i', str(p), '-t', '0.1', '-f', 'null', '-'], capture_output=True, timeout=20)
            if test.returncode: raise ValueError('Archivo multimedia inválido')
        data={'id':name,'name': name, 'url': '/media/uploads/' + name, 'original': file.filename, 'size': size,'license':'Aportado por el usuario: comprobar autorización','author':'Usuario','attribution':'','created':now(),'clientId':clientId}
        put('assets',data)
        return data
    except Exception as e:
        p.unlink(missing_ok=True); raise HTTPException(400, str(e))
@app.get('/api/assets')
def assets(request:Request): return visible_records(request,all_rows('assets'))
class Rights(BaseModel):
    author: str = Field(max_length=300)
    license: str = Field(max_length=500)
    attribution: str = Field(default='',max_length=2000)
    source: str = Field(default='',max_length=2000)
@app.put('/api/assets/{key}')
def asset_rights(key: str,req: Rights):
    record=get('assets',key); record.update(req.model_dump()); return put('assets',record)

def safe_fetch(url):
    if os.getenv('EXTERNAL_ENABLED', 'true') != 'true': raise ValueError('Acceso externo desactivado; pega el texto para continuar.')
    # Pin the connection to an inspected address: DNS rebinding cannot change the destination.
    for _ in range(5):
        u = urlsplit(url)
        if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.port not in (None, 80, 443):
            raise ValueError('Solo HTTP/HTTPS público en puertos estándar')
        addresses = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == 'https' else 80), type=socket.SOCK_STREAM)
        ips = [x[4][0] for x in addresses]
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips): raise ValueError('Destino local, privado o reservado bloqueado')
        ip = ips[0]; host = u.hostname
        pinned = url.replace(u.netloc, f'[{ip}]' if ':' in ip else ip, 1)
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            with client.stream('GET', pinned, headers={'Host': host, 'User-Agent': 'ClipStudio/0.1'}, extensions={'sni_hostname': host.encode()}) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers['location']); continue
                r.raise_for_status()
                if not any(t in r.headers.get('content-type', '') for t in ('text/', 'xml', 'json')): raise ValueError('Contenido no textual')
                content = bytearray(); started = time.monotonic()
                for chunk in r.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 2_000_000 or time.monotonic() - started > 20: raise ValueError('Descarga excede el límite')
                return bytes(content), url
    raise ValueError('Demasiadas redirecciones')
class Link(BaseModel):
    url: str
@app.post('/api/extract')
def extract(req: Link):
    try:
        if any(x in (urlsplit(req.url).hostname or '') for x in ('youtube.com', 'youtu.be', 'tiktok.com')):
            raise ValueError('Pega una transcripción autorizada. El enlace se conservará como fuente; no se descarga video de terceros.')
        raw, url = safe_fetch(req.url); soup = BeautifulSoup(raw, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']): tag.decompose()
        title = soup.title.get_text(' ', strip=True) if soup.title else url
        paragraphs = (soup.find('article') or soup.find('main') or soup).find_all('p')
        text = '\n\n'.join(p.get_text(' ', strip=True) for p in paragraphs)[:30000]
        if len(text) < 50: raise ValueError('No se pudo extraer texto suficiente; pega el contenido autorizado.')
        published=soup.find('meta',attrs={'property':'article:published_time'}) or soup.find('meta',attrs={'name':'date'})
        return {'text': text, 'source': {'url': url, 'title': title, 'accessed': now(), 'published':published.get('content') if published else None,'verified': False}}
    except Exception as e: raise HTTPException(422, f'No se pudo leer el enlace. {str(e)[:200]}')

rss_cache = {}
@app.get('/api/trends')
def trends(country: str = 'DO', category: str = 'Todas', period: int = 7):
    url = os.getenv('RSS_URL', 'https://feeds.bbci.co.uk/mundo/rss.xml')
    try:
        cached = rss_cache.get(url)
        if not cached or time.time() - cached[0] > 900:
            raw, _ = safe_fetch(url); root = ElementTree.fromstring(raw)
            items = [{'title': i.findtext('title'), 'url': i.findtext('link'), 'date': i.findtext('pubDate'), 'source': 'RSS · ' + urlsplit(url).hostname, 'signal': None} for i in root.findall('.//item')[:40]]
            rss_cache[url] = (time.time(), items)
        else: items = cached[1]
        from email.utils import parsedate_to_datetime
        items = [i for i in items if i['date'] and (datetime.now(timezone.utc)-parsedate_to_datetime(i['date'])).total_seconds() <= max(1,min(period,30))*86400]
        if category != 'Todas': items = [i for i in items if category.casefold() in i['title'].casefold()]
        return {'items': items, 'notice': f'Actualidad editorial en español. Esta fuente no ofrece interés, categorías ni datos por país ({country}). El filtro de categoría busca palabras en el título. No es un ranking de tendencias.'}
    except Exception as e: raise HTTPException(502, f'RSS no disponible: {e}. Puedes registrar un tema manualmente.')

def update_job(jid, **changes):
    data = get('jobs', jid)
    if data['status'] == 'cancelled' and changes.get('status') != 'cancelled': return data
    data.update(changes); return put('jobs', data)
def check_cancel(jid):
    if cancellations[jid].is_set(): raise InterruptedError('Trabajo cancelado')
def run_process(jid, args, **kwargs):
    check_cancel(jid)
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs) as p:
        processes[jid] = p
        if cancellations[jid].is_set(): p.terminate()
        try:
            _, err = p.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            p.kill(); p.communicate(); raise ValueError('Tiempo máximo de proceso excedido')
        finally: processes.pop(jid, None)
        check_cancel(jid)
        if p.returncode: raise ValueError(err.decode(errors='replace')[-1500:])
def start_job(kind, payload, work):
    global queue_started
    jid = uid(); cancellations[jid] = threading.Event()
    data = {'id': jid, 'kind': kind, 'status': 'queued', 'progress': 0, 'created': now(), 'payload': payload}
    put('jobs', data)
    def target():
        while True:
            nextid,task,task_payload=work_queue.get()
            try:
                with render_lock:
                    check_cancel(nextid); update_job(nextid, status='running')
                    result = task(nextid, task_payload)
                    check_cancel(nextid); update_job(nextid, status='done', progress=100, result=result)
            except InterruptedError: update_job(nextid, status='cancelled')
            except Exception as e: update_job(nextid, status='error', error=str(e)[:1800])
            finally:work_queue.task_done()
    with queue_start_lock:
        if not queue_started:
            threading.Thread(target=target, daemon=True).start();queue_started=True
    work_queue.put((jid,work,payload))
    return data
@app.get('/api/jobs')
def jobs(request:Request): return visible_records(request,all_rows('jobs'))[:50]
@app.post('/api/jobs/{jid}/cancel')
def cancel(jid: str):
    data = get('jobs', jid)
    if data['status'] in ('done', 'error', 'cancelled'): return data
    cancellations[jid].set()
    if jid in processes:
        try: processes[jid].terminate()
        except OSError: pass
    return update_job(jid, status='cancelled')

def wrap(draw, text, f, max_width):
    lines = []; line = ''
    for word in text.split():
        test = (line + ' ' + word).strip()
        if draw.textlength(test, font=f) > max_width and line: lines.append(line); line = word
        else: line = test
    return lines + ([line] if line else [])
def card(scene, path, width, height, brand, logo='', family='Arial', transparent=False, settings=None):
    settings=settings or {}
    color = scene.get('color', '#173c38')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color): color = '#173c38'
    im = Image.new('RGBA' if transparent else 'RGB', (width, height), (0,0,0,0) if transparent else color); d = ImageDraw.Draw(im)
    f = font(int(width * .07)); small = font(int(width * .025))
    chosen={'Georgia':'georgiab.ttf','Consolas':'consolab.ttf'}.get(family)
    if chosen and Path('C:/Windows/Fonts',chosen).exists(): f=ImageFont.truetype(str(Path('C:/Windows/Fonts',chosen)),int(width*.07))
    d.rounded_rectangle((width*.1, height*.16, width*.24, height*.166), radius=3, fill=brand if re.fullmatch(r'#[0-9a-fA-F]{6}', brand) else '#b9e977')
    d.text((width*.1,height*.12), 'CLIP STUDIO / HISTORIAS EN ESPAÑOL', font=small, fill='#cfe1d6')
    lines = wrap(d, scene.get('overlay') or scene['text'], f, width*.78)
    y = height*float(settings.get('overlayY',.36))
    for line in lines[:9]: d.text((width*.1,y), line, font=f, fill=settings.get('textColor','#ffffff')); y += width*.09
    if settings.get('isCover'):
        template=settings.get('cover','Documental')
        labels={'Documental':'UNA HISTORIA PARA ENTENDER','Podcast':'IDEAS EN CONVERSACIÓN','Noticias':'CONTEXTO Y ACTUALIDAD','Educativo':'APRENDE PASO A PASO','Sin rostro':'UNA NUEVA PERSPECTIVA'}
        label=labels.get(template,template.upper());accent=brand if re.fullmatch(r'#[0-9a-fA-F]{6}',brand) else '#b9e977'
        if template in ('Noticias','Educativo'):
            d.rounded_rectangle((width*.1,height*.84,width*.9,height*.9),radius=width*.012,fill=accent)
            rgb=tuple(int(accent[i:i+2],16) for i in (1,3,5));ink='#193428' if sum(a*b for a,b in zip(rgb,(.299,.587,.114)))>150 else '#ffffff'
            d.text((width*.13,height*.861),label,font=small,fill=ink)
        else:
            d.line((width*.1,height*.84,width*.9,height*.84),fill=accent,width=max(1,int(width*.003)))
            d.text((width*.1,height*.865),label,font=small,fill=accent)
            if template=='Podcast':
                for index in range(3):
                    cx=width*(.77+index*.035);d.rounded_rectangle((cx,height*(.76-index*.008),cx+width*.014,height*(.81+index*.008)),radius=3,fill=accent)
    if logo:
        with Image.open(file_path(logo)).convert('RGBA') as badge:
            badge.thumbnail((int(width*.16),int(height*.07)))
            im.paste(badge,(int(width*float(settings.get('logoX',.74))),int(height*float(settings.get('logoY',.11)))),badge)
    im.save(path)
def stamp(t):
    ms = round(t*1000); return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
def caption_events(scenes):
    events=[]; t=0
    for s in scenes:
        if s.get('captions'):
            for c in s['captions']:
                start=max(0,float(c['start'])); end=min(s['duration'],float(c['end']))
                if end>start: events.append({'start':t+start,'end':t+end,'text':c['text'],'words':[{**w,'start':float(w['start'])-start,'end':float(w['end'])-start} for w in c.get('words',[])]})
        else:
            words=s['text'].split(); count=max(1,len(words))
            for i in range(0,len(words),7):
                phrase=' '.join(words[i:i+7]); start=t+s['duration']*i/count; end=t+s['duration']*min(i+7,count)/count
                events.append({'start':start,'end':end,'text':phrase,'words':[]})
        t+=s['duration']
    return events
def srt(scenes):
    return '\n'.join(f"{i+1}\n{stamp(e['start'])} --> {stamp(e['end'])}\n{e['text']}\n" for i,e in enumerate(caption_events(scenes)))
def ass(scenes,settings=None):
    settings=settings or {}
    header='[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,Arial,52,&H0000EFFF,&H00FFFFFF,&H00151515,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,110,130,355,1\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'
    def asscolor(color):
        value=color.lstrip('#')
        if not re.fullmatch('[a-fA-F0-9]{6}',value):value='ffffff'
        return '&H00'+value[4:6]+value[2:4]+value[0:2]
    family=settings.get('font','Arial')
    if family not in ('Arial','Georgia','Consolas','DejaVu Sans'):family='Arial'
    style=f"Style: Default,{family},{int(settings.get('subtitleSize',52))},{asscolor(settings.get('highlightColor','#efff00'))},{asscolor(settings.get('subtitleColor','#ffffff'))},&H00151515,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,110,130,{int(settings.get('subtitleMargin',355))},1"
    header=re.sub(r'Style: Default[^\n]+',lambda _:style,header)
    def at(t):
        cs=round(t*100)
        return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'
    def clean(text): return str(text).replace('\\','').replace('{','').replace('}','').replace('\n',' ')
    for e in caption_events(scenes):
        text=clean(e['text'])
        if e['words']:
            text=''; cursor=0
            for w in e['words']:
                start=max(cursor,float(w['start'])); end=max(start,float(w['end']))
                if start>cursor: text+='{\\k'+str(round((start-cursor)*100))+'} '
                text+='{\\kf'+str(max(1,round((end-start)*100)))+'}'+clean(w['word']).strip()+' '
                cursor=end
        else: text='{\\c'+asscolor(settings.get('subtitleColor','#ffffff')).replace('&H00','&H',1)+'&}'+text
        header+=f"Dialogue: 0,{at(e['start'])},{at(e['end'])},Default,,0,0,0,,{text}\n"
    return header
def render(jid, payload):
    p = payload['project']; scenes = p['scenes']
    render_threads=max(1,min(8,int(os.getenv('CLIP_RENDER_THREADS','2'))))
    if not scenes: raise ValueError('Añade una escena')
    width,height = (720,1280) if payload['resolution']==720 else (1080,1920)
    work = ROOT/'jobs'/jid; work.mkdir()
    for i,s in enumerate(scenes):
        check_cancel(jid); update_job(jid, progress=int(i/len(scenes)*80), message=f'Escena {i+1} de {len(scenes)}')
        audio = file_path(s['audio']) if s.get('audio') else None
        if payload.get('voice') == 'piper' and not audio:
            model=os.getenv('PIPER_MODEL')
            if not model: raise ValueError('Configura PIPER_MODEL o carga una narración propia. También puedes elegir Sin voz.')
            audio=work/f'voice{i}.wav'; textfile=work/f'voice{i}.txt'; textfile.write_text(s['text'],encoding='utf-8')
            run_process(jid,[sys.executable,'-m','piper','-m',str(Path(model).resolve()),'-f',str(audio),'--input-file',str(textfile)])
            import wave
            with wave.open(str(audio)) as w: s['duration']=max(s['duration'], w.getnframes()/w.getframerate()+.15)
        image=work/f'card{i}.png'; card(s,image,width,height,p.get('brand','#b9e977'),p.get('logo',''),p.get('font','Arial'),settings=p.get('brandSnapshot'))
        args=[ffmpeg(),'-y','-v','error','-filter_complex_threads',str(render_threads)]
        asset = file_path(s['asset']) if s.get('asset') else image
        is_image=asset.suffix.lower() in ('.png','.jpg','.jpeg')
        if is_image: args+=['-loop','1','-i',str(asset)]
        else: args+=['-ss',str(s.get('start',0)),'-i',str(asset)]
        if audio: args+=['-i',str(audio)]
        elif not (s.get('originalAudio') and not is_image): args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
        from backend.framing import video_graph
        graph=video_graph(s,width,height)
        subtitle=work/f'scene{i}.ass'; subtitle.write_text(ass([s],{**(p.get('brandSnapshot') or {}),'font':p.get('font','Arial')}),encoding='utf-8')
        subtitles=f',ass=scene{i}.ass' if payload.get('burn',True) else ''
        video_filter=['-filter_complex',graph+f';[basev]null{subtitles}[outv]']
        video_map='[outv]'
        if s.get('asset') and s.get('overlay'):
            layer=work/f'overlay{i}.png'
            card(s,layer,width,height,p.get('brand','#b9e977'),p.get('logo',''),p.get('font','Arial'),transparent=True,settings=p.get('brandSnapshot'))
            layer_index=1 if s.get('originalAudio') and not is_image and not audio else 2
            args+=['-loop','1','-i',str(layer)]
            video_filter=['-filter_complex',graph+f';[basev][{layer_index}:v]overlay=0:0{subtitles}[outv]']
            video_map='[outv]'
        audio_map = '0:a:0' if s.get('originalAudio') and not is_image and not audio else '1:a:0'
        args+=['-t',str(s['duration']),'-map',video_map,'-map',audio_map,*video_filter,'-af',f"apad,volume={p.get('voiceVolume',1)}",'-c:v','libx264','-threads',str(render_threads),'-preset','ultrafast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2',str(work/f'{i}.mp4')]
        run_process(jid,args,cwd=work)
    (work/'concat.txt').write_text('\n'.join(f"file '{i}.mp4'" for i in range(len(scenes))),encoding='utf-8')
    base=f"{p['id'][:8]}-{payload.get('variant','A')}-{jid}"; output=ROOT/'exports'/f'{base}.mp4'
    args=[ffmpeg(),'-y','-v','error','-f','concat','-safe','0','-i',str(work/'concat.txt')]
    if p.get('music'):
        args+=['-stream_loop','-1','-i',str(file_path(p['music'])),'-filter_complex',f"[1:a]volume={p.get('musicVolume',.15)}[m];[0:a]asplit=2[v][sc];[m][sc]sidechaincompress=threshold=0.02:ratio=8[duck];[v][duck]amix=inputs=2:duration=first:normalize=0[a]",'-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-shortest']
    else: args+=['-c','copy']
    args+=['-movflags','+faststart',str(output)]
    run_process(jid,args,cwd=work)
    used={s.get(k) for s in scenes for k in ('asset','audio')}|{p.get('music'),p.get('logo')}
    resources=[a for a in all_rows('assets') if a['name'] in used]
    is_sharvard='es_ES-sharvard-medium' in os.getenv('PIPER_MODEL','')
    voice_credit={'engine':'Piper GPL-3.0-or-later','model':os.getenv('PIPER_MODEL'),'model_card':os.getenv('PIPER_MODEL_CARD') or ('https://huggingface.co/rhasspy/piper-voices/blob/main/es/es_ES/sharvard/medium/MODEL_CARD' if is_sharvard else ''),'attribution':os.getenv('PIPER_ATTRIBUTION') or ('Spanish Harvard corpus, University of Edinburgh, CC BY 3.0; adapted using Piper.' if is_sharvard else 'Consult the voice MODEL_CARD and enter attribution.')}
    for ext,content in [('srt',srt(scenes)),('txt',p.get('description','')),('credits.json',json.dumps({'sources':p.get('sources',[]),'review':p.get('review',''),'assets':resources,'voice':voice_credit if payload.get('voice')=='piper' else 'Audio propio o silencio'},ensure_ascii=False,indent=2))]:
        (ROOT/'exports'/f'{base}.{ext}').write_text(content,encoding='utf-8')
    cover_scene={**scenes[0],'overlay':p.get('coverText') or scenes[0].get('overlay') or p['title']}
    card(cover_scene,ROOT/'exports'/f'{base}.png',width,height,p.get('brand','#b9e977'),p.get('logo',''),p.get('font','Arial'),settings={**(p.get('brandSnapshot') or {}),'isCover':True,'cover':(p.get('brandSnapshot') or {}).get('cover',p.get('template','Documental'))})
    return {'video':f'/media/exports/{base}.mp4','srt':f'/media/exports/{base}.srt','cover':f'/media/exports/{base}.png','text':f'/media/exports/{base}.txt','credits':f'/media/exports/{base}.credits.json','duration':sum(s['duration'] for s in scenes),'scenes':scenes,'projectId':p['id']}
class Export(BaseModel):
    resolution: int = 720
    voice: str = 'none'
    burn: bool = True
    variant: str = Field(default='A',pattern=r'^[a-zA-Z0-9_-]{1,40}$')
    hook: str = ''
@app.post('/api/projects/{key}/render')
def export(key: str, req: Export):
    p = get('projects',key)
    if req.hook and p['scenes']: p['scenes'][0].update(text=req.hook,overlay=req.hook,duration=max(3,len(req.hook.split())/2.5),audio='',originalAudio=False,captions=[])
    return start_job('render', {'project':p,**req.model_dump()},render)

def voice_work(jid,payload):
    model=os.getenv('PIPER_MODEL')
    if not model: raise ValueError('Configura PIPER_MODEL o carga una narración propia.')
    work=ROOT/'jobs'/jid; work.mkdir()
    text=work/'text.txt'; text.write_text(payload['text'],encoding='utf-8')
    name=uid()+'.wav'; audio=ROOT/'uploads'/name
    run_process(jid,[sys.executable,'-m','piper','-m',str(Path(model).resolve()),'-f',str(audio),'--input-file',str(text)])
    import wave
    with wave.open(str(audio)) as w: duration=w.getnframes()/w.getframerate()
    return {'audio':name,'url':'/media/uploads/'+name,'duration':duration+.15,'sceneId':payload['sceneId'],'projectId':payload['projectId'],'spoken':payload['text']}
@app.post('/api/projects/{key}/scenes/{index}/voice')
def generate_scene_voice(key: str,index: int):
    p=get('projects',key)
    if not 0<=index<len(p['scenes']): raise HTTPException(404,'Escena no encontrada')
    s=p['scenes'][index]
    return start_job('voice',{'projectId':key,'clientId':p.get('clientId',''),'sceneId':s['id'],'text':s['text']},voice_work)

class Transcribe(BaseModel):
    asset: str
    target: int = Field(default=30,ge=15,le=90)
    segments: list[dict] = Field(default_factory=list)
def transcribe_work(jid,payload):
    asset=file_path(payload['asset']); segments=payload.get('segments')
    if not segments:
        try: from faster_whisper import WhisperModel
        except ImportError: raise ValueError('Instala requirements-optional.txt o importa una transcripción JSON con start, end y text.')
        device=os.getenv('WHISPER_DEVICE','cpu'); model=WhisperModel(os.getenv('WHISPER_MODEL','small'),device=device,compute_type='int8' if device=='cpu' else 'float16')
        stream,info=model.transcribe(str(asset),language='es',word_timestamps=True,vad_filter=True)
        segments=[]
        for s in stream:
            check_cancel(jid); segments.append({'start':s.start,'end':s.end,'text':s.text,'words':[{'start':w.start,'end':w.end,'word':w.word} for w in (s.words or [])]})
            update_job(jid,progress=min(90,int(s.end/max(info.duration,1)*90)))
    segments=sorted(segments,key=lambda s:float(s['start']))
    clips=[]; cursor=0
    while cursor<len(segments) and len(clips)<10:
        first=segments[cursor]; chosen=[]; start=float(first['start']); end=start
        while cursor<len(segments):
            s=segments[cursor]; chosen.append(s); end=float(s['end']); cursor+=1
            if end-start>=payload['target']: break
        if end<=start: continue
        text=' '.join(s['text'] for s in chosen)
        reason='Corte en límite de segmento de transcripción. Revisa que la idea se entienda sin el contexto anterior.'
        if '?' in text or '¿' in text: reason='Contiene una pregunta; revisa que la respuesta quede dentro del corte.'
        clips.append({'start':start,'end':end,'text':text,'reason':reason,'segments':chosen})
    return {'clips':clips,'segments':segments,'asset':payload['asset'],'notice':'Selección heurística por segmentos, sin predicción de rendimiento. El número depende de la duración disponible.'}
@app.post('/api/transcribe')
def transcribe(req: Transcribe,request:Request):
    try: file_path(req.asset)
    except ValueError as e: raise HTTPException(400,str(e))
    payload=req.model_dump()
    if 'production_protect_resources' in globals():
        scopes=production_protect_resources(request,payload)
        if scopes:payload['clientId']=scopes[0]
    return start_job('transcribe',payload,transcribe_work)
@app.post('/api/jobs/{jid}/retry')
def retry(jid: str):
    old=get('jobs',jid)
    if old['status'] not in ('error','cancelled'): raise HTTPException(409,'Solo se reintentan trabajos fallidos o cancelados')
    worker={**{'render':render,'voice':voice_work,'transcribe':transcribe_work},**production_workers}[old['kind']]
    if old['kind'] in production_workers:return production_enqueue(old['kind'],old['payload'],worker)
    return start_job(old['kind'],old['payload'],worker)
@app.get('/api/metrics')
def metrics(request:Request): return visible_records(request,all_rows('metrics'))
class Metric(BaseModel):
    model_config=ConfigDict(allow_inf_nan=False)
    project: str
    variant: str
    platform: str
    period: str
    views: float | None = Field(default=None, ge=0)
    average: float | None = Field(default=None, ge=0)
    watched: float | None = Field(default=None, ge=0, le=100)
    interactions: float | None = Field(default=None, ge=0)
    followers: float | None = None
    account: str = ''
    publicationId: str = ''
    publishedAt: str = ''
    window: str = ''
    hookType: str = ''
    duration: float | None = None
    template: str = ''
    format: str = '9:16'
@app.post('/api/metrics')
def metric(req: Metric,request:Request):
    if 'production_metric' in globals():return production_metric(req.model_dump(),request)
    return put('metrics',{'id':uid(),**req.model_dump()})
@app.post('/api/metrics/import')
async def import_metrics(request:Request,file: UploadFile=File(...)):
    raw=await file.read(1_000_001)
    if len(raw)>1_000_000: raise HTTPException(413,'CSV demasiado grande')
    try:
        rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        validated=[Metric(**{k:(None if v=='' and k in ('views','average','watched','interactions','followers') else v) for k,v in r.items()}) for r in rows]
        if 'production_metric_import' in globals():return production_metric_import([r.model_dump() for r in validated],request)
        return [metric(r,request) for r in validated]
    except Exception as e: raise HTTPException(422,str(e))

if not all_rows('projects'):
    save_project(Project(title='Una pausa también es progreso',template='Documental',description='Un pequeño recordatorio para tu día. #Pausa #Bienestar',
        hooks=['¿Y si avanzar también fuera detenerte?','Una pausa también es progreso.','Prueba esto antes de seguir con tu día.'],
        scenes=[Scene(text='A veces, una pausa es el primer paso para volver a concentrarte.',overlay='Una pausa también es progreso',duration=6,verified=True),Scene(text='Deja la pantalla un momento. Mira a tu alrededor y respira a tu ritmo.',overlay='Baja el ritmo. Vuelve a mirar.',duration=7,color='#4a392a',verified=True),Scene(text='Elige una sola tarea pequeña para continuar. Esta es una invitación, no una regla.',overlay='Un paso pequeño. Una nueva perspectiva.',duration=7,color='#263d50',verified=True)],review='Demostración editorial original. Tarjetas generadas localmente; sin afirmaciones médicas.'))

import backend.production
backend.production.install(app,sys.modules[__name__])
from backend.cloud import install_cloud
install_cloud(app,sys.modules[__name__])

# Cross-origin API access is opt-in; the local editor keeps its current network policy.
allowed_origins=[x.strip() for x in os.getenv('CLIP_ALLOWED_ORIGINS','').split(',') if x.strip()]
if allowed_origins:
    if '*' in allowed_origins:raise ValueError('CLIP_ALLOWED_ORIGINS requiere orígenes explícitos; no se admite *.')
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware,allow_origins=allowed_origins,allow_credentials=False,allow_methods=['GET','POST','PUT'],allow_headers=['Content-Type','Authorization','x-owner-key'])
