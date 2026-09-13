"""Short-term tracking and explainable attention; IDs are not identities."""
from dataclasses import dataclass
import math

@dataclass
class Track:
    id: int
    label: str
    score: float
    box: tuple
    seen: float
    name: str = ''
    born: float = 0
    velocity: tuple = (0., 0.)
    hits: int = 1
    interest: float = 0
    reasons: str = ''
    moving: bool = False
    viewpoint: tuple = (90., 90.)

def centre(box):
    x,y,w,h=box
    return x+w/2,y+h/2

class Attention:
    def __init__(self, config):
        self.config=config
        self.tracks={}
        self.next_id=1
        self.target=None
        self.since=0
        self.cooldowns={}
        self.mode='Explore'
        self.reason='Looking for subjects'
        self.last_time=None
        self.events=[]
        self.memory=[]
        self.ranked=[]
        self.search_position=None
        self.search_until=0

    def event(self, now, kind, track):
        self.events.append({'time':now,'event':kind,'track':track.id,'label':track.label})
        self.events=self.events[-100:]

    def update(self, detections, now, camera_shift=(0.,0.), motion_reliable=True,
               viewpoint=(90.,90.), camera_moving=False):
        self.events=[]
        dt=max(.001,now-self.last_time) if self.last_time is not None else .1
        self.last_time=now
        sx,sy=camera_shift
        # Translate old boxes with observed background movement before association.
        for t in self.tracks.values():
            x,y,w,h=t.box;t.box=(x+sx,y+sy,w,h)
        edges=[]
        for index,(label,score,box) in enumerate(detections):
            x,y=centre(box)
            for ident,t in self.tracks.items():
                age=now-t.seen
                if label!=t.label or age>self.config['lost_seconds']:continue
                a,b=centre(t.box)
                prediction=min(age,.5)
                distance=math.hypot(x-a-t.velocity[0]*prediction,y-b-t.velocity[1]*prediction)
                gate=max(65,min(180,max(box[2:]+t.box[2:])))
                if distance<gate:
                    size_penalty=abs(math.log(max(1,box[2]*box[3])/max(1,t.box[2]*t.box[3])))
                    edges.append((distance/gate+.25*size_penalty,ident,index))
        used_tracks=set();used_detections=set()
        for _,ident,index in sorted(edges):
            if ident in used_tracks or index in used_detections:continue
            used_tracks.add(ident);used_detections.add(index)
            t=self.tracks[ident];label,score,box=detections[index]
            old=centre(t.box);new=centre(box)
            age=max(.001,now-t.seen)
            was_lost=age>.5
            # Residual scene motion only has meaning when compensation is reliable.
            if motion_reliable and not camera_moving:
                vx,vy=(new[0]-old[0])/age,(new[1]-old[1])/age
                t.velocity=(.6*t.velocity[0]+.4*vx,.6*t.velocity[1]+.4*vy)
                speed=math.hypot(*t.velocity)
                moving=speed>35 if not t.moving else speed>15
                if t.hits>=3 and moving!=t.moving:self.event(now,'moving' if moving else 'stopped',t)
                t.moving=moving
            else:
                t.velocity=(0.,0.);t.moving=False
            t.box,t.score,t.seen=tuple(box),score,now
            t.hits+=1;t.viewpoint=tuple(viewpoint)
            if was_lost:self.event(now,'reacquired',t)
        for index,(label,score,box) in enumerate(detections):
            if index in used_detections:continue
            t=Track(self.next_id,label,score,tuple(box),now,born=now,viewpoint=tuple(viewpoint))
            self.tracks[t.id]=t;self.next_id+=1
            self.event(now,'appeared',t)
        for ident,t in list(self.tracks.items()):
            if now-t.seen>self.config['lost_seconds']:
                self.event(now,'left view',t)
                self.memory.append({'track':ident,'label':t.label,'last_seen':t.seen,'viewpoint':t.viewpoint})
                del self.tracks[ident]
        ttl=self.config.get('scene_memory_seconds',120)
        self.memory=[m for m in self.memory if now-m['last_seen']<ttl][-100:]
        self.cooldowns={k:v for k,v in self.cooldowns.items() if v>now}
        for t in self.tracks.values():
            reasons=[];interest=t.score
            if t.label in self.config['preferred_classes']:interest+=3;reasons.append('preferred class')
            if now-t.born<5:interest+=2*(1-(now-t.born)/5);reasons.append('new arrival')
            if t.moving:interest+=2;reasons.append('moving')
            if t.id in self.cooldowns:interest-=8;reasons.append('recently watched')
            t.interest=interest;t.reasons=', '.join(reasons) or 'visible subject'
        self.ranked=sorted((t for t in self.tracks.values() if now-t.seen<.5),key=lambda t:t.interest,reverse=True)
        if self.mode=='Park':
            self.target=None;self.search_position=None
            self.reason='Parked — observing without following'
            return None
        if self.target not in self.tracks:
            self.target=None
            if self.mode=='Follow':self.mode='Explore'
        t=self.tracks.get(self.target)
        if t and now-t.seen>.5:
            self.search_position=t.viewpoint
            self.search_until=now+.5
            self.reason=f'Lost {t.label} #{t.id} — checking last viewing direction'
            return None
        self.search_position=None
        if t and self.mode=='Explore' and now-self.since>=self.config['dwell_seconds']:
            self.cooldowns[t.id]=now+self.config['cooldown_seconds'];self.target=None;t=None
        choices=[x for x in self.ranked if x.id not in self.cooldowns]
        best=choices[0] if choices else None
        if t and best and best.id!=t.id and self.mode=='Explore':
            if now-self.since>=self.config.get('minimum_dwell_seconds',4) and best.interest>t.interest+self.config.get('switch_margin',2.5):
                self.cooldowns[t.id]=now+self.config['cooldown_seconds'];t=None
        if t is None and best:
            self.target=best.id;self.since=now;t=best
            self.event(now,'selected',t)
        if t:
            remaining=max(0,math.ceil(self.config['dwell_seconds']-(now-self.since)))
            suffix='locked by you' if self.mode=='Follow' else f'{t.reasons} · {remaining}s remaining'
            self.reason=f'Following {t.label} #{t.id} · {suffix}'
        else:
            self.target=None;self.reason='Exploring — checking for new activity'
        return t

    def select(self, ident, now):
        if ident in self.tracks:
            self.target,self.since,self.mode=ident,now,'Follow'
