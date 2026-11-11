import os,sys,json,time,shutil,uuid,subprocess,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ['CLIP_WORKSPACE']='workspace/whisper-batch-verification/'+uuid.uuid4().hex
from backend.main import app,ROOT,get,ffmpeg
from fastapi.testclient import TestClient
from faster_whisper import WhisperModel
from unittest.mock import patch
c=TestClient(app);shutil.copy2('workspace/verification/uploads/test-long.mp4',ROOT/'uploads'/'spoken-long.mp4')
# Keep the genuine local Spanish speech, replace the already captioned test picture with a clean original.
subprocess.run([ffmpeg(),'-y','-v','error','-f','lavfi','-i','color=c=0x173c38:s=960x540:r=15','-i',str(ROOT/'uploads'/'spoken-long.mp4'),'-t','100','-map','0:v:0','-map','1:a:0','-c:v','libx264','-threads','2','-preset','ultrafast','-c:a','aac',str(ROOT/'uploads'/'clean-spoken-long.mp4')],check=True)
calls=0;original=WhisperModel.transcribe
def tracked(self,*args,**kwargs):
 global calls;calls+=1;return original(self,*args,**kwargs)
def wait(key):
 for _ in range(1800):
  j=get('jobs',key)
  if j['status'] in ('done','error'):assert j['status']=='done',j;return j
  time.sleep(.1)
 raise AssertionError('timeout')
with patch.object(WhisperModel,'transcribe',tracked):
 b=c.post('/api/batches',json={'asset':'clean-spoken-long.mp4','name':'Whisper real una vez','authorized':True,'count':3,'target':30}).json();wait(b['selectionJob'])
 r=c.post('/api/batches/'+b['id']+'/regenerate',json={}).json();wait(r['id'])
 second=c.post('/api/batches',json={'asset':'clean-spoken-long.mp4','name':'Reutilizar transcripción','authorized':True,'count':2,'target':15}).json();wait(second['selectionJob'])
 assert calls==1,calls
 detail=c.get('/api/batches/'+b['id']).json();assert len(detail['clips'])>=3
for index,clip in enumerate(detail['clips']):
 response=c.put(f"/api/batches/{b['id']}/clips/{clip['id']}",json={'status':'approved' if index<2 else 'discarded','variant':'A' if index==0 else 'B'});assert response.status_code==200
export=c.post('/api/batches/'+b['id']+'/export',json={'resolution':720}).json();archive=wait(export['archive']['id']);assert archive['result']['completed']==2
with zipfile.ZipFile(ROOT/archive['result']['zip'].removeprefix('/media/')) as z:assert sum(n.endswith('.mp4') for n in z.namelist())==2
import av
for jid in export['jobs']:
 job=get('jobs',jid);assert '\\kf' in (ROOT/'jobs'/jid/'scene0.ass').read_text(encoding='utf-8')
 with av.open(str(ROOT/job['result']['video'].removeprefix('/media/'))) as video:
  v=video.streams.video[0];a=video.streams.audio[0];assert(v.width,v.height)==(720,1280);assert abs(float(v.duration*v.time_base)-float(a.duration*a.time_base))<.15
Path('whisper-batch-verification.json').write_text(json.dumps({'actualWhisperInvocations':calls,'firstBatchClips':len(detail['clips']),'regenerationReusesTranscript':True,'anotherBatchReusesTranscript':True,'twoApprovedRealSpeechExports':True,'discardedExcludedFromZip':True,'wordHighlightsRendered':True,'archive':archive['result']['zip'],'model':os.getenv('WHISPER_MODEL'),'device':os.getenv('WHISPER_DEVICE'),'workspace':str(ROOT)},indent=2))
print('Actual Whisper called once across two batches and regeneration',flush=True)
