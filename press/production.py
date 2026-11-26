from edition.dispatch import dispatch_edition
from press.device import PressDevice
from press.receipts import Receipt, ReceiptStore
from press.stock import require_loaded_paper


class RequestConflict(Exception):
    pass


def print_card(db, device: PressDevice, request_id, edition_id, paper_id):
    with db:
        db.execute('BEGIN IMMEDIATE')
        receipts = ReceiptStore(db)
        prior = receipts.find(request_id)
        if prior is not None:
            if (prior.edition_id, prior.paper_id) != (edition_id, paper_id):
                raise RequestConflict('confirmed request has different parameters')
            return prior

        order = dispatch_edition(db, edition_id, paper_id)
        require_loaded_paper(device.mechanics, order.expected_paper)
        acknowledgement = device.strike(order)
        edition = order.edition
        receipt = Receipt(request_id, edition.edition_id, acknowledgement.paper_id,
                          acknowledgement.press_no, edition.manuscript_id, edition.revision,
                          edition.proof_id)
        receipts.save(receipt)
    return receipt
