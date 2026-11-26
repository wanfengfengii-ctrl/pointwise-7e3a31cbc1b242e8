import json
from http.client import HTTPConnection


class WorkshopClient:
    def __init__(self, port):
        self.port = port

    def exchange(self, method, path, payload=None):
        connection = HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            if payload is None:
                connection.request(method, path)
            else:
                body = json.dumps(payload).encode('utf-8')
                connection.request(method, path, body, {'Content-Type': 'application/json'})
            reply = connection.getresponse()
            return reply.status, json.loads(reply.read())
        finally:
            connection.close()
