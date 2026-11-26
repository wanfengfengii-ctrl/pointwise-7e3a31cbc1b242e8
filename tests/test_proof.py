from tempfile import TemporaryDirectory

from tests.support import WorkshopCase, WorkshopRig, paper, scenario


FORWARD_POINTS = [[1, 0], [2, 2], [4, 1], [5, 0]]
REVERSE_POINTS = [[2, 0], [3, 1], [5, 2], [6, 0]]


class TestProof(WorkshopCase):
    def test_orientation(self):
        forward = self.rig.preview()
        spec = paper(direction='reverse')
        edit = self.rig.edit(1, ['U', 'V'], spec)
        reverse = self.rig.preview(edit['revision'])
        expected_occurrences = [
            {'cell_id': 'U', 'occurrence': 1, 'points': [[6, 0], [5, 2]]},
            {'cell_id': 'V', 'occurrence': 2, 'points': [[3, 1], [2, 0]]},
        ]
        self.assertEqual(forward['points'], FORWARD_POINTS)
        self.assertEqual(reverse['points'], REVERSE_POINTS)
        self.assertEqual(reverse['occurrences'], expected_occurrences)
        self.assertEqual(self.rig.preview(edit['revision']), reverse)
        edition = self.rig.publish(reverse['proof_id'])
        self.assertEqual(edition['points'], REVERSE_POINTS)
        self.assertEqual(edition['revision'], 2)
        self.assertEqual(edition['paper'], spec)
        scenario('n1.asymmetric_margins', {'cells': ['U', 'V'], 'paper': spec},
                 {'points': REVERSE_POINTS, 'occurrences': expected_occurrences},
                 {'points': reverse['points'], 'occurrences': reverse['occurrences']},
                 {'points': REVERSE_POINTS, 'revision': 2},
                 {'points': edition['points'], 'revision': edition['revision']},
                 ['proof/layout.py', 'proof/orientation.py', 'proof/sheets.py',
                  'edition/publication.py'],
                 '手算可压列 1 至 6，从实际右侧第 6 列减去各点阅读偏移。')

    def test_repeated_occurrences(self):
        revision = self.rig.edit(1, ['U', 'U'], paper(direction='reverse'))['revision']
        preview = self.rig.preview(revision)
        self.assertEqual(preview['occurrences'], [
            {'cell_id': 'U', 'occurrence': 1, 'points': [[6, 0], [5, 2]]},
            {'cell_id': 'U', 'occurrence': 2, 'points': [[3, 0], [2, 2]]},
        ])
        self.assertEqual(preview['points'], [[2, 2], [3, 0], [5, 2], [6, 0]])

    def test_stale_edit(self):
        old = self.rig.preview()
        accepted = self.rig.edit(1, ['V'], paper())
        current = self.rig.preview(accepted['revision'])
        stale = self.rig.edit(1, ['U', 'U'], paper(), status=409)
        self.assertEqual(stale['error'], 'stale_revision')
        self.assertEqual(stale['current_revision'], 2)
        self.assertEqual(self.rig.preview(1), old)
        self.assertEqual(self.rig.preview(2), current)
        self.assertEqual(current['points'], [[1, 1], [2, 0]])
        self.assertEqual(self.rig.preview(3, status=404)['error'], 'unknown_revision')
        frozen = self.rig.publish(old['proof_id'])
        receipt = self.rig.print_card('old-proof', frozen['edition_id'], 'B')
        self.assertEqual(receipt['revision'], 1)
        self.assertEqual(self.rig.press.observe_paper('B').points,
                         ((1, 0), (2, 2), (4, 1), (5, 0)))

    def test_edit_head(self):
        first = self.rig.edit(1, ['V'], paper())
        second = self.rig.edit(first['revision'], ['U'], paper())
        self.assertEqual((first['revision'], second['revision']), (2, 3))
        self.assertEqual(self.rig.preview(1)['points'], FORWARD_POINTS)
        self.assertEqual(self.rig.preview(2)['points'], [[1, 1], [2, 0]])
        self.assertEqual(self.rig.preview(3)['points'], [[1, 0], [2, 2]])

    def test_seed_reopen(self):
        first = self.rig.preview(1)
        self.rig.edit(1, ['V', 'V'], paper())
        edited = self.rig.preview(2)
        self.rig.seed['patterns']['V'] = [[0, 0]]
        self.rig.seed['manuscript']['cells'] = ['U']
        self.rig.restart()
        self.assertEqual(self.rig.preview(1), first)
        self.assertEqual(self.rig.preview(2), edited)
        result = self.rig.edit(2, ['V'], paper())
        self.assertEqual(result['revision'], 3)
        self.assertEqual(self.rig.preview(3)['points'], [[1, 1], [2, 0]])

    def test_outside_margin(self):
        revision = self.rig.edit(1, ['U', 'V'], paper(6, 1, 1))['revision']
        failure = self.rig.preview(revision, status=422)
        self.assertEqual(failure['error'], 'outside_printable_area')
        self.assertEqual(failure['violations'], [{'cell_id': 'V', 'occurrence': 2, 'point': [5, 0]}])
        self.assertNotIn('proof_id', failure)
        self.assertEqual(self.rig.query('SELECT COUNT(*) FROM proof_sheets'), [(0,)])
        self.assertEqual(self.rig.publish(1, status=404)['error'], 'unknown_proof')

    def test_right_edge(self):
        valid = self.rig.edit(1, ['U', 'V'], paper(7, 1, 1))['revision']
        self.assertEqual(self.rig.preview(valid)['points'][-1], [5, 0])
        narrow = self.rig.edit(valid, ['U', 'V'], paper(6, 1, 1))['revision']
        error = self.rig.preview(narrow, status=422)
        self.assertEqual(error['violations'], [{'cell_id': 'V', 'occurrence': 2, 'point': [5, 0]}])
        self.assertEqual(self.rig.query('SELECT revision FROM proof_sheets'), [(valid,)])

    def test_correct_and_preview(self):
        rejected = self.rig.edit(1, ['U', 'U'], paper(6, 1, 2, 'reverse'))['revision']
        self.assertEqual(self.rig.preview(rejected, status=422)['violations'], [
            {'cell_id': 'U', 'occurrence': 2, 'point': [0, 0]},
            {'cell_id': 'U', 'occurrence': 2, 'point': [-1, 2]},
        ])
        corrected = self.rig.edit(rejected, ['U', 'U'], paper(direction='reverse'))['revision']
        preview = self.rig.preview(corrected)
        edition = self.rig.publish(preview['proof_id'])
        self.assertEqual(edition['points'], [[2, 2], [3, 0], [5, 2], [6, 0]])
        self.assertEqual(edition['revision'], corrected)
        self.assertEqual(self.rig.preview(rejected, status=422)['error'], 'outside_printable_area')

    def test_invalid_edit_preserves_history(self):
        for cells, spec in [([], paper()), (['missing'], paper()), (['U'], paper(width=True)),
                            (['U'], paper(width=3, left=1, right=2)),
                            (['U'], paper(direction='sideways'))]:
            with self.subTest(cells=cells, spec=spec):
                response = self.rig.edit(1, cells, spec, status=422)
                self.assertEqual(response['error'], 'invalid_edit')
        self.assertEqual(self.rig.preview(1)['points'], FORWARD_POINTS)
        self.assertEqual(self.rig.preview(2, status=404)['error'], 'unknown_revision')
        self.assertEqual(self.rig.edit(1, ['U'], paper())['revision'], 2)

    def test_invalid_seed_rolls_back(self):
        with TemporaryDirectory(prefix='bad-tactile-seed-') as directory:
            seed = dict(self.rig.seed, patterns={})
            sample = WorkshopRig(directory, seed)
            with self.assertRaisesRegex(ValueError, 'catalog cannot be empty'):
                sample.start()
            sample.seed = self.rig.seed
            with sample:
                self.assertEqual(sample.preview(1)['points'], FORWARD_POINTS)
