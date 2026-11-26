import json
from dataclasses import asdict, dataclass
from itertools import groupby

from draft.paper import PaperSpec, decode_paper_spec
from draft.patterns import PatternCatalog
from draft.revisions import RevisionStore
from proof.bounds import require_in_bounds
from proof.layout import place_cells
from proof.orientation import project_point


class UnknownRevision(LookupError):
    pass


@dataclass(frozen=True)
class CellOccurrence:
    cell_id: str
    occurrence: int
    points: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ProofSheet:
    proof_id: int
    manuscript_id: str
    revision: int
    paper: PaperSpec
    points: tuple[tuple[int, int], ...]
    occurrences: tuple[CellOccurrence, ...]


class ProofStore:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def install(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS proof_sheets (
                proof_id INTEGER PRIMARY KEY,
                manuscript_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                paper TEXT NOT NULL,
                points TEXT NOT NULL,
                occurrences TEXT NOT NULL,
                UNIQUE (manuscript_id, revision),
                FOREIGN KEY (manuscript_id, revision)
                    REFERENCES draft_revisions (manuscript_id, revision)
            )
        ''')

    def put(self, revision, points, occurrences):
        self.db.execute('''
            INSERT INTO proof_sheets (manuscript_id, revision, paper, points, occurrences)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (manuscript_id, revision) DO NOTHING
        ''', (revision.manuscript_id, revision.revision, json.dumps(asdict(revision.paper)),
              json.dumps(points), json.dumps([asdict(item) for item in occurrences])))
        proof_id, = self.db.execute('''
            SELECT proof_id FROM proof_sheets WHERE manuscript_id = ? AND revision = ?
        ''', (revision.manuscript_id, revision.revision)).fetchone()
        return self.get(proof_id)

    def get(self, proof_id):
        row = self.db.execute('''
            SELECT proof_id, manuscript_id, revision, paper, points, occurrences
            FROM proof_sheets WHERE proof_id = ?
        ''', (str(proof_id),)).fetchone()
        if row is None:
            return None
        number, manuscript, revision, paper, points, occurrences = row
        return ProofSheet(
            number, manuscript, revision, decode_paper_spec(json.loads(paper)),
            tuple(map(tuple, json.loads(points))),
            tuple(CellOccurrence(item['cell_id'], item['occurrence'],
                                 tuple(map(tuple, item['points'])))
                  for item in json.loads(occurrences)),
        )


def build_preview(db, manuscript_id, revision):
    with db:
        db.execute('BEGIN IMMEDIATE')
        draft = RevisionStore(db).get(manuscript_id, revision)
        if draft is None:
            raise UnknownRevision('manuscript revision not found')
        placed = place_cells(draft, PatternCatalog(db))
        projected = tuple(project_point(point, draft.paper) for point in placed)
        require_in_bounds(projected, draft.paper)
        occurrences = tuple(
            CellOccurrence(cell_id, occurrence, tuple(point.point for point in group))
            for (occurrence, cell_id), group in groupby(
                projected, key=lambda point: (point.occurrence, point.cell_id)
            )
        )
        points = tuple(sorted(point.point for point in projected))
        return ProofStore(db).put(draft, points, occurrences)
