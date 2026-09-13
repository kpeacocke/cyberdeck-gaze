import json, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from gaze.hardware import Motor

class MotorTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((Path(__file__).parents[1]/'config.json').read_text())['motor']
        self.config['enabled']=False
        self.motor=Motor(self.config)
    def test_disabled_does_not_open_bus(self):
        self.assertIsNone(self.motor.bus)
    def test_speed_and_bounds(self):
        with patch('gaze.hardware.time.monotonic',return_value=self.motor.last+1):
            self.motor.move(999,-999)
        self.assertLessEqual(self.motor.pan,91.2)
        self.assertGreaterEqual(self.motor.tilt,88.8)
    def test_centred_subject_does_not_move(self):
        self.motor.follow((430,310,100,100))
        self.assertEqual((self.motor.pan,self.motor.tilt),(90,90))
    def test_close_releases_bus_even_on_write_failure(self):
        bus=Mock();bus.write_byte_data.side_effect=OSError('Disconnected')
        self.motor.bus=bus
        with self.assertRaises(OSError):self.motor.close()
        bus.close.assert_called_once()
        self.assertIsNone(self.motor.bus)

    def test_target_right_turns_right(self):
        self.motor.move=Mock()
        self.motor.follow((700,310,100,100))
        self.assertGreater(self.motor.move.call_args.args[0],90)
    def test_target_above_tilts_up(self):
        self.motor.move=Mock()
        self.motor.follow((430,0,100,100))
        self.assertGreater(self.motor.move.call_args.args[1],90)
    def test_target_below_tilts_down(self):
        self.motor.move=Mock()
        self.motor.follow((430,600,100,100))
        self.assertLess(self.motor.move.call_args.args[1],90)
