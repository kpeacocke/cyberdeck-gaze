"""Named commanded viewpoints, not measured positions or a room map."""
import json
from pathlib import Path

def validate_limits(values):
    for axis in ('pan','tilt'):
        low,high=values[axis+'_min'],values[axis+'_max']
        if not 0<=low<=90<=high<=180 or high-low<4:
            raise ValueError(f'{axis}: use limits between 0 and 180 that include centre 90')
    if values['pan_sign'] not in (-1,1) or values['tilt_sign'] not in (-1,1):
        raise ValueError('Axis signs must be +1 or -1')
    if not 1<=values['speed_deg_s']<=30:raise ValueError('Speed must be between 1 and 30 degrees/second')

class Places:
    def __init__(self,root):
        self.path=Path(root)/'viewpoints.json'
        self.items=json.loads(self.path.read_text()) if self.path.exists() else {}
    def save(self,name,angles):
        name=name.strip()
        if not name or len(name)>80:raise ValueError('Use a short viewpoint name')
        if len(self.items)>=30 and name not in self.items:raise ValueError('Maximum 30 viewpoints')
        self.items[name]=[float(a) for a in angles]
        self.flush()
    def forget(self,name):
        self.items.pop(name,None);self.flush()
    def flush(self):
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.items,indent=2));temp.replace(self.path)
    def valid(self,motor):
        return {n:p for n,p in self.items.items() if motor['pan_min']<=p[0]<=motor['pan_max'] and motor['tilt_min']<=p[1]<=motor['tilt_max']}
