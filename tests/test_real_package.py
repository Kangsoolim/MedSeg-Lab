"""Independent real-data QA: all voxels, frozen CSV, PNG pixels, components and mesh transport."""
import sys,unittest,json,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data_tools'))
import export_package as ep
import numpy as np
from scipy import ndimage as ndi
from PIL import Image

class RealPackageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.package=ep.ROOT/'frontend/public/demo'
  if not (cls.package/'index.json').is_file():raise unittest.SkipTest('Optional private demo package absent')
  cls.index=ep.read_json(cls.package/'index.json');cls.report=[]
 def test_all_real_cases(self):
  for entry in self.index['cases']:
   with self.subTest(case=entry['case_id']):
    c=ep.read_json(self.package/entry['case_id']/'case.json');ct,ctarr=ep.validate_nifti(c['ct_source']['path']);gn,gtarr=ep.validate_nifti(c['gt_source']['path'],ct,True)
    self.assertEqual(ep.sha(c['ct_source']['path']),c['ct_source']['sha256']);self.assertEqual(ep.sha(c['gt_source']['path']),c['gt_source']['sha256'])
    canon=ep.nib.as_closest_canonical(ct);np.testing.assert_allclose(c['spatial']['affine'],canon.affine);self.assertEqual(c['spatial']['shape'],list(canon.shape))
    transform=np.array(c['spatial']['to_ras_ornt']);gt=ep.apply_orientation(gtarr,transform).astype(bool);ctras=ep.apply_orientation(ctarr,transform)
    for k in range(canon.shape[2]):
     expected=np.rint((np.clip(np.flipud(ctras[:,:,k].T),-100,200)+100)/300*255).astype(np.uint8)
     actual=np.array(Image.open(self.package/c['case_id']/'ct'/f'{k:03}.png'))
     # B1 truncates conversion rather than rounds; both are fixed real HU window, retain B1 exact pixels.
     trunc=((np.clip(np.flipud(ctras[:,:,k].T),-100,200)+100)/300*255).astype(np.uint8)
     self.assertTrue(np.array_equal(actual,trunc) or np.array_equal(actual,expected))
    for method in c['methods']:
     pn,prarr=ep.validate_nifti(method['source']['path'],ct,True);self.assertEqual(ep.sha(method['source']['path']),method['source']['sha256'])
     pred=ep.apply_orientation(prarr,transform).astype(bool);fp=pred&~gt;fn=gt&~pred;tp=pred&gt
     frozen=method['frozen_metrics'];an=method['analysis'];self.assertEqual(int(frozen['fp_voxels']),int(fp.sum()));self.assertEqual(int(frozen['fn_voxels']),int(fn.sum()));self.assertEqual(int(frozen['tp_voxels']),int(tp.sum()))
     for key in ['dice_3d','iou_3d','precision_3d','recall_3d']:self.assertAlmostEqual(an['metrics'][key],float(frozen[key]),places=12)
     vv=abs(np.linalg.det(np.array(c['spatial']['affine'])[:3,:3]));self.assertAlmostEqual(an['volume']['fp_ml'],int(fp.sum())*vv/1000,places=9)
     for k,row in enumerate(an['slices']):
      for name,arr in [('fp',fp),('fn',fn),('tp',tp)]:self.assertEqual(row[f'{name}_voxels'],int(arr[:,:,k].sum()))
      overlay=np.array(Image.open(self.package/c['case_id']/method['id']/f'{k:03}.png'));np.testing.assert_array_equal(overlay[:,:,3]>0,np.flipud(pred[:,:,k].T))
      err=np.array(Image.open(self.package/c['case_id']/(method['id']+'_error')/f'{k:03}.png'))
      for name,arr in [('fp',fp),('fn',fn),('tp',tp)]:np.testing.assert_array_equal((err[:,:,:3]==ep.COLORS[name]).all(2)&(err[:,:,3]>0),np.flipud(arr[:,:,k].T))
     for key,mask in [('components',pred),('fp_components',fp)]:
      lab,count=ndi.label(mask,ndi.generate_binary_structure(3,3));sizes=np.bincount(lab.ravel())[1:];order=np.argsort(-sizes,kind='stable')+1;remap=np.zeros(count+1,np.uint16);remap[order]=np.arange(1,count+1);lab=remap[lab]
      exported=method[key];self.assertEqual(count,exported['count']);self.assertEqual(sum(x['voxels'] for x in exported['components']),int(mask.sum()))
      for comp,sl in zip(exported['components'],ndi.find_objects(lab)):
       loc=lab[sl]==comp['id'];self.assertEqual(comp['voxels'],int(loc.sum()));self.assertEqual(comp['gt_intersection_voxels'],int(gt[sl][loc].sum()));self.assertAlmostEqual(comp['volume_ml'],int(loc.sum())*vv/1000,places=9)
       info=comp['mesh'];mesh_path=self.package/c['case_id']/'meshes'/info['path'];b=mesh_path.read_bytes();nv,nf=struct.unpack('<II',b[:8]);self.assertEqual(len(b),8+12*nv+12*nf);self.assertEqual(nv,info['vertices']);self.assertGreater(nf,0);self.assertEqual(ep.sha(mesh_path),info['sha256'])
       v=np.frombuffer(b,dtype='<f4',offset=8,count=nv*3).reshape(-1,3);np.testing.assert_allclose(v.min(0),info['bounds_ras_mm'][0],atol=1e-5);np.testing.assert_allclose(v.max(0),info['bounds_ras_mm'][1],atol=1e-5)
      for k in range(mask.shape[2]):
       label_png=np.array(Image.open(self.package/c['case_id']/'meshes'/exported['labels_path']/f'{k:03}.png')).astype(np.uint16);np.testing.assert_array_equal(label_png[:,:,0]+256*label_png[:,:,1],np.flipud(lab[:,:,k].T))
    for t in c['targets']:
     world=ep.nib.affines.apply_affine(ct.affine,t['native']);np.testing.assert_allclose(t['ras_mm'],world);self.assertEqual(t['slice'],round(ep.nib.affines.apply_affine(np.linalg.inv(canon.affine),world)[2]))
    self.report.append({'case_id':c['case_id'],'slices':canon.shape[2],'methods':len(c['methods']),'verified':True})
  ep.dump(ep.ROOT/'docs/real-data-qa.json',{'cases':self.report,'all_passed':True,'method':'independent voxel/pixel/CSV/component/mesh checks'})
if __name__=='__main__':unittest.main(verbosity=2)
