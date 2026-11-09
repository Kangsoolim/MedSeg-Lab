"""Training shares the inference admission lock and Windows worker ownership."""
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from backend.config import ROOT, read, read_durable, sha, write
from backend.runtime import process_runtime
from backend.process_owner import WorkerOwner
from backend.service import BusyError, now
from backend.training_adapter import EventWriter, source_hashes, signature
from backend.training_data import resolve

ACTIVE = {'queued','preparing','running','stopping'}
DEFINITIONS = {
    'train_loss':dict(definition='0.5 MONAI DiceLoss(sigmoid=True) + 0.5 BCEWithLogitsLoss',unit='loss',aggregation='sample-weighted finite forward attempts, including AMP skipped attempts'),
    'val_mean_dice':dict(definition='Binary native-volume Dice at sigmoid >= 0.5',unit='ratio',aggregation='arithmetic mean of patient 3D Dice, no slice averaging'),
    'learning_rate':dict(definition='Adam learning rate',unit='learning_rate',aggregation='optimizer parameter group 0'),
    'global_step':dict(definition='Actual optimizer updates',unit='updates',aggregation='cumulative'),
    'batch_attempts':dict(definition='Finite forward attempts',unit='batches',aggregation='cumulative'),
    'optimizer_updates':dict(definition='Actual optimizer updates',unit='updates',aggregation='cumulative'),
    'amp_skipped_steps':dict(definition='Native AMP skipped updates',unit='updates',aggregation='cumulative'),
    'elapsed_seconds':dict(definition='Observed wall time in current process',unit='seconds',aggregation='current session'),
}


