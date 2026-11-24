"""Spreadsheet adapters: explicit paths, selected Google tabs, no marketplace scraping."""
import os, tempfile, pathlib, re, time, json

ID_HEADER='_DropPilot_ID'

def xls_safe(cell,value):
    cell.value=value
    if isinstance(value,str) and value.startswith('='): cell.data_type='s'

class Excel:
    def __init__(self,cfg):
        try: import openpyxl
        except ImportError: raise ValueError('Install Excel support: python -m pip install -r requirements.txt')
        self.x=openpyxl; self.path=pathlib.Path(cfg['path']).expanduser().resolve(); self.tab=cfg.get('tab') or 'Products'
        if self.path.suffix.lower()!='.xlsx':raise ValueError('Use an .xlsx file (not .xls or .xlsm)')
        self.stamp=self.path.stat().st_mtime_ns if self.path.exists() else None
        if self.path.exists():
            self.book=self.x.load_workbook(self.path); self.cached=self.x.load_workbook(self.path,data_only=True)
        else:
            if not self.path.parent.is_dir():raise ValueError('Excel folder does not exist')
            self.book=self.x.Workbook(); self.book.active.title=self.tab; self.cached=None
        if self.tab not in self.book.sheetnames:self.book.create_sheet(self.tab)
        self.ws=self.book[self.tab]; self.changed=False
    def read(self):
        vals=[]; formulas=set()
        for row in self.ws.iter_rows():
            line=[]
            for cell in row:
                v=cell.value
                if cell.data_type=='f':
                    formulas.add((cell.row,cell.column)); v=self.cached[self.tab].cell(cell.row,cell.column).value if self.cached and self.tab in self.cached.sheetnames else None
                if hasattr(v,'isoformat'):v=v.isoformat()
                line.append(v)
            vals.append(line)
        return vals,formulas
    def write(self, edits):
        for r,c,v in edits:
            cell=self.ws.cell(r,c)
            if cell.data_type=='f':continue
            xls_safe(cell,v);self.changed=True
        if self.changed:
            # Do not overwrite a file changed since it was read. Atomic replacement.
            actual=self.path.stat().st_mtime_ns if self.path.exists() else None
            if actual!=self.stamp:raise ValueError('Excel changed during sync; retry after saving/closing Excel')
            fd,tmp=tempfile.mkstemp(suffix='.xlsx',dir=self.path.parent);os.close(fd)
            try:
                self.book.save(tmp)
                actual=self.path.stat().st_mtime_ns if self.path.exists() else None
                if actual!=self.stamp:raise ValueError('Excel changed during save; retry')
                os.replace(tmp,self.path)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)

class Google:
    def __init__(self,cfg):
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import AuthorizedSession
        except ImportError:raise ValueError('Install Google support: python -m pip install -r requirements.txt')
        raw=cfg['path'].strip(); m=re.search(r'/spreadsheets/d/([\w-]+)',raw); self.sid=m[1] if m else raw
        if not re.fullmatch(r'[\w-]+',self.sid):raise ValueError('Invalid Google spreadsheet ID')
        self.tab=cfg.get('tab') or 'Products'; self.tabq="'"+self.tab.replace("'","''")+"'"
        scopes=['https://www.googleapis.com/auth/spreadsheets']; info=os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        cred=service_account.Credentials.from_service_account_info(json.loads(info),scopes=scopes) if info else service_account.Credentials.from_service_account_file(os.environ.get('DROPPILOT_GOOGLE_KEY','google-key.json'),scopes=scopes)
        self.session=AuthorizedSession(cred); self.base='https://sheets.googleapis.com/v4/spreadsheets/'+self.sid
        meta=self.call('GET',self.base,params={'fields':'sheets(properties(sheetId,title,gridProperties)' + ')'})
        prop=next((s['properties'] for s in meta.get('sheets',[]) if s['properties']['title']==self.tab),None)
        if prop is None:raise ValueError('Google tab not found; create it first in the spreadsheet')
        self.sheet_id=prop['sheetId']; self.grid=prop['gridProperties']; self.snapshot=None
    def call(self,method,url,**kwargs):
        r=self.session.request(method,url,timeout=25,**kwargs)
        if not r.ok:raise ValueError(f'Google Sheets HTTP {r.status_code}: {r.text[:350]}')
        return r.json()
    def read(self):
        from urllib.parse import quote
        url=self.base+'/values/'+quote(self.tabq,safe='')
        val=self.call('GET',url,params={'valueRenderOption':'UNFORMATTED_VALUE'}).get('values',[])
        f=self.call('GET',url,params={'valueRenderOption':'FORMULA'}).get('values',[])
        formulas={(i+1,j+1) for i,row in enumerate(f) for j,v in enumerate(row) if isinstance(v,str) and v.startswith('=')}
        if self.snapshot is None:self.snapshot=(val,formulas)
        return val,formulas
    def write(self,edits):
        if not edits:return
        if self.read()!=self.snapshot:raise ValueError('Google Sheet changed during sync; retry to avoid overwriting changes')
        rows=max(r for r,c,v in edits); cols=max(c for r,c,v in edits); req=[]
        for dim,need,have in [('ROWS',rows,self.grid['rowCount']),('COLUMNS',cols,self.grid['columnCount'])]:
            if need>have:req.append({'appendDimension':{'sheetId':self.sheet_id,'dimension':dim,'length':need-have}})
        if req:self.call('POST',self.base+':batchUpdate',json={'requests':req})
        def letters(c):
            s=''
            while c:c,r=divmod(c-1,26);s=chr(65+r)+s
            return s
        # combine adjacent edits within a row, reducing request payload
        runs=[]
        for r,c,v in sorted(edits,key=lambda x:(x[0],x[1])):
            if runs and runs[-1][0]==r and runs[-1][1]+len(runs[-1][2])==c:runs[-1][2].append('' if v is None else v)
            else:runs.append([r,c,['' if v is None else v]])
        data=[{'range':f'{self.tabq}!{letters(c)}{r}:{letters(c+len(v)-1)}{r}','values':[v]} for r,c,v in runs]
        # Single batch avoids partial commits for normal personal-use sheets.
        self.call('POST',self.base+'/values:batchUpdate',json={'valueInputOption':'RAW','data':data})
