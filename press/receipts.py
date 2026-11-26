from dataclasses import dataclass


class UnknownReceipt(LookupError):
    pass


@dataclass(frozen=True)
class Receipt:
    request_id: str
    edition_id: int
    paper_id: str
    press_no: int
    manuscript_id: str
    revision: int
    proof_id: int


class ReceiptStore:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def install(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS ordinary_receipts (
                request_id TEXT PRIMARY KEY,
                edition_id INTEGER NOT NULL REFERENCES frozen_editions(edition_id),
                paper_id TEXT NOT NULL,
                press_no INTEGER NOT NULL UNIQUE CHECK (press_no > 0),
                manuscript_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                proof_id INTEGER NOT NULL REFERENCES proof_sheets(proof_id),
                FOREIGN KEY (manuscript_id, revision)
                    REFERENCES draft_revisions (manuscript_id, revision)
            )
        ''')
        db.execute('''
            CREATE INDEX IF NOT EXISTS ordinary_receipts_by_edition
            ON ordinary_receipts (edition_id, press_no)
        ''')

    def save(self, receipt):
        self.db.execute('''
            INSERT INTO ordinary_receipts
                (request_id, edition_id, paper_id, press_no, manuscript_id, revision, proof_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (receipt.request_id, receipt.edition_id, receipt.paper_id, receipt.press_no,
              receipt.manuscript_id, receipt.revision, receipt.proof_id))

    def find(self, request_id):
        row = self.db.execute('''
            SELECT request_id, edition_id, paper_id, press_no, manuscript_id, revision, proof_id
            FROM ordinary_receipts WHERE request_id = ?
        ''', (request_id,)).fetchone()
        return None if row is None else Receipt(*row)

    def list_for_edition(self, edition_id):
        rows = self.db.execute('''
            SELECT request_id, edition_id, paper_id, press_no, manuscript_id, revision, proof_id
            FROM ordinary_receipts WHERE edition_id = ?
        ''', (edition_id,)).fetchall()
        return tuple(Receipt(*row) for row in rows)


def read_receipt(db, request_id):
    receipt = ReceiptStore(db).find(request_id)
    if receipt is None:
        raise UnknownReceipt('confirmed receipt not found')
    return receipt
