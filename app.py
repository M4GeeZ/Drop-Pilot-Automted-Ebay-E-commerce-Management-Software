"""Vercel Flask entry point; reuse the same tested local request handlers."""
import io, threading
from types import SimpleNamespace
from flask import Flask, request, Response
import server
app=Flask(__name__,static_folder=None)
app.config['MAX_CONTENT_LENGTH']=8_000_000
_init_lock=threading.Lock();_ready=False
class Adapter(server.Handler):
    def __init__(self):
        self.path=request.full_path.rstrip('?');self.headers=request.headers;self.rfile=io.BytesIO(request.get_data());self.server=SimpleNamespace(server_port=8765);self.response=None
    def send_data(self,status,content,typ='application/json; charset=utf-8',headers=None):
        if not isinstance(content,bytes):content=server.j(content).encode() if typ.startswith('application/json') else content.encode()
        self.response=Response(content,status=status,content_type=typ,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",**(headers or {})})
        return self.response
@app.route('/',defaults={'path':''},methods=['GET','POST'])
@app.route('/<path:path>',methods=['GET','POST'])
def route(path):
    global _ready
    h=Adapter()
    # Static login assets do not need a database connection.
    if path.startswith('api/') and path!='api/auth/status' and not _ready:
        with _init_lock:
            if not _ready:
                try:server.init();_ready=True
                except Exception:
                    app.logger.exception('Database initialization failed');return h.send_data(503,{'error':'Database not ready. Check DATABASE_URL and deployment logs.'})
    h.handle_req(request.method)
    return h.response if h.response is not None else h.send_data(500,{'error':'Request failed'})
