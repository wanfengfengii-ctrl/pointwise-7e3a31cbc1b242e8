from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from press.mechanics import EvidenceUnavailable, LoadedPaperChanged, PressBusy
from tests.support import WorkshopCase, paper, scenario


INITIAL_GRID = ((1, 0), (2, 2), (4, 1), (5, 0))


class TestProduction(WorkshopCase):
    def assert_no_confirmation(self, edition, request_id):
        self.assertEqual(self.rig.receipt(request_id, status=404)['error'], 'unknown_receipt')
        report = self.rig.report(edition)
        self.assertEqual((report['completed'], report['shortfall'], report['pieces']), (0, 2, []))

    def test_frozen_layout(self):
        edition = self.publish_initial()
        self.rig.edit(1, ['V'], paper(direction='reverse'))
        self.assertEqual(self.rig.preview(2)['points'], [[5, 0], [6, 1]])
        issued = self.rig.edition(edition['edition_id'])
        self.assertEqual(issued, edition)
        receipt = self.rig.print_card('print-frozen', edition['edition_id'], 'B')
        self.assertEqual((receipt['paper_id'], receipt['press_no']), ('B', 1))
        self.assertEqual((receipt['manuscript_id'], receipt['revision'], receipt['proof_id']),
                         ('hall', 1, edition['proof_id']))
        self.assertEqual(self.rig.press.observe_paper('B').points, INITIAL_GRID)

    def test_pinned_preview(self):
        preview = self.rig.preview()
        self.rig.edit(1, ['V'], paper())
        revised = self.rig.preview(2)
        self.assertEqual(revised['points'], [[1, 1], [2, 0]])
        edition = self.rig.publish(preview['proof_id'])
        number = edition['edition_id']
        self.assertEqual(self.rig.edition(number), edition)
        self.assertEqual(edition['points'], [list(point) for point in INITIAL_GRID])
        self.assertEqual(edition['revision'], 1)
        receipt = self.rig.print_card('pinned', number, 'B')
        observed = self.rig.press.observe_paper('B')
        self.assertEqual(observed.points, INITIAL_GRID)
        self.assertEqual(receipt['revision'], 1)
        self.assertEqual(receipt['proof_id'], preview['proof_id'])

    def test_publish_validation(self):
        preview = self.rig.preview()
        self.assertEqual(self.rig.publish(999, status=404)['error'], 'unknown_proof')
        for invalid in (0, -1, True, 1.5, '2', None):
            with self.subTest(target=invalid):
                result = self.rig.publish(preview['proof_id'], invalid, status=422)
                self.assertEqual(result['error'], 'invalid_target')
        self.assertEqual(self.rig.query('SELECT COUNT(*) FROM frozen_editions'), [(0,)])
        self.assertEqual(self.rig.query('SELECT COUNT(*) FROM edition_targets'), [(0,)])
        edition = self.rig.publish(preview['proof_id'], 2)
        self.assertEqual(self.rig.report(edition['edition_id'])['target'], 2)

    def test_wrong_sheet(self):
        number = self.publish_initial()['edition_id']
        self.assertEqual(self.rig.press.inspect_loaded(), 'B')
        error = self.rig.print_card('wrong-stock', number, 'A', status=409)
        self.assertEqual(error['error'], 'wrong_sheet')
        self.assertEqual(self.rig.press.press_count(), 0)
        self.assert_no_confirmation(number, 'wrong-stock')
        self.rig.press.load('A')
        receipt = self.rig.print_card('wrong-stock', number, 'A')
        self.assertEqual((receipt['paper_id'], receipt['press_no']), ('A', 1))

    def test_swap_before_strike(self):
        number = self.publish_initial()['edition_id']
        press = self.rig.press
        press.load('A')
        press.schedule_load('B')
        self.assertEqual(press.inspect_loaded(), 'A')
        error = self.rig.print_card('feed-change', number, 'A', status=409)
        self.assertEqual(error['error'], 'wrong_sheet')
        self.assertEqual(press.inspect_loaded(), 'B')
        self.assertEqual(press.press_count(), 0)
        self.assertEqual(press.observe_paper('B').points, ())
        self.assertEqual(press.observe_paper('A').strikes, ())
        self.assert_no_confirmation(number, 'feed-change')

    def test_device_refusal(self):
        number = self.publish_initial()['edition_id']
        press = self.rig.press
        press.arm_refusal()
        response = self.rig.print_card('confirmed-by-press', number, 'B', status=503)
        self.assertEqual(response['error'], 'device_refusal')
        self.assertEqual(press.press_count(), 0)
        self.assertEqual(press.observe_paper('B').strikes, ())
        self.assert_no_confirmation(number, 'confirmed-by-press')
        receipt = self.rig.print_card('confirmed-by-press', number, 'B')
        self.assertEqual(receipt['press_no'], 1)
        self.assertEqual(self.rig.report(number)['completed'], 1)

    def check_reply_loss(self, phase, expected_strikes):
        number = self.publish_initial()['edition_id']
        press = self.rig.press
        press.load('A')
        press.arm_reply_loss(phase)
        response = self.rig.print_card('lost-reply', number, 'A', status=503)
        self.assertEqual(response, {'error': 'device_no_reply', 'message': 'press reply was lost'})
        self.assert_no_confirmation(number, 'lost-reply')
        self.rig.restart()
        self.assert_no_confirmation(number, 'lost-reply')
        press = self.rig.press
        observed = press.observe_paper('A')
        expected_grid = INITIAL_GRID if expected_strikes else ()
        self.assertEqual(observed.points, expected_grid)
        self.assertEqual(press.press_count(), expected_strikes)
        self.assertEqual([strike.press_no for strike in observed.strikes],
                         list(range(1, expected_strikes + 1)))
        if phase == 'before':
            press.load('B')
            other = self.rig.print_card('other-paper', number, 'B')
            self.assertEqual(other['press_no'], 1)
            self.assertEqual(press.observe_paper('B').points, INITIAL_GRID)
            self.assertEqual(press.observe_paper('A').points, ())
            self.assertEqual(self.rig.receipt('lost-reply', status=404)['error'], 'unknown_receipt')
        report = self.rig.report(number)
        expected_completed = 1 if phase == 'before' else 0
        self.assertEqual(report['completed'], expected_completed)
        scenario(f'n8.loss_{phase}', {'request_id': 'lost-reply', 'paper_id': 'A', 'phase': phase},
                 {'paper_points': expected_grid, 'strikes_on_a': expected_strikes},
                 {'paper_points': observed.points, 'strikes_on_a': len(observed.strikes)},
                 {'error': 'device_no_reply', 'confirmed_pieces': expected_completed},
                 {'error': response['error'], 'confirmed_pieces': report['completed']},
                 ['press/mechanics.py', 'press/production.py', 'press/receipts.py', 'record/lookup.py'],
                 '从空白 A 和零压次开始，按注入的物理动作边界计算 A 的压次，只有明确回包的 B 可入账。')

    def test_loss_before(self):
        self.check_reply_loss('before', 0)

    def test_loss_after(self):
        self.check_reply_loss('after', 1)

    def test_exclusive_reopen(self):
        number = self.publish_initial()['edition_id']
        press = self.rig.press
        press.load('A')
        press.claim('fixture-hold', 'A')
        self.rig.restart()
        press = self.rig.press
        self.assertEqual(press.inspect_loaded(), 'A')
        press.claim('fixture-hold', 'A')
        with self.assertRaises(PressBusy):
            press.load('B', owner='fixture-hold')
        with self.assertRaises(PressBusy):
            press.release('different-owner')
        with self.assertRaises(LoadedPaperChanged):
            press.claim('fixture-hold', 'B')
        with self.assertRaises(PressBusy):
            press.strike('A', INITIAL_GRID)
        error = self.rig.print_card('after-release', number, 'A', status=503)
        self.assertEqual(error['error'], 'device_refusal')
        self.assertEqual(press.press_count(), 0)
        self.assert_no_confirmation(number, 'after-release')
        strike = press.strike('A', INITIAL_GRID, owner='fixture-hold')
        self.assertEqual((strike.paper_id, strike.press_no), ('A', 1))
        press.release('fixture-hold')
        press.load('B')
        receipt = self.rig.print_card('after-release', number, 'B')
        self.assertEqual((receipt['paper_id'], receipt['press_no']), ('B', 2))
        self.assertEqual(self.rig.report(number)['completed'], 1)

    def test_evidence_outage_preserves_physical_state(self):
        number = self.publish_initial()['edition_id']
        receipt = self.rig.print_card('visible-again', number, 'B')
        press = self.rig.press
        press.set_evidence_available(False)
        self.rig.restart()
        press = self.rig.press
        with self.assertRaises(EvidenceUnavailable):
            press.observe_paper('B')
        with self.assertRaises(EvidenceUnavailable):
            press.press_count()
        self.assertEqual(self.rig.receipt('visible-again'), receipt)
        press.set_evidence_available(True)
        self.assertEqual(press.press_count(), 1)
        self.assertEqual(press.observe_paper('B').points, INITIAL_GRID)

    def test_concurrent_same_request(self):
        number = self.publish_initial()['edition_id']
        start = Barrier(2)

        def make():
            start.wait(timeout=5)
            return self.rig.print_card('coincident', number, 'B')

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(make)
            second = executor.submit(make)
            self.assertEqual(first.result(), second.result())
        self.assertEqual(self.rig.press.press_count(), 1)
        self.assertEqual(self.rig.report(number)['completed'], 1)
