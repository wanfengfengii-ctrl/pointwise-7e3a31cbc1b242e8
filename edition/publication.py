from edition.editions import EditionStore
from proof.sheets import ProofStore
from record.targets import TargetStore, decode_target_quantity


class UnknownProof(LookupError):
    pass


def publish_edition(db, proof_id, target):
    quantity = decode_target_quantity(target)
    with db:
        db.execute('BEGIN IMMEDIATE')
        proof = ProofStore(db).get(proof_id)
        if proof is None:
            raise UnknownProof('proof sheet not found')
        edition = EditionStore(db).insert(proof)
        TargetStore(db).set_initial(edition.edition_id, quantity)
    return edition
