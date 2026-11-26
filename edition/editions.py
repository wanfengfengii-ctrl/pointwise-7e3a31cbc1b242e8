import json
from dataclasses import asdict, dataclass

from draft.paper import PaperSpec, decode_paper_spec


class UnknownEdition(LookupError):
    pass


@dataclass(frozen=True)
class FrozenEdition:
    edition_id: int
    proof_id: int
    manuscript_id: str
    revision: int
    paper: PaperSpec
    points: tuple[tuple[int, int], ...]
    sample_paper_id: str | None = None


def edition_snapshot(edition):
    """Serialise an edition in the original frozen-response shape.

    The designated sample is bookkeeping for trials and release; the edition
    response keeps the same fields ordinary editions have always returned.
    """
    snapshot = asdict(edition)
    snapshot.pop('sample_paper_id', None)
    return snapshot


class EditionStore:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def install(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS frozen_editions (
                edition_id INTEGER PRIMARY KEY,
                proof_id INTEGER NOT NULL REFERENCES proof_sheets(proof_id),
                manuscript_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                paper TEXT NOT NULL,
                points TEXT NOT NULL,
                sample_paper_id TEXT,
                FOREIGN KEY (manuscript_id, revision)
                    REFERENCES draft_revisions (manuscript_id, revision)
            )
        ''')
        columns = {row[1] for row in db.execute('PRAGMA table_info(frozen_editions)')}
        if 'sample_paper_id' not in columns:
            db.execute('ALTER TABLE frozen_editions ADD COLUMN sample_paper_id TEXT')
        db.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS frozen_editions_sample_paper
            ON frozen_editions (sample_paper_id) WHERE sample_paper_id IS NOT NULL
        ''')

    def insert(self, proof, sample_paper_id=None):
        cursor = self.db.execute('''
            INSERT INTO frozen_editions
                (proof_id, manuscript_id, revision, paper, points, sample_paper_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (proof.proof_id, proof.manuscript_id, proof.revision,
              json.dumps(asdict(proof.paper)), json.dumps(proof.points), sample_paper_id))
        return FrozenEdition(cursor.lastrowid, proof.proof_id, proof.manuscript_id,
                             proof.revision, proof.paper, proof.points, sample_paper_id)

    def get(self, edition_id):
        row = self.db.execute('''
            SELECT edition_id, proof_id, manuscript_id, revision, paper, points, sample_paper_id
            FROM frozen_editions WHERE edition_id = ?
        ''', (str(edition_id),)).fetchone()
        if row is None:
            raise UnknownEdition('edition not found')
        number, proof_id, manuscript_id, revision, paper, points, sample_paper_id = row
        return FrozenEdition(number, proof_id, manuscript_id, revision,
                             decode_paper_spec(json.loads(paper)),
                             tuple(map(tuple, json.loads(points))), sample_paper_id)

    def sample_for(self, paper_id):
        row = self.db.execute('''
            SELECT edition_id FROM frozen_editions WHERE sample_paper_id = ?
        ''', (paper_id,)).fetchone()
        return None if row is None else row[0]

    def designated_papers(self):
        rows = self.db.execute('''
            SELECT sample_paper_id FROM frozen_editions
            WHERE sample_paper_id IS NOT NULL
        ''').fetchall()
        return frozenset(row[0] for row in rows)
