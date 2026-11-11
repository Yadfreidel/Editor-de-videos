"""Immutable review versions and locally scoped capabilities. No external upload."""
import hashlib
import json
import secrets
import shutil
import threading
import time
from fastapi import HTTPException,Request
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field

def install_review(app,c,protect,principal,require_owner):
    lock=threading.RLock()
    class ClientInput(BaseModel):
        name:str=Field(min_length=1,max_length=150)
        brandId:str=''
    def allowed(request,clientid):
        return protect(request,{'clientId':clientid})
    @app.get('/api/clients')
    def clients(request:Request):
        if principal(request)['role']=='anonymous':raise HTTPException(403,'Desbloquea las herramientas de agencia.')
        return c.visible_records(request,c.all_rows('clients'))
    @app.post('/api/clients')
    def create_client(req:ClientInput,request:Request):
        require_owner(request)
        if req.brandId:c.get('brand_profiles',req.brandId)
        key=c.uid();return c.put('clients',{'id':key,'clientId':key,**req.model_dump(),'created':c.now()})
    @app.get('/api/clients/{key}')
    def client(key:str,request:Request):
        data=protect(request,c.get('clients',key));return {**data,'projects':[p for p in c.all_rows('projects') if p.get('clientId')==key],'reviews':[r for r in c.all_rows('reviews') if r['clientId']==key]}
    class CopyProject(BaseModel):projectId:str
    @app.post('/api/clients/{key}/projects')
    def copy_project(key:str,req:CopyProject,request:Request):
        allowed(request,key);client=c.get('clients',key);p=protect(request,c.get('projects',req.projectId));p.update(id=c.uid(),clientId=key,title=p['title']+' · '+client['name'],updated=c.now(),batchId='')
        c.production_protect_resources(request,p)
        # Source projects and previous brand snapshots remain unchanged.
        if client.get('brandId'):
            b=c.get('brand_profiles',client['brandId']);c.production_protect_resources(request,{'logo':b.get('logo','')});p.update(brand=b['color'],font=b['font'],logo=b['logo'],brandSnapshot=b)
            for s in p['scenes']:s['color']=b['background']
        # Give this client its own originals; sharing a source never locks an existing individual project.
        refs={s.get(k) for s in p['scenes'] for k in ('asset','audio')}|{p.get('music'),p.get('logo')}
        aliases={}
        for ref in refs:
            if ref:
                try:src=c.file_path(ref)
                except ValueError as e:raise HTTPException(422,f'No se puede copiar el recurso {ref}: {e}. Reemplázalo en el proyecto o perfil de marca.')
                name=f"client-{key[:8]}-{c.uid()}{src.suffix}";shutil.copy2(src,c.ROOT/'uploads'/name);aliases[ref]=name
                metadata=next((a for a in c.all_rows('assets') if a['name']==ref),None)
                if metadata:c.put('assets',{**metadata,'id':name,'name':name,'url':'/media/uploads/'+name,'clientId':key,'created':c.now()})
        for s in p['scenes']:
            for field in ('asset','audio'):
                if s.get(field) in aliases:s[field]=aliases[s[field]]
        for field in ('logo','music'):
            if p.get(field) in aliases:p[field]=aliases[p[field]]
        if p.get('brandSnapshot') and p['brandSnapshot'].get('logo') in aliases:p['brandSnapshot']['logo']=aliases[p['brandSnapshot']['logo']]
        return c.put('projects',p)
    class Collaborator(BaseModel):
        name:str=Field(min_length=1,max_length=100)
        clients:list[str]
    @app.post('/api/collaborators')
    def collaborator(req:Collaborator,request:Request):
        require_owner(request)
        for key in req.clients:c.get('clients',key)
        token=secrets.token_urlsafe(32);data={'id':c.uid(),'name':req.name,'role':'collaborator','clients':req.clients,'hash':hashlib.sha256(token.encode()).hexdigest(),'created':c.now(),'revoked':False}
        c.put('principals',data);return {'id':data['id'],'token':token,'name':req.name,'clients':req.clients,'role':'collaborator'}
    @app.post('/api/collaborators/{key}/revoke')
    def revoke_collaborator(key:str,request:Request):
        require_owner(request);p=c.get('principals',key);p['revoked']=True;c.put('principals',p);return {'revoked':True}

    class ReviewInput(BaseModel):
        projectId:str
        jobId:str
    @app.post('/api/reviews')
    def create_review(req:ReviewInput,request:Request):
        p=protect(request,c.get('projects',req.projectId))
        if not p.get('clientId'):raise HTTPException(422,'Copia el proyecto a un espacio de cliente antes de crear la revisión.')
        allowed(request,p['clientId']);job=c.get('jobs',req.jobId);snapshot=job.get('payload',{}).get('project',{})
        if job['status']!='done' or snapshot.get('id')!=p['id'] or snapshot.get('clientId')!=p['clientId'] or not job.get('result',{}).get('video'):raise HTTPException(422,'Elige un render terminado de este proyecto y cliente.')
        source=c.ROOT/job['result']['video'].removeprefix('/media/')
        if not source.is_file():raise HTTPException(422,'El archivo del render ya no está disponible. Vuelve a renderizar.')
        with lock:
            prior=[r for r in c.all_rows('reviews') if r['projectId']==p['id']]
            existing=next((r for r in prior if r['jobId']==req.jobId),None)
            if existing:return existing
            key=c.uid();dest=c.ROOT/'private_reviews'/f'{key}.mp4';shutil.copyfile(source,dest)
            with dest.open('rb') as source_file:digest=hashlib.file_digest(source_file,'sha256').hexdigest()
            data={'id':key,'clientId':p['clientId'],'projectId':p['id'],'jobId':job['id'],'version':len(prior)+1,'title':snapshot['title'],'description':snapshot.get('description',''),'snapshot':snapshot,'sha256':digest,'duration':job['result']['duration'],'status':'pending','comments':[],'events':[],'created':c.now()}
            return c.put('reviews',data)
    @app.get('/api/reviews')
    def reviews(request:Request):
        if principal(request)['role']=='anonymous':raise HTTPException(403,'Desbloquea agencia.')
        return c.visible_records(request,c.all_rows('reviews'))
    def owner_review(key,request):return protect(request,c.get('reviews',key))
    @app.get('/api/reviews/{key}')
    def review(key:str,request:Request):
        r=owner_review(key,request);versions=[x for x in c.all_rows('reviews') if x['projectId']==r['projectId']]
        return {**r,'media':f'/api/reviews/{key}/media','versions':[{'id':x['id'],'version':x['version'],'status':x['status'],'created':x['created']} for x in versions],'tokens':[{k:v for k,v in t.items() if k!='hash'} for t in c.all_rows('review_tokens') if t['reviewId']==key]}
    def file(key):
        path=c.ROOT/'private_reviews'/f'{key}.mp4'
        if not path.is_file():raise HTTPException(404,'La vista previa de esta versión no está disponible.')
        return FileResponse(path,media_type='video/mp4',filename=f'revision-{key[:8]}.mp4',content_disposition_type='inline',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
    @app.get('/api/reviews/{key}/media')
    def owner_media(key:str,request:Request):owner_review(key,request);return file(key)
    class Invite(BaseModel):
        name:str=Field(default='Cliente invitado',min_length=1,max_length=100)
        hours:float=Field(default=48,gt=0,le=168)
    @app.post('/api/reviews/{key}/invites')
    def invite(key:str,req:Invite,request:Request):
        r=owner_review(key,request);token=secrets.token_urlsafe(32);data={'id':c.uid(),'hash':hashlib.sha256(token.encode()).hexdigest(),'reviewId':key,'clientId':r['clientId'],'version':r['version'],'role':'reviewer','name':req.name,'expires':time.time()+req.hours*3600,'revoked':False,'created':c.now()};c.put('review_tokens',data)
        cloud=c.os.getenv('CLIP_REMOTE','false').lower()=='true'
        return {'id':data['id'],'url':('/review/#token=' if cloud else '/review/')+token,'token':token,'expires':data['expires'],'notice':'Enlace privado de esta versión en el servidor, con vencimiento y revocación.' if cloud else 'Enlace local: funciona en este equipo. Para acceso fuera de la PC hace falta un servicio remoto autorizado; no se ha subido ningún archivo.'}
    @app.post('/api/reviews/{key}/invites/{tokenid}/revoke')
    def revoke(key:str,tokenid:str,request:Request):
        owner_review(key,request);t=c.get('review_tokens',tokenid)
        if t['reviewId']!=key:raise HTTPException(403,'El enlace no pertenece a esta versión')
        t['revoked']=True;c.put('review_tokens',t);return {'revoked':True}
    @app.post('/api/reviews/{key}/share')
    def share(key:str,request:Request):
        owner_review(key,request)
        if c.os.getenv('CLIP_REMOTE','false').lower()=='true':return {'notice':'La vista previa seleccionada ya está en este servidor privado. Crea un enlace de revisión con vencimiento; no se publican originales ni otros archivos.'}
        raise HTTPException(409,'Servicio remoto no configurado. Puedes descargar la vista previa real. No se sube nada; un adaptador remoto debe exigir confirmación, HTTPS y permisos por cliente, clip y versión.')
    def reviewer(key,request):
        token=request.headers.get('authorization','').removeprefix('Bearer ').strip()
        if not token:raise HTTPException(401,'Falta el enlace autorizado de revisión')
        hashed=hashlib.sha256(token.encode()).hexdigest();t=next((t for t in c.all_rows('review_tokens') if secrets.compare_digest(t['hash'],hashed)),None)
        if not t or t['revoked'] or t['expires']<=time.time():raise HTTPException(403,'El enlace no existe, expiró o fue revocado.')
        r=c.get('reviews',key)
        if t['reviewId']!=key or t['clientId']!=r['clientId'] or t['version']!=r['version']:raise HTTPException(403,'El enlace no autoriza este cliente o versión.')
        return r,t
    @app.get('/api/reviewer/session')
    def review_session(request:Request):
        token=request.headers.get('authorization','').removeprefix('Bearer ').strip();hashed=hashlib.sha256(token.encode()).hexdigest()
        t=next((t for t in c.all_rows('review_tokens') if secrets.compare_digest(t['hash'],hashed)),None)
        if not t:raise HTTPException(403,'Enlace no válido')
        r,t=reviewer(t['reviewId'],request);return public_review(r,t)
    def public_review(r,t):return {k:v for k,v in {**r,'reviewer':t['name'],'role':'reviewer','media':f"/api/reviewer/{r['id']}/media"}.items() if k not in ('snapshot','sha256','jobId')}
    @app.get('/api/reviewer/{key}')
    def guest_review(key:str,request:Request):r,t=reviewer(key,request);return public_review(r,t)
    @app.get('/api/reviewer/{key}/media')
    def guest_media(key:str,request:Request):reviewer(key,request);return file(key)
    class Comment(BaseModel):
        time:float=Field(ge=0)
        text:str=Field(min_length=1,max_length=4000)
        parentId:str=''
    def add_comment(key,req,actor):
        with lock:
            r=c.get('reviews',key)
            if req.time>r['duration']:raise HTTPException(422,'El comentario debe situarse dentro de la versión revisada.')
            if req.parentId and not any(x['id']==req.parentId for x in r['comments']):raise HTTPException(422,'Comentario original no encontrado en esta versión')
            r['comments'].append({'id':c.uid(),**req.model_dump(),'author':actor.get('name','Propietario'),'role':actor['role'],'resolved':False,'created':c.now(),'version':r['version']});return c.put('reviews',r)
    @app.post('/api/reviews/{key}/comments')
    def comment(key:str,req:Comment,request:Request):owner_review(key,request);return add_comment(key,req,principal(request))
    @app.post('/api/reviewer/{key}/comments')
    def guest_comment(key:str,req:Comment,request:Request):r,t=reviewer(key,request);return public_review(add_comment(key,req,t),t)
    class Resolve(BaseModel):resolved:bool=True
    def resolve(key,commentid,req):
        with lock:
            r=c.get('reviews',key);comment=next((x for x in r['comments'] if x['id']==commentid),None)
            if not comment:raise HTTPException(404,'Comentario no encontrado')
            comment['resolved']=req.resolved;return c.put('reviews',r)
    @app.post('/api/reviews/{key}/comments/{commentid}/resolve')
    def resolve_owner(key:str,commentid:str,req:Resolve,request:Request):owner_review(key,request);return resolve(key,commentid,req)
    @app.post('/api/reviewer/{key}/comments/{commentid}/resolve')
    def resolve_guest(key:str,commentid:str,req:Resolve,request:Request):r,t=reviewer(key,request);return public_review(resolve(key,commentid,req),t)
    class Decision(BaseModel):
        status:str=Field(pattern='^(approved|changes_requested|pending)$')
    def set_decision(key,req,actor):
        with lock:
            r=c.get('reviews',key);r['status']=req.status;r['events'].append({'id':c.uid(),'status':req.status,'author':actor.get('name','Propietario'),'role':actor['role'],'version':r['version'],'created':c.now()});return c.put('reviews',r)
    @app.post('/api/reviews/{key}/decision')
    def decide(key:str,req:Decision,request:Request):owner_review(key,request);return set_decision(key,req,principal(request))
    @app.post('/api/reviewer/{key}/decision')
    def guest_decide(key:str,req:Decision,request:Request):r,t=reviewer(key,request);return public_review(set_decision(key,req,t),t)
