import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Viewer} from './Viewer';
import type {Transform} from './Viewer';
import type {CaseData,Spatial,Vec3} from './types';
import {fmt} from './types';
import {jsonFile,validateCase} from './data';
import {translateMessage} from './i18n';

const API='http://127.0.0.1:8008/api/v1';
type InputCase={case_id:string;ct:string;gt:string|null;spatial:Spatial;manifest:string|null;source_kind:string;reference_selection?:{seed:Vec3;roi:number[]}};
type Run={run_id:string;case_id:string;algorithm:string;status:string;created_at:string;started_at:string|null;ended_at:string|null;manifest?:string;logs:string;parameters:Record<string,unknown>;error?:{message:string;traceback?:string};progress?:{stage:string;slices_done?:number;slices_total?:number};result?:{device:string;checkpoint_sha256?:string;preprocessing_version:string;volume_ml:number;foreground_voxels:number;algorithm_seconds:number;output_path:string;gt_available:boolean;postprocess?:{status:string;warning?:string}}};

export default function AlgorithmWorkbench({initial,onOpen}:{initial:CaseData;onOpen:(data:CaseData)=>void}){
 const {t,i18n}=useTranslation();
 const [available,setAvailable]=useState<Record<string,boolean>>({});
 const [online,setOnline]=useState(false),[cases,setCases]=useState<InputCase[]>([]),[runs,setRuns]=useState<Run[]>([]);
 const [selected,setSelected]=useState(initial.case_id),[panel,setPanel]=useState('traditional_v2');
 const [view,setView]=useState(initial),[k,setK]=useState(initial.default_slice);
 const [pickLayout,setPickLayout]=useState(1);
 const ctView=useMemo(()=>({...view,display_modes:['ct']}),[view]);
 const [seed,setSeed]=useState<Vec3|null>(null),[roi,setRoi]=useState<number[]|null>(null),[corner,setCorner]=useState<Vec3|null>(null);
 const [pick,setPick]=useState('pan'),[transform,setTransform]=useState<Transform>({scale:1,x:0,y:0});
 const [iterations,setIterations]=useState(2),[multiplier,setMultiplier]=useState(2),[radius,setRadius]=useState(1),[opening,setOpening]=useState(1),[device,setDevice]=useState('auto');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[focused,setFocused]=useState<string|null>(null),[compare,setCompare]=useState<string[]>([]);
 const [importId,setImportId]=useState(''),[ct,setCt]=useState(''),[gt,setGt]=useState('');
 const token=useRef(''),sending=useRef(false);
 const call=useCallback(async<T,>(path:string,options:RequestInit={}):Promise<T>=>{
   const response=await fetch(API+path,{...options,signal:AbortSignal.timeout(options.method==='POST'&&['/jobs','/cases'].includes(path)?120000:15000),headers:{'Content-Type':'application/json','X-MedSeg-Token':token.current,...options.headers}});
   if(!response.ok){const e=await response.json();throw new Error(typeof e.detail==='string'?e.detail:JSON.stringify(e.detail))}
   return response.json();
 },[]);
 const refresh=useCallback(async()=>{
   const h=await call<{token:string;capabilities:Record<string,boolean>}>('/health');token.current=h.token;setAvailable(h.capabilities);
   const [c,r]=await Promise.all([call<InputCase[]>('/cases'),call<Run[]>('/runs')]);
   setCases(c);setRuns(r);setOnline(true);
 },[call]);
 useEffect(()=>{let ended=false;let timer:ReturnType<typeof setTimeout>;
   const poll=async()=>{try{await refresh()}catch{if(!ended)setOnline(false)}if(!ended)timer=setTimeout(poll,1500)};
   void poll();return()=>{ended=true;clearTimeout(timer)};
 },[refresh]);
 const entry=cases.find(c=>c.case_id===selected);
 const active=runs.find(r=>r.status==='running'||r.status==='queued');
 const current=runs.find(r=>r.run_id===focused)??active;
 // Keep observing a recovered task after it becomes terminal. Otherwise a
 // refresh leaves no focused ID and completion/cancellation removes its panel.
 useEffect(()=>{if(active&&!focused)setFocused(active.run_id)},[active?.run_id,focused]);
 useEffect(()=>{
   if(!entry)return;
   const controller=new AbortController();
   setSeed(null);setRoi(null);setCorner(null);setPick('pan');setTransform({scale:1,x:0,y:0});
   if(entry.manifest){jsonFile<CaseData>(entry.manifest,controller.signal).then(c=>{setView(c);setK(c.default_slice)}).catch(e=>{if(e.name!=='AbortError')setError(e.message)})}
   else {setView({...initial,case_id:entry.case_id,title:entry.case_id,spatial:entry.spatial,has_gt:!!entry.gt,methods:[],display_modes:['ct'],default_slice:Math.floor(entry.spatial.shape[2]/2),targets:[],gt_mesh:null,asset_base:`${API}/inputs/${entry.case_id}`,mesh_base:'',result_status:'exploratory_input'});setK(Math.floor(entry.spatial.shape[2]/2))}
   return()=>controller.abort();
   // Initial case is only a structural template for a CT-only imported preview.
   // eslint-disable-next-line react-hooks/exhaustive-deps
 },[entry?.case_id]);
 const action=async(fn:()=>Promise<void>)=>{if(sending.current)return;sending.current=true;setBusy(true);setError('');try{await fn()}catch(e){setError(String((e as Error).message))}finally{sending.current=false;setBusy(false)}};
 const start=()=>action(async()=>{
   if(panel==='traditional_v2'&&(!seed||!roi))throw new Error(t('Choose a seed and ROI first'));
   const r=await call<Run>('/jobs',{method:'POST',body:JSON.stringify({case_id:selected,algorithm:panel,parameters:{seed,roi,iterations,multiplier,radius,opening_mm:opening,device}})});
   setFocused(r.run_id);await refresh();
 });
 const point=(p:Vec3)=>{
   if(pick==='seed'){setSeed(p);setPick('pan')}
   else if(pick==='roi'){
     if(!corner)setCorner(p);
     else{setRoi([Math.min(p[0],corner[0]),Math.max(p[0],corner[0])+1,Math.min(p[1],corner[1]),Math.max(p[1],corner[1])+1,Math.min(p[2],corner[2]),Math.max(p[2],corner[2])+1]);setCorner(null);setPick('pan')}
   }
 };
 const world=seed?view.spatial.affine.slice(0,3).map(row=>row[0]*seed[0]+row[1]*seed[1]+row[2]*seed[2]+row[3]):null;
 const open=async(ids:string[])=>action(async()=>{
   const chosen=ids.map(id=>runs.find(r=>r.run_id===id)!);
   if(chosen.some(r=>r.status!=='completed'||!r.manifest))throw new Error(t('Only completed runs can be opened'));
   const packages=await Promise.all(chosen.map(r=>jsonFile<CaseData>(r.manifest!).then(validateCase)));
   const first=packages[0];
   if(packages.some(c=>JSON.stringify(c.ct_source)!==JSON.stringify(first.ct_source)||c.has_gt!==first.has_gt||JSON.stringify(c.gt_source)!==JSON.stringify(first.gt_source)))throw new Error(t('Compare runs with the same CT and GT sources'));
   const methods=packages.flatMap(c=>c.methods.filter(m=>m.id.startsWith('run_')).map(m=>({...m,name:`Interactive Experimental Run · ${chosen[packages.indexOf(c)].algorithm} · ${c.run_id?.slice(0,8)}`,asset_base:c.asset_base,mesh_base:c.mesh_base})));
   const result={...first,methods:[...first.methods.filter(m=>!m.id.startsWith('run_')),...methods]};
   result.display_modes=['ct',...(result.has_gt?['gt']:[]),...result.methods.map(m=>m.id),...(result.has_gt?result.methods.map(m=>m.id+'_error'):[])];
   onOpen(result);
 });
 return <section className="algorithm-workbench" aria-label={t('Algorithm Workbench')}>
   <div className="algorithm-status" role="status"><strong>{t(online?'Local computation service connected':'Local computation service disconnected')}</strong><span>{t('Interactive Experimental Run')}</span></div>
   <div className="segmented algorithm-tabs">{[['traditional_v2','Traditional V2'],['unet_e17','U-Net Inference'],['history','Run History']].map(([id,label])=><button key={id} aria-pressed={panel===id} onClick={()=>setPanel(id)}>{t(label)}</button>)}</div>
   <p className="small">{t('Experimental outputs stay in MedSeg-Lab/runs. Frozen course results remain separate. Internal dataset runs are exploratory reproductions.')}</p>
   {error&&<div role="alert" className="error">{t('Request failed')}: {translateMessage(error)}</div>}
   {panel!=='history'&&<>
    <label className="field-label">{t('Algorithm input')}<select aria-label={t('Algorithm input')} value={selected} disabled={!online||busy} onChange={e=>{setSelected(e.target.value);setError('')}}>{cases.length?cases.map(c=><option key={c.case_id} value={c.case_id}>{c.case_id} · {t(c.gt?'GT available':'No GT')}</option>):<option>{initial.case_id}</option>}</select></label>
    <div className="algorithm-grid"><div className="algorithm-image"><div className="viewer-toolbar"><button aria-pressed={pick==='pan'} onClick={()=>setPick('pan')}>{t('Pan / zoom')}</button>{panel==='traditional_v2'&&<><button aria-pressed={pick==='seed'} onClick={()=>{setPick('seed');setCorner(null)}}>{t('Set seed')}</button><button aria-pressed={pick==='roi'} onClick={()=>{setPick('roi');setCorner(null)}}>{t('Set ROI corners')}</button></>}<button onClick={()=>setTransform({scale:1,x:0,y:0})}>{t('Reset view')}</button></div>
    <div className="segmented" aria-label={t('View layout')}>{[1,2,4].map(n=><button key={n} aria-pressed={pickLayout===n} onClick={()=>setPickLayout(n)}>{t(n===1?'Single':n===2?'Dual':'Quad')}</button>)}</div>
    <div className="algorithm-ct"><div className={`algorithm-pick-grid pick-layout-${pickLayout}`}>{Array.from({length:pickLayout},(_,i)=><Viewer key={i} data={ctView} k={Math.min(k,view.spatial.shape[2]-1)} mode="ct" onMode={()=>{}} index={10+i} onSlice={d=>setK(v=>Math.max(0,Math.min(view.spatial.shape[2]-1,v+d)))} opacity={0} contour={false} transform={transform} onTransform={setTransform} selection={null} onPick={pick!=='pan'?point:undefined} seed={seed} roi={roi}/>)}</div></div>
    <label className="slice-control">{t('Slice')}<input aria-label={t('Algorithm axial slice')} type="range" min="0" max={view.spatial.shape[2]-1} value={k} onChange={e=>setK(Number(e.target.value))}/><output>k={k}</output></label>
    <p className="small">{t(pick==='seed'?'Click the CT to select a seed':pick==='roi'?(corner?'Choose the second ROI corner; change slice for 3D depth':'Choose the first ROI corner'):'Wheel: slice · Ctrl/Shift + wheel: zoom · Drag: pan · Double-click: reset')}</p>
    </div><div className="algorithm-parameters">
    {panel==='traditional_v2'?<><h3>{t('Seed / ROI')}</h3><p className="small">{t('Closest-RAS indices. ROI uses half-open bounds [i0,i1), [j0,j1), [k0,k1).')}</p>
    <output data-testid="seed-readout">{t('Seed')}: {seed?seed.join(', '):'—'}</output><p data-testid="seed-world">RAS / mm: {world?world.map(n=>fmt(n,2)).join(', '):'—'}</p>
    <div className="coordinate-fields">{['i','j','k'].map((axis,d)=><label key={axis}>{axis}<input aria-label={`Seed ${axis}`} type="number" min="0" max={view.spatial.shape[d]-1} value={seed?.[d]??''} onChange={e=>{const p:Vec3=[...(seed??[0,0,k])];p[d]=Number(e.target.value);setSeed(p)}}/></label>)}</div>
    <div className="coordinate-fields roi-fields">{['i0','i1','j0','j1','k0','k1'].map((axis,d)=><label key={axis}>{axis}<input aria-label={`ROI ${axis}`} type="number" min="0" max={view.spatial.shape[Math.floor(d/2)]} value={roi?.[d]??''} onChange={e=>{const r=roi?[...roi]:[0,view.spatial.shape[0],0,view.spatial.shape[1],0,view.spatial.shape[2]];r[d]=Number(e.target.value);setRoi(r)}}/></label>)}</div>
    <div className="algorithm-actions"><button onClick={()=>{setSeed(null);setRoi(null);setCorner(null);setPick('pan')}}>{t('Clear seed / ROI')}</button>{entry?.reference_selection&&<button onClick={()=>{setSeed(entry.reference_selection!.seed);setRoi(entry.reference_selection!.roi);setK(entry.reference_selection!.seed[2]);setPick('pan')}}>{t('Load archived CT-only selection')}</button>}</div>
    <label>{t('Neighborhood radius')}<input aria-label={t('Neighborhood radius')} type="number" min="1" max="5" value={radius} onChange={e=>setRadius(Number(e.target.value))}/></label>
    <label>{t('Confidence multiplier')}<input aria-label={t('Confidence multiplier')} type="number" min="0.1" max="10" step="0.1" value={multiplier} onChange={e=>setMultiplier(Number(e.target.value))}/></label>
    <label>{t('Iterations')}<input aria-label={t('Iterations')} type="number" min="0" max="10" value={iterations} onChange={e=>setIterations(Number(e.target.value))}/></label>
    <label>{t('Opening radius (mm)')}<input aria-label={t('Opening radius (mm)')} type="number" min="0" max="5" step="0.1" value={opening} onChange={e=>setOpening(Number(e.target.value))}/></label><p className="small">{t('Fixed: 3D six-connected original-seed selection; closing 0 mm. If opening removes the seed, the original mask is retained with a warning.')}</p>
    </>:<><h3>{t('Frozen Epoch 17')}</h3><p className="small">MONAI 2D U-Net · 16/32/64/128/256 · res2<br/>HU [-57,164] → [0,1] · 256×256<br/>FP32 · Sigmoid ≥0.5 · closest-RAS<br/>{t('Native shape and affine restored; no training')}</p><label>{t('Device')}<select aria-label={t('Device')} value={device} onChange={e=>setDevice(e.target.value)}><option value="auto">{t('Auto (CUDA / CPU)')}</option><option value="cpu">CPU</option><option value="cuda">CUDA</option></select></label><p className="small">SHA-256: 966a5e59e57d82bd9813ea411735b82256fe6be7114af2d9cde655684d6bfee4</p></>}
    <button className="run-button" disabled={!available[panel]||!online||busy||!!active||(panel==='traditional_v2'&&(!seed||!roi))} onClick={()=>void start()}>{t(panel==='traditional_v2'?'Run Traditional V2':'Run U-Net Inference')}</button>
    </div></div>
    <details className="case-insight"><summary>{t('Register local CT (optional GT)')}</summary><p>{t('Enter absolute paths under configured input_roots. Files stay on this computer. Use a unique case ID.')}</p><div className="import-fields"><label>{t('Input ID')}<input aria-label={t('Input ID')} value={importId} onChange={e=>setImportId(e.target.value)}/></label><label>{t('CT path')}<input aria-label={t('CT path')} value={ct} onChange={e=>setCt(e.target.value)}/></label><label>{t('GT path (optional)')}<input aria-label={t('GT path (optional)')} value={gt} onChange={e=>setGt(e.target.value)}/></label></div><button disabled={!online||busy||!ct||!importId} onClick={()=>void action(async()=>{const c=await call<InputCase>('/cases',{method:'POST',body:JSON.stringify({case_id:importId,ct,gt:gt||null})});await refresh();setSelected(c.case_id)})}>{t('Register CT')}</button></details>
   </>}
   {current&&<section className="run-detail"><h3>{t('Run status')}: {t(online?current.status:'Status unavailable')}</h3><p className="mono">{current.run_id} · {current.case_id} · {current.algorithm}</p>{online&&current.progress&&<p>{t(current.progress.stage)} {current.progress.slices_total?`${current.progress.slices_done} / ${current.progress.slices_total} ${t('slices processed')}`:''}</p>}
    {!online&&<p>{t('Status unavailable until the local service reconnects')}</p>}
    {['queued','running'].includes(current.status)&&<button disabled={!online||busy} onClick={()=>void action(async()=>{await call(`/jobs/${current.run_id}/cancel`,{method:'POST'});await refresh()})}>{t('Cancel task')}</button>}
    {current.error&&<div className="error" role="alert">{t('Run message')}: {translateMessage(current.error.message)}</div>}
    {current.result&&<><p>{current.result.device} · {fmt(current.result.algorithm_seconds,2)} s · {fmt(current.result.volume_ml)} mL · {current.result.foreground_voxels} voxels · {t(current.result.gt_available?'GT available':'No GT')}</p><p className="small">{t('Preprocessing')}: {current.result.preprocessing_version}<br/>{t('Output')}: {current.result.output_path}<br/>{current.result.checkpoint_sha256&&`E17 SHA-256: ${current.result.checkpoint_sha256}`}</p>{current.result.postprocess?.warning&&<p className="notice">{t('Morphology removed seed; original region-growing mask retained')}</p>}</>}
    <details><summary>{t('Actual parameters and logs')}</summary><pre>{JSON.stringify(current.parameters,null,2)}{'\n'}{current.logs}</pre>{current.error?.traceback&&<pre>{current.error.traceback}</pre>}</details>
    {current.status==='completed'&&<div className="algorithm-actions"><button disabled={!online||busy} onClick={()=>void open([current.run_id])}>{t('Open in analysis workspace')}</button><a href={`${API}/runs/${current.run_id}/export`} download>{t('Export native masks and record')}</a>{current.algorithm==='traditional_v2'&&['region_growing','morphology','prediction'].map(file=><a key={file} href={`${API}/runs/${current.run_id}/files/${file}.nii.gz`} download>{t(file)}</a>)}</div>}
   </section>}
   {panel==='history'&&<section className="run-history"><h3>{t('Run History')}</h3><div className="algorithm-actions"><button disabled={!online||busy||compare.length!==2} onClick={()=>void open(compare)}>{t('Compare selected runs')}</button><span>{t('Select two completed runs with matching inputs')}</span></div><div className="table-scroll"><table><thead><tr>{['Compare','Input ID','Algorithm','Run ID','Status','Started','Open'].map(label=><th key={label}>{t(label)}</th>)}</tr></thead><tbody>{runs.map(r=><tr key={r.run_id}><td><input aria-label={`${t('Compare')} ${r.run_id}`} type="checkbox" disabled={r.status!=='completed'} checked={compare.includes(r.run_id)} onChange={e=>setCompare(old=>e.target.checked?[...old.slice(-1),r.run_id]:old.filter(id=>id!==r.run_id))}/></td><td>{r.case_id}</td><td>{r.algorithm}</td><td><button onClick={()=>setFocused(r.run_id)}>{r.run_id.slice(0,8)}</button></td><td>{t(r.status)}</td><td>{r.created_at}</td><td><button disabled={!online||r.status!=='completed'} onClick={()=>void open([r.run_id])}>{t('Open')}</button></td></tr>)}</tbody></table></div>
    <p><a href="/?setup=storage">{i18n.resolvedLanguage==='zh'?'运行结果管理：查看文件范围与依赖后确认删除':'Run Storage Management: review files and dependencies before confirming deletion'}</a></p>
   </section>}
 </section>;
}
