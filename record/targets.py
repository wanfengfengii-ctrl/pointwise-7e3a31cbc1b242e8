class InvalidTarget(ValueError):
    pass


def decode_target_quantity(value):
    if type(value) is not int or value <= 0:
        raise InvalidTarget('target must be a positive integer')
    return value


class TargetStore:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def install(db):
        # Decimal text preserves the full range of integer targets accepted by JSON.
        db.execute('''
            CREATE TABLE IF NOT EXISTS edition_targets (
                edition_id INTEGER PRIMARY KEY REFERENCES frozen_editions(edition_id),
                quantity TEXT NOT NULL
            )
        ''')

    def set_initial(self, edition_id, quantity):
        self.db.execute('INSERT INTO edition_targets (edition_id, quantity) VALUES (?, ?)',
                        (edition_id, str(decode_target_quantity(quantity))))

    def get(self, edition_id):
        row = self.db.execute('SELECT quantity FROM edition_targets WHERE edition_id = ?',
                              (edition_id,)).fetchone()
        if row is None:
            raise RuntimeError(f'edition {edition_id} has no production target')
        return int(row[0])
