"""Local resource policy. External resources are read-only; outputs stay in runs/."""
import hashlib
import json
import os
import time
import stat
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E17_SHA = '966a5e59e57d82bd9813ea411735b82256fe6be7114af2d9cde655684d6bfee4'

def read(path):
    # Windows atomic replacement can briefly deny an opener sharing access.
    # Retry only that transient I/O error; malformed JSON still fails immediately.
    for attempt in range(51):
        try:
            payload=Path(path).read_text(encoding='utf-8-sig')
            break
        except PermissionError:
            if attempt==50:raise
            time.sleep(.02)
    return json.loads(payload)

def run_path(root, path):
    """Reject traversal, reparse points and hard-linked files before run I/O."""
    root, path = Path(root).absolute(), Path(path).absolute()
    boundary = ROOT/'runs'
    if '..' in path.parts or not root.is_relative_to(boundary) or not path.is_relative_to(root):
        raise ValueError('Run path is outside its designated storage directory')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Run path resolves outside its designated storage directory')
    current=boundary
    for part in (None,*path.relative_to(boundary).parts):
        if part is not None:current=current/part
        try: info=current.lstat()
        except FileNotFoundError: continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024):
            raise ValueError('Links and reparse points are forbidden in run storage')
        if stat.S_ISREG(info.st_mode) and info.st_nlink>1:
            raise ValueError('Hard-linked files are forbidden in run storage')
    return path

def _atomic(path, payload):
    path=Path(path)
    if path.absolute().is_relative_to(ROOT/'runs'):run_path(ROOT/'runs',path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('xb') as stream:
        stream.write(payload);stream.flush();os.fsync(stream.fileno())
    # Windows readers briefly deny FILE_SHARE_DELETE. Preserve atomic JSON
    # publication and retry only that transient sharing failure, with a bound.
    for attempt in range(51):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 50: raise
            time.sleep(.02)

def write(path, value):
    path=Path(path)
    payload=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
    _atomic(path,payload)
    if path.name in ('record.json','input.json','spec.json','experiment.json') and path.absolute().is_relative_to(ROOT/'runs'):
        _atomic(path.with_suffix('.json.bak'),payload)

def read_durable(root,path):
    path=run_path(root,path)
    try:
        value=read(path)
        if not isinstance(value,dict):raise ValueError('Expected a JSON object')
        backup=run_path(root,path.with_suffix('.json.bak'))
        if not backup.exists():_atomic(backup,path.read_bytes())
        return value
    except (json.JSONDecodeError,UnicodeError,FileNotFoundError,ValueError):
        backup=run_path(root,path.with_suffix('.json.bak'))
        value=read(backup)
        if not isinstance(value,dict):raise ValueError('Invalid metadata backup')
        if path.exists():_atomic(path.with_name(path.stem+'.corrupt.'+uuid.uuid4().hex+'.json'),path.read_bytes())
        _atomic(path,json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))
        return value

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def settings():
    file = Path(os.environ.get('MEDSEG_CONFIG', ROOT / 'backend/config.local.json'))
    local = read(file) if file.exists() else {}
    source = Path(local['source_root']).resolve() if local.get('source_root') else None
    return {'source_root': str(source) if source else '',
            'checkpoint': local.get('checkpoint') or '',
            'input_roots': local.get('input_roots', []),
            'runs': str(ROOT / 'runs'), 'max_voxels': 80_000_000,
            'max_file_bytes': 512 * 1024**2, 'max_storage_bytes': 10 * 1024**3,
            'timeout_seconds': 1800, 'max_records': 1000}

def input_path(value, cfg):
    p = Path(value)
    if not p.is_absolute():
        raise ValueError('Input path must be absolute')
    p = p.resolve(strict=True)
    if not any(p.is_relative_to(Path(r).resolve()) for r in cfg['input_roots']):
        raise ValueError('Input path is outside configured read-only input_roots')
    if not (p.name.lower().endswith('.nii.gz') or p.suffix.lower() == '.nii'):
        raise ValueError('Input must be a .nii or .nii.gz file')
    if p.stat().st_size > cfg['max_file_bytes']:
        raise ValueError('Input exceeds 512 MiB file limit')
    return p

def validate_input(value, cfg, reference=None, binary=False):
    import nibabel as nib
    import numpy as np
    from data_tools.export_package import validate_nifti
    p = input_path(value, cfg)
    try:
        header = nib.load(str(p))
    except (nib.filebasedimages.ImageFileError, OSError, EOFError) as error:
        raise ValueError('Invalid NIfTI input: ' + str(error)) from error
    if len(header.shape) != 3 or any(n < 1 for n in header.shape) or int(np.prod(header.shape)) > cfg['max_voxels']:
        raise ValueError('Input must be 3D with at most 80 million voxels')
    return validate_nifti(p, reference, binary)
