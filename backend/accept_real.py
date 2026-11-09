"""Real local acceptance through the HTTP API; no simulated algorithm results."""
import argparse
import time
from pathlib import Path
import httpx
import nibabel as nib
import numpy as np
from backend.config import ROOT, settings, read, write

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cpu',action='store_true')
    args=parser.parse_args()
    client=httpx.Client(base_url='http://127.0.0.1:8008',timeout=60)
    health=client.get('/api/v1/health').raise_for_status().json()
    client.headers['X-MedSeg-Token']=health['token']
    source=Path(settings()['source_root'])
    evidence=ROOT/'docs/phase2a'
    cases=client.get('/api/v1/cases').raise_for_status().json()
    results=[]
    def job(cid,algorithm,device='auto'):
        entry=next(c for c in cases if c['case_id']==cid)
        parameters={'device':device}
        if algorithm=='traditional_v2':parameters.update(entry['reference_selection'])
        r=client.post('/api/v1/jobs',json={'case_id':cid,'algorithm':algorithm,'parameters':parameters}).raise_for_status().json()
        print('submitted',cid,algorithm,r['run_id'],flush=True)
        start=time.monotonic()
        while r['status'] in ('queued','running'):
            if time.monotonic()-start>1800: raise RuntimeError('Acceptance timeout')
            time.sleep(.5)
            r=client.get('/api/v1/jobs/'+r['run_id']).raise_for_status().json()
        if r['status']!='completed': raise AssertionError(r)
        print('completed',r['run_id'],r['result']['device'],flush=True)
        return r
    def compare(r,cid,algorithm):
        actual=nib.load(r['result']['output_path'])
        frozen=source/('outputs/traditional_v2_open1mm/'+cid+'/traditional_mask.nii.gz' if algorithm=='traditional_v2' else 'outputs/unet_stage8_final_test_seed42_epoch17/'+cid+'/prediction.nii.gz')
        expected=nib.load(str(frozen))
        a=actual.get_fdata();b=expected.get_fdata()
        mismatch=int(np.count_nonzero(a!=b))
        gt=nib.load(str(source/f'data/raw/Task09_Spleen/labelsTr/{cid}.nii.gz')).get_fdata()>0
        tp=int(np.count_nonzero((a>0)&gt))
        row=dict(case_id=cid,algorithm=algorithm,run_id=r['run_id'],device=r['result']['device'],
                 mismatch_voxels=mismatch,foreground_voxels=int(a.sum()),frozen_foreground_voxels=int(b.sum()),
                 affine_max_abs_diff=float(np.max(np.abs(actual.affine-expected.affine))),
                 shape=list(a.shape),axis_codes=list(nib.aff2axcodes(actual.affine)),
                 dice=2*tp/(int(a.sum())+int(gt.sum())),volume_ml=r['result']['volume_ml'],
                 checkpoint_sha256=r['result'].get('checkpoint_sha256'))
        assert a.shape==b.shape
        assert np.array_equal(actual.affine,expected.affine)
        assert mismatch==0,row
        results.append(row);write(evidence/'real-comparison.json',results)
    for alg in ['traditional_v2','unet_e17']:
        r=job('spleen_8',alg); compare(r,'spleen_8',alg)
    if args.cpu:
        r=job('spleen_8','unet_e17','cpu');compare(r,'spleen_8','unet_e17')
    # Additional source case outside the three demo cases; exploratory reproduction.
    cid='phase2a_spleen3'
    if not any(c['case_id']==cid for c in cases):
        c=client.post('/api/v1/cases',json={'case_id':cid,'ct':str(source/'data/raw/Task09_Spleen/imagesTr/spleen_3.nii.gz'),
              'gt':str(source/'data/raw/Task09_Spleen/labelsTr/spleen_3.nii.gz')}).raise_for_status().json()
        cases.append(c)
    c=next(c for c in cases if c['case_id']==cid)
    c['reference_selection']={'seed':read(source/'outputs/traditional/spleen_3_seed_roi.json')['seed_ijk'],
                              'roi':read(source/'outputs/traditional/spleen_3_seed_roi.json')['roi_ijk_half_open']}
    r=job(cid,'traditional_v2');compare(r,'spleen_3','traditional_v2')
    write(evidence/'new-case.json',dict(run_id=r['run_id'],case_id=cid,manifest=r['manifest'],
                                      source_role='Existing internal dataset; exploratory reproduction, not independent testing'))
    print('PASS real voxel-level comparisons',len(results),flush=True)

if __name__=='__main__':main()
