import unittest
try:
    import cv2
    import numpy as np
except ImportError:
    cv2=None
from gaze.motion import BackgroundMotion

@unittest.skipIf(cv2 is None,'OpenCV is required for optical-flow tests')
class MotionTests(unittest.TestCase):
    def test_background_translation(self):
        rng=np.random.default_rng(4)
        frame=np.zeros((720,960,3),np.uint8)
        for x,y in rng.integers([20,20],[940,700],size=(150,2)):
            cv2.circle(frame,(int(x),int(y)),4,(255,255,255),-1)
        shifted=cv2.warpAffine(frame,np.float32([[1,0,12],[0,1,-8]]),(960,720))
        m=BackgroundMotion();m.update(frame,[])
        delta,reliable=m.update(shifted,[])
        self.assertTrue(reliable)
        self.assertAlmostEqual(delta[0],12,delta=1)
        self.assertAlmostEqual(delta[1],-8,delta=1)
    def test_textureless_view_is_not_reliable(self):
        frame=np.zeros((720,960,3),np.uint8)
        m=BackgroundMotion();m.update(frame,[])
        self.assertFalse(m.update(frame,[])[1])
