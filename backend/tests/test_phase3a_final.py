"""Independent Phase3A final acceptance fixtures; never research measurements."""
import copy
import uuid
import time
from pathlib import Path
from unittest.mock import patch
import pytest
torch=pytest.importorskip('torch',reason='Optional neural test profile')
from backend.config import ROOT,settings,write,read
from backend.training_adapter import primitives,signature,validate_checkpoint_state,EventWriter
from backend.training_contracts import TrainingConfig
from backend.training_contracts import StartTraining,ResumePreflight
from backend.service import Store,BusyError
from backend.training_service import TrainingManager
from backend.training_adapter import source_hashes


@pytest.fixture(scope='module')
def valid_state():
    torch.set_num_threads(4)
    p=primitives();model=p.build_unet();optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    config=TrainingConfig(device='cpu',amp=False,epochs=1,engineering_smoke=True,max_train_batches=1).model_dump()
    data={'acceptance_fixture':True};code={'fixture':'not a research run'}
    return dict(schema_version=3,adapter='monai-resunet-v1',boundary='completed_epoch',
        model_state_dict=model.state_dict(),optimizer_state_dict=optimizer.state_dict(),scaler_state_dict={},scheduler_state_dict=None,
        config=config,data=data,code=code,signature=signature(config,data,code),rng=p.capture_rng(),
        schedule=dict(batch_order='global_batch_shuffle',schedule_seed=600042,epoch=0),
        state=dict(epoch=0,global_step=0,best_mean_dice=-1.,best_epoch=0,patience_reference=-1.,bad_epochs=0,history=[],
                   optimizer_updates=0,batch_attempts=0,amp_skipped_steps=0,consecutive_amp_skips=0))


def test_native_checkpoint_accepts_valid_initial_state(valid_state):
    validate_checkpoint_state(copy.deepcopy(valid_state),'cpu')


@pytest.mark.parametrize('damage',[
 'rng_torch','rng_python','rng_numpy','optimizer_lr','optimizer_betas','epoch_negative',
 'best_epoch_future','negative_patience','schedule_epoch','signature_config','scheduler',
 'amp_backoff','amp_growth','amp_tracker',
])
def test_native_checkpoint_rejects_corrupt_state(valid_state,damage):
    value=copy.deepcopy(valid_state)
    if damage=='rng_torch':value['rng']['torch']=torch.zeros(1,dtype=torch.uint8)
    elif damage=='rng_python':value['rng']['python']=None
    elif damage=='rng_numpy':value['rng']['numpy']['keys']=torch.zeros(1,dtype=torch.int64)
    elif damage=='optimizer_lr':value['optimizer_state_dict']['param_groups'][0]['lr']=.002
    elif damage=='optimizer_betas':value['optimizer_state_dict']['param_groups'][0]['betas']=(.1,.2)
    elif damage=='epoch_negative':value['state']['epoch']=-1
    elif damage=='best_epoch_future':value['state']['best_epoch']=2
    elif damage=='negative_patience':value['state']['bad_epochs']=-1
    elif damage=='schedule_epoch':value['schedule']['epoch']=8
    elif damage=='signature_config':value['config']['learning_rate']=.002
    elif damage=='scheduler':value['scheduler_state_dict']={'unexpected_scheduler':True}
    else:
        value['config'].update(amp=True,device='cuda')
        value['signature']=signature(value['config'],value['data'],value['code'])
        value['scaler_state_dict']=dict(scale=65536.,growth_factor=2.,backoff_factor=.5,growth_interval=2000,_growth_tracker=0)
        key={'amp_backoff':'backoff_factor','amp_growth':'growth_factor','amp_tracker':'_growth_tracker'}[damage]
        value['scaler_state_dict'][key]={'amp_backoff':-1.,'amp_growth':.5,'amp_tracker':-1}[damage]
    with pytest.raises(ValueError):validate_checkpoint_state(value,'cuda' if damage.startswith('amp_') else 'cpu')


