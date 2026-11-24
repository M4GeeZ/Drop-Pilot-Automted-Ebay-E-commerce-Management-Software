import os, tempfile, unittest, subprocess, sys, time, json, urllib.request, urllib.error, socket
from pathlib import Path
from auth import make_hash
class AuthHTTP(unittest.TestCase):
    def test_private_session(self):
        with tempfile.TemporaryDirectory() as temp:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            env={**os.environ,'DROPPILOT_DATA':temp,'DROPPILOT_EMAIL':'test@example.test','DROPPILOT_PASSWORD_HASH':make_hash('test-password-123')};env.pop('DATABASE_URL',None);env.pop('VERCEL',None)
            proc=subprocess.Popen([sys.executable,'server.py','--port',str(port)],cwd=Path(__file__).resolve().parents[1],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            def req(path,data=None,token=None):
                headers={'Content-Type':'application/json'}
                if token:headers['Authorization']='Bearer '+token
                r=urllib.request.Request(f'http://127.0.0.1:{port}/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
                try:
                    with urllib.request.urlopen(r,timeout=5) as x:return x.status,json.loads(x.read())
                except urllib.error.HTTPError as x:return x.code,json.loads(x.read())
            try:
                for _ in range(50):
                    try:status,_=req('auth/status');break
                    except OSError:time.sleep(.1)
                self.assertEqual(req('bootstrap')[0],401)
                self.assertEqual(req('auth/login',{'email':'test@example.test','password':'wrong'})[0],401)
                status,data=req('auth/login',{'email':'test@example.test','password':'test-password-123'});self.assertEqual(status,200);t=data['token']
                status,b=req('bootstrap',token=t);self.assertEqual(status,200);a=b['accounts'][0]['id']
                self.assertEqual(req('state?account='+a,token=t)[0],200)
                self.assertEqual(req('product',{'account':a,'product':{'title':'Test'}},t)[0],200)
                self.assertEqual(req('auth/logout',{},t)[0],200);self.assertEqual(req('bootstrap',token=t)[0],401)
                for _ in range(5):self.assertEqual(req('auth/login',{'email':'test@example.test','password':'wrong'})[0],401)
                self.assertEqual(req('auth/login',{'email':'test@example.test','password':'test-password-123'})[0],429)
            finally:proc.terminate();proc.wait(timeout=5)
