"""Real media integration checks. Run from repo root with .venv/Scripts/python scripts/verify.py."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['CLIP_WORKSPACE']='workspace/verification'
from fastapi.testclient import TestClient
from backend.main import app, ffmpeg, ROOT
client=TestClient(app)
results=[]
def passed(name,**details):
    results.append({'check':name,'status':'passed',**details}); print(name,details,flush=True)
def wait(job):
    for _ in range(900):
        row=next(j for j in client.get('/api/jobs').json() if j['id']==job['id'])
        if row['status']=='done': return row['result']
        if row['status'] in ('error','cancelled'): raise AssertionError(row)
        time.sleep(.25)
    raise AssertionError('timeout')
def post(path,data):
    r=client.post(path,json=data); assert r.status_code==200,r.text; return r.json()
def inspect(url,width,height):
    import av
    path=ROOT/url.removeprefix('/media/')
    with av.open(str(path)) as c:
        v=c.streams.video[0]; a=c.streams.audio[0]
        assert (v.width,v.height)==(width,height)
        assert v.codec_context.name=='h264' and a.codec_context.name=='aac'
        vd=float(v.duration*v.time_base); ad=float(a.duration*a.time_base)
        assert abs(vd-ad)<.15,(vd,ad)
        frame=next(c.decode(video=0)); frame.to_image().save(ROOT/'exports'/'verified-frame.png')
    with av.open(str(path)) as c:
        import numpy as np
        peak=max(float(np.max(np.abs(f.to_ndarray()))) for f in c.decode(audio=0))
    assert peak>0.001,'Silent audio'
    return {'resolution':f'{width}x{height}','video_seconds':vd,'audio_seconds':ad,'audio_peak':peak}

p=post('/api/create',{'text':'Una historia empieza con una pregunta. Hoy vamos a mirar las cosas de otra manera.','mode':'script'})
p['scenes'][0]['overlay']='TEXTO EDITADO PARA VERIFICAR'
assert client.put('/api/projects/'+p['id'],json=p).status_code==200
assert client.get('/api/projects/'+p['id']).json()['scenes'][0]['overlay']==p['scenes'][0]['overlay']
passed('Autosave representation persists edited overlay')
render=wait(post('/api/projects/'+p['id']+'/render',{'voice':'piper','resolution':720,'burn':True}))
passed('Script to narrated MP4 with subtitles',**inspect(render['video'],720,1280))
assert client.get(render['srt']).status_code==200
assert 'Una historia' in client.get(render['srt']).text
passed('SRT, cover, publication and credits',artifacts=[render[k] for k in ('video','srt','cover','text','credits')])
short={**p,'id':__import__('uuid').uuid4().hex,'scenes':[{**p['scenes'][0],'duration':2,'text':'Hola.','overlay':'Hola.'}]}
client.put('/api/projects/'+short['id'],json=short)
full=wait(post('/api/projects/'+short['id']+'/render',{'voice':'piper','resolution':1080,'burn':True}))
passed('1080p render',**inspect(full['video'],1080,1920))
# Original generated test footage, 100 seconds with genuine synthesized Spanish speech.
source=ROOT/'uploads'/'test-long.mp4'
subprocess.run([ffmpeg(),'-y','-v','error','-stream_loop','-1','-i',str(ROOT/render['video'].removeprefix('/media/')),'-t','100','-c','copy',str(source)],check=True)
segments=[{'start':i*10,'end':(i+1)*10,'text':f'Pregunta {i+1}. Este es un segmento de prueba original.'} for i in range(10)]
clips=wait(post('/api/transcribe',{'asset':source.name,'target':30,'segments':segments}))
assert 3<=len(clips['clips'])<=10
passed('Long video with timestamped transcript to clips',clips=len(clips['clips']))
cut={**short,'id':__import__('uuid').uuid4().hex,'scenes':[{**short['scenes'][0],'asset':source.name,'originalAudio':True,'start':2,'duration':3}]}
client.put('/api/projects/'+cut['id'],json=cut)
clip=wait(post('/api/projects/'+cut['id']+'/render',{'voice':'none','resolution':720}))
passed('Trimmed clip retains source audio',**inspect(clip['video'],720,1280))
for url in ['http://127.0.0.1:8000','http://169.254.169.254/latest','file:///etc/passwd','https://example.invalid']:
    r=client.post('/api/extract',json={'url':url}); assert r.status_code==422,(url,r.text)
passed('Private, reserved, invalid and inaccessible links rejected')
previous=os.environ.pop('OLLAMA_MODEL',None)
assert client.post('/api/create',json={'text':'Tema de prueba','mode':'topic'}).status_code==409
if previous:os.environ['OLLAMA_MODEL']=previous
passed('Unconfigured model gives manual-script fallback')
rss=client.get('/api/trends'); assert rss.status_code==200,rss.text
assert len(rss.json()['items'])>0 and all(i['signal'] is None for i in rss.json()['items'])
passed('Live RSS, no fabricated trend signals',items=len(rss.json()['items']))
job=post('/api/projects/'+p['id']+'/render',{'voice':'none','resolution':1080})
cancel=post('/api/jobs/'+job['id']+'/cancel',{})
assert cancel['status']=='cancelled'
time.sleep(.5)
assert next(j for j in client.get('/api/jobs').json() if j['id']==job['id'])['status']=='cancelled'
passed('Render cancellation stays cancelled')
post('/api/metrics',{'project':p['id'],'variant':'A','platform':'TikTok','period':'Prueba local','views':10})
row=client.get('/api/metrics').json()[0]; assert row['average'] is None
passed('Missing metrics remain null')
Path('verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('All checks passed',flush=True)
