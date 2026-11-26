from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from tests.trial_support import TrialSupport


class TestTrialConcurrency(TrialSupport):
    def test_concurrent_same_request(self):
        trial, _ = self.publish_pair()
        number = trial['edition_id']
        self.rig.press.load('A')
        start = Barrier(2)

        def make():
            start.wait(timeout=5)
            return self.trial('trial-A', number, 'A')

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(make)
            second = executor.submit(make)
            self.assertEqual(first.result(), second.result())
        self.assertEqual(self.rig.press.press_count(), 1)
        self.assertEqual([strike.press_no for strike in
                          self.rig.press.observe_paper('A').strikes], [1])
        self.assertEqual(self.release(number, 'trial-A')['receipt'],
                         self.read_trial('trial-A'))
