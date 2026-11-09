import {useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {bestEpoch,saveFile} from './experiments';
import type {Experiment,Epoch} from './experiments';
const COLORS=['#2468b5','#ad6515','#7e51a6','#168272'];
export default function TrainingChart({runs,metric,onEpoch}:{runs:Experiment[];metric:string;onEpoch:(run:Experiment,epoch:Epoch)=>void}){
 const {t}=useTranslation();const svg=useRef<SVGSVGElement>(null);
 const all=runs.flatMap(r=>r.epochs??[]),indices=[...new Set(all.map(e=>e.epoch))].sort((a,b)=>a-b),min=indices[0]??0,max=indices.at(-1)??0,defaultLo=all.length>2000?indices[Math.max(0,indices.length-500)]:min;
 const [range,setRange]=useState<[number,number]|null>(null),[points,setPoints]=useState(true),[hover,setHover]=useState('');
 const lo=Math.max(min,Math.min(range?.[0]??defaultLo,max)),hi=Math.max(lo,Math.min(range?.[1]??max,max));
 const visible=all.filter(e=>e.epoch>=lo&&e.epoch<=hi).map(e=>e.metrics[metric]).filter((n):n is number=>n!=null);
 const ylo=metric==='learning_rate'?Math.min(...visible)*.9:Math.min(0,...visible),yhi=Math.max(...visible,0)*1.08||1;
 const x=(e:number)=>hi===lo?448:68+(e-lo)/(hi-lo)*760,y=(v:number)=>235-(v-ylo)/(yhi-ylo||1)*195;
 const unit=runs.find(r=>r.definitions[metric])?.definitions[metric]?.unit??'';
 const exportChart=()=>{if(svg.current){const copy=svg.current.cloneNode(true) as SVGSVGElement;copy.setAttribute('xmlns','http://www.w3.org/2000/svg');const meta=document.createElementNS('http://www.w3.org/2000/svg','metadata');meta.textContent=JSON.stringify({metric,unit,range:[lo,hi],smoothing:false,experiments:runs.map(r=>({experiment_id:r.experiment_id,definitions:r.definitions,sources:r.sources,split_id:r.split_id,lineage:r.lineage,points:r.epochs?.map(e=>({epoch:e.epoch,stage:e.stage,value:e.metrics[metric]??null,source:e.sources[metric]??null,checkpoint:e.checkpoint??null,flags:e.flags}))}))});copy.prepend(meta);saveFile(`training-${metric}.svg`,new XMLSerializer().serializeToString(copy),'image/svg+xml')}};
 return <section className="training-chart" aria-label={t('Training curve')}>
 <div className="research-toolbar"><label>{t('Epoch from')} <input aria-label={t('Epoch from')} type="number" min={min} max={max} value={lo} onChange={e=>setRange([Math.min(Number(e.target.value),hi),hi])}/></label><label>{t('Epoch to')} <input aria-label={t('Epoch to')} type="number" min={min} max={max} value={hi} onChange={e=>setRange([lo,Math.max(lo,Number(e.target.value))])}/></label><button onClick={()=>setRange(null)}>{t('Reset zoom')}</button><label><input type="checkbox" checked={points} onChange={e=>setPoints(e.target.checked)}/>{t('Raw data points')}</label><button onClick={exportChart}>{t('Export chart (SVG)')}</button></div>
 <p className="small" data-testid="epoch-window">{t('Epoch range')}: {lo}–{hi} / {min}–{max} · {t('Full recorded data is retained in exports.')}</p>
 {visible.length>2000?<p>{t('More than 2000 points: narrow the Epoch range to view raw points.')}</p>:!visible.length?<p>{t('Not Recorded')}</p>:<div className="training-chart-scroll"><svg ref={svg} data-testid="training-chart" viewBox="0 0 900 310" role="img" aria-label={`${t(metric)} / ${t('Epoch')}`} style={{width:'100%',minWidth:540,background:'white',fontFamily:'Arial,sans-serif'}}>
 <rect x="0" y="0" width="900" height="310" fill="white"/><text x="16" y="18" fill="#42536a" fontSize="12">{t(metric)} ({t(unit)}) · {t('Raw values; no smoothing')}</text>
 {[0,1,2,3,4].map(n=>{const value=ylo+(yhi-ylo)*n/4;return <g key={n}><line x1="68" x2="828" y1={y(value)} y2={y(value)} stroke="#e3e9ef"/><text x="61" y={y(value)+4} textAnchor="end" fontSize="10" fill="#52647c">{value.toPrecision(3)}</text></g>})}
 {(lo===hi?[0]:[0,1,2,3,4,5,6]).map(n=>{const epoch=lo+(hi-lo)*n/6;return <text key={n} x={x(epoch)} y="256" textAnchor="middle" fill="#52647c" fontSize="11">{Number(epoch.toFixed(1))}</text>})}<text x="450" y="280" textAnchor="middle" fontSize="12" fill="#42536a">{t('Epoch')} · {t('Recorded epoch numbers')}</text>
 {runs.map((run,i)=>{const best=bestEpoch(run),epochs=(run.epochs??[]).filter(e=>e.epoch>=lo&&e.epoch<=hi);const segments:Epoch[][]=[];for(const e of epochs){if(e.metrics[metric]==null){segments.push([]);continue}const last=segments.at(-1);if(!last?.length||last.at(-1)?.stage!==e.stage)segments.push([e]);else last.push(e)}return <g key={run.experiment_id}>
 {segments.filter(s=>s.length).map((segment,j)=><polyline key={j} fill="none" stroke={COLORS[i%4]} strokeWidth="2" points={segment.map(e=>`${x(e.epoch)},${y(e.metrics[metric]!)}`).join(' ')}/>)}
 {epochs.filter((e,j)=>j&&e.stage!==epochs[j-1].stage).map(e=><g key={'boundary'+e.epoch}><line x1={x(e.epoch)-5} x2={x(e.epoch)-5} y1="35" y2="235" stroke={COLORS[i%4]} strokeDasharray="4 4" opacity=".45"/><text x={x(e.epoch)} y={35+i*13} fontSize="9" fill={COLORS[i%4]}>{e.stage}</text></g>)}
 {epochs.filter(e=>e.metrics[metric]!=null).map(e=><circle key={e.epoch} data-testid={`point-${run.experiment_id}-${e.epoch}`} cx={x(e.epoch)} cy={y(e.metrics[metric]!)} r={e===best?6:e.flags.length?4.5:3.4} fill={points||e===best||e.flags.length?COLORS[i%4]:'transparent'} stroke={e.flags.includes('early_stopping')?'#b14343':e===best?'#184f30':'white'} strokeWidth={e===best||e.flags.length?2:1} tabIndex={0} role="button" aria-label={`${run.experiment_id} ${t('Epoch')} ${e.epoch}: ${e.metrics[metric]}`} onMouseEnter={()=>setHover(`${run.experiment_id} · E${e.epoch} · ${t(metric)} = ${e.metrics[metric]} · ${e.stage}`)} onFocus={()=>setHover(`${run.experiment_id} · E${e.epoch} = ${e.metrics[metric]}`)} onClick={()=>onEpoch(run,e)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' ')onEpoch(run,e)}}><title>{`${run.experiment_id} / E${e.epoch}\n${metric}: ${e.metrics[metric]}\n${e.stage}\n${e.sources[metric]?.path}\n${e.flags.join(', ')}`}</title></circle>)}
 </g>})}
 <text x="68" y="301" fill="#52647c" fontSize="9">{runs.map((r,i)=>`${i+1}: ${r.experiment_id}`).join('    ')} · {t('Dashed lines: stage boundaries')}</text>
 </svg></div>}
 <output className="training-readout" aria-live="polite">{hover||t('Hover for values; click a point for provenance')}</output>
 <div className="research-legend">{runs.map((r,i)=><span key={r.experiment_id}><i style={{background:COLORS[i%4]}}/>{r.experiment_id}</span>)}<span>● {t('Best validation model')} · {t('Outlined: recorded anomaly or early stopping')}</span></div>
 </section>;
}
