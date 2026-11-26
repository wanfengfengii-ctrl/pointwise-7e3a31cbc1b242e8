from dataclasses import dataclass

from edition.editions import FrozenEdition
from press.receipts import Receipt


@dataclass(frozen=True)
class PaperProvenance:
    request_id: str
    paper_id: str
    press_no: int
    edition_id: int
    manuscript_id: str
    revision: int
    proof_id: int


def build_ordered_provenance(edition: FrozenEdition, receipts: tuple[Receipt, ...]):
    return tuple(
        PaperProvenance(receipt.request_id, receipt.paper_id, receipt.press_no,
                        edition.edition_id, edition.manuscript_id, edition.revision,
                        edition.proof_id)
        for receipt in sorted(receipts, key=lambda item: item.press_no)
    )
