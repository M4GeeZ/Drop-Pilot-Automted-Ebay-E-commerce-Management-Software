"""Password verification and database-backed, revocable tab sessions."""
import os, hashlib, hmac, secrets, time
ROUNDS=600000
SESSION_SECONDS=8*3600

def make_hash(password):
    salt=secrets.token_hex(16)
    return f'pbkdf2_sha256${ROUNDS}${salt}$'+hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ROUNDS).hex()
def verify(password,encoded):
    try:
        name,rounds,salt,digest=encoded.split('$'); rounds=int(rounds)
        if name!='pbkdf2_sha256' or not 600000<=rounds<=2000000:return False
        return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),rounds).hex(),digest)
    except (ValueError,TypeError):return False

def digest(token):return hashlib.sha256(token.encode()).hexdigest()
def configured():return bool(os.environ.get('DROPPILOT_EMAIL') and os.environ.get('DROPPILOT_PASSWORD_HASH'))
def login(c,email,password):
    now=int(time.time()); row=c.execute('SELECT attempts,until_time FROM login_limit WHERE id=?',('admin',)).fetchone()
    if row and row['attempts']>=5 and row['until_time']>now:return 429,None
    attempts=row['attempts'] if row and row['until_time']>now else 0
    ok=verify(password[:1024],os.environ.get('DROPPILOT_PASSWORD_HASH',''))
    ok=hmac.compare_digest(email.strip().lower().encode(),os.environ.get('DROPPILOT_EMAIL','').strip().lower().encode()) and ok
    if not ok:
        c.execute('DELETE FROM login_limit WHERE id=?',('admin',));c.execute('INSERT INTO login_limit VALUES(?,?,?)',('admin',attempts+1,now+300));return 401,None
    c.execute('DELETE FROM login_limit WHERE id=?',('admin',));c.execute('DELETE FROM sessions WHERE expires<=?',(now,));token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?)',(digest(token),now+SESSION_SECONDS));return 200,token

def authorized(c,token):
    if not token or len(token)>128:return False
    return bool(c.execute('SELECT 1 FROM sessions WHERE token_hash=? AND expires>?',(digest(token),int(time.time()))).fetchone())
