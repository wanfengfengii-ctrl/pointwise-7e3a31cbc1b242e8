from dataclasses import dataclass

from edition.dispatch import PressOrder
from press.mechanics import (
    LoadedPaperChanged,
    MechanicalNoReply,
    MechanicalPress,
    MechanicalRefusal,
    PressBusy,
)
from press.stock import WrongSheet


@dataclass(frozen=True)
class DeviceAcknowledgement:
    paper_id: str
    press_no: int


class DeviceRefusal(Exception):
    pass


class DeviceNoReply(Exception):
    pass


class PressDevice:
    def __init__(self, mechanics: MechanicalPress):
        self.mechanics = mechanics

    def strike(self, order: PressOrder):
        edition = order.edition
        paper = edition.paper
        if not edition.points or any(
            not (paper.first_printable_column <= x < paper.end_printable_column and 0 <= y < 3)
            for x, y in edition.points
        ):
            raise DeviceRefusal('frozen points do not fit the printable grid')
        try:
            strike = self.mechanics.strike(order.expected_paper, edition.points)
        except LoadedPaperChanged as exc:
            raise WrongSheet(str(exc)) from exc
        except (MechanicalRefusal, PressBusy) as exc:
            raise DeviceRefusal(str(exc)) from exc
        except MechanicalNoReply as exc:
            raise DeviceNoReply(str(exc)) from exc
        return DeviceAcknowledgement(strike.paper_id, strike.press_no)
