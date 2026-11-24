"""Small PostgreSQL compatibility layer for the existing SQL repository."""
import os, re
class PG:
    def __init__(self,url):
        import psycopg
        from psycopg.rows import dict_row
        self.conn=psycopg.connect(url,row_factory=dict_row,connect_timeout=10,prepare_threshold=None)
    def execute(self,sql,params=()):
        sql=sql.replace("json_extract(body,'$.asin')","(body::jsonb ->> 'asin')").replace('ORDER BY rowid','ORDER BY demo DESC,id').replace('created DESC,rowid DESC','created DESC,id DESC')
        if 'INSERT OR REPLACE INTO baselines' in sql:
            sql=sql.replace('INSERT OR REPLACE','INSERT')+' ON CONFLICT(account,product,col) DO UPDATE SET value=EXCLUDED.value'
        return self.conn.execute(sql.replace('?','%s'),params)
    def executescript(self,script):
        for stmt in script.split(';'):
            if stmt.strip() and not stmt.strip().startswith('PRAGMA'):self.execute(stmt)
    def commit(self):self.conn.commit()
    def rollback(self):self.conn.rollback()
    def close(self):self.conn.close()
