import unittest
from mininetlab.xdp_mirror import run
from retry import retry


class TestRun(unittest.TestCase):
    @retry(tries=5, delay=1)
    def test_run(self):
        loss_rate = run()
        self.assertEqual(0.0, loss_rate)


if __name__ == '__main__':
    unittest.main()
