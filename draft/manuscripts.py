class ManuscriptStore:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def install(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS manuscripts (
                manuscript_id TEXT PRIMARY KEY,
                current_revision INTEGER NOT NULL CHECK (current_revision > 0)
            )
        ''')

    def head(self, manuscript_id):
        row = self.db.execute(
            'SELECT current_revision FROM manuscripts WHERE manuscript_id = ?',
            (manuscript_id,),
        ).fetchone()
        return None if row is None else row[0]

    def create(self, manuscript_id):
        self.db.execute(
            'INSERT INTO manuscripts (manuscript_id, current_revision) VALUES (?, 1)',
            (manuscript_id,),
        )

    def advance(self, manuscript_id, expected_revision):
        cursor = self.db.execute('''
            UPDATE manuscripts SET current_revision = current_revision + 1
            WHERE manuscript_id = ? AND current_revision = ?
        ''', (manuscript_id, expected_revision))
        return cursor.rowcount == 1
