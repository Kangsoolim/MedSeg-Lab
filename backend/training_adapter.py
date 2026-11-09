"""Versioned adapter around exact vendored Stage 7 computational primitives.

Changes from the course orchestrator are explicit: configurable LR/budget,
bounded engineering epochs, local event transport, and local checkpoints.
Network, loss, batching, AMP policy and native 3D validation stay unchanged.
"""
import hashlib
import importlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Protocol
from backend.config import ROOT, read, run_path, sha, write

VERSION = 'monai-resunet-v1'
VENDOR = ROOT/'backend/vendor/training'


class TrainingAdapter(Protocol):
    def validate_configuration(self): ...
    def prepare_dataset(self): ...
    def initialize_model(self): ...
    def train(self): ...
    def validate(self, epoch): ...
    def emit_events(self, kind, **payload): ...
    def save_checkpoint(self, name): ...
    def resume(self): ...
    def request_stop(self): ...
    def export_results(self): ...


def source_hashes():
    result={name:sha(VENDOR/name) for name in read(VENDOR/'SOURCES.json')}
    for name in ('training_adapter.py','training_worker.py','training_data.py','training_contracts.py'):
        result['backend/'+name]=sha(ROOT/'backend'/name)
    return result


def primitives():
    sys.path.insert(0,str(VENDOR))
    module=importlib.import_module('src.unet_pipeline')
    if not Path(module.__file__).resolve().is_relative_to(VENDOR):
        raise RuntimeError('Unexpected training module origin')
    return module


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def signature(config, data, code):
    learning={k:v for k,v in config.items() if k not in ('epochs','checkpoint_policy','preview_every')}
    return digest(dict(config=learning,data=data,code=code,version=VERSION))


