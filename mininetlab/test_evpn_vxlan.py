import os
import unittest
from mininetlab.evpn_vxlan import run


class TestRun(unittest.TestCase):
    def test_run(self):
        if os.environ.get('CI') is not None:
            self.skipTest("VRF may not work on CI such as Github workflows")
        loss_rate = run()
        self.assertEqual(0.0, loss_rate)