@pytest.fixture
def manager():
    cfg=settings();cfg['runs']=str(ROOT/'runs'/('final_unit_'+uuid.uuid4().hex))
    store=Store(cfg);store.training=TrainingManager(store)
    yield store.training
    store.training.close();store.close()


def admitted_request(manager):
    config=TrainingConfig(device='cpu',amp=False,epochs=1,engineering_smoke=True,max_train_batches=1)
    manager.tickets['UNIT_FIXTURE']=dict(time=time.monotonic(),config=config.model_dump(),code=source_hashes(),resume=None,
        data=dict(train_ids=['fixture-train'],val_ids=['fixture-val'],split_id=None,entries={}))
    return StartTraining(config=config,preflight_id='UNIT_FIXTURE',request_id=uuid.uuid4().hex,confirm='START REAL TRAINING')


def fixture_record(rid):
    return dict(run_id=rid,status='completed',created_at='2026-11-07T00:00:00+08:00',
                config={},parent_run_id=None,fixture='NOT MODEL TRAINING')


def test_start_rechecks_training_record_limit(manager):
    body=admitted_request(manager)
    for _ in range(100):
        rid=str(uuid.uuid4());directory=manager.path(rid);directory.mkdir();write(directory/'record.json',fixture_record(rid))
    with patch('threading.Thread.start'),pytest.raises(ValueError):manager.start(body)


@pytest.mark.parametrize('owner',['training','inference','import'])
def test_generated_run_id_cannot_shadow_any_existing_identity(manager,owner):
    body=admitted_request(manager);identifier=uuid.uuid4();rid=str(identifier)
    directory=manager.path(rid) if owner=='training' else manager.store.path(rid) if owner=='inference' else manager.store.path('experiments',rid)
    directory.mkdir(parents=True)
    write(directory/('experiment.json' if owner=='import' else 'record.json'),fixture_record(rid))
    with patch('backend.training_service.uuid.uuid4',return_value=identifier),patch('threading.Thread.start'),pytest.raises(ValueError):
        manager.start(body)


def test_graceful_stop_before_worker_launch_never_spawns_process(manager):
    body=admitted_request(manager)
    with patch('threading.Thread.start'):record=manager.start(body)
    rid=record['run_id'];manager.stop(rid)
    with patch('backend.training_service.subprocess.Popen',side_effect=AssertionError('Must not spawn after pre-worker stop')):
        manager._run(rid)
    assert manager.record(rid)['status']=='stopped'
    assert manager.store.active is None


def test_preflight_performs_one_complete_storage_safety_scan(manager):
    data=dict(train_ids=['fixture-train'],val_ids=['fixture-val'],entries={'train':dict(role='train',canonical_slices=1,shape=[1,1,1]),'val':dict(role='val',shape=[1,1,1])})
    config=TrainingConfig(device='cpu',amp=False,epochs=1,engineering_smoke=True,max_train_batches=1)
    with patch('backend.training_service.resolve',return_value=data),patch.object(manager.store,'inspect_tree',wraps=manager.store.inspect_tree) as scan:
        manager.preflight(ResumePreflight(config=config))
    assert scan.call_count==1


def test_retried_request_is_idempotent_and_changed_body_conflicts(manager):
    body=admitted_request(manager)
    with patch('threading.Thread.start'):
        first=manager.start(body)
        assert manager.start(body)['run_id']==first['run_id']
        changed=body.model_copy(update={'config':body.config.model_copy(update={'learning_rate':.002})})
        with pytest.raises(BusyError):manager.start(changed)