def validate_checkpoint_state(saved,device):
    """Reject malformed/nonfinite native state before an expensive task starts."""
    import math
    import torch
    try:
        p=primitives()
        from backend.training_contracts import TrainingConfig
        config=TrainingConfig(**saved['config']).model_dump()
        if (saved.get('schema_version')!=3 or saved.get('adapter')!=VERSION or saved.get('boundary')!='completed_epoch'
                or config!=saved['config'] or saved.get('signature')!=signature(config,saved['data'],saved['code'])
                or saved.get('scheduler_state_dict') is not None):
            raise ValueError('Checkpoint configuration/signature mismatch')
        state=saved['state']
        p.check_state_counters(state)
        for key in ('epoch','best_epoch','bad_epochs'):
            if type(state[key]) is not int or state[key]<0:raise ValueError('Invalid epoch/selection counter')
        if state['epoch']>config['epochs'] or state['best_epoch']>state['epoch']:
            raise ValueError('Invalid checkpoint epoch boundary')
        if saved.get('schedule')!=dict(batch_order='global_batch_shuffle',schedule_seed=600042,epoch=state['epoch']):
            raise ValueError('Checkpoint sampling boundary mismatch')
        history=state['history']
        if not isinstance(history,list) or [v['epoch'] for v in history]!=list(range(1,state['epoch']+1)):
            raise ValueError('Incomplete checkpoint epoch history')
        best,reference,best_epoch,bad=-1.,-1.,0,0
        for point in history:
            metrics=point['metrics'];score=metrics['val_mean_dice']
            if not 0<=score<=1 or any(not math.isfinite(v) for v in metrics.values()):
                raise ValueError('Invalid checkpoint metrics')
            if score>best:best,best_epoch=score,point['epoch']
            if score>reference+config['min_delta']:reference,bad=score,0
            else:bad+=1
        if (state['best_mean_dice'],state['best_epoch'],state['patience_reference'],state['bad_epochs'])!=(best,best_epoch,reference,bad):
            raise ValueError('Checkpoint model-selection state mismatch')
        if not history and any(state[k] for k in p.COUNTER_KEYS):raise ValueError('Updates without committed epoch')
        if history:
            for key in ('global_step','optimizer_updates','batch_attempts','amp_skipped_steps'):
                if history[-1]['metrics'][key]!=state[key]:raise ValueError('Checkpoint/history update counter mismatch')
        model=p.build_unet()
        model.load_state_dict(saved['model_state_dict'],strict=True)
        optimizer=torch.optim.Adam(model.parameters(),lr=config['learning_rate'])
        expected_groups=optimizer.state_dict()['param_groups']
        if saved['optimizer_state_dict']['param_groups']!=expected_groups:
            raise ValueError('Adam settings differ from recorded training configuration')
        optimizer.load_state_dict(saved['optimizer_state_dict'])
        for value in saved['model_state_dict'].values():
            if not torch.isfinite(value).all():raise ValueError('Nonfinite model tensor')
        optimizer_state=saved['optimizer_state_dict']['state']
        parameters=list(model.parameters())
        if state['global_step'] and set(optimizer_state)!=set(range(len(parameters))):
            raise ValueError('Missing optimizer parameter state')
        for index,item in optimizer_state.items():
            if index not in range(len(parameters)):raise ValueError('Unknown optimizer parameter state')
            if (set(item)!={'step','exp_avg','exp_avg_sq'} or item['exp_avg'].shape!=parameters[index].shape
                    or item['exp_avg_sq'].shape!=parameters[index].shape or item['step'].numel()!=1
                    or float(item['step'])!=state['global_step']):
                raise ValueError('Adam moment shape or update counter mismatch')
            for value in item.values():
                if isinstance(value,torch.Tensor) and not torch.isfinite(value).all():raise ValueError('Nonfinite optimizer tensor')
        scale=saved['scaler_state_dict']
        if bool(scale)!=bool(saved['config']['amp'] and device=='cuda'):raise ValueError('AMP precision mismatch')
        if scale and (set(scale)!={'scale','growth_factor','backoff_factor','growth_interval','_growth_tracker'}
                or not all(math.isfinite(scale[k]) for k in ('scale','growth_factor','backoff_factor'))
                or scale['scale']<=0 or scale['growth_factor']<=1 or not 0<scale['backoff_factor']<1
                or type(scale['growth_interval']) is not int or scale['growth_interval']<1
                or type(scale['_growth_tracker']) is not int or not 0<=scale['_growth_tracker']<scale['growth_interval']):
            raise ValueError('Invalid AMP scale/backoff/growth state')
        if not isinstance(saved['rng'],dict) or not all(k in saved['rng'] for k in ('python','torch','cuda','numpy')):
            raise ValueError('Missing RNG state')
        previous=p.capture_rng()
        try:
            if len(saved['rng']['cuda'])!=len(previous['cuda']):raise ValueError('CUDA RNG device count mismatch')
            p.restore_rng(saved['rng'])
        finally:p.restore_rng(previous)
    except (KeyError,TypeError,RuntimeError,ValueError,AttributeError,IndexError) as error:
        raise ValueError('Checkpoint model/optimizer/RNG state invalid / 权重模型、优化器或随机状态无效') from error


def inherited_best(checkpoint,saved):
    """A crash between best and last publication must leave the old best usable."""
    if not saved['state']['best_epoch']:return None
    import torch
    for name in ('best.pt','best.previous.pt'):
        candidate=run_path(ROOT/'runs',Path(checkpoint).parent/name)
        if not candidate.exists():continue
        try:payload=torch.load(candidate,map_location='cpu',weights_only=True)
        except Exception:continue
        if (payload.get('signature')==saved['signature'] and payload.get('state',{}).get('epoch')==saved['state']['best_epoch']
                and payload.get('state',{}).get('best_mean_dice')==saved['state']['best_mean_dice']):
            return candidate
    raise ValueError('Matching inherited best checkpoint unavailable / 匹配的继承最佳权重不可用')


