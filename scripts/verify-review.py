import os,sys,json,time,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ['CLIP_WORKSPACE']='workspace/review-verification'
from backend.main import app,ROOT,Project,Scene,put,get
from fastapi.testclient import TestClient
owner=TestClient(app);owner.headers['x-owner-key']=(ROOT/'owner-access.txt').read_text().strip()
anonymous=TestClient(app)
def post(client,path,data=None):
 r=client.post('/api'+path,json=data or {});assert r.status_code==200,(path,r.text);return r.json()
def wait(job):
 for _ in range(1000):
  j=get('jobs',job['id'])
  if j['status'] in ('done','error'):assert j['status']=='done',j;return j
  time.sleep(.1)
 raise AssertionError('timeout')
source=ROOT/'uploads'/'review-source.mp4';shutil.copy2('workspace/production-verification/uploads/batch-source.mp4',source)
put('assets',{'id':source.name,'name':source.name,'url':'/media/uploads/'+source.name,'original':'Prueba original','author':'Autor de prueba','license':'Material generado para pruebas','attribution':'Conservar esta atribución'})
p=Project(title='Original de revisión',scenes=[Scene(text='Texto original.',overlay='',duration=2,asset=source.name,originalAudio=True)]).model_dump();put('projects',p)
clients=[post(owner,'/clients',{'name':'Cliente '+str(i)}) for i in (1,2)]
copies=[post(owner,'/clients/'+cl['id']+'/projects',{'projectId':p['id']}) for cl in clients]
reviews=[]
for project in copies:
 job=wait(post(owner,'/projects/'+project['id']+'/render',{'resolution':720}))
 reviews.append(post(owner,'/reviews',{'projectId':project['id'],'jobId':job['id']}))
 credits=json.loads((ROOT/job['result']['credits'].removeprefix('/media/')).read_text(encoding='utf-8'));assert credits['assets'][0]['author']=='Autor de prueba'
invites=[post(owner,'/reviews/'+r['id']+'/invites',{'name':'Revisor','hours':1}) for r in reviews]
guest=TestClient(app);guest.headers['authorization']='Bearer '+invites[0]['token']
assert guest.get('/api/reviewer/'+reviews[0]['id']).status_code==200
assert guest.get('/api/reviewer/'+reviews[0]['id']+'/media').status_code==200
for path in ['/api/reviewer/'+reviews[1]['id'],'/api/reviewer/'+reviews[1]['id']+'/media','/api/projects/'+copies[1]['id'],'/api/clients/'+clients[1]['id']]:assert guest.get(path).status_code==403,path
assert guest.post('/api/reviewer/'+reviews[1]['id']+'/decision',json={'status':'approved'}).status_code==403
for project in copies:
 assert anonymous.get('/api/projects/'+project['id']).status_code==403
 assert anonymous.get('/media/uploads/'+project['scenes'][0]['asset']).status_code==403
malicious={**p,'id':'attempt-cross-client','scenes':copies[1]['scenes'],'clientId':''}
assert anonymous.put('/api/projects/'+malicious['id'],json=malicious).status_code==403
assert anonymous.put('/api/assets/'+copies[1]['scenes'][0]['asset'],json={'author':'Intento ajeno','license':'No autorizado'}).status_code==403
assert anonymous.get('/media/uploads/'+p['scenes'][0]['asset']).status_code==200
voice=wait(post(owner,'/projects/'+copies[0]['id']+'/scenes/0/voice'))
assert all(j['id']!=voice['id'] for j in anonymous.get('/api/jobs').json())
assert anonymous.get(voice['result']['url']).status_code==403
transcript=wait(post(owner,'/transcribe',{'asset':copies[0]['scenes'][0]['asset'],'target':15,'segments':[{'start':0,'end':2,'text':'Transcripción privada de prueba.'}]}))
assert all(j['id']!=transcript['id'] for j in anonymous.get('/api/jobs').json())
print('Two-client isolation: records, media, actions, and source-reference bypass',flush=True)
r=post(guest,'/reviewer/'+reviews[0]['id']+'/comments',{'time':1.25,'text':'Ajusta este corte.'});comment=r['comments'][0]
r=post(owner,'/reviews/'+reviews[0]['id']+'/comments',{'time':1.25,'text':'Lo revisamos.','parentId':comment['id']})
post(owner,'/reviews/'+reviews[0]['id']+'/comments/'+comment['id']+'/resolve',{'resolved':True})
approved=post(guest,'/reviewer/'+reviews[0]['id']+'/decision',{'status':'approved'})
assert approved['version']==1 and approved['status']=='approved' and approved['comments'][0]['time']==1.25
updated=copies[0];updated['title']='Nueva versión';put('projects',updated);job=wait(post(owner,'/projects/'+updated['id']+'/render',{'resolution':720}))
v2=post(owner,'/reviews',{'projectId':updated['id'],'jobId':job['id']});assert v2['version']==2 and v2['status']=='pending' and not v2['comments']
assert get('reviews',reviews[0]['id'])['status']=='approved'
assert guest.get('/api/reviewer/'+v2['id']).status_code==403
expired=post(owner,'/reviews/'+reviews[0]['id']+'/invites',{'hours':1});row=get('review_tokens',expired['id']);row['expires']=time.time()-1;put('review_tokens',row)
assert anonymous.get('/api/reviewer/'+reviews[0]['id'],headers={'authorization':'Bearer '+expired['token']}).status_code==403
post(owner,'/reviews/'+reviews[0]['id']+'/invites/'+invites[0]['id']+'/revoke')
assert guest.get('/api/reviewer/'+reviews[0]['id']+'/media').status_code==403
collab=post(owner,'/collaborators',{'name':'Colaborador cliente 1','clients':[clients[0]['id']]});staff=TestClient(app);staff.headers['authorization']='Bearer '+collab['token']
assert staff.get('/api/clients/'+clients[0]['id']).status_code==200
assert staff.get('/api/clients/'+clients[1]['id']).status_code==403
post(owner,'/collaborators/'+collab['id']+'/revoke')
assert staff.get('/api/clients/'+clients[0]['id']).status_code==403
assert owner.post('/api/reviews/'+v2['id']+'/share',json={}).status_code==409
Path('review-verification.json').write_text(json.dumps({'twoClientsIsolated':True,'mediaAndWritesProtected':True,'referenceBypassBlocked':True,'timestamp':1.25,'versionApprovalIsolated':True,'expiredAndRevokedRejected':True,'collaboratorScopedAndRevocable':True,'remoteUpload':False,'remoteRealEnvironmentTested':False},indent=2),encoding='utf-8')
print('Review versioning, comments, replies, resolution, expiry, revocation and roles passed',flush=True)
