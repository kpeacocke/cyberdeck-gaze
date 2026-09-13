import unittest
from gaze.core import Attention
C=dict(lost_seconds=2,dwell_seconds=12,cooldown_seconds=20,preferred_classes=['person'],minimum_dwell_seconds=4,switch_margin=2.5)
class InterestTests(unittest.TestCase):
    def test_camera_shift_preserves_track(self):
        a=Attention(C);ident=a.update([('person',.9,(300,100,80,120))],0).id
        t=a.update([('person',.9,(80,100,80,120))],.1,camera_shift=(-220,0),camera_moving=True)
        self.assertEqual(t.id,ident);self.assertFalse(t.moving)
    def test_camera_motion_does_not_score_activity(self):
        a=Attention(C)
        for i in range(6):t=a.update([('person',.9,(100+i*20,100,80,120))],i*.1,camera_moving=True)
        self.assertFalse(t.moving);self.assertNotIn('moving',t.reasons)
    def test_real_motion_in_settled_view_scores(self):
        a=Attention(C)
        for i in range(6):t=a.update([('person',.9,(100+i*12,100,80,120))],i*.1)
        self.assertTrue(t.moving);self.assertIn('moving',t.reasons)
    def test_occluded_target_returns_same_id(self):
        a=Attention(C);ident=a.update([('dog',.9,(100,100,80,120))],0,viewpoint=(95,92)).id
        self.assertIsNone(a.update([],1));self.assertEqual(a.search_position,(95,92))
        self.assertEqual(a.update([('dog',.9,(110,100,80,120))],1.2).id,ident)
        self.assertIn('reacquired',[e['event'] for e in a.events])
    def test_memory_expires(self):
        a=Attention(dict(C,scene_memory_seconds=4));a.update([('dog',.9,(10,10,80,80))],0)
        a.update([],3);self.assertEqual(a.memory[0]['label'],'dog')
        a.update([],5);self.assertEqual(a.memory,[])
    def test_minimum_dwell_prevents_twitch(self):
        a=Attention(C);ident=a.update([('chair',.6,(10,10,80,80))],0).id
        t=a.update([('chair',.6,(10,10,80,80)),('person',.99,(500,10,80,80))],1)
        self.assertEqual(t.id,ident)
    def test_assignment_is_one_to_one(self):
        a=Attention(C);a.update([('person',.9,(10,10,80,80)),('person',.9,(200,10,80,80))],0)
        a.update([('person',.9,(180,10,80,80)),('person',.9,(30,10,80,80))],.1)
        self.assertEqual(a.tracks[1].box[0],30);self.assertEqual(a.tracks[2].box[0],180)
