"""Bounded local sightings store; never silently falls back from NVMe."""
import sqlite3
import time
from pathlib import Path

class Store:
    def __init__(self, config):
        self.root = Path(config['storage_dir']).expanduser()
        if str(self.root).startswith('/mnt/nvme/') and not Path('/mnt/nvme').is_mount():
            raise RuntimeError('NVMe is not mounted; refusing to write sightings to the SD card')
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root/'sightings.sqlite3')
        self.db.execute('CREATE TABLE IF NOT EXISTS sightings (id INTEGER PRIMARY KEY, created REAL, label TEXT, name TEXT DEFAULT "", path TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, created REAL, kind TEXT, track INTEGER, label TEXT)')
        self.config = config
        self.prune()

    def event(self, event):
        self.db.execute('INSERT INTO events(created,kind,track,label) VALUES(?,?,?,?)',
                        (time.time(),event['event'],event['track'],event['label']))
        self.db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 1000)')
        self.db.commit()

    def add(self, label, image):
        stamp = time.time()
        name = f'{time.time_ns()}.jpg'
        image.thumbnail((320,240))
        image.save(self.root/name, quality=80)
        self.db.execute('INSERT INTO sightings(created,label,path) VALUES(?,?,?)',(stamp,label,name))
        self.db.commit()
        self.prune()

    def recent(self):
        return self.db.execute('SELECT id,created,label,name,path FROM sightings ORDER BY created DESC LIMIT 30').fetchall()

    def rename(self, ident, name):
        self.db.execute('UPDATE sightings SET name=? WHERE id=?',(name,ident))
        self.db.commit()

    def forget(self, ident):
        row = self.db.execute('SELECT path FROM sightings WHERE id=?',(ident,)).fetchone()
        if row:
            (self.root/row[0]).unlink(missing_ok=True)
            self.db.execute('DELETE FROM sightings WHERE id=?',(ident,))
            self.db.commit()

    def prune(self):
        cutoff = time.time()-self.config['unknown_retention_hours']*3600
        self.db.execute('DELETE FROM events WHERE created<?',(cutoff,))
        self.db.commit()
        for (ident,) in self.db.execute('SELECT id FROM sightings WHERE name="" AND created<?',(cutoff,)).fetchall():
            self.forget(ident)
        rows = self.db.execute('SELECT id,path,name FROM sightings ORDER BY created').fetchall()
        total = sum((self.root/path).stat().st_size for _,path,_ in rows if (self.root/path).exists())
        limit = self.config['max_storage_mb']*1024*1024
        for ident,path,name in rows:
            if total <= limit:
                break
            if not name:
                size = (self.root/path).stat().st_size if (self.root/path).exists() else 0
                self.forget(ident)
                total -= size
        if total > limit:
            raise RuntimeError('Saved sightings exceed storage budget; remove some saved sightings or increase the limit')
