"""Native desktop app. Camera owns a worker; Tk and storage stay on main thread."""
import argparse
import json
import queue
import threading
import time
from pathlib import Path
from .core import Attention
from .storage import Store

class App:
    def __init__(self, root, config, config_path):
        import tkinter as tk
        from tkinter import ttk
        self.root, self.config, self.config_path = root, config, config_path
        self.store = Store(config)
        self.attention = Attention(config)
        self.frames = queue.Queue(maxsize=1)
        self.commands = queue.Queue()
        self.stop = threading.Event()
        self.last_saved = {}
        self.last_pruned = 0
        self.motor_state = 'MOTION DISABLED — calibration required'
        self.latest = None
        root.title('CYBERDECK / GAZE')
        root.configure(bg='#10171e')
        root.geometry('1160x920')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', background='#18232d', foreground='#e0edf5', font=('DejaVu Sans',11))
        style.configure('TButton', padding=9)
        header = tk.Frame(root,bg='#10171e')
        header.pack(fill='x',padx=18,pady=14)
        tk.Label(header,text='GAZE  /  LOCAL VISION',fg='#54ddcf',bg='#10171e',font=('DejaVu Sans',20,'bold')).pack(side='left')
        for mode in ['Explore','Follow','Park']:
            ttk.Button(header,text=mode,command=lambda m=mode:self.set_mode(m)).pack(side='left',padx=5)
        ttk.Button(header,text='Settings',command=self.settings).pack(side='right')
        body=tk.Frame(root,bg='#10171e');body.pack(fill='both',expand=True,padx=18)
        self.canvas=tk.Canvas(body,width=840,height=630,bg='#080d12',highlightthickness=0)
        self.canvas.pack(side='left',anchor='n')
        self.canvas.bind('<Button-1>', self.click)
        side=tk.Frame(body,bg='#18232d',width=270);side.pack(side='left',fill='both',expand=True,padx=(12,0))
        tk.Label(side,text='RECENT SIGHTINGS',fg='#54ddcf',bg='#18232d').pack(pady=10)
        self.listbox=tk.Listbox(side,bg='#18232d',fg='#e0edf5',selectbackground='#326677',height=15,width=30,exportselection=False)
        self.listbox.pack(fill='x',padx=10)
        self.listbox.bind('<<ListboxSelect>>',self.show_sighting)
        self.thumb=tk.Label(side,bg='#18232d');self.thumb.pack(pady=10)
        ttk.Button(side,text='Save with name',command=self.name_sighting).pack(fill='x',padx=10,pady=4)
        ttk.Button(side,text='Forget sighting',command=self.forget).pack(fill='x',padx=10,pady=4)
        tk.Label(side,text='Names label saved sightings.\nAutomatic identity recognition\nis not enabled in this release.',fg='#a0b1be',bg='#18232d',justify='left').pack(padx=10,pady=12)
        self.status=tk.StringVar(value='Starting AI Camera — loading its model may take a while…')
        tk.Label(root,textvariable=self.status,fg='#a0b1be',bg='#10171e',anchor='w',wraplength=1200).pack(fill='x',padx=18,pady=12)
        self.refresh_list()
        self.worker=threading.Thread(target=self.capture,daemon=True)
        self.worker.start()
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(50,self.tick)

    def capture(self):
        from .hardware import Camera, Motor
        camera=motor=None
        try:
            camera=Camera(self.config)
            motor=Motor(self.config['motor'])
            self.motor_state='MOTION ACTIVE' if motor.bus else 'MOTION DISABLED — calibration required'
            while not self.stop.is_set():
                frame,detections=camera.read()
                latest_command=None
                while not self.commands.empty():
                    latest_command=self.commands.get_nowait()
                if latest_command:
                    op,value=latest_command
                    if op=='follow':motor.follow(value)
                    if op=='park':motor.move(90,90)
                    if op=='scan':motor.move(value,90)
                packet=(frame,detections,None)
                try:self.frames.get_nowait()
                except queue.Empty:pass
                self.frames.put_nowait(packet)
        except Exception as error:
            try:self.frames.get_nowait()
            except queue.Empty:pass
            self.frames.put_nowait((None,[],f'{type(error).__name__}: {error}'))
        finally:
            if motor:motor.close()
            if camera:camera.close()

    def tick(self):
        from PIL import Image, ImageTk, ImageDraw
        try:
            frame,detections,error=self.frames.get_nowait()
            if error:
                self.status.set('CAMERA ERROR: '+error)
            else:
                now=time.monotonic()
                if now-self.last_pruned>60:
                    self.store.prune()
                    self.last_pruned=now
                target=self.attention.update(detections,now)
                raw=Image.fromarray(frame)
                image=raw.copy();draw=ImageDraw.Draw(image)
                for track in self.attention.tracks.values():
                    if now-track.seen>.5:continue
                    x,y,w,h=track.box
                    colour='#54ddcf' if track.id==self.attention.target else '#d8af65'
                    draw.rectangle((x,y,x+w,y+h),outline=colour,width=3)
                    draw.text((max(0,x),max(0,y-16)),f'{track.label} #{track.id}  {track.score:.0%}',fill=colour)
                    if now-self.last_saved.get(track.id,-100)>30:
                        crop=raw.crop((max(0,x),max(0,y),min(960,x+w),min(720,y+h)))
                        if crop.width and crop.height:
                            self.store.add(track.label,crop)
                            self.last_saved[track.id]=now
                            self.refresh_list()
                self.last_saved={k:v for k,v in self.last_saved.items() if now-v<120}
                self.photo=ImageTk.PhotoImage(image.resize((840,630)))
                if not hasattr(self,'image_item'):self.image_item=self.canvas.create_image(0,0,anchor='nw',image=self.photo)
                else:self.canvas.itemconfigure(self.image_item,image=self.photo)
                if target:self.commands.put(('follow',target.box))
                elif self.attention.mode=='Park':self.commands.put(('park',None))
                elif not self.attention.tracks:
                    # Step-and-pause viewpoints, not continuous scanning blur.
                    positions=[75,90,105,90]
                    self.commands.put(('scan',positions[int(now//5)%4]))
                self.status.set(f'{self.attention.mode.upper()}  ·  {self.attention.reason}  ·  {self.motor_state}\nStorage: {self.store.root}')
        except queue.Empty:pass
        except Exception as error:self.status.set('APP ERROR: '+str(error))
        if not self.stop.is_set():self.root.after(40,self.tick)

    def set_mode(self,mode):
        if mode=='Follow':
            self.status.set('Click a detected subject in the live view to follow it.')
            return
        self.attention.mode=mode
        self.attention.target=None

    def click(self,event):
        for t in self.attention.tracks.values():
            x,y,w,h=t.box
            if x<=event.x/0.875<=x+w and y<=event.y/0.875<=y+h:
                self.attention.select(t.id,time.monotonic());break

    def refresh_list(self):
        self.rows=self.store.recent();self.listbox.delete(0,'end')
        for _,stamp,label,name,_ in self.rows:
            self.listbox.insert('end',f'{time.strftime("%H:%M",time.localtime(stamp))}  {name or label}')

    def selected(self):
        selection=self.listbox.curselection()
        return self.rows[selection[0]] if selection else None

    def show_sighting(self,event=None):
        from PIL import Image,ImageTk
        row=self.selected()
        if row:
            with Image.open(self.store.root/row[4]) as im:
                im.thumbnail((240,180));self.thumb_photo=ImageTk.PhotoImage(im)
            self.thumb.configure(image=self.thumb_photo)

    def name_sighting(self):
        from tkinter import simpledialog
        row=self.selected()
        if row:
            name=simpledialog.askstring('Save sighting','Name for this saved sighting (not automatic recognition):',parent=self.root)
            if name and name.strip():self.store.rename(row[0],name.strip()[:80]);self.refresh_list()

    def forget(self):
        row=self.selected()
        if row:self.store.forget(row[0]);self.refresh_list();self.thumb.configure(image='')

    def settings(self):
        import tkinter as tk
        from tkinter import ttk,messagebox
        win=tk.Toplevel(self.root);win.title('Gaze settings')
        fields={}
        for i,key in enumerate(['storage_dir','unknown_retention_hours','max_storage_mb','dwell_seconds','confidence']):
            ttk.Label(win,text=key.replace('_',' ').title()).grid(row=i,column=0,padx=12,pady=8,sticky='w')
            var=tk.StringVar(value=str(self.config[key]));fields[key]=var
            ttk.Entry(win,textvariable=var,width=45).grid(row=i,column=1,padx=12)
        def save():
            try:
                updated=dict(self.config)
                for key,var in fields.items():updated[key]=var.get() if key=='storage_dir' else float(var.get())
                if not Path(updated['storage_dir']).is_absolute():raise ValueError('Storage must be an absolute path')
                if not 0<updated['confidence']<=1:raise ValueError('Confidence must be between 0 and 1')
                if any(updated[k]<=0 for k in ['unknown_retention_hours','max_storage_mb','dwell_seconds']):raise ValueError('Limits must be positive')
                self.config_path.write_text(json.dumps(updated,indent=2)+'\n')
                messagebox.showinfo('Settings saved','Restart Gaze to apply. Existing sightings remain at their original location.',parent=win);win.destroy()
            except Exception as error:messagebox.showerror('Invalid settings',str(error),parent=win)
        ttk.Button(win,text='Save settings',command=save).grid(row=len(fields),column=1,pady=15)

    def close(self):
        self.stop.set()
        self.worker.join(timeout=3)
        self.store.db.close()
        self.root.destroy()

def main():
    import tkinter as tk
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default=str(Path.home()/'.config/cyberdeck-gaze/config.json'))
    args=parser.parse_args();path=Path(args.config).expanduser()
    config=json.loads(path.read_text())
    import fcntl, signal
    lock_path=Path.home()/'.cache/cyberdeck-gaze.lock'
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    lock=lock_path.open('w')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Cyberdeck Gaze is already running. Open its existing window.')
    root=tk.Tk();app=App(root,config,path)
    signal.signal(signal.SIGTERM,lambda *_: root.after(0,app.close))
    root.mainloop()

if __name__ == "__main__":
    main()
