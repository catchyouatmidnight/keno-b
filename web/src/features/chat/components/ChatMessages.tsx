import {useEffect,useMemo,useRef} from 'react';
import {Button,Space,Tag,Tooltip,Typography} from '../../../shared/ui';
import {Bookmark,Brain,Copy,GitBranch,Hammer,Lightbulb,Pencil,RotateCcw,ThumbsDown,ThumbsUp} from 'lucide-react';
import {Markdown,Sources} from '../../../components';
import {seconds} from '../../../metrics.mjs';
import type {Run,Source} from '../../../shared/types';

const relativeTime=(value:string)=>{const at=new Date(value).getTime();if(!Number.isFinite(at))return '';const ms=Math.max(0,Date.now()-at),minute=60000,hour=3600000,day=86400000;if(ms<minute)return 'just now';if(ms<hour)return Math.floor(ms/minute)+'m ago';if(ms<day)return Math.floor(ms/hour)+'h ago';return Math.floor(ms/day)+'d ago';};
const toolCount=(run:Run)=>Array.isArray(run.context.tool_calls)?run.context.tool_calls.length:0;

export function ChatMessages({turns,selectedRun,onSelect,onSource,onFeedback,onBranch,onSaveCase,onInspect,progress}:{turns:Run[];selectedRun:Run|null;onSelect:(run:Run)=>void;onSource:(source:Source)=>void;onFeedback:(run:Run,value:'up'|'down')=>void;onBranch:(run:Run,action:'branch'|'edit'|'regenerate')=>void;onSaveCase:(run:Run)=>void;onInspect:(run:Run)=>void;progress:string}){
 const logRef=useRef<HTMLDivElement>(null);
 const streaming=useMemo(()=>turns.some(run=>run.status==='running'),[turns]);
 const lastText=turns.at(-1)?.assistant_text||'';
 useEffect(()=>{const node=logRef.current;if(!node)return;const nearBottom=node.scrollHeight-node.scrollTop-node.clientHeight<180;if(nearBottom||streaming)node.scrollTo({top:node.scrollHeight,behavior:streaming?'auto':'smooth'});},[turns.length,lastText,streaming,progress]);
 return <div ref={logRef} data-testid="chat-log" className="flex-1 overflow-y-auto px-[22px] py-6 max-md:px-[10px]" role="log" aria-live="polite" aria-busy={streaming}>
  <div className="mx-auto w-full max-w-[860px] space-y-8">
   {!turns.length&&<div className="grid min-h-[44vh] place-items-center"><div className="max-w-lg text-center"><div className="mx-auto mb-4 grid h-10 w-10 place-items-center rounded-xl border border-zinc-800 bg-zinc-900"><Lightbulb size={18}/></div><Typography.Title level={4}>Start a conversation</Typography.Title><Typography.Paragraph type="secondary">Ask about your documents, use local tools, or test Keno’s reasoning. Nothing is sent to an external inference provider.</Typography.Paragraph><div className="mt-4 grid gap-2 text-left sm:grid-cols-3">{['Summarize a document','Recall something I saved','Compare two ideas'].map(item=><div key={item} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-[11px] text-zinc-400">{item}</div>)}</div></div></div>}
   {turns.map(run=><div data-testid="conversation-turn" key={run.request_id} onClick={()=>onSelect(run)} className={selectedRun?.request_id===run.request_id?'rounded-xl bg-zinc-900/30':''}>
    <div className="group flex gap-4"><div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-zinc-700 bg-zinc-800 font-semibold">Y</div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><Typography.Text strong>You</Typography.Text><span className="text-[10px] text-zinc-500">{relativeTime(run.created_at)}</span><div className="ml-auto opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100"><Button aria-label="Edit from this message" type="text" size="small" icon={<Pencil size={13}/>} onClick={e=>{e.stopPropagation();onBranch(run,'edit');}}/><Button aria-label="Branch from this message" type="text" size="small" icon={<GitBranch size={13}/>} onClick={e=>{e.stopPropagation();onBranch(run,'branch');}}/></div></div><div className="mt-2 whitespace-pre-wrap text-[15px] leading-7 text-zinc-200">{run.user_text}</div></div></div>
    <div className="mt-6 flex gap-4"><div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-zinc-700 bg-zinc-800 text-lg font-semibold">k</div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><Typography.Text strong>Keno</Typography.Text><span className="text-xs text-zinc-500">Local AI Agent</span>{run.status==='running'&&<Tag>processing</Tag>}</div>{run.status==='running'&&<div className="mt-3 flex items-center gap-2 text-xs text-zinc-500"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-300"/>{progress||'Processing request…'}</div>}<div className="mt-3"><Markdown sources={run.context.document_sources||[]} text={run.assistant_text||(run.status==='running'?'':'No confirmed saved answer.')} onSource={onSource}/></div>{run.status==='failed'&&<div className="mt-2 text-xs text-red-300">Incomplete response · not confirmed saved</div>}<Sources context={run.context} onSource={onSource}/>
     <div className="mt-3 flex items-center gap-1 text-zinc-500">
      <Tooltip title="Copy"><Button aria-label="Copy answer" type="text" size="small" icon={<Copy size={16}/>} onClick={e=>{e.stopPropagation();void navigator.clipboard.writeText(run.assistant_text||'');}}/></Tooltip>
      <Button aria-label="Mark helpful" type={run.feedback?.value==='up'?'primary':'text'} size="small" icon={<ThumbsUp size={16}/>} onClick={e=>{e.stopPropagation();onFeedback(run,'up');}}/>
      <Button aria-label="Mark unhelpful" type={run.feedback?.value==='down'?'primary':'text'} size="small" icon={<ThumbsDown size={16}/>} onClick={e=>{e.stopPropagation();onFeedback(run,'down');}}/>
      <Button aria-label="Regenerate response" type="text" size="small" icon={<RotateCcw size={16}/>} onClick={e=>{e.stopPropagation();onBranch(run,'regenerate');}}/>
      <Button aria-label="Save benchmark case" type="text" size="small" icon={<Bookmark size={16}/>} onClick={e=>{e.stopPropagation();onSaveCase(run);}}/>
      <Button aria-label="Inspect run" type="text" size="small" icon={<Brain size={16}/>} onClick={e=>{e.stopPropagation();onInspect(run);}}/>
      {toolCount(run)>0&&<span className="ml-1 inline-flex items-center gap-1 text-[10px]"><Hammer size={15}/>{toolCount(run)}</span>}
      <div className="ml-2 h-px flex-1 bg-zinc-700"/><span className="text-[10px]">{seconds(run.context.total_seconds)}</span>{typeof run.context.generated_tokens==='number'&&<span className="text-[10px]">{String(run.context.generated_tokens)} tokens</span>}
     </div>
    </div></div>
   </div>)}
  </div>
 </div>;
}
