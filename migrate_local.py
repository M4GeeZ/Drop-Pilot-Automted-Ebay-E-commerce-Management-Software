"""Copy an existing SQLite workspace to a fresh PostgreSQL target; no login tokens copied."""
import sqlite3, sys, pathlib, os, json
if len(sys.argv)!=2 or not os.environ.get('DATABASE_URL'):raise SystemExit('Usage: set DATABASE_URL and run python migrate_local.py <old.sqlite3>')
source=pathlib.Path(sys.argv[1]).resolve()
if not source.is_file():raise SystemExit('SQLite source not found')
import server
server.init()
tables=['accounts','products','baselines','events','history','competitors']
with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as old, server.db() as new:
    old.row_factory=sqlite3.Row
    if new.execute('SELECT 1 FROM accounts WHERE demo=0').fetchone():raise SystemExit('Refusing to overwrite existing real cloud workspaces.')
    if input('Replace seeded cloud demo data with your local data? Type MIGRATE: ')!='MIGRATE':raise SystemExit('Cancelled')
    for t in reversed(tables):new.execute('DELETE FROM '+t)
    new.execute('DELETE FROM sessions');new.execute('DELETE FROM login_limit')
    disconnected=set()
    for t in tables:
        for row in old.execute('SELECT * FROM '+t):
            d=dict(row)
            if t=='accounts' and json.loads(d['connection']).get('type')=='excel':
                disconnected.add(d['id']);d.update(connection='{}',last_sync=None,sync_status='Not connected')
            if t=='baselines' and d['account'] in disconnected:continue
            new.execute('INSERT INTO '+t+' ('+','.join(d)+') VALUES ('+','.join('?' for _ in d)+')',tuple(d.values()))
print('Migration complete. Local Excel connections were disconnected.')
