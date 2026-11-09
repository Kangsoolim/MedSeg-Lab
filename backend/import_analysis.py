"""Aligned mask import: all paths pass the same configured input policy."""
import uuid
from backend.config import validate_input, sha, write
from backend.service import now, BusyError

def analyze(store,cid,predictions):
    from data_tools.export_package import export_case
    with store.lock:
        if store.active:raise BusyError('Another computation is active')
        if cid not in store.cases:raise ValueError('Unknown registered CT')
        if not 1<=len(predictions)<=8:raise ValueError('Provide 1–8 aligned binary prediction masks')
        store.capacity();entry=store.cases[cid]
        ct,_=validate_input(entry['ct'],store.cfg)
        if entry.get('gt'):validate_input(entry['gt'],store.cfg,ct,True)
        rid=str(uuid.uuid4())
        masks=[]
        for i,path in enumerate(predictions):
            validate_input(path,store.cfg,ct,True)
            masks.append(dict(id='run_'+rid.replace('-','_')+'_import_'+str(i+1),name='Imported mask '+str(i+1),path=path,color_key='unet' if i%2 else 'traditional'))
        directory=store.path(rid);directory.mkdir()
        spec=dict(run_id=rid,case_id=cid,input=entry,algorithm='aligned_masks',predictions=masks)
        write(directory/'spec.json',spec)
        record=dict(run_id=rid,case_id=cid,algorithm='aligned_masks',status='running',created_at=now(),started_at=now(),ended_at=None,parameters={},result_status='Imported analysis')
        write(directory/'record.json',record)
        try:
            package=export_case(dict(case_id=cid,ct=entry['ct'],gt=entry.get('gt'),predictions=masks),directory/'package')
            base=f'http://127.0.0.1:8008/api/v1/runs/{rid}/files/package'
            package.update(asset_base=base,mesh_base=base+'/meshes',run_id=rid,result_status='imported_analysis')
            write(directory/'package/case.json',package)
            record.update(status='completed',ended_at=now(),manifest=base+'/case.json',result=dict(gt_available=bool(entry.get('gt')),source='User-supplied aligned binary masks'))
        except Exception:
            record.update(status='failed',ended_at=now(),error={'message':'Aligned analysis failed; inspect local inputs'})
            write(directory/'record.json',record);raise
        write(directory/'record.json',record)
        return package
