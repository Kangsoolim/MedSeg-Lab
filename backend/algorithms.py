"""Thin execution adapters around byte-identical course spatial/V2/model modules."""
import importlib.metadata
import time
from pathlib import Path
import numpy as np
from backend.config import E17_SHA, ROOT, read, sha, validate_input, write
from backend.vendor.io_spatial import load_case, prepare_slices, restore_mask, save_original_mask
from backend.vendor.traditional_segmentation import confidence_connected_roi
from backend.vendor.region_postprocess import postprocess_region_native

PREPROCESSING = 'closestRAS_HU-57_164_256_linear_CT_nearest_GT_v1'

def check_vendor():
    records = read(ROOT / 'backend/vendor/SOURCES.json')
    for name, item in records.items():
        if sha(ROOT / 'backend/vendor' / name) != item['sha256']:
            raise ValueError(f'Algorithm source integrity mismatch: {name}')
    return records

def validate_selection(shape, p):
    seed, roi = p['seed'], p['roi']
    if seed is None or roi is None:
        raise ValueError('Choose a seed and half-open 3D ROI before running V2')
    if not all(0 <= seed[d] < shape[d] for d in range(3)):
        raise ValueError(f'Seed is outside canonical image shape {shape}')
    if not all(0 <= roi[2*d] < roi[2*d+1] <= shape[d] for d in range(3)):
        raise ValueError(f'Invalid half-open ROI for canonical shape {shape}')
    if not all(roi[2*d] <= seed[d] < roi[2*d+1] for d in range(3)):
        raise ValueError('Seed must be inside the half-open ROI')

