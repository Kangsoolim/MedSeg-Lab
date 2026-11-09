"""Training contracts/state tests. Fixtures below are not research metrics."""
import os
import uuid
from pathlib import Path
from unittest.mock import patch
import pytest
pytest.importorskip('torch',reason='Optional neural test profile')
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import ROOT,settings,read,write,sha
from backend.training_adapter import EventWriter,source_hashes,signature,primitives
from backend.training_contracts import TrainingConfig
from backend.training_data import course_manifest,resolve
from backend.training_service import TrainingManager
from backend.service import Store,BusyError


@pytest.fixture
def store():
    cfg=settings();cfg['runs']=str(ROOT/'runs'/('training_unit_'+uuid.uuid4().hex))
    s=Store(cfg);s.training=TrainingManager(s)
    yield s
    s.training.close();s.close()


@pytest.mark.parametrize('patch_config',[
 {'learning_rate':-1},{'learning_rate':float('nan')},{'epochs':0},{'epochs':61},
 {'batch_size':0},{'batch_size':5},{'batch_size':1.5},{'device':'command'},
 {'device':'cpu','amp':True},{'min_delta':-1},{'patience':0},{'unknown':'bad'},
 {'max_train_batches':1},{'engineering_smoke':True,'epochs':4,'max_train_batches':1},
 {'engineering_smoke':True,'epochs':1},
])
def test_invalid_configuration(patch_config):
    with pytest.raises(ValueError):TrainingConfig(**patch_config)


def test_vendor_source_identity():
    for path,item in read(ROOT/'backend/vendor/training/SOURCES.json').items():
        assert sha(ROOT/'backend/vendor/training'/path)==item['sha256']
        assert sha(Path(settings()['source_root'])/path)==item['sha256']


def test_course_partition_and_heldout_guard(store):
    split,entries=course_manifest(store.cfg)
    assert [len(split[k]) for k in ('train','val','test')]==[29,6,6]
    assert not set(entries).intersection(split['test'])
    with pytest.raises(ValueError):resolve(store,TrainingConfig(train_ids=[split['test'][0]]),False)
    with pytest.raises(ValueError):resolve(store,TrainingConfig(train_ids=[split['train'][0]]*2),False)


def test_event_commit_cursor_and_restart(store):
    rid=str(uuid.uuid4());directory=store.training.path(rid);directory.mkdir()
    write(directory/'record.json',dict(run_id=rid,status='completed'))
    writer=EventWriter(directory)
    writer.emit('log',message='fixture, not training')
    writer.emit('log',message='fixture second event')
    resumed=EventWriter(directory);resumed.emit('terminal',status='completed')
    events=store.training.events(rid,1)
    assert [e['sequence'] for e in events]==[2,3]
    assert len({e['event_id'] for e in events})==2
    assert store.training.events(rid,3)==[]


def test_shared_admission_and_path_guards(store):
    store.active={'id':'fixture','kind':'inference'}
    from backend.training_contracts import ResumePreflight
    with pytest.raises(BusyError):store.training.preflight(ResumePreflight(config=TrainingConfig()))
    from backend.contracts import JobRequest
    store.active={'id':'fixture','kind':'training'}
    with pytest.raises(BusyError):store.submit(JobRequest(case_id='spleen_8',algorithm='unet_e17'))
    store.active=None
    for rid in ('../escape','NUL','bad'):
        with pytest.raises(ValueError):store.training.path(rid)
    with pytest.raises(ValueError):store.training.path(str(uuid.uuid4()),'../../escape')


def test_interrupted_recovery_keeps_checkpoint(store):
    rid=str(uuid.uuid4());directory=store.training.path(rid);directory.mkdir()
    checkpoint=directory/'last.pt';checkpoint.write_bytes(b'fixture, not a valid model')
    write(directory/'record.json',dict(run_id=rid,status='running',created_at='2026-01-01T00:00:00+00:00'))
    store.training=TrainingManager(store)
    assert store.training.record(rid)['status']=='interrupted'
    assert checkpoint.read_bytes()==b'fixture, not a valid model'
    assert store.training.events(rid)[0]['status']=='interrupted'


