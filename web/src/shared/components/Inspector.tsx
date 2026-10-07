import {Collapse,Progress,Table,Tabs,Typography} from '../ui';
import {useState} from 'react';
import {display,number,seconds,stages} from '../../metrics.mjs';
import type {Context,Source} from '../types';
import {JsonView} from './JsonView';
import {Sources} from './MarkdownView';

const metric=(context:Context,key:string)=>number(context[key]);
export function Inspector({context,events=[],raw,browserSeconds,onSource}:{context:Context;events?:Array<{name:string;at:number;data:unknown}>;raw?:unknown;browserSeconds?:number;onSource:(source:Source)=>void}){
 const [tab,setTab]=useState('Pipeline'),route=context.route||{},stageRows=stages(context),waterfall=stageRows.map(([stage,value])=>({stage:String(stage),value:number(value)})).filter(item=>item.value!==null) as Array<{stage:string;value:number}>,maxStage=Math.max(0,...waterfall.map(item=>item.value));
 const metricKeys=['first_token_seconds','total_seconds','context_prepare_seconds','tool_model_seconds','retrieval_seconds','context_retrieval_seconds','action_tool_seconds','tool_execution_seconds','prompt_eval_seconds','generation_seconds','model_total_seconds','model_first_delta_seconds','model_first_reasoning_seconds','hidden_reasoning_seconds','model_first_token_seconds','prompt_tokens','server_prompt_tokens','generated_tokens','prompt_tokens_per_second','generation_tokens_per_second','cache_usage','context_utilization','execution_mode','effective_max_tokens','effective_context_size','agent_step_limit','tool_planning_rounds','history_turns','retrieved_history','context_policy','reply_language','thinking_budget','finish_reason'];
 const tools=Array.isArray(context.tool_calls)?context.tool_calls.length:0,memories=Array.isArray(context.memory_retrieval)?context.memory_retrieval.length:0;
 const summary=[
  ['First token',seconds(metric(context,'first_token_seconds'))],
  ['Total',seconds(metric(context,'total_seconds')??browserSeconds)],
  ['Generation',metric(context,'generation_tokens_per_second')===null?'—':metric(context,'generation_tokens_per_second')!.toFixed(1)+' tok/s'],
  ['Retrieval',seconds(metric(context,'context_retrieval_seconds')??metric(context,'retrieval_seconds'))],
  ['Context',metric(context,'context_utilization')===null?'—':Math.round(metric(context,'context_utilization')!*100)+'%'],
  ['Tools / memory',tools+' / '+memories],
 ];
 const items=[
  {key:'Pipeline',label:'Pipeline',children:<div className="space-y-4 p-3"><div className="grid grid-cols-2 gap-2 xl:grid-cols-3">{summary.map(([label,value])=><div key={label} className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-2.5"><div className="text-[9px] uppercase tracking-wider text-zinc-600">{label}</div><div className="mt-1 font-mono text-[11px] text-zinc-200">{value}</div></div>)}</div><Typography.Paragraph type="secondary" className="!mb-0 !text-xs">Measured run telemetry. No hidden reasoning text is exposed.</Typography.Paragraph><div className="space-y-2">{waterfall.map(item=><div key={item.stage} className="grid grid-cols-[110px_1fr_52px] items-center gap-2 text-[10px] text-zinc-400"><span className="truncate">{item.stage}</span><Progress percent={maxStage?Math.max(2,item.value/maxStage*100):0}/><span className="text-right font-mono">{seconds(item.value)}</span></div>)}</div><Table rowKey="label" dataSource={stageRows.map(([label,duration,note])=>({label:String(label),duration,note:String(note)}))} columns={[{title:'Stage',dataIndex:'label',render:(value,record:any)=><div>{value}<div className="text-[9px] text-zinc-500">{record.note}</div></div>},{title:'Duration',dataIndex:'duration',render:value=><span className="font-mono">{seconds(value)}</span>}]} />{events.length>0&&<Collapse items={[{key:'events',label:`Browser event log · ${events.length}`,children:<JsonView value={events}/>}]}/>}</div>},
  {key:'Steps',label:'Steps',children:<div className="p-3"><Typography.Paragraph type="secondary" className="!text-xs">Controlled tool/retrieval steps only; hidden chain-of-thought text is not exposed.</Typography.Paragraph><JsonView value={context.agent_steps||context.tool_calls||[]}/></div>},
  {key:'Decisions',label:'Decisions',children:<div className="p-3"><Table rowKey="key" dataSource={Object.entries({...route,decisions:route.decisions||null}).map(([key,value])=>({key,value:display(value)}))} columns={[{title:'Key',dataIndex:'key',render:value=><span className="font-mono">{value}</span>},{title:'Value',dataIndex:'value'}]}/></div>},
  {key:'Metrics',label:'Metrics',children:<div className="p-3"><Table rowKey="key" dataSource={[{key:'browser observed duration',value:seconds(browserSeconds)},...metricKeys.map(key=>({key,value:display(context[key])}))]} columns={[{title:'Metric',dataIndex:'key',render:value=><span className="font-mono">{value}</span>},{title:'Value',dataIndex:'value',render:value=><span className="font-mono">{value}</span>}]} /></div>},
  {key:'Sources',label:'Sources',children:<div className="p-3"><Sources context={context} onSource={onSource}/><div className="mt-3"><JsonView value={{coverage:context.document_coverage_details,citation_check:context.citation_check,web_verification:context.web_verification}}/></div></div>},
  {key:'Raw',label:'Raw',children:<div className="p-3"><JsonView value={raw??context}/></div>},
 ];
 return <div className="inspector h-full min-h-0 overflow-y-auto overscroll-contain rounded-lg border border-zinc-800 bg-zinc-900/70"><Tabs activeKey={tab} onChange={setTab} items={items}/></div>;
}
