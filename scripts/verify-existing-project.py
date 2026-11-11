"""Open, edit and export a copy of the oldest existing project; never writes the source DB."""
import os,sys,json,sqlite3,shutil,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
source=Path(os.getenv('CLIP_WORKSPACE','workspace')).resolve()
destination=source/'compatibility-copies'/uuid.uuid4().hex;destination.mkdir(parents=True)
with sqlite3.connect(source/'studio.sqlite3') as old:
    original_id,original_json=old.execute('SELECT id,data FROM projects ORDER BY rowid LIMIT 1').fetchone()
    with sqlite3.connect(destination/'studio.sqlite3') as copy:old.backup(copy)
original=json.loads(original_json);(destination/'uploads').mkdir()
if original.get('logo'):shutil.copy2(source/'uploads'/original['logo'],destination/'uploads'/original['logo'])
os.environ['CLIP_WORKSPACE']=str(destination)
from backend.main import app,ROOT,get
from fastapi.testclient import TestClient
import av,numpy as np
client=TestClient(app);client.headers['x-owner-key']=(ROOT/'owner-access.txt').read_text().strip()
p=client.get('/api/projects/'+original_id).json()
p['scenes']=p['scenes'][:1];p['scenes'][0].update(text='Una prueba de compatibilidad con voz local.',overlay='Proyecto anterior, edición conservada',duration=2,asset='',audio='',originalAudio=False,captions=[],framing={'mode':'manual'})
p['music']='';p['compatibilityProbe']={'preserve':'yes'}
assert client.put('/api/projects/'+p['id'],json=p).status_code==200
assert client.get('/api/projects/'+p['id']).json()['compatibilityProbe']==p['compatibilityProbe']
exports=[]
for resolution in (720,1080):
    job=client.post('/api/projects/'+p['id']+'/render',json={'resolution':resolution,'voice':'piper','burn':True}).json()
    for i in range(1000):
        row=get('jobs',job['id'])
        if row['status'] in ('done','error'):break
        time.sleep(.1)
    assert row['status']=='done',row
    result=row['result'];file=ROOT/result['video'].removeprefix('/media/')
    with av.open(str(file)) as container:
        video=container.streams.video[0];audio=container.streams.audio[0]
        assert (video.width,video.height)==(resolution,resolution*16//9)
        assert video.codec_context.name=='h264' and audio.codec_context.name=='aac'
        skew=abs(float(video.duration*video.time_base)-float(audio.duration*audio.time_base));assert skew<.15
        assert next(container.decode(video=0))
    with av.open(str(file)) as container:peak=max(float(np.abs(f.to_ndarray()).max()) for f in container.decode(audio=0))
    assert peak>.001
    assert 'Una prueba' in (ROOT/result['srt'].removeprefix('/media/')).read_text(encoding='utf-8')
    exports.append({'resolution':resolution,'skewSeconds':skew,'audioPeak':peak,'file':str(file)})
    print('Existing project copy exported',resolution,flush=True)
with sqlite3.connect(source/'studio.sqlite3') as current:assert current.execute('SELECT data FROM projects WHERE id=?',(original_id,)).fetchone()[0]==original_json
Path('existing-project-verification.json').write_text(json.dumps({'originalProjectId':original_id,'sourceUnchanged':True,'unknownFieldsPreserved':True,'copy':str(destination),'exports':exports},ensure_ascii=False,indent=2),encoding='utf-8')
