from edition.editions import EditionStore, edition_snapshot
from press.errors import PaperConflict, UnknownPhysicalPaper
from press.mechanics import EvidenceUnavailable
from press.outcomes import Pending
from proof.sheets import ProofStore
from record.targets import TargetStore, decode_target_quantity


class UnknownProof(LookupError):
    pass


def _sample_is_usable(editions, mechanics, paper_id):
    if not mechanics.knows_paper(paper_id):
        raise UnknownPhysicalPaper('the press does not know this paper')
    if editions.sample_for(paper_id) is not None:
        raise PaperConflict('paper is already the sample for another edition')
    try:
        observation = mechanics.observe_paper(paper_id)
    except EvidenceUnavailable:
        return False
    if observation.strikes:
        raise PaperConflict('sample paper has already been pressed')
    return True


def publish_edition(db, proof_id, target, sample_paper_id=None, mechanics=None):
    quantity = decode_target_quantity(target)
    with db:
        db.execute('BEGIN IMMEDIATE')
        proof = ProofStore(db).get(proof_id)
        if proof is None:
            raise UnknownProof('proof sheet not found')
        editions = EditionStore(db)
        if sample_paper_id is not None:
            if not _sample_is_usable(editions, mechanics, sample_paper_id):
                # Blankness cannot be confirmed while evidence is unreadable;
                # issue no edition this round.
                return Pending({'status': 'pending'})
        edition = editions.insert(proof, sample_paper_id)
        TargetStore(db).set_initial(edition.edition_id, quantity)
    return edition_snapshot(edition)
