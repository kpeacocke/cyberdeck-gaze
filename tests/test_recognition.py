import unittest
from gaze.recognition import choose_match
class MatchPolicyTests(unittest.TestCase):
    def test_unknown_below_threshold(self):
        self.assertIsNone(choose_match([('A',.45)],.5,.08)[0])
    def test_ambiguous_people_abstain(self):
        self.assertIsNone(choose_match([('A',.7),('B',.68)],.5,.08)[0])
    def test_multiple_examples_not_competitors(self):
        self.assertEqual(choose_match([('A',.75),('A',.72),('B',.5)],.5,.08)[0],'A')
    def test_no_enrolments_stays_unknown(self):
        self.assertEqual(choose_match([],.5,.08),(None,0.))
