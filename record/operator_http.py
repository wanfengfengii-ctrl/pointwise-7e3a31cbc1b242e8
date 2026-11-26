import argparse
import json
import logging
import sqlite3
from contextlib import closing
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from draft.bootstrap import initialize_draft
from draft.edits import InvalidEdit, StaleRevision, edit_manuscript
from draft.patterns import require_identifier
from edition.editions import EditionStore, UnknownEdition
from edition.publication import UnknownProof, publish_edition
from edition.readback import read_edition
from press.device import DeviceNoReply, DeviceRefusal, PressDevice
from press.mechanics import MechanicalPress
from press.production import RequestConflict, print_card
from press.receipts import ReceiptStore, UnknownReceipt, read_receipt
from press.stock import WrongSheet
from proof.bounds import OutsidePrintableArea
from proof.sheets import ProofStore, UnknownRevision, build_preview
from record.lookup import edition_report
from record.targets import InvalidTarget, TargetStore


DEFAULT_SEED = Path(__file__).resolve().parents[1] / 'samples' / 'workshop.json'
MAX_BODY = 1024 * 1024


class BadRequest(ValueError):
    pass


class UnknownRoute(LookupError):
    pass


ERROR_RESPONSES = {
    BadRequest: (422, 'invalid_request'),
    InvalidEdit: (422, 'invalid_edit'),
    InvalidTarget: (422, 'invalid_target'),
    UnknownRevision: (404, 'unknown_revision'),
    UnknownProof: (404, 'unknown_proof'),
    UnknownEdition: (404, 'unknown_edition'),
    UnknownReceipt: (404, 'unknown_receipt'),
    UnknownRoute: (404, 'unknown_route'),
    WrongSheet: (409, 'wrong_sheet'),
    RequestConflict: (409, 'request_conflict'),
    DeviceRefusal: (503, 'device_refusal'),
    DeviceNoReply: (503, 'device_no_reply'),
}


def read_seed(path=DEFAULT_SEED):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _business_connection(path):
    db = sqlite3.connect(path, timeout=10)
    db.execute('PRAGMA foreign_keys = ON')
    return db


def _positive_int(value, name):
    if type(value) is not int or value <= 0:
        raise BadRequest(f'{name} must be a positive integer')
    return value


def _identifier(value, name):
    try:
        return require_identifier(value)
    except ValueError as exc:
        raise BadRequest(f'{name} must be a nonempty identifier without NUL') from exc


def _edition_number(segment):
    if not segment.isascii() or not segment.isdecimal():
        raise UnknownEdition('edition not found')
    return segment.lstrip('0') or '0'


class WorkshopHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._handle(self._get)

    def do_POST(self):
        self._handle(self._post)

    def log_message(self, format, *args):
        logging.getLogger(__name__).info(format, *args)

    def _handle(self, route):
        try:
            parts = self._path_parts()
            with closing(_business_connection(self.server.business_path)) as db:
                data = route(db, parts)
        except StaleRevision as exc:
            self._send_json(409, {'error': 'stale_revision', 'message': str(exc),
                                  'current_revision': exc.current_revision})
        except OutsidePrintableArea as exc:
            self._send_json(422, {'error': 'outside_printable_area', 'message': str(exc),
                                  'violations': [asdict(point) for point in exc.violations]})
        except tuple(ERROR_RESPONSES) as exc:
            status, code = ERROR_RESPONSES[type(exc)]
            self._send_json(status, {'error': code, 'message': str(exc)})
        else:
            self._send_json(200, data)

    def _path_parts(self):
        try:
            path = urlsplit(self.path).path
            return [unquote(segment, errors='strict') for segment in path.split('/')[1:]]
        except ValueError as exc:
            raise BadRequest('invalid request path') from exc

    def _read_json(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError('invalid length')
            body = self.rfile.read(length).decode('utf-8')
            value = json.loads(body)
        except (ValueError, RecursionError) as exc:
            raise BadRequest('expected a UTF-8 JSON object of at most 1 MiB') from exc
        if not isinstance(value, dict):
            raise BadRequest('expected a JSON object')
        return value

    def _send_json(self, status, value):
        payload = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _get(self, db, parts):
        match parts:
            case ['editions', edition]:
                return read_edition(db, _edition_number(edition))
            case ['editions', edition, 'report']:
                return asdict(edition_report(db, _edition_number(edition)))
            case ['receipts', request_id]:
                return asdict(read_receipt(db, _identifier(request_id, 'request_id')))
            case _:
                raise UnknownRoute('endpoint not found')

    def _post(self, db, parts):
        match parts:
            case ['manuscripts', manuscript, 'edit']:
                body = self._read_json()
                result = edit_manuscript(db, manuscript, body.get('expected_revision'),
                                         body.get('cells'), body.get('paper'))
            case ['previews']:
                body = self._read_json()
                manuscript = _identifier(body.get('manuscript_id'), 'manuscript_id')
                revision = _positive_int(body.get('revision'), 'revision')
                result = build_preview(db, manuscript, revision)
            case ['editions']:
                body = self._read_json()
                proof_id = _positive_int(body.get('proof_id'), 'proof_id')
                result = publish_edition(db, proof_id, body.get('target'))
            case ['impressions']:
                body = self._read_json()
                request_id = _identifier(body.get('request_id'), 'request_id')
                edition = _positive_int(body.get('edition_id'), 'edition_id')
                paper_id = _identifier(body.get('paper_id'), 'paper_id')
                result = print_card(db, self.server.device, request_id, edition, paper_id)
            case _:
                raise UnknownRoute('endpoint not found')
        return asdict(result)


class WorkshopServer(ThreadingHTTPServer):
    def __init__(self, business_path, device, port):
        self.business_path = business_path
        self.device = device
        super().__init__(('127.0.0.1', port), WorkshopHandler)


def serve_workshop(business_path, device_path, seed, *, port=0):
    business_path = Path(business_path).resolve()
    device_path = Path(device_path).resolve()
    if business_path == device_path or (
        business_path.exists() and device_path.exists() and business_path.samefile(device_path)
    ):
        raise ValueError('business and press must use separate database files')
    with closing(_business_connection(business_path)) as db:
        initialize_draft(db, seed)
        with db:
            db.execute('BEGIN IMMEDIATE')
            ProofStore.install(db)
            EditionStore.install(db)
            TargetStore.install(db)
            ReceiptStore.install(db)
    stock = seed['device']
    mechanics = MechanicalPress(device_path, stock['papers'], stock['loaded'])
    return WorkshopServer(business_path, PressDevice(mechanics), port)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run the local tactile-card workshop HTTP service')
    parser.add_argument('--business', required=True, type=Path)
    parser.add_argument('--device', required=True, type=Path)
    parser.add_argument('--seed', type=Path, default=DEFAULT_SEED)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args(argv)
    with serve_workshop(args.business, args.device, read_seed(args.seed), port=args.port) as server:
        print(f'Listening on http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
