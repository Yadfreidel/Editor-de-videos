"""Production extension. Uses the existing SQLite JSON records, queue and renderer."""
import copy
import csv
import hashlib
import io
import json
import secrets
import shutil
import sqlite3
import threading
import time
import zipfile
from pathlib import Path
from datetime import datetime,timezone

from fastapi import HTTPException, Request, UploadFile, File, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel,Field
from backend.migrations import migrate

RENDER_REVISION='production-2026-11-11-v1'

class Profile(BaseModel):
    name: str=Field(min_length=1,max_length=100)
    color: str=Field(default='#b9e977',pattern=r'^#[0-9a-fA-F]{6}$')
    background: str=Field(default='#173c38',pattern=r'^#[0-9a-fA-F]{6}$')
    textColor: str=Field(default='#ffffff',pattern=r'^#[0-9a-fA-F]{6}$')
    font: str='Arial'
    logo: str=''
    subtitleSize: int=Field(default=52,ge=24,le=96)
    subtitleColor: str=Field(default='#ffffff',pattern=r'^#[0-9a-fA-F]{6}$')
    highlightColor: str=Field(default='#efff00',pattern=r'^#[0-9a-fA-F]{6}$')
    subtitleMargin: int=Field(default=355,ge=100,le=800)
    overlayY: float=Field(default=.36,ge=.18,le=.7)
    logoX: float=Field(default=.74,ge=0,le=.84)
    logoY: float=Field(default=.11,ge=0,le=.9)
    cover: str='Documental'

class BatchInput(BaseModel):
    name: str=Field(default='Mi lote',min_length=1,max_length=150)
    asset: str
    authorized: bool
    count: int=Field(default=5,ge=1,le=10)
    target: int=Field(default=30,ge=15,le=90)
    brandId: str=''
    clientId: str=''
    segments: list[dict]=Field(default_factory=list)

class ClipDecision(BaseModel):
    status: str=Field(pattern='^(pending|approved|discarded)$')
    variant: str=Field(default='A',pattern='^[AB]$')

class BatchExport(BaseModel):
    resolution: int=Field(default=720)
    voice: str='none'
    burn: bool=True
    retryFailed: bool=False

class ApplyBrand(BaseModel):
    brandId: str
    projectIds: list[str]
    confirmed: bool=False

