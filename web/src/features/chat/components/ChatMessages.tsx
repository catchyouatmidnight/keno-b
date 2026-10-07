import {Button,Space,Tag,Tooltip,Typography} from 'antd';
import {Bookmark,Brain,Copy,GitBranch,Hammer,Pencil,RotateCcw,ThumbsDown,ThumbsUp} from 'lucide-react';
import {Markdown,Sources} from '../../../components';
import {seconds} from '../../../metrics.mjs';
import type {Run,Source} from '../../../shared/types';

const relativeTime=(value:string)=>{const at=new Date(value).getTime();if(!Number.isFinite(at))return '';const ms=Math.max(0,Date.now()-at),minute=60000,hour=3600000,day=86400000;if(ms<minute)return 'just now';if(ms<hour)return Math.floor(ms/minute)+'m ago';if(ms<day)return Math.floor(ms/hour)+'h ago';return Math.floor(ms/day)+'d ago';};
const toolCount=(run:Run)=>Array.isArray(run.context.tool_calls)?run.context.tool_calls.length:0;

export function ChatMessages({turns,selectedRun,onSelect,onSource,onFeedback,onBranch,onSaveCase,onInspect,progress}:{turns:Run[];selectedRun:Run|null;onSelect:(run:Run)=>void;onSource:(source:Source)=>void;onFeedback:(run:Run,value:'up'|'down')=>void;onBranch:(run:Run,action:'branch'|'edit'|'regenerate')=>void;onSaveCase:(run:Run)=>void;onInspect:(run:Run)=>void;progress:string}){
 return <div className="flex-1 overflow-y-auto px-[22px] py-6 max-md:px-[10px]" role="log" aria-live="polite">
  <div className="mx-auto w-full max-w-[860px] space-y-8">{turns.map(run=><div data-testid="conversation-turn" key={run.request_id} onClick={()=>onSelect(run)} className={selectedRun?.request_id===run.request_id?'rounded-xl bg-zinc-900/30':''}>
   <div className="flex gap-4"><div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-zinc-700 bg-zinc-800 font-semibold">Y</div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><Typography.Text strong>You</Typography.Text><span className="text-[10px] text-zinc-500">{relativeTime(run.created_at)}</span><div className="ml-auto opacity-0 transition-opacity hover:opacity-100 group-hover:opacity-100"><Button type="text" size="small" icon={<Pencil size={13}/>} onClick={e=>{e.stopPropagation();onBranch(run,'edit');}}/><Button type="text" size="small" icon={<GitBranch size={13}/>} onClick={e=>{e.stopPropagation();onBranch(run,'branch');}}/></div></div><div className="mt-2 whitespace-pre-wrap text-[15px] leading-7 text-zinc-200">{run.user_text}</div></div></div>
   <div className="mt-6 flex gap-4"><div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-zinc-700 bg-zinc-800 text-lg font-semibold">k</div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><Typography.Text strong>Keno</Typography.Text><span className="text-xs text-zinc-500">Local AI Agent</span>{run.status==='running'&&<Tag>processing</Tag>}</div>{run.status==='running'&&<div className="mt-2 text-xs text-zinc-500">{progress||'Processing request…'}</div>}<div className="mt-3"><Markdown sources={run.context.document_sources||[]} text={run.assistant_text||(run.status==='running'?'':'No confirmed saved answer.')} onSource={onSource}/></div>{run.status==='failed'&&<div className="mt-2 text-xs text-red-300">Incomplete response · not confirmed saved</div>}<Sources context={run.context} onSource={onSource}/>
    <div className="mt-3 flex items-center gap-1 text-zinc-500">
     <Tooltip title="Copy"><Button type="text" size="small" icon={<Copy size={16}/>} onClick={e=>{e.stopPropagation();void navigator.clipboard.writeText(run.assistant_text||'');}}/></Tooltip>
     <Button aria-label="Mark helpful" type={run.feedback?.value==='up'?'primary':'text'} size="small" icon={<ThumbsUp size={16}/>} onClick={e=>{e.stopPropagation();onFeedback(run,'up');}}/>
     <Button aria-label="Mark unhelpful" type={run.feedback?.value==='down'?'primary':'text'} size="small" icon={<ThumbsDown size={16}/>} onClick={e=>{e.stopPropagation();onFeedback(run,'down');}}/>
     <Button type="text" size="small" icon={<RotateCcw size={16}/>} onClick={e=>{e.stopPropagation();onBranch(run,'regenerate');}}/>
     <Button type="text" size="small" icon={<Bookmark size={16}/>} onClick={e=>{e.stopPropagation();onSaveCase(run);}}/>
     <Button type="text" size="small" icon={<Brain size={16}/>} onClick={e=>{e.stopPropagation();onInspect(run);}}/>
     {toolCount(run)>0&&<span className="ml-1 inline-flex items-center gap-1 text-[10px]"><Hammer size={15}/>{toolCount(run)}</span>}
     <div className="ml-2 h-px flex-1 bg-zinc-700"/><span className="text-[10px]">{seconds(run.context.total_seconds)}</span>{typeof run.context.generated_tokens==='number'&&<span className="text-[10px]">{String(run.context.generated_tokens)} tokens</span>}
    </div>
   </div></div>
  </div>)}</div>
 </div>;
}
