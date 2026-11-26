class RequestConflict(Exception):
    """A request number already binds different parameters."""


class UnknownPhysicalPaper(LookupError):
    """The press does not know the requested physical paper."""


class PaperConflict(Exception):
    """A physical paper is already pressed or reserved for another trial."""


class TrialNotAllowed(Exception):
    """The edition or the supplied paper cannot be used for a trial."""


class UnknownTrial(LookupError):
    """No trial request is registered under this number."""


class EditionNotReleased(Exception):
    """A trial edition cannot produce formal pieces before release."""


class SamplePaperReserved(Exception):
    """A designated sample paper cannot serve as a formal piece."""


class ReleaseConflict(Exception):
    """A release request contradicts the registered trial or release record."""
