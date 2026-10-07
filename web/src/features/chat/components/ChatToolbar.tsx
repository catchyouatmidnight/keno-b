import {Bookmark,Plus,Trash2} from 'lucide-react';
import {Button,Popconfirm,Select} from '../../../shared/ui';
import type {Session} from '../../../shared/types';
export function ChatToolbar({sessionId,sessions,busy,memoryEnabled,mode,setMode,output,setOutput,onSession,onNew,onClear,onMemory,onSaveCase,onDelete}:{sessionId:string;sessions:Session[];busy:boolean;memoryEnabled:boolean;mode:'fast'|'balanced'|'deep';setMode:(value:'fast'|'balanced'|'deep')=>void;output:number;setOutput:(value:number)=>void;onSession:(id:string)=>void;onNew:()=>void;onClear:()=>void;onMemory:()=>void;onSaveCase:()=>void;onDelete:()=>void}){
 return <div className="flex min-w-0 flex-wrap items-center gap-2 border-b border-zinc-800 p-2.5">
  <Select className="min-w-0 basis-full flex-1 sm:min-w-[220px] sm:basis-auto" value={sessionId||undefined} placeholder="New conversation" disabled={busy} onChange={onSession} options={sessions.map(session=>({value:session.id,label:session.title}))}/>
  <Select aria-label="Execution mode" className="min-w-0 flex-1 sm:w-28 sm:flex-none" value={mode} onChange={setMode} options={[{value:'fast',label:'Fast'},{value:'balanced',label:'Balanced'},{value:'deep',label:'Deep'}]}/>
  <Select aria-label="Response length" className="min-w-0 flex-1 sm:w-28 sm:flex-none" value={output} onChange={setOutput} options={[{value:512,label:'Short'},{value:1024,label:'Medium'},{value:2048,label:'Long'},{value:3072,label:'Extended'}]}/>
  <div className="flex w-full min-w-0 flex-wrap items-center gap-1 sm:w-auto">
   <Button type="text" onClick={onNew} disabled={busy} icon={<Plus size={14}/>}>New</Button>
   <Button type="text" onClick={onClear} disabled={busy}>Clear</Button>
   <Button type="text" onClick={onMemory} disabled={!sessionId||busy}>{memoryEnabled?'Memory on':'Memory off'}</Button>
   <Button type="text" aria-label="Save as benchmark case" onClick={onSaveCase} disabled={busy} icon={<Bookmark size={14}/>}/>
   <Popconfirm title="Delete this session and its messages?" onConfirm={onDelete} disabled={!sessionId||busy}><Button type="text" danger aria-label="Delete session" disabled={!sessionId||busy} icon={<Trash2 size={14}/>}/></Popconfirm>
  </div>
 </div>;
}
