import {useEffect,useState} from 'react';
import {useLab} from '../../../app/providers/LabProvider';

export interface MemoryRow {key:string;content:string;category:string;pinned:boolean;importance:number;confidence:number;retrieval_count:number;last_reason:string;history_count?:number;updated_at?:string}
export interface MemoryHistory {id:number;memory_key:string;content:string;category:string;importance:number;confidence:number;replaced_at:string;replacement_request_id?:string|null;reason:string}
export const blankMemory:MemoryRow={key:'',content:'',category:'fact',pinned:false,importance:.5,confidence:.8,retrieval_count:0,last_reason:'',history_count:0};

export function useMemory(){
 const {api,connected,setError}=useLab();
 const [query,setQuery]=useState(''),[items,setItems]=useState<MemoryRow[]>([]),[edit,setEdit]=useState<MemoryRow>(blankMemory),[duplicates,setDuplicates]=useState<Array<{keys:string[];similarity:number;preview:string[]}>>([]),[history,setHistory]=useState<MemoryHistory[]>([]),[busy,setBusy]=useState(false),[saved,setSaved]=useState('');
 async function load(q=query){if(!connected)return;try{setItems(await api.get<MemoryRow[]>('/memories?q='+encodeURIComponent(q)));}catch(error){setError((error as Error).message);}}
 async function open(memory:MemoryRow){setEdit({...memory});setSaved('');try{setHistory(await api.get<MemoryHistory[]>('/memory-history/'+encodeURIComponent(memory.key)));}catch(error){setHistory([]);setError((error as Error).message);}}
 useEffect(()=>{void load('');},[connected,api]);
 async function save(){if(!edit.key.trim()||!edit.content.trim())return;setBusy(true);try{const result=await api.put<MemoryRow&{superseded_previous?:boolean}>('/memories/'+encodeURIComponent(edit.key),{key:edit.key,content:edit.content,category:edit.category,pinned:edit.pinned,importance:edit.importance,confidence:edit.confidence,source_conversation_id:null,expires_at:null});setEdit(blankMemory);setHistory([]);setSaved(result.superseded_previous?'Memory updated. Previous value preserved in correction history.':'Memory saved.');await load();}catch(error){setError((error as Error).message);}finally{setBusy(false);}}
 async function remove(key:string){setBusy(true);try{await api.remove('/memories/'+encodeURIComponent(key));if(edit.key===key){setEdit(blankMemory);setHistory([]);}await load();}catch(error){setError((error as Error).message);}finally{setBusy(false);}}
 async function findDuplicates(){setBusy(true);try{setDuplicates(await api.get('/memories/duplicates'));}catch(error){setError((error as Error).message);}finally{setBusy(false);}}
 async function merge(keys:string[]){setBusy(true);try{await api.post('/memories/merge',{keys,target_key:keys[0]});setDuplicates(items=>items.filter(item=>item.keys.join('|')!==keys.join('|')));await load();}catch(error){setError((error as Error).message);}finally{setBusy(false);}}
 return {connected,query,setQuery,items,edit,setEdit,duplicates,history,busy,saved,load,open,save,remove,findDuplicates,merge,clear:()=>{setEdit(blankMemory);setHistory([]);}};
}
