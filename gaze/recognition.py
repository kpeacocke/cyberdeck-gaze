"""Local enrolled-reference matching. Unknown embeddings are never persisted."""
import json
import queue
import threading
import time
from pathlib import Path


def choose_match(scores, threshold, margin):
    """Compare distinct identities, not individual examples of the same identity."""
    best={}
    for name,score in scores:
        best[name]=max(best.get(name,-1),float(score))
    ranked=sorted(best.items(),key=lambda item:item[1],reverse=True)
    if not ranked:return None,0.
    name,score=ranked[0]
    if score<threshold or (len(ranked)>1 and score-ranked[1][1]<margin):return None,score
    return name,score

class Recognizer:
    def __init__(self, root, config):
        import cv2
        self.cv=cv2
        self.root=Path(root)
        self.path=self.root/'known-subjects.json'
        self.config=config
        self.gallery=json.loads(self.path.read_text()) if self.path.exists() else []
        self.face_detector=self.face_recognizer=None
        model_dir=Path(config.get('recognition_model_dir','/mnt/nvme/models/cyberdeck-gaze'))
        if (model_dir/'yunet.onnx').exists() and (model_dir/'sface.onnx').exists():
            self.face_detector=cv2.FaceDetectorYN.create(str(model_dir/'yunet.onnx'),'',(320,320),.9,.3,5000)
            self.face_recognizer=cv2.FaceRecognizerSF.create(str(model_dir/'sface.onnx'),'')
        self.orb=cv2.ORB_create(nfeatures=600)

    def save(self):
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.gallery))
        temp.chmod(0o600)
        temp.replace(self.path)

    def feature(self, rgb, kind):
        import numpy as np
        cv=self.cv
        if rgb is None or rgb.size==0:raise ValueError('No usable image')
        bgr=cv.cvtColor(rgb,cv.COLOR_RGB2BGR)
        if kind=='person':
            if self.face_detector is None:raise ValueError('Face models are unavailable')
            self.face_detector.setInputSize((bgr.shape[1],bgr.shape[0]))
            _,faces=self.face_detector.detect(bgr)
            if faces is None or len(faces)!=1:raise ValueError('Use an image with exactly one clear face')
            f=faces[0]
            if min(f[2:4])<40:raise ValueError('Face is too small; move closer and save a clearer sighting')
            aligned=self.face_recognizer.alignCrop(bgr,f)
            if cv.Laplacian(cv.cvtColor(aligned,cv.COLOR_BGR2GRAY),cv.CV_64F).var()<25:
                raise ValueError('Face is too blurred')
            vector=self.face_recognizer.feature(aligned).flatten()
            vector=vector/max(np.linalg.norm(vector),1e-9)
            return {'vector':vector.tolist()}
        if kind not in ('dog','cat'):raise ValueError('Enrol a person, dog or cat')
        # Pet appearance is an explicitly experimental visual-reference comparison.
        bgr=cv.resize(bgr,(256,256))
        grey=cv.cvtColor(bgr,cv.COLOR_BGR2GRAY)
        _,descriptors=self.orb.detectAndCompute(grey,None)
        if descriptors is None or len(descriptors)<20:raise ValueError('Pet image has too little visible detail')
        hsv=cv.cvtColor(bgr,cv.COLOR_BGR2HSV)
        hist=cv.calcHist([hsv],[0,1],None,[24,16],[0,180,0,256])
        cv.normalize(hist,hist)
        return {'descriptors':descriptors.tolist(),'histogram':hist.flatten().tolist()}

    def enrol(self, name, kind, rgb):
        name=name.strip()
        if not name or len(name)>80:raise ValueError('Use a name between 1 and 80 characters')
        if len(self.gallery)>=200:raise ValueError('Reference limit reached; remove unused examples first')
        feature=self.feature(rgb,kind)
        self.gallery.append({'name':name,'kind':kind,'feature':feature,'created':time.time()})
        self.save()
        return f'Saved reference for {name}. Add views with different angles and lighting.'

    def forget(self, name):
        self.gallery=[row for row in self.gallery if row['name']!=name]
        self.save()

    def match(self, kind, rgb):
        import numpy as np
        entries=[g for g in self.gallery if g['kind']==kind]
        if not entries:return {'name':None,'reason':'not enrolled','score':0}
        try:feature=self.feature(rgb,kind)
        except ValueError as error:return {'name':None,'reason':str(error),'score':0}
        scores=[]
        for entry in entries:
            ref=entry['feature']
            if kind=='person':
                score=float(np.dot(feature['vector'],ref['vector']))
            else:
                a=np.array(feature['descriptors'],np.uint8);b=np.array(ref['descriptors'],np.uint8)
                pairs=self.cv.BFMatcher(self.cv.NORM_HAMMING).knnMatch(a,b,k=2)
                good=sum(len(pair)==2 and pair[0].distance<.7*pair[1].distance for pair in pairs)
                ratio=good/max(1,min(len(a),len(b)))
                colour=self.cv.compareHist(np.array(feature['histogram'],np.float32),np.array(ref['histogram'],np.float32),self.cv.HISTCMP_CORREL)
                score=min(1,ratio*3)*.8+max(0,colour)*.2 if good>=12 else 0.
            scores.append((entry['name'],score))
        threshold=self.config.get('face_match_threshold',.5) if kind=='person' else self.config.get('pet_match_threshold',.7)
        name,score=choose_match(scores,threshold,self.config.get('recognition_margin',.08))
        return {'name':name,'score':round(score,3),'reason':'face match' if kind=='person' else 'experimental appearance match','possible':kind!='person'}

class RecognitionWorker:
    """Bounded asynchronous CPU work; never blocks the camera or Tk loop."""
    def __init__(self,root,config):
        self.jobs=queue.Queue(maxsize=2)
        self.results=queue.Queue(maxsize=8)
        self.stop=threading.Event()
        self.root,self.config=root,config
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def submit(self,op,token,payload):
        try:self.jobs.put_nowait((op,token,payload));return True
        except queue.Full:return False

    def run(self):
        try:r=Recognizer(self.root,self.config)
        except Exception as error:
            self.results.put(('error',None,str(error)));return
        while not self.stop.is_set():
            try:op,token,payload=self.jobs.get(timeout=.3)
            except queue.Empty:continue
            try:
                if op=='match':result=r.match(*payload)
                elif op=='enrol':result=r.enrol(*payload)
                elif op=='forget':r.forget(payload);result=f'Forgot {payload}'
                else:raise ValueError('Unknown recognition operation')
                if op!='match':result={'message':result,'subjects':sorted({x['name'] for x in r.gallery})}
            except Exception as error:result={'error':str(error)}
            try:self.results.put_nowait((op,token,result))
            except queue.Full:pass
