"""Independent final acceptance regressions. All attack targets are disposable fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import uuid
from unittest.mock import patch
import nibabel as nib
import numpy as np
import psutil
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import ROOT, read, settings, write
from backend.contracts import ImportRequest, JobRequest
from backend.service import Store

def junction(link, target):
    # Never point these fixtures at the protected course project.
    assert link.is_relative_to(ROOT/'runs') and target.is_relative_to(ROOT/'runs')
    env=dict(os.environ,MEDSEG_TEST_LINK=str(link),MEDSEG_TEST_TARGET=str(target))
    subprocess.run(['powershell','-NoProfile','-Command',
                    '$ErrorActionPreference="Stop"; New-Item -ItemType Junction -Path $env:MEDSEG_TEST_LINK -Target $env:MEDSEG_TEST_TARGET | Out-Null'],
                    env=env,check=True,capture_output=True)

class FinalLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'runs'/('finaltest_'+uuid.uuid4().hex)
        self.root.mkdir()
        self.cfg=settings();self.cfg['runs']=str(self.root/'store')
        self.cfg['input_roots']=[str(self.root),*self.cfg['input_roots']]
        self.store=Store(self.cfg)

    def tearDown(self):self.store.close()

    def seed_case(self):
        ct=self.root/'fixture.nii.gz'
        n=nib.Nifti1Image(np.full((5,6,3),40,np.float32),np.eye(4));n.header.set_xyzt_units('mm');nib.save(n,ct)
        self.store.cases['fixture']={'case_id':'fixture','ct':str(ct),'gt':None,'spatial':{'shape':[5,6,3]},'comparators':[]}
        return JobRequest(case_id='fixture',algorithm='traditional_v2',parameters={'seed':[2,2,1],'roi':[0,5,0,6,0,3]})

    def test_queued_cancel_never_starts_worker(self):
        body=self.seed_case()
        with patch('threading.Thread.start'):
            record=self.store.submit(body)
        self.assertEqual(record['status'],'queued')
        final=self.store.cancel(record['run_id'])
        self.store.run(record['run_id'])
        self.assertEqual(final['status'],'cancelled')
        self.assertNotIn('pid',final)
        self.assertIsNone(self.store.active)

    def test_startup_record_error_stops_already_spawned_worker(self):
        body=self.seed_case()
        with patch('threading.Thread.start'):
            record=self.store.submit(body)
        original=subprocess.Popen
        children=[]
        def controlled(*args,**kwargs):
            proc=original([sys.executable,'-B','-c','import time; time.sleep(60)'],cwd=ROOT,
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            children.append(proc);return proc
        from backend import service
        original_write=service.write
        def fail_running(path,value):
            if Path(path).name=='record.json' and value.get('status')=='running':
                raise OSError('Injected metadata commit failure')
            return original_write(path,value)
        try:
            with patch('backend.service.subprocess.Popen',controlled),patch('backend.service.write',fail_running):
                self.store.run(record['run_id'])
            self.assertEqual(self.store.get(record['run_id'])['status'],'failed')
            self.assertIsNotNone(children[0].poll(),'Spawned worker survived metadata failure')
        finally:
            for p in children:
                if p.poll() is None:p.kill();p.wait(timeout=5)

    def test_corrupt_completed_record_recovers_without_losing_result(self):
        rid=str(uuid.uuid4());p=self.store.root/rid/'record.json'
        value=dict(run_id=rid,status='completed',case_id='fixture',algorithm='traditional_v2',parameters={},
                   created_at='2026-11-05T00:00:00Z',result={'output_sha256':'sealed'})
        write(p,value)
        p.write_text('{"status":',encoding='utf-8')
        self.store.close();self.store=Store(self.cfg)
        self.assertEqual(self.store.get(rid)['status'],'completed')
        self.assertEqual(self.store.get(rid)['result']['output_sha256'],'sealed')
        self.assertTrue(list(p.parent.glob('record.corrupt.*.json')))

    def test_hardlinked_record_is_rejected_without_modifying_target(self):
        target=self.root/'sentinel.json';target.write_text('{"secret":"test-fixture"}',encoding='utf-8')
        before=target.read_bytes();rid=str(uuid.uuid4());directory=self.store.root/rid;directory.mkdir()
        link=directory/'record.json';os.link(target,link)
        try:
            with self.assertRaises(ValueError):self.store.get(rid)
            self.assertEqual(target.read_bytes(),before)
        finally:link.unlink()

    def test_api_traversal_missing_files_and_script_fields_rejected(self):
        cfg=dict(self.cfg);cfg['runs']=str(self.root/'api')
        with TestClient(create_app(cfg)) as client:
            client.headers['X-MedSeg-Token']=client.get('/api/v1/health').json()['token']
            store=client.app.state.store;rid=str(uuid.uuid4())
            write(store.root/rid/'record.json',dict(run_id=rid,status='completed',created_at='2026-11-05'))
            self.assertIn(client.get('/api/v1/runs/'+rid+'/files/..%2F..%2Fsentinel.json').status_code,(404,422))
            self.assertEqual(client.post('/api/v1/cases',json={'case_id':'missing','ct':str(self.root/'missing.nii.gz')}).status_code,404)
            self.assertEqual(client.post('/api/v1/jobs',json={'case_id':'spleen_8','algorithm':'unet_e17','command':'arbitrary script'}).status_code,422)
            self.assertEqual(client.get('/api/v1/inputs/valid/ct/..%5C..%5Csecret.json').status_code,404)

    @unittest.skipUnless(sys.platform=='win32','Windows junction semantics')
    def test_inputs_junction_cannot_write_outside_store(self):
        target=self.root/'sentinel';target.mkdir()
        link=self.store.root/'inputs';junction(link,target)
        ct=self.root/'fixture.nii.gz'
        n=nib.Nifti1Image(np.ones((5,5,3),np.float32),np.eye(4));n.header.set_xyzt_units('mm');nib.save(n,ct)
        try:
            with self.assertRaises(ValueError):self.store.register(ImportRequest(case_id='escape',ct=str(ct)))
            self.assertEqual(list(target.iterdir()),[])
        finally:
            assert link.resolve()==target.resolve();os.rmdir(link)

    @unittest.skipUnless(sys.platform=='win32','Windows junction semantics')
    def test_run_junction_cannot_read_outside_store(self):
        target=self.root/'sentinel';target.mkdir()
        rid=str(uuid.uuid4())
        write(target/'record.json',dict(run_id=rid,status='completed',created_at='2026-11-05'))
        link=self.store.root/rid;junction(link,target)
        try:
            with self.assertRaises(ValueError):self.store.get(rid)
        finally:
            assert link.resolve()==target.resolve();os.rmdir(link)
