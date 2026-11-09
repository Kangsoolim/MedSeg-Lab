"""Prepare a reviewable source-only candidate; never configures Git or uploads."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--revision',type=int,default=1);args=parser.parse_args()
if not 1<=args.revision<=999:raise ValueError('Revision must be 1–999')
suffix='' if args.revision==1 else '-r'+str(args.revision)
output=ROOT/('.release-qa/release-candidate'+suffix)
archive=ROOT/('.release-qa/medseg-lab-phase3b-source-candidate'+suffix+'.zip')
if output.exists() or archive.exists():raise FileExistsError('Candidate already exists; retain it and explicitly choose a new review directory before regenerating')
docs={'INSTALLATION.md','IMPORT_WORKFLOW.md','TRAINING_IMPORT.md','DATA_FORMAT.md','TRAINING_WORKSPACE.md','TRAINING_RUNTIME_ARCHITECTURE.md','EXPERIMENT_SCHEMA.md','THIRD_PARTY_LICENSES.md','PHASE3B_IMPLEMENTATION.md','PHASE3B_QA.md','RELEASE_READINESS.md','RELEASE_HANDOFF.md'}
scripts={'Common.ps1','Setup-Phase3B.ps1','Check-Environment.py','Check-ReleaseSafety.py','Prepare-IsolatedQA.py','Prepare-Release.py','Accept-Phase3B.py','Benchmark-Phase3B.py','Import-Case.ps1','Build.ps1','Test.ps1'}
files=set()
for args in [('ls-files','-z'),('ls-files','--others','--exclude-standard','-z')]:files.update(subprocess.check_output(['git',*args],cwd=ROOT).decode().split('\0'))
manifest={};output.mkdir(parents=True)
for name in sorted(files-{''}):
    p=Path(name);parts=p.parts
    allowed=name in {'README.md','LICENSE','.gitignore','.gitattributes','Start-Phase3B.ps1','Start-MedSegLab.ps1'} or parts[0] in {'backend','data_tools','tests'} or (parts[0]=='frontend' and len(parts)>1 and parts[1] not in {'public','dist','node_modules'}) or (parts[0]=='scripts' and p.name in scripts) or (parts[0]=='docs' and (p.name in docs or len(parts)>1 and parts[1] in {'licenses','assets'}))
    if not allowed:continue
    if any(part in {'.git','.venv','node_modules','__pycache__','runs','.release-qa'} for part in parts):raise ValueError('Excluded directory entered candidate')
    if re.search(r'\.(nii(?:\.gz)?|pt|pth|ckpt|dcm|dicom|safetensors|npy|npz|log|zip)$',name,re.I):raise ValueError('Private resource entered candidate: '+name)
    source=ROOT/name
    if not source.is_file() or source.is_symlink():raise ValueError('Unexpected release source')
    payload=source.read_bytes()
    try:text=payload.decode('utf-8')
    except UnicodeError:text=''
    if re.search(r'(?i)[A-Z]:[\\/]Users[\\/][^\s\"<>`]+',text):raise ValueError('Personal path in candidate: '+name)
    dest=output/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(payload)
    manifest[name]=dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
receipt=dict(kind='history-free source review candidate; not published',baseline='v0.5.0-alpha',files=manifest,excluded='Git history, private data/models/runs/configs/evidence/environments/build outputs')
(output/'release-manifest.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(output.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(output).as_posix())
print(json.dumps(dict(path=str(archive),files=len(manifest),bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest()),indent=2))
