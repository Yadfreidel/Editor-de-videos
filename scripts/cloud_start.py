"""Single process: one SQLite database and one bounded media queue."""
import os
import uvicorn
if os.getenv('CLIP_REMOTE','false').lower()!='true':raise SystemExit('Este comando de despliegue requiere CLIP_REMOTE=true.')
if len(os.getenv('CLIP_OWNER_KEY',''))<32:raise SystemExit('Falta CLIP_OWNER_KEY. Configura un secreto de al menos 32 caracteres antes de publicar.')
port=int(os.getenv('PORT','8000'))
if not 1<=port<=65535:raise SystemExit('PORT no válido')
# Import by module name from the repository root, including paths with spaces on Windows.
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
options={}
if os.getenv('CLIP_TLS_CERT') and os.getenv('CLIP_TLS_KEY'):
 options={'ssl_certfile':os.environ['CLIP_TLS_CERT'],'ssl_keyfile':os.environ['CLIP_TLS_KEY']}
uvicorn.run('backend.main:app',host='0.0.0.0',port=port,workers=1,proxy_headers=True,**options)
