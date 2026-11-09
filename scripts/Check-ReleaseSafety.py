"""Read-only current-source and Git-history pattern audit; not an authorization proof."""
from pathlib import Path
import json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
files=set()
for args in [('ls-files','-z'),('ls-files','--others','--exclude-standard','-z')]:files.update(git(*args).decode().split('\0'))
private=[];medical=[];secrets=[]
for name in files-{''}:
    if re.search(r'\.(nii(?:\.gz)?|pt|pth|ckpt|dcm|dicom|safetensors|npy|npz)$',name,re.I):medical.append(name)
    p=ROOT/name
    try:value=p.read_text(encoding='utf-8')
    except (OSError,UnicodeError):continue
    if re.search(r'(?i)[A-Z]:[\\/]Users[\\/][^\s\"<>`]+',value):private.append(name)
    if re.search(r'AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}',value):secrets.append(name)
objects=git('rev-list','--objects','--all').decode().splitlines();sizes=subprocess.run(['git','cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize)'],cwd=ROOT,input=''.join(p.split(' ',1)[0]+'\n' for p in objects),text=True,capture_output=True,check=True).stdout.splitlines()
large=[];history_private=[]
for obj,info in zip(objects,sizes):
    oid,kind,size=info.split()
    if kind!='blob':continue
    if int(size)>1024*1024:large.append({'object':obj,'bytes':int(size)})
    if int(size)>2*1024*1024:continue
    try:value=git('cat-file','blob',oid).decode('utf-8')
    except UnicodeError:continue
    if re.search(r'(?i)[A-Z]:[\\/]Users[\\/][^\s\"<>`]+',value):history_private.append(obj)
result=dict(source_files=len(files-{''}),medical_files=medical,current_personal_paths=private,secret_pattern_hits=secrets,history_objects=len(objects),history_large_blobs=large,history_personal_path_blobs=history_private,notes='History authors also require review. Pattern checks are not a comprehensive privacy/legal guarantee. No history rewrite or upload performed.')
print(json.dumps(result,indent=2))
sys.exit(bool(private or medical or secrets))
