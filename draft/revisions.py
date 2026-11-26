import json
from dataclasses import asdict, dataclass

from draft.paper import PaperSpec, decode_paper_spec


@dataclass(frozen=True)
class DraftRevision:
    manuscript_id: str
    revision: int
    cells: tuple[str, ...]
    paper: PaperSpec


class RevisionStore:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def install(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS draft_revisions (
                manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
                revision INTEGER NOT NULL CHECK (revision > 0),
                cells TEXT NOT NULL,
                paper TEXT NOT NULL,
                PRIMARY KEY (manuscript_id, revision)
            )
        ''')

    def append(self, entry):
        self.db.execute('''
            INSERT INTO draft_revisions (manuscript_id, revision, cells, paper)
            VALUES (?, ?, ?, ?)
        ''', (
            entry.manuscript_id,
            entry.revision,
            json.dumps(entry.cells),
            json.dumps(asdict(entry.paper)),
        ))

    def get(self, manuscript_id, revision):
        row = self.db.execute('''
            SELECT revision, cells, paper FROM draft_revisions
            WHERE manuscript_id = ? AND revision = ?
        ''', (manuscript_id, str(revision))).fetchone()
        if row is None:
            return None
        number, cells, paper = row
        return DraftRevision(manuscript_id, number, tuple(json.loads(cells)),
                             decode_paper_spec(json.loads(paper)))
