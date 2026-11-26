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
                FOREIGN KEY (manuscript_id, revision)
                    REFERENCES draft_revisions (manuscript_id, revision)
            )
        ''')

    def insert(self, proof):
        cursor = self.db.execute('''
            INSERT INTO frozen_editions (proof_id, manuscript_id, revision, paper, points)
            VALUES (?, ?, ?, ?, ?)
        ''', (proof.proof_id, proof.manuscript_id, proof.revision,
              json.dumps(asdict(proof.paper)), json.dumps(proof.points)))
        return FrozenEdition(cursor.lastrowid, proof.proof_id, proof.manuscript_id,
                             proof.revision, proof.paper, proof.points)

    def get(self, edition_id):
        row = self.db.execute('''
            SELECT edition_id, proof_id, manuscript_id, revision, paper, points
            FROM frozen_editions WHERE edition_id = ?
        ''', (str(edition_id),)).fetchone()
        if row is None:
            raise UnknownEdition('edition not found')
        number, proof_id, manuscript_id, revision, paper, points = row
        return FrozenEdition(number, proof_id, manuscript_id, revision,
                             decode_paper_spec(json.loads(paper)),
                             tuple(map(tuple, json.loads(points))))
