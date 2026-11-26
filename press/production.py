from edition.dispatch import dispatch_edition
from edition.editions import EditionStore
from press.device import PressDevice
from press.errors import EditionNotReleased, RequestConflict, SamplePaperReserved
from press.outcomes import Pending
from press.receipts import Receipt, ReceiptStore
from press.stock import require_loaded_paper
from press.trials import is_released, press_guard, trial_holds_press


def print_card(db, device: PressDevice, request_id, edition_id, paper_id):
    with press_guard(), db:
        db.execute('BEGIN IMMEDIATE')
        receipts = ReceiptStore(db)
        prior = receipts.find(request_id)
        if prior is not None:
            # A confirmed ordinary original stays readable and never strikes
            # again, whatever waits at the press.
            if (prior.edition_id, prior.paper_id) != (edition_id, paper_id):
                raise RequestConflict('confirmed request has different parameters')
            return prior

        order = dispatch_edition(db, edition_id, paper_id)
        edition = order.edition
        if paper_id in EditionStore(db).designated_papers():
            raise SamplePaperReserved('a designated sample paper cannot be a formal piece')
        if edition.sample_paper_id is not None and not is_released(db, edition.edition_id):
            raise EditionNotReleased('trial edition needs its release before formal cards')
        if trial_holds_press(db, device.mechanics):
            # The open trial's paper is mounted and awaiting its strike, so an
            # ordinary order on another paper waits without striking.
            return Pending({'status': 'pending'})

        require_loaded_paper(device.mechanics, order.expected_paper)
        acknowledgement = device.strike(order)
        receipt = Receipt(request_id, edition.edition_id, acknowledgement.paper_id,
                          acknowledgement.press_no, edition.manuscript_id, edition.revision,
                          edition.proof_id)
        receipts.save(receipt)
    return receipt
