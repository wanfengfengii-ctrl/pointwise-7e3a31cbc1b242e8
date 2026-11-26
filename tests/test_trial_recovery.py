from unittest import mock

import press.trials
from tests.support import scenario
from tests.trial_support import SAMPLE_POINTS, TrialSupport


class TestTrialRecovery(TrialSupport):
    def check_reply_loss(self, phase, expected_strikes):
        trial, _ = self.publish_pair()
        number = trial['edition_id']
        press = self.rig.press
        press.load('A')
        press.arm_reply_loss(phase)
        self.assertEqual(self.trial('trial-A', number, 'A', status=202),
                         {'request_id': 'trial-A', 'status': 'pending'})
        self.rig.restart()
        press = self.rig.press
        observed = press.observe_paper('A')
        expected_grid = tuple(tuple(point) for point in SAMPLE_POINTS)
        self.assertEqual(observed.points, expected_grid if expected_strikes else ())
        self.assertEqual(press.press_count(), expected_strikes)
        self.assertEqual(self.read_trial('trial-A', status=202),
                         {'request_id': 'trial-A', 'status': 'pending'})
        self.assertEqual(self.release(number, 'trial-A', status=202),
                         {'request_id': 'trial-A', 'status': 'pending'})
        self.rig.press.load('C')
        self.assertEqual(self.rig.print_card('early', number, 'C', status=409)['error'],
                         'edition_not_released')
        self.rig.press.load('A')
        receipt = self.trial('trial-A', number, 'A')
        self.assertEqual((receipt['paper_id'], receipt['press_no']), ('A', 1))
        self.assertEqual(press.press_count(), 1)
        self.assertEqual(self.read_trial('trial-A'), receipt)
        self.assertEqual(self.trial('trial-A', number, 'A'), receipt)
        self.assertEqual(press.press_count(), 1)
        released = self.release(number, 'trial-A')
        self.assertEqual(released['receipt'], receipt)
        self.rig.press.load('C')
        self.rig.print_card('formal-C', number, 'C')
        self.rig.restart()
        self.assertEqual(self.release(number, 'trial-A'), released)
        self.assertEqual(self.trial('trial-A', number, 'A'), receipt)
        self.assertEqual(self.rig.press.press_count(), 2)
        self.assertEqual([strike.press_no for strike in
                          self.rig.press.observe_paper('A').strikes], [1])
        piece = self.rig.report(number)['pieces'][0]
        scenario(f'trial.loss_{phase}',
                 {'request_id': 'trial-A', 'paper_id': 'A', 'phase': phase},
                 {'a_points': expected_grid if expected_strikes else [],
                  'a_strikes': expected_strikes},
                 {'a_points': list(observed.points), 'a_strikes': len(observed.strikes)},
                 {'resumed_press_no': 1, 'formal_press_no': 2},
                 {'resumed_press_no': receipt['press_no'],
                  'formal_press_no': piece['press_no']},
                 ['press/mechanics.py', 'press/trials.py', 'press/production.py',
                  'record/lookup.py', 'edition/publication.py'],
                 '从空白 A 起算，压前失答未落凸点、压后失答只落一次，续办按实际压次补首执，正确放行后才在别纸制卡。')

    def test_loss_before(self):
        self.check_reply_loss('before', 0)

    def test_loss_after(self):
        self.check_reply_loss('after', 1)

    def test_evidence_outage_then_resume(self):
        trial, _ = self.publish_pair()
        number = trial['edition_id']
        self.rig.press.load('A')
        self.rig.press.arm_reply_loss('after')
        self.trial('trial-A', number, 'A', status=202)
        press = self.rig.press
        press.set_evidence_available(False)
        self.rig.restart()
        press = self.rig.press
        press.set_evidence_available(False)
        self.assertEqual(self.read_trial('trial-A', status=202),
                         {'request_id': 'trial-A', 'status': 'pending'})
        self.assertEqual(self.trial('trial-A', number, 'A', status=202),
                         {'request_id': 'trial-A', 'status': 'pending'})
        self.assertEqual(self.rig.query('SELECT COUNT(*) FROM trial_requests'), [(1,)])
        press.set_evidence_available(True)
        receipt = self.trial('trial-A', number, 'A')
        self.assertEqual(receipt['press_no'], 1)
        self.assertEqual(press.press_count(), 1)
        self.assertEqual(self.release(number, 'trial-A')['receipt'], receipt)

    def test_other_paper_deferred_then_resumes(self):
        trial, ordinary = self.publish_pair()
        number = trial['edition_id']
        press = self.rig.press
        press.load('A')
        press.arm_reply_loss('before')
        self.trial('trial-A', number, 'A', status=202)
        # While A is mounted and unpressed, an ordinary order on B waits.
        self.assertEqual(self.rig.print_card('card-B', ordinary['edition_id'], 'B', status=202),
                         {'status': 'pending'})
        self.assertEqual(press.press_count(), 0)
        press.load('B')
        card = self.rig.print_card('card-B', ordinary['edition_id'], 'B')
        self.assertEqual(card['press_no'], 1)
        press.load('A')
        receipt = self.trial('trial-A', number, 'A')
        self.assertEqual(receipt['press_no'], 2)
        self.assertEqual(self.release(number, 'card-B', status=409)['error'],
                         'release_conflict')
        self.assertEqual(self.release(number, 'trial-A')['receipt'], receipt)
        self.assertEqual(press.press_count(), 2)

    def test_press_held_by_fixture(self):
        trial, ordinary = self.publish_pair()
        number = trial['edition_id']
        press = self.rig.press
        press.load('A')
        press.arm_reply_loss('before')
        self.trial('trial-A', number, 'A', status=202)
        press.claim('fixture-hold', 'A')
        # Deferring an ordinary new order while the trial needs the press may
        # answer 202; the existing busy refusal may also answer 503.
        status, body = self.rig.client.exchange('POST', '/impressions',
                                                 {'request_id': 'card-B',
                                                  'edition_id': ordinary['edition_id'],
                                                  'paper_id': 'B'})
        self.assertIn(status, (202, 503))
        self.assertEqual(press.press_count(), 0)
        press.release('fixture-hold')
        receipt = self.trial('trial-A', number, 'A')
        self.assertEqual(receipt['press_no'], 1)
        self.assertEqual(self.release(number, 'trial-A')['receipt'], receipt)

    def test_wrong_sheet_then_original_paper(self):
        trial, _ = self.publish_pair()
        number = trial['edition_id']
        press = self.rig.press
        press.load('A')
        press.arm_reply_loss('before')
        self.trial('trial-A', number, 'A', status=202)
        press.load('B')
        self.assertEqual(self.trial('trial-A', number, 'A', status=409)['error'],
                         'wrong_sheet')
        self.assertEqual(self.read_trial('trial-A', status=202)['status'], 'pending')
        press.load('A')
        receipt = self.trial('trial-A', number, 'A')
        self.assertEqual(receipt['press_no'], 1)
        self.assertEqual(self.release(number, 'trial-A')['receipt'], receipt)

    def test_physical_paper_conflict_after_untracked_strike(self):
        trial, _ = self.publish_pair()
        number = trial['edition_id']
        press = self.rig.press
        press.load('A')
        # A strike under a different owner leaves A non-blank before the trial.
        press.strike('A', SAMPLE_POINTS, owner=None)
        self.assertEqual(self.trial('trial-A', number, 'A', status=409)['error'],
                         'paper_conflict')
        self.assertEqual(self.rig.query('SELECT COUNT(*) FROM trial_requests'), [(0,)])

    def test_stale_pending_record_releases_slot_on_conflict(self):
        trial, _ = self.publish_pair()
        second = self.rig.publish_sample(trial['proof_id'], 'C')
        number = trial['edition_id']
        press = self.rig.press
        press.load('A')
        press.set_evidence_available(False)
        self.assertEqual(self.trial('trial-A', number, 'A', status=202)['status'], 'pending')
        press.set_evidence_available(True)
        # Someone pressed A outside this trial; it can never be proven.
        press.strike('A', SAMPLE_POINTS)
        self.assertEqual(self.trial('trial-A', number, 'A', status=409)['error'],
                         'paper_conflict')
        self.assertEqual(self.rig.query('SELECT COUNT(*) FROM trial_requests'), [(0,)])
        press.load('C')
        self.assertEqual(self.trial('trial-C', second['edition_id'], 'C')['press_no'], 2)

    def test_reply_loss_after_settles_on_own_strike(self):
        trial, _ = self.publish_pair()
        number = trial['edition_id']
        press = self.rig.press
        press.load('A')
        press.arm_reply_loss('after')
        self.trial('trial-A', number, 'A', status=202)
        # Its own strike exists, so this request settles on its own points.
        receipt = self.trial('trial-A', number, 'A')
        self.assertEqual(receipt['press_no'], 1)
        self.assertEqual(press.press_count(), 1)

    def test_pattern_mismatch_releases_slot(self):
        trial, _ = self.publish_pair()
        number = trial['edition_id']
        press = self.rig.press
        press.load('A')
        press.arm_reply_loss('before')
        self.trial('trial-A', number, 'A', status=202)
        # The trial's strike never landed, but the sheet now carries a foreign
        # pattern, so the original number can never be proven.
        press.strike('A', [[1, 0]])
        self.assertEqual(self.trial('trial-A', number, 'A', status=409)['error'],
                         'paper_conflict')
        self.assertEqual(self.rig.query('SELECT COUNT(*) FROM trial_requests'), [(0,)])

    def test_confirmed_ordinary_original_survives_wait(self):
        trial, ordinary = self.publish_pair()
        press = self.rig.press
        press.load('B')
        first = self.rig.print_card('card-B', ordinary['edition_id'], 'B')
        press.load('A')
        press.arm_reply_loss('before')
        self.trial('trial-A', trial['edition_id'], 'A', status=202)
        # A pending trial holding A must not disturb an already confirmed order.
        self.assertEqual(self.rig.print_card('card-B', ordinary['edition_id'], 'B'), first)
        self.assertEqual(press.press_count(), 1)

    def test_crash_after_strike_settles_without_second_press(self):
        trial, _ = self.publish_pair()
        number = trial['edition_id']
        self.rig.press.load('A')
        with mock.patch.object(press.trials, '_settle_attempt',
                               side_effect=RuntimeError('simulated crash')):
            with self.assertRaises(Exception):
                self.rig.client.exchange(
                    'POST', '/proofs',
                    {'request_id': 'trial-A', 'edition_id': number, 'paper_id': 'A'})
        self.rig.restart()
        self.assertEqual([strike.press_no for strike in
                          self.rig.press.observe_paper('A').strikes], [1])
        self.assertEqual(self.rig.query('SELECT state FROM trial_requests'), [('pending',)])
        receipt = self.trial('trial-A', number, 'A')
        self.assertEqual(receipt['press_no'], 1)
        self.assertEqual(self.rig.press.press_count(), 1)
        self.assertEqual(self.release(number, 'trial-A')['receipt'], receipt)