def fingerprint(data):
    def stable(value):
        if isinstance(value,dict):return {k:stable(v) for k,v in value.items() if k not in ('updated','created')}
        if isinstance(value,list):return [stable(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(stable(data),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def install(app,c):
    """c is the existing backend module; no second processing queue is introduced."""
    root=c.ROOT
    try: migration=migrate(c.DB)
    except Exception as e:
        migration_error=str(e)
        @app.middleware('http')
        async def failed_closed(request,call_next):
            if request.url.path.startswith(('/api/','/media/')) and request.url.path not in ('/api/production/status','/api/health'):
                return JSONResponse(status_code=503,content={'detail':'Migración pendiente: el acceso a datos está suspendido para conservar los permisos. Consulta /api/production/status y reinicia tras corregir el problema.'})
            return await call_next(request)
        @app.get('/api/production/status')
        def failed():return JSONResponse(status_code=503,content={'error':'Migración no aplicada. Los datos anteriores se conservan. Reinicia tras resolver el error.','detail':migration_error})
        return
    (root/'private_reviews').mkdir(exist_ok=True)
    ownerfile=root/'owner-access.txt'
    configured_key=c.os.getenv('CLIP_OWNER_KEY','')
    if c.os.getenv('CLIP_REMOTE','false').lower()=='true' and len(configured_key)<32:raise RuntimeError('Configura CLIP_OWNER_KEY como secreto de al menos 32 caracteres antes de publicar.')
    if not configured_key and not ownerfile.exists():ownerfile.write_text(secrets.token_urlsafe(32),encoding='utf-8')
    ownerkey=configured_key or ownerfile.read_text(encoding='utf-8').strip()
    request_lock=threading.RLock(); batch_lock=threading.RLock()

    def principal(request):
        bearer=request.headers.get('authorization','').removeprefix('Bearer ').strip()
        token=bearer or request.headers.get('x-owner-key') or request.cookies.get('clip_owner','')
        if token and secrets.compare_digest(token.encode(),ownerkey.encode()):return {'role':'owner'}
        if token:
            hashed=hashlib.sha256(token.encode()).hexdigest()
            for item in c.all_rows('principals'):
                if secrets.compare_digest(item['hash'],hashed) and not item.get('revoked'):return item
        return {'role':'anonymous'}
    def can_client(request,clientid,write=False):
        who=principal(request)
        return who['role']=='owner' or (who['role']=='collaborator' and clientid in who.get('clients',[]))
    def require_owner(request):
        if principal(request)['role']!='owner':raise HTTPException(403,'Desbloquea la sesión del propietario con la clave local.')
    def protect(request,record):
        project=record.get('project',{})
        if isinstance(project,str):
            try:project=c.get('projects',project)
            except HTTPException:project={}
        clientid=record.get('clientId') or project.get('clientId') or record.get('payload',{}).get('project',{}).get('clientId') or record.get('payload',{}).get('clientId')
        if c.os.getenv('CLIP_REMOTE','false').lower()=='true' and principal(request)['role']=='collaborator' and not clientid:raise HTTPException(403,'Este acceso solo permite trabajar en los espacios de cliente asignados.')
        if record.get('name') and record.get('url','').startswith('/media/uploads/'):
            for p in c.all_rows('projects'):
                if p.get('clientId') and record['name'] in json.dumps(p) and not can_client(request,p['clientId']):raise HTTPException(403,'Recurso de un cliente protegido')
        if clientid and not can_client(request,clientid):raise HTTPException(403,'Este espacio requiere autorización de su propietario o colaborador.')
        return record
    def visible(request,rows):
        out=[]
        for r in rows:
            try:protect(request,r);out.append(r)
            except HTTPException:pass
        return out
    c.visible_records=visible

    def protect_resources(request,body):
        names=set();scopes=set()
        def walk(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key in ('asset','audio','music','logo') and isinstance(item,str) and item:names.add(item)
                    walk(item)
            elif isinstance(value,list):
                for item in value:walk(item)
        walk(body)
        if names:
            for a in c.all_rows('assets'):
                if a.get('name') in names and a.get('clientId'):protect(request,a);scopes.add(a['clientId'])
            for p in c.all_rows('projects'):
                if p.get('clientId') and any(n in json.dumps(p) for n in names):protect(request,p);scopes.add(p['clientId'])
            for b in c.all_rows('batches'):
                if b.get('clientId') and b.get('asset') in names:protect(request,b);scopes.add(b['clientId'])
        return sorted(scopes)

    @app.middleware('http')
    async def private_guard(request,call_next):
        path=request.url.path
        try:
            # Reviewer capabilities never authorize access to the owner's API or static directories.
            token=request.headers.get('authorization','').removeprefix('Bearer ')
            if token and any(secrets.compare_digest(t['hash'],hashlib.sha256(token.encode()).hexdigest()) for t in c.all_rows('review_tokens')) and not path.startswith('/api/reviewer/'):
                raise HTTPException(403,'Este enlace solo permite revisar su versión asignada.')
            if request.method in ('POST','PUT') and 'application/json' in request.headers.get('content-type',''):
                body=await request.json();protect_resources(request,body)
                if path=='/api/metrics':protect(request,body)
            if path.startswith('/api/projects/'):
                key=path.split('/')[3]
                try:existing=c.get('projects',key)
                except HTTPException:existing={}
                protect(request,existing)
                protect_resources(request,existing)
                if request.method=='PUT':
                    body=await request.json();protect(request,body)
                    if existing.get('clientId') and body.get('clientId')!=existing['clientId']:raise HTTPException(409,'No se puede quitar o cambiar el espacio desde el editor.')
            if path.startswith('/api/jobs/'):
                jid=path.split('/')[3]
                try:protect(request,c.get('jobs',jid))
                except HTTPException as e:
                    if e.status_code!=404:raise
            if path.startswith('/api/assets/'):
                try:protect(request,c.get('assets',path.split('/')[3]))
                except HTTPException as e:
                    if e.status_code!=404:raise
            if path.startswith('/media/'):
                name=Path(path).name
                for a in c.all_rows('assets'):
                    if a.get('name')==name:protect(request,a)
                for b in c.all_rows('batches'):
                    if b.get('asset')==name:protect(request,b)
                for j in c.all_rows('jobs'):
                    if name in json.dumps(j.get('result',{})):protect(request,j)
                for p in c.all_rows('projects'):
                    if p.get('clientId') and (name in json.dumps(p) or name==f"thumb-{p['id']}.jpg"):protect(request,p)
            return await call_next(request)
        except HTTPException as e:return JSONResponse(status_code=e.status_code,content={'detail':e.detail})

    @app.get('/api/production/status')
    def status(request:Request):return {'migration':migration,'role':principal(request)['role'],'remoteConfigured':c.os.getenv('CLIP_REMOTE','false').lower()=='true','ownerKeyFile':None if configured_key else str(ownerfile),'levels':{'Individual':['Editor local','Narración','Exportación'],'Pro':['Lotes','Perfiles de marca','Análisis'],'Agencia':['Clientes','Colaboradores','Revisión privada']}}
    class Login(BaseModel):key:str
    @app.post('/api/access/login')
    def login(req:Login,response:Response):
        role='owner' if secrets.compare_digest(req.key.encode(),ownerkey.encode()) else None
        if not role:
            hashed=hashlib.sha256(req.key.encode()).hexdigest()
            role=next((p['role'] for p in c.all_rows('principals') if secrets.compare_digest(p['hash'],hashed) and not p.get('revoked')),None)
        if not role:raise HTTPException(403,'Clave local incorrecta o revocada')
        response.set_cookie('clip_owner',req.key,httponly=True,samesite='strict',secure=c.os.getenv('CLIP_REMOTE','false').lower()=='true',max_age=86400)
        return {'role':role}
    @app.post('/api/access/logout')
    def logout(response:Response):response.delete_cookie('clip_owner');return {'role':'anonymous'}

    @app.get('/api/brands')
    def brands(request:Request):return visible(request,c.all_rows('brand_profiles'))
    @app.post('/api/brands')
    def create_brand(req:Profile):return c.put('brand_profiles',{'id':c.uid(),**req.model_dump(),'updated':c.now()})
    @app.put('/api/brands/{key}')
    def update_brand(key:str,req:Profile):
        c.get('brand_profiles',key);return c.put('brand_profiles',{'id':key,**req.model_dump(),'updated':c.now()})
    @app.post('/api/brands/{key}/duplicate')
    def duplicate_brand(key:str):
        b=c.get('brand_profiles',key);b.update(id=c.uid(),name=b['name']+' · copia',updated=c.now());return c.put('brand_profiles',b)
    @app.post('/api/brands/preview')
    def preview_brand(req:Profile,request:Request):
        b=req.model_dump();scopes=protect_resources(request,{'logo':b.get('logo','')})
        p=c.Project(id='brand-preview-'+fingerprint(b)[:24],title='Vista previa visual de marca',scenes=[c.Scene(text='Tu historia conserva su identidad. Cada palabra cuenta.',overlay='Una historia con identidad.',duration=4,color=b['background'])],brand=b['color'],font=b['font'],logo=b['logo'],template=b['cover']).model_dump()
        p.update(brandSnapshot=b,clientId=scopes[0] if scopes else '')
        job=enqueue_unique('brand-preview',{'project':p,'resolution':720,'voice':'none','burn':True,'variant':'MARCA'},c.render)
        return {**job,'warnings':brand_warnings(b)}
    def brand_warnings(b):
        warnings=[]
        if b.get('logo'):
            try:c.file_path(b['logo'])
            except ValueError:warnings.append('Logo no encontrado: '+b['logo']+'. Reemplázalo en el perfil.')
        candidates={'Arial':['C:/Windows/Fonts/arialbd.ttf','/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf'],'Georgia':['C:/Windows/Fonts/georgiab.ttf'],'Consolas':['C:/Windows/Fonts/consolab.ttf'],'DejaVu Sans':['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']}
        if b.get('font') not in candidates or not any(Path(p).exists() for p in candidates.get(b.get('font'),[])):warnings.append('Fuente no disponible: '+b.get('font','')+'. Se usará la fuente alternativa; elige otra para mantener el diseño.')
        return warnings
    @app.get('/api/brands/{key}/validate')
    def validate_brand(key:str):return {'warnings':brand_warnings(c.get('brand_profiles',key))}
    def apply_profile(p,b):
        p=copy.deepcopy(p);p.update(brand=b['color'],font=b['font'],logo=b['logo'],template=b['cover'],brandSnapshot=copy.deepcopy(b),updated=c.now())
        for s in p['scenes']:s['color']=b['background']
        return p
    @app.post('/api/brands/apply')
    def apply_brand(req:ApplyBrand,request:Request):
        if not req.confirmed:raise HTTPException(409,'Confirma los clips afectados: se reemplazarán colores, fuente, logo, subtítulos, posiciones y portada; se conservan texto, cortes, audio y encuadre.')
        b=c.get('brand_profiles',req.brandId);ps=[protect(request,c.get('projects',key)) for key in req.projectIds]
        protect_resources(request,{'logo':b.get('logo','')})
        updated=[apply_profile(p,b) for p in ps]
        with c.db() as con:
            for p in updated:con.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p,ensure_ascii=False),p['id']))
        return {'projects':updated,'warnings':brand_warnings(b)}

    def transcript_key(asset):
        p=c.file_path(asset);h=hashlib.sha256()
        with p.open('rb') as f:
            while chunk:=f.read(1024*1024):h.update(chunk)
        return h.hexdigest()+'-'+str(c.os.getenv('WHISPER_MODEL','small'))+'-es'
    def produce_candidates(jid,payload):
        batch=c.get('batches',payload['batchId']);key=batch['transcriptKey']
        try:transcript=c.get('transcripts',key)
        except HTTPException:
            result=c.transcribe_work(jid,{'asset':batch['asset'],'target':batch['target'],'segments':payload.get('segments',[])})
            transcript=c.put('transcripts',{'id':key,'asset':batch['asset'],'segments':result['segments'],'created':c.now(),'origin':'manual' if payload.get('segments') else 'whisper'})
        result=c.transcribe_work(jid,{'asset':batch['asset'],'target':batch['target'],'segments':transcript['segments']})
        candidates=result['clips'][:batch['count']]
        with batch_lock:
            batch=c.get('batches',batch['id']);existing={round(x['start'],2):x for x in batch['clips']}
            for clip in candidates:
                if round(clip['start'],2) in existing:continue
                # Non-overlapping candidates from the existing selector; do not overwrite an edited project.
                if any(min(x['end'],clip['end'])-max(x['start'],clip['start'])>.8*min(x['end']-x['start'],clip['end']-clip['start']) for x in batch['clips']):continue
                text=clip['text'][:3000];scene=c.Scene(text=text,overlay='',duration=min(120,clip['end']-clip['start']),asset=batch['asset'],start=clip['start'],originalAudio=True).model_dump()
                scene['captions']=[{**s,'start':s['start']-clip['start'],'end':s['end']-clip['start'],'words':[{**w,'start':w['start']-clip['start'],'end':w['end']-clip['start']} for w in s.get('words',[])]} for s in clip['segments']]
                title=' '.join(text.split()[:9]) or 'Clip sin título'
                p=c.Project(title=title,scenes=[scene],template='Podcast',hooks=[f'¿Qué podemos aprender de {title.lower()}?',f'Una idea para explorar: {title}'],description=title).model_dump()
                p.update(clientId=batch.get('clientId',''),batchId=batch['id'],hookType='original',format='9:16',updated=c.now())
                if batch.get('brandId'):p=apply_profile(p,c.get('brand_profiles',batch['brandId']))
                c.put('projects',p)
                thumb=root/'exports'/f"thumb-{p['id']}.jpg"
                try:c.run_process(jid,[c.ffmpeg(),'-y','-v','error','-ss',str(clip['start']),'-i',str(c.file_path(batch['asset'])),'-frames:v','1','-vf','scale=320:-2',str(thumb)])
                except InterruptedError:raise
                except Exception:thumb=None
                batch['clips'].append({'id':c.uid(),'projectId':p['id'],'start':clip['start'],'end':clip['end'],'reason':clip['reason'],'status':'pending','variant':'A','thumbnail':'/media/exports/'+thumb.name if thumb else ''})
                c.put('batches',batch)
            batch['notice']=f"{len(candidates)} propuestas nuevas o reutilizadas de {batch['count']} solicitadas. Selección por límites de transcripción; no se repiten cortes ya guardados. Si hay menos, el material o sus límites no permiten más sin repetir."
            batch['transcriptionOrigin']=transcript['origin'];batch['updated']=c.now();c.put('batches',batch)
        return {'batchId':batch['id'],'candidates':len(batch['clips']),'transcriptReused':True}
    def enqueue_unique(kind,payload,worker):
        if kind in ('batch-render','brand-preview','batch-zip'):payload={**payload,'rendererRevision':RENDER_REVISION}
        fp=fingerprint({'kind':kind,**payload})
        with request_lock:
            with c.db() as con:row=con.execute('SELECT job_id FROM production_requests WHERE fingerprint=?',(fp,)).fetchone()
            if row:
                old=c.get('jobs',row[0])
                if old['status'] in ('queued','running','done'):return old
            job=c.start_job(kind,payload,worker)
            with c.db() as con:con.execute('INSERT OR REPLACE INTO production_requests VALUES (?,?)',(fp,job['id']))
            return job
    @app.get('/api/batches')
    def batches(request:Request):return visible(request,c.all_rows('batches'))
    @app.post('/api/batches')
    def new_batch(req:BatchInput,request:Request):
        if not req.authorized:raise HTTPException(422,'Confirma que el video es propio o autorizado')
        protect(request,req.model_dump());c.file_path(req.asset)
        if req.clientId:c.get('clients',req.clientId)
        if req.brandId:protect_resources(request,{'logo':c.get('brand_profiles',req.brandId).get('logo','')})
        key=transcript_key(req.asset)
        batch={'id':c.uid(),**req.model_dump(exclude={'segments'}),'transcriptKey':key,'clips':[],'created':c.now(),'updated':c.now()}
        c.put('batches',batch)
        job=enqueue_unique('batch-select',{'batchId':batch['id'],'clientId':req.clientId,'segments':req.segments},produce_candidates)
        with batch_lock:
            batch=c.get('batches',batch['id']);batch['selectionJob']=job['id'];c.put('batches',batch)
        return batch
    def batch_detail(key,request):
        b=protect(request,c.get('batches',key));out=copy.deepcopy(b)
        for clip in out['clips']:
            clip['project']=c.get('projects',clip['projectId'])
            scenes=clip['project']['scenes'];clip['editDuration']=sum(s['duration'] for s in scenes)
            clip['editStart']=scenes[0].get('start',0) if scenes else clip['start'];clip['editEnd']=clip['editStart']+(scenes[0]['duration'] if scenes else 0)
            clip['previewAsset']=(scenes[0].get('asset') if scenes else '') or b['asset']
            clip['jobs']=[j for j in c.all_rows('jobs') if j.get('payload',{}).get('batchId')==key and j.get('payload',{}).get('clipId')==clip['id']]
        out['summary']={'proposed':len(out['clips']),'approved':sum(x['status']=='approved' for x in out['clips']),'exported':sum(any(j['status']=='done' for j in x['jobs']) for x in out['clips'])}
        out['archives']=[j for j in c.all_rows('jobs') if j['kind']=='batch-zip' and j.get('payload',{}).get('batchId')==key]
        if out['archives']:
            tasks=[c.get('jobs',jid) for jid in out['archives'][0]['payload']['jobIds']]
            out['summary']['progress']=round(sum(100 if j['status'] in ('done','error','cancelled') else j['progress'] for j in tasks)/max(1,len(tasks)))
            out['summary']['failed']=sum(j['status']=='error' for j in tasks)
        else:out['summary']['progress']=0;out['summary']['failed']=0
        return out
    @app.get('/api/batches/{key}')
    def get_batch(key:str,request:Request):return batch_detail(key,request)
    @app.post('/api/batches/{key}/regenerate')
    def regenerate(key:str,request:Request):
        b=protect(request,c.get('batches',key))
        if b.get('selectionJob'):
            previous=c.get('jobs',b['selectionJob'])
            if previous['status'] in ('queued','running'):return previous
        job=enqueue_unique('batch-select',{'batchId':key,'clientId':b.get('clientId',''),'revision':c.now()},produce_candidates)
        with batch_lock:
            b=c.get('batches',key);b['selectionJob']=job['id'];c.put('batches',b)
        return job
    @app.put('/api/batches/{key}/clips/{clipid}')
    def decision(key:str,clipid:str,req:ClipDecision,request:Request):
        with batch_lock:
            b=protect(request,c.get('batches',key));clip=next((x for x in b['clips'] if x['id']==clipid),None)
            if not clip:raise HTTPException(404,'Clip no encontrado')
            clip.update(req.model_dump());b['updated']=c.now();c.put('batches',b)
        return clip
    def archive_work(jid,payload):
        completed=[];failed=[]
        for i,jobid in enumerate(payload['jobIds']):
            c.check_cancel(jid);job=c.get('jobs',jobid)
            if job['status']=='done':completed.append(job)
            else:failed.append({'jobId':jobid,'clipId':job['payload']['clipId'],'status':job['status'],'error':job.get('error','Trabajo no terminado')})
            c.update_job(jid,progress=int((i+1)/max(1,len(payload['jobIds']))*90))
        name=f"lote-{payload['batchId'][:8]}-{jid}.zip";path=root/'exports'/name
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for index,job in enumerate(completed):
                p=job['payload']['project'];prefix=f"{index+1:02}-{p['id'][:8]}-{job['payload'].get('variant','A')}"
                for kind in ('video','srt','cover','text','credits'):
                    url=job['result'].get(kind)
                    if url:
                        source=root/url.removeprefix('/media/')
                        if source.exists():z.write(source,prefix+'/'+source.name)
            z.writestr('resumen.json',json.dumps({'completed':[j['id'] for j in completed],'failed':failed,'requested':len(payload['jobIds']),'note':'Solo incluye los clips aprobados al solicitar este lote. Los resultados anteriores se conservan.'},ensure_ascii=False,indent=2))
        return {'zip':'/media/exports/'+name,'completed':len(completed),'failed':failed,'batchId':payload['batchId']}
    def batch_clip_render(jid,payload):
        p=copy.deepcopy(payload['project']);index=0 if payload.get('variant','A')=='A' else 1
        hooks=p.get('hooks',[]);hook=hooks[index] if index<len(hooks) else ''
        if hook and p['scenes']:
            s=p['scenes'][0]
            if s.get('asset') and s.get('originalAudio') and not s.get('audio') and s['duration']>4:
                length=min(3,s['duration']);first=copy.deepcopy(s);rest=copy.deepcopy(s);first['duration']=length;first['overlay']=hook;rest.update(id=c.uid(),start=s.get('start',0)+length,duration=s['duration']-length)
                def cut_captions(offset,duration):
                    captions=[]
                    for cap in s.get('captions',[]):
                        start=max(0,cap['start']-offset);end=min(duration,cap['end']-offset)
                        if end<=start:continue
                        words=[{**w,'start':max(0,w['start']-offset),'end':min(duration,w['end']-offset)} for w in cap.get('words',[]) if w['end']>offset and w['start']<offset+duration]
                        captions.append({**cap,'start':start,'end':end,'words':words,'text':' '.join(w['word'] for w in words) if words else cap['text']})
                    return captions
                first['captions']=cut_captions(0,length);rest['captions']=cut_captions(length,rest['duration'])
                if rest.get('framing'):
                    def shift(points):
                        previous=[f for f in points if f['t']<=length];after=[{**f,'t':f['t']-length} for f in points if f['t']>length]
                        return ([{**previous[-1],'t':0}] if previous else [])+after
                    for track in rest['framing'].get('tracks',[]):track['frames']=shift(track['frames'])
                    rest['framing']['corrections']=shift(rest['framing'].get('corrections',[]))
                p['scenes']=[first,rest,*p['scenes'][1:]]
            else:s['overlay']=hook
        return c.render(jid,{**payload,'project':p})
    @app.post('/api/batches/{key}/export')
    def export_batch(key:str,req:BatchExport,request:Request):
        b=protect(request,c.get('batches',key));jobs=[]
        for clip in b['clips']:
            if clip['status']!='approved':continue
            p=c.get('projects',clip['projectId']);variant=clip.get('variant','A')
            # Hook variants are editorial metadata until the user chooses a new narrated opening in the editor.
            payload={'batchId':key,'clientId':b.get('clientId',''),'clipId':clip['id'],'project':p,'variant':variant,'resolution':req.resolution,'voice':req.voice,'burn':req.burn}
            job=enqueue_unique('batch-render',payload,batch_clip_render);jobs.append(job['id'])
        if not jobs:raise HTTPException(409,'Aprueba al menos un clip antes de exportar.')
        archive=enqueue_unique('batch-zip',{'batchId':key,'clientId':b.get('clientId',''),'jobIds':jobs},archive_work)
        return {'jobs':jobs,'archive':archive}
    @app.post('/api/batches/{key}/cancel')
    def cancel_batch(key:str,request:Request):
        protect(request,c.get('batches',key));cancelled=[]
        for j in c.all_rows('jobs'):
            if j.get('payload',{}).get('batchId')==key and j['status'] in ('queued','running'):c.cancel(j['id']);cancelled.append(j['id'])
        return {'cancelled':cancelled,'note':'Los proyectos editados y resultados terminados se conservan.'}

    c.production_workers={'batch-select':produce_candidates,'batch-render':batch_clip_render,'batch-zip':archive_work,'brand-preview':c.render}
    c.production_enqueue=enqueue_unique
    c.production_protect=protect
    c.production_principal=principal
    c.production_require_owner=require_owner
    c.production_protect_resources=protect_resources
    # Further features are installed against the same boundary and queue.
    from backend.review import install_review
    from backend.analytics import install_analytics
    from backend.framing import install_framing
    install_framing(app,c,protect)
    install_review(app,c,protect,principal,require_owner)
    install_analytics(app,c,protect,visible)
