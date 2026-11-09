"""Engineering fixtures only. No generated scores are research results."""
import json
import uuid
from pathlib import Path
from unittest.mock import patch
import nibabel as nib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import ROOT,settings,write,read
from backend.service import Store,BusyError
from backend.training_service import TrainingManager
from backend.training_adapter import EventWriter
from backend.storage import plan,operate,listing

@pytest.fixture
def store():
    cfg=settings();cfg.update(source_root='',checkpoint='',input_roots=[],runs=str(ROOT/'runs'/('phase3b_unit_'+uuid.uuid4().hex)))
    with patch.object(Store,'catalog',return_value={}):s=Store(cfg)
    s.training=TrainingManager(s);s.cfg['input_roots']=[str(s.root)]
    yield s
    s.training.close();s.close()

def record(s,kind='training',status='completed',parent=None):
    rid=str(uuid.uuid4());directory=s.training.path(rid) if kind=='training' else s.path(rid);directory.mkdir()
    write(directory/'record.json',dict(run_id=rid,status=status,created_at='2026-11-09T00:00:00Z',parent_run_id=parent))
    return rid,directory

def test_empty_default_config(tmp_path,monkeypatch):
    f=tmp_path/'empty.json';f.write_text('{}');monkeypatch.setenv('MEDSEG_CONFIG',str(f))
    cfg=settings();assert cfg['source_root']=='' and cfg['checkpoint']=='' and cfg['input_roots']==[]
    cfg['runs']=str(ROOT/'runs'/('phase3b_api_'+uuid.uuid4().hex))
    with patch.object(Store,'catalog',return_value={}),TestClient(create_app(cfg)) as c:
        h=c.get('/api/v1/health');assert h.status_code==200 and not h.json()['checkpoint_exists']
        assert c.get('/api/v1/training/catalog').status_code==200
        assert c.get('/api/v1/training/catalog').json()['cases']==[]
        assert c.get('/api/v1/experiments').status_code==200

def test_missing_neural_runtime_is_explicit(store):
    from backend.training_contracts import ResumePreflight,TrainingConfig
    with patch('backend.capabilities.capabilities',return_value={'training':False}):
        with pytest.raises(ValueError,match='optional neural'):store.training.preflight(ResumePreflight(config=TrainingConfig(device='cpu',amp=False)))

def test_index_paging_restart_corruption_and_increment(store):
    rid,d=record(store);w=EventWriter(d)
    for i in range(1003):w.emit('log',message='controlled scale fixture')
    assert len(store.training.events(rid))==500
    assert [e['sequence'] for e in store.training.events(rid,1000)]==[1001,1002,1003]
    EventWriter(d).emit('terminal',status='completed')
    assert store.index.last_sequence(rid)==1004
    store.index.path.write_bytes(b'corrupt derived cache')
    assert store.index.last_sequence(rid)==1004
    from backend.index import DerivedIndex
    store.index=DerivedIndex(store)
    assert store.index.events(rid,1003)[0]['sequence']==1004
    (d/'events'/'000001004.json').unlink()
    assert store.index.last_sequence(rid)==1003

def test_index_identity_and_link_safety(store):
    rid,d=record(store);w=EventWriter(d);w.emit('log',message='fixture')
    path=d/'events'/'000000001.json';v=read(path);v['run_id']=str(uuid.uuid4());write(path,v)
    with pytest.raises(ValueError):store.training.events(rid)
    path.unlink();other=store.path('outside.json');other.write_text('{}')
    import os
    os.link(other,path)
    try:
        with pytest.raises(ValueError):store.training.events(rid)
    finally:path.unlink()

def test_metadata_never_stale(store):
    rid,d=record(store)
    assert store.training.record(rid)['status']=='completed'
    v=read(d/'record.json');v['status']='failed';write(d/'record.json',v)
    assert store.training.record(rid)['status']=='failed'
    (d/'record.json').write_text('{broken')
    assert store.training.record(rid)['status']=='failed'

def test_storage_size_archive_cleanup_and_delete(store):
    rid,d=record(store);(d/'last.pt').write_bytes(b'fixture checkpoint')
    (d/'export.zip').write_bytes(b'cache')
    impact=plan(store,'training',rid)
    assert impact['categories']['checkpoints']==18 and impact['categories']['exports']==5
    operate(store,'training',rid,'archive');assert (d/'last.pt').exists()
    assert store.training.record(rid)['storage_archived']
    operate(store,'training',rid,'restore')
    impact=plan(store,'training',rid)
    with pytest.raises(ValueError):operate(store,'training',rid,'delete',rid,'outdated')
    operate(store,'training',rid,'cleanup',rid,impact['plan_sha256'])
    assert not (d/'export.zip').exists() and (d/'last.pt').exists()
    impact=plan(store,'training',rid)
    operate(store,'training',rid,'delete',rid,impact['plan_sha256'])
    assert not d.exists() and store.path('tombstones','training-'+rid+'.json').is_file()

