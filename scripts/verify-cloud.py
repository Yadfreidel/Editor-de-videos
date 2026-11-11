"""Cloud boundary tests with HTTPS cookies; uses its own workspace, never user data."""
import os,sys,secrets,uuid,json,time,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['CLIP_WORKSPACE']='workspace/cloud-verification/'+uuid.uuid4().hex
os.environ['CLIP_REMOTE']='true';secret=secrets.token_urlsafe(32);os.environ['CLIP_OWNER_KEY']=secret
from backend.main import app,ROOT,Project,Scene,put,get,ffmpeg
from fastapi.testclient import TestClient
owner=TestClient(app,base_url='https://cloud.test');anonymous=TestClient(app,base_url='https://cloud.test')
def post(client,path,data=None):
 r=client.post('/api'+path,json=data or {});assert r.status_code==200,(path,r.text);return r.json()
def wait(jid):
 for _ in range(600):
  j=get('jobs',jid)
  if j['status'] in ('done','error'):assert j['status']=='done',j;return j
  time.sleep(.1)
 raise AssertionError('timeout')
assert anonymous.get('/api/health').status_code==200
assert anonymous.get('/api/health').json()['remote'] is True
assert str(ROOT) not in anonymous.get('/api/health').text
for path in ('/api/projects','/api/jobs','/api/assets','/api/metrics','/docs','/openapi.json'):
 assert anonymous.get(path).status_code==401,path
assert anonymous.post('/api/access/login',json={'key':'clave incorrecta'}).status_code==403
assert anonymous.post('/api/access/login',json={'key':'contraseña inválida'}).status_code==403
r=owner.post('/api/access/login',json={'key':secret});assert r.status_code==200
cookie=r.headers['set-cookie'];assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie
assert owner.get('/api/access/session').json()['role']=='owner'
p=post(owner,'/create',{'text':'Una historia privada en un servidor.','mode':'script'})
p['scenes'][0]['duration']=2;assert owner.put('/api/projects/'+p['id'],json=p).status_code==200
job=wait(post(owner,'/projects/'+p['id']+'/render',{'voice':'piper','resolution':720})['id'])
assert owner.get(job['result']['video']).status_code==200
assert anonymous.get(job['result']['video']).status_code==401
clients=[post(owner,'/clients',{'name':'Cliente nube '+str(i)}) for i in (1,2)]
copies=[post(owner,'/clients/'+client['id']+'/projects',{'projectId':p['id']}) for client in clients]
staff_key=post(owner,'/collaborators',{'name':'Equipo cliente 1','clients':[clients[0]['id']]})['token']
staff=TestClient(app,base_url='https://cloud.test');post(staff,'/access/login',{'key':staff_key})
visible=staff.get('/api/projects').json();assert all(x.get('clientId')==clients[0]['id'] for x in visible)
assert staff.get('/api/projects/'+p['id']).status_code==403
assert staff.get('/api/projects/'+copies[1]['id']).status_code==403
assert staff.post('/api/create',json={'text':'Un estudio ajeno','mode':'script'}).status_code==403
uploaded=staff.post('/api/upload',data={'clientId':clients[0]['id']},files={'file':('voice.wav',(ROOT/'jobs'/job['id']/'voice0.wav').read_bytes(),'audio/wav')})
assert uploaded.status_code==200,uploaded.text
assert uploaded.json()['clientId']==clients[0]['id']
assert anonymous.get(uploaded.json()['url']).status_code==401
render=wait(post(owner,'/projects/'+copies[0]['id']+'/render',{'resolution':720,'voice':'piper'})['id'])
review=post(owner,'/reviews',{'projectId':copies[0]['id'],'jobId':render['id']})
invite=post(owner,'/reviews/'+review['id']+'/invites',{'hours':1})
assert invite['url'].startswith('/review/#token=')
guest=TestClient(app,base_url='https://cloud.test');guest.headers['authorization']='Bearer '+invite['token']
assert guest.get('/api/reviewer/'+review['id']+'/media').status_code==200
assert guest.get('/api/projects').status_code in (401,403)
assert post(owner,'/reviews/'+review['id']+'/share')['notice']
post(guest,'/reviewer/'+review['id']+'/comments',{'time':1,'text':'Comentario de prueba de la versión privada.'})
assert post(guest,'/reviewer/'+review['id']+'/decision',{'status':'approved'})['status']=='approved'
post(owner,'/reviews/'+review['id']+'/invites/'+invite['id']+'/revoke')
assert guest.get('/api/reviewer/'+review['id']+'/media').status_code==403
post(owner,'/access/logout');assert owner.get('/api/projects').status_code==401
Path('cloud-verification.json').write_text(json.dumps({'httpsSessionCookie':True,'anonymousApiAndMediaBlocked':True,'ownerRenderWithAudio':True,'collaboratorsScoped':True,'privateReview':True,'guestRevocation':True,'logout':True,'workspace':str(ROOT),'deployedToInternet':False},indent=2),encoding='utf-8')
print('Cloud access, HTTPS cookie, private MP4, scoped collaborators and review passed.',flush=True)
