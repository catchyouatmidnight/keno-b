import {useEffect,useRef,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {useLab} from '../../../app/providers/LabProvider';
import {base64File} from '../../../shared/api/client';
import {randomId} from '../../../id.mjs';
import type {Context,Run,Session,Source} from '../../../shared/types';

export interface ChatAttachment {id:string;name:string;pages:number;kind:string}
type Mode='fast'|'balanced'|'deep';

export function useChat(){
 const {api,connected,sessions,docs,refresh,setError,setCognitive}=useLab();
 const [params,setParams]=useSearchParams();
 const sessionId=params.get('session')||'';
 const [turns,setTurns]=useState<Run[]>([]),[input,setInput]=useState(''),[busy,setBusy]=useState(false),[uploading,setUploading]=useState(false);
 const [output,setOutput]=useState(512),[mode,setMode]=useState<Mode>('balanced'),[attachments,setAttachments]=useState<ChatAttachment[]>([]);
 const [selected,setSelected]=useState<string[]>([]),[libraryIds,setLibraryIds]=useState<string[]>(params.getAll('doc')),[selectedRun,setSelectedRun]=useState<Run|null>(null);
 const [events,setEvents]=useState<Array<{name:string;at:number;data:unknown}>>([]),[browserSeconds,setBrowserSeconds]=useState<number>(),[progress,setProgress]=useState('');
 const [source,setSource]=useState<Source|null>(null),[inspect,setInspect]=useState(true),[panelWidth,setPanelWidth]=useState(370),[memoryEnabled,setMemoryEnabled]=useState(true);
 const abort=useRef<AbortController|null>(null),retry=useRef<{id:string;input:string;session:string;ids:string[];library:string[]}|null>(null),alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;abort.current?.abort();};},[]);
 useEffect(()=>{
  if(!connected){setTurns([]);setAttachments([]);setSelectedRun(null);setEvents([]);setInput('');setLibraryIds([]);setSelected([]);setSource(null);setMemoryEnabled(true);retry.current=null;return;}
  if(busy||uploading)return;
  if(!sessionId){setTurns([]);setAttachments([]);setMemoryEnabled(true);return;}
  const control=new AbortController();
  void Promise.all([
   api.get<Session>(`/conversations/${sessionId}`,control.signal),
   api.get<ChatAttachment[]>(`/conversations/${sessionId}/attachments`,control.signal),
   api.get<{enabled:boolean}>(`/conversations/${sessionId}/memory`,control.signal),
  ]).then(([session,files,memory])=>{
   setTurns((session.turns||[]).map(turn=>({...turn,context:JSON.parse(turn.metadata||'{}')})));
   setAttachments(files);setMemoryEnabled(memory.enabled);setSelected([]);retry.current=null;
   const from=params.get('prompt_from'),run=(session.turns||[]).find(turn=>turn.request_id===from);
   if(run){setInput(run.user_text);const context=JSON.parse(run.metadata||'{}');const ids=(context.attachment_ids||[]) as string[];setSelected(ids.filter(id=>!id.startsWith('lib:')));setLibraryIds(ids.filter(id=>id.startsWith('lib:')).map(id=>id.slice(4)));}
  }).catch(error=>{if(!control.signal.aborted)setError(error.message);});
  return()=>control.abort();
 },[sessionId,connected,api,busy,uploading,params,setError]);

 async function newSession(){
  const session=await api.post<Session>('/conversations',{title:'Session · '+new Date().toLocaleString()});
  setParams({session:session.id});setTurns([]);setAttachments([]);setSelected([]);setLibraryIds([]);setMemoryEnabled(true);retry.current=null;await refresh();return session.id;
 }
 async function submit(replay=false,override?:{session:string;text:string;ids?:string[];library?:string[]}){
  if(!connected||busy||uploading)return;
  const text=override?.text??(replay?retry.current?.input:input.trim());if(!text)return;
  setError('');setBusy(true);setProgress('Processing request…');setEvents([]);const started=performance.now();
  let session=override?.session||sessionId,id=randomId() as string,ids=override?.ids?[...override.ids]:[...selected],libs=override?.library?[...override.library]:[...libraryIds];
  setCognitive(ids.length||libs.length?{phase:'occipital',label:'Reading evidence',detail:'Images, documents, or retrieval context active'}:{phase:'thinking',label:'Thinking',detail:'Reasoning and routing request'});
  try{
   if(replay&&retry.current&&!override){({id,session,ids,library:libs}=retry.current);}else if(!session){session=await newSession();}
   retry.current={id,input:text,session,ids,library:libs};abort.current=new AbortController();
   const pending:Run={request_id:id,conversation_id:session,user_text:text,assistant_text:'',status:'running',created_at:new Date().toISOString(),context:{}};
   setTurns(items=>[...items.filter(run=>run.request_id!==id),pending]);setSelectedRun(pending);
   const result=await api.chat({conversation_id:session,message:text,request_id:id,stream:true,max_tokens:output,execution_mode:mode,attachment_ids:ids,library_document_ids:libs},abort.current.signal,(name,data)=>{
    if(!alive.current)return;const at=(performance.now()-started)/1000;
    setEvents(items=>[...items.slice(-199),{name,at,data:name==='delta'?{characters:String(data.text||'').length}:data}]);
    if(name==='cognitive'){const stage=String(data.stage||'idle');const phase=stage==='reasoning'||stage==='route_started'||stage==='tool'?'thinking':stage==='retrieval'||stage==='vision'?'occipital':stage==='memory_search'||stage==='memory_save'?'memory':stage==='generation'?'responding':'idle';setCognitive({phase,label:stage.replaceAll('_',' '),detail:String(data.detail||'')});}
    if(name==='context'){pending.context=data as Context;setProgress('Context prepared · generating response…');}
    if(name==='tool')setProgress('Running tool…');
    if(name==='delta'){pending.assistant_text+=(data.text as string)||'';setProgress('Generating response…');}
    if(name==='timing')pending.context={...pending.context,...data};
    setTurns(items=>items.map(run=>run.request_id===id?{...pending}:run));setSelectedRun({...pending});
   });
   pending.assistant_text=result.reply;pending.context=result.context;pending.status='complete';
   setCognitive({phase:'idle',label:'Idle',detail:'Response complete'});setTurns(items=>items.map(run=>run.request_id===id?{...pending}:run));setSelectedRun({...pending});setInput('');retry.current=null;setProgress('Saved');
  }catch(error){
   setCognitive({phase:'idle',label:'Idle',detail:'Request stopped'});
   const message=(error as Error).name==='AbortError'?'Canceled locally. Partial output is not a confirmed saved answer.':(error as Error).message;
   setError(message);setProgress('Request not completed');setTurns(items=>items.map(run=>run.request_id===id?{...run,status:'failed'}:run));
  }finally{if(alive.current){setBusy(false);setBrowserSeconds((performance.now()-started)/1000);await refresh();}}
 }
 async function upload(files:File[]){
  if(!files.length||!connected||busy)return;setUploading(true);
  try{const session=sessionId||await newSession();for(const file of files){const attachment=await api.post<ChatAttachment>('/attachments',{conversation_id:session,name:file.name,data_base64:await base64File(file)});setAttachments(items=>[...items,attachment]);setSelected(items=>items.length+libraryIds.length<4?[...items,attachment.id]:items);}setError('');}
  catch(error){setError((error as Error).message);}finally{setUploading(false);}
 }
 function runFiles(run:Run){const raw=(run.context.attachment_ids||[]) as string[];return {ids:raw.filter(id=>!id.startsWith('lib:')),library:raw.filter(id=>id.startsWith('lib:')).map(id=>id.slice(4))};}
 async function saveCase(run=selectedRun){if(!run)return;const title=prompt('Benchmark case title',run.user_text.slice(0,80));if(!title)return;const files=runFiles(run);try{await api.post('/lab/cases',{title,suite:'Custom',input:run.user_text,setup:[],attachment_ids:files.ids,conversation_id:files.ids.length?run.conversation_id:null,library_document_ids:files.library,expected:'Review answer quality manually.',assertions:[{kind:'manual',value:''}],timeout:180,tags:['saved-from-playground'],intent:'fresh'});await refresh();setProgress('Benchmark case saved');}catch(error){setError((error as Error).message);}}
 async function feedback(run:Run,value:'up'|'down'){try{const next=run.feedback?.value===value?'clear':value;await api.put('/runs/'+run.request_id+'/feedback',{value:next,note:''});setTurns(items=>items.map(item=>item.request_id===run.request_id?{...item,feedback:next==='clear'?null:{value,note:''}}:item));}catch(error){setError((error as Error).message);}}
 async function branchFrom(run:Run,action:'branch'|'edit'|'regenerate'){try{const branch=await api.post<Session>('/conversations/'+run.conversation_id+'/branch',{request_id:run.request_id,include_target:action==='branch'});setParams({session:branch.id});setTurns([]);setAttachments([]);setSelected([]);setLibraryIds([]);if(action==='edit'){setInput(run.user_text);setProgress('Branched before this message. Edit and send.');return;}if(action==='regenerate'){const files=runFiles(run);await submit(false,{session:branch.id,text:run.user_text,ids:files.ids,library:files.library});}else{setProgress('Conversation branch created.');await refresh();}}catch(error){setError((error as Error).message);}}
 async function toggleMemory(){if(!sessionId)return;try{const result=await api.put<{enabled:boolean}>('/conversations/'+sessionId+'/memory',{enabled:!memoryEnabled});setMemoryEnabled(result.enabled);setProgress(result.enabled?'Conversation memory enabled.':'Conversation memory disabled.');}catch(error){setError((error as Error).message);}}
 async function deleteSession(){if(!sessionId)return;await api.remove('/conversations/'+sessionId);setParams({});await refresh();}
 function resize(e:React.PointerEvent){const start=e.clientX,width=panelWidth;e.currentTarget.setPointerCapture(e.pointerId);const move=(event:PointerEvent)=>setPanelWidth(Math.max(280,Math.min(650,width+start-event.clientX)));const up=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);};window.addEventListener('pointermove',move);window.addEventListener('pointerup',up);}
 return {connected,sessions,docs,sessionId,turns,input,setInput,busy,uploading,output,setOutput,mode,setMode,attachments,selected,setSelected,libraryIds,setLibraryIds,selectedRun,setSelectedRun,events,browserSeconds,progress,source,setSource,inspect,setInspect,panelWidth,memoryEnabled,newSession,submit,upload,saveCase,feedback,branchFrom,toggleMemory,deleteSession,resize,setParams,abort};
}
