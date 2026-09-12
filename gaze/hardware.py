"""IMX500 detection and bounded PCA9685 motion. No hardware opens at import."""
import time

class Camera:
    def __init__(self, config):
        from picamera2 import Picamera2
        from picamera2.devices import IMX500
        self.ai = IMX500(config['model'])
        self.labels = self.ai.network_intrinsics.labels
        self.cam = Picamera2(self.ai.camera_num)
        self.cam.configure(self.cam.create_preview_configuration(main={'size': (960,720), 'format':'RGB888'}, controls={'FrameRate':15}, buffer_count=6))
        self.threshold = config['confidence']
        self.cam.start()
        self.ai.set_auto_aspect_ratio()

    def read(self):
        import cv2
        request = self.cam.capture_request()
        try:
            frame = request.make_array('main')
            metadata = request.get_metadata()
            outputs = self.ai.get_outputs(metadata, add_batch=True)
            detections = []
            if outputs is not None:
                boxes, scores, classes = outputs[0][0], outputs[1][0], outputs[2][0]
                for box, score, category in zip(boxes, scores, classes):
                    idx = int(category)
                    if float(score) >= self.threshold and 0 <= idx < len(self.labels) and self.labels[idx] != '-':
                        rect = self.ai.convert_inference_coords(box, metadata, self.cam)
                        detections.append((self.labels[idx], float(score), rect))
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), detections
        finally:
            request.release()

    def close(self):
        self.cam.stop()
        self.cam.close()

class Motor:
    def __init__(self, config):
        self.c = config
        self.bus = None
        self.pan = self.tilt = 90.
        self.last = time.monotonic()
        if config['enabled'] and config['calibrated']:
            from smbus2 import SMBus
            self.bus = SMBus(config['bus'])
            addr = config['address']
            self.bus.write_byte_data(addr, 0, 0x10)
            self.bus.write_byte_data(addr, 0xfe, 121)  # nominal 50 Hz
            self.bus.write_byte_data(addr, 0, 0x20)
            time.sleep(.005)
            self.bus.write_byte_data(addr, 0, 0xa0)

    def move(self, pan, tilt):
        now = time.monotonic()
        step = min(now-self.last, .1)*self.c['speed_deg_s']
        self.last = now
        for axis, wanted in [('pan',pan), ('tilt',tilt)]:
            wanted = max(self.c[axis+'_min'], min(self.c[axis+'_max'], wanted))
            old = getattr(self, axis)
            angle = old+max(-step, min(step,wanted-old))
            setattr(self, axis, angle)
            if self.bus:
                pulse = self.c['pulse_min_us']+angle/180*(self.c['pulse_max_us']-self.c['pulse_min_us'])
                ticks = round(pulse*4096/20000)
                self.bus.write_i2c_block_data(self.c['address'], 6+4*self.c[axis+'_channel'], [0,0,ticks&255,ticks>>8])

    def follow(self, box):
        x,y,w,h = box
        dx,dy = (x+w/2-480)/480, (y+h/2-360)/360
        dx = 0 if abs(dx)<.10 else dx
        dy = 0 if abs(dy)<.10 else dy
        self.move(self.pan+dx*8*self.c['pan_sign'], self.tilt+dy*6*self.c['tilt_sign'])

    def close(self):
        if self.bus:
            for ch in [self.c['pan_channel'],self.c['tilt_channel']]:
                self.bus.write_byte_data(self.c['address'],9+4*ch,0x10)
            self.bus.close()
