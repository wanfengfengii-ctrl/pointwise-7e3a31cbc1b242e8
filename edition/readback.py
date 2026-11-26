from dataclasses import asdict

from edition.editions import EditionStore


def read_edition(db, edition_id):
    edition = EditionStore(db).get(edition_id)
    return asdict(edition)
