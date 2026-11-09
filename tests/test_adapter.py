"""Meaningful spatial/import invariants. Synthetic fixtures exist only inside isolated tests."""
import sys,tempfile,unittest,subprocess,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data_tools'))
import export_package as ep
import numpy as np
import nibabel as nib

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ep.ROOT/'tests');self.root=Path(self.temp.name)
        self.affine=np.diag([-2.,3.,4.,1.]);self.affine[:3,3]=[40,-20,10]
        self.ct=np.arange(8*9*7,dtype=np.float32).reshape(8,9,7)-200
        self.gt=np.zeros(self.ct.shape,np.uint8);self.gt[1:4,2:6,1:4]=1
        self.pred=self.gt.copy();self.pred[7,8,6]=1;self.pred[1,2,1]=0
        self.ctpath=self.save('ct',self.ct);self.gtpath=self.save('gt',self.gt);self.predpath=self.save('prediction',self.pred)
    def tearDown(self):self.temp.cleanup()
    def save(self,name,data,affine=None,unit='mm'):
        n=nib.Nifti1Image(data,self.affine if affine is None else affine);n.header.set_xyzt_units(unit);p=self.root/(name+'.nii.gz');nib.save(n,p);return p
    def spec(self,gt=True):return {'case_id':'test_case','ct':str(self.ctpath),'gt':str(self.gtpath) if gt else None,'predictions':[{'id':'algorithm_a','name':'Test A','path':str(self.predpath),'version':'test-only','color_key':'unet'}]}
    def test_no_gt_is_viewable_without_overlap_metrics(self):
        c=ep.export_case(self.spec(False),self.root/'out');self.assertFalse(c['has_gt']);self.assertIsNone(c['methods'][0]['analysis']);self.assertIsNone(c['methods'][0]['frozen_metrics']);self.assertNotIn('gt',c['display_modes']);self.assertEqual(c['methods'][0]['components']['count'],2)
    def test_flip_affine_and_all_slice_alignment_and_volume(self):
        before={p:ep.sha(p) for p in [self.ctpath,self.gtpath,self.predpath]};c=ep.export_case(self.spec(),self.root/'out')
        expected=nib.as_closest_canonical(nib.load(self.ctpath));self.assertEqual(c['spatial']['axis_codes'],['R','A','S']);np.testing.assert_allclose(c['spatial']['affine'],expected.affine)
        m=c['methods'][0];a=m['analysis'];self.assertAlmostEqual(a['volume']['fp_ml'],.024,12);self.assertAlmostEqual(a['volume']['fn_ml'],.024,12);self.assertAlmostEqual(a['volume']['net_error_ml'],0,12);self.assertEqual(m['components']['count'],2)
        self.assertEqual(sum(x['fp_voxels'] for x in a['slices']),1);self.assertEqual(sum(x['fn_voxels'] for x in a['slices']),1)
        self.assertEqual(sum(x['voxels'] for x in m['components']['components']),int(self.pred.sum()))
        for comp in m['components']['components']:self.assertTrue((self.root/'out/meshes'/comp['mesh']['path']).is_file())
        self.assertEqual(before,{p:ep.sha(p) for p in before})
    def test_reserved_ids_cannot_overwrite_ct(self):
        spec=self.spec();spec['predictions'][0]['id']='ct'
        with self.assertRaisesRegex(ValueError,'reserved'):ep.export_case(spec,self.root/'out')
    def test_empty_method_list_rejected(self):
        spec=self.spec();spec['predictions']=[]
        with self.assertRaisesRegex(ValueError,'prediction mask'):ep.export_case(spec,self.root/'out')
    def test_shape_mismatch(self):
        wrong=self.save('shape',self.pred[:-1]);ref,_=ep.validate_nifti(self.ctpath)
        with self.assertRaisesRegex(ValueError,'shape mismatch'):ep.validate_nifti(wrong,ref,True)
    def test_affine_mismatch(self):
        a=self.affine.copy();a[0,3]+=1;wrong=self.save('affine',self.pred,a);ref,_=ep.validate_nifti(self.ctpath)
        with self.assertRaisesRegex(ValueError,'affine mismatch'):ep.validate_nifti(wrong,ref,True)
    def test_unknown_unit(self):
        p=self.save('unknown',self.ct,unit='unknown')
        with self.assertRaisesRegex(ValueError,'unit'):ep.validate_nifti(p)
    def test_continuous_mask_rejected(self):
        p=self.save('continuous',self.pred.astype(float)+.01)
        with self.assertRaisesRegex(ValueError,'binary'):ep.validate_nifti(p,binary=True)
    def test_multilabel_rejected(self):
        data=self.pred.copy();data[0,0,0]=2;p=self.save('labels',data)
        with self.assertRaisesRegex(ValueError,'binary'):ep.validate_nifti(p,binary=True)
    def test_nonfinite_rejected(self):
        data=self.ct.copy();data[0,0,0]=np.nan;p=self.save('nan',data)
        with self.assertRaisesRegex(ValueError,'nonfinite'):ep.validate_nifti(p)
    def test_4d_rejected(self):
        p=self.save('4d',self.ct[:,:,:,None])
        with self.assertRaisesRegex(ValueError,'3D'):ep.validate_nifti(p)
    def test_missing_source_explicit(self):
        with self.assertRaises(FileNotFoundError):ep.validate_nifti(self.root/'missing.nii.gz')
    def test_cli_import_publishes_real_package_contract(self):
        spec=self.root/'spec.json';spec.write_text(json.dumps(self.spec(False)),encoding='utf-8');out=self.root/'package'
        result=subprocess.run([sys.executable,'-B',str(ep.ROOT/'data_tools/export_package.py'),'import','--spec',str(spec),'--output',str(out)],capture_output=True,text=True,errors='replace')
        self.assertEqual(result.returncode,0,result.stderr)
        index=ep.read_json(out/'index.json');self.assertEqual(index['cases'][0]['case_id'],'test_case')
        self.assertTrue((out/'test_case/ct/000.png').is_file());self.assertIsNone(ep.read_json(out/'test_case/case.json')['methods'][0]['analysis'])
    def test_cli_failure_preserves_existing_index(self):
        out=self.root/'package';out.mkdir();index=out/'index.json';index.write_text('{"schema_version":"1.0","cases":[]}',encoding='utf-8');before=index.read_bytes()
        spec=self.spec();a=self.affine.copy();a[2,3]+=9;spec['predictions'][0]['path']=str(self.save('wrong_cli',self.pred,a));file=self.root/'bad.json';file.write_text(json.dumps(spec),encoding='utf-8')
        result=subprocess.run([sys.executable,'-B',str(ep.ROOT/'data_tools/export_package.py'),'import','--spec',str(file),'--output',str(out)],capture_output=True,text=True,errors='replace')
        self.assertNotEqual(result.returncode,0);self.assertIn('affine mismatch',result.stderr);self.assertEqual(index.read_bytes(),before);self.assertFalse((out/'test_case').exists());self.assertFalse(list(out.glob('.import-*')))
    def test_output_cannot_escape_new_project(self):
        with self.assertRaisesRegex(ValueError,'outputs must remain'):ep.require_local_output(ep.ROOT.parent/'external-readonly-input'/'output')
    def test_unsafe_id_rejected(self):
        with self.assertRaises(ValueError):ep.safe_id('../escape')
    def test_duplicate_methods_rejected_before_output(self):
        spec=self.spec();spec['predictions']*=2
        with self.assertRaisesRegex(ValueError,'duplicate'):ep.export_case(spec,self.root/'out')
        self.assertFalse((self.root/'out').exists())
    def test_bad_alignment_does_not_publish(self):
        spec=self.spec();a=self.affine.copy();a[2,3]+=9;spec['predictions'][0]['path']=str(self.save('wrong',self.pred,a))
        with self.assertRaisesRegex(ValueError,'affine mismatch'):ep.export_case(spec,self.root/'out')
        self.assertFalse((self.root/'out').exists())
    def test_empty_foreground_is_truthful(self):
        zeros=np.zeros((3,3,3),np.uint8);m=ep.component_analysis(zeros,np.eye(4),self.root/'mesh','test',zeros)
        self.assertEqual(m['count'],0);self.assertEqual(m['components'],[])
    def test_26_connectivity_and_gt_intersection_is_not_error_label(self):
        mask=np.zeros((8,8,8),np.uint8);mask[1,1,1]=1;mask[2,2,2]=1;mask[7,7,7]=1;gt=np.zeros_like(mask);gt[1,1,1]=1
        c=ep.component_analysis(mask,np.diag([2.,3.,4.,1.]),self.root/'mesh','test',gt)
        self.assertEqual(c['count'],2);self.assertEqual(c['components'][0]['gt_intersection_voxels'],1);self.assertEqual(c['components'][1]['gt_intersection_voxels'],0);self.assertAlmostEqual(c['components'][0]['volume_ml'],.048)
    def test_oblique_rotation_preserves_physical_volume(self):
        theta=.3;r=np.array([[np.cos(theta),-np.sin(theta),0],[np.sin(theta),np.cos(theta),0],[0,0,1]])
        a=self.affine.copy();a[:3,:3]=r@a[:3,:3];p=self.save('oblique',self.ct,a)
        n,_=ep.validate_nifti(p);s=ep.spatial(n);np.testing.assert_allclose(s['spacing_mm'],[2,3,4],atol=1e-5)
        positions=np.asarray(s['slice_positions_mm']);np.testing.assert_allclose(np.diff(positions),4,atol=1e-5)
    def test_existing_output_is_not_overwritten(self):
        out=self.root/'out';out.mkdir();(out/'keep.txt').write_text('keep')
        with self.assertRaises(FileExistsError):ep.export_case(self.spec(),out)
        self.assertEqual((out/'keep.txt').read_text(),'keep')
if __name__=='__main__':unittest.main(verbosity=2)
