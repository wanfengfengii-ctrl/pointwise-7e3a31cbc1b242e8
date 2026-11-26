from tests.trial_support import TrialSupport


class TestTrial(TrialSupport):
    def test_designate_and_validate_sample(self):
        proof = self.rig.preview()
        self.assertEqual(self.rig.publish_sample(proof['proof_id'], 'Z', status=404)['error'],
                         'unknown_paper')
        self.rig.press.load('A')
        self.rig.press.strike('A', [[1, 0]])
        self.assertEqual(self.rig.publish_sample(proof['proof_id'], 'A', status=409)['error'],
                         'paper_conflict')
        trial = self.rig.publish_sample(proof['proof_id'], 'C', target=2)
        self.assertEqual(sorted(trial),
                         ['edition_id', 'manuscript_id', 'paper', 'points', 'proof_id',
                          'revision'])
        self.assertEqual(self.rig.edition(trial['edition_id']), trial)
        again = self.rig.publish_sample(proof['proof_id'], 'C', status=409)
        self.assertEqual(again['error'], 'paper_conflict')

    def test_ordinary_edition_unchanged(self):
        ordinary = self.rig.publish(self.rig.preview()['proof_id'], target=2)
        self.assertNotIn('sample_paper_id', ordinary)
        self.assertEqual(self.rig.edition(ordinary['edition_id']), ordinary)
        self.assertEqual(self.release(ordinary['edition_id'], 'x', status=409)['error'],
                         'release_conflict')

    def test_evidence_outage_defers_edition(self):
        proof = self.rig.preview()
        self.rig.press.set_evidence_available(False)
        self.assertEqual(self.rig.publish_sample(proof['proof_id'], 'A', status=202),
                         {'status': 'pending'})
        self.assertEqual(self.rig.query('SELECT COUNT(*) FROM frozen_editions'), [(0,)])
        self.rig.press.set_evidence_available(True)
        issued = self.rig.publish_sample(proof['proof_id'], 'A')
        self.rig.press.load('A')
        self.assertEqual(self.trial('trial-A', issued['edition_id'], 'A')['press_no'], 1)

    def test_formal_blocked_until_release(self):
        trial, ordinary = self.publish_pair()
        number = trial['edition_id']
        self.rig.press.load('C')
        blocked = self.rig.print_card('early', number, 'C', status=409)
        self.assertEqual(blocked['error'], 'edition_not_released')
        self.assertEqual(self.rig.press.press_count(), 0)
        self.assertEqual(self.rig.report(number)['pieces'], [])
        # Ordinary editions keep printing as before.
        self.rig.press.load('B')
        self.assertEqual(self.rig.print_card('ordinary', ordinary['edition_id'], 'B')['press_no'], 1)

    def test_sample_paper_never_a_formal_piece(self):
        trial, ordinary = self.publish_pair()
        for edition in (trial['edition_id'], ordinary['edition_id']):
            self.rig.press.load('A')
            error = self.rig.print_card('uses-sample', edition, 'A', status=409)
            self.assertEqual(error['error'], 'sample_paper_reserved')
        self.assertEqual(self.rig.press.press_count(), 0)

    def test_trial_basic_and_release(self):
        trial, _ = self.publish_pair()
        number = trial['edition_id']
        self.rig.press.load('A')
        receipt = self.trial('trial-A', number, 'A')
        self.assertEqual(receipt, {'request_id': 'trial-A', 'edition_id': number,
                                   'paper_id': 'A', 'press_no': 1})
        self.assertEqual(self.read_trial('trial-A'), receipt)
        report = self.rig.report(number)
        self.assertEqual((report['completed'], report['shortfall'], report['pieces']),
                         (0, 1, []))
        released = self.release(number, 'trial-A')
        self.assertEqual(released, {'edition_id': number, 'receipt': receipt})
        self.rig.press.load('C')
        card = self.rig.print_card('formal-C', number, 'C')
        report = self.rig.report(number)
        self.assertEqual(report['completed'], 1)
        self.assertEqual([(item['request_id'], item['paper_id'], item['press_no'])
                          for item in report['pieces']], [('formal-C', 'C', 2)])
        self.assertEqual(card['press_no'], 2)

    def test_trial_validation(self):
        trial, ordinary = self.publish_pair()
        number = trial['edition_id']
        self.assertEqual(self.trial('nope', ordinary['edition_id'], 'B', status=409)['error'],
                         'trial_not_allowed')
        self.assertEqual(self.trial('wrong', number, 'B', status=409)['error'],
                         'trial_not_allowed')
        self.assertEqual(self.trial('missing', 999, 'A', status=404)['error'],
                         'unknown_edition')
        self.assertEqual(self.trial('ghost', number, 'Z', status=404)['error'],
                         'unknown_paper')
        self.assertEqual(self.read_trial('ghost', status=404)['error'], 'unknown_trial')
        self.assertEqual(self.rig.query('SELECT COUNT(*) FROM trial_requests'), [(0,)])

    def test_single_open_trial_then_conflicts(self):
        first, _ = self.publish_pair()
        second = self.rig.publish_sample(first['proof_id'], 'C')
        self.rig.press.load('A')
        self.rig.press.arm_reply_loss('before')
        self.assertEqual(self.trial('trial-A', first['edition_id'], 'A', status=202),
                         {'request_id': 'trial-A', 'status': 'pending'})
        self.assertEqual(self.trial('trial-C', second['edition_id'], 'C', status=202),
                         {'request_id': 'trial-C', 'status': 'pending'})
        self.assertEqual(self.rig.query('SELECT COUNT(*) FROM trial_requests'), [(1,)])
        self.assertEqual(self.trial('trial-X', first['edition_id'], 'A', status=409)['error'],
                         'request_conflict')
        self.assertEqual(self.trial('trial-A', first['edition_id'], 'C', status=409)['error'],
                         'request_conflict')
        self.rig.press.load('A')
        self.assertEqual(self.trial('trial-A', first['edition_id'], 'A')['press_no'], 1)
        self.rig.press.load('C')
        self.assertEqual(self.trial('trial-C', second['edition_id'], 'C')['press_no'], 2)

    def test_release_conflicts(self):
        trial, _ = self.publish_pair()
        number = trial['edition_id']
        other = self.rig.publish_sample(trial['proof_id'], 'C')['edition_id']
        self.rig.press.load('A')
        receipt = self.trial('trial-A', number, 'A')
        self.assertEqual(self.release(other, 'trial-A', status=409)['error'],
                         'release_conflict')
        self.assertEqual(self.release(number, 'missing', status=404)['error'], 'unknown_trial')
        released = self.release(number, 'trial-A')
        self.assertEqual(released['receipt'], receipt)
        self.assertEqual(self.release(number, 'trial-A'), released)
        self.assertEqual(self.release(number, 'changed', status=409)['error'],
                         'release_conflict')
        self.assertEqual(self.rig.press.press_count(), 1)

    def test_ordinary_receipt_cannot_release(self):
        trial, ordinary = self.publish_pair()
        number = trial['edition_id']
        self.rig.press.load('B')
        card = self.rig.print_card('card-B', ordinary['edition_id'], 'B')
        self.assertEqual(card['press_no'], 1)
        blocked = self.release(number, 'card-B', status=409)
        self.assertEqual(blocked['error'], 'release_conflict')
        self.rig.press.load('A')
        self.trial('trial-A', number, 'A')
        self.assertEqual(self.release(number, 'trial-A')['receipt']['press_no'], 2)
