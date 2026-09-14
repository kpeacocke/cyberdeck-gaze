import json,unittest
from pathlib import Path
from unittest.mock import patch
from gaze.hardware import Motor
from gaze.core import Attention
class FollowLoopTests(unittest.TestCase):
    def test_static_subject_converges_inside_deadband(self):
        c=json.loads((Path(__file__).parents[1]/'config.json').read_text())
        c['motor']['enabled']=False
        with patch('gaze.hardware.time.monotonic',return_value=0):motor=Motor(c['motor'])
        for i in range(1,120):
            x=480+(94-motor.pan)*20
            y=360-(97-motor.tilt)*20
            with patch('gaze.hardware.time.monotonic',return_value=i*.05):motor.follow((x-25,y-25,50,50))
        self.assertLess(abs(motor.pan-94),2.5)
        self.assertLess(abs(motor.tilt-97),1.9)
    def test_crossing_tracks_use_velocity(self):
        c=dict(lost_seconds=2,dwell_seconds=12,cooldown_seconds=20,preferred_classes=['person'])
        a=Attention(c)
        for i in range(7):
            a.update([('person',.9,(20+i*20,100,30,60)),('person',.9,(240-i*20,100,30,60))],i*.1)
        self.assertGreater(a.tracks[1].box[0],a.tracks[2].box[0])
