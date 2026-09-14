import unittest
from unittest.mock import Mock
from gaze.app import App
class RecoveryTests(unittest.TestCase):
    def test_camera_loop_retries_failure_without_recreating_ui(self):
        app=App.__new__(App)
        app.stop=Mock()
        app.stop.is_set.side_effect=[False,False,False,False,True]
        app.capture_once=Mock(side_effect=[RuntimeError('temporary camera failure'),None])
        app.capture()
        self.assertEqual(app.capture_once.call_count,2)
        self.assertEqual(app.stop.wait.call_count,2)
        self.assertIn('temporary camera failure',app.motor_state)
