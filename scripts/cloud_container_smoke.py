"""Run inside the test container. Never prints the owner key or a review capability."""
import os,json,time,subprocess,sys
from pathlib import Path
import httpx
import av
root=Path(os.getenv('CLIP_WORKSPACE','/data'));base='http://127.0.0.1:'+os.getenv('PORT','8000')
owner=httpx.Client(base_url=base,headers={'x-owner-key':os.environ['CLIP_OWNER_KEY']},timeout=30)
guest=httpx.Client(base_url=base,timeout=30)
def post(path,data):
 r=owner.post('/api'+path,json=data);assert r.status_code==200,(path,r.text);return r.json()
def wait(key):
 for _ in range(1800):
  row=next(j for j in owner.get('/api/jobs').json() if j['id']==key)
  if row['status'] in ('done','error'):assert row['status']=='done',row.get('error');return row
  time.sleep(.1)
 raise AssertionError('Job timeout')
for _ in range(300):
 try:
  if guest.get('/api/health').status_code==200:break
 except httpx.HTTPError:pass
 time.sleep(.1)
if '--after-restart' in sys.argv:
 result=json.loads((root/'cloud-smoke-result.json').read_text());assert owner.get('/api/projects/'+result['projectId']).status_code==200
 print('Cloud container: project and media survive restart.');raise SystemExit(0)
assert guest.get('/api/projects').status_code==401
assert guest.get('/').status_code==200
health=guest.get('/api/health').json();assert health['remote'] and health['piper'] and health['whisper'] and health['ffmpeg']
p=post('/create',{'text':'Una prueba de video privado.','mode':'script'})
job=wait(post('/projects/'+p['id']+'/render',{'resolution':720,'voice':'piper'})['id'])
video=root/job['result']['video'].removeprefix('/media/')
with av.open(str(video)) as container:
 v=container.streams.video[0];a=container.streams.audio[0];assert(v.width,v.height)==(720,1280)
 assert v.codec_context.name=='h264' and a.codec_context.name=='aac'
 assert abs(float(v.duration*v.time_base)-float(a.duration*a.time_base))<.15
assert guest.get(job['result']['video']).status_code==401
assert owner.get(job['result']['video']).status_code==200
voice=root/'jobs'/job['id']/'voice0.wav';clean=root/'uploads'/'cloud-original-test.mp4'
subprocess.run([os.getenv('FFMPEG_PATH','ffmpeg'),'-y','-v','error','-f','lavfi','-i','color=c=0x173c38:s=640x360:r=15','-stream_loop','-1','-i',str(voice),'-t','45','-c:v','libx264','-threads','1','-preset','ultrafast','-c:a','aac',str(clean)],check=True)
with clean.open('rb') as source:
 r=owner.post('/api/upload',files={'file':('cloud-original-test.mp4',source,'video/mp4')});assert r.status_code==200,r.text;asset=r.json()['name']
batch=post('/batches',{'asset':asset,'name':'Cloud container integration','authorized':True,'count':3,'target':15})
wait(batch['selectionJob']);b=owner.get('/api/batches/'+batch['id']).json();assert len(b['clips'])>=2
for clip in b['clips'][:2]:
 owner.put('/api/batches/'+b['id']+'/clips/'+clip['id'],json={'status':'approved','variant':'A'}).raise_for_status()
 project=clip['project'];project['scenes'][0]['duration']=3;owner.put('/api/projects/'+project['id'],json=project).raise_for_status()
exports=post('/batches/'+b['id']+'/export',{'resolution':720});archive=wait(exports['archive']['id']);assert archive['result']['completed']==2
assert guest.get(archive['result']['zip']).status_code==401
assert owner.get(archive['result']['zip']).status_code==200
client=post('/clients',{'name':'Cliente de prueba nube'})
copy=post('/clients/'+client['id']+'/projects',{'projectId':b['clips'][0]['projectId']})
render=wait(post('/projects/'+copy['id']+'/render',{'resolution':720})['id'])
review=post('/reviews',{'projectId':copy['id'],'jobId':render['id']})
invite=post('/reviews/'+review['id']+'/invites',{'hours':1})
authorized={'Authorization':'Bearer '+invite['token']}
assert guest.get('/api/reviewer/'+review['id']+'/media',headers=authorized).status_code==200
assert guest.get('/api/reviewer/'+review['id']+'/media').status_code==401
post('/reviews/'+review['id']+'/invites/'+invite['id']+'/revoke',{})
assert guest.get('/api/reviewer/'+review['id']+'/media',headers=authorized).status_code==403
(root/'cloud-smoke-result.json').write_text(json.dumps({'projectId':p['id'],'privateRender':True,'whisperBatch':True,'approvedZip':True,'scopedReview':True}))
print('Cloud container: narration, MP4, Whisper, batch ZIP, private media and review passed.')
