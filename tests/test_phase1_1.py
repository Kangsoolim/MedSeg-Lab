"""Phase 1.1 additions; real source variants remain isolated from the demo index."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data_tools'))
import export_package as ep
import numpy as np
from scipy import ndimage as ndi
from jsonschema import validate

class Phase11Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.package=ep.ROOT/'frontend/public/demo'
  if not (cls.package/'index.json').is_file():raise unittest.SkipTest('Optional private demo package absent')
  cls.cases=[ep.read_json(cls.package/e['case_id']/'case.json') for e in ep.read_json(cls.package/'index.json')['cases']]

 def test_real_six_and_26_connectivity_are_explicit_and_conserve_voxels(self):
  results=[]
  for c in self.cases:
   _,gt=ep.validate_nifti(c['gt_source']['path'],binary=True)
   for m in c['methods']:
    _,pred=ep.validate_nifti(m['source']['path'],binary=True)
    for kind,mask in [('prediction',pred.astype(bool)),('fp',pred.astype(bool)&~gt.astype(bool))]:
     lab6,n6=ndi.label(mask,ndi.generate_binary_structure(3,1));lab26,n26=ndi.label(mask,ndi.generate_binary_structure(3,3))
     record=m['components' if kind=='prediction' else 'fp_components']
     self.assertEqual(record['connectivity'],26);self.assertEqual(n26,record['count']);self.assertGreaterEqual(n6,n26)
     self.assertEqual(np.count_nonzero(lab6),int(mask.sum()));self.assertEqual(np.count_nonzero(lab26),int(mask.sum()))
     self.assertEqual(int(np.bincount(lab6.ravel())[1:].sum()),sum(x['voxels'] for x in record['components']))
     results.append({'case':c['case_id'],'method':m['id'],'kind':kind,'six_connected':n6,'twenty_six_connected':n26,'voxels':int(mask.sum())})
  ep.dump(ep.ROOT/'docs/phase1_1-connectivity.json',{'decision':'User confirmed: retain 26-connected interactive analysis; independently audit six connectivity.','results':results})

 def test_mesh_coordinates_match_source_voxel_extents_and_affine(self):
  checked=0
  for c in self.cases:
   inverse=np.linalg.inv(c['spatial']['affine'])
   for method in c['methods']:
    for comp in method['components']['components']:
     raw=(self.package/c['case_id']/'meshes'/comp['mesh']['path']).read_bytes()
     nv=int(np.frombuffer(raw,dtype='<u4',count=1)[0]);world=np.frombuffer(raw,dtype='<f4',offset=8,count=nv*3).reshape(-1,3)
     voxel=ep.nib.affines.apply_affine(inverse,world)
     # Marching-cubes boundaries must retain native half-voxel extents in each axis.
     np.testing.assert_allclose(voxel.min(0),np.array(comp['bbox_ijk'][0])-.5,atol=.0002)
     np.testing.assert_allclose(voxel.max(0),np.array(comp['bbox_ijk'][1])+.5,atol=.0002)
     checked+=1
  self.assertEqual(checked,37)

 def test_real_optional_gt_import_with_arbitrary_method_id_and_schema(self):
  c=self.cases[0];m=c['methods'][-1];sources=[Path(c['ct_source']['path']),Path(m['source']['path'])];before={str(p):ep.sha(p) for p in sources}
  with tempfile.TemporaryDirectory(dir=ep.ROOT/'tests') as td:
   out=Path(td)/'real_optional_gt'
   spec={'case_id':'real_spleen8_optional_gt_qa','title':'QA variant of real spleen_8','ct':str(sources[0]),'gt':None,'predictions':[{'id':'archived_mask_a','name':'Archived binary mask','path':str(sources[1]),'version':'QA copy of existing frozen mask','color_key':'unet'}]}
   validate(spec,ep.read_json(ep.ROOT/'data_tools/input.schema.json'))
   imported=ep.export_case(spec,out)
   validate(imported,ep.read_json(ep.ROOT/'data_tools/package.schema.json'))
   self.assertFalse(imported['has_gt']);self.assertEqual(imported['display_modes'],['ct','archived_mask_a'])
   self.assertIsNone(imported['methods'][0]['analysis']);self.assertIsNone(imported['methods'][0]['frozen_metrics']);self.assertIsNone(imported['methods'][0]['fp_components'])
   self.assertEqual(imported['spatial']['shape'],c['spatial']['shape']);np.testing.assert_array_equal(imported['spatial']['affine'],c['spatial']['affine']);np.testing.assert_array_equal(imported['spatial']['spacing_mm'],c['spatial']['spacing_mm'])
   self.assertEqual(imported['methods'][0]['components']['count'],m['components']['count'])
   # Persist a small manifest-only browser QA fixture: assets point at the existing
   # real exported package, never fabricated images or a published fake case.
   imported['asset_base']=c['asset_base'];imported['mesh_base']=c['mesh_base'];imported['display_modes']=['ct',m['id']];imported['methods'][0]['id']=m['id'];imported['methods'][0]['components']['labels_path']=m['components']['labels_path']
   for item,original in zip(imported['methods'][0]['components']['components'],m['components']['components']):item['mesh']=original['mesh']
   ep.dump(ep.ROOT/'docs/phase1_1-real-no-gt-manifest.json',imported)
  self.assertEqual(before,{str(p):ep.sha(p) for p in sources})

 def test_real_mask_header_mismatch_and_crop_are_rejected_without_source_change(self):
  c=self.cases[0];path=Path(c['gt_source']['path']);before=ep.sha(path);ref,_=ep.validate_nifti(c['ct_source']['path']);n,arr=ep.validate_nifti(path,binary=True)
  with tempfile.TemporaryDirectory(dir=ep.ROOT/'tests') as td:
   for name,data,affine,error in [('affine',arr,n.affine.copy(),'affine mismatch'),('shape',arr[:-1],n.affine.copy(),'shape mismatch'),('spacing',arr,n.affine.copy(),'affine mismatch')]:
    if name=='affine':affine[0,3]+=5
    if name=='spacing':affine[:3,0]*=2
    variant=ep.nib.Nifti1Image(data,affine);variant.header.set_xyzt_units('mm');p=Path(td)/(name+'.nii.gz');ep.nib.save(variant,p)
    with self.assertRaisesRegex(ValueError,error):ep.validate_nifti(p,ref,True)
   np.testing.assert_array_equal(ref.affine,ep.nib.load(c['ct_source']['path']).affine)
  self.assertEqual(before,ep.sha(path))

if __name__=='__main__':unittest.main(verbosity=2)