def test_http_long_sequence_pages_and_complete_export_ignore_uncommitted_files():
    from fastapi.testclient import TestClient
    from backend.app import create_app
    cfg=settings();cfg['runs']=str(ROOT/'runs'/('final_events_'+uuid.uuid4().hex))
    with TestClient(create_app(cfg)) as c:
        manager=c.app.state.store.training;rid=str(uuid.uuid4());directory=manager.path(rid);directory.mkdir()
        write(directory/'record.json',fixture_record(rid))
        writer=EventWriter(directory)
        for index in range(2003):writer.emit('log',message='CONTROLLED LOG PAGINATION FIXTURE; NOT MODEL TRAINING',fixture_index=index)
        (directory/'events'/'999999999.json.tmp').write_text('{uncommitted',encoding='utf-8')
        all_events=[];cursor=0;pages=[]
        while True:
            value=c.get(f'/api/v1/training/runs/{rid}/events?after={cursor}').json()
            if not value['events']:break
            pages.append(len(value['events']));all_events.extend(value['events']);cursor=value['next_sequence']
        assert pages==[500,500,500,500,3]
        assert [e['sequence'] for e in all_events]==list(range(1,2004))
        assert c.get(f'/api/v1/training/runs/{rid}/events?after=500').json()['events']==all_events[500:1000]
        import json
        exported=[json.loads(line) for line in c.get(f'/api/v1/training/runs/{rid}/logs').text.splitlines()]
        assert exported==all_events


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='Windows Job Object descendant ownership')
def test_force_termination_stops_owned_descendant_processes(manager):
    import subprocess,sys,json,psutil
    from backend.runtime import process_runtime
    rid=str(uuid.uuid4());directory=manager.path(rid);directory.mkdir()
    write(directory/'record.json',dict(run_id=rid,status='running'))
    gate=directory/'go';pidfile=directory/'child.json'
    code="import sys,time,subprocess,json;from pathlib import Path;gate=Path(sys.argv[1]);pidfile=Path(sys.argv[2]);\nwhile not gate.exists():time.sleep(.01)\nchild=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)'],creationflags=subprocess.CREATE_NO_WINDOW);pidfile.write_text(json.dumps({'pid':child.pid}));time.sleep(60)"
    executable,environment=process_runtime()
    process=subprocess.Popen([executable,'-B','-c',code,str(gate),str(pidfile)],env=environment,creationflags=subprocess.CREATE_NO_WINDOW)
    child=None
    try:
        manager.store.worker_owner.assign(process);gate.write_text('go',encoding='utf-8')
        deadline=time.monotonic()+8
        while not pidfile.exists() and time.monotonic()<deadline:time.sleep(.02)
        child=psutil.Process(json.loads(pidfile.read_text())['pid'])
        manager.store.active=dict(id=rid,kind='training',process=process)
        manager.stop(rid,force=True)
        assert process.poll() is not None
        deadline=time.monotonic()+2
        while child.is_running() and time.monotonic()<deadline:time.sleep(.02)
        assert not child.is_running(),'Owned descendant survived force termination'
    finally:
        manager.store.worker_owner.close()
        if process.poll() is None:process.kill();process.wait(timeout=5)
        if child and child.is_running():
            child.kill();child.wait(timeout=5)


@pytest.mark.skipif(not torch.cuda.is_available(),reason='CUDA required for controlled AMP overflow fixture')
def test_controlled_amp_overflow_skip_backoff_and_scaler_restore():
    # Tiny synthetic tensor fixture, explicitly not medical training/results.
    p=primitives();torch.manual_seed(123)
    from src.training import guarded_step
    model=torch.nn.Conv2d(1,1,1).cuda();optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    scaler=torch.amp.GradScaler('cuda',enabled=True)
    x=torch.ones((1,1,4,4),device='cuda');y=torch.ones_like(x)
    before=model.weight.detach().clone()
    hook=model.weight.register_hook(lambda gradient:torch.full_like(gradient,float('inf')))
    try:skipped=guarded_step(model,x,y,optimizer,p.DiceBCELoss(),scaler,True)
    finally:hook.remove()
    assert skipped['optimizer_step_skipped'] and skipped['consecutive_skips']==1
    assert skipped['scale_after']==skipped['scale_before']*.5
    assert torch.equal(model.weight,before) and not optimizer.state
    saved=copy.deepcopy(scaler.state_dict());restored=torch.amp.GradScaler('cuda',enabled=True);restored.load_state_dict(saved)
    assert restored.state_dict()==saved
    result=guarded_step(model,x,y,optimizer,p.DiceBCELoss(),restored,True,consecutive_skips=1)
    assert not result['optimizer_step_skipped'] and result['consecutive_skips']==0
    assert not torch.equal(model.weight,before)
    assert restored.state_dict()['_growth_tracker']==1


