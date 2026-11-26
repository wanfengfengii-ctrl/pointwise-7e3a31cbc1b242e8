from dataclasses import dataclass

from press.receipts import Receipt


@dataclass(frozen=True)
class CompletionTotals:
    target: int
    completed: int
    shortfall: int


def summarize_completion(target: int, receipts: tuple[Receipt, ...]):
    completed = len(receipts)
    return CompletionTotals(target, completed, max(target - completed, 0))
