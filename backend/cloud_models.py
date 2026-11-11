"""Explicit build-time public model downloads. Never reads user media or credentials."""
import os
import subprocess
import sys
from pathlib import Path
from huggingface_hub import snapshot_download
folder=Path(os.getenv('CLIP_MODEL_DIR','/opt/clip-models'));folder.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,'-m','piper.download_voices','--download-dir',str(folder/'piper'),'es_ES-sharvard-medium'],check=True)
snapshot_download(repo_id='Systran/faster-whisper-tiny',local_dir=str(folder/'whisper-tiny'))
