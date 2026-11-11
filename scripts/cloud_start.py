"""Single process: one SQLite database and one bounded media queue."""
import os
import sys
if os.getenv('CLIP_REMOTE','false').lower()!='true':raise SystemExit('Este comando de despliegue requiere CLIP_REMOTE=true.')
if len(os.getenv('CLIP_OWNER_KEY',''))<32:raise SystemExit('Falta CLIP_OWNER_KEY. Configura un secreto de al menos 32 caracteres antes de publicar.')
port=int(os.getenv('PORT','8000'))
if not 1<=port<=65535:raise SystemExit('PORT no válido')
args=[sys.executable,'-m','uvicorn','backend.main:app','--host','0.0.0.0','--port',str(port),'--workers','1','--proxy-headers']
if os.getenv('CLIP_TLS_CERT') and os.getenv('CLIP_TLS_KEY'):args+=['--ssl-certfile',os.environ['CLIP_TLS_CERT'],'--ssl-keyfile',os.environ['CLIP_TLS_KEY']]
os.execv(sys.executable,args)
