"""Rebuildable SQLite derived cache. Atomic JSON files remain authoritative.

Every refresh walks event entries and rejects links before trusting cached data.
No TTL: changed/deleted files are reconciled in one transaction. Atomic replacement
is detected through ctime/mtime/size. Readers never publish uncommitted temp files.
"""
import json
import re
import sqlite3
import stat
import threading
from backend.config import read, run_path

def recover_database(method):
    def wrapped(self,*args,**kwargs):
        with self.lock:
            try:return method(self,*args,**kwargs)
            except sqlite3.DatabaseError:
                self.discard()
                return method(self,*args,**kwargs)
    return wrapped

class DerivedIndex:
    def __init__(self,store):
        self.store=store
        self.path=store.path('.derived-index.sqlite3')
        self.lock=threading.RLock()

    def discard(self):
        # All connections are short-lived under this lock; remove derived files only.
        for suffix in ('','-journal','-wal','-shm'):
            self.store.path(self.path.name+suffix).unlink(missing_ok=True)

    def connect(self):
        # Validate all possible SQLite auxiliary paths before opening the DB.
        for suffix in ('','-journal','-wal','-shm'):
            self.store.path(self.path.name+suffix)
        try:
            db=sqlite3.connect(self.path,timeout=10)
            db.execute('CREATE TABLE IF NOT EXISTS events (run TEXT, sequence INTEGER, stamp TEXT, kind TEXT, payload TEXT, PRIMARY KEY(run,sequence))')
            db.execute('CREATE TABLE IF NOT EXISTS metadata (path TEXT PRIMARY KEY, stamp TEXT, payload TEXT)')
            return db
        except sqlite3.DatabaseError:
            if 'db' in locals():db.close()
            # Only our exact derived database is removed, never source records.
            self.discard()
            db=sqlite3.connect(self.path,timeout=10)
            db.execute('CREATE TABLE events (run TEXT, sequence INTEGER, stamp TEXT, kind TEXT, payload TEXT, PRIMARY KEY(run,sequence))')
            db.execute('CREATE TABLE metadata (path TEXT PRIMARY KEY, stamp TEXT, payload TEXT)')
            return db

    @staticmethod
    def stamp(info):return f'{info.st_mtime_ns}:{info.st_ctime_ns}:{info.st_size}'

    def sync(self,db,rid):
        directory=self.store.training.path(rid,'events')
        existing=dict(db.execute('SELECT sequence,stamp FROM events WHERE run=?',(rid,)))
        found=set()
        if directory.exists():
            import os
            with os.scandir(directory) as entries:
                for entry in entries:
                    if not re.fullmatch(r'\d{9,}\.json',entry.name):continue
                    info=entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink>1 or getattr(info,'st_file_attributes',0)&1024:
                        raise ValueError('Links or non-files forbidden in event index')
                    seq=int(entry.name[:-5]);found.add(seq);stamp=self.stamp(info)
                    if existing.get(seq)==stamp:continue
                    path=directory/entry.name
                    event=read(path)
                    from backend.training_contracts import LiveTrainingEvent
                    LiveTrainingEvent.model_validate(event)
                    if event['run_id']!=rid or event['sequence']!=seq:raise ValueError('Event source identity mismatch')
                    db.execute('INSERT OR REPLACE INTO events VALUES (?,?,?,?,?)',(rid,seq,stamp,event['event_type'],json.dumps(event,allow_nan=False)))
        for seq in existing.keys()-found:db.execute('DELETE FROM events WHERE run=? AND sequence=?',(rid,seq))

    @recover_database
    def query(self,rid,after=0,limit=None,projection=False):
        with self.lock:
            db=self.connect()
            try:
                with db:
                    self.sync(db,rid)
                    sql='SELECT payload FROM events WHERE run=? AND sequence>?'
                    args=[rid,after]
                    if projection:
                        sql+=" AND (kind IN ('epoch_end','checkpoint','resumed','status') OR sequence=(SELECT max(sequence) FROM events WHERE run=? AND kind='batch'))"
                        args.append(rid)
                    sql+=' ORDER BY sequence'
                    if limit is not None:sql+=' LIMIT ?';args.append(limit)
                    return [json.loads(row[0]) for row in db.execute(sql,args)]
            finally:db.close()

    def events(self,rid,after=0,limit=500):return self.query(rid,after,limit)
    def projection_events(self,rid):return self.query(rid,projection=True)
    @recover_database
    def last_sequence(self,rid):
        with self.lock:
            db=self.connect()
            try:
                with db:
                    self.sync(db,rid)
                    return db.execute('SELECT coalesce(max(sequence),0) FROM events WHERE run=?',(rid,)).fetchone()[0]
            finally:db.close()

    def metadata_many(self,paths):
        return self._metadata_many(tuple(paths))

    @recover_database
    def _metadata_many(self,paths):
        # One SQLite transaction per catalog, with source/path checks per entry.
        with self.lock:
            db=self.connect()
            try:
                result=[]
                with db:
                    for path in paths:
                        path=run_path(self.store.root,path)
                        from backend.config import read_durable
                        if not path.exists():
                            result.append(read_durable(self.store.root,path));continue
                        stamp=self.stamp(path.stat());key=str(path.relative_to(self.store.root))
                        row=db.execute('SELECT stamp,payload FROM metadata WHERE path=?',(key,)).fetchone()
                        if row and row[0]==stamp:result.append(json.loads(row[1]));continue
                        value=read_durable(self.store.root,path)
                        db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?,?)',(key,stamp,json.dumps(value)))
                        result.append(value)
                return result
            finally:db.close()

    def metadata(self,path):return self.metadata_many([path])[0]
