"""Compare the V1 press histories behind the trial-card example."""
import json
from tempfile import TemporaryDirectory

from tests.support import WorkshopRig, require_equal


def trace(a_fault):
    b_fault = "after" if a_fault == "before" else "before"
    with TemporaryDirectory(prefix="trial-fixture-") as directory, WorkshopRig(directory) as rig:
        proof = rig.preview()
        editions = {paper: rig.publish(proof["proof_id"], 1)["edition_id"] for paper in ("A", "B")}
        press = rig.press
        for paper, fault in (("A", a_fault), ("B", b_fault)):
            press.load(paper)
            press.arm_reply_loss(fault)
            result = rig.print_card(f"make-{paper}", editions[paper], paper, status=503)
            require_equal(result["error"], "device_no_reply")

        rig.restart()
        press = rig.press
        shared = {
            "loaded": press.inspect_loaded(),
            "press_count": press.press_count(),
            "receipts": {paper: rig.receipt(f"make-{paper}", status=404)["error"]
                         for paper in editions},
            "completed": {paper: rig.report(number)["completed"]
                          for paper, number in editions.items()},
        }
        strikes = {paper: [{"press_no": strike.press_no, "points": [list(p) for p in strike.points]}
                           for strike in press.observe_paper(paper).strikes]
                   for paper in editions}
        return shared, strikes


def main():
    shared_before, before = trace("before")
    shared_after, after = trace("after")
    require_equal(shared_before, shared_after)
    require_equal(shared_before, {
        "loaded": "B", "press_count": 1,
        "receipts": {"A": "unknown_receipt", "B": "unknown_receipt"},
        "completed": {"A": 0, "B": 0},
    })
    one = [{"press_no": 1, "points": [[1, 0], [2, 2], [4, 1], [5, 0]]}]
    require_equal(before, {"A": [], "B": one})
    require_equal(after, {"A": one, "B": []})
    print(json.dumps({"shared": shared_before, "A_lost_before": before, "A_lost_after": after},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