def test_graceful_request_is_persistent_intent(store):
    rid=str(uuid.uuid4());directory=store.training.path(rid);directory.mkdir()
    write(directory/'record.json',dict(run_id=rid,status='running'))
    store.active=dict(id=rid,kind='training',process=None)
    result=store.training.stop(rid)
    assert result['status']=='stopping' and (directory/'STOP').is_file()
    assert store.active is not None
    result=store.training.stop(rid,force=True)
    assert result['status']=='stopped' and store.active is None


def test_signature_learning_and_data_compatibility():
    c=TrainingConfig().model_dump();data={'fixture':'no research data'};code=source_hashes()
    original=signature(c,data,code)
    assert original==signature(dict(c,epochs=60,preview_every=2,checkpoint_policy='every_epoch'),data,code)
    assert original!=signature(dict(c,learning_rate=.002),data,code)
    assert original!=signature(c,{'fixture':'changed dataset'},code)


def test_early_stopping_reference_and_best_are_separate():
    p=primitives();state=dict(epoch=1,best_mean_dice=-1,best_epoch=0,patience_reference=-1,bad_epochs=0)
    assert p.update_selection(state,.5,2,.01)==(True,False)
    state['epoch']=2
    assert p.update_selection(state,.505,2,.01)==(True,False)
    assert state['best_epoch']==2 and state['bad_epochs']==1
    state['epoch']=3
    assert p.update_selection(state,.504,2,.01)==(False,True)


def test_training_api_security_and_no_implicit_start():
    cfg=settings();cfg['runs']=str(ROOT/'runs'/('training_api_'+uuid.uuid4().hex))
    with TestClient(create_app(cfg)) as client:
        assert client.get('/api/v1/training/runs').json()==[]
        assert client.post('/api/v1/training/runs',json={}).status_code==403
        client.headers['X-MedSeg-Token']=client.get('/api/v1/health').json()['token']
        assert client.post('/api/v1/training/runs',json={}).status_code==422
        assert client.get('/api/v1/training/runs').json()==[]
        assert client.get('/api/v1/training/runs/not-a-uuid').status_code==422


def test_cuda_unavailable_is_actionable(store):
    from backend.training_contracts import ResumePreflight
    with patch('torch.cuda.is_available',return_value=False),patch.object(store,'capacity'):
        with pytest.raises(ValueError,match='CUDA unavailable'):
            store.training.preflight(ResumePreflight(config=TrainingConfig()))


def test_training_record_recovers_durable_backup(store):
    rid=str(uuid.uuid4());directory=store.training.path(rid);directory.mkdir()
    write(directory/'record.json',dict(run_id=rid,status='completed'))
    (directory/'record.json').write_text('{broken',encoding='utf-8')
    assert store.training.record(rid)['status']=='completed'


def test_actual_failed_worker_exits_and_releases_shared_slot(store):
    # Deliberately malformed INTERNAL spec; no forward/metrics are claimed here.
    import threading,time
    rid=str(uuid.uuid4());directory=store.training.path(rid);directory.mkdir()
    write(directory/'spec.json',{'invalid_lifecycle_fixture':True})
    write(directory/'record.json',dict(run_id=rid,status='queued',created_at='2026-01-01T00:00:00+00:00',config={'engineering_smoke':True}))
    EventWriter(directory).emit('status',status='queued')
    store.active=dict(id=rid,kind='training',process=None)
    worker=threading.Thread(target=store.training._run,args=(rid,));worker.start();worker.join(timeout=40)
    assert not worker.is_alive()
    record=store.training.record(rid)
    assert record['status']=='failed' and record['exit_code']!=0
    assert store.active is None
    assert store.training.events(rid)[-1]['status']=='failed'
    import psutil
    assert not psutil.pid_exists(record['pid'])


def test_force_stops_actual_controlled_lifecycle_process(store):
    # This sleeping process is a lifecycle fixture, never a model-training PASS.
    import subprocess,sys,psutil
    rid=str(uuid.uuid4());directory=store.training.path(rid);directory.mkdir()
    write(directory/'record.json',dict(run_id=rid,status='running'))
    process=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)'],creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    store.worker_owner.assign(process)
    store.active=dict(id=rid,kind='training',process=process)
    store.training.stop(rid)
    assert process.poll() is None
    assert store.training.stop(rid,force=True)['status']=='stopped'
    assert process.poll() is not None and not psutil.pid_exists(process.pid)
    assert store.active is None


