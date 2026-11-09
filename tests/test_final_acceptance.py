"""Independent final acceptance: extra real case, CSV identity and source integrity.

Run with the existing scientific Python; all generated medical assets stay local/ignored.
No algorithms or inference are executed: predictions are existing archived masks.
"""
import csv,json,subprocess,sys,unittest
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi
from jsonschema import validate
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data_tools'))
import export_package as ep

CATALOG=ep.ROOT/'demo/final_acceptance/catalog'
EVIDENCE=ep.ROOT/'docs/final-acceptance'
from backend.config import settings
SOURCE_CONFIGURED=bool(settings().get('source_root'))
SOURCE=Path(settings().get('source_root') or '.')

class FinalAcceptanceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if not SOURCE_CONFIGURED or not (ep.ROOT/'frontend/public/demo/index.json').is_file():raise unittest.SkipTest('Optional course/demo integration profile not configured')
  EVIDENCE.mkdir(parents=True,exist_ok=True)
  cls.original=ep.read_json(ep.ROOT/'frontend/public/demo/index.json')
  cls.report={}

 @classmethod
 def tearDownClass(cls):
  ep.dump(EVIDENCE/'independent-data.json',cls.report)

 def test_extra_real_case_import_cli_schema_metrics_and_no_gt(self):
  cid='spleen_3'
  paths={'ct':SOURCE/f'data/raw/Task09_Spleen/imagesTr/{cid}.nii.gz','gt':SOURCE/f'data/raw/Task09_Spleen/labelsTr/{cid}.nii.gz','prediction':SOURCE/f'outputs/traditional_v2_open1mm/{cid}/traditional_mask.nii.gz'}
  before={str(p):ep.sha(p) for p in paths.values()}
  CATALOG.mkdir(parents=True,exist_ok=True)
  # Each run gets a fresh namespace; previous evidence is retained.
  import time
  run=str(time.time_ns())
  output=CATALOG/run;output.mkdir()
  records=[]
  for has_gt in [True,False]:
   imported_id='acceptance_spleen3_'+('gt' if has_gt else 'no_gt')
   spec={'case_id':imported_id,'title':'Real spleen_3 import '+('with GT' if has_gt else 'without GT'),'ct':str(paths['ct']),'gt':str(paths['gt']) if has_gt else None,'predictions':[{'id':'archived_v2','name':'Archived traditional V2','path':str(paths['prediction']),'version':'existing archived mask; no execution','color_key':'traditional'}]}
   validate(spec,ep.read_json(ep.ROOT/'data_tools/input.schema.json'))
   spec_path=output/(imported_id+'.json');ep.dump(spec_path,spec)
   result=subprocess.run([sys.executable,'-B',str(ep.ROOT/'data_tools/export_package.py'),'import','--spec',str(spec_path),'--output',str(output)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   manifest=ep.read_json(output/imported_id/'case.json');validate(manifest,ep.read_json(ep.ROOT/'data_tools/package.schema.json'))
   self.assertEqual(manifest['has_gt'],has_gt);self.assertEqual(manifest['methods'][0]['id'],'archived_v2')
   n,ct=ep.validate_nifti(paths['ct']);_,pred=ep.validate_nifti(paths['prediction'],n,True);_,gt=ep.validate_nifti(paths['gt'],n,True)
   method=manifest['methods'][0];vv=abs(np.linalg.det(n.affine[:3,:3]))/1000
   self.assertAlmostEqual(sum(c['volume_ml'] for c in method['components']['components']),pred.sum()*vv,places=9)
   if has_gt:
    tp=int(np.count_nonzero(pred.astype(bool)&gt.astype(bool)));union=int(np.count_nonzero(pred.astype(bool)|gt.astype(bool)))
    self.assertAlmostEqual(method['analysis']['metrics']['dice_3d'],2*tp/int(pred.sum()+gt.sum()),places=12)
    self.assertAlmostEqual(method['analysis']['metrics']['iou_3d'],tp/union,places=12)
    self.assertAlmostEqual(method['analysis']['volume']['pred_ml'],pred.sum()*vv,places=9)
   else:
    for key in ['analysis','fp_components','frozen_metrics']:self.assertIsNone(method[key])
    self.assertIsNone(manifest['gt_mesh']);self.assertIsNone(manifest['gt_source'])
   records.append({'case_id':imported_id,'has_gt':has_gt,'shape':manifest['spatial']['shape'],'spacing_mm':manifest['spatial']['spacing_mm'],'prediction_ml':float(pred.sum()*vv),'analysis':method['analysis']['metrics'] if has_gt else None,'components':method['components']['count']})
  index=ep.read_json(output/'index.json');index['cases']=self.original['cases']+index['cases']
  for key in ['frozen_summary','metric_source','metric_source_sha256']:index[key]=self.original[key]
  ep.dump(output/'index.json',index)
  ep.dump(EVIDENCE/'catalog.json',{'directory':str(output),'cases':records})
  self.assertEqual(before,{str(p):ep.sha(p) for p in paths.values()})
  self.report['real_import']={'source_case':'spleen_3','not_in_original_demo':True,'records':records,'input_hashes_unchanged':True,'input_sha256':before,'source_scope':'same source dataset, not cross-center/generalization validation'}
  # Existing three cases and their catalog are untouched, including frozen strings.
  self.assertEqual(self.original,ep.read_json(ep.ROOT/'frontend/public/demo/index.json'))

 def test_formal_csv_package_and_frozen_summary_exact_identity(self):
  with (SOURCE/'results/unet_stage8_final_test/all_methods_test_metrics.csv').open(encoding='utf-8-sig') as handle:rows=list(csv.DictReader(handle))
  with (SOURCE/'results/unet_stage8_final_test/summary_mean_sample_sd.csv').open(encoding='utf-8-sig') as handle:summary=list(csv.DictReader(handle))
  self.assertEqual(summary,self.original['frozen_summary'])
  self.assertEqual(ep.sha(self.original['metric_source']),self.original['metric_source_sha256'])
  records=[]
  for entry in self.original['cases']:
   c=ep.read_json(ep.ROOT/'frontend/public/demo'/entry['case_id']/'case.json')
   for method in c['methods']:
    row=next(r for r in rows if r['case_id']==c['case_id'] and r['method']==ep.METHODS[method['id']])
    self.assertEqual(row,method['frozen_metrics'])
    records.append({'case':c['case_id'],'method':method['id'],'dice':row['dice_3d'],'iou':row['iou_3d']})
  expected={'Traditional_postprocessed_primary':('0.797899','78.716'),'UNet_Epoch17_frozen':('0.886920','25.493')}
  for name,(dice,volume) in expected.items():
   row=next(r for r in summary if r['method']==name)
   self.assertEqual(f"{float(row['dice_3d_mean']):.6f}",dice);self.assertEqual(f"{float(row['abs_volume_error_ml_mean']):.3f}",volume)
  self.report['frozen_metrics']={'exact_csv_identity':True,'cases':records,'summary':summary}

 def test_independent_six_connectivity_bounds_volumes_and_distant_fp(self):
  c=ep.read_json(ep.ROOT/'frontend/public/demo/spleen_17/case.json');n,gt=ep.validate_nifti(c['gt_source']['path'],binary=True)
  m=next(m for m in c['methods'] if m['id']=='unet');_,pred=ep.validate_nifti(m['source']['path'],n,True)
  transform=np.array(c['spatial']['to_ras_ornt']);gt=ep.apply_orientation(gt,transform).astype(bool);pred=ep.apply_orientation(pred,transform).astype(bool)
  distance=ndi.distance_transform_edt(~gt,sampling=c['spatial']['spacing_mm']);records={}
  vv=abs(np.linalg.det(np.array(c['spatial']['affine'])[:3,:3]))/1000
  for name,mask in [('prediction',pred),('fp',pred&~gt)]:
   sets={}
   for conn in [6,26]:
    labels,count=ndi.label(mask,ndi.generate_binary_structure(3,1 if conn==6 else 3));components=[]
    for i,sl in enumerate(ndi.find_objects(labels),1):
     selected=labels[sl]==i;vox=int(selected.sum());intersect=int(gt[sl][selected].sum())
     components.append({'voxels':vox,'volume_ml':vox*vv,'bounds_ijk':[[s.start for s in sl],[s.stop-1 for s in sl]],'gt_intersection_voxels':intersect,'max_distance_to_gt_mm':float(distance[sl][selected].max())})
    self.assertEqual(sum(x['voxels'] for x in components),int(mask.sum()))
    sets[str(conn)]={'count':count,'components':components}
   self.assertEqual(sets['26']['count'],m['components' if name=='prediction' else 'fp_components']['count']);records[name]=sets
  self.assertEqual([records['prediction'][x]['count'] for x in ['6','26']],[38,30]);self.assertEqual([records['fp'][x]['count'] for x in ['6','26']],[246,133])
  self.assertTrue(any(x['gt_intersection_voxels']>0 and x['max_distance_to_gt_mm']>20 for x in records['prediction']['26']['components']))
  for target in c['targets']:
   point=tuple(np.rint(target['canonical_ijk']).astype(int));self.assertEqual(bool(gt[point]),target['gt_foreground']);self.assertAlmostEqual(float(distance[point]),target['distance_to_gt_mm'],places=7)
  self.report['connectivity_spleen17_unet']=records


 def test_invalid_nifti_and_real_multilabel_are_rejected_before_publication(self):
  import tempfile
  c=ep.read_json(ep.ROOT/'frontend/public/demo/spleen_8/case.json');source=Path(c['gt_source']['path']);before=ep.sha(source);n,arr=ep.validate_nifti(source,binary=True)
  with tempfile.TemporaryDirectory(dir=ep.ROOT/'tests') as directory:
   local=Path(directory);corrupt=local/'invalid.nii.gz';corrupt.write_bytes(b'not a NIfTI volume')
   with self.assertRaises(ep.nib.filebasedimages.ImageFileError) as caught:ep.validate_nifti(corrupt)
   self.assertIn('not',str(caught.exception).lower())
   arr=arr.copy();arr.flat[0]=2;variant=ep.nib.Nifti1Image(arr,n.affine);variant.header.set_xyzt_units('mm');label=local/'multilabel.nii.gz';ep.nib.save(variant,label)
   spec={'case_id':'invalid_real_labels','ct':c['ct_source']['path'],'gt':str(label),'predictions':[{'id':'archived','path':c['methods'][0]['source']['path']}]}
   with self.assertRaisesRegex(ValueError,'binary labels must be exactly 0 or 1'):ep.export_case(spec,local/'out')
   self.assertFalse((local/'out').exists())
   self.report['invalid_files']={'corrupt_nifti_error':str(caught.exception).replace(str(corrupt),'[local invalid NIfTI]'),'real_multilabel':'rejected before output','source_unchanged':True}
  self.assertEqual(before,ep.sha(source))
if __name__=='__main__':unittest.main(verbosity=2)


