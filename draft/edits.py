from draft.manuscripts import ManuscriptStore
from draft.paper import decode_paper_spec
from draft.patterns import PatternCatalog, require_identifier
from draft.revisions import DraftRevision, RevisionStore


class StaleRevision(Exception):
    def __init__(self, current_revision):
        super().__init__('expected revision differs from the current revision')
        self.current_revision = current_revision


class InvalidEdit(ValueError):
    pass


def edit_manuscript(db, manuscript_id, expected_revision, cells, paper):
    try:
        require_identifier(manuscript_id)
        if type(expected_revision) is not int or expected_revision <= 0:
            raise ValueError('expected_revision must be a positive integer')
        spec = decode_paper_spec(paper)
    except ValueError as exc:
        raise InvalidEdit(str(exc)) from exc

    with db:
        db.execute('BEGIN IMMEDIATE')
        manuscripts = ManuscriptStore(db)
        current = manuscripts.head(manuscript_id)
        if current is None:
            raise InvalidEdit(f'unknown manuscript {manuscript_id}')
        if expected_revision != current:
            raise StaleRevision(current)
        try:
            sequence = PatternCatalog(db).require_cells(cells)
        except ValueError as exc:
            raise InvalidEdit(str(exc)) from exc
        entry = DraftRevision(manuscript_id, current + 1, sequence, spec)
        RevisionStore(db).append(entry)
        if not manuscripts.advance(manuscript_id, expected_revision):
            raise StaleRevision(manuscripts.head(manuscript_id))
    return entry