class EventWriter:
    """One process owns a run; each committed sequence is an atomic JSON file."""
    def __init__(self, directory):
        self.directory=run_path(ROOT/'runs',Path(directory))
        self.events=run_path(ROOT/'runs',self.directory/'events')
        self.events.mkdir(exist_ok=True)
        self.sequence=max([int(p.stem) for p in self.events.glob('*.json')]+[0])

    def emit(self, kind, epoch=0, step=None, **payload):
        from backend.service import now
        self.sequence+=1
        event=dict(schema_version=2,run_id=self.directory.name,sequence=self.sequence,
                   event_id=f'{self.directory.name}:{self.sequence}',timestamp=now(),event_type=kind,epoch=epoch,step=step,**payload)
        from backend.training_contracts import LiveTrainingEvent
        LiveTrainingEvent.model_validate(event)
        write(run_path(ROOT/'runs',self.events/f'{self.sequence:09d}.json'),event)
        return event


class MonaiResidualUNet:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.spec=read(directory/'spec.json')
        self.config=self.spec['config']
        self.data=self.spec['data']
        self.writer=EventWriter(directory)
        self.p=primitives()
        import torch
        self.torch=torch
        self.device=torch.device(self.config['device'])
        self.started=time.perf_counter()

    def emit_events(self, kind, **payload):
        return self.writer.emit(kind,**payload)

    def validate_configuration(self):
        from backend.training_contracts import TrainingConfig
        TrainingConfig(**self.config)
        if self.device.type=='cuda' and not self.torch.cuda.is_available():
            raise ValueError('CUDA unavailable / CUDA不可用')
        if source_hashes()!=self.spec['code']:
            raise ValueError('Training code changed since preflight / 预检后训练代码已变化')
        for entry in self.data['entries'].values():
            for key in ('ct','gt'):
                if sha(entry[key])!=entry[key+'_sha256']:
                    raise ValueError('Training input changed / 训练输入已变化')

    def prepare_dataset(self):
        from src.unet_data import prepare_pair
        from src.common.io_spatial import load_case
        entries=self.data['entries']
        ids=self.data['train_ids']
        emit=self.emit_events
        class Dataset:
            case_ids=ids
            def load_patient(self,index):
                cid=ids[index]
                emit('log',message='Preparing training CT/GT / 预处理训练CT与GT',case_id=cid)
                case=load_case(entries[cid]['ct'],entries[cid]['gt'])
                pair,meta=prepare_pair(case)
                return case,pair,meta
        self.dataset=Dataset()

    def initialize_model(self):
        t=self.torch
        t.set_num_threads(min(4,os.cpu_count() or 1))
        self.p.set_seed(self.config['seed'])
        if self.device.type=='cuda':
            t.backends.cuda.matmul.allow_tf32=False
            t.backends.cudnn.allow_tf32=False
        self.model=self.p.build_unet().to(self.device)
        self.optimizer=t.optim.Adam(self.model.parameters(),lr=self.config['learning_rate'])
        self.scaler=t.amp.GradScaler('cuda',enabled=self.config['amp'])
        self.state=dict(epoch=0,global_step=0,best_mean_dice=-1.,best_epoch=0,patience_reference=-1.,bad_epochs=0,history=[],
                        optimizer_updates=0,batch_attempts=0,amp_skipped_steps=0,consecutive_amp_skips=0)
        self.emit_events('log',message='Model initialized / 模型已初始化',device=str(self.device),environment=self.p.environment())

    def save_checkpoint(self,name):
        self.p.check_state_counters(self.state)
        payload=dict(schema_version=3,adapter=VERSION,boundary='completed_epoch',state=self.state,
                     model_state_dict=self.model.state_dict(),optimizer_state_dict=self.optimizer.state_dict(),
                     scaler_state_dict=self.scaler.state_dict(),scheduler_state_dict=None,rng=self.p.capture_rng(),
                     config=self.config,data=self.data,code=self.spec['code'],environment=self.p.environment(),
                     signature=signature(self.config,self.data,self.spec['code']),
                     schedule=dict(batch_order='global_batch_shuffle',schedule_seed=600042,epoch=self.state['epoch']),run_id=self.directory.name)
        target=run_path(ROOT/'runs',self.directory/name)
        temp=run_path(ROOT/'runs',target.with_name('.'+name+'.'+uuid.uuid4().hex+'.tmp'))
        with temp.open('xb') as stream:
            self.torch.save(payload,stream);stream.flush();os.fsync(stream.fileno())
        if name=='best.pt' and target.exists():
            import shutil
            previous=run_path(ROOT/'runs',self.directory/'best.previous.pt')
            previous_temp=run_path(ROOT/'runs',self.directory/('.best.previous.'+uuid.uuid4().hex+'.tmp'))
            with target.open('rb') as source,previous_temp.open('xb') as output:
                shutil.copyfileobj(source,output);output.flush();os.fsync(output.fileno())
            previous_temp.replace(previous)
        temp.replace(target)
        self.emit_events('checkpoint',epoch=self.state['epoch'],step=self.state['global_step'],checkpoint_reference=name,sha256=sha(target),boundary='completed_epoch')

    def resume(self):
        parent=self.spec.get('resume')
        if not parent:
            self.save_checkpoint('last.pt')
            return
        path=run_path(ROOT/'runs',Path(parent['path']))
        if sha(path)!=parent['sha256']:
            raise ValueError('Resume checkpoint hash mismatch / 恢复权重哈希不匹配')
        saved=self.torch.load(path,map_location='cpu',weights_only=True)
        validate_checkpoint_state(saved,str(self.device))
        expected=signature(self.config,self.data,self.spec['code'])
        if saved.get('signature')!=expected or saved.get('boundary')!='completed_epoch' or saved.get('environment')!=self.p.environment():
            raise ValueError('Incompatible checkpoint/configuration/environment / 权重配置或环境不兼容')
        if saved['state']['epoch']>=self.config['epochs'] or saved['state']['bad_epochs']>=self.config['patience']:
            raise ValueError('No remaining training budget or already early stopped / 无剩余轮次或已早停')
        self.model.load_state_dict(saved['model_state_dict'],strict=True)
        self.optimizer.load_state_dict(saved['optimizer_state_dict'])
        self.scaler.load_state_dict(saved['scaler_state_dict'])
        self.state=saved['state']
        self.p.check_state_counters(self.state)
        if any(not self.torch.isfinite(v).all() for v in saved['model_state_dict'].values()):
            raise ValueError('Nonfinite checkpoint / 权重含非有限值')
        self.p.restore_rng(saved['rng'])
        # Preserve the exact inherited best artifact, without relabeling its epoch.
        best=inherited_best(path,saved)
        if best is not None:
            target=run_path(ROOT/'runs',self.directory/'best.pt')
            with best.open('rb') as source,target.open('xb') as output:
                import shutil
                shutil.copyfileobj(source,output)
        self.save_checkpoint('last.pt')
        self.emit_events('resumed',epoch=self.state['epoch'],step=self.state['global_step'],parent_run_id=parent['run_id'],checkpoint_sha256=parent['sha256'],inherited_history=self.state['history'])

    def request_stop(self):
        return run_path(ROOT/'runs',self.directory/'STOP').exists()

    def validate(self,epoch):
        entries={cid:dict(image_relpath=e['ct'],label_relpath=e['gt']) for cid,e in self.data['entries'].items()}
        return self.p.validate_cases(self.model,'',entries,{'val':self.data['val_ids']},self.data['val_ids'],
                  run_path(ROOT/'runs',self.directory/f'validation_epoch_{epoch:03d}'),self.device,self.config['batch_size'],.5)

    def train(self):
        import logging
        from src.unet_schedule import shuffled_patient_batches
        adapter=self
        class Monitor(logging.Handler):
            def emit(self,record):
                if record.msg.startswith('epoch=%d step=%d attempt='):
                    a=record.args
                    adapter.emit_events('batch',epoch=a[0],step=a[1],batch_attempt=a[2],train_loss=a[3],optimizer_step_skipped=a[6],amp_scale=a[8],elapsed_seconds=time.perf_counter()-adapter.started)
        logger=logging.getLogger('medseg.training.'+self.directory.name)
        logger.setLevel(logging.INFO);logger.propagate=False
        logger.addHandler(Monitor())
        self.emit_events('status',status='running',epoch=self.state['epoch'])
        reason='max_epochs'
        for epoch in range(self.state['epoch']+1,self.config['epochs']+1):
            if self.request_stop():
                reason='user_stop_at_epoch_boundary';break
            self.emit_events('epoch_start',epoch=epoch,step=self.state['global_step'])
            before=next(self.model.parameters()).detach().clone()
            batches=shuffled_patient_batches(self.dataset,self.config['batch_size'],self.config['seed'],epoch,600042,
                     run_path(ROOT/'runs',self.directory/f'batch_order_epoch_{epoch:03d}.json'))
            history=self.p.train(self.model,batches,self.optimizer,self.p.DiceBCELoss(.5,.5),self.device,1,
                       logger=logger,start_epoch=epoch-1,global_step=self.state['global_step'],amp=self.config['amp'],scaler=self.scaler,
                       max_batches=self.config['max_train_batches'],batch_attempts=self.state['batch_attempts'],
                       amp_skipped_steps=self.state['amp_skipped_steps'],consecutive_amp_skips=self.state['consecutive_amp_skips'])
            if history['global_step']==self.state['global_step'] or self.torch.equal(before,next(self.model.parameters()).detach()):
                raise RuntimeError('No actual parameter update / 模型参数未实际更新')
            self.emit_events('log',epoch=epoch,message='Training finished; validating native volumes / 训练结束，验证原空间三维病例')
            validation=self.validate(epoch)
            self.emit_events('validation_end',epoch=epoch,val_mean_dice=validation['mean_dice'],case_count=validation['patient_count'],scope='native patient 3D Dice arithmetic mean')
            self.state.update(epoch=epoch,**{k:history[k] for k in self.p.COUNTER_KEYS})
            improved,early=self.p.update_selection(self.state,validation['mean_dice'],self.config['patience'],self.config['min_delta'])
            metrics=dict(train_loss=history['epochs'][0]['loss'],val_mean_dice=validation['mean_dice'],learning_rate=self.optimizer.param_groups[0]['lr'],
                         global_step=self.state['global_step'],batch_attempts=self.state['batch_attempts'],optimizer_updates=self.state['optimizer_updates'],
                         amp_skipped_steps=self.state['amp_skipped_steps'],elapsed_seconds=time.perf_counter()-self.started)
            point=dict(epoch=epoch,stage='engineering_smoke' if self.config['engineering_smoke'] else 'live_training',metrics=metrics,
                       flags=(['early_stopping'] if early else [])+(['empty_validation_prediction'] if any(r['pred_voxels']==0 for r in validation['rows']) else []),
                       patients=validation['rows'],best_epoch=self.state['best_epoch'],bad_epochs=self.state['bad_epochs'],
                       preview_available=epoch%self.config['preview_every']==0,parameters_updated=True)
            self.state['history'].append(point)
            if improved:self.save_checkpoint('best.pt')
            if self.config['checkpoint_policy']=='every_epoch':self.save_checkpoint(f'epoch_{epoch:03d}.pt')
            self.save_checkpoint('last.pt')
            self.emit_events('epoch_end',epoch=epoch,step=self.state['global_step'],point=point,early_stopping=early)
            if early:reason='early_stopping';break
            if self.request_stop():reason='user_stop_at_epoch_boundary';break
        logger.handlers.clear()
        self.reason=reason
        return 'stopped' if reason=='user_stop_at_epoch_boundary' else 'completed'

    def export_results(self):
        write(self.directory/'summary.json',dict(state=self.state,stop_reason=self.reason,elapsed_seconds=time.perf_counter()-self.started,
                                               device=str(self.device),engineering_smoke=self.config['engineering_smoke']))
