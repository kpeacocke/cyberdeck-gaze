"""Run on the Pi when its optional recognition models are installed."""
import tempfile,unittest
from pathlib import Path
from gaze.recognition import Recognizer
MODELS=Path('/mnt/nvme/models/cyberdeck-gaze')
@unittest.skipUnless((MODELS/'sface.onnx').exists(),'Optional Pi recognition models absent')
class RecognitionModelTests(unittest.TestCase):
    def test_blank_image_not_enrolled(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as root:
            r=Recognizer(root,{})
            with self.assertRaises(ValueError):r.enrol('friend','person',np.zeros((320,320,3),np.uint8))
            self.assertEqual(r.gallery,[])
    def test_pet_reference_persists_and_forgets(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as root:
            # Synthetic texture tests reference persistence, not animal identity accuracy.
            image=np.random.default_rng(3).integers(0,255,(256,256,3),dtype=np.uint8)
            r=Recognizer(root,{})
            r.enrol('test pet','dog',image)
            r=Recognizer(root,{})
            result=r.match('dog',image)
            self.assertEqual(result['name'],'test pet');self.assertTrue(result['possible'])
            r.forget('test pet');self.assertIsNone(r.match('dog',image)['name'])
