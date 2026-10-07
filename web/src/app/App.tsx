import {lazy,Suspense,useEffect,useMemo,useState} from 'react';
import {NavLink,Route,Routes,useLocation,useNavigate} from 'react-router-dom';
import {Alert,Button,Drawer,Input,Layout,Menu,Modal,Space,Tag,Typography} from 'antd';
import {BrainCircuit,Database,FileText,FlaskConical,House,ListTree,MessageSquareText,PanelLeft,Search,Settings as SettingsIcon,Wrench} from 'lucide-react';
import {useLab} from './providers/LabProvider';

const Playground=lazy(()=>import('../Playground'));
const BrainSynapsis=lazy(()=>import('../BrainSynapsis'));
const Memory=lazy(()=>import('../Memory'));
const Documents=lazy(()=>import('../Documents'));
const Benchmarks=lazy(()=>import('../Benchmarks'));
const Settings=lazy(()=>import('../Settings'));
const Overview=lazy(()=>import('../Workspace').then(m=>({default:m.Overview})));
const Runs=lazy(()=>import('../Workspace').then(m=>({default:m.Runs})));
const Runtime=lazy(()=>import('../Workspace').then(m=>({default:m.Runtime})));

export const navigation=[
 {path:'/',label:'Home',icon:House},
 {path:'/playground',label:'Chat',icon:MessageSquareText},
 {path:'/brain-synapsis',label:'Brain Synapsis',icon:BrainCircuit},
 {path:'/memory',label:'Memory',icon:Database},
 {path:'/documents',label:'Documents',icon:FileText},
 {path:'/benchmarks',label:'Benchmarks',icon:FlaskConical},
 {path:'/runs',label:'Runs',icon:ListTree},
 {path:'/runtime',label:'Runtime',icon:Wrench},
 {path:'/settings',label:'Settings',icon:SettingsIcon},
] as const;

function initialTheme(){try{return localStorage.getItem('keno.lab.theme')||'system';}catch{return 'system';}}

