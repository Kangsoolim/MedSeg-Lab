"""Algorithm contracts and API failure/restart/cancellation tests.

Small arrays here are exclusively negative/invariant fixtures, never product data.
Real inference equivalence is separately exercised by backend.accept_real.
"""
import importlib.util
import time
import uuid
from pathlib import Path
import unittest
import nibabel as nib
import numpy as np
import psutil
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import ROOT, settings, read, write, sha, validate_input
from backend.contracts import Parameters
from backend.algorithms import check_vendor, validate_selection
from backend.vendor.io_spatial import load_case, prepare_slices, restore_mask
from backend.vendor.region_postprocess import postprocess_region_native

class AlgorithmContractTests(unittest.TestCase):
    @unittest.skipUnless(__import__('sys').platform=='win32','Windows sharing semantics')
    def test_atomic_progress_write_retries_short_windows_reader_lock(self):
        import threading
        p=ROOT/'runs'/('sharing_'+uuid.uuid4().hex+'.json')
        write(p,{'stage':'initial'})
        reader=p.open('rb')
        threading.Timer(.15,reader.close).start()
        write(p,{'stage':'next'})
        self.assertEqual(read(p)['stage'],'next')

    def test_vendor_byte_identity_with_readonly_source(self):
        for name,record in check_vendor().items():
            original=Path(settings()['source_root'])/record['source']
            if not original.exists():self.skipTest('External course source is not configured; vendor hashes already checked')
            self.assertEqual(sha(original),record['sha256'])

    def test_strict_parameter_contract(self):
        for p in [{'seed':[1.1,2,3]},{'radius':0},{'iterations':11},{'opening_mm':-1},{'multiplier':float('nan')},{'seed_component':False},{'unknown':1}]:
            with self.assertRaises(ValueError): Parameters(**p)

    def test_selection_range_roi_and_containment(self):
        for seed,roi in [([-1,2,2],[0,5,0,5,0,5]),([5,2,2],[0,5,0,5,0,5]),([1,1,1],[2,1,0,5,0,5]),([1,1,1],[2,5,0,5,0,5]),(None,None)]:
            with self.assertRaises(ValueError):validate_selection([5,5,5],{'seed':seed,'roi':roi})
        validate_selection([5,5,5],{'seed':[0,0,0],'roi':[0,5,0,5,0,5]})

    def test_orientation_resize_matches_external_original(self):
        path=Path(settings()['source_root'])/'src/common/io_spatial.py'
        if not path.exists():self.skipTest('External original spatial module is not configured')
        spec=importlib.util.spec_from_file_location('course_io_readonly',path)
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        ct=Path(settings()['source_root'])/'data/raw/Task09_Spleen/imagesTr/spleen_8.nii.gz'
        if not ct.exists():self.skipTest('External real preprocessing fixture is not configured')
        a,ma=prepare_slices(load_case(ct));b,mb=original.prepare_slices(original.load_case(ct))
        np.testing.assert_array_equal(a,b)
        np.testing.assert_array_equal(restore_mask(a,ma),original.restore_mask(b,mb))
        self.assertEqual(ma,mb)

class APIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=ROOT/'runs'/('qa_'+uuid.uuid4().hex)
        cls.directory.mkdir()
        cls.cfg=settings();cls.cfg.update(runs=str(cls.directory),checkpoint=str(cls.directory/'missing-e17.pt'),input_roots=[str(cls.directory),*cls.cfg['input_roots']])
        cls.ct=cls.directory/'ct.nii.gz'
        n=nib.Nifti1Image(np.ones((9,9,5),np.float32)*30,np.diag([-1.,2.,3.,1.]));n.header.set_xyzt_units('mm');nib.save(n,cls.ct)
        cls.app=create_app(cls.cfg);cls.client=TestClient(cls.app);cls.client.__enter__()
        cls.client.headers['X-MedSeg-Token']=cls.client.get('/api/v1/health').json()['token']

    @classmethod
    def tearDownClass(cls):cls.client.__exit__(None,None,None)

    def register(self,cid='negative_fixture'):
        if cid not in self.app.state.store.cases:
            r=self.client.post('/api/v1/cases',json={'case_id':cid,'ct':str(self.ct)})
            self.assertEqual(r.status_code,201,r.text)
        return cid

    def wait(self,r):
        deadline=time.monotonic()+180
        while r['status'] in ('running','queued'):
            self.assertLess(time.monotonic(),deadline)
            time.sleep(.05);r=self.client.get('/api/v1/jobs/'+r['run_id']).json()
        return r

    def test_health_security_and_path_boundary(self):
        self.assertEqual(self.client.get('/api/v1/health').status_code,200)
        self.assertEqual(self.client.post('/api/v1/jobs',headers={'X-MedSeg-Token':''},json={}).status_code,403)
        self.assertEqual(self.client.get('/api/v1/health',headers={'Origin':'https://example.com'}).status_code,403)
        self.assertEqual(self.client.get('/api/v1/health',headers={'Host':'evil.example'}).status_code,400)
        self.assertEqual(self.client.post('/api/v1/cases',json={'case_id':'outside','ct':str(ROOT/'README.md')}).status_code,422)
        self.assertEqual(self.client.get('/api/v1/jobs/not-a-uuid').status_code,422)

    def test_invalid_nifti_and_spatial_info(self):
        bad=self.directory/'broken.nii.gz';bad.write_bytes(b'not a nifti')
        r=self.client.post('/api/v1/cases',json={'case_id':'invalid','ct':str(bad)})
        self.assertEqual(r.status_code,422,r.text);self.assertIn('Invalid NIfTI',r.text)
        for kind in ['unknown_unit','shear','nonfinite','too_large','four_dimensional']:
            data=np.ones((4,4,3),np.float32)
            affine=np.eye(4)
            if kind=='shear':affine[0,1]=.2
            if kind=='nonfinite':data[0,0,0]=np.nan
            if kind=='four_dimensional':data=data[...,None]
            n=nib.Nifti1Image(data,affine)
            if kind!='unknown_unit':n.header.set_xyzt_units('mm')
            p=self.directory/(kind+'.nii');nib.save(n,p)
            cfg=dict(self.cfg)
            if kind=='too_large':cfg['max_voxels']=1
            with self.assertRaises(ValueError):validate_input(p,cfg)

    def test_no_gt_import_and_duplicate(self):
        cid=self.register()
        r=self.client.post('/api/v1/cases',json={'case_id':cid,'ct':str(self.ct)})
        self.assertEqual(r.status_code,422)
        entry=self.app.state.store.cases[cid]
        self.assertIsNone(entry['gt'])
        self.assertEqual(self.client.get('/api/v1/inputs/'+cid+'/ct/000.png').status_code,200)

    def test_seed_and_roi_rejected_before_execution(self):
        cid=self.register()
        for p in [{'seed':[9,1,1],'roi':[0,9,0,9,0,5]},{'seed':[1,1,1],'roi':[2,1,0,9,0,5]}]:
            r=self.client.post('/api/v1/jobs',json={'case_id':cid,'algorithm':'traditional_v2','parameters':p})
            self.assertEqual(r.status_code,422,r.text)

    def test_missing_e17_real_failure_diagnostics(self):
        cid=self.register()
        before=len(self.client.get('/api/v1/runs').json())
        response=self.client.post('/api/v1/jobs',json={'case_id':cid,'algorithm':'unet_e17'})
        self.assertEqual(response.status_code,422)
        self.assertIn('resource unavailable',response.json()['detail'])
        self.assertEqual(len(self.client.get('/api/v1/runs').json()),before)

    def test_duplicate_and_real_process_cancellation(self):
        cid=self.register()
        body={'case_id':cid,'algorithm':'traditional_v2','parameters':{'seed':[2,2,1],'roi':[0,9,0,9,0,5]}}
        r=self.client.post('/api/v1/jobs',json=body).json()
        self.assertEqual(self.client.post('/api/v1/jobs',json=body).status_code,409)
        for _ in range(100):
            row=self.client.get('/api/v1/jobs/'+r['run_id']).json()
            if row.get('pid'):break
            time.sleep(.01)
        start=time.monotonic()
        self.assertEqual(self.client.get('/api/v1/health').status_code,200)
        self.assertLess(time.monotonic()-start,2)
        process=self.app.state.store.active['process']
        final=self.client.post('/api/v1/jobs/'+r['run_id']+'/cancel').json()
        self.assertEqual(final['status'],'cancelled')
        self.assertIsNotNone(process.poll(), 'Cancellation must wait for actual process exit')
        # Windows can retain an exited PID briefly after GetExitCodeProcess
        # already confirms termination; do not confuse that with a live worker.
        deadline=time.monotonic()+2
        while psutil.pid_exists(row['pid']) and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(psutil.pid_exists(row['pid']))
        self.assertEqual(self.client.get('/api/v1/runs/'+r['run_id']+'/export').status_code,409)

    def test_restart_records_and_interrupted_recovery(self):
        # A separate store uses actual on-disk metadata and the real OS lock.
        from backend.service import Store
        cfg=dict(self.cfg);cfg['runs']=str(self.directory/'restart')
        first=Store(cfg);rid=str(uuid.uuid4())
        record=dict(run_id=rid,status='running',created_at='2026-11-05',error=None)
        write(first.root/rid/'record.json',record);first.close()
        second=Store(cfg)
        try:
            self.assertEqual(second.get(rid)['status'],'failed')
            self.assertIn('Service restarted',second.get(rid)['error']['message'])
            self.assertEqual(second.list()[0]['run_id'],rid)
            with self.assertRaises(OSError):Store(cfg)
        finally:second.close()

    def test_delete_requires_exact_confirmation(self):
        cid=self.register()
        r=self.client.post('/api/v1/jobs',json={'case_id':cid,'algorithm':'traditional_v2','parameters':{'seed':[2,2,1],'roi':[0,9,0,9,0,5]}}).json()
        rid=r['run_id'];self.client.post('/api/v1/jobs/'+rid+'/cancel')
        self.assertEqual(self.client.delete('/api/v1/runs/'+rid).status_code,422)
        self.assertEqual(self.client.delete('/api/v1/runs/'+rid+'?confirm='+rid).status_code,422)
        impact=self.client.get('/api/v1/storage/inference/'+rid).json()
        self.assertEqual(self.client.delete('/api/v1/runs/'+rid+'?confirm='+rid+'&plan_sha256='+impact['plan_sha256']).status_code,200)
        self.assertFalse((self.directory/rid).exists())

if __name__=='__main__':unittest.main()
