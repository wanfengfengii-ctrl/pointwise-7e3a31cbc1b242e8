from press.mechanics import MechanicalPress


class WrongSheet(Exception):
    pass


def require_loaded_paper(mechanics: MechanicalPress, expected_paper):
    loaded = mechanics.inspect_loaded()
    if loaded is None or loaded != expected_paper:
        raise WrongSheet('expected paper is not loaded')
    return loaded
