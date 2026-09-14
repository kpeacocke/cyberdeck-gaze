#!/usr/bin/env python3
"""Fetch public OpenCV models; verify content before replacing local files."""
import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

MODELS={
 'yunet.onnx':('face_detection_yunet/face_detection_yunet_2023mar.onnx','8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'),
 'sface.onnx':('face_recognition_sface/face_recognition_sface_2021dec.onnx','0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79'),
}
def main():
 p=argparse.ArgumentParser();p.add_argument('--directory',default='/mnt/nvme/models/cyberdeck-gaze');args=p.parse_args()
 root=Path(args.directory)
 if str(root).startswith('/mnt/nvme/') and not Path('/mnt/nvme').is_mount():raise SystemExit('Mount NVMe first')
 root.mkdir(parents=True,exist_ok=True)
 for filename,(source,digest) in MODELS.items():
  target=root/filename
  if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==digest:continue
  url='https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/'+source
  with urlopen(url,timeout=120) as response:data=response.read(60*1024*1024)
  if hashlib.sha256(data).hexdigest()!=digest:raise SystemExit('Model checksum mismatch: '+filename)
  temporary=target.with_suffix('.tmp');temporary.write_bytes(data);temporary.replace(target)
 print('Recognition models verified:',root)
if __name__=='__main__':main()