def test_force_http_requires_token_confirmation_and_grace_period():
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from backend.runtime import process_runtime
    import subprocess,psutil
    cfg=settings();cfg['runs']=str(ROOT/'runs'/('final_force_'+uuid.uuid4().hex))
    with TestClient(create_app(cfg)) as c:
        manager=c.app.state.store.training;rid=str(uuid.uuid4());directory=manager.path(rid);directory.mkdir()
        write(directory/'record.json',dict(run_id=rid,status='running'))
        executable,environment=process_runtime()
        process=subprocess.Popen([executable,'-B','-c','import time;time.sleep(60)'],env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if __import__('sys').platform=='win32' else 0)
        try:
            manager.store.worker_owner.assign(process);manager.store.active=dict(id=rid,kind='training',process=process)
            c.headers['X-MedSeg-Token']=c.get('/api/v1/health').json()['token']
            legacy=c.post(f'/api/v1/jobs/{rid}/cancel',json={})
            assert legacy.status_code==200 and legacy.json()['status']=='stopping'
            assert process.poll() is None,'Legacy cancel must not bypass graceful training stop'
            del c.headers['X-MedSeg-Token']
            assert c.post(f'/api/v1/training/runs/{rid}/force?confirm={rid}',json={}).status_code==403
            c.headers['X-MedSeg-Token']=c.get('/api/v1/health').json()['token']
            assert c.post(f'/api/v1/training/runs/{rid}/force?confirm=wrong',json={}).status_code==422
            assert c.post(f'/api/v1/training/runs/{rid}/force?confirm={rid}',json={}).status_code==409
            assert process.poll() is None
            record=manager.record(rid);record['stop_requested_at']='2020-01-01T00:00:00+00:00'
            write(directory/'record.json',record)  # Only this lifecycle fixture's clock is controlled.
            response=c.post(f'/api/v1/training/runs/{rid}/force?confirm={rid}',json={})
            assert response.status_code==200 and response.json()['status']=='stopped'
            assert process.poll() is not None
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=5)


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='Windows junction safety')
def test_training_checkpoint_junction_is_rejected_without_touching_target(manager):
    import os,subprocess
    rid=str(uuid.uuid4());link=manager.root/rid;target=manager.store.path('junction-target');target.mkdir()
    canary=target/'last.pt';canary.write_bytes(b'controlled canary; not model weights')
    environment=dict(os.environ,MEDSEG_TEST_LINK=str(link),MEDSEG_TEST_TARGET=str(target))
    subprocess.run(['powershell','-NoProfile','-Command',
        '$ErrorActionPreference="Stop"; New-Item -ItemType Junction -Path $env:MEDSEG_TEST_LINK -Target $env:MEDSEG_TEST_TARGET | Out-Null'],env=environment,capture_output=True,check=True)
    try:
        with pytest.raises(ValueError):manager.path(rid,'last.pt')
        assert canary.read_bytes()==b'controlled canary; not model weights'
    finally:
        assert link.absolute().is_relative_to(ROOT/'runs') and link.resolve()==target.resolve()
        os.rmdir(link)  # Remove the verified junction itself, never recursively delete its target.


def test_live_projection_reports_actual_patience_reference(manager):
    body=admitted_request(manager)
    with patch('threading.Thread.start'):record=manager.start(body)
    rid=record['run_id'];point=dict(epoch=1,stage='CONTROLLED FIXTURE',metrics={'val_mean_dice':.5},flags=[],bad_epochs=0)
    EventWriter(manager.path(rid)).emit('epoch_end',epoch=1,point=point)
    assert manager.projection(rid)['early_stopping']['patience_reference']==.5
