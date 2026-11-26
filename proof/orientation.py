from dataclasses import dataclass

from draft.paper import PaperSpec
from proof.layout import PlacedPoint


@dataclass(frozen=True)
class PaperPoint:
    cell_id: str
    occurrence: int
    point: tuple[int, int]


def project_point(placed: PlacedPoint, paper: PaperSpec):
    if paper.direction == 'forward':
        column = paper.first_printable_column + placed.offset
    else:
        column = paper.end_printable_column - 1 - placed.offset
    return PaperPoint(placed.cell_id, placed.occurrence, (column, placed.row))
