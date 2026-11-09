"""Single-worker persistent job store with OS ownership and actual termination."""
import atexit
import json
import os
import stat
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from backend.config import ROOT, read, read_durable, run_path, sha, validate_input, write
from backend.process_owner import WorkerOwner
from backend.runtime import process_runtime

def now(): return datetime.now(timezone.utc).isoformat()

class BusyError(ValueError): pass

class Store:
    def __init__(self, cfg):
        self.cfg = cfg
        self.root = run_path(ROOT/'runs', Path(cfg['runs']).absolute())
        if not self.root.is_relative_to(ROOT/'runs'):
            raise ValueError('Run storage must remain within MedSeg-Lab/runs')
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.active = None
        self.closed = False
        self.token = secrets.token_urlsafe(32)
        self.ownership = self.path('.service.lock').open('a+b')
        self.ownership.seek(0)
        self.ownership.write(b'1'); self.ownership.flush(); self.ownership.seek(0)
        if sys.platform == 'win32':
            import msvcrt
            try:msvcrt.locking(self.ownership.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:self.ownership.close();raise
        else:
            import fcntl
            fcntl.flock(self.ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # A worker from a crashed service may still exist. Recover only after
        # stopping the exact recorded PID with matching process start time.
        self.worker_owner=WorkerOwner()
        self.storage_warnings=[]
        for f in self.root.glob('*/record.json'):
            try:record = read_durable(self.root,f)
            except (ValueError,OSError):
                # A damaged entry must not prevent all other history from opening.
                self.storage_warnings.append(str(f))
                continue
            if record['status'] in ('queued','running'):
                self.stop_orphan(record)
                record.update(status='failed', ended_at=now(), error={'message':'Service restarted; interrupted job stopped. Partial results are not published.'})
                write(f, record)
        from backend.index import DerivedIndex
        self.index = DerivedIndex(self)
        self.cases = self.catalog()
        atexit.register(self.close)

    def path(self,*parts):return run_path(self.root,self.root.joinpath(*parts))

    def stop_orphan(self, record):
        if record.get('pid') and record.get('process_created'):
            import psutil
            try:
                proc = psutil.Process(record['pid'])
                if abs(proc.create_time()-record['process_created']) < .01:
                    proc.kill(); proc.wait(timeout=10)
            except psutil.NoSuchProcess:
                pass

    def catalog(self):
        cases = {}
        index_path = ROOT/'frontend/public/demo/index.json'
        if index_path.exists():
            for entry in read(index_path)['cases']:
                manifest = read(ROOT/'frontend/public'/entry['manifest'])
                ct = manifest.get('ct_source',{}).get('path')
                if not ct: continue
                comparators = [dict(id=m['id'],name=m['name'],version=m['version'],color_key=m['color_key'],path=m['source']['path']) for m in manifest['methods']]
                case = dict(case_id=entry['case_id'], ct=ct, gt=(manifest.get('gt_source') or {}).get('path'),
                            spatial=manifest['spatial'], manifest='/'+entry['manifest'], comparators=comparators,
                            source_kind='frozen_catalog')
                seed_path = Path(self.cfg['source_root'])/'outputs/traditional'/f'{entry["case_id"]}_seed_roi.json'
                if self.cfg.get('source_root') and seed_path.exists():
                    values = read(seed_path)
                    case['reference_selection'] = {'seed':values['seed_ijk'], 'roi':values['roi_ijk_half_open']}
                cases[entry['case_id']] = case
        for f in self.path('inputs').glob('*/input.json'):
            try:entry = read_durable(self.root,f)
            except (ValueError,OSError):self.storage_warnings.append(str(f));continue
            if entry['case_id'] not in cases: cases[entry['case_id']] = entry
        return cases

    def register(self, request):
        from data_tools import export_package as ep
        from nibabel.orientations import apply_orientation
        from PIL import Image
        import numpy as np
        with self.lock:
            if request.case_id in self.cases: raise ValueError('Case ID already exists; choose a new ID')
            self.capacity()
            ct, data = validate_input(request.ct, self.cfg)
            if request.gt: validate_input(request.gt, self.cfg, ct, True)
            space = ep.spatial(ct)
            directory = self.path('inputs',request.case_id)
            directory.mkdir(parents=True, exist_ok=False)
            entry = dict(case_id=request.case_id, ct=str(Path(request.ct).resolve()), gt=str(Path(request.gt).resolve()) if request.gt else None,
                         spatial=space, comparators=[], source_kind='exploratory_import',
                         source_hashes={request.ct:sha(request.ct)}, manifest=None)
            arr = apply_orientation(data, np.array(space['to_ras_ornt']))
            (directory/'ct').mkdir()
            for k in range(arr.shape[2]):
                im = np.rint((np.clip(ep.display(arr,k),-100,200)+100)/300*255).astype(np.uint8)
                Image.fromarray(im).save(directory/'ct'/f'{k:03}.png')
            write(directory/'input.json', entry)
            self.cases[request.case_id] = entry
            return entry

    def capacity(self):
        files = [self.path(p.relative_to(self.root)) for p in self.root.glob('*/record.json')]
        used = self.inspect_tree(self.root)
        if len(files) >= self.cfg['max_records'] or used >= self.cfg['max_storage_bytes'] or shutil.disk_usage(self.root).free < 2*1024**3:
            raise ValueError('Run storage limit reached or less than 2 GiB free; explicitly export/delete old runs')
        return used

    def inspect_tree(self,directory):
        directory=self.path(Path(directory).relative_to(self.root))
        total=0
        for parent,dirs,files in os.walk(directory,followlinks=False):
            for name in dirs:self.path(Path(parent,name).relative_to(self.root))
            for name in files:
                info=Path(parent,name).lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024) or info.st_nlink>1:
                    raise ValueError('Links are forbidden in run storage')
                total+=info.st_size
        return total

    def record(self, rid):
        # UUID validation also rejects traversal and special Windows names.
        if str(uuid.UUID(rid)) != rid: raise ValueError('Invalid Run ID')
        path=self.path(rid,'record.json')
        return self.index.metadata(path) if hasattr(self,'index') and path.exists() else read_durable(self.root,path)

    def list(self):
        records=[]
        for p in self.root.glob('*/record.json'):
            try:records.append(self.get(p.parent.name))
            except (ValueError,OSError):continue
        return sorted(records,key=lambda r:r['created_at'],reverse=True)

    def get(self, rid):
        with self.lock:
            record = self.record(rid)
            if record['status'] == 'running':
                p = self.path(rid,'progress.json')
                if p.exists(): record['progress'] = read(p)
            log = self.path(rid,'worker.log')
            record['logs'] = log.read_text(encoding='utf-8', errors='replace')[-32000:] if log.exists() else ''
            return record

    def submit(self, request):
        from backend.algorithms import validate_selection
        with self.lock:
            if self.active: raise BusyError('Another job is active; finish or cancel it first')
            if request.case_id not in self.cases: raise ValueError('Unknown input case')
            self.capacity()
            entry = self.cases[request.case_id]
            p = request.parameters.model_dump()
            from backend.capabilities import capabilities
            available=capabilities(self.cfg)
            if not available[request.algorithm]:raise ValueError('Algorithm resource unavailable; see configuration status / 算法资源不可用，请检查配置状态')
            if request.algorithm == 'traditional_v2': validate_selection(entry['spatial']['shape'], p)
            # Header/data validation stays in the disposable worker. Submission
            # hashes bound compressed files and HTTP requests run in threadpool.
            from backend.config import input_path
            paths = [entry['ct']] + ([entry['gt']] if entry.get('gt') else []) + [m['path'] for m in entry.get('comparators',[])]
            input_path(entry['ct'], self.cfg)
            if entry.get('gt'): input_path(entry['gt'], self.cfg)
            hashes = {path:sha(path) for path in paths}
            rid = str(uuid.uuid4())
            directory = self.path(rid)
            directory.mkdir()
            spec = dict(run_id=rid,input=entry,case_id=request.case_id,algorithm=request.algorithm,parameters=p,
                        config=self.cfg,source_hashes=hashes,version='phase2a-v1',result_status='Interactive Experimental Run')
            write(directory/'spec.json',spec)
            record = dict(run_id=rid,case_id=request.case_id,algorithm=request.algorithm,parameters=p,
                          status='queued',created_at=now(),started_at=None,ended_at=None,error=None,
                          result_status='Interactive Experimental Run',spec_sha256=sha(directory/'spec.json'))
            write(directory/'record.json',record)
            self.active = {'id':rid, 'process':None}
            threading.Thread(target=self.run,args=(rid,),daemon=True).start()
            return record

    def run(self, rid):
        directory = self.path(rid)
        with self.lock:
            if self.record(rid)['status'] != 'queued': return
            log = self.path(rid,'worker.log').open('w',encoding='utf-8')
            process=None
            try:
                executable,environment=process_runtime()
                process = subprocess.Popen([executable,'-S','-B','-m','backend.worker',str(directory)],cwd=ROOT,env=environment,
                    stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
                self.worker_owner.assign(process)
                import psutil
                self.active.update(process=process, log=log)
                record = self.record(rid)
                record.update(status='running',started_at=now(),pid=process.pid,process_created=psutil.Process(process.pid).create_time())
                write(directory/'record.json', record)
            except Exception as error:
                self.worker_owner.close();self.worker_owner=WorkerOwner()
                if process and process.poll() is None:
                    process.kill();process.wait(timeout=10)
                log.close()
                record = self.record(rid)
                record.update(status='failed',ended_at=now(),error={'message':str(error)})
                write(directory/'record.json',record); self.active=None
                return
        try:
            process.wait(timeout=self.cfg['timeout_seconds'])
        except subprocess.TimeoutExpired:
            self.cancel(rid, reason='Resource time limit exceeded', failed=True)
        with self.lock:
            log.close()
            record = self.record(rid)
            if record['status'] == 'running':
                if process.returncode == 0 and (directory/'result.json').exists():
                    record.update(status='completed',result=read(directory/'result.json'),
                                  manifest=f'http://127.0.0.1:8008/api/v1/runs/{rid}/files/package/case.json')
                else:
                    record.update(status='failed',error=read(directory/'error.json') if (directory/'error.json').exists() else {'message':f'Worker exit code {process.returncode}'})
                record['ended_at'] = now(); write(directory/'record.json',record)
            if self.active and self.active['id'] == rid: self.active = None

    def cancel(self, rid, reason='Cancelled by user; worker stopped', failed=False):
        with self.lock:
            if self.active and self.active['id']==rid and self.active.get('kind')=='training':
                return self.training.stop(rid)
            record = self.record(rid)
            if record['status'] not in ('queued','running'): return self.get(rid)
            if self.active and self.active['id'] == rid:
                proc = self.active['process']
                if proc and proc.poll() is None:
                    self.worker_owner.close();self.worker_owner=WorkerOwner()
                    proc.terminate()
                    try: proc.wait(timeout=5)
                    except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
            record.update(status='failed' if failed else 'cancelled',ended_at=now(),error={'message':reason})
            write(self.root/rid/'record.json',record)
            # New jobs may start only once the old process has exited.
            self.active = None
            return self.get(rid)

    def close(self):
        with self.lock:
            if self.closed: return
            if self.active:
                if self.active.get('kind')=='training':self.training.close()
                else:self.cancel(self.active['id'], 'Service shut down; worker stopped')
            self.closed=True
            self.worker_owner.close()
            self.ownership.close()