class TrainingManager:
    def __init__(self, store):
        self.store=store
        self.root=store.path('training');self.root.mkdir(exist_ok=True)
        self.tickets={}
        for path in self.root.glob('*/record.json'):
            record=read_durable(store.root,store.path('training',path.parent.name,'record.json'))
            if record['status'] in ACTIVE:
                store.stop_orphan(record)
                record.update(status='interrupted',ended_at=now(),stop_reason='backend_interrupted')
                write(path,record)
                EventWriter(path.parent).emit('terminal',status='interrupted',stop_reason='backend_interrupted')

    def path(self,rid,*parts):
        if str(uuid.UUID(rid))!=rid:raise ValueError('Invalid Training Run ID / 训练Run ID无效')
        return self.store.path('training',rid,*parts)

    def events(self,rid,after=0,limit=500):
        self.record(rid)
        return self.store.index.events(rid,after,limit)

    def record(self,rid):
        path=self.path(rid,'record.json')
        return self.store.index.metadata(path) if path.exists() else read_durable(self.store.root,path)

    def get(self,rid):
        record=self.record(rid)
        if record['status'] in ('queued','preparing'):
            for path in sorted(self.path(rid,'events').glob('*.json')):
                event=read(self.path(rid,'events',path.name))
                if event.get('status')=='running':
                    record['status']='running'
                    break
        record['last_sequence']=self.store.index.last_sequence(rid)
        record['checkpoints']=[dict(name=p.name,bytes=p.stat().st_size) for p in self.path(rid).glob('*.pt') if self.path(rid,p.name).is_file()]
        return record

    def list(self):
        return sorted([self.get(p.parent.name) for p in self.root.glob('*/record.json')],key=lambda r:r['created_at'],reverse=True)

    def preflight(self,body):
        import psutil
        from backend.capabilities import capabilities
        if not capabilities(self.store.cfg)['training']:raise ValueError('Install optional neural runtime with Setup-Phase3B.ps1 -Neural / 请安装可选神经网络依赖')
        import torch
        config=body.config
        with self.store.lock:
            if self.store.active:raise BusyError('Another computation is active / 已有计算任务在运行')
            used=self.store.capacity()
            if len(list(self.root.glob('*/record.json')))>=100:raise ValueError('Training run limit reached / 训练记录达到上限')
            if config.device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA unavailable / CUDA不可用')
            data=resolve(self.store,config)
            code=source_hashes()
            # Global batch shuffle materializes all selected prepared tensors.
            slices=sum(e['canonical_slices'] for e in data['entries'].values() if e['role']=='train')
            ram=slices*2*256*256*4*2+1024**3
            if ram>psutil.virtual_memory().available:raise ValueError('Insufficient RAM for global batch shuffle / 全局批次打乱所需内存不足')
            ckpt_bytes=32*1024**2
            masks=sum(e['shape'][0]*e['shape'][1]*e['shape'][2] for e in data['entries'].values() if e['role']=='val')
            estimated=ckpt_bytes*(config.epochs if config.checkpoint_policy=='every_epoch' else 3)+config.epochs*(masks+8*1024**2)
            free=shutil.disk_usage(self.root).free
            if free<estimated+2*1024**3 or used+estimated>self.store.cfg['max_storage_bytes']:
                raise ValueError('Insufficient storage quota/free disk / 存储配额或磁盘空间不足')
            probe=self.store.path('training','.write-'+uuid.uuid4().hex)
            with probe.open('xb') as stream:stream.write(b'write-test')
            probe.unlink()
            resume=None
            if body.resume_run_id:
                parent=self.record(body.resume_run_id)
                if parent['status'] in ACTIVE:raise BusyError('Stop parent before resuming / 恢复前请先停止父任务')
                path=self.path(body.resume_run_id,body.checkpoint)
                try:saved=torch.load(path,map_location='cpu',weights_only=True)
                except Exception as error:
                    raise ValueError('Checkpoint is unreadable or incomplete / 权重无法读取或不完整') from error
                if not isinstance(saved,dict):raise ValueError('Invalid checkpoint payload / 权重内容无效')
                from backend.training_adapter import primitives
                if saved.get('schema_version')!=3 or saved.get('boundary')!='completed_epoch' or saved.get('signature')!=signature(config.model_dump(),data,code):
                    raise ValueError('Resume model/data/learning settings differ / 恢复模型、数据或训练配置不兼容')
                if saved.get('environment')!=primitives().environment():raise ValueError('Resume environment differs / 恢复环境不同')
                from backend.training_adapter import validate_checkpoint_state
                validate_checkpoint_state(saved,config.device)
                from backend.training_adapter import inherited_best
                inherited_best(path,saved)
                if saved['state']['epoch']>=config.epochs or saved['state']['bad_epochs']>=config.patience:
                    raise ValueError('Increase total epoch budget; early-stopped states cannot continue / 需增加总轮次，已早停状态不可继续')
                resume=dict(run_id=body.resume_run_id,path=str(path),sha256=sha(path),epoch=saved['state']['epoch'])
            ticket=uuid.uuid4().hex
            self.tickets={k:v for k,v in self.tickets.items() if time.monotonic()-v['time']<600}
            if len(self.tickets)>=20:raise BusyError('Too many unused preflights / 未使用预检过多')
            self.tickets[ticket]=dict(time=time.monotonic(),config=config.model_dump(),data=data,code=code,resume=resume)
            return dict(preflight_id=ticket,valid=True,expires_seconds=600,train_count=len(data['train_ids']),val_count=len(data['val_ids']),
                        estimated_output_bytes=estimated,available_disk_bytes=free,estimated_ram_bytes=ram,
                        device=config.device,gpu=torch.cuda.get_device_name(0) if config.device=='cuda' else None,
                        checks=['CT/GT spatial and binary validation','train/val disjoint, test excluded','code/data hashes','output writable, no overwrite','disk/RAM limits','single compute slot'],
                        warnings=['Patient identity independence is not established / 无法证明患者身份完全独立']+(['Engineering smoke; metrics are not formal course results / 工程短训练指标不属于正式课程结果'] if config.engineering_smoke else []),
                        resume_epoch=resume['epoch'] if resume else None)

    def start(self,body):
        with self.store.lock:
            for r in self.list():
                if r.get('request_id')==body.request_id:
                    if r['config']!=body.config.model_dump() or r['parent_run_id']!=body.resume_run_id:
                        raise BusyError('Request ID reused with different configuration / 同一请求ID对应不同配置')
                    return r
            if self.store.active:raise BusyError('Another computation is active / 已有计算任务在运行')
            ticket=self.tickets.get(body.preflight_id)
            if not ticket or time.monotonic()-ticket['time']>600:raise ValueError('Repeat preflight / 请重新预检')
            resume=ticket['resume']
            if ticket['config']!=body.config.model_dump() or (resume or {}).get('run_id')!=body.resume_run_id or (resume and Path(resume['path']).name!=body.checkpoint):
                raise ValueError('Preflight configuration changed / 预检配置已变化')
            if source_hashes()!=ticket['code']:raise ValueError('Code changed; repeat preflight / 代码已变更，请重新预检')
            if len(list(self.root.glob('*/record.json')))>=100:raise ValueError('Training run limit reached / 训练记录达到上限')
            rid=str(uuid.uuid4());directory=self.path(rid)
            if directory.exists() or self.store.path(rid).exists() or self.store.path('experiments',rid).exists():
                raise BusyError('Generated Run ID already exists; repeat submission / 生成的Run ID已存在，请重新提交')
            directory.mkdir(exist_ok=False)
            spec={k:ticket[k] for k in ('config','data','code','resume')}
            write(directory/'spec.json',spec)
            record=dict(run_id=rid,status='queued',created_at=now(),started_at=None,ended_at=None,request_id=body.request_id,
                        config=ticket['config'],train_ids=ticket['data']['train_ids'],val_ids=ticket['data']['val_ids'],
                        split_id=ticket['data']['split_id'],code=ticket['code'],parent_run_id=body.resume_run_id,
                        source_kind='resumed_training' if resume else 'live_training',stop_reason=None)
            write(directory/'record.json',record)
            EventWriter(directory).emit('status',status='queued')
            self.store.active=dict(id=rid,kind='training',process=None)
            self.tickets.pop(body.preflight_id)
            threading.Thread(target=self._run,args=(rid,),daemon=True).start()
            return record

    def _run(self,rid):
        directory=self.path(rid);process=None;log=None
        try:
            with self.store.lock:
                record=self.record(rid)
                if record['status'] not in ACTIVE:return
                if record['status']=='stopping':
                    record.update(status='stopped',ended_at=now(),stop_reason='user_stop_before_worker')
                    write(directory/'record.json',record)
                    EventWriter(directory).emit('terminal',status='stopped',stop_reason='user_stop_before_worker')
                    return
                executable,environment=process_runtime()
                environment.update(MPLCONFIGDIR=str(self.path(rid,'mpl')),PYTHONDONTWRITEBYTECODE='1')
                log=self.path(rid,'worker.log').open('w',encoding='utf-8')
                process=subprocess.Popen([executable,'-S','-B','-m','backend.training_worker',str(directory)],cwd=ROOT,env=environment,
                         stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
                self.store.worker_owner.assign(process)
                import psutil
                self.store.active.update(process=process)
                record.update(status='stopping' if record['status']=='stopping' else 'preparing',started_at=now(),pid=process.pid,process_created=psutil.Process(process.pid).create_time())
                write(directory/'record.json',record)
            # Bounded run lifetime; a browser disconnect does not affect this wait.
            process.wait(timeout=600 if record['config']['engineering_smoke'] else 21600)
            with self.store.lock:
                record=self.record(rid)
                if record['status'] in ACTIVE:
                    events=self.events(rid,0,None)
                    terminal=next((e for e in reversed(events) if e['event_type']=='terminal'),None)
                    status=terminal['status'] if terminal and process.returncode==0 else 'failed'
                    record.update(status=status,ended_at=now(),stop_reason=(terminal or {}).get('stop_reason','worker_exit'),exit_code=process.returncode)
                    write(directory/'record.json',record)
                    if not terminal:EventWriter(directory).emit('terminal',status='failed',stop_reason='unexpected_worker_exit')
        except Exception as error:
            with self.store.lock:
                if process and process.poll() is None:process.kill();process.wait(timeout=10)
                record=self.record(rid)
                if record['status'] in ACTIVE:
                    record.update(status='failed',ended_at=now(),stop_reason=type(error).__name__)
                    write(directory/'record.json',record)
                    EventWriter(directory).emit('terminal',status='failed',stop_reason=type(error).__name__)
        finally:
            if log:log.close()
            with self.store.lock:
                if self.store.active and self.store.active['id']==rid:
                    self.store.worker_owner.close()
                    self.store.worker_owner=WorkerOwner()
                    self.store.active=None

    def stop(self,rid,force=False,interrupted=False):
        with self.store.lock:
            record=self.record(rid)
            if record['status'] not in ACTIVE:return self.get(rid)
            if force:
                process=(self.store.active or {}).get('process')
                if not self.store.active or self.store.active['id']!=rid:raise ValueError('Worker ownership mismatch')
                owned=self.store.worker_owner.handle is not None
                self.store.worker_owner.close()
                self.store.worker_owner=WorkerOwner()
                if process and process.poll() is None:
                    if owned:
                        try:process.wait(timeout=5)
                        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                    else:process.kill();process.wait(timeout=10)
                record.update(status='interrupted' if interrupted else 'stopped',ended_at=now(),stop_reason='backend_interrupted' if interrupted else 'force_termination_lost_partial_epoch')
                write(self.path(rid,'record.json'),record)
                EventWriter(self.path(rid)).emit('terminal',status=record['status'],stop_reason=record['stop_reason'])
                self.store.active=None
            else:
                write(self.path(rid,'STOP'),{'requested_at':now()})
                # Worker is sole event writer while alive: no concurrent sequences.
                record.update(status='stopping',stop_requested_at=now())
                write(self.path(rid,'record.json'),record)
            return self.get(rid)

    def projection(self,rid):
        record=self.record(rid);events=self.store.index.projection_events(rid)
        points={e['epoch']:dict(e['point'],timestamp=e['timestamp'],sources={k:dict(path='events/'+f"{e['sequence']:09d}.json",definition=v['definition']) for k,v in DEFINITIONS.items()}) for e in events if e['event_type']=='epoch_end'}
        # Resume inherits history with explicit shared ancestry, never duplicated steps.
        if record['parent_run_id']:
            spec=read(self.path(rid,'spec.json'))
            restored=next((e for e in events if e['event_type']=='resumed' and 'inherited_history' in e),None)
            if restored:
                inherited={p['epoch']:dict(p,sources={k:dict(path=record['parent_run_id']+'/'+Path(spec['resume']['path']).name,sha256=spec['resume']['sha256']) for k in p['metrics']}) for p in restored['inherited_history']}
            else:
                parent=self.projection(record['parent_run_id'])
                inherited={p['epoch']:p for p in parent['epochs'] if p['epoch']<=spec['resume']['epoch']}
            points={**inherited,**points}
        checkpoints=[dict(path=e['checkpoint_reference'],sha256=e['sha256'],epoch=e['epoch'],boundary=e['boundary']) for e in events if e['event_type']=='checkpoint']
        summary_path=self.path(rid,'summary.json')
        summary=read(summary_path) if summary_path.exists() else None
        state=(summary or {}).get('state',{})
        reference=-1.
        for epoch in sorted(points):
            score=points[epoch]['metrics']['val_mean_dice']
            if score>reference+record['config']['min_delta']:reference=score
        last_batch=next((e for e in reversed(events) if e['event_type']=='batch'),None)
        # Running is projected from real worker events, while stop intent wins.
        status=record['status']
        if status in ('preparing','queued') and any(e.get('status')=='running' for e in events):status='running'
        return dict(schema_version=1,experiment_id=rid,run_id=rid,name=('Engineering Smoke Test · ' if record['config']['engineering_smoke'] else '')+rid,
            type='training',algorithm='MONAI 2D Residual U-Net',source_kind=record['source_kind'],status=status,
            created_at=record['created_at'],started_at=record['started_at'],ended_at=record['ended_at'],dataset=record['config']['dataset'],
            split_id=record['split_id'],case_ids=record['val_ids'],train_case_ids=record['train_ids'],hyperparameters=record['config'],
            device=record['config']['device'],code_version=record['code'],definitions=DEFINITIONS,epochs=list(sorted(points.values(),key=lambda p:p['epoch'])),
            sources=[dict(path='spec.json',sha256=sha(self.path(rid,'spec.json')))],checkpoints=checkpoints,
            lineage=[dict(parent=record['parent_run_id'],child=rid,through_epoch=read(self.path(rid,'spec.json'))['resume']['epoch'],relation='epoch_boundary_resume')] if record['parent_run_id'] else [],
            early_stopping=dict(monitor='val_mean_dice',mode='max',patience=record['config']['patience'],min_delta=record['config']['min_delta'],
                    best_epoch=state.get('best_epoch',max(points.values(),key=lambda p:p['metrics']['val_mean_dice'])['epoch'] if points else 0),bad_epochs=state.get('bad_epochs',points[max(points)]['bad_epochs'] if points else 0),patience_reference=state.get('patience_reference',reference),stop_reason=record['stop_reason']),
            latest_batch=last_batch,stop_reason=record['stop_reason'],warnings=['Patient identity independence not established','Engineering test metrics are not official course results'] if record['config']['engineering_smoke'] else ['Patient identity independence not established'])

    def close(self):
        with self.store.lock:
            if self.store.active and self.store.active.get('kind')=='training':self.stop(self.store.active['id'],force=True,interrupted=True)
