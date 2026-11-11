"""Production integration tests, isolated from the owner's workspace."""
import os,sys,json,time,sqlite3,shutil,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['CLIP_WORKSPACE']='workspace/production-verification'
from backend.main import app,ROOT,DB,ffmpeg,get,put,all_rows
from backend.migrations import migrate
from fastapi.testclient import TestClient
import subprocess
client=TestClient(app)
checks=[]
def ok(name,**details):checks.append({'check':name,'passed':True,**details});print(name,details,flush=True)
def post(url,data=None,**kwargs):
    r=client.post('/api'+url,json=data or {},**kwargs);assert r.status_code==200,(url,r.text);return r.json()
def wait(key):
    for i in range(1000):
        j=get('jobs',key)
        if j['status'] in ('done','error','cancelled'):return j
        time.sleep(.1)
    raise AssertionError('Job timeout '+key)
def detail(b):return client.get('/api/batches/'+b['id']).json()

# Preserve all original JSON, unknown fields, rollback and new-database paths.
case=ROOT/'migration-cases';case.mkdir(exist_ok=True)
old=case/'old.sqlite3'
with sqlite3.connect(old) as c:
    c.execute('CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
    c.execute('INSERT OR REPLACE INTO projects VALUES (?,?)',('legacy',json.dumps({'id':'legacy','custom':'preservar'})))
migrate(old)
with sqlite3.connect(old) as c:assert json.loads(c.execute('SELECT data FROM projects').fetchone()[0])['custom']=='preservar'
fresh=case/'new.sqlite3';migrate(fresh)
try:migrate(old,[(99,'injected_failure',['CREATE TABLE must_rollback(id TEXT)','THIS IS INVALID SQL'])]);raise AssertionError('Expected rollback')
except sqlite3.OperationalError:pass
with sqlite3.connect(old) as c:
    assert not c.execute("SELECT name FROM sqlite_master WHERE name='must_rollback'").fetchone()
    assert not c.execute('SELECT 1 FROM schema_migrations WHERE version=99').fetchone()
ok('Incremental migrations: old/new databases and full transaction rollback')
scope_case=case/('scope-'+__import__('uuid').uuid4().hex+'.sqlite3')
with sqlite3.connect(scope_case) as con:
    con.execute('CREATE TABLE projects(id TEXT PRIMARY KEY,data TEXT)');con.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,data TEXT)')
    con.execute('INSERT INTO projects VALUES (?,?)',('private-project',json.dumps({'id':'private-project','clientId':'client-one','scenes':[{'asset':'private.mp4'}]})))
    con.execute('INSERT INTO jobs VALUES (?,?)',('old-voice',json.dumps({'id':'old-voice','kind':'voice','payload':{'projectId':'private-project'}})))
    con.execute('INSERT INTO jobs VALUES (?,?)',('old-transcript',json.dumps({'id':'old-transcript','kind':'transcribe','payload':{'asset':'private.mp4'}})))
migrate(scope_case)
with sqlite3.connect(scope_case) as con:assert all(json.loads(r[0])['payload']['clientId']=='client-one' for r in con.execute('SELECT data FROM jobs'))
ok('Legacy auxiliary jobs inherit private project scopes without changing projects')
from unittest.mock import patch
from types import SimpleNamespace
from fastapi import FastAPI
from backend.production import install
failed_app=FastAPI()
with patch('backend.production.migrate',side_effect=sqlite3.OperationalError('fallo simulado')):install(failed_app,SimpleNamespace(ROOT=case,DB=old))
failed_client=TestClient(failed_app)
assert failed_client.get('/api/production/status').status_code==503
assert failed_client.get('/media/uploads/private.mp4').status_code==503
ok('Migration error is recoverable and fails closed before serving private data')

