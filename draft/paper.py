from dataclasses import dataclass


@dataclass(frozen=True)
class PaperSpec:
    width: int
    left: int
    right: int
    direction: str

    def __post_init__(self):
        if any(type(value) is not int for value in (self.width, self.left, self.right)):
            raise ValueError('width and margins must be integers')
        if self.width <= 0 or self.left < 0 or self.right < 0:
            raise ValueError('width must be positive and margins nonnegative')
        if self.first_printable_column >= self.end_printable_column:
            raise ValueError('margins must leave at least one printable column')
        if self.direction not in ('forward', 'reverse'):
            raise ValueError('direction must be forward or reverse')

    @property
    def first_printable_column(self):
        return self.left

    @property
    def end_printable_column(self):
        return self.width - self.right


def decode_paper_spec(value):
    if not isinstance(value, dict):
        raise ValueError('paper must be an object')
    required = ('width', 'left', 'right', 'direction')
    if any(key not in value for key in required):
        raise ValueError('paper requires width, left, right and direction')
    return PaperSpec(*(value[key] for key in required))