@pytest.mark.parametrize('status',['queued','preparing','running','stopping'])
def test_active_run_protected(store,status):
    rid,d=record(store,status=status)
    for action in ('archive','delete','cleanup'):
        with pytest.raises(BusyError):operate(store,'training',rid,action,rid,'')
    # Do not let fixture shutdown pretend to own a real process.
    v=read(d/'record.json');v['status']='failed';write(d/'record.json',v)

def test_resume_parent_cannot_be_deleted(store):
    parent,d=record(store);child,_=record(store,parent=parent)
    impact=plan(store,'training',parent)
    assert impact['dependents']==[child]
    with pytest.raises(BusyError):operate(store,'training',parent,'delete',parent,impact['plan_sha256'])
    operate(store,'training',parent,'archive');assert d.exists()

def test_storage_paging_filters_and_traversal(store):
    for i in range(27):record(store,kind='inference',status='failed')
    v=listing(store,kind='inference',status='failed',limit=25)
    assert v['total']==27 and len(v['items'])==25
    assert len(listing(store,offset=25)['items'])==2
    assert not listing(store,since='2027-01-01')['items']
    for rid in ('../escape','NUL','not-uuid'):
        with pytest.raises(ValueError):plan(store,'inference',rid)

def test_aligned_multi_mask_import_and_mismatch(store):
    from backend.contracts import ImportRequest
    from backend.import_analysis import analyze
    affine=np.diag([1.,1.5,2.,1.]);paths=[]
    for name,data in [('ct',np.full((9,8,5),30,dtype=np.float32)),('gt',np.ones((9,8,5),dtype=np.uint8)),('pred',np.zeros((9,8,5),dtype=np.uint8))]:
        path=store.root/(name+'.nii.gz');n=nib.Nifti1Image(data,affine);n.header.set_xyzt_units('mm');nib.save(n,path);paths.append(str(path))
    store.register(ImportRequest(case_id='synthetic_install_fixture',ct=paths[0],gt=paths[1]))
    c=analyze(store,'synthetic_install_fixture',[paths[2],paths[2]])
    assert len(c['methods'])==2 and c['methods'][0]['analysis']['metrics']['dice_3d']==0
    bad=store.root/'bad.nii.gz';n=nib.Nifti1Image(np.zeros((8,8,5),dtype=np.uint8),affine);n.header.set_xyzt_units('mm');nib.save(n,bad)
    with pytest.raises(ValueError):analyze(store,'synthetic_install_fixture',[str(bad)])
    store.register(ImportRequest(case_id='ct_without_gt',ct=paths[0]))
    c=analyze(store,'ct_without_gt',[paths[2]])
    assert c['methods'][0]['analysis'] is None and not c['has_gt']

def test_storage_api_requires_token_and_current_plan(store):
    cfg=store.cfg.copy();cfg['runs']=str(ROOT/'runs'/('phase3b_http_'+uuid.uuid4().hex))
    with patch.object(Store,'catalog',return_value={}),TestClient(create_app(cfg)) as c:
        s=c.app.state.store;rid,d=record(s)
        assert c.post(f'/api/v1/storage/training/{rid}/archive',json={}).status_code==403
        c.headers['X-MedSeg-Token']=c.get('/api/v1/health').json()['token']
        assert c.post(f'/api/v1/storage/training/{rid}/delete?confirm={rid}',json={}).status_code==422
        assert c.get('/api/v1/storage').json()['total']==1
        assert c.post(f'/api/v1/storage/training/{rid}/archive',json={}).status_code==200

def test_index_wrong_schema_rebuild_and_metadata_recovery(store):
    import sqlite3
    rid,d=record(store);EventWriter(d).emit('log',message='schema corruption fixture')
    with sqlite3.connect(store.index.path) as db:db.execute('CREATE TABLE events (wrong TEXT)')
    db.close()
    assert store.index.last_sequence(rid)==1
    store.index.path.write_bytes(b'corrupt cache before metadata')
    assert store.training.record(rid)['status']=='completed'

def test_registered_known_heldout_filename_remains_protected(store):
    from backend.training_contracts import TrainingConfig
    from backend.training_data import resolve
    store.cases['spleen_8']={'source_kind':'exploratory_import'}
    store.cases['safe']={'source_kind':'exploratory_import'}
    config=TrainingConfig(dataset='registered',train_ids=['spleen_8'],val_ids=['safe'],device='cpu',amp=False)
    with pytest.raises(ValueError,match='held-out'):resolve(store,config,False)


def test_metadata_rebuild_replays_entire_catalog(store):
    import sqlite3
    first,d1=record(store);second,d2=record(store)
    db=sqlite3.connect(store.index.path)
    try:
        db.execute('CREATE TABLE metadata (wrong TEXT)');db.commit()
    finally:db.close()
    rows=store.index.metadata_many(p for p in (d1/'record.json',d2/'record.json'))
    assert {r['run_id'] for r in rows}=={first,second}
