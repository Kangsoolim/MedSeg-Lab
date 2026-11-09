"""Resolve only declared train/validation inputs; never infer patient identity."""
import csv
import io
from pathlib import Path
import nibabel as nib
import numpy as np
from backend.config import input_path, read, sha, validate_input


COURSE_HELDOUT_IDS={'spleen_8','spleen_16','spleen_17','spleen_33','spleen_38','spleen_59'}

def course_manifest(cfg):
    if not cfg.get('source_root'):
        return {'train':[], 'val':[], 'test':[], 'counts':{'train':0,'val':0,'test':0}}, {}
    source = Path(cfg['source_root'])
    split = read(source/'data/split.json')
    rows = list(csv.DictReader(io.StringIO((source/'data/cases.csv').read_text(encoding='utf-8-sig'))))
    cases = {r['case_id']: r for r in rows if r['pair_valid'].lower() == 'true'}
    seen = set()
    for role in ('train', 'val', 'test'):
        ids = split[role]
        if not ids or len(ids) != len(set(ids)) or seen.intersection(ids) or not set(ids).issubset(cases):
            raise ValueError('Invalid frozen partition / 冻结划分无效')
        if split['counts'][role] != len(ids):
            raise ValueError('Partition count mismatch / 划分计数不匹配')
        seen.update(ids)
    if not split.get('is_frozen') or seen != set(cases):
        raise ValueError('Expected complete frozen patient split / 需要完整冻结病例划分')
    entries = {}
    for role in ('train', 'val'):
        for cid in split[role]:
            row = cases[cid]
            for key, folder in (('image_relpath', 'imagesTr'), ('label_relpath', 'labelsTr')):
                if Path(row[key].replace('\\', '/')).parts not in [(folder, cid+'.nii.gz'), (folder, cid+'.nii')]:
                    raise ValueError('Unsafe course manifest path / 课程清单路径无效')
            entries[cid] = dict(case_id=cid, ct=str(source/'data/raw/Task09_Spleen'/row['image_relpath']),
                                gt=str(source/'data/raw/Task09_Spleen'/row['label_relpath']), role=role)
    return split, entries


def catalog(store):
    split, entries = course_manifest(store.cfg)
    result = []
    for entry in [*entries.values(), *[dict(e, role='unassigned') for e in store.cases.values() if e.get('source_kind') == 'exploratory_import']]:
        cid = entry['case_id']
        try:
            ct = nib.load(str(input_path(entry['ct'], store.cfg)))
            gt = nib.load(str(input_path(entry['gt'], store.cfg))) if entry.get('gt') else None
            aligned = gt is not None and gt.shape == ct.shape and np.allclose(ct.affine, gt.affine, atol=1e-5, rtol=0)
            info = dict(shape=list(ct.shape), spacing=list(map(float, ct.header.get_zooms()[:3])),
                        orientation=list(nib.aff2axcodes(ct.affine)), gt_available=aligned, error=None)
        except (ValueError, OSError, nib.filebasedimages.ImageFileError):
            info = dict(shape=None, spacing=None, orientation=None, gt_available=False, error='Input unavailable or mismatched / 输入缺失或空间不匹配')
        result.append(dict(case_id=cid, dataset='registered' if entry['role']=='unassigned' else 'course', role=entry['role'], **info))
    return dict(cases=result, counts=split['counts'], split_id=sha(Path(store.cfg['source_root'])/'data/split.json') if store.cfg.get('source_root') else None,
                identity_warning='Case IDs are disjoint; independent patient identity cannot be proven / 病例ID可查重，无法证明患者身份完全独立',
                model=dict(input_channels=1, output_channels=1, channels=[16,32,64,128,256], residual_units=2,
                           input_size=[256,256], loss='0.5 MONAI DiceLoss(sigmoid=True) + 0.5 BCEWithLogitsLoss', optimizer='Adam',
                           preprocessing='closest RAS; HU [-57,164] → [0,1]; CT linear / GT nearest',
                           batch_order='global_batch_shuffle', schedule_seed=600042, adapter='monai-resunet-v1'))


def resolve(store, config, validate=True):
    split, course = course_manifest(store.cfg)
    if config.dataset == 'course':
        entries = course
        train_ids = config.train_ids or split['train']
        val_ids = config.val_ids or split['val']
        if not set(train_ids).issubset(split['train']) or not set(val_ids).issubset(split['val']):
            raise ValueError('Selected cases cross frozen boundaries / 所选病例跨越冻结划分')
    else:
        entries = {k:v for k,v in store.cases.items() if v.get('source_kind')=='exploratory_import'}
        train_ids, val_ids = config.train_ids, config.val_ids
    heldout=set(split['test'])|COURSE_HELDOUT_IDS
    if not train_ids or not val_ids or len(set(train_ids+val_ids)) != len(train_ids+val_ids):
        raise ValueError('Nonempty disjoint train/validation required / 训练和验证集需非空且互斥')
    selected = {}
    hashes = set()
    patient_roles={}
    for role, ids in [('train',train_ids), ('val',val_ids)]:
        for cid in ids:
            if cid not in entries or cid in heldout:
                raise ValueError('Unknown case or held-out test case / 未知病例或保留测试病例')
            entry=entries[cid]
            patient=config.patient_ids.get(cid,cid).strip().casefold()
            if not patient or len(patient)>160:raise ValueError('Invalid patient identity / 患者标识无效')
            if patient in patient_roles and patient_roles[patient]!=role:
                raise ValueError('Patient identity overlaps train/validation / 患者标识跨训练和验证集重复')
            patient_roles[patient]=role
            if not entry.get('gt'):
                raise ValueError('Paired GT required / 需要配对GT')
            paths = [input_path(entry[k],store.cfg) for k in ('ct','gt')]
            if any(p.name.removesuffix('.gz').removesuffix('.nii') in heldout for p in paths):
                raise ValueError('Held-out test resource forbidden / 禁止使用保留测试资源')
            if validate:
                ct,_ = validate_input(str(paths[0]),store.cfg)
                validate_input(str(paths[1]),store.cfg,ct,True)
            ct_hash,gt_hash = map(sha, paths)
            if ct_hash in hashes:
                raise ValueError('Duplicate CT across selected cases / 所选病例存在重复CT，可能泄漏')
            hashes.add(ct_hash)
            header=nib.load(str(paths[0]))
            axes=nib.aff2axcodes(header.affine)
            slice_axis=next((i for i,c in enumerate(axes) if c in ('S','I')),None)
            if slice_axis is None:raise ValueError('Invalid anatomical orientation / 解剖方向无效')
            selected[cid]=dict(ct=str(paths[0]),gt=str(paths[1]),ct_sha256=ct_hash,gt_sha256=gt_hash,role=role,
                               shape=list(header.shape),canonical_slices=int(header.shape[slice_axis]),spacing=list(map(float,header.header.get_zooms()[:3])))
    return dict(train_ids=train_ids,val_ids=val_ids,entries=selected,split_id=sha(Path(store.cfg['source_root'])/'data/split.json') if config.dataset=='course' else None,
                dataset=config.dataset, identity_independence='Not established from available patient metadata')
