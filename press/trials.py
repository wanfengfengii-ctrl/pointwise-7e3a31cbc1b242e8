import threading
from dataclasses import dataclass

from edition.dispatch import PressOrder
from edition.editions import EditionStore
from press.device import DeviceNoReply, DeviceRefusal, PressDevice
from press.errors import (
    PaperConflict,
    ReleaseConflict,
    RequestConflict,
    TrialNotAllowed,
    UnknownPhysicalPaper,
    UnknownTrial,
)
from press.mechanics import EvidenceUnavailable
from press.outcomes import Pending
from press.stock import WrongSheet, require_loaded_paper

# Trials and ordinary strikes share one physical press; serialise them inside
# this process so a request number never strikes twice and at most one trial is
# unresolved at a time.
_PRESS_GUARD = threading.Lock()


def press_guard():
    return _PRESS_GUARD


@dataclass(frozen=True)
class TrialRecord:
    request_id: str
    edition_id: int
    paper_id: str
    state: str
    press_no: int | None
    attempted: bool


@dataclass(frozen=True)
class TrialReceipt:
    request_id: str
    edition_id: int
    paper_id: str
    press_no: int


@dataclass(frozen=True)
class ReleaseResult:
    edition_id: int
    receipt: TrialReceipt


@dataclass(frozen=True)
class _Decision:
    kind: str                                   # 'return' or 'press'
    result: object = None
    exc: BaseException | None = None
    edition: object = None
    record: TrialRecord | None = None
    request_id: str | None = None


def _pending(request_id):
    return Pending({'request_id': request_id, 'status': 'pending'})


class TrialStore:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def install(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS trial_requests (
                request_id TEXT PRIMARY KEY,
                edition_id INTEGER NOT NULL REFERENCES frozen_editions(edition_id),
                paper_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('pending', 'settled')),
                press_no INTEGER UNIQUE,
                attempted INTEGER NOT NULL DEFAULT 0 CHECK (attempted IN (0, 1)),
                CHECK ((state = 'pending' AND press_no IS NULL)
                       OR (state = 'settled' AND press_no IS NOT NULL))
            )
        ''')
        db.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS trial_requests_per_edition
            ON trial_requests (edition_id)
        ''')

    def find(self, request_id):
        row = self.db.execute('''
            SELECT request_id, edition_id, paper_id, state, press_no, attempted
            FROM trial_requests WHERE request_id = ?
        ''', (request_id,)).fetchone()
        return None if row is None else TrialRecord(*row)

    def find_for_edition(self, edition_id):
        row = self.db.execute('''
            SELECT request_id, edition_id, paper_id, state, press_no, attempted
            FROM trial_requests WHERE edition_id = ?
        ''', (edition_id,)).fetchone()
        return None if row is None else TrialRecord(*row)

    def has_pending_elsewhere(self, edition_id):
        return self.db.execute('''
            SELECT 1 FROM trial_requests WHERE state = 'pending' AND edition_id != ?
        ''', (edition_id,)).fetchone() is not None

    def register_pending(self, request_id, edition_id, paper_id, attempted):
        self.db.execute('''
            INSERT INTO trial_requests
                (request_id, edition_id, paper_id, state, press_no, attempted)
            VALUES (?, ?, ?, 'pending', NULL, ?)
        ''', (request_id, edition_id, paper_id, 1 if attempted else 0))

    def remove(self, request_id):
        self.db.execute('DELETE FROM trial_requests WHERE request_id = ?', (request_id,))

    def mark_attempted(self, request_id):
        self.db.execute('UPDATE trial_requests SET attempted = 1 WHERE request_id = ?',
                        (request_id,))

    def settle(self, request_id, press_no):
        self.db.execute('''
            UPDATE trial_requests SET state = 'settled', press_no = ?, attempted = 1
            WHERE request_id = ?
        ''', (press_no, request_id))

    def receipt(self, record):
        if record.state != 'settled' or record.press_no is None:
            return None
        return TrialReceipt(record.request_id, record.edition_id, record.paper_id,
                            record.press_no)


