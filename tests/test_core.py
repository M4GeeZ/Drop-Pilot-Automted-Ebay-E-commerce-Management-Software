import os,tempfile,unittest,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
TMP=tempfile.TemporaryDirectory();os.environ['DROPPILOT_DATA']=TMP.name
import server as s
from engine import normalize, DEFAULT_SETTINGS, title_optimize, uid

class Core(unittest.TestCase):
    @classmethod
    def setUpClass(cls):s.init()
    def setUp(self):
        with s.db() as c:self.a=s.create_account(c,'test '+uid())
    def test_math(self):
        p=normalize({'title':'Test','source_price':19.99,'tax':1.2,'selling_price':34.97,'fee_pct':13.6,'fixed_fee':.4},DEFAULT_SETTINGS)
        self.assertEqual(p['fees'],5.16);self.assertEqual(p['profit'],8.62);self.assertEqual(p['roi'],40.68)
    def test_title(self):
        self.assertLessEqual(len(title_optimize('Product ' * 100)),80)
    def test_isolation(self):
        with s.db() as c:
            p=s.save_product(c,self.a,{'title':'One'});other=s.create_account(c,'other')
            self.assertEqual(s.all_products(c,other),[])
            with self.assertRaises(ValueError):s.get_product(c,other,p)
    def test_duplicate(self):
        with s.db() as c:
            s.save_product(c,self.a,{'title':'One','amazon_url':'https://amazon.com/dp/B012345678'})
            with self.assertRaises(ValueError):s.save_product(c,self.a,{'title':'Two','amazon_url':'https://amazon.com/dp/B012345678'})
    def test_excel_sync(self):
        import openpyxl
        file=pathlib.Path(TMP.name)/(self.a+'.xlsx')
        with s.db() as c:
            p=s.save_product(c,self.a,{'title':'One','seo_title':'One','source_price':10,'selling_price':25,'status':'Published','stock':'In stock'})
            c.execute('UPDATE accounts SET connection=? WHERE id=?',(s.j({'type':'excel','path':str(file),'tab':'Products','auto':False}),self.a))
        s.sync(self.a)
        w=openpyxl.load_workbook(file);ws=w['Products'];headers={x.value:x.column for x in ws[1]};self.assertEqual(ws.cell(2,headers['Amazon Price']).value,10)
        ws.cell(2,headers['Amazon Price'],12);w.save(file);w.close();s.sync(self.a)
        with s.db() as c:
            self.assertEqual(s.get_product(c,self.a,p)['source_price'],12)
            s.save_product(c,self.a,{'selling_price':30,'source_seller':'Acme'},p)
            ac=s.account(c,self.a);cols=ac['columns']+[{'id':uid(),'heading':'Supplier','source':'source_seller'}];c.execute('UPDATE accounts SET columns_json=? WHERE id=?',(s.j(cols),self.a))
        s.sync(self.a);w=openpyxl.load_workbook(file);ws=w['Products'];headers={x.value:x.column for x in ws[1]};self.assertEqual(ws.cell(2,headers['Selling Price']).value,30);self.assertEqual(ws.cell(2,headers['Supplier']).value,'Acme')
        ws.cell(2,headers['Amazon Price'],14);w.save(file);w.close()
        with s.db() as c:s.save_product(c,self.a,{'source_price':15},p)
        r=s.sync(self.a);self.assertTrue(r['conflicts']);w=openpyxl.load_workbook(file);self.assertEqual(w['Products'].cell(2,headers['Amazon Price']).value,14);w.close()
    def test_formula_preserved(self):
        import openpyxl
        file=pathlib.Path(TMP.name)/(self.a+'.xlsx');w=openpyxl.Workbook();ws=w.active;ws.title='Products';ws.append(['Amazon Price','Selling Price','Estimated Profit ($)','SEO Title']);ws.append([10,25,'=B2-A2','Existing item']);w.save(file);w.close()
        with s.db() as c:c.execute('UPDATE accounts SET connection=? WHERE id=?',(s.j({'type':'excel','path':str(file),'tab':'Products','auto':False}),self.a))
        s.sync(self.a);w=openpyxl.load_workbook(file);self.assertEqual(w['Products']['C2'].value,'=B2-A2');w.close()
        with s.db() as c:self.assertEqual(len(s.all_products(c,self.a)),1)
if __name__=='__main__':unittest.main()
