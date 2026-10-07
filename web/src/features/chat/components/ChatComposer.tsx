import {Button,Checkbox,Input,Popover,Select,Space,Upload} from 'antd';
import {Paperclip,RotateCcw,Send,Square} from 'lucide-react';
import type {Doc} from '../../../shared/types';
import type {ChatAttachment} from '../hooks/useChat';

interface Props{
 connected:boolean;busy:boolean;uploading:boolean;input:string;setInput:(value:string)=>void;
 attachments:ChatAttachment[];selected:string[];setSelected:React.Dispatch<React.SetStateAction<string[]>>;
 libraryIds:string[];setLibraryIds:React.Dispatch<React.SetStateAction<string[]>>;docs:Doc[];
 mode:'fast'|'balanced'|'deep';setMode:(value:'fast'|'balanced'|'deep')=>void;output:number;setOutput:(value:number)=>void;
 upload:(files:File[])=>Promise<void>;submit:(replay?:boolean)=>Promise<void>;cancel:()=>void;progress:string;setError:(message:string)=>void;
}
export function ChatComposer(props:Props){
 const count=props.selected.length+props.libraryIds.length;
 const toggleAttachment=(id:string,checked:boolean)=>{if(checked&&count>=4){props.setError('Select at most four combined files.');return;}props.setSelected(items=>checked?[...items,id]:items.filter(item=>item!==id));};
 const toggleLibrary=(id:string,checked:boolean)=>{if(checked&&count>=4){props.setError('Select at most four combined files.');return;}props.setLibraryIds(items=>checked?[...items,id]:items.filter(item=>item!==id));};
 return <div data-testid="chat-composer" className="mx-auto mb-2 mt-3 w-[min(860px,calc(100%-44px))] rounded-[22px] border border-zinc-700 bg-zinc-800/90 px-4 py-3 shadow-sm focus-within:border-zinc-500 max-md:w-[calc(100%-20px)]">
  <Input.TextArea aria-label="Message Keno" value={props.input} autoSize={{minRows:1,maxRows:8}} maxLength={8000} disabled={!props.connected} placeholder={props.connected?'Message Keno…':'Connect in Settings to start testing'} className="!min-h-6 !resize-none !border-0 !bg-transparent !p-0 !shadow-none" onChange={e=>props.setInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void props.submit();}}} onPaste={event=>{const files=Array.from(event.clipboardData.files).filter(file=>file.type.startsWith('image/'));if(files.length){event.preventDefault();void props.upload(files);}}}/>
  {(props.attachments.length>0||props.libraryIds.length>0)&&<div className="mt-2 flex flex-wrap gap-2">{props.attachments.map(item=><Checkbox key={item.id} checked={props.selected.includes(item.id)} disabled={props.busy} onChange={e=>toggleAttachment(item.id,e.target.checked)}>{item.name}</Checkbox>)}{props.libraryIds.map(id=><Button key={id} size="small" onClick={()=>props.setLibraryIds(items=>items.filter(item=>item!==id))}>{props.docs.find(doc=>doc.id===id)?.name||id} ×</Button>)}</div>}
  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
   <Space size={4}>
    <Upload multiple showUploadList={false} beforeUpload={file=>{void props.upload([file as File]);return Upload.LIST_IGNORE;}} accept=".pdf,.docx,.txt,.md,.csv,.png,.jpg,.jpeg,.webp" disabled={!props.connected||props.busy||props.uploading}><Button type="text" icon={<Paperclip size={15}/>}>Attach</Button></Upload>
    <Popover trigger="click" placement="topLeft" content={<div className="max-h-64 w-72 overflow-y-auto space-y-2">{props.docs.length?props.docs.map(doc=><div key={doc.id}><Checkbox checked={props.libraryIds.includes(doc.id)} disabled={props.busy} onChange={e=>toggleLibrary(doc.id,e.target.checked)}>{doc.name}</Checkbox></div>):<span className="text-xs text-zinc-500">No imported documents.</span>}</div>}><Button type="text">Library</Button></Popover>
   </Space>
   <Space size={6} wrap>
    <Select aria-label="Execution mode" value={props.mode} onChange={props.setMode} variant="borderless" popupMatchSelectWidth={140} options={[{value:'fast',label:'Fast'},{value:'balanced',label:'Balanced'},{value:'deep',label:'Deep'}]} className="min-w-28"/>
    <Select aria-label="Response length" value={props.output} onChange={props.setOutput} variant="borderless" popupMatchSelectWidth={140} options={[{value:512,label:'Short'},{value:1024,label:'Medium'},{value:2048,label:'Long'},{value:3072,label:'Extended'}]} className="min-w-28"/>
    {props.busy?<Button icon={<Square size={14}/>} onClick={props.cancel}>Stop</Button>:<Button onClick={()=>void props.submit(true)} disabled={!props.connected||props.uploading} icon={<RotateCcw size={14}/>}>Retry</Button>}
    <Button type="primary" icon={<Send size={15}/>} disabled={!props.connected||props.busy||props.uploading||!props.input.trim()} onClick={()=>void props.submit()}>Send</Button>
   </Space>
  </div>
  {props.progress&&<div className="mt-2 text-[10px] text-zinc-500">{props.progress}</div>}
 </div>;
}
