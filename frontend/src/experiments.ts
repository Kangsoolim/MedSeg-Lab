import type {CaseData} from './types';
import {jsonFile,validateCase} from './data';
export const EXP_API='http://127.0.0.1:8008/api/v1';
export type Source={path:string;sha256?:string;line?:number;definition?:string};
export type Definition={definition:string;unit:string;aggregation:string};
export type Checkpoint=Source&{epoch:number;schema_version?:number;boundary?:string};
export type Epoch={epoch:number;stage:string;timestamp?:string|null;metrics:Record<string,number|null>;sources:Record<string,Source>;flags:string[];checkpoint?:Checkpoint|null;patients?:Record<string,string|number>[];predictions?:Array<Source&{case_id:string}>};
export type Experiment={schema_version:number;experiment_id:string;run_id:string|null;name:string;type:'training'|'inference'|'traditional'|'frozen';algorithm:string;source_kind:string;status:string;created_at?:string|null;started_at?:string|null;ended_at?:string|null;dataset?:string|null;split_id?:string|null;case_ids?:string[]|null;code_version?:unknown;device?:string|null;hyperparameters:Record<string,unknown>;definitions:Record<string,Definition>;epochs?:Epoch[];sources:Source[];checkpoints?:Checkpoint[];lineage?:Array<{parent:string;child:string;through_epoch:number;relation:string}>;early_stopping?:{monitor:string;mode:string;patience:number;min_delta:number;best_epoch:number;bad_epochs:number;patience_reference:number;stop_reason:string}|null;warnings?:string[];metrics?:Record<string,number|null>;gt_available?:boolean;manifest?:string;method_id?:string;source_artifact?:string;checkpoint_sha256?:string;checkpoint_epoch?:number;training_experiment_id?:string;input_hashes?:Record<string,string|null>};
export type Catalog={schema_version:number;experiments:Experiment[];inventory:Source[];lineage:Array<{parent:string;child:string;through_epoch:number;relation:string}>};
export function bestEpoch(run:Experiment,metric='val_mean_dice'){
 const points=(run.epochs??[]).filter(e=>e.metrics[metric]!=null);
 const lower=metric.includes('loss');return points.reduce<Epoch|undefined>((best,e)=>!best||((e.metrics[metric] as number)-(best.metrics[metric] as number))*(lower?-1:1)>0?e:best,undefined);
}
export function comparable(runs:Experiment[],metric:string):boolean{
 if(runs.length<2)return false;
 if(runs.every(r=>r.type==='training'))return !!runs[0].split_id&&!!runs[0].case_ids?.length&&runs.every(r=>r.split_id===runs[0].split_id&&JSON.stringify([...r.case_ids??[]].sort())===JSON.stringify([...runs[0].case_ids??[]].sort())&&!!r.definitions[metric]&&['definition','unit','aggregation'].every(k=>r.definitions[metric][k as keyof Definition]===runs[0].definitions[metric]?.[k as keyof Definition]));
 if(runs.some(r=>r.type==='training'))return false;
 return !!runs[0].input_hashes?.ct&&!!runs[0].input_hashes?.gt&&runs.every(r=>r.gt_available&&r.input_hashes?.ct===runs[0].input_hashes?.ct&&r.input_hashes?.gt===runs[0].input_hashes?.gt&&JSON.stringify(r.definitions.overlap)===JSON.stringify(runs[0].definitions.overlap));
}
export function saveFile(name:string,text:string,type='application/json'){
 const url=URL.createObjectURL(new Blob([text],{type}));const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export function experimentCSV(runs:Experiment[]){
 const columns=['experiment_id','run_id','type','epoch','stage','timestamp','metric_name','metric_value','unit','aggregation','definition','source','source_sha256','split_id','case_ids','checkpoint_reference','metadata_json'];
 const quote=(value:unknown)=>{let s=value==null?'':typeof value==='object'?JSON.stringify(value):String(value);if(typeof value==='string'&&(/^[\s\uFEFF]*[=+@-]/.test(s)||/^[\t\r\n]/.test(s)))s="'"+s;return '"'+s.replaceAll('"','""')+'"'};
 const rows:unknown[][]=[columns];
 for(const run of runs){const {epochs,...metadata}=run;for(const e of epochs??[{epoch:null,stage:null,timestamp:null,metrics:run.metrics??{},sources:{} as Record<string,Source>,checkpoint:null}])for(const [metric,value] of Object.entries(e.metrics)){
 const d=run.definitions[metric]??run.definitions.overlap;const s=e.sources[metric]??run.sources[0];
 rows.push([run.experiment_id,run.run_id,run.type,e.epoch,e.stage,e.timestamp,metric,value,d?.unit,d?.aggregation,d?.definition,s?.path,s?.sha256,run.split_id,run.case_ids,e.checkpoint,metadata]);
 }}return rows.map(row=>row.map(quote).join(',')).join('\r\n');
}
export async function openExperiments(runs:Experiment[]):Promise<CaseData>{
 if(!runs.length||runs.some(r=>!r.manifest))throw new Error('Only completed runs can be opened');
 const packages=await Promise.all(runs.map(r=>jsonFile<CaseData>(r.manifest!).then(validateCase)));
 const first=packages[0];
 if(packages.some(c=>JSON.stringify(c.ct_source)!==JSON.stringify(first.ct_source)||JSON.stringify(c.gt_source)!==JSON.stringify(first.gt_source)))throw new Error('Compare runs with the same CT and GT sources');
 const selected=packages.flatMap((c,i)=>c.methods.filter(m=>runs[i].method_id?m.id===runs[i].method_id:m.id.startsWith('run_')).map(m=>({...m,name:runs[i].name,asset_base:c.asset_base,mesh_base:c.mesh_base})));
 if(!selected.length)throw new Error('Selected method is unavailable / 选中方法不可用');
 if(new Set(selected.map(m=>m.id)).size!==selected.length)throw new Error('Duplicate methods; open individual results / 重复方法，请单独打开结果');
 // Put the explicitly selected result last: the existing workspace focuses it.
 const methods=packages.length===1?[...first.methods.filter(m=>!selected.some(s=>s.id===m.id)),...selected]:selected;
 return {...first,methods,display_modes:['ct',...(first.has_gt?['gt']:[]),...methods.map(m=>m.id),...(first.has_gt?methods.map(m=>m.id+'_error'):[])]};
}

export type SavedComparison={schema_version:1;selected:string[];primary:string;metric:string;epoch:number};
export const COMPARISON_KEY='medseg.comparison.v1';
export function loadComparison():SavedComparison|null{
 try{const v=JSON.parse(localStorage.getItem(COMPARISON_KEY)??'null');return v?.schema_version===1&&Array.isArray(v.selected)&&v.selected.length<=4&&v.selected.every((id:unknown)=>typeof id==='string')&&typeof v.primary==='string'&&typeof v.metric==='string'&&Number.isInteger(v.epoch)?v:null}catch{return null}
}
