from collections.abc import Iterable

from draft.paper import PaperSpec
from proof.orientation import PaperPoint


class OutsidePrintableArea(Exception):
    def __init__(self, violations):
        super().__init__('a point falls outside the printable columns')
        self.violations = tuple(violations)


def require_in_bounds(points: Iterable[PaperPoint], paper: PaperSpec):
    violations = [point for point in points if not (
        paper.first_printable_column <= point.point[0] < paper.end_printable_column
    )]
    if violations:
        raise OutsidePrintableArea(violations)
