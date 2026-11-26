import json
import sqlite3
import threading
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from press.mechanics import MechanicalPress
from record.operator_http import read_seed, serve_workshop
from tests.http_client import WorkshopClient


def paper(width=9, left=1, right=2, direction='forward'):
    return {'width': width, 'left': left, 'right': right, 'direction': direction}


def edit_payload(expected, cells, spec):
    return {'expected_revision': expected, 'cells': cells, 'paper': spec}


def impression_payload(request_id, edition, paper_id):
    return {'request_id': request_id, 'edition_id': edition, 'paper_id': paper_id}


def receipt_path(request_id):
    return '/receipts/' + quote(request_id, safe='')


def require_equal(actual, expected):
    if actual != expected:
        raise AssertionError(f'expected {expected!r}, got {actual!r}')


def scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual,
             code_paths, oracle):
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id,
        'input': inputs,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': code_paths,
        'oracle': oracle,
    }, ensure_ascii=False, separators=(',', ':')), flush=True)


class WorkshopRig:
    def __init__(self, directory, seed=None):
        root = Path(directory)
        self.business_path = root / 'workshop.sqlite'
        self.device_path = root / 'press.sqlite'
        self.seed = read_seed() if seed is None else seed
        self.server = None
        self.thread = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def start(self):
        self.server = serve_workshop(self.business_path, self.device_path, self.seed)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        try:
            self.thread.start()
        except BaseException:
            self.server.server_close()
            self.server = None
            self.thread = None
            raise
        self.client = WorkshopClient(self.server.server_port)

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.thread.join()
            self.server.server_close()
            self.server = None
            self.thread = None

    def restart(self):
        self.close()
        self.start()

    @property
    def press(self):
        return MechanicalPress(self.device_path)

    def query(self, sql):
        # Read separately so regressions can check effects that have no public list endpoint.
        with closing(sqlite3.connect(self.business_path)) as db:
            return db.execute(sql).fetchall()

    def request(self, method, path, payload=None, *, expected=200):
        status, value = self.client.exchange(method, path, payload)
        if status != expected:
            raise AssertionError(f'{method} {path}: expected {expected}, got {status}: {value}')
        return value

    def edit(self, expected_revision, cells, spec, *, status=200):
        return self.request('POST', '/manuscripts/hall/edit',
                            edit_payload(expected_revision, cells, spec), expected=status)

    def preview(self, revision=1, *, status=200):
        return self.request('POST', '/previews', {'manuscript_id': 'hall', 'revision': revision},
                            expected=status)

    def publish(self, proof_id, target=2, *, status=200):
        return self.request('POST', '/editions', {'proof_id': proof_id, 'target': target},
                            expected=status)

    def publish_sample(self, proof_id, sample_paper_id, target=1, *, status=200):
        return self.request('POST', '/editions',
                            {'proof_id': proof_id, 'target': target,
                             'sample_paper_id': sample_paper_id}, expected=status)

    def edition(self, edition, *, status=200):
        return self.request('GET', f'/editions/{edition}', expected=status)

    def print_card(self, request_id, edition, paper_id, *, status=200):
        return self.request('POST', '/impressions', impression_payload(request_id, edition, paper_id),
                            expected=status)

    def receipt(self, request_id, *, status=200):
        return self.request('GET', receipt_path(request_id), expected=status)

    def report(self, edition, *, status=200):
        return self.request('GET', f'/editions/{edition}/report', expected=status)


class WorkshopCase(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory(prefix='tactile-workshop-'))
        self.rig = self.enterContext(WorkshopRig(directory))

    def publish_initial(self, target=2):
        proof = self.rig.preview()
        return self.rig.publish(proof['proof_id'], target)