def test_hardlinked_training_artifact_is_rejected(store):
    rid=str(uuid.uuid4());directory=store.training.path(rid);directory.mkdir()
    original=directory/'original.json';original.write_text('{}')
    linked=directory/'linked.json'
    os.link(original,linked)
    try:
        with pytest.raises(ValueError):store.training.path(rid,'linked.json')
    finally:linked.unlink()


def test_supplied_patient_identity_conflict_is_rejected(store):
    config=TrainingConfig(train_ids=['spleen_56'],val_ids=['spleen_9'],patient_ids={'spleen_56':'person-A','spleen_9':'PERSON-A'})
    with pytest.raises(ValueError,match='Patient identity overlaps'):resolve(store,config,False)


def test_checkpoint_rejects_invalid_model_optimizer_rng():
    from backend.training_adapter import validate_checkpoint_state
    with pytest.raises(ValueError,match='Checkpoint model'):
        validate_checkpoint_state({'state':{}},'cpu')


def test_import_cannot_shadow_live_training_identity(store):
    from backend.experiments import HistoryImport,import_history
    rid=str(uuid.uuid4());directory=store.training.path(rid);directory.mkdir()
    write(directory/'record.json',dict(run_id=rid,status='completed'))
    body=HistoryImport(experiment_id=rid,format='json',source_name='identity collision fixture',
        content='[{"epoch":1,"metric_name":"fixture","metric_value":0.25}]',
        definitions={'fixture':dict(definition='Controlled collision fixture, not model training',unit='fixture',aggregation='fixture')})
    with pytest.raises(BusyError):import_history(store,body)


def test_history_exposes_actual_running_event_not_stale_preparing(store):
    rid=str(uuid.uuid4());directory=store.training.path(rid);directory.mkdir()
    write(directory/'record.json',dict(run_id=rid,status='preparing'))
    EventWriter(directory).emit('status',status='running')
    assert store.training.get(rid)['status']=='running'
    store.training.stop(rid)
    assert store.training.get(rid)['status']=='stopping'


def test_best_last_interruption_window_uses_previous_best(store):
    # Checkpoint selection fixture only; these are deliberately not real metrics.
    import torch
    from backend.training_adapter import inherited_best
    rid=str(uuid.uuid4());directory=store.training.path(rid);directory.mkdir()
    saved=dict(signature='fixture',state=dict(best_epoch=1,best_mean_dice=.5))
    torch.save(dict(signature='fixture',state=dict(epoch=2,best_mean_dice=.6)),directory/'best.pt')
    torch.save(dict(signature='fixture',state=dict(epoch=1,best_mean_dice=.5)),directory/'best.previous.pt')
    assert inherited_best(directory/'last.pt',saved).name=='best.previous.pt'
    assert inherited_best(directory/'last.pt',dict(signature='fixture',state=dict(best_epoch=0))) is None


def test_resume_projection_retains_checkpoint_history_missing_parent_event(store):
    # Telemetry gap fixture: no model step or measured research score is claimed.
    parent,child=str(uuid.uuid4()),str(uuid.uuid4())
    config=TrainingConfig().model_dump()
    for rid,pid in [(parent,None),(child,parent)]:
        directory=store.training.path(rid);directory.mkdir()
        write(directory/'record.json',dict(run_id=rid,status='completed',config=config,parent_run_id=pid,
            source_kind='resumed_training' if pid else 'live_training',created_at='2026-01-01T00:00:00+00:00',
            started_at=None,ended_at=None,train_ids=['fixture-train'],val_ids=['fixture-val'],split_id='fixture',code={},stop_reason='fixture'))
        resume=dict(run_id=parent,path=str(store.training.path(parent,'last.pt')),sha256='fixture-only',epoch=1) if pid else None
        write(directory/'spec.json',dict(resume=resume))
        EventWriter(directory)
    point=dict(epoch=1,stage='UNIT FIXTURE, NOT TRAINING',metrics={'val_mean_dice':.5},flags=[],bad_epochs=0)
    EventWriter(store.training.path(child)).emit('resumed',epoch=1,inherited_history=[point])
    result=store.training.projection(child)
    assert len(result['epochs'])==1 and result['epochs'][0]['epoch']==1
    assert result['epochs'][0]['sources']['val_mean_dice']['sha256']=='fixture-only'
