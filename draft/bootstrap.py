from draft.manuscripts import ManuscriptStore
from draft.paper import decode_paper_spec
from draft.patterns import PatternCatalog, require_identifier
from draft.revisions import DraftRevision, RevisionStore


def initialize_draft(db, seed):
    with db:
        db.execute('BEGIN IMMEDIATE')
        PatternCatalog.install(db)
        ManuscriptStore.install(db)
        RevisionStore.install(db)
        if db.execute('SELECT 1 FROM manuscripts LIMIT 1').fetchone():
            return
        catalog = PatternCatalog(db)
        catalog.seed(seed['patterns'])
        initial = seed['manuscript']
        manuscript_id = require_identifier(initial['manuscript_id'])
        cells = catalog.require_cells(initial['cells'])
        paper = decode_paper_spec(initial['paper'])
        ManuscriptStore(db).create(manuscript_id)
        RevisionStore(db).append(DraftRevision(manuscript_id, 1, cells, paper))