source=ROOT/'uploads'/'batch-source.mp4'
subprocess.run([ffmpeg(),'-y','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=15','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','48','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(source)],check=True)
segments=[{'start':i*4,'end':(i+1)*4,'text':f'Pregunta {i+1}. Una idea original de prueba.'} for i in range(12)]
from PIL import Image
Image.new('RGBA',(64,64),'#ff1020').save(ROOT/'uploads'/'test-logo.png')
brand=post('/brands',{'name':'Marca de prueba','color':'#c0ef74','background':'#24374b','subtitleColor':'#ffcc99','font':'Arial','logo':'test-logo.png','logoX':.72,'logoY':.08})
preview=wait(post('/brands/preview',brand)['id']);assert preview['status']=='done',preview
import av,numpy as np
with av.open(str(ROOT/preview['result']['video'].removeprefix('/media/'))) as container:
    frame=next(container.decode(video=0)).to_ndarray(format='rgb24').astype(int);region=frame[int(1280*.65):int(1280*.9)]
    assert ((np.abs(region-np.array([255,204,153]))<20).all(axis=2)).sum()>100,'Subtitle colour does not match brand in rendered preview'
ok('Real brand preview uses final renderer, including subtitle colour pixels')
other_preview=wait(post('/brands/preview',{**brand,'cover':'Noticias'})['id'])
assert (ROOT/other_preview['result']['cover'].removeprefix('/media/')).read_bytes()!=(ROOT/preview['result']['cover'].removeprefix('/media/')).read_bytes()
batch=post('/batches',{'asset':source.name,'authorized':True,'count':3,'target':15,'name':'Verificación de lote','brandId':brand['id'],'segments':segments})
assert wait(batch['selectionJob'])['status']=='done'
b=detail(batch);assert len(b['clips'])==3,b
first=get('projects',b['clips'][0]['projectId']);first['title']='Edición que debe conservarse';put('projects',first)
before=first['brandSnapshot']['color']
updated={**brand,'color':'#123456'}
assert client.put('/api/brands/'+brand['id'],json=updated).status_code==200
assert get('projects',first['id'])['brandSnapshot']['color']==before
reg=post('/batches/'+batch['id']+'/regenerate');assert wait(reg['id'])['status']=='done'
assert get('projects',first['id'])['title']==first['title']
assert len([t for t in all_rows('transcripts') if t['id']==batch['transcriptKey']])==1
ok('One transcript, non-overlapping candidates, regeneration preserves edits and brand snapshot')
assert client.post('/api/brands/apply',json={'brandId':brand['id'],'projectIds':[first['id']],'confirmed':False}).status_code==409
post('/brands/apply',{'brandId':brand['id'],'projectIds':[first['id']],'confirmed':True})
assert get('projects',b['clips'][1]['projectId'])['brandSnapshot']['color']==before
for i,clip in enumerate(b['clips']):
    r=client.put(f"/api/batches/{batch['id']}/clips/{clip['id']}",json={'status':'approved' if i<2 else 'discarded','variant':'B' if i==1 else 'A'});assert r.status_code==200
    # Shorten only test projects: exercise the real renderer without producing long fixtures.
    p=get('projects',clip['projectId']);p['scenes'][0]['duration']=2;p['coverText']='PORTADA PROPIA';put('projects',p)
export=post('/batches/'+batch['id']+'/export',{'resolution':720})
archive=wait(export['archive']['id']);assert archive['status']=='done',archive
assert archive['result']['completed']==2,archive
path=ROOT/archive['result']['zip'].removeprefix('/media/')
with zipfile.ZipFile(path) as z:
    names=z.namelist();assert sum(n.endswith('.mp4') for n in names)==2
    assert all(b['clips'][2]['projectId'][:8] not in n for n in names)
again=post('/batches/'+batch['id']+'/export',{'resolution':720});assert again['jobs']==export['jobs']
import av
for index,jid in enumerate(export['jobs']):
    job=get('jobs',jid);p=job['payload']['project'];result=job['result']
    assert result['scenes'][0]['overlay']==p['hooks'][index]
    cover=Image.open(ROOT/result['cover'].removeprefix('/media/')).convert('RGB')
    assert cover.getpixel((int(720*.72)+10,int(1280*.08)+10))==(255,16,32)
    assert (ROOT/result['cover'].removeprefix('/media/')).read_bytes()!=(ROOT/'jobs'/jid/'card0.png').read_bytes()
    with av.open(str(ROOT/result['video'].removeprefix('/media/'))) as container:
        frame=next(container.decode(video=0)).to_image().convert('RGB');rgb=frame.getpixel((int(720*.72)+10,int(1280*.08)+10));assert max(abs(a-b) for a,b in zip(rgb,(255,16,32)))<25,rgb
    assert '99ccff' in (ROOT/'jobs'/jid/'scene0.ass').read_text(encoding='utf-8').lower()
ok('Two approved exports in ZIP, discarded excluded, duplicate request reuses jobs',zip=str(path))
# A bad resource affects one job only; successful output survives and is reused on retry.
bad=get('projects',b['clips'][0]['projectId']);bad['scenes'][0]['asset']='missing-test-resource.mp4';put('projects',bad)
partial=post('/batches/'+batch['id']+'/export',{'resolution':720});result=wait(partial['archive']['id'])
assert result['result']['completed']==1 and len(result['result']['failed'])==1,result
bad['scenes'][0]['asset']=source.name;put('projects',bad)
retry=post('/batches/'+batch['id']+'/export',{'resolution':720,'retryFailed':True});assert wait(retry['archive']['id'])['result']['completed']==2
assert retry['jobs'][1]==export['jobs'][1]
ok('Partial failure preserves successful output; retry reuses healthy clip')
Path('production-verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print('Production phase checks passed',flush=True)
