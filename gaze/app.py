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
        self.manual = False
        self.motor_angles = (90.,90.)
        self.last_runtime = 0
        from .motion import BackgroundMotion
        self.background=BackgroundMotion()
        self.previous_angles=(90.,90.)
        self.camera_settle_until=0
        from .recognition import RecognitionWorker
        from .places import Places
        self.recognition=RecognitionWorker(self.store.root,config)
        self.places=Places(self.store.root)
        from .scene import SceneObserver
        self.scene=SceneObserver(self.store.root,config)
        self.recognition_due=0
        self.recognition_cursor=0
        self.recognition_results={}
        self.recognition_votes={}
        self.recognition_note='Enrol a clear sighting to recognise it on return'
        self.view_goal=None
        self.view_name=''
        self.best_frames={}

        root.title('CYBERDECK / GAZE')
        root.configure(bg='#10171e')
        root.geometry('1160x1320')
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
        ttk.Button(header,text='Motors',command=self.motor_controls).pack(side='right',padx=5)
        body=tk.Frame(root,bg='#10171e');body.pack(fill='both',expand=True,padx=18)
        self.canvas=tk.Canvas(body,width=840,height=630,bg='#080d12',highlightthickness=0)
        self.canvas.pack(side='left',anchor='n')
        self.canvas.bind('<Button-1>', self.click)
        side=tk.Frame(body,bg='#18232d',width=270);side.pack(side='left',fill='both',expand=True,padx=(12,0))
        tk.Label(side,text='RECENT SIGHTINGS',fg='#54ddcf',bg='#18232d').pack(pady=10)
        self.listbox=tk.Listbox(side,bg='#18232d',fg='#e0edf5',selectbackground='#326677',height=8,width=30,exportselection=False)
        self.listbox.pack(fill='x',padx=10)
        self.listbox.bind('<<ListboxSelect>>',self.show_sighting)
        self.thumb=tk.Label(side,bg='#18232d');self.thumb.pack(pady=10)
        ttk.Button(side,text='Save with name',command=self.name_sighting).pack(fill='x',padx=10,pady=4)
        ttk.Button(side,text='Enrol friend / pet',command=self.enrol_sighting).pack(fill='x',padx=10,pady=4)
        ttk.Button(side,text='Known subjects / forget',command=self.known_subjects).pack(fill='x',padx=10,pady=4)
        ttk.Button(side,text='Observation history',command=self.observation_history).pack(fill='x',padx=10,pady=4)
        ttk.Button(side,text='Viewpoints',command=self.viewpoints).pack(fill='x',padx=10,pady=4)
        ttk.Button(side,text='Forget sighting',command=self.forget).pack(fill='x',padx=10,pady=4)
        self.recognition_status=tk.StringVar(value=self.recognition_note)
        tk.Label(side,textvariable=self.recognition_status,fg='#a0b1be',bg='#18232d',justify='left',wraplength=240).pack(padx=10,pady=8)
        self.attention_text=tk.StringVar(value='Watching for activity')
        tk.Label(side,textvariable=self.attention_text,fg='#54ddcf',bg='#18232d',justify='left',wraplength=240).pack(padx=10,pady=8)
        self.status=tk.StringVar(value='Starting AI Camera — loading its model may take a while…')
        tk.Label(root,textvariable=self.status,fg='#a0b1be',bg='#10171e',anchor='w',wraplength=1200).pack(fill='x',padx=18,pady=12)
        self.refresh_list()
        self.worker=threading.Thread(target=self.capture,daemon=True)
        self.worker.start()
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(50,self.tick)

    def capture(self):
        while not self.stop.is_set():
            try:self.capture_once()
            except Exception as error:
                self.motor_state='Camera recovery: '+str(error)
            if not self.stop.is_set():self.stop.wait(3)

    def capture_once(self):
        from .hardware import Camera, Motor
        camera=motor=None
        try:
            camera=Camera(self.config)
            motor=Motor(dict(self.config['motor'], enabled=False))
            manual_goal=None
            if self.config['motor']['enabled'] and self.config['motor']['calibrated']:
                try:
                    motor.arm()
                    self.motor_state='MOTION ACTIVE'
                except Exception as error:self.motor_state='MOTOR UNAVAILABLE: '+str(error)
            while not self.stop.is_set():
                frame,detections=camera.read()
                try:
                    while not self.commands.empty():
                        op,value=self.commands.get_nowait()
                        if op=='auto':
                            if self.config['motor']['calibrated']:
                                if not motor.bus:motor.arm()
                                self.motor_state='MOTION ACTIVE'
                        elif op=='arm':
                            if not motor.bus:motor.arm()
                            self.motor_state='MANUAL MOTOR TEST — automatic movement paused'
                        elif op=='configure':
                            motor.c=dict(value)
                        elif op=='off':
                            motor.close();manual_goal=None
                            self.motor_state='MOTORS OFF'
                        elif op=='jog' and motor.bus:
                            base=manual_goal or (motor.pan,motor.tilt)
                            manual_goal=(max(motor.c['pan_min'],min(motor.c['pan_max'],base[0]+value[0])),max(motor.c['tilt_min'],min(motor.c['tilt_max'],base[1]+value[1])))
                        elif not self.manual and motor.bus and self.config['motor']['calibrated']:
                            manual_goal=None
                            if op=='follow':motor.follow(value)
                            if op=='park':motor.move(90,90)
                            if op=='scan':motor.move(value,90)
                            if op=='look':motor.move(*value)
                    if self.manual and motor.bus and manual_goal:
                        motor.move(*manual_goal)
                except Exception as error:
                    self.motor_state=f'MOTOR UNAVAILABLE: {error} — camera remains active'
                    manual_goal=None
                    try:motor.close()
                    except OSError:pass
                self.motor_angles=(motor.pan,motor.tilt)
                packet=(frame,detections,None)
                try:self.frames.get_nowait()
                except queue.Empty:pass
                self.frames.put_nowait(packet)
        except Exception as error:
            try:self.frames.get_nowait()
            except queue.Empty:pass
            self.frames.put_nowait((None,[],f'{type(error).__name__}: {error}'))
        finally:
            try:
                if motor:motor.close()
            finally:
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
                shift,reliable=self.background.update(frame,[d[2] for d in detections])
                if max(abs(a-b) for a,b in zip(self.motor_angles,self.previous_angles))>.15:
                    self.camera_settle_until=now+.7
                self.previous_angles=self.motor_angles
                target=self.attention.update(detections,now,shift,reliable,self.motor_angles,now<self.camera_settle_until)
                if self.view_goal:self.attention.reason='Looking at '+self.view_name
                self.attention_text.set('ATTENTION\n'+self.attention.reason+'\n\nCANDIDATES\n'+'\n'.join(f'{t.label} #{t.id}: {t.interest:.1f}\n{t.reasons}' for t in self.attention.ranked[:3]))
                for event in self.attention.events:self.store.event(event)
                scene_name=None;scene_position=None
                for name,position in self.places.valid(self.config['motor']).items():
                    if max(abs(a-b) for a,b in zip(position,self.motor_angles))<.4:
                        scene_name=name;scene_position=position;break
                stable=now>=self.camera_settle_until and not self.manual
                for event in self.scene.observe(scene_name,scene_position,detections,time.time(),stable):
                    self.store.event(event)


                self.poll_recognition(now)
                raw=Image.fromarray(frame)
                image=raw.copy();draw=ImageDraw.Draw(image)
                eligible=[t.id for t in self.attention.tracks.values() if now-t.seen<.5 and t.label in ('person','dog','cat')]
                recognise_id=eligible[self.recognition_cursor%len(eligible)] if eligible else None
                for track in self.attention.tracks.values():
                    if now-track.seen>.5:continue
                    x,y,w,h=track.box
                    colour='#54ddcf' if track.id==self.attention.target else '#d8af65'
                    draw.rectangle((x,y,x+w,y+h),outline=colour,width=3)
                    draw.text((max(0,x),max(0,y-16)),f'{track.name or track.label} #{track.id}  {track.score:.0%}',fill=colour)
                    crop=raw.crop((max(0,x),max(0,y),min(960,x+w),min(720,y+h)))
                    if crop.width>0 and crop.height>0:
                        import cv2, numpy as np
                        crop.thumbnail((640,480))
                        quality=float(cv2.Laplacian(np.asarray(crop.convert('L')),cv2.CV_64F).var())*track.score
                        best=self.best_frames.get(track.id)
                        if best is None:self.best_frames[track.id]=(now,quality,crop.copy(),track.label)
                        elif quality>best[1]:self.best_frames[track.id]=(best[0],quality,crop.copy(),track.label)
                        if now-self.last_saved.get(track.id,-100)>30 and now-self.best_frames[track.id][0]>=2:
                            self.store.add(track.label,self.best_frames[track.id][2])
                            self.last_saved[track.id]=now
                            del self.best_frames[track.id]
                            self.refresh_list()
                        if now>=self.recognition_due and track.id==recognise_id:
                            if self.recognition.submit('match',(track.id,now),(track.label,np.asarray(crop).copy())):
                                self.recognition_due=now+1
                                self.recognition_cursor+=1
                for ident in list(self.best_frames):
                    if ident not in self.attention.tracks:
                        _,_,saved,label=self.best_frames.pop(ident)
                        if now-self.last_saved.get(ident,-100)>30:
                            self.store.add(label,saved);self.refresh_list()
                if len(self.best_frames)>30:
                    self.best_frames=dict(list(self.best_frames.items())[-30:])
                self.last_saved={k:v for k,v in self.last_saved.items() if now-v<120}
                self.photo=ImageTk.PhotoImage(image.resize((840,630)))
                if not hasattr(self,'image_item'):self.image_item=self.canvas.create_image(0,0,anchor='nw',image=self.photo)
                else:self.canvas.itemconfigure(self.image_item,image=self.photo)
                if self.manual:pass
                elif self.view_goal:self.commands.put(('look',self.view_goal))
                elif target:self.commands.put(('follow',target.box))
                elif self.attention.mode=='Park':self.commands.put(('park',None))
                elif self.attention.search_position:
                    self.commands.put(('look',self.attention.search_position))
                elif self.attention.target is None:
                    # Step-and-pause viewpoints, not continuous scanning blur.
                    mc=self.config['motor']
                    positions=[mc['pan_min'],90,mc['pan_max'],90]
                    saved=list(self.places.valid(mc).values())
                    if saved:self.commands.put(('look',saved[int(now//self.config.get('viewpoint_dwell_seconds',10))%len(saved)]))
                    else:self.commands.put(('scan',positions[int(now//5)%4]))
                if now-self.last_runtime>=1:
                    runtime={'timestamp':time.time(),'mode':self.attention.mode,'motor':self.motor_state,'pan':self.motor_angles[0],'tilt':self.motor_angles[1],'target':self.attention.target,'recognition':self.recognition_note,'viewpoints':len(self.places.items),'scene':self.scene.note,'tracks':len(self.attention.tracks),'reason':self.attention.reason,'candidates':[{'id':t.id,'label':t.label,'interest':round(t.interest,2),'reasons':t.reasons} for t in self.attention.ranked[:5]],'memory':self.attention.memory}
                    tmp=self.store.root/'runtime.tmp'
                    tmp.write_text(json.dumps(runtime))
                    tmp.replace(self.store.root/'runtime.json')
                    self.last_runtime=now
                self.status.set(f'{self.attention.mode.upper()}  ·  {self.attention.reason}  ·  {self.motor_state}\nStorage: {self.store.root}')
        except queue.Empty:pass
        except Exception as error:self.status.set('APP ERROR: '+str(error))
        if not self.stop.is_set():self.root.after(40,self.tick)

    def poll_recognition(self, now):
        while True:
            try:op,token,result=self.recognition.results.get_nowait()
            except queue.Empty:break
            if op=='error':
                self.recognition_note='Recognition unavailable: '+str(result)
            elif op=='match':
                ident,requested=token
                track=self.attention.tracks.get(ident)
                if track is None or now-requested>3 or now-track.seen>.5:continue
                name=result.get('name')
                previous,count=self.recognition_votes.get(ident,(None,0))
                count=count+1 if name and name==previous else 1
                self.recognition_votes[ident]=(name,count)
                if name and count>=2:
                    track.name=('Possible ' if result.get('possible') else '')+name
                    self.recognition_note=f'{track.name} · {result["reason"]} · similarity {result["score"]:.2f}'
                else:
                    track.name=''
                    self.recognition_note='Unknown · '+result.get('reason',result.get('error','checking match'))
            else:
                self.recognition_note=result.get('error',result.get('message','Updated'))
                if op=='enrol' and 'error' not in result and token:
                    ident,name=token;self.store.rename(ident,name);self.refresh_list()
                if op=='forget':
                    self.recognition_votes.clear()
                    for t in self.attention.tracks.values():t.name=''
            self.recognition_status.set(self.recognition_note)
        self.recognition_votes={k:v for k,v in self.recognition_votes.items() if k in self.attention.tracks}

    def enrol_sighting(self):
        from tkinter import simpledialog,messagebox
        from PIL import Image
        import numpy as np
        row=self.selected()
        if not row:
            messagebox.showinfo('Enrol','Select a clear person, dog or cat sighting first.',parent=self.root);return
        if row[2] not in ('person','dog','cat'):
            messagebox.showinfo('Enrol','This release enrols people, dogs and cats.',parent=self.root);return
        name=simpledialog.askstring('Enrol known subject','Name (reuse it to add another reference):',parent=self.root)
        if not name or not name.strip():return
        with Image.open(self.store.root/row[4]) as im:image=np.asarray(im.convert('RGB')).copy()
        if self.recognition.submit('enrol',(row[0],name.strip()),(name.strip(),row[2],image)):
            self.recognition_status.set('Checking reference quality…')
        else:self.recognition_status.set('Recognition busy; try enrolment again shortly')

    def known_subjects(self):
        import tkinter as tk
        from tkinter import ttk
        win=tk.Toplevel(self.root);win.title('Known subjects — local references')
        listing=tk.Listbox(win,width=45,height=12);listing.pack(padx=15,pady=15)
        path=self.store.root/'known-subjects.json'
        gallery=json.loads(path.read_text()) if path.exists() else []
        names=sorted({g['name'] for g in gallery})
        for name in names:
            rows=[g for g in gallery if g['name']==name]
            listing.insert('end',f'{name} — {rows[0]["kind"]}, {len(rows)} references')
        def forget():
            selected=listing.curselection()
            if selected and self.recognition.submit('forget',None,names[selected[0]]):
                self.recognition_status.set('Deleting enrolled references…');win.destroy()
        ttk.Button(win,text='Delete all recognition references for selection',command=forget).pack(padx=15,pady=10)
        ttk.Label(win,text='Deletes recognition data. Saved sighting photos are managed separately.').pack(padx=15,pady=10)

    def observation_history(self):
        import tkinter as tk
        from tkinter import ttk
        win=tk.Toplevel(self.root);win.title('Gaze — observation history')
        scene=tk.StringVar(value=self.scene.note)
        ttk.Label(win,textvariable=scene,wraplength=850).pack(padx=12,pady=12)
        listing=tk.Listbox(win,width=100,height=25)
        listing.pack(padx=12,pady=8,fill='both',expand=True)
        ttk.Label(win,text='Detection changes are not proof that something physically arrived or left.\nLighting, occlusion and recognition errors can change what is detected.').pack(padx=12,pady=12)
        def refresh():
            if not win.winfo_exists():return
            scene.set(self.scene.note)
            listing.delete(0,'end')
            for stamp,kind,ident,label in self.store.recent_events():
                suffix=f' #{ident}' if ident else ''
                listing.insert('end',f'{time.strftime("%H:%M:%S",time.localtime(stamp))}  {label}{suffix} — {kind}')
            win.after(2000,refresh)
        refresh()

    def viewpoints(self):
        import tkinter as tk
        from tkinter import ttk,simpledialog,messagebox
        win=tk.Toplevel(self.root);win.title('Named viewpoints')
        listing=tk.Listbox(win,width=45,height=10);listing.pack(padx=12,pady=12)
        names=[]
        def refresh():
            names[:]=list(self.places.items);listing.delete(0,'end')
            for name in names:listing.insert('end',f'{name} — {self.places.items[name]}')
        def save():
            name=simpledialog.askstring('Save viewpoint','Name this current camera direction:',parent=win)
            if name:
                try:self.places.save(name,self.motor_angles);refresh()
                except ValueError as error:messagebox.showerror('Viewpoint',str(error),parent=win)
        def look():
            sel=listing.curselection()
            if not sel:return
            name=names[sel[0]]
            if name not in self.places.valid(self.config['motor']):
                messagebox.showerror('Outside limits','This viewpoint is outside the current calibrated travel.',parent=win);return
            self.attention.mode='Park';self.attention.target=None
            self.view_goal=self.places.items[name]
            self.view_name=name
            self.commands.put(('auto',None))
            self.attention.reason='Looking at '+name
        def forget():
            sel=listing.curselection()
            if sel:
                self.scene.reset(names[sel[0]])
                self.places.forget(names[sel[0]]);refresh()
        def reset_baseline():
            sel=listing.curselection()
            if sel:self.scene.reset(names[sel[0]])
        for title,action in [('Save current direction',save),('Look at selection',look),('Reset observation baseline',reset_baseline),('Delete selection',forget)]:
            ttk.Button(win,text=title,command=action).pack(fill='x',padx=12,pady=4)
        ttk.Label(win,text='Explore revisits saved viewpoints. Explore or Park releases a fixed view.').pack(padx=12,pady=10)
        refresh()

    def calibration(self, parent):
        import tkinter as tk
        from tkinter import ttk,messagebox
        from .places import validate_limits
        win=tk.Toplevel(parent);win.title('Calibrate motor travel')
        original=dict(self.config['motor'])
        fields={}
        keys=['pan_min','pan_max','tilt_min','tilt_max','pan_sign','tilt_sign','speed_deg_s']
        ttk.Label(win,text='Extend one bound by at most 5° per test. Jog in the Motors window.\nSave only after observing free travel and adequate cable slack.').grid(row=0,columnspan=2,padx=12,pady=12)
        for i,key in enumerate(keys,1):
            ttk.Label(win,text=key.replace('_',' ')).grid(row=i,column=0,padx=12,pady=4)
            fields[key]=tk.StringVar(value=str(original[key]))
            ttk.Entry(win,textvariable=fields[key],width=15).grid(row=i,column=1,padx=12)
        def values():
            candidate=dict(self.config['motor'])
            for key,var in fields.items():candidate[key]=float(var.get())
            validate_limits(candidate)
            for key in keys[:4]:
                if abs(candidate[key]-self.config['motor'][key])>5:raise ValueError('Change each bound at most 5° per test')
            return candidate
        def trial():
            try:
                candidate=values();self.commands.put(('configure',candidate))
                self.recognition_status.set('Trial limits active in manual mode; jog and observe before saving')
            except ValueError as error:messagebox.showerror('Calibration',str(error),parent=win)
        def save():
            try:
                candidate=values();candidate.update(enabled=True,calibrated=True)
                self.config['motor']=candidate
                self.config_path.write_text(json.dumps(self.config,indent=2)+'\n')
                self.commands.put(('configure',dict(candidate)))
                win.destroy()
            except ValueError as error:messagebox.showerror('Calibration',str(error),parent=win)
        def cancel():
            self.commands.put(('configure',dict(self.config['motor'])));win.destroy()
        ttk.Button(win,text='Apply trial bounds',command=trial).grid(row=8,column=0,padx=12,pady=12)
        ttk.Button(win,text='Save observed limits',command=save).grid(row=8,column=1,padx=12,pady=12)
        win.protocol('WM_DELETE_WINDOW',cancel)

    def motor_controls(self):
        import tkinter as tk
        from tkinter import ttk
        self.manual=True
        win=tk.Toplevel(self.root);win.title('Pan / tilt — manual test')
        ttk.Label(win,text='Automatic tracking is paused. Arm, then jog each axis.\nFirst jog commands near centre (90°); physical position is unknown.').pack(padx=16,pady=12)
        ttk.Button(win,text='Arm / retry controller',command=lambda:self.commands.put(('arm',None))).pack(pady=5)
        row=ttk.Frame(win);row.pack(padx=12,pady=10)
        for label,delta in [('Pan −2°',(-2,0)),('Pan +2°',(2,0)),('Tilt −2°',(0,-2)),('Tilt +2°',(0,2))]:
            ttk.Button(row,text=label,command=lambda d=delta:self.commands.put(('jog',d))).pack(side='left',padx=3)
        ttk.Button(win,text='Calibrate limits / directions',command=lambda:self.calibration(win)).pack(pady=8)
        ttk.Button(win,text='Stop / release motors',command=lambda:self.commands.put(('off',None))).pack(pady=8)
        state=tk.StringVar()
        ttk.Label(win,textvariable=state,wraplength=550).pack(padx=12,pady=10)
        def update():
            if win.winfo_exists():
                state.set(self.motor_state);win.after(200,update)
        def close():
            self.commands.put(('off',None))
            self.commands.put(('configure',dict(self.config['motor'])))
            self.manual=False
            win.destroy()
        win.protocol('WM_DELETE_WINDOW',close)
        update()

    def set_mode(self,mode):
        if mode=='Follow':
            self.status.set('Click a detected subject in the live view to follow it.')
            return
        self.view_goal=None
        self.attention.mode=mode
        self.attention.target=None
        if not self.manual:self.commands.put(('auto',None))

    def click(self,event):
        for t in self.attention.tracks.values():
            x,y,w,h=t.box
            if x<=event.x/0.875<=x+w and y<=event.y/0.875<=y+h:
                self.view_goal=None
                self.attention.select(t.id,time.monotonic())
                if not self.manual:self.commands.put(('auto',None))
                break

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
        self.recognition.stop.set()
        self.worker.join(timeout=3)
        self.recognition.thread.join(timeout=2)
        self.store.db.close()
        self.root.destroy()

def main():
    import tkinter as tk
    import cv2
    cv2.setNumThreads(2)
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
