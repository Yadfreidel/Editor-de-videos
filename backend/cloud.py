"""Optional internet deployment boundary. Local operation is unchanged by default."""
import os
import time
import threading
from collections import defaultdict,deque
from pathlib import Path
from fastapi import Request,HTTPException
from fastapi.responses import JSONResponse,FileResponse
from fastapi.staticfiles import StaticFiles

def remote_enabled():return os.getenv('CLIP_REMOTE','false').lower()=='true'

def install_cloud(app,c):
    if not remote_enabled():return
    key=os.getenv('CLIP_OWNER_KEY','')
    if len(key)<32:raise RuntimeError('CLIP_REMOTE requiere CLIP_OWNER_KEY de al menos 32 caracteres. Configúrala como secreto del proveedor; no la añadas al repositorio.')
    if not hasattr(c,'production_principal'):raise RuntimeError('No se publica la API: corrige la migración antes de activar el servidor remoto.')
    attempts=defaultdict(deque);lock=threading.Lock()
    public={'/api/health','/api/access/login','/api/access/session'}
    @app.middleware('http')
    async def private_internet_api(request,call_next):
        path=request.url.path
        if path=='/api/access/login' and request.method=='POST':
            ip=request.client.host if request.client else 'unknown'
            with lock:
                queue=attempts[ip];now=time.monotonic()
                while queue and queue[0]<now-60:queue.popleft()
                if len(queue)>=20:return JSONResponse(status_code=429,content={'detail':'Demasiados intentos. Espera un minuto antes de volver a entrar.'},headers={'Retry-After':'60'})
                queue.append(now)
        protected=path.startswith(('/api/','/media/')) or path in ('/docs','/openapi.json','/redoc')
        if protected and path not in public and not path.startswith('/api/reviewer/') and request.method!='OPTIONS':
            actor=c.production_principal(request)
            if actor['role'] not in ('owner','collaborator'):
                return JSONResponse(status_code=401,content={'detail':'Entra con tu clave privada para acceder a este servidor.'},headers={'Cache-Control':'no-store'})
            if actor['role']=='collaborator' and (path=='/api/create' or path=='/api/brand' or (path.startswith('/api/brands') and request.method!='GET')):
                return JSONResponse(status_code=403,content={'detail':'Este acceso permite editar los clips de tus clientes asignados. Las plantillas globales y el estudio individual son del propietario.'})
        response=await call_next(request)
        if protected:
            response.headers['Cache-Control']='private, no-store'
            response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        return response
    @app.get('/api/access/session')
    def session(request:Request):
        actor=c.production_principal(request)
        return {'role':actor['role'],'remote':True,'name':actor.get('name','Propietario' if actor['role']=='owner' else '')}
    frontend=Path(os.getenv('CLIP_FRONTEND_DIR','/app/frontend'))
    if frontend.is_dir():
        @app.get('/review/{token}',include_in_schema=False)
        def legacy_review(token:str):return FileResponse(frontend/'review'/'index.html',headers={'Cache-Control':'private, no-store'})
        app.mount('/',StaticFiles(directory=frontend,html=True),name='private-cloud-interface')
