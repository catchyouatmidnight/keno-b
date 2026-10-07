import {useEffect,useState} from 'react';
import {useLab} from '../../../app/providers/LabProvider';
import {preferences} from '../../../preferences.mjs';

export interface RuntimeModels {installed:Array<{name:string;bytes:number;quantization:string|null;loaded:boolean;managed:boolean}>;loaded:string;selected?:string;pending:string|null;recommendation:{threads:number;context_size:number;quantization:string;reason:string};activation:string}

export function useSettings(){
 const lab=useLab();
 const [key,setKey]=useState(''),[pending,setPending]=useState(false),[tab,setTab]=useState('Connection');
 const [profile,setProfile]=useState({name:'',background:'',preferences:''}),[identity,setIdentity]=useState({name:'Keno',personality:'',response_examples:''});
 const [tools,setTools]=useState({automatic_memory:true,weather_enabled:false,search_enabled:false}),[labPrefs,setLabPrefs]=useState(preferences),[saved,setSaved]=useState('');
 const [models,setModels]=useState<RuntimeModels|null>(null),[selectedModel,setSelectedModel]=useState(''),[modelUrl,setModelUrl]=useState(''),[modelFilename,setModelFilename]=useState(''),[modelBusy,setModelBusy]=useState(false);
 async function loadModels(){if(!lab.connected)return;try{const data=await lab.api.get<RuntimeModels>('/runtime/models');setModels(data);setSelectedModel(data.pending||data.loaded||data.installed[0]?.name||'');}catch(error){lab.setError((error as Error).message);}}
 useEffect(()=>{if(!lab.connected)return;void Promise.all([lab.api.get<typeof profile>('/profile'),lab.api.get<typeof identity>('/identity'),lab.api.get<typeof tools>('/tools/settings'),lab.api.get<RuntimeModels>('/runtime/models')]).then(([p,i,t,m])=>{setProfile(p);setIdentity(i);setTools(t);setModels(m);setSelectedModel(m.pending||m.loaded||m.installed[0]?.name||'');}).catch(error=>lab.setError(error.message));},[lab.connected,lab.api]);
 async function save(path:string,value:unknown){try{await lab.api.put(path,value);setSaved('Saved on your server.');await lab.refresh();}catch(error){lab.setError((error as Error).message);}}
 async function connect(){if(!key.trim())return;setPending(true);try{await lab.connect(key);setKey('');setSaved('Connected');}catch(error){lab.setError((error as Error).message);}finally{setPending(false);}}
 async function activateModel(){if(!selectedModel)return;setModelBusy(true);setSaved('Switching local model…');try{const result=await lab.api.put<{selected:string;loaded:string;activated:boolean}>('/runtime/model',{name:selectedModel});setSaved(result.activated?'Activated '+result.loaded+'.':'Model selection updated.');await loadModels();await lab.refresh();}catch(error){lab.setError((error as Error).message);setSaved('');}finally{setModelBusy(false);}}
 async function downloadModel(){if(!modelUrl.trim())return;setModelBusy(true);setSaved('Downloading model through the isolated egress service…');try{const result=await lab.api.post<{name:string;bytes:number}>('/runtime/models/download',{url:modelUrl.trim(),filename:modelFilename.trim()||null});setSaved('Installed '+result.name+'. Select it below and stage it for activation.');setModelUrl('');setModelFilename('');await loadModels();}catch(error){lab.setError((error as Error).message);setSaved('');}finally{setModelBusy(false);}}
 function saveLabPrefs(){localStorage.setItem('keno.lab.preferences',JSON.stringify(labPrefs));setSaved('Harmless UI defaults saved in this browser.');}
 async function downloadSchema(){try{const response=await fetch('/openapi.json',{cache:'no-store'});if(!response.ok)throw Error('API schema unavailable');const data=await response.json();const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='keno-openapi.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){lab.setError((error as Error).message);}}
 return {...lab,key,setKey,pending,tab,setTab,profile,setProfile,identity,setIdentity,tools,setTools,labPrefs,setLabPrefs,saved,setSaved,models,selectedModel,setSelectedModel,modelUrl,setModelUrl,modelFilename,setModelFilename,modelBusy,loadModels,save,connectNow:connect,activateModel,downloadModel,saveLabPrefs,downloadSchema};
}
