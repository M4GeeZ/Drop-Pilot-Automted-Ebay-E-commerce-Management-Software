"""Local-only DropPilot portal. Start with python server.py."""
import json, os, sqlite3, threading, time, pathlib, csv, io, secrets, argparse, webbrowser, traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from contextlib import contextmanager
from engine import *
from sheets import Excel, Google, ID_HEADER
import auth
from cloud_db import PG
CLOUD=bool(os.environ.get("VERCEL")); DATABASE_URL=os.environ.get("DATABASE_URL", "")
AUTH_REQUIRED=CLOUD or auth.configured()
ROOT=pathlib.Path(__file__).resolve().parent; os.chdir(ROOT)
DATA=pathlib.Path(os.environ.get('DROPPILOT_DATA','/tmp/droppilot' if CLOUD else ROOT/'data'));DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'droppilot.sqlite3'; LOCK=threading.RLock(); SYNC_LOCKS={}; STOP=threading.Event(); TOKEN=secrets.token_urlsafe(32)
@contextmanager
def db():
    if DATABASE_URL:
        c=PG(DATABASE_URL)
    else:
        if CLOUD:raise RuntimeError('DATABASE_URL must be configured for persistent cloud storage')
        c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=15000')
    try:
        if DATABASE_URL:c.execute('SELECT pg_advisory_xact_lock(710218462)')
        else:c.execute('BEGIN IMMEDIATE')
        yield c;c.commit()
    except: c.rollback();raise
    finally:c.close()
