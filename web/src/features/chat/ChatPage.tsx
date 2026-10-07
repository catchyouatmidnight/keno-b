import {Button,Drawer,Grid,Typography} from '../../shared/ui';
import {ChevronRight,Plus} from 'lucide-react';
import {Inspector,SourcePreview} from '../../components';
import {useLab} from '../../app/providers/LabProvider';
import {ChatComposer} from './components/ChatComposer';
import {ChatMessages} from './components/ChatMessages';
import {ChatToolbar} from './components/ChatToolbar';
import {useChat} from './hooks/useChat';

export default function ChatPage(){
 const chat=useChat(),{setError}=useLab(),screens=Grid.useBreakpoint();
 const desktopInspector=chat.inspect&&!!screens.xl;
 const mobileInspector=chat.inspect&&screens.xl===false;
 return <div>
  <div className="mb-6 flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><Typography.Title level={2} className="!mb-1">Chat</Typography.Title><Typography.Text type="secondary">Real conversations. Observable decisions.</Typography.Text></div><div className="flex flex-wrap gap-2"><Button icon={<Plus size={15}/>} onClick={()=>void chat.newSession().catch(error=>setError(error.message))} disabled={!chat.connected||chat.busy}>New session</Button><Button icon={<ChevronRight size={15}/>} onClick={()=>chat.setInspect(!chat.inspect)}>{chat.inspect?'Hide inspector':'Inspect'}</Button></div></div>
  <div className="grid grid-cols-1 items-stretch gap-2 xl:grid-cols-[minmax(0,1fr)_4px_auto]">
   <div className="flex h-[calc(100dvh-212px)] min-h-[520px] min-w-0 flex-col overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/70">
    <ChatToolbar sessionId={chat.sessionId} sessions={chat.sessions} busy={chat.busy} memoryEnabled={chat.memoryEnabled} mode={chat.mode} setMode={chat.setMode} output={chat.output} setOutput={chat.setOutput} onSession={id=>chat.setParams({session:id})} onNew={()=>void chat.newSession().catch(error=>setError(error.message))} onClear={()=>chat.setTurns([])} onMemory={()=>void chat.toggleMemory()} onSaveCase={()=>void chat.saveCase()} onDelete={()=>void chat.deleteSession().catch(error=>setError(error.message))}/>
    <ChatMessages turns={chat.turns} selectedRun={chat.selectedRun} onSelect={chat.setSelectedRun} onSource={chat.setSource} onFeedback={(run,value)=>void chat.feedback(run,value)} onBranch={(run,action)=>void chat.branchFrom(run,action)} onSaveCase={run=>void chat.saveCase(run)} onInspect={run=>{chat.setSelectedRun(run);chat.setInspect(true);}} progress={chat.progress}/>
    <ChatComposer connected={chat.connected} busy={chat.busy} uploading={chat.uploading} input={chat.input} setInput={chat.setInput} attachments={chat.attachments} selected={chat.selected} setSelected={chat.setSelected} libraryIds={chat.libraryIds} setLibraryIds={chat.setLibraryIds} docs={chat.docs} upload={chat.upload} submit={chat.submit} cancel={()=>chat.abort.current?.abort()} progress={chat.progress} setError={setError}/>
   </div>
   {desktopInspector&&<><div className="hidden cursor-col-resize rounded-full hover:bg-zinc-800 xl:block" onPointerDown={chat.resize}/><div data-testid="desktop-inspector" className="hidden h-[calc(100dvh-212px)] min-h-[520px] overflow-hidden xl:block" style={{width:chat.panelWidth}}><Inspector context={chat.selectedRun?.context||{}} events={chat.events} raw={chat.selectedRun||undefined} browserSeconds={chat.browserSeconds} onSource={chat.setSource}/></div></>}
  </div>
  <Drawer title="Inspector" placement="right" width="min(92vw, 420px)" open={mobileInspector} onClose={()=>chat.setInspect(false)} styles={{body:{padding:8,background:'#09090b'}}}><Inspector context={chat.selectedRun?.context||{}} events={chat.events} raw={chat.selectedRun||undefined} browserSeconds={chat.browserSeconds} onSource={chat.setSource}/></Drawer>
  {chat.source&&<SourcePreview source={chat.source} onClose={()=>chat.setSource(null)}/>}
 </div>;
}
