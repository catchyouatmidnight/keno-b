import {ArrowUp,FolderOpen,Paperclip,Square,UploadCloud} from 'lucide-react';
import {Button,Checkbox,Popover,Textarea,Upload} from '../../../shared/ui';
import type {Doc} from '../../../shared/types';
import type {ChatAttachment} from '../hooks/useChat';

interface Props{
 connected:boolean;busy:boolean;uploading:boolean;input:string;setInput:(value:string)=>void;
 attachments:ChatAttachment[];selected:string[];setSelected:React.Dispatch<React.SetStateAction<string[]>>;
 libraryIds:string[];setLibraryIds:React.Dispatch<React.SetStateAction<string[]>>;docs:Doc[];
 upload:(files:File[])=>Promise<void>;submit:(replay?:boolean)=>Promise<void>;cancel:()=>void;progress:string;setError:(message:string)=>void;
}
export function ChatComposer(props:Props){
 const count=props.selected.length+props.libraryIds.length;
 const toggleAttachment=(id:string,checked:boolean)=>{if(checked&&count>=4){props.setError('Select at most four combined files.');return;}props.setSelected(items=>checked?[...items,id]:items.filter(item=>item!==id));};
 const toggleLibrary=(id:string,checked:boolean)=>{if(checked&&count>=4){props.setError('Select at most four combined files.');return;}props.setLibraryIds(items=>checked?[...items,id]:items.filter(item=>item!==id));};
 const attachMenu=<div className="w-72 space-y-3">
  <Upload multiple beforeUpload={(file:File)=>{void props.upload([file]);return Upload.LIST_IGNORE;}} accept=".pdf,.docx,.txt,.md,.csv,.png,.jpg,.jpeg,.webp" disabled={!props.connected||props.busy||props.uploading}><Button block icon={<UploadCloud size={14}/>}>Upload files</Button></Upload>
  <div className="border-t border-zinc-800 pt-2"><div className="mb-2 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-zinc-500"><FolderOpen size={12}/>Library</div><div className="max-h-48 space-y-2 overflow-y-auto">{props.docs.length?props.docs.map(doc=><div key={doc.id}><Checkbox checked={props.libraryIds.includes(doc.id)} disabled={props.busy} onChange={(e:any)=>toggleLibrary(doc.id,e.target.checked)}>{doc.name}</Checkbox></div>):<div className="text-xs text-zinc-600">No imported documents.</div>}</div></div>
 </div>;
 return <div className="mx-auto mb-2 mt-3 w-[min(860px,calc(100%-44px))] max-md:w-[calc(100%-20px)]">
  {(props.attachments.length>0||props.libraryIds.length>0)&&<div className="mb-2 flex flex-wrap gap-1.5 px-2">{props.attachments.map(item=><button key={item.id} type="button" onClick={()=>toggleAttachment(item.id,!props.selected.includes(item.id))} className={`rounded-md border px-2 py-1 text-[10px] ${props.selected.includes(item.id)?'border-zinc-500 bg-zinc-800 text-zinc-100':'border-zinc-800 text-zinc-500'}`}>{item.name}</button>)}{props.libraryIds.map(id=><button key={id} type="button" onClick={()=>props.setLibraryIds(items=>items.filter(item=>item!==id))} className="rounded-md border border-zinc-800 px-2 py-1 text-[10px] text-zinc-400">{props.docs.find(doc=>doc.id===id)?.name||id} ×</button>)}</div>}
  <div data-testid="chat-composer" className="flex min-h-[68px] items-end gap-2 rounded-[30px] border border-zinc-800 bg-zinc-900 px-3 py-2.5 shadow-sm transition-colors focus-within:border-zinc-600">
   <Popover placement="topLeft" content={attachMenu}><Button type="text" aria-label="Attach" className="mb-0.5 h-10 w-10 shrink-0 rounded-full p-0 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100" icon={<Paperclip size={20}/>}/></Popover>
   <Textarea aria-label="Message Keno" value={props.input} autoSize={{minRows:1,maxRows:8}} maxLength={8000} disabled={!props.connected} placeholder={props.connected?'Ask Keno anything…':'Connect in Settings to start testing'} className="max-h-40 min-h-10 flex-1 resize-none border-0 bg-transparent px-1 py-2.5 text-[15px] leading-5 shadow-none focus:border-transparent" onChange={(e:any)=>props.setInput(e.target.value)} onKeyDown={(e:any)=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void props.submit();}}} onPaste={(event:any)=>{const files=Array.from(event.clipboardData.files as FileList).filter((file:File)=>file.type.startsWith('image/'));if(files.length){event.preventDefault();void props.upload(files);}}}/>
   {props.busy?<Button type="primary" aria-label="Stop" className="mb-0.5 h-10 w-10 shrink-0 rounded-full p-0" icon={<Square size={16}/>} onClick={props.cancel}/>:<Button type="primary" aria-label="Send" className="mb-0.5 h-10 w-10 shrink-0 rounded-full p-0" icon={<ArrowUp size={20}/>} disabled={!props.connected||props.uploading||!props.input.trim()} onClick={()=>void props.submit()}/>}
  </div>
  <div className="mt-2 text-center text-[10px] text-zinc-600">{props.progress||'Attach files · Enter to send · Shift+Enter for a new line'}</div>
 </div>;
}
