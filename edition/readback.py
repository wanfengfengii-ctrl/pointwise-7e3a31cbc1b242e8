from edition.editions import EditionStore, edition_snapshot


def read_edition(db, edition_id):
    return edition_snapshot(EditionStore(db).get(edition_id))
