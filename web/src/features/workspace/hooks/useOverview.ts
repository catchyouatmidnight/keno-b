import {useEffect,useMemo,useState} from 'react';
import {useLab} from '../../../app/providers/LabProvider';
import {number,percentile} from '../../../metrics.mjs';
import {verdict} from '../../../Benchmarks';

export function useOverview(){
 const lab=useLab(),[memoryCount,setMemoryCount]=useState<number|null>(null);
 useEffect(()=>{if(!lab.connected){setMemoryCount(null);return;}void lab.api.get<unknown[]>('/memories?limit=500').then(items=>setMemoryCount(items.length)).catch(()=>setMemoryCount(null));},[lab.connected,lab.api,lab.runs.length]);
 return useMemo(()=>{
  const complete=lab.runs.filter(r=>r.status==='complete'),first=complete.map(r=>number(r.context.first_token_seconds)),firstMeasured=first.filter((value):value is number=>value!==null),firstAverage=firstMeasured.length?firstMeasured.reduce((a,b)=>a+b,0)/firstMeasured.length:null,total=complete.map(r=>number(r.context.total_seconds)),generation=complete.map(r=>number(r.context.generation_tokens_per_second)).filter((value):value is number=>value!==null),tested=lab.results.filter(r=>verdict(r)!==null),failed=lab.runs.filter(r=>r.status==='failed'),last=lab.runs[0],today=new Date().toISOString().slice(0,10),searchesToday=lab.runs.filter(r=>r.created_at.slice(0,10)===today&&Array.isArray(r.context.tool_calls)&&r.context.tool_calls.some((call:unknown)=>{const item=call as {name?:string;status?:string};return item.name==='web_search'&&item.status==='complete';})).length;
  const trend=[...lab.runs].reverse().filter(r=>number(r.context.first_token_seconds)!==null).slice(-20).map((r,index)=>({run:index+1,first:number(r.context.first_token_seconds),total:number(r.context.total_seconds)}));
  const stages=last?[{stage:'Routing',seconds:number(last.context.route?.seconds)},{stage:'Context',seconds:number(last.context.context_prepare_seconds)},{stage:'Retrieval/tools',seconds:number(last.context.tool_execution_seconds??last.context.tool_seconds)},{stage:'Prompt eval',seconds:number(last.context.prompt_eval_seconds)},{stage:'Generation',seconds:number(last.context.generation_seconds)}].filter(item=>item.seconds!==null):[];
  const modelGroups=new Map<string,typeof lab.results>();for(const result of lab.results){const model=typeof result.configuration?.model==='string'?result.configuration.model:'Unrecorded';modelGroups.set(model,[...(modelGroups.get(model)||[]),result]);}
  const modelStats=[...modelGroups].map(([model,items])=>{const measured=items.map(item=>number(item.run?.context?.first_token_seconds)).filter((value):value is number=>value!==null),totals=items.map(item=>number(item.run?.context?.total_seconds)).filter((value):value is number=>value!==null),judged=items.filter(item=>verdict(item)!==null);return {model,runs:items.length,first:percentile(measured,.5),total:percentile(totals,.5),pass:judged.length?judged.filter(verdict).length+'/'+judged.length:'—'};});
  return {...lab,memoryCount,complete,first,firstMeasured,firstAverage,total,generation,tested,failed,last,searchesToday,trend,stages,modelStats};
 },[lab,memoryCount]);
}
