import json
from tempfile import TemporaryDirectory

from tests.support import WorkshopRig, paper, require_equal, scenario


def main():
    with TemporaryDirectory(prefix='tactile-demo-') as directory, WorkshopRig(directory) as shop:
        narrow = shop.edit(1, ['U', 'V'], paper(6, 1, 1))
        failure = shop.preview(narrow['revision'], status=422)
        require_equal(failure['violations'], [{'cell_id': 'V', 'occurrence': 2, 'point': [5, 0]}])
        require_equal('proof_id' in failure, False)
        spec = paper(direction='reverse')
        corrected = shop.edit(narrow['revision'], ['U', 'V'], spec)
        preview = shop.preview(corrected['revision'])
        expected_points = [[2, 0], [3, 1], [5, 2], [6, 0]]
        require_equal(preview['points'], expected_points)
        require_equal(preview['occurrences'], [
            {'cell_id': 'U', 'occurrence': 1, 'points': [[6, 0], [5, 2]]},
            {'cell_id': 'V', 'occurrence': 2, 'points': [[3, 1], [2, 0]]},
        ])
        edition = shop.publish(preview['proof_id'], 2)
        number = edition['edition_id']
        changed = shop.edit(corrected['revision'], ['V'], paper())
        require_equal(shop.preview(changed['revision'])['points'], [[1, 1], [2, 0]])
        require_equal(shop.edition(number), edition)
        first = shop.print_card('demo-B', number, 'B')
        before = shop.report(number)
        require_equal((before['completed'], before['shortfall']), (1, 1))
        shop.press.load('A')
        second = shop.print_card('demo-A', number, 'A')
        shop.restart()
        require_equal(shop.receipt('demo-B'), first)
        require_equal(shop.print_card('demo-B', number, 'B'), first)
        require_equal(shop.receipt('demo-A'), second)
        require_equal(shop.press.press_count(), 2)
        observed = {paper_id: [list(point) for point in shop.press.observe_paper(paper_id).points]
                    for paper_id in ('B', 'A')}
        require_equal(observed, {'B': expected_points, 'A': expected_points})
        report = shop.report(number)
        rows = [[item['paper_id'], item['press_no'], item['revision']] for item in report['pieces']]
        expected_handoff = {'completed': 2, 'shortfall': 0, 'paper_order': [['B', 1, 3], ['A', 2, 3]]}
        actual_handoff = {'completed': report['completed'], 'shortfall': report['shortfall'],
                          'paper_order': rows}
        require_equal(actual_handoff, expected_handoff)
        require_equal([item['proof_id'] for item in report['pieces']], [preview['proof_id']] * 2)
        scenario('n7', {'cells': ['U', 'V'], 'paper': spec, 'target': 2, 'load_order': ['B', 'A']},
                 {'B': expected_points, 'A': expected_points}, observed, expected_handoff,
                 actual_handoff, ['proof/layout.py', 'proof/orientation.py', 'edition/publication.py',
                                  'press/mechanics.py', 'press/production.py', 'record/lookup.py'],
                 '按样例纸规手算 U、V 反向落点，从空机依次确认 B、A，不计重开的原号复领。')
        print(json.dumps({'rejected_preview': failure, 'edition': edition, 'report': report},
                         ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
