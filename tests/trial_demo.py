"""Trial-card walkthrough: pre- and post-strike reply loss, release and formal card."""
import json
from tempfile import TemporaryDirectory

from tests.support import WorkshopRig, require_equal, scenario


EXPECTED_POINTS = [[1, 0], [2, 2], [4, 1], [5, 0]]


def trial(rig, request_id, edition, paper_id, *, status=200):
    return rig.request('POST', '/proofs',
                       {'request_id': request_id, 'edition_id': edition, 'paper_id': paper_id},
                       expected=status)


def release(rig, edition, request_id, *, status=200):
    return rig.request('POST', f'/editions/{edition}/release', {'request_id': request_id},
                       expected=status)


def loss_round(a_fault):
    """One clean press, A faulted, verified and released, then a formal card on C."""
    with TemporaryDirectory(prefix='trial-demo-') as directory, WorkshopRig(directory) as rig:
        proof = rig.preview()
        require_equal(proof['points'], EXPECTED_POINTS)
        trial_edition = rig.publish_sample(proof['proof_id'], 'A', target=1)
        ordinary = rig.publish(proof['proof_id'], target=1)
        number = trial_edition['edition_id']
        require_equal('sample_paper_id' in trial_edition, False)
        require_equal('sample_paper_id' in ordinary, False)

        rig.press.load('A')
        rig.press.arm_reply_loss(a_fault)
        submitted = trial(rig, 'trial-A', number, 'A', status=202)
        require_equal(submitted, {'request_id': 'trial-A', 'status': 'pending'})

        rig.restart()
        press = rig.press
        strikes_before_resume = len(press.observe_paper('A').strikes)
        require_equal(strikes_before_resume, 1 if a_fault == 'after' else 0)
        require_equal(rig.request('GET', '/proofs/trial-A', expected=202),
                      {'request_id': 'trial-A', 'status': 'pending'})
        require_equal(release(rig, number, 'trial-A', status=202),
                      {'request_id': 'trial-A', 'status': 'pending'})
        rig.press.load('C')
        blocked = rig.print_card('formal-C', number, 'C', status=409)
        require_equal(blocked['error'], 'edition_not_released')
        require_equal(press.press_count(), 1 if a_fault == 'after' else 0)

        rig.press.load('A')
        receipt = trial(rig, 'trial-A', number, 'A')
        require_equal(receipt, {'request_id': 'trial-A', 'edition_id': number,
                                'paper_id': 'A', 'press_no': 1})
        require_equal(trial(rig, 'trial-A', number, 'A'), receipt)
        require_equal(len(press.observe_paper('A').strikes), 1)

        released = release(rig, number, 'trial-A')
        require_equal(released, {'edition_id': number, 'receipt': receipt})

        rig.press.load('C')
        formal = rig.print_card('formal-C', number, 'C')
        require_equal(formal['press_no'], 2)
        report = rig.report(number)
        require_equal([(item['request_id'], item['paper_id'], item['press_no'])
                       for item in report['pieces']], [('formal-C', 'C', 2)])

        rig.restart()
        require_equal(release(rig, number, 'trial-A'), released)
        require_equal(trial(rig, 'trial-A', number, 'A'), receipt)
        require_equal(rig.press.press_count(), 2)
        require_equal([strike.press_no for strike in rig.press.observe_paper('A').strikes], [1])
        scenario(f'trial.demo.loss_{a_fault}',
                 {'fault': a_fault, 'sample': 'A', 'formal': 'C'},
                 {'a_strikes_before_resume': 1 if a_fault == 'after' else 0,
                  'trial_press_no': 1, 'formal_press_no': 2},
                 {'a_strikes_before_resume': strikes_before_resume,
                  'trial_press_no': receipt['press_no'],
                  'formal_press_no': formal['press_no']},
                 {'report_pieces': [['formal-C', 'C', 2]], 'a_strikes': 1},
                 {'report_pieces': [[item['request_id'], item['paper_id'], item['press_no']]
                                    for item in report['pieces']],
                  'a_strikes': 1},
                 ['press/trials.py', 'press/production.py', 'press/mechanics.py',
                  'edition/publication.py', 'record/lookup.py'],
                 '手算：压前失答 A 无凸点，压后失答 A 一次；续办只补首执，放行后才在 C 制正式件，A 始终只有一次压纹。')
        return {'trial': trial_edition, 'receipt': receipt, 'released': released,
                'formal': formal, 'report': report}


def other_paper(hold):
    """B competes with a pending A trial, either free-run or deferred."""
    with TemporaryDirectory(prefix='trial-other-') as directory, WorkshopRig(directory) as rig:
        proof = rig.preview()
        trial_edition = rig.publish_sample(proof['proof_id'], 'A', target=1)
        ordinary = rig.publish(proof['proof_id'], target=1)
        number = trial_edition['edition_id']
        press = rig.press
        press.load('A')
        press.arm_reply_loss('before')
        trial(rig, 'trial-A', number, 'A', status=202)

        if hold:
            press.claim('fixture-hold', 'A')
            deferred = rig.print_card('card-B', ordinary['edition_id'], 'B', status=202)
            require_equal(deferred, {'status': 'pending'})
            press.release('fixture-hold')
            a_receipt = trial(rig, 'trial-A', number, 'A')
            require_equal(a_receipt['press_no'], 1)
            press.load('B')
            b_receipt = rig.print_card('card-B', ordinary['edition_id'], 'B')
            require_equal(b_receipt['press_no'], 2)
        else:
            require_equal(rig.print_card('card-B', ordinary['edition_id'], 'B', status=202),
                          {'status': 'pending'})
            press.load('B')
            b_receipt = rig.print_card('card-B', ordinary['edition_id'], 'B')
            require_equal(b_receipt['press_no'], 1)
            press.load('A')
            a_receipt = trial(rig, 'trial-A', number, 'A')
            require_equal(a_receipt['press_no'], 2)

        rejected = release(rig, number, 'card-B', status=409)
        require_equal(rejected['error'], 'release_conflict')
        released = release(rig, number, 'trial-A')
        require_equal(released['receipt'], a_receipt)
        scenario(f'trial.demo.other_{"hold" if hold else "free"}',
                 {'hold': hold, 'sample': 'A', 'other': 'B'},
                 {'a_press_no': 1 if hold else 2, 'b_press_no': 2 if hold else 1,
                  'b_releases_a': False},
                 {'a_press_no': a_receipt['press_no'], 'b_press_no': b_receipt['press_no'],
                  'b_releases_a': False},
                 {'release': 'trial-A'},
                 {'release': released['receipt']['request_id']},
                 ['press/trials.py', 'press/production.py', 'press/mechanics.py'],
                 '手算：B 先办则 B 取 1、A 取 2；A 独占时 B 暂缓，A 取 1、B 取 2；B 的普通首执放行 E 均失败。')
        return {'a': a_receipt, 'b': b_receipt, 'released': released, 'rejected': rejected}


def main():
    loss_before = loss_round('before')
    loss_after = loss_round('after')
    other_free = other_paper(False)
    other_hold = other_paper(True)
    print(json.dumps({'loss_before': loss_before, 'loss_after': loss_after,
                      'other_free': other_free, 'other_hold': other_hold},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
