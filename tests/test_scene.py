import tempfile,unittest
from gaze.scene import SceneObserver

class SceneTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.scene=SceneObserver(self.tmp.name,dict(scene_confirm_seconds=2,scene_min_samples=3,unknown_retention_hours=1))
        self.person=[('person',.9,(0,0,100,100))]
    def tearDown(self):self.tmp.cleanup()
    def confirm(self,detections,start=0,name='Door',position=(90,90)):
        events=[]
        for i in range(3):events+=self.scene.observe(name,position,detections,start+i,True)
        return events
    def test_persistent_change_and_no_repeat(self):
        self.confirm(self.person)
        events=self.confirm([],3)
        self.assertEqual(len(events),1);self.assertIn('1 → 0',events[0]['event'])
        self.assertEqual(self.confirm([],6),[])
    def test_brief_missing_detection_does_not_change_baseline(self):
        self.confirm(self.person)
        self.scene.observe('Door',(90,90),[],3,True)
        self.confirm(self.person,4)
        self.assertEqual(self.scene.baselines['Door']['counts'],{'person':1})
    def test_camera_movement_cannot_form_baseline(self):
        for i in range(10):self.scene.observe('Door',(90,90),self.person,i,False)
        self.assertEqual(self.scene.baselines,{})
    def test_distinct_viewpoints_never_compared(self):
        self.confirm(self.person)
        events=self.confirm([],3,'Desk',(95,90))
        self.assertIn('baseline recorded',events[0]['event'])
    def test_new_angle_resets_same_name_baseline(self):
        self.confirm(self.person)
        events=self.confirm([],3,position=(95,90))
        self.assertIn('baseline recorded',events[0]['event'])
    def test_expiry_and_explicit_reset(self):
        self.confirm(self.person)
        self.scene.observe(None,None,[],4000,False)
        self.assertFalse(self.scene.baselines)
        self.confirm(self.person,4001)
        self.scene.reset('Door');self.assertFalse(self.scene.baselines)
    def test_baseline_persists(self):
        self.confirm(self.person)
        restored=SceneObserver(self.tmp.name,{})
        self.assertEqual(restored.baselines['Door']['counts'],{'person':1})
