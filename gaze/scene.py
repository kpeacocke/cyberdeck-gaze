"""Compare persistent detector counts at the same settled, named viewpoint."""
from collections import Counter
import json
from pathlib import Path

class SceneObserver:
    def __init__(self, root, config):
        self.path=Path(root)/'scene-baselines.json'
        self.baselines=json.loads(self.path.read_text()) if self.path.exists() else {}
        self.seconds=config.get('scene_confirm_seconds',3)
        self.minimum=config.get('scene_min_samples',5)
        self.ttl=config.get('unknown_retention_hours',24)*3600
        self.pending=None
        self.since=0
        self.samples=0
        self.note='Save a viewpoint to compare observations there'

    def save(self):
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.baselines,indent=2))
        temp.replace(self.path)

    def reset(self, name):
        self.baselines.pop(name,None);self.pending=None;self.save()

    def observe(self, name, position, detections, now, stationary):
        expired=[n for n,b in self.baselines.items() if now-b['time']>self.ttl]
        for n in expired:self.baselines.pop(n)
        if expired:self.save()
        if not name or not stationary:
            self.pending=None;self.samples=0
            self.note='Waiting for a settled named viewpoint'
            return []
        counts=dict(Counter(label for label,score,box in detections))
        signature=(name,tuple(position),tuple(sorted(counts.items())))
        if signature!=self.pending:
            self.pending=signature;self.since=now;self.samples=1
        else:self.samples+=1
        if now-self.since<self.seconds or self.samples<self.minimum:
            self.note=f'{name}: confirming a persistent observation'
            return []
        previous=self.baselines.get(name)
        if previous and previous['position']!=list(position):previous=None
        events=[]
        if previous:
            before=previous['counts']
            for label in sorted(set(before)|set(counts)):
                old,new=before.get(label,0),counts.get(label,0)
                if old!=new:
                    events.append({'event':f'{name}: detected count {old} → {new}', 'track':0, 'label':label})
            self.note=f'{name}: '+('persistent detection change' if events else 'no persistent detection change')
        else:
            self.note=f'{name}: baseline recorded'
            events.append({'event':f'{name}: baseline recorded','track':0,'label':', '.join(sorted(counts)) or 'no objects detected'})
        if previous is None or previous['counts']!=counts or now-previous['time']>60:
            self.baselines[name]={'time':now,'position':list(position),'counts':counts}
            if len(self.baselines)>30:
                oldest=min(self.baselines,key=lambda n:self.baselines[n]['time']);self.baselines.pop(oldest)
            self.save()
        return events
