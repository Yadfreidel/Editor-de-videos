import os,sys,time,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['CLIP_WORKSPACE']='workspace/framing-verification'
from backend.main import app,ROOT,get,put,Scene,Project
from backend.framing import track_samples
from fastapi.testclient import TestClient
import cv2,numpy as np,av
c=TestClient(app);results=[]
fixture=Path('workspace/test-fixtures/astronaut.png')
if not fixture.exists():
 import httpx
 fixture.parent.mkdir(parents=True,exist_ok=True)
 response=httpx.get('https://raw.githubusercontent.com/scikit-image/scikit-image/v0.25.2/skimage/data/astronaut.png',timeout=30,follow_redirects=True);response.raise_for_status();fixture.write_bytes(response.content)
photo=cv2.imread(str(fixture));assert photo is not None
def wait(job):
 for _ in range(1000):
  j=get('jobs',job['id'])
  if j['status'] in ('done','error'):assert j['status']=='done',j;return j['result']
  time.sleep(.1)
 raise AssertionError('timeout')
def post(path,data):
 r=c.post('/api'+path,json=data);assert r.status_code==200,r.text;return r.json()
projects={};analyses={}
for case in ('one','two','none','occlusion'):
 path=ROOT/'uploads'/f'{case}.mp4';writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),10,(1280,720))
 for n in range(40):
  frame=np.full((720,1280,3),40,np.uint8)
  if case!='none' and not (case=='occlusion' and 12<=n<24):frame[100:612,70+n*3:582+n*3]=photo
  if case=='two':frame[100:612,700:1212]=photo
  writer.write(frame)
 writer.release()
 p=Project(title='Prueba encuadre '+case,scenes=[Scene(text='Prueba visual.',overlay='',duration=4,asset=path.name)]).model_dump();put('projects',p);projects[case]=p
 result=wait(post('/framing/analyze',{'projectId':p['id'],'sceneIndex':0}));analyses[case]=result
 assert (len(result['tracks'])>=2 if case=='two' else len(result['tracks'])>=1 if case!='none' else len(result['tracks'])==0),(case,result)
 assert result['speakerIdentified'] is False
 results.append({'case':case,'tracks':len(result['tracks']),'samples':result['samples']})
 print('DETECT',case,len(result['tracks']),flush=True)
occluded=analyses['occlusion']['tracks'][0]['frames'];assert any(not p['visible'] for p in occluded)
for i,p in enumerate(occluded):
 if not p['visible'] and i:assert p['x']==occluded[i-1]['x']
outputs={}
for mode in ('manual-left','manual-right','follow','split','follow-dense'):
 p=projects['two'];s=p['scenes'][0];s['duration']=2
 s['x']=0 if mode=='manual-left' else 1
 s['framing']={'mode':'manual' if mode.startswith('manual') else 'follow' if mode=='follow-dense' else mode,**analyses['two'],'person':analyses['two']['tracks'][0]['id'],'left':analyses['two']['tracks'][0]['id'],'right':analyses['two']['tracks'][1]['id']}
 if mode=='follow-dense':s['framing']['tracks']=[{'id':s['framing']['person'],'frames':[{'t':n*.5,'x':.2+(n%20)*.01} for n in range(240)]}]
 put('projects',p);result=wait(post('/projects/'+p['id']+'/render',{'resolution':720,'burn':False}));path=ROOT/result['video'].removeprefix('/media/')
 with av.open(str(path)) as video:
  v=video.streams.video[0];assert(v.width,v.height)==(720,1280)
  frame=next(video.decode(video=0));image=frame.to_image();image.save(ROOT/'exports'/f'{mode}.png');outputs[mode]=hashlib.sha256(image.tobytes()).hexdigest()
 print('RENDER',mode,flush=True)
assert outputs['manual-left']!=outputs['manual-right']
assert outputs['split']!=outputs['follow']
Path('framing-verification.json').write_text(json.dumps({'cases':results,'manualChangeReachesMp4':True,'allThreeModesRendered':True,'occlusionHoldsCrop':True,'speakerIdentification':False,'fixture':'NASA Eileen Collins, public domain; skimage.data.astronaut'},ensure_ascii=False,indent=2),encoding='utf-8')
print('Framing checks passed',flush=True)
