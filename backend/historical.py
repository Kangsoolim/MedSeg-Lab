"""Open only hash-verified saved masks; no historical inference is performed."""
import hashlib
from pathlib import Path
from backend.config import read, sha, write
from backend.experiments import static_catalog
from backend.service import BusyError

def open_historical(store,eid,epoch,case_id):
    record=next((r for r in static_catalog()['experiments'] if r['experiment_id']==eid),None)
    if record is None:raise FileNotFoundError('Archived training experiment unavailable / 归档实验不可用')
    point=next((e for e in record['epochs'] if e['epoch']==epoch),None)
    prediction=next((p for p in (point or {}).get('predictions',[]) if p['case_id']==case_id),None)
    if prediction is None:raise FileNotFoundError('No saved prediction for this Epoch/case / 此轮次病例没有已保存预测')
    if not store.cfg.get('source_root'):raise ValueError('Optional course adapter is not configured')
    source=Path(store.cfg['source_root']).resolve()
    mask=(source/prediction['path']).resolve(strict=True)
    if not mask.is_relative_to(source/'outputs/unet_runs') or sha(mask)!=prediction['sha256']:raise ValueError('Historical mask hash mismatch / 历史掩膜哈希不匹配')
    ct=source/'data/raw/Task09_Spleen/imagesTr'/f'{case_id}.nii.gz'
    gt=source/'data/raw/Task09_Spleen/labelsTr'/f'{case_id}.nii.gz'
    key=hashlib.sha256((eid+'/'+str(epoch)+'/'+case_id+'/'+prediction['sha256']).encode()).hexdigest()[:32]
    with store.lock:
        if store.active:raise BusyError('Wait for the active computation before historical export / 请等待当前计算完成')
        directory=store.path('historical',key)
        manifest=store.path('historical',key,'case.json')
        if manifest.exists():
            saved=read(manifest)
            if saved.get('result_status')=='historical_verified' and all(sha(p)==h for p,h in saved['inputs'].items()):return saved
            raise ValueError('Incomplete or changed historical cache / 历史缓存不完整或来源变化')
        store.capacity()
        if directory.exists():raise ValueError('Incomplete historical export; remove local cache explicitly / 历史导出未完成，请手动清理本地缓存')
        from data_tools.export_package import export_case
        package=export_case({'case_id':case_id,'ct':str(ct),'gt':str(gt),'predictions':[{'id':'historical_unet','name':'Historical saved prediction','version':eid+' / E'+str(epoch),'path':str(mask),'color_key':'unet'}]},directory)
        base=f'http://127.0.0.1:8008/api/v1/historical/{key}/files'
        package.update(asset_base=base,mesh_base=base+'/meshes',result_status='historical_verified',
            analysis_note='Verified saved historical prediction; no new inference / 已核验的真实历史预测，未重新推理',
            historical_source={'experiment_id':eid,'epoch':epoch,'checkpoint':point.get('checkpoint'),'prediction':prediction})
        for m in package['methods']:
            m['computed_pred_volume_ml']=sum(c['volume_ml'] for c in m['components']['components'])
            m['result_status']='historical_verified'
        write(manifest,package)
        return package
