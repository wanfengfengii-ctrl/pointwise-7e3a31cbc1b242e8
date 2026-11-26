from tests.support import WorkshopCase


class TestRecord(WorkshopCase):
    def test_receipt_reopened(self):
        edition = self.publish_initial()
        number = edition['edition_id']
        first = self.rig.print_card('reopen/réception', number, 'B')
        self.rig.restart()
        self.assertEqual(self.rig.edition(number), edition)
        self.assertEqual(self.rig.receipt('reopen/réception'), first)
        self.assertEqual(self.rig.print_card('reopen/réception', number, 'B'), first)
        self.assertEqual(self.rig.press.press_count(), 1)
        self.assertEqual(len(self.rig.press.observe_paper('B').strikes), 1)
        self.assertEqual(self.rig.report(number)['completed'], 1)

    def test_changed_parameters(self):
        edition = self.publish_initial()
        number = edition['edition_id']
        second = self.rig.publish(edition['proof_id'])['edition_id']
        first = self.rig.print_card('fixed-parameters', number, 'B')
        wrong_paper = self.rig.print_card('fixed-parameters', number, 'A', status=409)
        wrong_edition = self.rig.print_card('fixed-parameters', second, 'B', status=409)
        self.assertEqual(wrong_paper['error'], 'request_conflict')
        self.assertEqual(wrong_edition['error'], 'request_conflict')
        self.assertEqual(self.rig.receipt('fixed-parameters'), first)
        self.assertEqual(self.rig.press.press_count(), 1)
        self.assertEqual(self.rig.report(second)['completed'], 0)

    def test_stock_changed(self):
        number = self.publish_initial()['edition_id']
        first = self.rig.print_card('with-new-stock', number, 'B')
        self.rig.press.load('A')
        self.rig.restart()
        self.assertEqual(self.rig.press.inspect_loaded(), 'A')
        self.assertEqual(self.rig.print_card('with-new-stock', number, 'B'), first)
        self.assertEqual(self.rig.press.observe_paper('A').strikes, ())
        self.assertEqual(self.rig.press.press_count(), 1)

    def test_completion_order(self):
        edition = self.publish_initial()
        number = edition['edition_id']
        first = self.rig.print_card('first', number, 'B')
        before = self.rig.report(number)
        self.assertEqual((before['completed'], before['shortfall']), (1, 1))
        self.assertEqual(self.rig.receipt('first'), first)
        self.assertEqual(self.rig.report(number), before)
        self.rig.press.load('A')
        second = self.rig.print_card('second', number, 'A')
        report = self.rig.report(number)
        self.assertEqual((report['target'], report['completed'], report['shortfall']), (2, 2, 0))
        self.assertEqual(report['pieces'], [
            {'request_id': 'first', 'paper_id': 'B', 'press_no': 1, 'edition_id': number,
             'manuscript_id': 'hall', 'revision': 1, 'proof_id': edition['proof_id']},
            {'request_id': 'second', 'paper_id': 'A', 'press_no': 2, 'edition_id': number,
             'manuscript_id': 'hall', 'revision': 1, 'proof_id': edition['proof_id']},
        ])
        self.assertEqual(second['press_no'], 2)
        self.assertEqual(self.rig.receipt('first'), first)

    def test_zero_progress(self):
        number = self.publish_initial(target=3)['edition_id']
        self.assertEqual(self.rig.report(number), {
            'edition_id': number, 'target': 3, 'completed': 0, 'shortfall': 3, 'pieces': [],
        })
        self.assertEqual(self.rig.edition(999, status=404)['error'], 'unknown_edition')
        self.assertEqual(self.rig.report(999, status=404)['error'], 'unknown_edition')
        missing = self.rig.print_card('unknown-edition', 999, 'B', status=404)
        self.assertEqual(missing['error'], 'unknown_edition')
        self.assertEqual(self.rig.press.press_count(), 0)

    def test_edition_isolation(self):
        first_edition = self.publish_initial()
        first_number = first_edition['edition_id']
        other_number = self.rig.publish(first_edition['proof_id'], 3)['edition_id']
        first = self.rig.print_card('on-first', first_number, 'B')
        self.assertEqual(self.rig.report(other_number), {
            'edition_id': other_number, 'target': 3, 'completed': 0, 'shortfall': 3, 'pieces': [],
        })
        self.rig.press.load('C')
        other = self.rig.print_card('on-other', other_number, 'C')
        self.rig.press.load('A')
        last = self.rig.print_card('on-first-again', first_number, 'A')
        self.rig.restart()
        self.assertEqual(self.rig.print_card('on-first', first_number, 'B'), first)
        self.assertEqual(self.rig.receipt('on-other'), other)
        self.assertEqual(self.rig.receipt('on-first-again'), last)
        self.assertEqual(self.rig.press.press_count(), 3)
        first_report = self.rig.report(first_number)
        other_report = self.rig.report(other_number)
        self.assertEqual((first_report['completed'], first_report['shortfall']), (2, 0))
        self.assertEqual((other_report['completed'], other_report['shortfall']), (1, 2))
        self.assertEqual([(item['paper_id'], item['press_no']) for item in first_report['pieces']],
                         [('B', 1), ('A', 3)])
        self.assertEqual([(item['paper_id'], item['press_no']) for item in other_report['pieces']],
                         [('C', 2)])
        self.assertTrue(all(item['edition_id'] == first_number for item in first_report['pieces']))
        self.assertEqual(other_report['pieces'][0]['edition_id'], other_number)

    def test_over_target(self):
        number = self.publish_initial(target=1)['edition_id']
        first = self.rig.print_card('first-legal', number, 'B')
        self.rig.press.load('C')
        later = self.rig.print_card('later-legal', number, 'C')
        report = self.rig.report(number)
        self.assertEqual((report['target'], report['completed'], report['shortfall']), (1, 2, 0))
        self.assertEqual([item['press_no'] for item in report['pieces']], [1, 2])
        self.assertEqual(self.rig.receipt('first-legal'), first)
        self.assertEqual(self.rig.receipt('later-legal'), later)
