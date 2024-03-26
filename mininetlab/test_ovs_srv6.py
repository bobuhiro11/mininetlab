import unittest
from mininetlab.ovs_srv6 import run


class TestRun(unittest.TestCase):
    def test_run(self):
        loss_rate = run()
        self.assertEqual(0.0, loss_rate)


if __name__ == '__main__':
    unittest.main()
