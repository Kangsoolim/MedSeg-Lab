"""Verify protected source hashes and local-delivery boundaries without writing sources."""
from pathlib import Path
import argparse,json,subprocess,sys
from export_package import ROOT,read_json,sha,dump,require_local_output
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--report',type=Path,default=ROOT/'docs/final-source-verification.json');p.add_argument('--browser-results',type=Path,default=ROOT/'docs/browser-results.json');p.add_argument('--release',action='store_true',help='Permit a reviewed local source commit; still reject ignored, medical or private files');args=p.parse_args()
before=read_json(ROOT/'docs/source-before.json');changed=[]
for rel,expected in before.items():
    if sha(args.source/rel)!=expected: changed.append(rel)
inputs={}
for entry in read_json(ROOT/'frontend/public/demo/index.json')['cases']:
    case=read_json(ROOT/'frontend/public/demo'/entry['case_id']/'case.json')
    for rec in [case['ct_source'],case['gt_source'],*[m['source'] for m in case['methods']]]:
        if rec is None: continue
        inputs[rec['path']]=sha(rec['path'])==rec['sha256']
tracked=subprocess.check_output(['git','-C',str(ROOT),'ls-files'],text=True).splitlines()
remotes=subprocess.check_output(['git','-C',str(ROOT),'remote'],text=True).splitlines()
unsafe_tracked=[]
for name in tracked:
    ignored=subprocess.run(['git','-C',str(ROOT),'check-ignore','--no-index','-q',name],capture_output=True).returncode==0
    medical_or_binary=Path(name).suffix.lower() in {'.png','.jpg','.jpeg','.tif','.tiff','.bmp','.dcm','.dicom','.nii','.gz','.mesh','.npy','.npz','.pt','.pth','.ckpt','.onnx','.safetensors'}
    if ignored or medical_or_binary: unsafe_tracked.append(name)
for pattern in ['frontend/public/demo/index.json','frontend/dist/index.html','docs/screenshots/workstation-1366x768.png','.pnpm-store/test','example.nii.gz','model.pth']:
    subprocess.run(['git','-C',str(ROOT),'check-ignore','-q',pattern],check=True)
report={'protected_files':len(before),'changed_protected_files':changed,'nifti_inputs':inputs,'tracked_files':tracked,'unsafe_tracked_files':unsafe_tracked,'release_mode':args.release,'remotes':remotes,'no_commit':subprocess.run(['git','-C',str(ROOT),'rev-parse','--verify','HEAD'],capture_output=True).returncode!=0,
        'production_html_sha256':sha(ROOT/'frontend/dist/index.html'),'production_assets':{p.name:sha(p) for p in (ROOT/'frontend/dist/assets').glob('*') if p.is_file()},
        'browser_results':read_json(args.browser_results)['stats'],'source_unchanged':not changed and all(inputs.values())}
dump(require_local_output(args.report),report)
if changed or not all(inputs.values()) or unsafe_tracked or (tracked and not args.release) or remotes: raise SystemExit('DELIVERY BOUNDARY CHECK FAILED')
print(json.dumps({'protected_files':len(before),'nifti_inputs':len(inputs),'source_unchanged':True,'tracked_files':len(tracked),'remotes':len(remotes),'no_commit':report['no_commit']}))