def j(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'))
def load(s):return json.loads(s)
def init():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,name TEXT NOT NULL,settings TEXT NOT NULL,columns_json TEXT NOT NULL,custom TEXT NOT NULL,connection TEXT NOT NULL,last_sync TEXT, sync_status TEXT DEFAULT 'Not connected',demo INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,body TEXT NOT NULL,deleted INTEGER DEFAULT 0, dirty INTEGER DEFAULT 1, created TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_products_account ON products(account,deleted);
        CREATE INDEX IF NOT EXISTS ix_products_asin ON products(account,deleted,json_extract(body,'$.asin'));
        CREATE TABLE IF NOT EXISTS baselines(account TEXT,product TEXT,col TEXT,value TEXT,PRIMARY KEY(account,product,col));
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,account TEXT,kind TEXT,title TEXT,detail TEXT,created TEXT,seen INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS ix_events_account ON events(account,created);
        CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY,account TEXT,product TEXT,body TEXT,created TEXT);
        CREATE INDEX IF NOT EXISTS ix_hist ON history(account,product,created);
        CREATE TABLE IF NOT EXISTS competitors(id TEXT PRIMARY KEY,account TEXT,product TEXT,body TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, expires BIGINT NOT NULL);
        CREATE TABLE IF NOT EXISTS login_limit(id TEXT PRIMARY KEY, attempts INTEGER NOT NULL, until_time BIGINT NOT NULL);
        ''')
        if not c.execute('SELECT 1 FROM accounts').fetchone():
            a=create_account(c,'Demo workspace',True);seed(c,a)
def account(c,a):
    x=c.execute('SELECT * FROM accounts WHERE id=?',(a,)).fetchone()
    if not x:raise ValueError('Workspace not found')
    return {**dict(x),'settings':load(x['settings']),'columns':load(x['columns_json']),'custom':load(x['custom']),'connection':load(x['connection'])}
def create_account(c,name,demo=False):
    a=uid();c.execute('INSERT INTO accounts(id,name,settings,columns_json,custom,connection,demo) VALUES(?,?,?,?,?,?,?)',(a,name,j(DEFAULT_SETTINGS),j(columns_default()),'[]','{}',int(demo)));return a
def event(c,a,kind,title,detail=''):
    c.execute('INSERT INTO events VALUES(?,?,?,?,?,?,0)',(uid(),a,kind,title,detail,now()))
def get_product(c,a,pid,include_deleted=False):
    x=c.execute('SELECT * FROM products WHERE account=? AND id=?',(a,pid)).fetchone()
    if not x or (x['deleted'] and not include_deleted):raise ValueError('Product not found')
    return {**load(x['body']),'id':x['id'],'deleted':bool(x['deleted']),'dirty':bool(x['dirty']),'created':x['created']}
def all_products(c,a,deleted=False):
    return [{**load(x['body']),'id':x['id'],'deleted':bool(x['deleted']),'dirty':bool(x['dirty']),'created':x['created']} for x in c.execute('SELECT * FROM products WHERE account=? AND deleted=? ORDER BY created DESC,id',(a,int(deleted)))]
def save_product(c,a,data,pid=None,quiet=False,external=False):
    ac=account(c,a);old=get_product(c,a,pid,True) if pid else None
    p=normalize(data,ac['settings'],old,ac['custom']);p.pop('id',None);p.pop('deleted',None);p.pop('dirty',None);p.pop('created',None)
    if p['status']!='Archived' and p.get('asin'):
        if c.execute("SELECT 1 FROM products WHERE account=? AND deleted=0 AND json_extract(body,'$.asin')=? AND id<>? LIMIT 1",(a,p['asin'],pid or '')).fetchone():raise ValueError('This ASIN already exists in this workspace')
    if pid:c.execute('UPDATE products SET body=?,dirty=1 WHERE account=? AND id=?',(j(p),a,pid))
    else:
        pid=uid();c.execute('INSERT INTO products VALUES(?,?,?,?,?,?)',(pid,a,j(p),0,1,now()))
    if not old or any(old.get(k)!=p.get(k) for k in ('source_price','shipping','selling_price','stock','profit','last_checked')):
        c.execute('INSERT INTO history VALUES(?,?,?,?,?)',(uid(),a,pid,j({k:p.get(k) for k in ('source_price','shipping','selling_price','stock','profit','last_checked')}),now()))
    if old:
        if old.get('stock')!=p['stock'] and p['stock']!='Unknown':event(c,a,'warning' if p['stock']=='Out of stock' else 'success',p['stock'],p['title'])
        if old.get('source_price')!=p['source_price']:event(c,a,'warning' if p['source_price']>old.get('source_price',0) else 'info','Source price changed',f"{p['title']} · ${old.get('source_price',0):.2f} → ${p['source_price']:.2f}")
        if old.get('shipping')!=p['shipping']:event(c,a,'info','Shipping changed',p['title'])
        if old.get('profit',0)>=ac['settings']['target_profit']>p['profit']:event(c,a,'warning','Profit below target',p['title'])
    if not quiet:event(c,a,'success','Product updated' if old else 'Product added',p['title'])
    return pid

def seed(c,a):
    sample=[('Compact USB-C Charging Hub',12.99,27.49,'In stock',18),('Bamboo Drawer Organizer',16.50,35.95,'In stock',26),('Portable Desk Fan',19.99,29.99,'Out of stock',12),('Travel Packing Cubes Set',14.25,31.49,'In stock',35),('Stainless Steel Water Bottle',11.95,24.99,'In stock',19),('Adjustable Laptop Stand',24.50,42.99,'Unknown',10),('Silicone Kitchen Utensil Set',17.40,34.99,'In stock',23),('Wireless Mouse Pad',9.99,21.95,'In stock',8)]
    for i,(title,cost,sell,stock,sold) in enumerate(sample):save_product(c,a,dict(title=title,source_price=cost,selling_price=sell,competitor_price=sell+.02,stock=stock,status='Published' if i<6 else 'Draft',sold7=sold,sold14=sold*2,sold30=sold*4,category='General',keyword=title.split()[0],notes='Illustrative demo product; not live marketplace data.',last_checked=''),quiet=True)
    event(c,a,'info','Welcome to DropPilot','Sample workspace. Create a new workspace for real products.')

def sync(a):
    with LOCK: lock=SYNC_LOCKS.setdefault(a,threading.Lock())
    if not lock.acquire(False):return {'busy':True,'message':'Sync already running'}
    try:
        with db() as c:ac=account(c,a)
        cfg=ac['connection'];cols=ac['columns']
        if not cfg:raise ValueError('Connect a spreadsheet first')
        if CLOUD and cfg['type']=='excel':raise ValueError('Local Excel sync requires the local DropPilot app; Vercel cannot access your PC files')
        adapter=(Excel if cfg['type']=='excel' else Google)(cfg);rows,formulas=adapter.read();headers=list(rows[0]) if rows else []
        # Header names are unique, exact match; new fields append without moving user data.
        if len([x for x in headers if x not in ('',None)])!=len(set(str(x) for x in headers if x not in ('',None))):raise ValueError('Duplicate spreadsheet headers. Make headers unique before syncing.')
        edits=[]; conflicts=[]; imported=0; pushed=0
        def header(h):
            if h not in headers:headers.append(h);edits.append((1,len(headers),h))
            return headers.index(h)+1
        positions={col['id']:header(col['heading']) for col in cols}; idc=header(ID_HEADER)
        def cell(row,col):return row[col-1] if len(row)>=col else None
        with LOCK,db() as c:
            # Keep database transaction open until remote write completes: failure rolls back imported changes/baselines.
            latest=account(c,a)
            if latest['connection']!=cfg or latest['columns']!=cols:raise ValueError('Connection or mapping changed during sync; retry')
            baseline={(r['product'],r['col']):load(r['value']) for r in c.execute('SELECT * FROM baselines WHERE account=?',(a,))}
            products={p['id']:p for p in all_products(c,a,False)};deleted={p['id'] for p in all_products(c,a,True)};seen=set()
            for r,row in enumerate(rows[1:],2):
                pid=cell(row,idc); pid=str(pid).strip() if pid else ''
                vals={col['source']:cell(row,positions[col['id']]) for col in cols if col['source'] not in DERIVED and (r,positions[col['id']]) not in formulas}
                if not pid and not any(v not in ('',None) for v in vals.values()):continue
                if pid in seen:conflicts.append(f'Row {r}: duplicate DropPilot ID');continue
                if pid in deleted:
                    seen.add(pid);continue # preserve historical external row, no destructive delete
                if not pid or pid not in products:
                    if pid:conflicts.append(f'Row {r}: unknown DropPilot ID, clear ID to import');continue
                    data={k:v for k,v in vals.items() if not k.startswith('custom_') and v not in ('',None)};data['custom']={k:v for k,v in vals.items() if k.startswith('custom_')};data['status']=data.get('status','Published')
                    try:pid=save_product(c,a,data,quiet=True,external=True)
                    except ValueError as e:conflicts.append(f'Row {r}: {e}');continue
                    edits.append((r,idc,pid));products[pid]=get_product(c,a,pid);imported+=1
                    # App values derived from normalized input; no conflict on new import.
                    fresh=True
                else:fresh=False
                seen.add(pid);p=products[pid];incoming={};custom={};blocked=set()
                for col in cols:
                    k=col['source'];pos=positions[col['id']];sheet=cell(row,pos);app=column_value(p,col);key=(pid,col['id']);base=baseline.get(key)
                    if (r,pos) in formulas:continue
                    if fresh or k in DERIVED:continue
                    if key not in baseline:
                        if sheet not in ('',None) and not same(sheet,app):
                            conflicts.append(f'Row {r} · {col["heading"]}: existing values differ; align manually');blocked.add(col['id'])
                        continue
                    sc=not same(sheet,base); pc=not same(app,base)
                    if sc and pc and not same(sheet,app):conflicts.append(f'Row {r} · {col["heading"]}: both sides changed; align manually');blocked.add(col['id']);continue
                    if sc and not pc:
                        if k.startswith('custom_'):custom[k]=sheet
                        else:incoming[k]=sheet
                if incoming or custom:
                    try:
                        incoming['custom']=custom;save_product(c,a,incoming,pid,quiet=True,external=True);p=get_product(c,a,pid);products[pid]=p;imported+=1
                    except ValueError as e:conflicts.append(f'Row {r}: {e}');continue
                for col in cols:
                    pos=positions[col['id']];v=column_value(p,col)
                    if (r,pos) in formulas or col['id'] in blocked:continue
                    if not same(v,cell(row,pos)):edits.append((r,pos,v));pushed+=1
                    c.execute('INSERT OR REPLACE INTO baselines VALUES(?,?,?,?)',(a,pid,col['id'],j(v)))
                if not blocked:c.execute('UPDATE products SET dirty=0 WHERE id=?',(pid,))
            nextrow=max(2,len(rows)+1)
            for pid,p in products.items():
                if pid in seen or p['status']!='Published':continue
                if any(key[0]==pid for key in baseline):conflicts.append(f'{p["title"]}: linked row removed externally; restore row or archive product');continue
                edits.append((nextrow,idc,pid))
                for col in cols:
                    v=column_value(p,col);edits.append((nextrow,positions[col['id']],v));c.execute('INSERT OR REPLACE INTO baselines VALUES(?,?,?,?)',(a,pid,col['id'],j(v)))
                c.execute('UPDATE products SET dirty=0 WHERE id=?',(pid,));nextrow+=1;pushed+=1
            adapter.write(edits)
            status='Conflicts — review' if conflicts else 'Synchronized';c.execute('UPDATE accounts SET last_sync=?,sync_status=? WHERE id=?',(now(),status,a))
            if conflicts:event(c,a,'warning','Spreadsheet needs review','; '.join(conflicts[:12]))
            elif edits or imported:event(c,a,'success','Spreadsheet synchronized',f'{imported} imported/updated · {pushed} cells/rows written')
        return dict(imported=imported,written=pushed,conflicts=conflicts,message=status)
    except Exception as e:
        with db() as c:
            prev=account(c,a)['sync_status'];c.execute('UPDATE accounts SET sync_status=? WHERE id=?',('Sync failed',a));
            if prev!='Sync failed':event(c,a,'warning','Synchronization failed',str(e)[:500])
        raise
    finally:lock.release()

DUE={}
def worker():
    while not STOP.wait(3):
        try:
            with db() as c:accounts=[account(c,r['id']) for r in c.execute('SELECT id FROM accounts')]
            for ac in accounts:
                a=ac['id'];cfg=ac['connection']
                if not cfg or not cfg.get('auto'):continue
                interval=max(15,int(ac['settings'].get('interval',60)))
                if time.monotonic()<DUE.get(a,0):continue
                DUE[a]=time.monotonic()+interval
                try:sync(a)
                except Exception as e:print('Sync:',str(e)[:250],flush=True)
        except Exception as e:print('Worker:',e,flush=True)

def queue_sync(a):
    # Background synchronization is independent of the UI request.
    DUE[a]=0

def state(c,a):
    ac=account(c,a);ac.pop('columns_json',None)
    return {'account':ac,'products':all_products(c,a),'trash':all_products(c,a,True),'events':[dict(r) for r in c.execute('SELECT * FROM events WHERE account=? ORDER BY created DESC,rowid DESC LIMIT 100',(a,))],'accounts':[dict(r) for r in c.execute('SELECT id,name,demo,sync_status FROM accounts ORDER BY rowid')]}

class Handler(BaseHTTPRequestHandler):
    server_version='DropPilot/1.0'
    def log_message(self,fmt,*args):pass
    def send_data(self,status,content,typ='application/json; charset=utf-8',headers=None):
        if not isinstance(content,bytes):content=j(content).encode() if typ.startswith('application/json') else content.encode()
        self.send_response(status);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(content)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(content)
    def do_GET(self):self.handle_req('GET')
    def do_POST(self):self.handle_req('POST')
    def handle_req(self,method):
        try:
            host=self.headers.get('Host','');port=self.server.server_port
            if not CLOUD and host not in (f'127.0.0.1:{port}',f'localhost:{port}'):return self.send_data(403,{'error':'Localhost only'})
            if method=='POST' and self.headers.get('Origin') not in (None,('https://' if CLOUD else 'http://')+host):return self.send_data(403,{'error':'Invalid origin'})
            u=urlparse(self.path);path=u.path;q=parse_qs(u.query);a=q.get('account',[''])[0]
            if path=='/api/auth/status' and method=='GET':return self.send_data(200,{'required':AUTH_REQUIRED,'configured':auth.configured(),'cloud':CLOUD})
            if path=='/api/auth/login' and method=='POST':
                if not auth.configured():return self.send_data(503,{'error':'Configure the login environment variables first'})
                n=int(self.headers.get('Content-Length','0'))
                if n<1 or n>8192:return self.send_data(400,{'error':'Invalid login request'})
                d=load(self.rfile.read(n));email=str(d.get('email',''));password=str(d.get('password',''))
                with db() as c:status,t=auth.login(c,email,password)
                return self.send_data(status,{'token':t} if t else {'error':'Too many attempts. Try again in five minutes.' if status==429 else 'Incorrect email or password.'})
            if path.startswith('/api/'):
                t=self.headers.get('Authorization','').removeprefix('Bearer ')
                if AUTH_REQUIRED:
                    if not auth.configured():return self.send_data(503,{'error':'Login is not configured'})
                    with db() as c:allowed=auth.authorized(c,t)
                    if not allowed:return self.send_data(401,{'error':'Please sign in again'})
                    if path=='/api/auth/logout' and method=='POST':
                        with db() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(auth.digest(t),))
                        return self.send_data(200,{'ok':True})
                elif method=='POST' and self.headers.get('X-DropPilot-Token')!=TOKEN:return self.send_data(403,{'error':'Invalid local request'})
            if not path.startswith('/api/'):
                files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/favicon.svg':('favicon.svg','image/svg+xml')}
                if path not in files:return self.send_data(404,{'error':'Not found'})
                f,t=files[path];return self.send_data(200,(ROOT/'static'/f).read_bytes(),t)
            if method=='GET':
                with db() as c:
                    if path=='/api/bootstrap':return self.send_data(200,{'token':TOKEN,'accounts':[dict(r) for r in c.execute('SELECT id,name,demo FROM accounts ORDER BY rowid')],'fields':FIELDS,'derived':list(DERIVED),'cloud':CLOUD,'auth':AUTH_REQUIRED})
                    if path=='/api/state':return self.send_data(200,state(c,a))
                    if path=='/api/history':return self.send_data(200,[dict(r)|{'body':load(r['body'])} for r in c.execute('SELECT * FROM history WHERE account=? AND product=? ORDER BY created DESC,rowid DESC LIMIT 100',(a,q.get('id',[''])[0]))])
                    if path=='/api/competitors':return self.send_data(200,[{'id':r['id'],**load(r['body'])} for r in c.execute('SELECT * FROM competitors WHERE account=? AND product=?',(a,q.get('id',[''])[0]))])
                    if path=='/api/export':
                        ac=account(c,a);s=io.StringIO();w=csv.writer(s);cols=ac['columns'];w.writerow([x['heading'] for x in cols]);
                        def safe(v):return "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v
                        for p in all_products(c,a):w.writerow([safe(column_value(p,col)) for col in cols])
                        return self.send_data(200,s.getvalue().encode('utf-8-sig'),'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename="droppilot-products.csv"'})
                return self.send_data(404,{'error':'Unknown endpoint'})
            n=int(self.headers.get('Content-Length','0'))
            if n>8_000_000:return self.send_data(413,{'error':'Request too large'})
            data=load(self.rfile.read(n) or b'{}');a=data.get('account',a)
            if path=='/api/sync':return self.send_data(200,sync(a))
            if path=='/api/auto-sync':
                with db() as c:ac=account(c,a)
                if not ac['connection'].get('auto') or ac['connection'].get('type')!='google':return self.send_data(200,{'skipped':True})
                from datetime import datetime,timezone
                last=ac.get('last_sync');interval=max(30,int(ac['settings'].get('interval',60)))
                if last and (datetime.now(timezone.utc)-datetime.fromisoformat(last.replace('Z','+00:00'))).total_seconds()<interval:return self.send_data(200,{'skipped':True})
                return self.send_data(200,sync(a))
            with LOCK,db() as c:
                if path=='/api/accounts':
                    name=str(data.get('name','')).strip()[:80]
                    if not name:raise ValueError('Workspace name required')
                    return self.send_data(200,{'id':create_account(c,name)})
                ac=account(c,a)
                if path=='/api/product':
                    pid=save_product(c,a,data['product'],data.get('id'));queue_sync(a);result={'id':pid}
                elif path=='/api/bulk':
                    ids=list(dict.fromkeys(data.get('ids',[])))[:1000];action=data.get('action')
                    for pid in ids:
                        p=get_product(c,a,pid,True)
                        if action=='delete':c.execute('UPDATE products SET deleted=1 WHERE account=? AND id=?',(a,pid))
                        elif action=='restore':c.execute('UPDATE products SET deleted=0,dirty=1 WHERE account=? AND id=?',(a,pid))
                        elif action in ('Published','Archived','Draft'):save_product(c,a,{'status':action},pid,quiet=True)
                        else:raise ValueError('Unknown bulk action')
                    event(c,a,'success','Products updated',f'{len(ids)} · {action}');queue_sync(a);result={'count':len(ids)}
                elif path=='/api/settings':
                    settings=ac['settings'];settings.update({k:v for k,v in data['settings'].items() if k in DEFAULT_SETTINGS})
                    for k in ('fee_pct','fixed_fee','ad_pct','target_profit','undercut','min_roi','interval'):settings[k]=float(dec(settings[k],k))
                    if settings['fee_pct']+settings['ad_pct']>=100 or not 15<=settings['interval']<=86400:raise ValueError('Invalid fee or sync interval (15–86400 seconds)')
                    c.execute('UPDATE accounts SET settings=? WHERE id=?',(j(settings),a))
                    for p in all_products(c,a):
                        change={k:settings[k] for k in ('fee_pct','fixed_fee','ad_pct')} if data.get('apply_fees') else {};save_product(c,a,change,p['id'],quiet=True)
                    event(c,a,'success','Settings saved');queue_sync(a);result={}
                elif path=='/api/columns':
                    cols=data['columns'];custom=data.get('custom',ac['custom']);keys={f['key'] for f in custom};heads=[str(x['heading']).strip() for x in cols]
                    if not cols or len(cols)>100 or any(not h or h==ID_HEADER for h in heads) or len(set(heads))!=len(heads):raise ValueError('Use 1–100 unique, non-empty headings')
                    if len({x['id'] for x in cols})!=len(cols) or len({x['source'] for x in cols})!=len(cols):raise ValueError('Each field can be mapped once')
                    for col,h in zip(cols,heads):
                        col['heading']=h[:120]
                        if col['source'] not in FIELDS and col['source'] not in keys:raise ValueError('Unknown column source')
                    for f in custom:
                        if not f['key'].startswith('custom_') or f.get('type') not in ('text','number','url'):raise ValueError('Invalid custom field')
                    oldcols={x['id']:x for x in ac['columns']}
                    for col in cols:
                        oldcol=oldcols.get(col['id'])
                        if oldcol and (oldcol['heading']!=col['heading'] or oldcol['source']!=col['source']):c.execute('DELETE FROM baselines WHERE account=? AND col=?',(a,col['id']))
                    c.execute('UPDATE accounts SET columns_json=?,custom=? WHERE id=?',(j(cols),j(custom),a));event(c,a,'success','Column mapping saved','New headers append to connected sheets; existing physical order is preserved.');queue_sync(a);result={}
                elif path=='/api/connect':
                    cfg=data.get('connection',{});old=ac['connection']
                    if cfg and (cfg.get('type') not in ('excel','google') or not str(cfg.get('path','')).strip()):raise ValueError('Select a spreadsheet and enter its path or link')
                    if CLOUD and cfg.get('type')=='excel':raise ValueError('Connect local Excel in the desktop/local version, not Vercel')
                    if cfg and ac['demo']:raise ValueError('Use a real workspace to avoid exporting sample data')
                    if cfg:
                        for other in c.execute('SELECT connection FROM accounts WHERE id<>?',(a,)):
                            oc=load(other['connection'])
                            if oc and all(oc.get(k)==cfg.get(k) for k in ('type','path','tab')):raise ValueError('This spreadsheet is already connected to another workspace')
                    if any(old.get(k)!=cfg.get(k) for k in ('type','path','tab')):c.execute('DELETE FROM baselines WHERE account=?',(a,))
                    c.execute('UPDATE accounts SET connection=?,sync_status=? WHERE id=?',(j(cfg),'Ready to sync' if cfg else 'Not connected',a));queue_sync(a);result={}
                elif path=='/api/seen':c.execute('UPDATE events SET seen=1 WHERE account=?',(a,));result={}
                elif path=='/api/competitor':
                    pid=data['product'];get_product(c,a,pid);v=data['entry'];price=float(dec(v.get('price'),'price'));ship=float(dec(v.get('shipping'),'shipping'));url=str(v.get('url','')).strip()
                    if not re.match(r'^https?://[^\s]+$',url,re.I):raise ValueError('Enter a valid competitor URL')
                    c.execute('INSERT INTO competitors VALUES(?,?,?,?)',(uid(),a,pid,j({'url':url,'price':price,'shipping':ship,'total':round(price+ship,2),'recorded':now()})));result={}
                elif path=='/api/competitor/delete':c.execute('DELETE FROM competitors WHERE account=? AND id=?',(a,data['id']));result={}
                elif path=='/api/import':
                    reader=csv.DictReader(io.StringIO(data['csv'].lstrip('\ufeff')));count=0;errors=[];mapping={col['heading']:col['source'] for col in ac['columns']};mapping.update(data.get('mapping',{}))
                    for i,row in enumerate(reader,2):
                        d={mapping.get(k,k):v for k,v in row.items() if k and v not in ('',None)};d['custom']={k:v for k,v in d.items() if k.startswith('custom_')};d['status']=d.get('status','Draft')
                        try:save_product(c,a,d,quiet=True);count+=1
                        except ValueError as e:errors.append(f'Row {i}: {e}')
                    event(c,a,'info','CSV import complete',f'{count} imported · {len(errors)} rejected');result={'count':count,'errors':errors}
                elif path=='/api/backup':
                    if CLOUD or DATABASE_URL:raise ValueError('Use the database provider backup tools or export CSV')
                    path2=DATA/f'backup-{time.strftime("%Y%m%d-%H%M%S")}.sqlite3'
                    with sqlite3.connect(path2) as dest:c.backup(dest)
                    result={'path':str(path2)}
                else:return self.send_data(404,{'error':'Unknown endpoint'})
            return self.send_data(200,result)
        except (ValueError,KeyError,TypeError,sqlite3.IntegrityError,FileNotFoundError,PermissionError) as e:return self.send_data(400,{'error':str(e)})
        except (BrokenPipeError,ConnectionResetError):return
        except Exception as e:print(traceback.format_exc(),flush=True);return self.send_data(500,{'error':'Server error. Check deployment logs.' if CLOUD else str(e)[:500]})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--open',action='store_true');args=parser.parse_args();init();server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);threading.Thread(target=worker,daemon=True).start();url=f'http://127.0.0.1:{args.port}';print(f'DropPilot running at {url} — local demo only. Ctrl+C to stop.',flush=True)
    if args.open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:STOP.set();server.server_close()
