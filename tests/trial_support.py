from tests.support import WorkshopCase


SAMPLE_POINTS = [[1, 0], [2, 2], [4, 1], [5, 0]]


class TrialSupport(WorkshopCase):
    def publish_pair(self):
        """Freeze a trial edition E on A and an ordinary edition F, same proof."""
        proof = self.rig.preview()
        trial = self.rig.publish_sample(proof['proof_id'], 'A', target=1)
        ordinary = self.rig.publish(proof['proof_id'], target=1)
        return trial, ordinary

    def trial(self, request_id, edition, paper_id, *, status=200):
        return self.rig.request('POST', '/proofs',
                                {'request_id': request_id, 'edition_id': edition,
                                 'paper_id': paper_id}, expected=status)

    def read_trial(self, request_id, *, status=200):
        from urllib.parse import quote
        return self.rig.request('GET', '/proofs/' + quote(request_id, safe=''),
                                expected=status)

    def release(self, edition, request_id, *, status=200):
        return self.rig.request('POST', f'/editions/{edition}/release',
                                {'request_id': request_id}, expected=status)
