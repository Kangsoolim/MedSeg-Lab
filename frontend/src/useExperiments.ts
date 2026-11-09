import {useCallback,useEffect,useRef,useState} from 'react';
import {EXP_API} from './experiments';
import type {Catalog,Experiment} from './experiments';
export function useExperiments(){
 const [records,setRecords]=useState<Experiment[]>([]),[catalog,setCatalog]=useState<Catalog|null>(null),[online,setOnline]=useState(false),[error,setError]=useState(''),[loaded,setLoaded]=useState(false);
 const token=useRef('');const archived=useRef<Experiment[]>([]);const mounted=useRef(true);
 const refresh=useCallback(async()=>{
  try{const h=await fetch(EXP_API+'/health',{signal:AbortSignal.timeout(3000)});if(!h.ok)throw new Error('Service unavailable');token.current=(await h.json()).token;
   const response=await fetch(EXP_API+'/experiments',{signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error('Experiment service unavailable');const data=await response.json() as Experiment[];
   if(mounted.current){setRecords(data);setOnline(true);setError('')}
  }catch{if(mounted.current){setOnline(false);setRecords(archived.current)}}
  finally{if(mounted.current)setLoaded(true)}
 },[]);
 useEffect(()=>{mounted.current=true;const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;
  const staticData=fetch('/training/catalog.json',{signal:controller.signal}).then(r=>{if(!r.ok)throw new Error('Training catalog missing / 训练目录缺失');return r.json() as Promise<Catalog>}).then(c=>{if(mounted.current){archived.current=c.experiments;setCatalog(c);setRecords(old=>old.length?old:c.experiments)}}).catch(e=>{if(mounted.current&&e.name!=='AbortError')setError(e.message)});
  const poll=async()=>{await staticData;await refresh();if(mounted.current)timer=setTimeout(poll,8000)};void poll();
  return()=>{mounted.current=false;controller.abort();clearTimeout(timer)};
 },[refresh]);
 const importLog=async(body:unknown)=>{const response=await fetch(EXP_API+'/experiments/import',{method:'POST',signal:AbortSignal.timeout(120000),headers:{'Content-Type':'application/json','X-MedSeg-Token':token.current},body:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));await refresh();return value as Experiment};
 return {records,catalog,online,error,loaded,refresh,importLog,token};
}
