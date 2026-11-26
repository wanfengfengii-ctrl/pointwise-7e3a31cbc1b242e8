from dataclasses import dataclass

from edition.editions import EditionStore, FrozenEdition


@dataclass(frozen=True)
class PressOrder:
    edition: FrozenEdition
    expected_paper: str


def dispatch_edition(db, edition_id, expected_paper):
    edition = EditionStore(db).get(edition_id)
    return PressOrder(edition, expected_paper)