class ReleaseStore:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def install(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS edition_releases (
                edition_id INTEGER PRIMARY KEY REFERENCES frozen_editions(edition_id),
                request_id TEXT NOT NULL UNIQUE REFERENCES trial_requests(request_id)
            )
        ''')

    def find_for_edition(self, edition_id):
        row = self.db.execute('SELECT request_id FROM edition_releases WHERE edition_id = ?',
                              (edition_id,)).fetchone()
        return None if row is None else row[0]

    def save(self, edition_id, request_id):
        self.db.execute('INSERT INTO edition_releases (edition_id, request_id) VALUES (?, ?)',
                        (edition_id, request_id))


def is_released(db, edition_id):
    return ReleaseStore(db).find_for_edition(edition_id) is not None


def _matching_strike(observation, points):
    for strike in observation.strikes:
        if strike.points == points:
            return strike
    return None


def trial_holds_press(db, mechanics):
    """Whether an open trial's mounted paper still awaits this trial's strike.

    Only then must ordinary work on a different paper be deferred: the trial
    paper is mounted and unpressed, so any other strike would change the sheet
    the trial needs. Once its paper is pressed, or another sheet is mounted,
    ordinary orders may proceed.
    """
    loaded = mechanics.inspect_loaded()
    for (paper_id,) in db.execute(
            "SELECT paper_id FROM trial_requests WHERE state = 'pending'"):
        if loaded != paper_id:
            continue
        try:
            observation = mechanics.observe_paper(paper_id)
        except EvidenceUnavailable:
            return True
        if not observation.strikes:
            return True
    return False


def submit_trial(db, device: PressDevice, request_id, edition_id, paper_id):
    with _PRESS_GUARD:
        db.execute('BEGIN IMMEDIATE')
        try:
            decision = _decide(db, device.mechanics, request_id, edition_id, paper_id)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        if decision.exc is not None:
            raise decision.exc
        if decision.kind == 'return':
            return decision.result
        return _perform(db, device, decision)


def _decide(db, mechanics, request_id, edition_id, paper_id):
    edition = EditionStore(db).get(edition_id)
    trials = TrialStore(db)
    record = trials.find(request_id)
    if record is not None:
        # A registered number is bound to its edition and paper; report that
        # conflict first even if the new paper is not any edition's sample.
        if (record.edition_id, record.paper_id) != (edition_id, paper_id):
            raise RequestConflict('trial request has different parameters')
        if record.state == 'settled':
            return _Decision('return', result=trials.receipt(record))
        return _resume(mechanics, trials, record, edition)

    if not mechanics.knows_paper(paper_id):
        raise UnknownPhysicalPaper('the press does not know this paper')
    if edition.sample_paper_id is None or paper_id != edition.sample_paper_id:
        raise TrialNotAllowed('paper is not the sample designated for this edition')

    if trials.find_for_edition(edition_id) is not None:
        raise RequestConflict('edition already has a trial request')
    if trials.has_pending_elsewhere(edition_id):
        # Not accepted yet: only one unresolved trial at a time. The same
        # original request may be delivered again once the other settles.
        return _Decision('return', result=_pending(request_id))

    try:
        observation = mechanics.observe_paper(paper_id)
    except EvidenceUnavailable:
        trials.register_pending(request_id, edition_id, paper_id, attempted=False)
        return _Decision('return', result=_pending(request_id))
    if observation.strikes:
        raise PaperConflict('sample paper is no longer blank')

    try:
        require_loaded_paper(mechanics, paper_id)
    except WrongSheet as exc:
        return _Decision('return', exc=exc)

    return _Decision('press', edition=edition, request_id=request_id)


def _resume(mechanics, trials, record, edition):
    try:
        observation = mechanics.observe_paper(record.paper_id)
    except EvidenceUnavailable:
        return _Decision('return', result=_pending(record.request_id))

    if observation.strikes:
        if not record.attempted:
            # This trial never struck, yet the paper is no longer blank, so it
            # can never be proven. Drop the registration so the single open
            # slot is not wedged, and report the physical conflict.
            trials.remove(record.request_id)
            return _Decision(
                'return', exc=PaperConflict('sample paper was pressed before this trial'))
        strike = _matching_strike(observation, edition.points)
        if strike is None:
            trials.remove(record.request_id)
            return _Decision(
                'return', exc=PaperConflict('sample paper carries a different pattern'))
        trials.settle(record.request_id, strike.press_no)
        return _Decision('return', result=trials.receipt(trials.find(record.request_id)))

    try:
        require_loaded_paper(mechanics, record.paper_id)
    except WrongSheet as exc:
        return _Decision('return', exc=exc)

    return _Decision('press', edition=edition, record=record)


def _perform(db, device, decision):
    # Record the attempt before the strike so a crash or lost reply between the
    # physical action and the receipt can still settle under the original
    # number without striking twice.
    request_id = _prepare_attempt(db, decision)
    try:
        acknowledgement = device.strike(PressOrder(decision.edition,
                                                   decision.edition.sample_paper_id))
    except DeviceNoReply:
        return _pending(request_id)
    except DeviceRefusal:
        if decision.record is None:
            _discard_attempt(db, request_id)
        raise
    except WrongSheet:
        if decision.record is None:
            _discard_attempt(db, request_id)
        raise
    _settle_attempt(db, request_id, acknowledgement.press_no)
    return TrialReceipt(request_id, decision.edition.edition_id,
                        acknowledgement.paper_id, acknowledgement.press_no)


def _prepare_attempt(db, decision):
    db.execute('BEGIN IMMEDIATE')
    try:
        trials = TrialStore(db)
        if decision.record is None:
            trials.register_pending(decision.request_id, decision.edition.edition_id,
                                    decision.edition.sample_paper_id, attempted=True)
            request_id = decision.request_id
        else:
            request_id = decision.record.request_id
            if not decision.record.attempted:
                trials.mark_attempted(request_id)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return request_id


def _discard_attempt(db, request_id):
    db.execute('BEGIN IMMEDIATE')
    try:
        TrialStore(db).remove(request_id)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _settle_attempt(db, request_id, press_no):
    db.execute('BEGIN IMMEDIATE')
    try:
        TrialStore(db).settle(request_id, press_no)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def read_trial(db, request_id):
    store = TrialStore(db)
    record = store.find(request_id)
    if record is None:
        raise UnknownTrial('trial request not found')
    receipt = store.receipt(record)
    return receipt if receipt is not None else _pending(request_id)


def release_edition(db, edition_id, request_id):
    with db:
        db.execute('BEGIN IMMEDIATE')
        edition = EditionStore(db).get(edition_id)
        if edition.sample_paper_id is None:
            raise ReleaseConflict('ordinary editions have no sample trial to release')
        trials = TrialStore(db)
        releases = ReleaseStore(db)

        existing = releases.find_for_edition(edition_id)
        if existing is not None:
            if existing != request_id:
                raise ReleaseConflict('edition is already released under another request')
            return ReleaseResult(edition_id, trials.receipt(trials.find(existing)))

        record = trials.find(request_id)
        if record is None:
            from press.receipts import ReceiptStore
            if ReceiptStore(db).find(request_id) is not None:
                raise ReleaseConflict('ordinary receipts cannot release a trial edition')
            raise UnknownTrial('trial request not found')
        if record.edition_id != edition_id or record.paper_id != edition.sample_paper_id:
            raise ReleaseConflict('trial request belongs to another edition or paper')
        if record.state != 'settled':
            return _pending(request_id)
        releases.save(edition_id, request_id)
        return ReleaseResult(edition_id, trials.receipt(record))