export default function App(){
 const {connected,status,runs,sessions,docs,error,setError,refresh}=useLab();
 const location=useLocation(),navigate=useNavigate();
 const [collapsed,setCollapsed]=useState(false),[drawer,setDrawer]=useState(false),[command,setCommand]=useState(false),[query,setQuery]=useState(''),[theme,setTheme]=useState(initialTheme);
 const page=navigation.find(item=>item.path===location.pathname)?.label||'Workspace';
 useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)');const apply=()=>document.documentElement.dataset.theme=theme==='system'?(media.matches?'dark':'light'):theme;apply();media.addEventListener('change',apply);try{localStorage.setItem('keno.lab.theme',theme);}catch{}return()=>media.removeEventListener('change',apply);},[theme]);
 useEffect(()=>{const listener=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setCommand(v=>!v);}if(e.key==='Escape'){setCommand(false);setDrawer(false);}};window.addEventListener('keydown',listener);return()=>window.removeEventListener('keydown',listener);},[]);
 useEffect(()=>setDrawer(false),[location.pathname]);
 const commandItems=useMemo(()=>{
  const q=query.trim().toLowerCase(),match=(value:string)=>!q||value.toLowerCase().includes(q);
  return {
   pages:navigation.filter(item=>match(item.label)),
   runs:q?runs.filter(r=>match(r.user_text)||match(r.request_id)).slice(0,5):[],
   sessions:q?sessions.filter(s=>match(s.title)).slice(0,5):[],
   docs:q?docs.filter(d=>match(d.name)).slice(0,5):[],
  };
 },[query,runs,sessions,docs]);
 const go=(path:string)=>{navigate(path);setCommand(false);setQuery('');};
 const menuItems=navigation.map(({path,label,icon:Icon})=>({key:path,icon:<Icon size={16}/>,label:<NavLink end={path==='/'} to={path}>{label}</NavLink>}));
 return <Layout className="min-h-screen bg-zinc-950 text-zinc-50">
  <Layout.Sider width={208} collapsedWidth={64} collapsed={collapsed} trigger={null} theme="dark" className="!fixed inset-y-0 left-0 z-30 hidden border-r border-zinc-800 !bg-zinc-950 lg:block">
   <div className="flex h-full flex-col px-2 py-5">
    <div className="flex items-center gap-3 px-2 pb-5"><div className="grid h-9 w-9 place-items-center rounded-lg border border-zinc-800 bg-zinc-900 text-xl font-semibold">k</div>{!collapsed&&<div><Typography.Text strong className="!text-zinc-100">Keno-B Lab</Typography.Text><div className="text-[10px] text-zinc-500">Local intelligence workspace</div></div>}</div>
    <Menu mode="inline" theme="dark" selectedKeys={[location.pathname]} items={menuItems} className="!border-0 !bg-transparent"/>
    <div className="mt-auto px-3 text-[10px] text-zinc-500">{!collapsed&&<><div className="flex items-center gap-2"><span className={'h-1.5 w-1.5 rounded-full '+(connected?'bg-zinc-100':'bg-zinc-600')}/>{connected?'Backend connected':'Disconnected'}</div><div className="mt-1">Self-hosted · CPU inference</div></>}</div>
   </div>
  </Layout.Sider>
  <Drawer placement="left" width={240} open={drawer} onClose={()=>setDrawer(false)} styles={{body:{padding:8,background:'#09090b'}}><Menu mode="inline" theme="dark" selectedKeys={[location.pathname]} items={menuItems}/></Drawer>
  <Layout className={'!bg-zinc-950 transition-[margin] '+(collapsed?'lg:ml-16':'lg:ml-52')}>
   <div className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-zinc-800 bg-zinc-950/95 px-4 backdrop-blur lg:px-6">
    <Space size={8}><Button type="text" icon={<PanelLeft size={18}/>} onClick={()=>window.innerWidth<1024?setDrawer(true):setCollapsed(v=>!v)} aria-label="Toggle navigation"/><Typography.Text type="secondary">Workspace</Typography.Text><span className="text-zinc-600">/</span><Typography.Text strong>{page}</Typography.Text></Space>
    <Space size={8} className="min-w-0"><span className="hidden max-w-64 truncate font-mono text-[10px] text-zinc-500 md:block">{status?.model||'Model unavailable'}</span><Tag color={connected?'default':'warning'}>{connected?'Connected':'Disconnected'}</Tag><Button icon={<Search size={14}/>} onClick={()=>setCommand(true)} className="hidden sm:inline-flex">Search</Button></Space>
   </div>
   {error&&<Alert type="error" showIcon closable message={error} afterClose={()=>setError('')} className="!rounded-none"/>}
   {!connected&&location.pathname!=='/settings'&&<Alert type="warning" showIcon message={<span>Backend disconnected. <Button type="link" size="small" onClick={()=>navigate('/settings')}>Configure connection</Button></span>} className="!rounded-none"/>}
   <Layout.Content className="mx-auto w-full max-w-[1900px] flex-1 p-4 lg:p-6"><Suspense fallback={<div className="grid min-h-52 place-items-center text-zinc-500">Loading workspace…</div>}><Routes>
    <Route path="/" element={<Overview/>}/><Route path="/playground" element={<Playground/>}/><Route path="/brain-synapsis" element={<BrainSynapsis/>}/><Route path="/memory" element={<Memory/>}/><Route path="/documents" element={<Documents/>}/><Route path="/benchmarks" element={<Benchmarks/>}/><Route path="/runs" element={<Runs/>}/><Route path="/runtime" element={<Runtime/>}/><Route path="/settings" element={<Settings theme={theme} setTheme={setTheme}/>}/><Route path="*" element={<Overview/>}/>
   </Routes></Suspense></Layout.Content>
   <Layout.Footer className="!flex !justify-between !gap-4 !border-t !border-zinc-800 !bg-zinc-950 !px-6 !py-3 !text-[10px] !text-zinc-500"><span>Keno-B Lab · {status?.version||'Version unavailable'}</span><span className="hidden sm:block">No external inference, scripts or analytics · <Button type="link" size="small" disabled={!connected} onClick={()=>void refresh()}>Refresh data</Button></span></Layout.Footer>
  </Layout>
  <Modal title="Search workspace" open={command} onCancel={()=>setCommand(false)} footer={null} destroyOnClose>
   <Input autoFocus prefix={<Search size={15}/>} placeholder="Search pages, runs, sessions or documents…" value={query} onChange={e=>setQuery(e.target.value)}/>
   <div className="mt-4 max-h-[55vh] space-y-4 overflow-y-auto">
    <CommandGroup title="Navigation" items={commandItems.pages.map(item=>({key:item.path,label:item.label,onClick:()=>go(item.path)}))}/>
    {query&&<><CommandGroup title="Runs" items={commandItems.runs.map(item=>({key:item.request_id,label:item.user_text.slice(0,90),onClick:()=>go('/runs?request='+encodeURIComponent(item.request_id))}))}/><CommandGroup title="Sessions" items={commandItems.sessions.map(item=>({key:item.id,label:item.title,onClick:()=>go('/playground?session='+item.id)}))}/><CommandGroup title="Documents" items={commandItems.docs.map(item=>({key:item.id,label:item.name,onClick:()=>go('/playground?doc='+item.id)}))}/></>}
   </div>
  </Modal>
 </Layout>;
}
function CommandGroup({title,items}:{title:string;items:Array<{key:string;label:string;onClick:()=>void}>}){if(!items.length)return null;return <div><div className="mb-1 text-[10px] font-medium uppercase tracking-[.18em] text-zinc-500">{title}</div><div className="space-y-1">{items.map(item=><Button key={item.key} type="text" block className="!justify-start" onClick={item.onClick}>{item.label}</Button>)}</div></div>;}
