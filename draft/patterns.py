import json
from dataclasses import dataclass


@dataclass(frozen=True)
class CellPattern:
    cell_id: str
    points: tuple[tuple[int, int], ...]


def require_identifier(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('expected a nonempty identifier without NUL')
    value.encode('utf-8')
    return value


def decode_pattern(cell_id, value):
    require_identifier(cell_id)
    if not isinstance(value, list) or not value:
        raise ValueError(f'cell {cell_id} requires a nonempty point array')
    points = []
    for point in value:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError(f'cell {cell_id} has an invalid point')
        x, y = point
        if type(x) is not int or type(y) is not int or not (0 <= x < 2 and 0 <= y < 3):
            raise ValueError(f'cell {cell_id} has a point outside the two by three grid')
        points.append((x, y))
    if len(points) != len(set(points)):
        raise ValueError(f'cell {cell_id} contains duplicate points')
    return CellPattern(cell_id, tuple(sorted(points)))


class PatternCatalog:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def install(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS cell_patterns (
                cell_id TEXT PRIMARY KEY,
                points TEXT NOT NULL
            )
        ''')

    def get(self, cell_id):
        row = self.db.execute(
            'SELECT points FROM cell_patterns WHERE cell_id = ?', (cell_id,)
        ).fetchone()
        if row is None:
            return None
        return decode_pattern(cell_id, json.loads(row[0]))

    def seed(self, values):
        if self.db.execute('SELECT 1 FROM cell_patterns LIMIT 1').fetchone():
            return
        if not isinstance(values, dict) or not values:
            raise ValueError('the cell catalog cannot be empty')
        patterns = [decode_pattern(cell_id, points) for cell_id, points in values.items()]
        self.db.executemany(
            'INSERT INTO cell_patterns (cell_id, points) VALUES (?, ?)',
            [(pattern.cell_id, json.dumps(pattern.points)) for pattern in patterns],
        )

    def require_cells(self, values):
        if not isinstance(values, list) or not values:
            raise ValueError('cells must be a nonempty array')
        cells = tuple(require_identifier(value) for value in values)
        for cell_id in dict.fromkeys(cells):
            if self.get(cell_id) is None:
                raise ValueError(f'unknown cell {cell_id}')
        return cells
