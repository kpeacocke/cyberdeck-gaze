import unittest
from gaze.core import Attention
C=dict(lost_seconds=2,dwell_seconds=10,cooldown_seconds=20,preferred_classes=['person'])
class AttentionTests(unittest.TestCase):
    def test_stable_follow(self):
        a=Attention(C);t=a.update([('person',.9,(10,10,100,100))],0)
        self.assertEqual(a.update([('person',.8,(20,10,100,100))],1).id,t.id)
    def test_switch_after_dwell(self):
        a=Attention(C);d=[('person',.9,(10,10,100,100)),('dog',.9,(500,10,100,100))]
        first=a.update(d,0).id
        for i in range(1,11):t=a.update(d,i)
        self.assertNotEqual(t.id,first)
    def test_manual_follow_does_not_expire(self):
        a=Attention(C);d=[('person',.9,(10,10,100,100))]
        ident=a.update(d,0).id;a.select(ident,0)
        for i in range(1,15):self.assertEqual(a.update(d,i).id,ident)
    def test_park_does_not_select(self):
        a=Attention(C);a.mode='Park';self.assertIsNone(a.update([('dog',.9,(1,1,20,20))],0))
    def test_stale_track_not_moved(self):
        a=Attention(C);a.update([('dog',.9,(1,1,20,20))],0)
        self.assertIsNone(a.update([],1))
        a.update([],3);self.assertFalse(a.tracks)
    def test_different_classes_never_merge(self):
        a=Attention(C);x=a.update([('dog',.9,(1,1,20,20))],0).id
        a.update([('cat',.9,(1,1,20,20))],.1)
        self.assertEqual(len(a.tracks),2)
if __name__=='__main__':unittest.main()
