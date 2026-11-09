"""MedSeg-Lab: strictly local, read-only NIfTI adapter. No resampling or inference."""
from __future__ import annotations
import argparse, csv, hashlib, itertools, json, os, re, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import nibabel as nib
from nibabel.orientations import apply_orientation, axcodes2ornt, io_orientation, ornt_transform, inv_ornt_aff
from scipy import ndimage as ndi
from skimage.measure import marching_cubes
from PIL import Image

COLORS = {'gt':(23,101,139),'traditional':(170,114,13),'unet':(116,80,166),'tp':(33,133,181),'fp':(229,104,57),'fn':(228,182,55)}
METHODS = {'traditional':'ConfidenceConnected_ROI_postprocessed','unet':'UNet_Epoch17_frozen'}
ROOT = Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def require_local_output(path):
    resolved=Path(path).resolve()
    if not resolved.is_relative_to(ROOT.resolve()): raise ValueError('all outputs must remain inside the MedSeg-Lab project; protected source is read-only')
    return resolved
def read_json(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def safe_id(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',value): raise ValueError('case/method id must be 1-80 safe ASCII letters, digits, _ or -')
    return value
def validate_nifti(path, reference=None, binary=False):
    path=Path(path)
    # Opening first preserves PermissionError (rather than ambiguous is_file False).
    with path.open('rb') as f: f.read(1)
    n=nib.load(str(path)); a=np.asarray(n.affine,dtype=float)
    if len(n.shape)!=3: raise ValueError(f'{path}: expected 3D, got shape {n.shape}')
    if not np.isfinite(a).all() or abs(np.linalg.det(a[:3,:3]))<1e-10 or not np.allclose(a[3],[0,0,0,1]): raise ValueError(f'{path}: invalid/singular affine')
    if n.header.get_xyzt_units()[0]!='mm': raise ValueError(f'{path}: spatial unit must explicitly be mm')
    if not np.allclose(np.linalg.norm(a[:3,:3],axis=0),n.header.get_zooms()[:3],rtol=1e-5,atol=1e-4): raise ValueError(f'{path}: spacing/header disagreement')
    # Slice area and normal-distance labels require an orthogonal voxel basis. Oblique orthogonal grids work.
    b=a[:3,:3]; norm=b/np.linalg.norm(b,axis=0)
    if not np.allclose(norm.T@norm,np.eye(3),atol=1e-5): raise ValueError(f'{path}: sheared grid unsupported; no resampling performed')
    if reference is not None:
        if n.shape!=reference.shape: raise ValueError(f'{path}: shape mismatch {n.shape} vs {reference.shape}')
        if not np.allclose(a,reference.affine,rtol=1e-5,atol=1e-4): raise ValueError(f'{path}: affine mismatch; refusing resampling')
    data=n.get_fdata(dtype=np.float32)
    if not np.isfinite(data).all(): raise ValueError(f'{path}: nonfinite voxel value')
    if binary and not np.isin(data,[0,1]).all(): raise ValueError(f'{path}: binary labels must be exactly 0 or 1')
    return n, data.astype(np.uint8) if binary else data

def spatial(n):
    transform=ornt_transform(io_orientation(n.affine),axcodes2ornt(('R','A','S')))
    a=n.affine@inv_ornt_aff(transform,n.shape)
    shape=tuple(int(n.shape[int(i)]) for i in np.argsort(transform[:,0]))
    spacing=np.linalg.norm(a[:3,:3],axis=0)
    normal=np.cross(a[:3,0],a[:3,1]); normal/=np.linalg.norm(normal)
    if normal@a[:3,2]<0: normal=-normal
    centers=[nib.affines.apply_affine(a,[(shape[0]-1)/2,(shape[1]-1)/2,k]).tolist() for k in range(shape[2])]
    return {'shape':list(shape),'affine':a.tolist(),'spacing_mm':spacing.tolist(),'axis_codes':list(nib.aff2axcodes(a)),
            'unit':'mm','native_shape':list(n.shape),'native_affine':n.affine.tolist(),'to_ras_ornt':transform.tolist(),
            'slice_centers_ras_mm':centers,'slice_positions_mm':[float(np.dot(c,normal)) for c in centers],
            'slice_normal_ras':normal.tolist(),'display_transform':'flipud(RAS[:,:,k].T); right R, top A; nearest-neighbor masks',
            'display_aspect':float(shape[0]*spacing[0]/(shape[1]*spacing[1]))}
def display(arr,k): return np.flipud(arr[:,:,k].T)
def save_overlay(p,classes):
    first=next(iter(classes.values())); out=np.zeros((*first.shape,4),np.uint8)
    for name,mask in classes.items(): out[mask]=(*COLORS[name],255)
    Image.fromarray(out).save(p)
def labels_png(p,arr):
    out=np.zeros((*arr.shape,3),np.uint8); out[:,:,0]=arr%256; out[:,:,1]=arr//256
    Image.fromarray(out).save(p)
def mesh(binary,affine,path,offset=None):
    if not binary.any(): return {'status':'empty','vertices':0,'triangles':0}
    v,f,_,_=marching_cubes(np.pad(binary,1),level=.5,step_size=1,allow_degenerate=False)
    v=v-1+(np.zeros(3) if offset is None else np.asarray(offset))
    v=nib.affines.apply_affine(affine,v).astype('<f4')
    if np.linalg.det(np.asarray(affine)[:3,:3])<0: f=f[:,::-1]
    f=f.astype('<u4')
    # Binary: uint32 vertex count, uint32 triangle count, packed float32 xyz, uint32 triangles.
    path.write_bytes(np.array([len(v),len(f)],dtype='<u4').tobytes()+v.tobytes()+f.tobytes())
    return {'status':'ready','path':path.name,'vertices':len(v),'triangles':len(f),'bounds_ras_mm':[v.min(0).tolist(),v.max(0).tolist()], 'sha256':sha(path)}
def component_analysis(mask,affine,out,method,gt=None):
    out.mkdir(parents=True,exist_ok=True)
    labels,count=ndi.label(mask,structure=ndi.generate_binary_structure(3,3))
    if count>65535: raise ValueError('more than 65535 components: label transport limit')
    sizes=np.bincount(labels.ravel())[1:]; order=np.argsort(-sizes,kind='stable')+1
    remap=np.zeros(count+1,np.uint16); remap[order]=np.arange(1,count+1)
    labels=remap[labels]
    spacing=np.linalg.norm(np.asarray(affine)[:3,:3],axis=0); volume=abs(np.linalg.det(np.asarray(affine)[:3,:3]))/1000
    distance=ndi.distance_transform_edt(labels!=1,sampling=spacing) if count>1 else None
    gt_distance=ndi.distance_transform_edt(~gt.astype(bool),sampling=spacing) if gt is not None else None
    comps=[]
    for idx,sl in enumerate(ndi.find_objects(labels),1):
        local=labels[sl]==idx; n=int(local.sum()); origin=np.array([s.start for s in sl]); coords=np.argwhere(local)+origin
        lo=coords.min(0); hi=coords.max(0)
        corners=np.array(list(itertools.product(*[(lo[i]-.5,hi[i]+.5) for i in range(3)])))
        world=nib.affines.apply_affine(affine,corners); centroid=nib.affines.apply_affine(affine,coords.mean(0))
        geom=mesh(local,affine,out/f'{method}_{idx}.mesh',origin)
        overlap=int(np.count_nonzero(gt[sl][local])) if gt is not None else None
        gap=float(distance[sl][local].min()) if distance is not None and idx!=1 else 0.0
        comps.append({'id':idx,'voxels':n,'volume_ml':n*volume,'bbox_ijk':[lo.tolist(),hi.tolist()],
                      'bbox_ras_mm':[world.min(0).tolist(),world.max(0).tolist()],'centroid_ras_mm':centroid.tolist(),
                      'representative_k':int(round(coords[:,2].mean())),'gt_intersection_voxels':overlap,
                      'min_distance_to_gt_mm':float(gt_distance[sl][local].min()) if gt_distance is not None else None,
                      'max_distance_to_gt_mm':float(gt_distance[sl][local].max()) if gt_distance is not None else None,
                      'contains_gt_distant_over_20mm':bool(gt_distance[sl][local].max()>20) if gt_distance is not None else None,
                      'min_distance_to_largest_prediction_mm':gap,'separated_over_20mm':gap>20,'mesh':geom})
    labdir=out/'labels'/method; labdir.mkdir(parents=True,exist_ok=True)
    for k in range(labels.shape[2]): labels_png(labdir/f'{k:03}.png',display(labels,k))
    return {'connectivity':26,'count':count,'components':comps,'labels_path':f'labels/{method}',
            'gt_available':gt is not None,'distance_definition':'minimum voxel-center distance to largest predicted component; >20mm descriptive, not a clinical/FP label'}
def error_analysis(pred,gt,affine):
    fp=pred.astype(bool)&~gt.astype(bool); fn=gt.astype(bool)&~pred.astype(bool); tp=pred.astype(bool)&gt.astype(bool)
    a=np.asarray(affine); vv=abs(np.linalg.det(a[:3,:3])); area=np.linalg.norm(np.cross(a[:3,0],a[:3,1]))
    rows=[{'k':k,'fp_voxels':int(fp[:,:,k].sum()),'fn_voxels':int(fn[:,:,k].sum()),'tp_voxels':int(tp[:,:,k].sum()),
           'fp_mm2':float(fp[:,:,k].sum()*area),'fn_mm2':float(fn[:,:,k].sum()*area),'tp_mm2':float(tp[:,:,k].sum()*area)} for k in range(pred.shape[2])]
    g=float(gt.sum()*vv/1000); p=float(pred.sum()*vv/1000); f=float(fp.sum()*vv/1000); n=float(fn.sum()*vv/1000)
    denom=int(pred.sum()+gt.sum()); union=int((pred.astype(bool)|gt.astype(bool)).sum()); t=int(tp.sum())
    return {'slices':rows,'volume':{'gt_ml':g,'pred_ml':p,'fp_ml':f,'fn_ml':n,'net_error_ml':p-g,'absolute_error_ml':abs(p-g)},
            'metrics':{'dice_3d':2*t/denom if denom else 1.0,'iou_3d':t/union if union else 1.0,
                       'precision_3d':t/int(pred.sum()) if pred.any() else None,'recall_3d':t/int(gt.sum()) if gt.any() else None}},fp

def export_case(spec,out):
    cid=safe_id(spec['case_id']); ct_path=Path(spec['ct']); paths=[ct_path]
    gt_path=spec.get('gt'); preds=spec.get('predictions',[])
    ids=[safe_id(p['id']) for p in preds]
    if not ids: raise ValueError('at least one prediction mask is required')
    if len(set(ids))!=len(ids) or any(i in {'gt','ct','meshes','labels','case','index'} for i in ids) or any(i+'_error' in ids for i in ids): raise ValueError('duplicate/reserved prediction id')
    if gt_path: paths.append(Path(gt_path))
    if any(p.get('color_key','unet') not in ('traditional','unet') for p in preds): raise ValueError('color_key must be traditional or unet')
    paths += [Path(p['path']) for p in preds]
    before={str(p):sha(p) for p in paths}
    ct,ctdata=validate_nifti(ct_path); s=spatial(ct); transform=np.array(s['to_ras_ornt']); affine=np.array(s['affine'])
    arrays={'ct':apply_orientation(ctdata,transform)}
    if gt_path: arrays['gt']=apply_orientation(validate_nifti(gt_path,ct,True)[1],transform)
    for p in preds: arrays[p['id']]=apply_orientation(validate_nifti(p['path'],ct,True)[1],transform)
    # Fully validate before writing any payload.
    out.mkdir(parents=True,exist_ok=False); (out/'meshes').mkdir()
    for name in arrays: (out/name).mkdir()
    for p in preds:
        if gt_path: (out/(p['id']+'_error')).mkdir()
    for k in range(s['shape'][2]):
        im=np.rint((np.clip(display(arrays['ct'],k),-100,200)+100)/300*255).astype(np.uint8)
        Image.fromarray(im).save(out/'ct'/f'{k:03}.png')
        for name,arr in arrays.items():
            if name=='ct': continue
            color='gt' if name=='gt' else next((p.get('color_key','unet') for p in preds if p['id']==name),'unet')
            save_overlay(out/name/f'{k:03}.png',{color:display(arr,k).astype(bool)})
            if name!='gt' and gt_path:
                pr=display(arr,k).astype(bool); g=display(arrays['gt'],k).astype(bool)
                save_overlay(out/(name+'_error')/f'{k:03}.png',{'tp':pr&g,'fp':pr&~g,'fn':g&~pr})
    methods=[]
    for p in preds:
        mid=p['id']; pred=arrays[mid]; gt=arrays.get('gt'); analysis=None; fpc=None
        comp=component_analysis(pred,affine,out/'meshes',mid,gt)
        if gt is not None:
            analysis,fp=error_analysis(pred,gt,affine); fpc=component_analysis(fp,affine,out/'meshes',mid+'_fp',gt)
        methods.append({'id':mid,'name':p.get('name',mid),'version':p.get('version','imported binary mask'),
                        'color_key':p.get('color_key','unet'),'source':{'path':str(p['path']),'sha256':before[str(Path(p['path']))]},
                        'components':comp,'fp_components':fpc,'analysis':analysis,'frozen_metrics':None})
    gt_mesh=mesh(arrays['gt'],affine,out/'meshes'/'gt.mesh') if gt_path else None
    for p in paths:
        if sha(p)!=before[str(p)]: raise RuntimeError(f'input changed during export: {p}')
    meta={'case_id':cid,'title':spec.get('title',cid),'analysis_note':'Imported aligned 3D CT + binary masks',
          'spatial':s,'default_slice':int(np.argmax(arrays['gt'].sum((0,1)))) if gt_path else s['shape'][2]//2,
          'targets':[],'methods':methods,'gt_mesh':gt_mesh,'has_gt':bool(gt_path),'status':'voxel_verified',
          'ct_source':{'path':str(ct_path),'sha256':before[str(ct_path)]},'gt_source':{'path':str(gt_path),'sha256':before[str(Path(gt_path))]} if gt_path else None,
          'asset_base':f'demo/{cid}','mesh_base':f'demo/{cid}/meshes','static_figures':[],
          'display_modes':['ct']+(['gt'] if gt_path else [])+ids+([i+'_error' for i in ids] if gt_path else []),
          'generated_at':datetime.now(timezone.utc).isoformat(),'hu_window':[-100,200], 'inputs':before}
    dump(out/'case.json',meta); return meta

def snapshot_source(root):
    files=[]
    b1=root/'deliverables/course_web_demo'
    files += [p for p in b1.rglob('*') if p.is_file()]
    for sub in ['results/unet_stage8_final_test','src/common','configs']:
        files += [p for p in (root/sub).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    for base in ['outputs/traditional_v2_open1mm','outputs/unet_stage8_final_test_seed42_epoch17']:
        for cid in ['spleen_8','spleen_59','spleen_17']:
            files += [p for p in (root/base/cid).rglob('*') if p.is_file()]
    return {str(p.relative_to(root)).replace('\\','/'):sha(p) for p in files}

def migrate_b1(source,out):
    source=source.resolve(); b1=source/'deliverables/course_web_demo'
    if source==out.resolve() or source in out.resolve().parents: raise ValueError('output must be outside protected source')
    before=snapshot_source(source); dump(ROOT/'docs/source-before.json',before)
    prov=read_json(b1/'provenance.json')
    text=(b1/'js/data.js').read_text(encoding='utf-8-sig'); b=json.loads(text[text.index('{'):text.rindex('}')+1])
    rows=list(csv.DictReader((source/'results/unet_stage8_final_test/all_methods_test_metrics.csv').open(encoding='utf-8-sig')))
    cases=[]; audit=[]
    for cid,c in b['cases'].items():
        d=prov['cases'][cid]['display_export']; srec=d['sources']; destination=out/cid
        if destination.exists(): raise FileExistsError(f'refusing overwrite: {destination}')
        # Migrate only current verified build, byte for byte. No pixel-derived measurements.
        shutil.copytree(b1/c['assetBase'],destination); (destination/'meshes').mkdir()
        for record in d['slices']:
            k=record['canonical_k']
            for mode,expected in record['png_sha256'].items():
                if sha(destination/mode/f'{k:03}.png')!=expected: raise ValueError(f'B1 PNG hash mismatch {cid}/{mode}/{k}')
        access={}; loaded={}
        for name,rec in srec.items():
            try:
                n,arr=validate_nifti(rec['path'],binary=name!='ct')
                if sha(rec['path'])!=rec['sha256']: raise ValueError(f'input hash differs from B1: {name}')
                if list(n.shape)!=rec['shape'] or not np.allclose(n.affine,rec['affine'],rtol=1e-5,atol=1e-4): raise ValueError('B1 spatial disagreement')
                loaded[name]=(n,arr); access[name]={'status':'readable','sha256':rec['sha256']}
            except PermissionError as e: access[name]={'status':'blocked','error':str(e),'type':'PermissionError'}
        reference=loaded['traditional'][0]; s=spatial(reference)
        if s['shape']!=d['canonical_shape'] or not np.allclose(s['affine'],d['canonical_affine']): raise ValueError('canonical mismatch')
        affine=np.asarray(s['affine']); transform=np.asarray(s['to_ras_ornt']); gt=None
        if 'gt' in loaded:
            gn,garr=loaded['gt']; validate_nifti(srec['gt']['path'],reference,True); gt=apply_orientation(garr,transform)
        methods=[]
        for mid,version in METHODS.items():
            n,arr=loaded[mid]
            if n.shape!=reference.shape or not np.allclose(n.affine,reference.affine): raise ValueError('prediction mismatch')
            ras=apply_orientation(arr,transform); comp=component_analysis(ras,affine,destination/'meshes',mid,gt)
            frozen=next(r for r in rows if r['case_id']==cid and r['method']==version)
            for key,value in c['metrics'][mid].items():
                if frozen[key]!=value: raise ValueError(f'frozen CSV mismatch {cid}/{mid}/{key}')
            pred_ml=float(ras.sum()*abs(np.linalg.det(affine[:3,:3]))/1000)
            if abs(pred_ml-float(frozen['pred_volume_ml']))>1e-6: raise ValueError('new prediction volume disagrees with frozen CSV')
            analysis=None; fpc=None
            if gt is not None:
                analysis,fp=error_analysis(ras,gt,affine); fpc=component_analysis(fp,affine,destination/'meshes',mid+'_fp',gt)
            methods.append({'id':mid,'name':'传统 V2' if mid=='traditional' else 'U-Net','version':version,'color_key':mid,
                'source':srec[mid],'components':comp,'fp_components':fpc,'analysis':analysis,'frozen_metrics':frozen,
                'computed_pred_volume_ml':pred_ml,'volume_crosscheck_delta_ml':pred_ml-float(frozen['pred_volume_ml'])})
        figures=[]
        for key,rel in c['figures'].items():
            target=destination/f'{key}.png'; shutil.copyfile(b1/rel,target); figures.append(f'demo/{cid}/{key}.png')
            if sha(target)!=sha(b1/rel): raise ValueError('static figure copy mismatch')
        targets=[]
        for t in c['targets']:
            world=nib.affines.apply_affine(reference.affine,t['native']); ijk=nib.affines.apply_affine(np.linalg.inv(affine),world)
            if int(round(ijk[2]))!=t['slice']: raise ValueError('target spatial mismatch')
            targets.append({**t,'label':t['name']+' · 已核实定位','ras_mm':world.tolist(),'canonical_ijk':ijk.tolist(),
                            'prediction_component_ids':{m['id']:int(0) for m in methods}})
        # Point labels read from true prediction masks, never from display PNG.
        for t in targets:
            for m in methods:
                ar=apply_orientation(loaded[m['id']][1],transform)
                labs,_=ndi.label(ar,ndi.generate_binary_structure(3,3)); sz=np.bincount(labs.ravel())[1:]; order=np.argsort(-sz,kind='stable')+1
                point=int(labs[tuple(np.rint(t['canonical_ijk']).astype(int))]); t['prediction_component_ids'][m['id']]=int(np.where(order==point)[0][0]+1) if point else 0
        meta={'case_id':cid,'title':c['title'],'analysis_note':c['analysis'],'spatial':s,'default_slice':c['defaultSlice'],
              'targets':targets,'methods':methods,'gt_mesh':mesh(gt,affine,destination/'meshes'/'gt.mesh') if gt is not None else None,
              'has_gt':gt is not None,'status':'b1_png_verified_prediction_voxels_verified','access':access,
              'asset_base':f'demo/{cid}','mesh_base':f'demo/{cid}/meshes','display_modes':['ct','gt','traditional','unet','traditional_error','unet_error'],
              'static_figures':figures,'hu_window':[-100,200],'ct_source':srec['ct'],'gt_source':srec['gt'],
              'b1_build_id':b['buildId'],'generated_at':datetime.now(timezone.utc).isoformat(),
              'blocked_reason':None if gt is not None else '原始 CT/GT PermissionError；PNG 为 B1 已验收真实素材。新逐切片 FP/FN、GT 相交与 GT 三维表面未生成。'}
        dump(destination/'case.json',meta); cases.append({'case_id':cid,'title':c['title'],'manifest':f'demo/{cid}/case.json'})
        audit.append({'case_id':cid,'access':access,'prediction_component_counts':{m['id']:m['components']['count'] for m in methods},'gt_analysis_available':gt is not None})
    after=snapshot_source(source)
    if before!=after: raise RuntimeError('protected source hash changed!')
    dump(ROOT/'docs/source-integrity.json',{'files_checked':len(before),'unchanged':before==after,'before':before,'after':after})
    dump(ROOT/'docs/data-audit.json',{'cases':audit,'source_unchanged':True,'source_files_checked':len(before)})
    summary=list(csv.DictReader((source/'results/unet_stage8_final_test/summary_mean_sample_sd.csv').open(encoding='utf-8-sig')))
    dump(out/'index.json',{'schema_version':'1.0','cases':cases,'frozen_summary':summary,'metric_source':str(source/'results/unet_stage8_final_test/all_methods_test_metrics.csv'),
         'metric_source_sha256':sha(source/'results/unet_stage8_final_test/all_methods_test_metrics.csv'),'connectivity':26,'generated_at':datetime.now(timezone.utc).isoformat()})
    for entry in cases: enrich_case(out/entry['case_id']/'case.json')
    print(json.dumps(audit,ensure_ascii=False))

def enrich_case(path):
    c=read_json(path)
    if not c['has_gt']: return
    gt_path=c['gt_source']['path']; n,gt_native=validate_nifti(gt_path,binary=True)
    if sha(gt_path)!=c['gt_source']['sha256']: raise ValueError('GT source hash differs')
    s=spatial(n); transform=np.array(s['to_ras_ornt']); gt=apply_orientation(gt_native,transform).astype(bool)
    distance=ndi.distance_transform_edt(~gt,sampling=s['spacing_mm'])
    for method in c['methods']:
        source=method['source']; pn,pred_native=validate_nifti(source['path'],n,True)
        if sha(source['path'])!=source['sha256']: raise ValueError('prediction source hash differs')
        pred=apply_orientation(pred_native,transform).astype(bool)
        for kind,mask in [('components',pred),('fp_components',pred&~gt)]:
            if method.get(kind) is None: continue
            labels,count=ndi.label(mask,ndi.generate_binary_structure(3,3)); sizes=np.bincount(labels.ravel())[1:]; order=np.argsort(-sizes,kind='stable')+1
            remap=np.zeros(count+1,np.uint16);remap[order]=np.arange(1,count+1); labels=remap[labels]
            for comp,sl in zip(method[kind]['components'],ndi.find_objects(labels)):
                values=distance[sl][labels[sl]==comp['id']]
                comp['min_distance_to_gt_mm']=float(values.min());comp['max_distance_to_gt_mm']=float(values.max())
                comp['contains_gt_distant_over_20mm']=bool(values.max()>20)
            for t in c['targets']:
                point=tuple(np.rint(t['canonical_ijk']).astype(int))
                t.setdefault('fp_component_ids' if kind=='fp_components' else 'prediction_component_ids',{})[method['id']]=int(labels[point])
        for t in c['targets']:
            point=tuple(np.rint(t['canonical_ijk']).astype(int)); t['gt_foreground']=bool(gt[point]);t['distance_to_gt_mm']=float(distance[point])
    dump(path,c)

def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('migrate-b1'); p.add_argument('--source',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('import'); p.add_argument('--spec',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output=require_local_output(args.output); args.output.mkdir(parents=True,exist_ok=True)
    if args.command=='migrate-b1': migrate_b1(args.source,args.output)
    else:
        spec=read_json(args.spec); cid=safe_id(spec['case_id']); final=args.output/cid
        if final.exists(): raise FileExistsError(f'refusing overwrite: {final}')
        existing_index=read_json(args.output/'index.json') if (args.output/'index.json').exists() else {'schema_version':'1.0','cases':[]}
        if any(c['case_id']==cid for c in existing_index['cases']): raise ValueError('case id already registered')
        # Atomic publish: failed exports never replace an existing case or index.
        with tempfile.TemporaryDirectory(prefix='.import-',dir=args.output) as tmp:
            built=Path(tmp)/cid; meta=export_case(spec,built); shutil.move(str(built),final)
        index_path=args.output/'index.json'; index=read_json(index_path) if index_path.exists() else {'schema_version':'1.0','cases':[]}
        if any(c['case_id']==cid for c in index['cases']): raise ValueError('case id already registered')
        index['cases'].append({'case_id':cid,'title':meta['title'],'manifest':f'demo/{cid}/case.json'})
        temp=index_path.with_suffix('.tmp'); dump(temp,index); os.replace(temp,index_path)
        print(f'EXPORTED {cid} -> {final}')
if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'EXPORT FAILED: {type(e).__name__}: {e}',file=sys.stderr); sys.exit(1)