def execute(spec, out, stage):
    started = time.perf_counter()
    cfg, entry, p = spec['config'], spec['input'], spec['parameters']
    source_modules = check_vendor()
    stage('validating_input')
    for path, expected in spec['source_hashes'].items():
        if sha(path) != expected:
            raise ValueError('Input changed since job submission: ' + path)
    validate_input(entry['ct'], cfg)
    # Prediction never sees GT. Evaluation/export is a separate stage below.
    case = load_case(entry['ct'])
    details = {'source_modules': source_modules,
               'code_sha256': {name:sha(ROOT/name) for name in ['backend/algorithms.py','backend/worker.py','backend/config.py','data_tools/export_package.py']},
               'preprocessing_version': PREPROCESSING,
               'gt_used_for_prediction': False, 'device': 'cpu'}
    if spec['algorithm'] == 'traditional_v2':
        validate_selection(case['canonical_shape'], p)
        import SimpleITK as sitk
        sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(2)
        stage('confidence_connected')
        raw, base = confidence_connected_roi(case, tuple(p['seed']), tuple(p['roi']),
                      p['iterations'], p['multiplier'], p['radius'])
        save_original_mask(raw, case, out / 'region_growing.nii.gz')
        stage('morphology_and_seed_component')
        final, post = postprocess_region_native(raw, case, tuple(p['seed']), tuple(p['roi']), p['opening_mm'], 0.0)
        # The course module performs opening + seed selection together. Reproduce
        # the actual pre-selection morphology stage using its exact footprint.
        from backend.vendor.region_postprocess import physical_disk
        from scipy import ndimage as ndi
        from nibabel.orientations import apply_orientation
        canonical = apply_orientation(raw, case['to_ras_ornt']).astype(bool)
        i0,i1,j0,j1,k0,k1 = p['roi']
        if p['opening_mm'] > 0:
            spacing = np.linalg.norm(case['canonical_affine'][:3,:2], axis=0)
            disk = physical_disk(p['opening_mm'], tuple(spacing))
            for k in range(k0,k1):
                canonical[i0:i1,j0:j1,k] = ndi.binary_opening(canonical[i0:i1,j0:j1,k], structure=disk, border_value=0)
        morph = apply_orientation(canonical, case['to_original_ornt']).astype(np.uint8)
        save_original_mask(morph, case, out / 'morphology.nii.gz')
        details.update(base_segmentation=base, postprocess=post, connectivity=6)
    else:
        stage('loading_e17')
        import torch
        from backend.vendor.unet import build_unet
        checkpoint = Path(cfg['checkpoint'])
        actual_sha = sha(checkpoint)
        if actual_sha != E17_SHA:
            raise ValueError('Checkpoint SHA-256 differs from frozen E17')
        saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
        if saved.get('schema_version') not in (1,2) or saved.get('checkpoint_boundary') != 'completed_epoch' or saved['state']['epoch'] != 17:
            raise ValueError('Expected full completed-epoch E17 checkpoint')
        if saved['config']['threshold'] != 0.5 or saved['config']['seed'] != 42:
            raise ValueError('E17 inference configuration mismatch')
        torch.manual_seed(42)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.set_num_threads(4)
        device = 'cuda' if p['device'] == 'auto' and torch.cuda.is_available() else p['device']
        if device == 'auto': device = 'cpu'
        if device == 'cuda' and not torch.cuda.is_available():
            raise ValueError('CUDA requested but unavailable; select CPU or auto')
        model = build_unet().to(device)
        model.load_state_dict(saved['model_state_dict'], strict=True)
        model.eval()
        stage('preprocessing')
        images, meta = prepare_slices(case)
        probabilities = np.empty_like(images)
        with torch.no_grad():
            for start in range(0,len(images),4):
                stage('inference', slices_done=start, slices_total=len(images))
                x = torch.from_numpy(images[start:start+4]).to(device)
                logits = model(x)
                if logits.shape != x.shape or not torch.isfinite(logits).all():
                    raise FloatingPointError('Invalid E17 logits')
                probabilities[start:start+len(x)] = torch.sigmoid(logits).cpu().numpy()
        stage('restoring_native_space', slices_done=len(images), slices_total=len(images))
        final = restore_mask(probabilities, meta, threshold=0.5)
        write(out / 'spatial.json', meta)
        details.update(model='MONAI_2D_UNet_16_32_64_128_256_res2', checkpoint_sha256=actual_sha,
                       checkpoint_epoch=17, weight_tensors=len(saved['model_state_dict']), device=device,
                       batch_size=4, threshold=0.5, precision='FP32; autocast/TF32 disabled',
                       prepared_shape=list(images.shape))
    stage('saving_native_mask')
    mask_path = save_original_mask(final, case, out / 'prediction.nii.gz')
    from data_tools import export_package as ep
    n, _ = ep.validate_nifti(entry['ct'])
    ep.validate_nifti(mask_path, n, True)
    # Evaluation may read GT only after the native prediction has been saved.
    stage('analysis_export')
    if entry.get('gt'): validate_input(entry['gt'], cfg, n, True)
    predictions = [{'id':'run_'+spec['run_id'].replace('-','_'), 'name':'Interactive Experimental Run',
                    'version':spec['algorithm']+' / '+spec['run_id'],
                    'path':str(mask_path), 'color_key':'traditional' if spec['algorithm']=='traditional_v2' else 'unet'}]
    # Preserve official comparators as separate methods; never write to them.
    predictions += entry.get('comparators', [])
    package = ep.export_case({'case_id':entry['case_id'], 'ct':entry['ct'], 'gt':entry.get('gt'),
                              'predictions':predictions}, out/'package')
    base = f'http://127.0.0.1:8008/api/v1/runs/{spec["run_id"]}/files/package'
    package.update(asset_base=base, mesh_base=base+'/meshes',
                   result_status='interactive_experimental', run_id=spec['run_id'],
                   analysis_note='Interactive Experimental Run; exploratory reproduction, not an independent test')
    for method in package['methods']:
        method['computed_pred_volume_ml'] = sum(c['volume_ml'] for c in method['components']['components'])
        method['result_status'] = 'interactive_experimental' if method['id'].startswith('run_') else 'frozen_comparator'
    write(out/'package/case.json', package)
    for path, expected in spec['source_hashes'].items():
        if sha(path) != expected: raise ValueError('Input changed during computation: '+path)
    details.update(foreground_voxels=int(final.sum()), volume_ml=float(final.sum()*abs(np.linalg.det(n.affine[:3,:3]))/1000),
                   native_shape=list(final.shape), native_affine=n.affine.tolist(), output_path=str(mask_path),
                   output_sha256=sha(mask_path), gt_available=bool(entry.get('gt')),
                   metrics=package['methods'][0]['analysis']['metrics'] if entry.get('gt') else None,
                   algorithm_seconds=time.perf_counter()-started,
                   environment={k:importlib.metadata.version(k) for k in ['numpy','scipy','nibabel','SimpleITK','scikit-image']+(['torch','monai'] if spec['algorithm']=='unet_e17' else [])})
    write(out/'result.json', details)
    stage('finished')
