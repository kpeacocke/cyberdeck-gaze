import tempfile,time,unittest
from pathlib import Path
from gaze.storage import Store
class FakeImage:
    def thumbnail(self,size):pass
    def save(self,path,**kwargs):Path(path).write_bytes(b'fake image')
class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.s=Store(dict(storage_dir=self.tmp.name,unknown_retention_hours=1,max_storage_mb=1))
    def tearDown(self):self.s.db.close();self.tmp.cleanup()
    def test_unknown_expires_saved_survives(self):
        self.s.add('person',FakeImage());self.s.add('dog',FakeImage())
        self.s.rename(self.s.recent()[0][0],'Rex')
        self.s.db.execute('UPDATE sightings SET created=?',(time.time()-7200,));self.s.db.commit()
        self.s.prune();self.assertEqual(len(self.s.recent()),1)
        self.assertEqual(self.s.recent()[0][3],'Rex')
    def test_forget_removes_file_and_row(self):
        self.s.add('person',FakeImage());row=self.s.recent()[0]
        self.s.forget(row[0]);self.assertFalse((self.s.root/row[4]).exists());self.assertEqual(self.s.recent(),[])
    def test_budget_prunes_unknown(self):
        self.s.config['max_storage_mb']=0.000001
        self.s.add('person',FakeImage());self.assertEqual(self.s.recent(),[])
