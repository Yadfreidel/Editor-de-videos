"""Local equivalent of GitHub Pages' repository subdirectory, for verification only."""
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
import os
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory='.next-pages',**kwargs)
    def do_GET(self):
        if not urlsplit(self.path).path.startswith('/Editor-de-videos/'):
            self.send_response(302);self.send_header('Location','/Editor-de-videos/');self.end_headers();return
        self.path=self.path.removeprefix('/Editor-de-videos');super().do_GET()
ThreadingHTTPServer(('127.0.0.1',int(os.getenv('CLIP_PAGES_TEST_PORT','8087'))),Handler).serve_forever()
