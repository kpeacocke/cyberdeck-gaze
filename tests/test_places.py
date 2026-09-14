import tempfile,unittest
from gaze.places import Places,validate_limits
class PlacesTests(unittest.TestCase):
    def test_persistence_and_bounds(self):
        with tempfile.TemporaryDirectory() as root:
            p=Places(root);p.save('Door',(95,90))
            p=Places(root);self.assertEqual(p.items['Door'],[95,90])
            self.assertEqual(p.valid(dict(pan_min=80,pan_max=92,tilt_min=80,tilt_max=100)),{})
            p.forget('Door');self.assertEqual(Places(root).items,{})
    def test_limits_require_centre_and_valid_signs(self):
        c=dict(pan_min=80,pan_max=100,tilt_min=80,tilt_max=100,pan_sign=1,tilt_sign=-1,speed_deg_s=12)
        validate_limits(c)
        with self.assertRaises(ValueError):validate_limits(dict(c,pan_min=95))
        with self.assertRaises(ValueError):validate_limits(dict(c,tilt_sign=0))
        with self.assertRaises(ValueError):validate_limits(dict(c,speed_deg_s=100))
