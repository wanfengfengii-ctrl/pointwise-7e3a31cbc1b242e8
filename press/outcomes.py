from dataclasses import dataclass


@dataclass(frozen=True)
class Pending:
    """A request seen but not settled yet; the HTTP entry answers with 202."""

    payload: dict
