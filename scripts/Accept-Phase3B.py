"""Explicit bounded real-input acceptance. Never starts full course training.

Run using a CPU-only Torch environment, with approved existing resource paths.
All output goes to a fresh UUID namespace under MedSeg-Lab/runs.
"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT,settings,write,sha,read
from backend.service import Store
from backend.training_service import TrainingManager
from backend.contracts import ImportRequest,JobRequest

def wait(manager,rid,timeout=240):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        record=manager.get(rid)
        if record['status'] not in ('queued','preparing','running','stopping'):
            if record['status']!='completed':raise RuntimeError(json.dumps(record))
            return record
        time.sleep(.25)
    raise TimeoutError('Bounded acceptance exceeded its time limit')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--course-root',type=Path,required=True);parser.add_argument('--checkpoint',type=Path);parser.add_argument('--mode',choices=['inference','training'],required=True);args=parser.parse_args()
    cfg=settings();cfg.update(source_root='',checkpoint=str(args.checkpoint.resolve()) if args.checkpoint else '',input_roots=[str((args.course_root/'data/raw/Task09_Spleen').resolve())],runs=str(ROOT/'runs'/('phase3b_real_'+uuid.uuid4().hex)))
    s=Store(cfg);s.cases={};s.training=TrainingManager(s)
    evidence=dict(mode=args.mode,source_kind='Existing real CT/GT, local authorized workflow; not external-institution or research performance acceptance',runs_root=str(s.root),input_hashes={})
    try:
        if args.mode=='inference':
            # Not one of the three frozen showcase cases. No GT used for seed choice.
            ct=args.course_root/'data/raw/Task09_Spleen/imagesTr/spleen_2.nii.gz';gt=args.course_root/'data/raw/Task09_Spleen/labelsTr/spleen_2.nii.gz'
            entry=s.register(ImportRequest(case_id='real_import_workflow',ct=str(ct.resolve()),gt=str(gt.resolve())))
            shape=entry['spatial']['shape'];seed=[n//2 for n in shape];roi=[v for n in shape for v in (0,n)]
            record=wait(s,s.submit(JobRequest(case_id=entry['case_id'],algorithm='traditional_v2',parameters={'seed':seed,'roi':roi,'device':'cpu'}))['run_id'])
            out=s.path(record['run_id']);evidence['v2']=record
            from backend.import_analysis import analyze
            # Generated masks are controlled local outputs, not arbitrary external input roots.
            # Explicit acceptance config allows this fresh namespace for the import round-trip.
            s.cfg['input_roots'].append(str(s.root))
            package=analyze(s,entry['case_id'],[str(out/'prediction.nii.gz'),str(out/'region_growing.nii.gz')])
            assert len(package['methods'])==2 and package['has_gt']
            evidence['multi_mask_run']=package['run_id'];evidence['geometry']=package['spatial'];evidence['analysis_available']=all(m['analysis'] is not None for m in package['methods'])
            if args.checkpoint:
                import torch
                assert torch.version.cuda is None and not torch.cuda.is_available(),'Use a CPU-only wheel for this acceptance'
                evidence['e17']=wait(s,s.submit(JobRequest(case_id=entry['case_id'],algorithm='unet_e17',parameters={'device':'cpu'}))['run_id'])
                evidence['checkpoint_sha256']=sha(args.checkpoint)
            evidence['input_hashes']={str(p):sha(p) for p in (ct,gt)}
        else:
            import torch
            assert torch.version.cuda is None and not torch.cuda.is_available(),'Use a CPU-only wheel for this acceptance'
            from backend.training_contracts import TrainingConfig,ResumePreflight,StartTraining
            for cid in ('spleen_56','spleen_9'):
                ct=args.course_root/f'data/raw/Task09_Spleen/imagesTr/{cid}.nii.gz';gt=args.course_root/f'data/raw/Task09_Spleen/labelsTr/{cid}.nii.gz'
                s.register(ImportRequest(case_id=cid,ct=str(ct.resolve()),gt=str(gt.resolve())))
                evidence['input_hashes'].update({str(p):sha(p) for p in (ct,gt)})
            config=TrainingConfig(dataset='registered',train_ids=['spleen_56'],val_ids=['spleen_9'],device='cpu',amp=False,epochs=1,batch_size=1,engineering_smoke=True,max_train_batches=1)
            def start(c,parent=None):
                pre=s.training.preflight(ResumePreflight(config=c,resume_run_id=parent));return s.training.start(StartTraining(config=c,preflight_id=pre['preflight_id'],request_id=uuid.uuid4().hex,confirm='START REAL TRAINING',resume_run_id=parent))
            parent=wait(s.training,start(config)['run_id']);config=config.model_copy(update={'epochs':2})
            child=wait(s.training,start(config,parent['run_id'])['run_id'])
            projection=s.training.projection(child['run_id']);assert [p['epoch'] for p in projection['epochs']]==[1,2]
            assert projection['lineage'][0]['parent']==parent['run_id']
            from backend.storage import plan,operate
            impact=plan(s,'training',parent['run_id']);assert child['run_id'] in impact['dependents']
            operate(s,'training',parent['run_id'],'archive');assert s.training.path(parent['run_id'],'last.pt').is_file()
            evidence.update(parent=parent,child=child,lineage=projection['lineage'],epochs=projection['epochs'],scope='Two actual optimizer updates total: E1 parent, E2 child. Full native validation of one selected volume per boundary. Not a full dataset pass or performance result.')
            evidence['environment']=dict(torch=torch.__version__,cuda=torch.version.cuda,available=torch.cuda.is_available())
        target=ROOT/'docs/phase3b'/('real-'+args.mode+'.json')
        if target.exists():raise FileExistsError('Refusing to replace completed evidence')
        write(target,evidence);print(json.dumps(dict(mode=args.mode,status='PASS',evidence=str(target),runs_root=str(s.root))))
    finally:s.training.close();s.close()

if __name__=='__main__':main()
