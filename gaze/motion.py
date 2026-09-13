"""Background optical flow, excluding known subjects. No semantic inference."""
class BackgroundMotion:
    def __init__(self):
        self.previous=None
        self.boxes=[]

    def update(self, rgb, boxes):
        import cv2
        import numpy as np
        grey=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
        small=cv2.resize(grey,(480,360))
        shift=(0.,0.);reliable=False
        if self.previous is not None:
            mask=np.full(small.shape,255,np.uint8)
            for x,y,w,h in self.boxes:
                cv2.rectangle(mask,(max(0,int(x/2)-8),max(0,int(y/2)-8)),(int((x+w)/2)+8,int((y+h)/2)+8),0,-1)
            points=cv2.goodFeaturesToTrack(self.previous,100,.02,12,mask=mask)
            if points is not None and len(points)>=12:
                nxt,status,_=cv2.calcOpticalFlowPyrLK(self.previous,small,points,None)
                if nxt is not None:
                    good=status.ravel()==1
                    old=points[good].reshape(-1,2);new=nxt[good].reshape(-1,2)
                    if len(old)>=12:
                        delta=new-old;median=np.median(delta,axis=0)
                        inliers=np.linalg.norm(delta-median,axis=1)<2.5
                        if inliers.sum()>=10 and inliers.mean()>.65:
                            shift=tuple(float(v)*2 for v in np.median(delta[inliers],axis=0));reliable=True
        self.previous=small;self.boxes=boxes
        return shift,reliable
