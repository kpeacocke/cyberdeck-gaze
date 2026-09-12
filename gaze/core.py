"""Hardware-independent tracking and attention policy."""
from dataclasses import dataclass
import math

@dataclass
class Track:
    id: int
    label: str
    score: float
    box: tuple
    seen: float
    name: str = ""

class Attention:
    def __init__(self, config):
        self.config = config
        self.tracks = {}
        self.next_id = 1
        self.target = None
        self.since = 0
        self.cooldowns = {}
        self.mode = "Explore"
        self.reason = "Looking for subjects"

    def update(self, detections, now):
        available = set(self.tracks)
        for label, score, box in detections:
            x, y, w, h = box
            candidates = []
            for ident in available:
                t = self.tracks[ident]
                if t.label != label or now - t.seen > self.config['lost_seconds']:
                    continue
                a, b, c, d = t.box
                distance = math.hypot(x+w/2-a-c/2, y+h/2-b-d/2)
                if distance < max(65, min(180, max(w, h, c, d))):
                    candidates.append((distance, ident))
            if candidates:
                ident = min(candidates)[1]
                available.remove(ident)
                t = self.tracks[ident]
                t.box, t.score, t.seen = tuple(box), score, now
            else:
                ident = self.next_id
                self.next_id += 1
                self.tracks[ident] = Track(ident, label, score, tuple(box), now)
        self.tracks = {k:t for k,t in self.tracks.items() if now-t.seen <= self.config['lost_seconds']}
        self.cooldowns = {k:v for k,v in self.cooldowns.items() if v > now}
        if self.mode == 'Park':
            self.target = None
            self.reason = 'Parked — observing without movement'
            return None
        if self.target not in self.tracks:
            self.target = None
            if self.mode == 'Follow':
                self.mode = 'Explore'
        if self.target is not None and self.mode == 'Explore' and now-self.since >= self.config['dwell_seconds']:
            self.cooldowns[self.target] = now+self.config['cooldown_seconds']
            self.target = None
        if self.target is None:
            choices = [t for t in self.tracks.values() if t.id not in self.cooldowns and now-t.seen < .5]
            if choices:
                t = max(choices, key=lambda t:(t.label in self.config['preferred_classes'], t.score))
                self.target, self.since = t.id, now
        t = self.tracks.get(self.target)
        self.reason = (f"{'Following selection' if self.mode == 'Follow' else 'Watching'}: {t.name or t.label} #{t.id}" if t else 'Exploring — looking for new subjects')
        if t and now-t.seen > .5:
            self.reason = 'Subject obscured — briefly waiting for return'
            return None
        return t

    def select(self, ident, now):
        if ident in self.tracks:
            self.target, self.since, self.mode = ident, now, 'Follow'
