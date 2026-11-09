"""Explicit storage operations confined to validated UUID run directories."""
import hashlib
import json
import shutil
from pathlib import Path
from backend.config import read, write, sha
from backend.service import BusyError, now

ACTIVE={'queued','preparing','running','stopping'}

def locate(store,kind,rid):
    if kind=='training':return store.training.path(rid),store.training.record(rid)
    if kind=='inference':return store.path(rid),store.record(rid)
    raise ValueError('Expected training or inference')

def category(path):
    if path.suffix=='.pt':return 'checkpoints'
    if path.name=='export.zip':return 'exports'
    if path.suffix in ('.log','.jsonl') or 'events' in path.parts:return 'logs'
    if 'previews' in path.parts or 'package' in path.parts or path.suffix in ('.png','.mesh','.gz'):return 'previews'
    return 'metadata'

def plan(store,kind,rid):
    directory,record=locate(store,kind,rid)
    store.inspect_tree(directory)
    files=[];totals={k:0 for k in ('checkpoints','previews','logs','exports','metadata')}
    for path in sorted(directory.rglob('*')):
        store.path(path.relative_to(store.root))
        if path.is_file():
            info=path.stat();group=category(path.relative_to(directory));totals[group]+=info.st_size
            files.append(dict(path=path.relative_to(directory).as_posix(),bytes=info.st_size,kind=group,mtime_ns=info.st_mtime_ns))
    dependents=[]
    for child in store.index.metadata_many(store.training.root.glob('*/record.json')):
        if child.get('parent_run_id')==rid:dependents.append(child['run_id'])
    value=dict(run_id=rid,kind=kind,status=record['status'],created_at=record.get('created_at',''),
        archived=bool(record.get('storage_archived')),bytes=sum(totals.values()),categories=totals,files=files,
        dependents=dependents,parent_run_id=record.get('parent_run_id'),active=record['status'] in ACTIVE,
        cleanup_files=[f['path'] for f in files if f['path']=='export.zip'])
    value['plan_sha256']=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
    return value

def listing(store,kind='',status='',since='',until='',offset=0,limit=50,archived=''):
    if kind not in ('','training','inference') or not 1<=limit<=100 or offset<0:raise ValueError('Invalid storage page/filter')
    rows=[]
    for typ,root in [('inference',store.root),('training',store.training.root)]:
        if kind and kind!=typ:continue
        for record in store.index.metadata_many(root.glob('*/record.json')):
            if status and record['status']!=status:continue
            date=record.get('created_at','')
            if since and date[:10]<since or until and date[:10]>until:continue
            if archived and bool(record.get('storage_archived'))!=(archived=='true'):continue
            rows.append((date,typ,record))
    rows.sort(key=lambda v:(v[0],v[2]['run_id']),reverse=True)
    items=[]
    for date,typ,record in rows[offset:offset+limit]:
        directory,_=locate(store,typ,record['run_id'])
        items.append(dict(run_id=record['run_id'],kind=typ,status=record['status'],created_at=date,
            archived=bool(record.get('storage_archived')),bytes=store.inspect_tree(directory)))
    return dict(items=items,total=len(rows),offset=offset,limit=limit)

def operate(store,kind,rid,action,confirm='',expected=''):
    with store.lock:
        directory,record=locate(store,kind,rid)
        if record['status'] in ACTIVE or (store.active or {}).get('id')==rid:raise BusyError('Active run cannot be changed')
        impact=plan(store,kind,rid)
        if action in ('archive','restore'):
            record['storage_archived']=action=='archive';record['storage_updated_at']=now()
            write(directory/'record.json',record)
            return dict(action=action,run_id=rid)
        if action not in ('cleanup','delete'):raise ValueError('Unknown storage action')
        if confirm!=rid or expected!=impact['plan_sha256']:raise ValueError('Review current impact and confirm full Run ID; plan changed or confirmation missing')
        if action=='cleanup':
            for name in impact['cleanup_files']:store.path(directory.relative_to(store.root),name).unlink()
            return dict(action=action,removed=impact['cleanup_files'])
        if impact['dependents']:raise BusyError('Resume children reference this run; archive it instead')
        # Preserve a small private provenance tombstone before explicit deletion.
        tombstone=dict(run_id=rid,kind=kind,deleted_at=now(),record=record,impact=impact,
            spec=read(directory/'spec.json') if (directory/'spec.json').exists() else None,
            checkpoint_hashes={p.name:sha(p) for p in directory.glob('*.pt')})
        write(store.path('tombstones',kind+'-'+rid+'.json'),tombstone)
        store.inspect_tree(directory)
        shutil.rmtree(directory)
        return dict(action=action,run_id=rid,provenance_retained=True)
