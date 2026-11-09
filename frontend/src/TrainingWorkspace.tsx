import {useCallback,useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import TrainingChart from './TrainingChart';
import {EXP_API,bestEpoch} from './experiments';
import type {Experiment,Epoch} from './experiments';
import type {CaseData} from './types';

type Config={adapter:string;dataset:'course'|'registered';train_ids:string[];val_ids:string[];patient_ids:Record<string,string>;epochs:number;batch_size:number;learning_rate:number;seed:number;patience:number;min_delta:number;amp:boolean;device:'cpu'|'cuda';checkpoint_policy:'last_best'|'every_epoch';preview_every:number;engineering_smoke:boolean;max_train_batches:number|null};
type Entry={case_id:string;dataset:string;role:string;shape:number[]|null;spacing:number[]|null;orientation:string[]|null;gt_available:boolean;error:string|null};
type Catalog={cases:Entry[];counts:{train:number;val:number};split_id:string;model:Record<string,unknown>};
type Run={run_id:string;status:string;config:Config;parent_run_id:string|null;checkpoints:{name:string;bytes:number}[]};
type Event={sequence:number;timestamp:string;event_type:string;epoch:number;step:number|null;status?:string;message?:string;train_loss?:number};
type LiveRun=Experiment&{latest_batch?:{epoch:number;batch_attempt:number;step:number;train_loss:number;elapsed_seconds:number}|null;stop_reason?:string};
type PreviewEpoch=Epoch&{preview_available?:boolean};
type Preflight={preflight_id:string;train_count:number;val_count:number;estimated_output_bytes:number;estimated_ram_bytes:number;available_disk_bytes:number;gpu:string|null;checks:string[];warnings:string[];resume_epoch:number|null};
const DEFAULTS:Config={adapter:'monai-resunet-v1',dataset:'registered',train_ids:[],val_ids:[],patient_ids:{},epochs:50,batch_size:4,learning_rate:.001,seed:42,patience:10,min_delta:.0001,amp:false,device:'cpu',checkpoint_policy:'last_best',preview_every:1,engineering_smoke:false,max_train_batches:null};
const ACTIVE=['queued','preparing','running','stopping'];
const KEY='medseg.training.active.v1';
const selectedRun=()=>{try{return localStorage.getItem(KEY)??''}catch{return ''}};

export default function TrainingWorkspace({onOpen}:{onOpen:(data:CaseData)=>void}){
 const {t,i18n}=useTranslation();
 const [config,setConfig]=useState<Config>(DEFAULTS),[catalog,setCatalog]=useState<Catalog|null>(null),[runs,setRuns]=useState<Run[]>([]),[rid,setRid]=useState(selectedRun);
 const [canTrain,setCanTrain]=useState(false);
 const [run,setRun]=useState<LiveRun|null>(null),[events,setEvents]=useState<Event[]>([]),[online,setOnline]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [preflight,setPreflight]=useState<Preflight|null>(null),[parent,setParent]=useState<string|null>(null),[checkpoint,setCheckpoint]=useState('last.pt'),[metric,setMetric]=useState('train_loss'),[epoch,setEpoch]=useState<Epoch|null>(null);
 const cursor=useRef(0),token=useRef(''),requestId=useRef('');
 const bilingual=(value:string)=>{const parts=value.split(' / ');return i18n.resolvedLanguage==='zh'?(parts[1]??t(value)):parts[0]};
 const api=useCallback(async(path:string,body?:unknown)=>{
  const response=await fetch(EXP_API+'/training'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-MedSeg-Token':token.current},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(120000)});
  const value=await response.json();if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));return value;
 },[]);
 useEffect(()=>{let alive=true;let timer:ReturnType<typeof setTimeout>;let loaded=false;
  const poll=async()=>{try{
   const health=await fetch(EXP_API+'/health',{signal:AbortSignal.timeout(4000)});if(!health.ok)throw new Error('offline');const healthValue=await health.json();token.current=healthValue.token;setCanTrain(!!healthValue.capabilities?.training);
   const listPromise=api('/runs');const catalogPromise=loaded?Promise.resolve(null):api('/catalog');
   const [list,cat]=await Promise.all([listPromise,catalogPromise]);if(!alive)return;
   setOnline(true);setRuns(list);if(cat){setCatalog(cat);loaded=true}
   if(rid){const [projection,batch]=await Promise.all([api('/runs/'+rid),api(`/runs/${rid}/events?after=${cursor.current}`)]);if(!alive)return;
    setRun(projection);setEvents(old=>{const map=new Map(old.map(e=>[e.sequence,e]));for(const event of batch.events)map.set(event.sequence,event);return [...map.values()].sort((a,b)=>a.sequence-b.sequence).slice(-500)});cursor.current=batch.next_sequence;
   }
  }catch{if(alive)setOnline(false)}finally{if(alive)timer=setTimeout(poll,1500)}};
  void poll();return()=>{alive=false;clearTimeout(timer)};
 },[api,rid]);
 useEffect(()=>{cursor.current=0;setEvents([]);setRun(null);setEpoch(null);try{localStorage.setItem(KEY,rid)}catch{/* persistent selection optional */}},[rid]);
 const update=(patch:Partial<Config>)=>{setConfig(c=>({...c,...patch}));setPreflight(null);setError('')};
 const action=async(fn:()=>Promise<void>)=>{if(busy)return;setBusy(true);setError('');try{await fn()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}};
 const check=()=>action(async()=>{setPreflight(null);const value=await api('/preflight',{config,resume_run_id:parent,checkpoint});setPreflight(value);requestId.current=crypto.randomUUID().replaceAll('-','')});
 const start=()=>action(async()=>{if(!preflight)return;const value=await api('/runs',{config,preflight_id:preflight.preflight_id,request_id:requestId.current,confirm:'START REAL TRAINING',resume_run_id:parent,checkpoint});setRid(value.run_id);setPreflight(null);setParent(null)});
 const selected=runs.find(r=>r.run_id===rid);
 const active=!!selected&&ACTIVE.includes(selected.status);
 const last=run?.epochs?.at(-1),best=run?bestEpoch(run):undefined,batch=run?.latest_batch;
 const display=(value:unknown)=>value==null?t('Pending'):String(value);
 const current=(epoch?run?.epochs?.find(e=>e.epoch===epoch.epoch):last) as PreviewEpoch|undefined;
 const resume=()=>{if(!selected)return;setConfig({...selected.config,epochs:Math.min(selected.config.engineering_smoke?3:60,Math.max(selected.config.epochs+1,(last?.epoch??0)+1))});setParent(rid);setPreflight(null);setError('')};
 const choose=(id:string,role:'train_ids'|'val_ids',checked:boolean)=>update({[role]:checked?[...config[role],id]:config[role].filter(v=>v!==id)});
 const cases=catalog?.cases.filter(c=>c.dataset===config.dataset)??[];
 return <section className="research-workspace training-workspace" data-testid="training-workspace">
  <div className="research-toolbar"><span className={online?'connection online':'connection offline'}>{t(online?'Local backend connected':'Training backend unavailable')}</span><span>{t('Real training · local data · epoch-boundary recovery')}</span></div>
  {!online&&<p className="notice">{t('Start the local Python backend to train. Static analysis remains available.')}</p>}
  <div className="training-layout">
  <section className="research-card training-configuration"><h2>{t('Training configuration')}</h2>
   <label>{t('Dataset')}<select aria-label={t('Dataset')} value={config.dataset} onChange={e=>update({dataset:e.target.value as Config['dataset'],train_ids:[],val_ids:[]})}><option value="course">{t('Verified course split')}</option><option value="registered">{t('Registered local cases')}</option></select></label>
   <p className="small">{t('Case IDs can be checked. Independent patient identity cannot be proven from available metadata.')}</p>
   <details><summary>{t('Select train and validation cases')} · {catalog?.counts.train??'—'} / {catalog?.counts.val??'—'}</summary>
    <p>{t('Empty course selections use the complete frozen partition. Imported data requires explicit selections. Test cases are excluded.')}</p>
    <div className="training-cases table-scroll"><table><thead><tr>{['Case','Patient identity (optional)','Train','Validation','Dimensions','Spacing (mm)','Orientation','GT available'].map(k=><th key={k}>{t(k)}</th>)}</tr></thead><tbody>{cases.map(c=><tr key={c.case_id}><td>{c.case_id}</td><td>{config.dataset==='registered'?<input aria-label={`${t('Patient identity (optional)')} ${c.case_id}`} value={config.patient_ids?.[c.case_id]??''} onChange={e=>{const patient_ids={...config.patient_ids};if(e.target.value.trim())patient_ids[c.case_id]=e.target.value;else delete patient_ids[c.case_id];update({patient_ids})}}/>:c.case_id}</td><td><input type="checkbox" aria-label={`${t('Train')} ${c.case_id}`} disabled={!c.gt_available||c.role==='val'||config.val_ids.includes(c.case_id)} checked={config.train_ids.includes(c.case_id)} onChange={e=>choose(c.case_id,'train_ids',e.target.checked)}/></td><td><input type="checkbox" aria-label={`${t('Validation')} ${c.case_id}`} disabled={!c.gt_available||c.role==='train'||config.train_ids.includes(c.case_id)} checked={config.val_ids.includes(c.case_id)} onChange={e=>choose(c.case_id,'val_ids',e.target.checked)}/></td><td>{c.shape?.join(' × ')??'—'}</td><td>{c.spacing?.map(v=>v.toFixed(2)).join(' × ')??'—'}</td><td>{c.orientation?.join('')??'—'}</td><td>{t(c.gt_available?'Available':'Unavailable')}</td></tr>)}</tbody></table></div>
   </details>
   <details><summary>MONAI 2D Residual U-Net · v1</summary><dl className="training-model"><dt>{t('Network channels')}</dt><dd>1 → (16, 32, 64, 128, 256) → 1</dd><dt>{t('Residual units')}</dt><dd>2 · 256 × 256</dd><dt>{t('Loss function')}</dt><dd>0.5 DiceLoss(sigmoid=True) + 0.5 BCEWithLogitsLoss</dd><dt>{t('Optimizer')}</dt><dd>Adam · {t('Global batch shuffle')} · PCG64 / 600042</dd><dt>{t('Preprocessing')}</dt><dd>closest RAS · HU [-57,164] → [0,1] · {t('CT linear / GT nearest')}</dd><dt>{t('Split ID')}</dt><dd>{catalog?.split_id??'—'}</dd><dt>{t('Training adapter')}</dt><dd>monai-resunet-v1</dd></dl></details>
   <div className="training-form">{([
    ['epochs','Total Epochs',1,config.engineering_smoke?3:60,1],['batch_size','Batch Size',1,4,1],['learning_rate','Learning Rate',.0000001,.01,.0001],['seed','Random Seed',0,2147483647,1],['patience','Early Stopping Patience',1,60,1],['min_delta','Min Delta',0,1,.0001],['preview_every','Preview every N Epochs',1,60,1],
   ] as const).map(([key,label,min,max,step])=><label key={key}>{t(label)}<input aria-label={t(label)} type="number" min={min} max={max} step={step} value={config[key]} onChange={e=>update({[key]:Number(e.target.value)})}/></label>)}
   <label>{t('Device')}<select aria-label={t('Device')} value={config.device} onChange={e=>update({device:e.target.value as Config['device'],amp:e.target.value==='cuda'})}><option value="cpu">CPU</option><option value="cuda">CUDA</option></select></label>
   <label>{t('Checkpoint policy')}<select aria-label={t('Checkpoint policy')} value={config.checkpoint_policy} onChange={e=>update({checkpoint_policy:e.target.value as Config['checkpoint_policy']})}><option value="last_best">{t('Last + best')}</option><option value="every_epoch">{t('Every Epoch + last + best')}</option></select></label>
   </div>
   <label className="toggle"><input type="checkbox" aria-label="AMP" disabled={config.device!=='cuda'} checked={config.amp} onChange={e=>update({amp:e.target.checked})}/>AMP (CUDA)</label>
   <label className="toggle"><input type="checkbox" aria-label={t('Engineering Smoke Test')} checked={config.engineering_smoke} onChange={e=>update({engineering_smoke:e.target.checked,epochs:e.target.checked?1:50,max_train_batches:e.target.checked?1:null,train_ids:e.target.checked?cases.filter(c=>c.role==='train').slice(0,1).map(c=>c.case_id):[],val_ids:e.target.checked?cases.filter(c=>c.role==='val').slice(0,1).map(c=>c.case_id):[]})}/>{t('Engineering Smoke Test')}</label>
   {config.engineering_smoke&&<><p className="notice">{t('At most 3 epochs, 1–8 batches per epoch. Subset metrics are not formal course results.')}</p><label>{t('Maximum training batches')}<input aria-label={t('Maximum training batches')} type="number" min="1" max="8" value={config.max_train_batches??1} onChange={e=>update({max_train_batches:Number(e.target.value)})}/></label></>}
   {parent&&<div className="notice"><strong>{t('Resumed Training Run')}</strong><p>{parent} · {t('Epoch-boundary recovery only')}</p><label>{t('Resume checkpoint')}<select aria-label={t('Resume checkpoint')} value={checkpoint} onChange={e=>{setCheckpoint(e.target.value);setPreflight(null)}}><option>last.pt</option><option>best.pt</option></select></label><button onClick={()=>{setParent(null);setPreflight(null)}}>{t('Create a new independent run')}</button></div>}
   <button disabled={!canTrain||!online||busy||runs.some(r=>ACTIVE.includes(r.status))} onClick={()=>void check()}>{t(busy?'Working…':'Run preflight')}</button>
   {preflight&&<div className="training-preflight" data-testid="training-preflight"><h3>{t('Preflight passed')}</h3><p>{t('Train')}: {preflight.train_count} · {t('Validation')}: {preflight.val_count} · {preflight.gpu??'CPU'}</p><p>{t('Estimated output')}: {(preflight.estimated_output_bytes/1024**2).toFixed(0)} MiB · {t('Estimated RAM')}: {(preflight.estimated_ram_bytes/1024**3).toFixed(2)} GiB</p><p>{t('Checked data, geometry, GT, code, device, disk, output and compute conflicts.')}</p>{preflight.warnings.map(w=><p className="notice" key={w}>{bilingual(w)}</p>)}<p>{t('This action starts actual forward, backward and optimizer updates.')}</p><button className="primary" disabled={busy} onClick={()=>void start()}>{t('Confirm and start real training')}</button></div>}
  </section>
  <section className="research-card training-monitor"><h2>{t('Training monitor')}</h2>
   <label>{t('Training run history')}<select aria-label={t('Training run history')} value={rid} onChange={e=>setRid(e.target.value)}><option value="">{t('Select a training run')}</option>{runs.map(r=><option key={r.run_id} value={r.run_id}>{r.config.engineering_smoke?t('Engineering Smoke Test'):t(r.parent_run_id?'Resumed Training Run':'Live Training Run')} · {r.run_id} · {t(r.status)}</option>)}</select></label>
   {run?<><p className="run-identity">{t(run.source_kind)} · <code>{run.run_id}</code></p><div className="training-metrics" data-testid="live-metrics">{[
     [t('Status'),t(run.status)],[t('Current Epoch / Total'),`${batch?.epoch??last?.epoch??0} / ${run.hyperparameters.epochs}`],[t('Training Loss'),batch?.train_loss??last?.metrics.train_loss],
     [t('Validation Dice'),last?.metrics.val_mean_dice],[t('Learning Rate'),last?.metrics.learning_rate??run.hyperparameters.learning_rate],[t('Completed batch attempts'),batch?.batch_attempt??last?.metrics.batch_attempts],
     [t('Actual optimizer updates'),batch?.step??last?.metrics.global_step],[t('Observed elapsed (s)'),active?batch?.elapsed_seconds??last?.metrics.elapsed_seconds:last?.metrics.elapsed_seconds],[t('Best Epoch'),best?.epoch],
     [t('Dice / BCE components'),t('Not Recorded')],
   ].map(([key,value])=><div key={String(key)}><span>{String(key)}</span><strong>{display(typeof value==='number'?Number(value.toPrecision(7)):value)}</strong></div>)}</div>
   <p>{t('Latest completed validation Epoch')}: {display(last?.epoch)}</p>{last?.flags.length?<p className="notice">{t('Recorded metric warning')}: {last.flags.map(f=>t(f)).join(' · ')}</p>:null}
   <div className="research-toolbar"><button disabled={!active||selected?.status==='stopping'||busy} onClick={()=>void action(async()=>{await api(`/runs/${rid}/stop`,{});setRuns(await api('/runs'))})}>{t('Graceful stop')}</button><button disabled={!active||selected?.status!=='stopping'||busy} onClick={()=>{if(window.confirm(t('Force termination may lose the current epoch. Continue?')))void action(async()=>{await api(`/runs/${rid}/force?confirm=${rid}`,{});setRuns(await api('/runs'))})}}>{t('Force terminate')}</button><button disabled={active||!selected?.checkpoints.length||busy} onClick={resume}>{t('Configure resume')}</button></div>
   {selected?.status==='stopping'&&<p className="notice">{t('Stopping after the current epoch and validation. Force termination becomes available after 15 seconds.')}</p>}
   {run.stop_reason&&<p>{t('Stop reason')}: {t(run.stop_reason)}</p>}
   <label>{t('Metric')}<select aria-label={t('Live metric')} value={metric} onChange={e=>setMetric(e.target.value)}>{['train_loss','val_mean_dice','learning_rate','amp_skipped_steps'].map(m=><option key={m} value={m}>{t(m)}</option>)}</select></label>
   <TrainingChart runs={[run]} metric={metric} onEpoch={(_,e)=>setEpoch(e)}/>
   <p>{t('Early stopping')}: {run.early_stopping?.bad_epochs??0} / {run.early_stopping?.patience} · {t('Best Epoch')}: {run.early_stopping?.best_epoch||t('Pending')}</p>
   <details><summary>{t('Epoch details')} · {current?.epoch??t('Pending')}</summary><pre>{JSON.stringify(current??{},null,2)}</pre></details>
   <h3>{t('Validation Preview')}</h3><p>{t('Full native 3D validation case; the 2D viewer shows synchronized slices and TP/FP/FN.')}</p>
   {current?.preview_available?<div className="research-toolbar">{run.case_ids?.map(cid=><button key={cid} disabled={busy} onClick={()=>void action(async()=>{const data=await api(`/runs/${rid}/preview/${current.epoch}/${cid}`,{});onOpen(data)})}>{t('Open validation preview')} · E{current.epoch} · {cid}</button>)}</div>:<p>{t('No preview generated for this Epoch')}</p>}
   <h3>{t('Checkpoints')}</h3><p>{t('Epoch-boundary recovery only')}</p><ul>{selected?.checkpoints.map(c=><li key={c.name}>{c.name} · {(c.bytes/1024**2).toFixed(1)} MiB</li>)}</ul>
   <div className="research-toolbar"><a href={`${EXP_API}/training/runs/${rid}/logs`} download>{t('Export training logs')}</a>{!active&&<a href={`${EXP_API}/training/runs/${rid}/export`} download>{t('Export run and checkpoints')}</a>}<a href={`${EXP_API}/experiments/${rid}/export`} download>{t('Export experiment (JSON)')}</a></div>
   <details open><summary>{t('Real training events')} · {events.length} / {cursor.current} (latest 500)</summary><div className="training-events" role="log" aria-label={t('Training logs')}>{events.map(e=><div key={e.sequence} data-sequence={e.sequence}><span>#{e.sequence} · {e.timestamp.slice(11,19)} · E{e.epoch}</span> <strong>{t(e.event_type)}</strong> {e.status?t(e.status):''} {e.message?bilingual(e.message):''} {e.train_loss!=null?`${t('Training Loss')}: ${e.train_loss}`:''}</div>)}</div></details>
   </>:<p>{t('No live run selected. Creating a configuration never starts training.')}</p>}
  </section></div>{error&&<p role="alert">{bilingual(error)}</p>}
 </section>;
}
