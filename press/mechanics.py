import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass


class LoadedPaperChanged(Exception):
    pass


class PressBusy(Exception):
    pass


class UnknownPaper(LookupError):
    pass


class MechanicalRefusal(Exception):
    pass


class MechanicalNoReply(Exception):
    pass


class EvidenceUnavailable(Exception):
    pass


@dataclass(frozen=True)
class PhysicalStrike:
    paper_id: str
    press_no: int
    points: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class PaperObservation:
    paper_id: str
    points: tuple[tuple[int, int], ...]
    strikes: tuple[PhysicalStrike, ...]


def _require_owner(active, caller):
    if active != caller:
        raise PressBusy('mechanical ownership does not match the command')


def _require_paper(db, paper_id):
    row = db.execute('SELECT 1 FROM physical_papers WHERE paper_id = ?', (paper_id,)).fetchone()
    if row is None:
        raise UnknownPaper(f'unknown physical paper {paper_id}')


def _validated_grid(points):
    grid = tuple(tuple(point) for point in points)
    if not grid or any(len(point) != 2 or any(
        type(coordinate) is not int or coordinate < 0 for coordinate in point
    ) for point in grid):
        raise MechanicalRefusal('invalid physical point grid')
    if len(set(grid)) != len(grid):
        raise MechanicalRefusal('physical point grid contains duplicate points')
    return tuple(sorted(grid))


