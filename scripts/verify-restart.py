"""Exercise cancellation and recovery across a real local server restart."""
import os,sys,time,json,sqlite3,shutil,socket,subprocess,uuid
from pathlib import Path
import httpx
ROOT=Path('workspace/restart-verification').resolve();ROOT.mkdir(parents=True,exist_ok=True)
(ROOT/'uploads').mkdir(exist_ok=True);shutil.copy2('workspace/production-verification/uploads/batch-source.mp4',ROOT/'uploads'/'source.mp4')
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
env={**os.environ,'CLIP_WORKSPACE':str(ROOT)};base=f'http://127.0.0.1:{port}';http=httpx.Client(base_url=base,timeout=15)
log=(ROOT/'server.log').open('a',encoding='utf-8');server=None
def boot():
 p=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(port)],env=env,stdout=log,stderr=log)
 for i in range(200):
  try:
   if http.get('/api/production/status').status_code==200:return p
  except httpx.HTTPError:pass
  if p.poll() is not None:raise RuntimeError('Test server failed; see server.log')
  time.sleep(.1)
 raise RuntimeError('Startup timeout')
def post(path,data=None):
 r=http.post('/api'+path,json=data or {});assert r.status_code==200,r.text;return r.json()
def read_job(key):
 with sqlite3.connect(ROOT/'studio.sqlite3') as c:return json.loads(c.execute('SELECT data FROM jobs WHERE id=?',(key,)).fetchone()[0])
def wait(key):
 for i in range(1000):
  j=read_job(key)
  if j['status'] in ('done','error','cancelled'):return j
  time.sleep(.1)
 raise AssertionError('Timeout')
try:
 server=boot()
 segments=[{'start':n*4,'end':(n+1)*4,'text':f'Idea de prueba {n}.'} for n in range(12)]
 b=post('/batches',{'asset':'source.mp4','authorized':True,'count':3,'target':15,'name':'Reinicio verificable','segments':segments});assert wait(b['selectionJob'])['status']=='done'
 b=http.get('/api/batches/'+b['id']).json()
 for i,clip in enumerate(b['clips']):
  assert http.put(f"/api/batches/{b['id']}/clips/{clip['id']}",json={'status':'approved' if i<2 else 'discarded','variant':'A'}).status_code==200
  p=clip['project'];p['scenes'][0]['duration']=5;assert http.put('/api/projects/'+p['id'],json=p).status_code==200
 exported=post('/batches/'+b['id']+'/export',{'resolution':720});archive=wait(exported['archive']['id']);assert archive['status']=='done' and archive['result']['completed']==2
 completed=read_job(exported['jobs'][1]);completed_file=ROOT/completed['result']['video'].removeprefix('/media/');assert completed_file.is_file()
 p=http.get('/api/projects/'+b['clips'][0]['projectId']).json();p['title']='Edición conservada tras reinicio';p['scenes'][0]['duration']=90;http.put('/api/projects/'+p['id'],json=p).raise_for_status()
 busy=post('/batches/'+b['id']+'/export',{'resolution':1080});post('/batches/'+b['id']+'/cancel');assert wait(busy['jobs'][0])['status']=='cancelled'
 p['scenes'][0]['duration']=5;http.put('/api/projects/'+p['id'],json=p).raise_for_status()
 # A queued snapshot left by an interrupted process: same format as a real durable job.
 server.terminate();server.wait(timeout=15);server=None
 interrupted={**completed,'id':uuid.uuid4().hex,'status':'queued','progress':0};interrupted.pop('result',None)
 with sqlite3.connect(ROOT/'studio.sqlite3') as db:db.execute('INSERT INTO jobs VALUES (?,?)',(interrupted['id'],json.dumps(interrupted)))
 server=boot()
 assert read_job(interrupted['id'])['status']=='error'
 assert completed_file.is_file() and read_job(completed['id'])['status']=='done'
 assert http.get('/api/projects/'+p['id']).json()['title']==p['title']
 retried=post('/jobs/'+interrupted['id']+'/retry');assert wait(retried['id'])['status']=='done'
 Path('restart-verification.json').write_text(json.dumps({'realServerRestart':True,'cancelledBatchPreservesEdits':True,'completedMediaPreserved':True,'interruptedQueueRecoverable':True,'retryAfterRestart':True},indent=2))
 print('Real restart, cancellation, persisted edits/results and retry passed',flush=True)
finally:
 if server and server.poll() is None:server.terminate();server.wait(timeout=15)
 http.close();log.close()
