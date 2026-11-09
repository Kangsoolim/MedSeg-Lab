"""Versioned historical experiments; legacy Run History remains authoritative."""
import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from backend.config import ROOT, read, read_durable, sha, write
from backend.service import BusyError

CATALOG = ROOT/'frontend/public/training/catalog.json'
ID = r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$'

class TrainingEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    run_id: str = Field(pattern=ID)
    epoch: int = Field(ge=0, strict=True)
    step: int | None = Field(default=None, ge=0, strict=True)
    metric_name: str | None = None
    metric_value: float | None = None
    timestamp: str | None = None
    event_type: Literal['metric','checkpoint','epoch_end','stopped']
    checkpoint_reference: str | None = None

class HistoryImport(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    experiment_id: str = Field(pattern=ID)
    format: Literal['csv','json','jsonl']
    content: str = Field(min_length=1, max_length=1_000_000)
    source_name: str = Field(min_length=1, max_length=256)
    # Canonical names -> input column names. metric_name/value for long format;
    # otherwise metrics maps canonical metric names -> wide input columns.
    mapping: dict[str,str] = Field(default_factory=lambda:{'epoch':'epoch','metric_name':'metric_name','metric_value':'metric_value'})
    metrics: dict[str,str] = Field(default_factory=dict)
    definitions: dict[str,dict[str,str]]
    metadata: dict = Field(default_factory=dict)


def static_catalog():
    return read(CATALOG) if CATALOG.is_file() else {'schema_version':1,'experiments':[],'inventory':[],'lineage':[]}


def validate_history_metadata(metadata):
    for key in ['algorithm','dataset','split_id','code_version','device']:
        if metadata.get(key) is not None and not isinstance(metadata[key],str):raise ValueError(f'{key} must be text or null / 必须为文本或空值')
    cases=metadata.get('case_ids')
    if cases is not None and (not isinstance(cases,list) or any(not isinstance(c,str) or not c for c in cases)):
        raise ValueError('case_ids must be an array of case names / case_ids必须为病例名数组')
    if 'hyperparameters' in metadata and not isinstance(metadata['hyperparameters'],dict):raise ValueError('hyperparameters must be an object / 超参数必须为对象')
    for key in ['started_at','ended_at']:validate_timestamp(metadata.get(key),key)
    def finite(value,depth=0):
        if depth>32:raise ValueError('Metadata nesting exceeds limit / 元数据嵌套超限')
        if isinstance(value,float) and not math.isfinite(value):raise ValueError('Non-finite metadata / 非有限元数据')
        if isinstance(value,dict):
            for item in value.values():finite(item,depth+1)
        elif isinstance(value,list):
            for item in value:finite(item,depth+1)
    finite(metadata)


def validate_timestamp(value,name='timestamp'):
    if value is None:return
    if not isinstance(value,str):raise ValueError(f'{name} must be ISO date/time text or null / 时间必须为ISO文本或空值')
    try:datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as error:raise ValueError(f'{name}: invalid ISO date/time / 无效ISO时间') from error


def csv_safe(value):
    # Text only: a negative numeric metric must remain numeric.
    if isinstance(value,str) and (re.match(r'^[\s\ufeff]*[=+@-]',value) or value.startswith(('\t','\r','\n'))):return "'"+value
    return value


def normalize_import(body):
    validate_history_metadata(body.metadata)
    if body.experiment_id.upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        raise ValueError('Reserved Windows Experiment ID / Windows保留实验ID')
    def unique_object(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate JSON key / 重复JSON字段: '+key)
            result[key]=value
        return result
    try:
        if body.format == 'csv':
            reader=csv.DictReader(io.StringIO(body.content.lstrip('\ufeff')),strict=True)
            if reader.fieldnames is None or len(reader.fieldnames)!=len(set(reader.fieldnames)):raise ValueError('Duplicate or missing CSV headers / CSV列名重复或缺失')
            rows=[];locations=[]
            for row in reader:
                rows.append(row);locations.append({'line':reader.line_num,'record_index':len(rows)})
            if any(None in row or any(v is None for v in row.values()) for row in rows):raise ValueError('CSV row has extra columns / CSV行含多余列')
        elif body.format == 'json':
            rows=json.loads(body.content,object_pairs_hook=unique_object)
            locations=[{'record_index':i+1} for i in range(len(rows))] if isinstance(rows,list) else []
        else:
            entries=[(i,line) for i,line in enumerate(body.content.splitlines(),1) if line.strip()]
            rows=[json.loads(line,object_pairs_hook=unique_object) for _,line in entries]
            locations=[{'line':line,'record_index':i+1} for i,(line,_) in enumerate(entries)]
    except (ValueError, csv.Error, RecursionError) as error: raise ValueError('Invalid log file / 日志文件损坏: '+str(error)) from error
    if not isinstance(rows,list) or not rows or len(rows)>20000:
        raise ValueError('Expected 1–20000 log rows / 需要1–20000行日志')
    if not body.definitions: raise ValueError('Metric definitions required / 必须提供指标定义')
    for name,definition in body.definitions.items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}',name) or not all(definition.get(k) for k in ['definition','unit','aggregation']):
            raise ValueError('Each metric requires definition, unit and aggregation / 每项指标需要定义、单位和聚合方式')
    digest=hashlib.sha256(body.content.encode('utf-8')).hexdigest()
    source={'path':body.source_name,'sha256':digest,'kind':'user_import'}
    epochs={}; missing=[]; seen=set()
    for index,row in enumerate(rows):
        location=locations[index];line=location.get('line',index+1)
        if not isinstance(row,dict): raise ValueError(f'Row {line}: expected object / 需要对象')
        raw=row.get(body.mapping.get('epoch','epoch'))
        if isinstance(raw,bool) or not re.fullmatch(r'\d+',str(raw)):
            raise ValueError(f'Row {line}: invalid Epoch / Epoch无效')
        epoch=int(raw)
        if epoch>1_000_000: raise ValueError('Epoch exceeds limit / Epoch超出限制')
        eid=row.get(body.mapping.get('experiment_id','experiment_id'))
        if eid is not None and eid!=body.experiment_id: raise ValueError('Conflicting Experiment ID / 实验ID冲突')
        stage=row.get(body.mapping.get('stage','stage'))
        if stage is not None and not isinstance(stage,str):raise ValueError('stage must be text or null / 阶段必须为文本或空值')
        stage=stage or 'imported'
        required=[body.mapping.get('epoch','epoch'),*body.metrics.values()] if body.metrics else [body.mapping.get(k,k) for k in ['epoch','metric_name','metric_value']]
        if any(column not in row for column in required):raise ValueError('Missing required mapped columns / 缺少必需映射列')
        pairs=[(n,row.get(c)) for n,c in body.metrics.items()] if body.metrics else [(row.get(body.mapping.get('metric_name','metric_name')),row.get(body.mapping.get('metric_value','metric_value')))]
        item=epochs.setdefault(epoch,{'epoch':epoch,'stage':stage,'metrics':{},'sources':{},'timestamp':row.get(body.mapping.get('timestamp','timestamp')),'flags':[]})
        timestamp=row.get(body.mapping.get('timestamp','timestamp'))
        validate_timestamp(timestamp)
        if timestamp and item['timestamp'] and timestamp!=item['timestamp']:raise ValueError('Conflicting Epoch timestamps / 同轮次时间戳冲突')
        if timestamp:item['timestamp']=timestamp
        if item['stage']!=stage: raise ValueError('Conflicting stages at same Epoch; import separate branches / 同轮次阶段冲突，请分别导入分支')
        for name,value in pairs:
            if not isinstance(name,str) or name not in body.definitions: raise ValueError(f'Undefined metric / 未定义指标: {name}')
            key=(epoch,name)
            if key in seen: raise ValueError(f'Duplicate Epoch/metric / 重复轮次指标: {epoch}/{name}')
            seen.add(key)
            if value is None or value=='': number=None;missing.append(f'{epoch}/{name}')
            else:
                if isinstance(value,bool): raise ValueError('Boolean metric is invalid / 布尔值不能作为指标')
                try:number=float(value)
                except (TypeError,ValueError) as error: raise ValueError(f'Row {line}: metric must be numeric / 指标必须为数值') from error
                if not math.isfinite(number): raise ValueError('Non-finite metric rejected / 拒绝非有限指标')
            item['metrics'][name]=number
            item['sources'][name]={**source,**location,'definition':body.definitions[name]['definition']}
    if not any(v is not None for e in epochs.values() for v in e['metrics'].values()):
        raise ValueError('No recorded metric values / 没有已记录的指标值')
    metadata=body.metadata
    return {'schema_version':1,'experiment_id':body.experiment_id,'run_id':body.experiment_id,'type':'training',
            'algorithm':str(metadata.get('algorithm') or 'Unknown'),'name':body.experiment_id,
            'source_kind':'imported_history','status':'historical','created_at':datetime.now(timezone.utc).isoformat(),
            'started_at':metadata.get('started_at'),'ended_at':metadata.get('ended_at'),
            'dataset':metadata.get('dataset'),'split_id':metadata.get('split_id'),'case_ids':metadata.get('case_ids'),
            'code_version':metadata.get('code_version'),'device':metadata.get('device'),
            'hyperparameters':metadata.get('hyperparameters',{}),'checkpoints':[],
            'definitions':body.definitions,'epochs':sorted(epochs.values(),key=lambda e:e['epoch']),
            'sources':[source],'lineage':[],'early_stopping':None,'metadata':metadata,
            'warnings':['Missing values retained as null / 缺失值保留为空: '+', '.join(missing)] if missing else []}


def training_records(store):
    records=list(static_catalog()['experiments'])
    directory=store.path('experiments')
    for f in directory.glob('*/experiment.json'):
        try: records.append(read_durable(store.root,store.path('experiments',f.parent.name,'experiment.json')))
        except (ValueError,OSError) as error: store.storage_warnings.append(str(error))
    return records


def import_history(store,body):
    normalized=normalize_import(body)
    with store.lock:
        records=training_records(store)
        identities={r['experiment_id'].casefold() for r in records}
        identities.update(p.parent.name.casefold() for p in store.root.glob('*/record.json'))
        if hasattr(store,'training'):
            identities.update(p.parent.name.casefold() for p in store.training.root.glob('*/record.json'))
        index=ROOT/'frontend/public/demo/index.json'
        if index.exists():
            for entry in read(index)['cases']:
                case=read(ROOT/'frontend/public'/entry['manifest'])
                identities.update(('frozen_'+entry['case_id']+'_'+m['id']).casefold() for m in case['methods'])
        if body.experiment_id.casefold() in identities:raise BusyError('Experiment ID already exists; no overwrite / 实验ID已存在，不允许覆盖')
        if any(s.get('sha256')==normalized['sources'][0]['sha256'] for r in records for s in r.get('sources',[])):
            raise BusyError('Identical source already imported / 相同日志已经导入')
        store.capacity()
        if len(records)>=1000: raise ValueError('Experiment record limit reached / 实验记录达到上限')
        path=store.path('experiments',body.experiment_id,'experiment.json')
        if path.parent.exists(): raise BusyError('Experiment directory already exists / 实验目录已存在')
        # Preserve exact received content plus mapping receipt; publish record last.
        write(store.path('experiments',body.experiment_id,'source.json'),{'content':body.content,'format':body.format,'mapping':body.mapping,'metrics':body.metrics,'sha256':normalized['sources'][0]['sha256']})
        normalized['source_artifact']='source.json'
        write(path,normalized)
    return normalized


def inference_definitions():
    overlap={'definition':'Native 3D binary overlap; threshold 0.5 for E17','aggregation':'single_patient','unit':'ratio'}
    result={'overlap':overlap}
    for key in ['dice_3d','iou_3d','precision_3d','recall_3d']:
        result[key]={**overlap,'definition':key+'; '+overlap['definition']}
    for key in ['tp_voxels','fp_voxels','fn_voxels','tn_voxels','gt_voxels','pred_voxels']:
        result[key]={'definition':key+' in the complete native 3D binary mask','aggregation':'single_patient','unit':'voxels'}
    for key in ['pred_volume_ml','gt_volume_ml','fp_volume_ml','fn_volume_ml','volume_error_ml_pred_minus_gt','abs_volume_error_ml']:
        result[key]={'definition':key+'; native voxel counts times absolute affine determinant / 1000','aggregation':'single_patient','unit':'mL'}
    result['voxel_volume_mm3']={'definition':'Absolute determinant of native affine linear part','aggregation':'single_patient','unit':'mm3'}
    for key in ['RAVE_percent','signed_relative_volume_error_percent']:
        result[key]={'definition':key+' relative to GT volume','aggregation':'single_patient','unit':'%'}
    result['pred_to_gt_volume_ratio']={'definition':'Native prediction volume / GT volume','aggregation':'single_patient','unit':'ratio'}
    result['runtime_seconds']={'definition':'Elapsed adapter execution including analysis export','aggregation':'single_run','unit':'s'}
    return result


def numeric_reference(fields):
    # Preserve exact original strings separately; expose only defined numeric metrics.
    result={}
    for key in inference_definitions():
        if key not in fields:continue
        raw=fields[key]
        if raw is None or raw=='':result[key]=None;continue
        number=float(raw)
        if not math.isfinite(number):raise ValueError('Non-finite frozen reference metric')
        result[key]=int(number) if key.endswith('_voxels') else number
    return result


def unified_records(store):
    records=training_records(store)
    if hasattr(store,'training'):
        records.extend(store.training.projection(r['run_id']) for r in store.training.list())
    # Projection only: never migrate, duplicate or rewrite legacy records.
    for run in store.list():
        result=run.get('result') or {}
        spec=read_durable(store.root,store.path(run['run_id'],'spec.json'))
        package=store.path(run['run_id'],'package','case.json')
        method=read(package)['methods'][0] if package.exists() else {}
        records.append({'schema_version':1,'experiment_id':run['run_id'],'run_id':run['run_id'],
            'name':run['case_id']+' / '+run['algorithm'],'type':'traditional' if run['algorithm']=='traditional_v2' else 'inference',
            'algorithm':run['algorithm'],'case_ids':[run['case_id']],'status':run['status'],
            'created_at':run['created_at'],'started_at':run.get('started_at'),'ended_at':run.get('ended_at'),
            'dataset':None,'split_id':None,'source_kind':'interactive_experimental',
            'input_hashes':{k:spec.get('source_hashes',{}).get(v) for k,v in [('ct',spec['input']['ct']),('gt',spec['input'].get('gt'))] if v},
            'code_version':result.get('code_sha256'),'device':result.get('device'),'hyperparameters':run['parameters'],
            'checkpoint_sha256':result.get('checkpoint_sha256'),'checkpoint_epoch':result.get('checkpoint_epoch'),
            'training_experiment_id':next((t['experiment_id'] for t in records if t['type']=='training' and any(c['sha256']==result.get('checkpoint_sha256') for c in t.get('checkpoints',[]))),None),
            'metrics':{**(result.get('metrics') or {}),'pred_volume_ml':result.get('volume_ml'),
                       'fp_volume_ml':(method.get('analysis') or {}).get('volume',{}).get('fp_ml'),
                       'fn_volume_ml':(method.get('analysis') or {}).get('volume',{}).get('fn_ml'),
                       'runtime_seconds':result.get('algorithm_seconds')},
            'gt_available':result.get('gt_available',False),'manifest':run.get('manifest'),'method_id':method.get('id'),
            'sources':[{'path':str(store.path(run['run_id'],'record.json')),'sha256':sha(store.path(run['run_id'],'record.json'))}],
            'definitions':inference_definitions(),
            'outputs':{'prediction':result.get('output_path'),'sha256':result.get('output_sha256')}})
    # Frozen reference metadata is read from the same authoritative case catalog.
    index=ROOT/'frontend/public/demo/index.json'
    if index.exists():
        for entry in read(index)['cases']:
            manifest_path=ROOT/'frontend/public'/entry['manifest']
            case=read(manifest_path)
            for m in case['methods']:
                reference_metrics=numeric_reference(m.get('frozen_metrics') or (m.get('analysis') or {}).get('metrics') or {})
                records.append({'schema_version':1,'experiment_id':'frozen_'+entry['case_id']+'_'+m['id'],
                    'run_id':None,'name':entry['case_id']+' / '+m['name'],'type':'frozen' if m.get('frozen_metrics') else 'inference','algorithm':m['id'],'method_id':m['id'],
                    'case_ids':[entry['case_id']],'status':'frozen' if m.get('frozen_metrics') else 'historical','source_kind':'frozen_reference' if m.get('frozen_metrics') else 'imported_analysis',
                    'created_at':None,'started_at':None,'ended_at':None,'code_version':None,'device':None,
                    'hyperparameters':{},'reference_fields':m.get('frozen_metrics'),'metrics':{**reference_metrics,'pred_volume_ml':m.get('computed_pred_volume_ml') if m.get('computed_pred_volume_ml') is not None else reference_metrics.get('pred_volume_ml'),
                    'fp_volume_ml':(m.get('analysis') or {}).get('volume',{}).get('fp_ml'),'fn_volume_ml':(m.get('analysis') or {}).get('volume',{}).get('fn_ml')},
                    'gt_available':case['has_gt'],'input_hashes':{k:(case.get(k+'_source') or {}).get('sha256') for k in ['ct','gt']},
                    'definitions':inference_definitions(),
                    'manifest':'/'+entry['manifest'],'sources':[{'path':str(manifest_path),'sha256':sha(manifest_path)}]})
    return records


def export_csv(record):
    stream=io.StringIO(newline='')
    fields=['experiment_id','run_id','type','epoch','stage','timestamp','metric_name','metric_value','unit','aggregation','definition','source','source_sha256','split_id','case_ids','checkpoint_reference','metadata_json']
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for epoch in record.get('epochs',[]) or [{'epoch':None,'stage':None,'metrics':record.get('metrics',{}),'sources':{}}]:
        for metric,value in epoch['metrics'].items():
            d=record.get('definitions',{}).get(metric,record.get('definitions',{}).get('overlap',{}))
            source=epoch.get('sources',{}).get(metric) or (record.get('sources') or [{}])[0]
            row=dict(experiment_id=record['experiment_id'],run_id=record.get('run_id'),type=record['type'],epoch=epoch['epoch'],stage=epoch.get('stage'),timestamp=epoch.get('timestamp'),metric_name=metric,metric_value=value,
                unit=d.get('unit'),aggregation=d.get('aggregation'),definition=d.get('definition'),source=source.get('path'),source_sha256=source.get('sha256'),split_id=record.get('split_id'),
                case_ids=json.dumps(record.get('case_ids')),checkpoint_reference=json.dumps(epoch.get('checkpoint')),
                metadata_json=json.dumps({k:v for k,v in record.items() if k!='epochs'},ensure_ascii=False))
            # Prevent formula execution when a user opens an untrusted log in Excel.
            writer.writerow({k:csv_safe(v) for k,v in row.items()})
    return stream.getvalue()