class MechanicalPress:
    def __init__(self, path, paper_ids=None, initial_paper=None):
        self.path = path
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS physical_papers (paper_id TEXT PRIMARY KEY)')
            db.execute('''
                CREATE TABLE IF NOT EXISTS physical_strikes (
                    press_no INTEGER PRIMARY KEY,
                    paper_id TEXT NOT NULL REFERENCES physical_papers(paper_id),
                    points TEXT NOT NULL
                )
            ''')
            db.execute('''
                CREATE INDEX IF NOT EXISTS strikes_per_paper
                ON physical_strikes (paper_id, press_no)
            ''')
            db.execute('''
                CREATE TABLE IF NOT EXISTS mechanical_state (
                    slot INTEGER PRIMARY KEY CHECK (slot = 1),
                    loaded TEXT REFERENCES physical_papers(paper_id),
                    owner TEXT,
                    next_loaded TEXT REFERENCES physical_papers(paper_id),
                    next_fault TEXT CHECK (next_fault IN ('refusal', 'before', 'after')),
                    evidence_available INTEGER NOT NULL DEFAULT 1
                        CHECK (evidence_available IN (0, 1))
                )
            ''')
            if db.execute('SELECT 1 FROM mechanical_state WHERE slot = 1').fetchone():
                return
            if not isinstance(paper_ids, (list, tuple)) or not paper_ids:
                raise ValueError('a new press requires a nonempty paper catalog')
            if any(not isinstance(paper, str) or not paper or '\x00' in paper
                   for paper in paper_ids) or len(set(paper_ids)) != len(paper_ids):
                raise ValueError('paper identifiers must be distinct nonempty strings without NUL')
            db.executemany('INSERT INTO physical_papers VALUES (?)', [(paper,) for paper in paper_ids])
            if initial_paper is not None:
                _require_paper(db, initial_paper)
            db.execute('INSERT INTO mechanical_state (slot, loaded) VALUES (1, ?)', (initial_paper,))

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA foreign_keys = ON')
        return db

    def _state(self, db):
        return db.execute('''
            SELECT loaded, owner, next_loaded, next_fault, evidence_available
            FROM mechanical_state WHERE slot = 1
        ''').fetchone()

    def load(self, paper_id, *, owner=None):
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            loaded, active, _, _, _ = self._state(db)
            _require_owner(active, owner)
            _require_paper(db, paper_id)
            if active is not None and paper_id != loaded:
                raise PressBusy('loaded paper is fixed by mechanical ownership')
            db.execute('UPDATE mechanical_state SET loaded = ? WHERE slot = 1', (paper_id,))

    def inspect_loaded(self):
        with closing(self._connect()) as db:
            return self._state(db)[0]

    def schedule_load(self, paper_id):
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            _require_owner(self._state(db)[1], None)
            _require_paper(db, paper_id)
            db.execute('UPDATE mechanical_state SET next_loaded = ? WHERE slot = 1', (paper_id,))

    def knows_paper(self, paper_id):
        with closing(self._connect()) as db:
            db.execute('BEGIN')
            return db.execute(
                'SELECT 1 FROM physical_papers WHERE paper_id = ?', (paper_id,)
            ).fetchone() is not None

    def observe_paper(self, paper_id):
        with closing(self._connect()) as db, db:
            db.execute('BEGIN')
            if not self._state(db)[4]:
                raise EvidenceUnavailable('paper observation is temporarily unavailable')
            _require_paper(db, paper_id)
            rows = db.execute('''
                SELECT press_no, points FROM physical_strikes
                WHERE paper_id = ? ORDER BY press_no
            ''', (paper_id,)).fetchall()
        strikes = tuple(
            PhysicalStrike(paper_id, number, tuple(map(tuple, json.loads(points))))
            for number, points in rows
        )
        surface = tuple(sorted({point for strike in strikes for point in strike.points}))
        return PaperObservation(paper_id, surface, strikes)

    def press_count(self):
        with closing(self._connect()) as db, db:
            db.execute('BEGIN')
            if not self._state(db)[4]:
                raise EvidenceUnavailable('press count is temporarily unavailable')
            return db.execute('SELECT COALESCE(MAX(press_no), 0) FROM physical_strikes').fetchone()[0]

    def claim(self, owner, expected_paper):
        if not isinstance(owner, str) or not owner or '\x00' in owner:
            raise ValueError('mechanical ownership requires a nonempty identifier without NUL')
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            loaded, active, queued, _, _ = self._state(db)
            if active is not None:
                _require_owner(active, owner)
            if loaded != expected_paper or loaded is None:
                raise LoadedPaperChanged('expected paper is not loaded')
            if queued is not None:
                raise PressBusy('a scheduled paper change has not yet run')
            db.execute('UPDATE mechanical_state SET owner = ? WHERE slot = 1', (owner,))

    def release(self, owner):
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            active = self._state(db)[1]
            if active is not None:
                _require_owner(active, owner)
                db.execute('UPDATE mechanical_state SET owner = NULL WHERE slot = 1')

    def _arm_failure(self, fault):
        with closing(self._connect()) as db, db:
            db.execute('UPDATE mechanical_state SET next_fault = ? WHERE slot = 1', (fault,))

    def arm_reply_loss(self, phase):
        if phase not in ('before', 'after'):
            raise ValueError('reply loss phase must be before or after')
        self._arm_failure(phase)

    def arm_refusal(self):
        self._arm_failure('refusal')

    def set_evidence_available(self, available):
        if type(available) is not bool:
            raise ValueError('evidence availability requires a boolean')
        with closing(self._connect()) as db, db:
            db.execute('UPDATE mechanical_state SET evidence_available = ? WHERE slot = 1',
                       (available,))

    def strike(self, expected_paper, points, *, owner=None):
        grid = _validated_grid(points)
        result = None
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            loaded, active, queued, fault, _ = self._state(db)
            _require_owner(active, owner)
            if queued is not None:
                loaded = queued
                db.execute('''
                    UPDATE mechanical_state SET loaded = ?, next_loaded = NULL WHERE slot = 1
                ''', (loaded,))
            paper_matches = loaded is not None and loaded == expected_paper
            if paper_matches:
                db.execute('UPDATE mechanical_state SET next_fault = NULL WHERE slot = 1')
                if fault not in ('refusal', 'before'):
                    cursor = db.execute('''
                        INSERT INTO physical_strikes (paper_id, points) VALUES (?, ?)
                    ''', (loaded, json.dumps(grid)))
                    result = PhysicalStrike(loaded, cursor.lastrowid, grid)

        # A feed change or actual impression has committed before the caller sees an outcome.
        if not paper_matches:
            raise LoadedPaperChanged('paper changed before the physical strike')
        if fault == 'refusal':
            raise MechanicalRefusal('press refused the strike')
        if fault in ('before', 'after'):
            raise MechanicalNoReply('press reply was lost')
        return result
