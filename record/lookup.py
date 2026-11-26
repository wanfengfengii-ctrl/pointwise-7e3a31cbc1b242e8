from dataclasses import dataclass

from edition.editions import EditionStore
from press.receipts import ReceiptStore
from record.completion import summarize_completion
from record.provenance import PaperProvenance, build_ordered_provenance
from record.targets import TargetStore


@dataclass(frozen=True)
class EditionReport:
    edition_id: int
    target: int
    completed: int
    shortfall: int
    pieces: tuple[PaperProvenance, ...]


def edition_report(db, edition_id):
    with db:
        db.execute('BEGIN')
        edition = EditionStore(db).get(edition_id)
        target = TargetStore(db).get(edition.edition_id)
        receipts = ReceiptStore(db).list_for_edition(edition.edition_id)
    totals = summarize_completion(target, receipts)
    pieces = build_ordered_provenance(edition, receipts)
    return EditionReport(edition.edition_id, totals.target, totals.completed, totals.shortfall,
                         pieces)
