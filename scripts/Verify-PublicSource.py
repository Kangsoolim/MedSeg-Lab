"""Verify the exact reviewed source boundary; optionally archive only those bytes."""
import argparse,hashlib,json,re,subprocess,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
OLD_BLOBS=('a00fba0d955bab7ecf45d6ec2b78f38a0c907454','889453d1cf2973dab8ecbdd7b6ca96fb6c07af40','5eb93a459484e836275d12c96869089fdb193a50','b45d01b47213d27f17a25aa009ac231c68716a99')
PRIVATE=re.compile(r'(?i)[A-Z]:[\\/]Users[\\/][^\s\"<>`]+|[A-Z]:[\\/](?:Projects|Anaconda)[^\s\"<>`]*|/home/[a-z0-9_.-]+|/Users/[a-z0-9_.-]+')
SECRET=re.compile(r'AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}')
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
def check_bytes(name,b):
 try:t=b.decode('utf-8')
 except UnicodeError:return
 if PRIVATE.search(t) or SECRET.search(t):raise ValueError('Private path/credential pattern: '+name)
def main():
 p=argparse.ArgumentParser();p.add_argument('--archive',type=Path);a=p.parse_args()
 raw=(ROOT/'release-manifest.json').read_bytes();m=json.loads(raw);files=m['files']
 expected=set(files)|{'release-manifest.json'}
 actual=set(git('ls-files','-z').decode().split('\0')+git('ls-files','--others','--exclude-standard','-z').decode().split('\0'))-{''}
 if actual!=expected:raise ValueError('Git source/manifest membership differs: '+str(sorted(actual^expected)))
 for name,record in files.items():
  q=PurePosixPath(name)
  if q.is_absolute() or '..' in q.parts or ':' in name or '\\' in name:raise ValueError('Unsafe member')
  if any(x in {'.git','.venv','node_modules','runs','.release-private','.release-qa','__pycache__','dist'} for x in q.parts):raise ValueError('Excluded member')
  if re.search(r'\.(nii(?:\.gz)?|pt|pth|ckpt|onnx|dcm|dicom|mha|mhd|nrrd|safetensors|npy|npz|log|zip|sqlite3)$',name,re.I) or q.name in {'config.local.json','.env'}:raise ValueError('Private resource')
  f=ROOT/name
  if f.is_symlink() or f.stat().st_nlink!=1:raise ValueError('Source link')
  b=f.read_bytes()
  if record!={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}:raise ValueError('Hash mismatch: '+name)
  check_bytes(name,b)
 check_bytes('release-manifest.json',raw)
 for oid in OLD_BLOBS:
  if subprocess.run(['git','-C',str(ROOT),'cat-file','-e',oid],capture_output=True).returncode==0:raise ValueError('Historical private blob exists')
 object_rows=git('cat-file','--batch-all-objects','--batch-check=%(objectname) %(objecttype) %(objectsize)').decode().splitlines()
 for row in object_rows:
  oid,kind,size=row.split()
  if int(size)>1024*1024:raise ValueError('Unexpected large Git object')
  if kind=='blob':check_bytes(oid,git('cat-file','blob',oid))
 if git('remote').strip():raise ValueError('Unexpected remote')
 result=dict(status='PASS',payload_files=len(files),manifest_files=1,git_objects=len(object_rows),historical_private_blobs_present=0,remote_count=0)
 if a.archive:
  a.archive.parent.mkdir(parents=True,exist_ok=True)
  with zipfile.ZipFile(a.archive,'x',zipfile.ZIP_DEFLATED) as z:
   for name in sorted(expected):z.write(ROOT/name,name)
  with zipfile.ZipFile(a.archive) as z:
   assert set(z.namelist())==expected and len(z.namelist())==len(expected) and z.testzip() is None
   for name,rec in files.items():assert hashlib.sha256(z.read(name)).hexdigest()==rec['sha256']
  result.update(archive=str(a.archive),archive_sha256=hashlib.sha256(a.archive.read_bytes()).hexdigest())
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
