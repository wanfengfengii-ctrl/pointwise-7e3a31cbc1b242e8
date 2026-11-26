from dataclasses import dataclass

from draft.patterns import PatternCatalog
from draft.revisions import DraftRevision

CELL_ADVANCE = 3


@dataclass(frozen=True)
class PlacedPoint:
    cell_id: str
    occurrence: int
    offset: int
    row: int


def place_cells(revision: DraftRevision, catalog: PatternCatalog):
    patterns = {cell_id: catalog.get(cell_id) for cell_id in dict.fromkeys(revision.cells)}
    for index, cell_id in enumerate(revision.cells):
        pattern = patterns[cell_id]
        if pattern is None:
            raise ValueError(f'revision references unknown cell {cell_id}')
        for x, y in pattern.points:
            yield PlacedPoint(cell_id, index + 1, CELL_ADVANCE * index + x, y)
