import unittest
from mininetlab.ipt_masquerade import run


class TestRun(unittest.TestCase):
    def test_run(self):
        loss_rate = run()
        self.assertEqual(0.0, loss_rate)
