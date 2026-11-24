"""DropPilot business logic; no network access at import time."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_CEILING
import re, uuid, json, datetime, math

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
def uid(): return uuid.uuid4().hex

def money(n): return float(n.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
def dec(n, name='number'):
    try:
        d=Decimal(str(n if n not in ('',None) else 0).replace(',',''))
        if not d.is_finite() or d<0 or d>Decimal('1000000000'): raise ValueError()
        return d
    except (InvalidOperation, ValueError): raise ValueError(f'Invalid {name}: enter a non-negative number')

def title_optimize(s):
    s=re.sub(r'\b(free shipping|best seller|limited time|hot sale)\b',' ',str(s),flags=re.I)
    s=re.sub(r'\s+',' ',s).strip(' ,-|')
    out=[]
    for w in s.split():
        if out and out[-1].casefold()==w.casefold(): continue
        if len(' '.join(out+[w]))>80: break
        out.append(w)
    return ' '.join(out) if out else s[:80]

FIELDS={
 'amazon_url':'Amazon Link','source_price':'Amazon Price','shipping':'Source Shipping','tax':'Source Tax',
 'ebay_url':'eBay Competitor Link','competitor_price':'Competitor Total Price','selling_price':'Selling Price',
 'fee_pct':'Fee %','fixed_fee':'Fixed Fee','ad_pct':'Ad Fee %','other_cost':'Other Costs',
 'fees':'Estimated Fees','total_cost':'Source Total','profit':'Estimated Profit ($)','margin':'Margin (%)','roi':'ROI (%)',
 'title':'Product Title','seo_title':'SEO Title','keyword':'Keyword','asin':'ASIN','image_url':'Image URL',
 'stock':'Stock Status','status':'Workflow Status','sold':'Total Sold','sold7':'Sold 7 Days','sold14':'Sold 14 Days','sold30':'Sold 30 Days',
 'notes':'Notes','category':'Category','last_checked':'Last Checked','updated_at':'Last Updated','break_even':'Break-even Price',
 'target_price':'Target Profit Price','health':'Health Score','source_seller':'Source Seller','delivery':'Delivery Estimate'}
NUM={'source_price','shipping','tax','competitor_price','selling_price','fee_pct','fixed_fee','ad_pct','other_cost','sold','sold7','sold14','sold30'}
DERIVED={'fees','total_cost','profit','margin','roi','break_even','target_price','health','updated_at'}
DEFAULT_COLS=['amazon_url','source_price','shipping','ebay_url','selling_price','profit','margin','roi','fees','seo_title','keyword','stock','sold7','sold14','sold30']
DEFAULT_SETTINGS={'fee_pct':13.6,'fixed_fee':.4,'ad_pct':0,'target_profit':5,'undercut':.02,'min_roi':20,'zip':'','interval':60,'marketplace':'US','theme':'light'}

def calc(p, settings):
    c=sum(dec(p.get(k),k) for k in ['source_price','shipping','tax','other_cost'])
    s=dec(p.get('selling_price'),'selling price'); r=(dec(p.get('fee_pct'),'fee')+dec(p.get('ad_pct'),'ad fee'))/100; fixed=dec(p.get('fixed_fee'),'fixed fee')
    if r>=1: raise ValueError('Combined percentage fees must be below 100%')
    f=(s*r+fixed).quantize(Decimal('.01'),rounding=ROUND_HALF_UP); profit=s-c-f
    score=0 if p.get('stock')=='Out of stock' else min(100,max(0,round((float(profit/c*100) if c else 0)*1.2+ (35 if p.get('stock')=='In stock' else 10))))
    ceil=lambda d:float(d.quantize(Decimal('.01'),rounding=ROUND_CEILING))
    return dict(total_cost=money(c),fees=money(f),profit=money(profit),margin=money(profit/s*100) if s else None,roi=money(profit/c*100) if c else None,break_even=ceil((c+fixed)/(1-r)),target_price=ceil((c+fixed+dec(settings.get('target_profit')))/(1-r)),health=score)

def normalize(data, settings, old=None, custom_fields=()):
    p=dict(old or {}); p.update({k:v for k,v in data.items() if k in FIELDS and k not in DERIVED})
    for k in NUM:
        if k in ('fee_pct','fixed_fee','ad_pct') and k not in p: p[k]=settings[k]
        elif k.startswith('sold') and p.get(k) in ('',None): p[k]=None; continue
        else: p[k]=float(dec(p.get(k),k))
        if k.startswith('sold') and p[k] is not None:
            if p[k]%1: raise ValueError('Sold counts must be whole numbers')
            p[k]=int(p[k])
    for k in FIELDS.keys()-NUM-DERIVED:
        if k in p: p[k]=str(p[k] or '').strip()[:5000]
    p['title']=p.get('title','') or p.get('seo_title','') or p.get('asin','') or 'Untitled product'
    if not p.get('seo_title') or data.get('optimize'): p['seo_title']=title_optimize(p['title'])
    if len(p['seo_title'])>80: raise ValueError('SEO title must be at most 80 characters')
    for k in ('amazon_url','ebay_url','image_url'):
        if p.get(k) and not re.match(r'^https?://[^\s]+$',p[k],re.I): raise ValueError(f'{FIELDS[k]} must be an HTTP(S) URL')
    if not p.get('asin'):
        m=re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?#]|$)',p.get('amazon_url',''),re.I)
        if m:p['asin']=m[1].upper()
    p['stock']=p.get('stock') or 'Unknown'; p['status']=p.get('status') or 'Draft'
    if p['stock'] not in ('In stock','Out of stock','Unknown'): raise ValueError('Invalid stock status')
    if p['status'] not in ('Draft','Published','Archived'): raise ValueError('Invalid workflow status')
    custom=dict(p.get('custom') or {}); incoming=data.get('custom') or {}
    for f in custom_fields:
        k=f['key']
        if k in incoming:
            v=incoming[k]
            if f.get('type')=='number' and v not in ('',None): v=float(dec(v,f['heading']))
            elif v is not None:
                v=str(v)[:5000]
                if f.get('type')=='url' and v and not re.match(r'^https?://[^\s]+$',v,re.I):raise ValueError(f"{f['heading']} must be an HTTP(S) URL")
            custom[k]=v
    p['custom']=custom
    p.update(calc(p,settings)); p['updated_at']=now(); return p

def column_value(p,col):
    k=col['source']; return p.get('custom',{}).get(k) if k.startswith('custom_') else p.get(k)

def comparable(v):
    if v is None or v=='': return ''
    if isinstance(v,bool): return str(v).lower()
    try:
        d=Decimal(str(v)); return str(d.normalize()) if d.is_finite() else str(v)
    except InvalidOperation:return str(v).strip()

def same(a,b):return comparable(a)==comparable(b)

def columns_default():return [dict(id=uid(),heading=FIELDS[k],source=k) for k in DEFAULT_COLS]
