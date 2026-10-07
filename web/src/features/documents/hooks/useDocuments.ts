import {useEffect,useState} from 'react';
import {useLab} from '../../../app/providers/LabProvider';
import {base64File} from '../../../shared/api/client';
import type {Doc,Source} from '../../../shared/types';

export interface FolderItem {path:string;documents:number;depth:number}
export interface RetrievalStats {seconds:number;candidate_count:number;ranked_count:number;returned:number;match_strength:number;confidence:number;confidence_kind:string;top_rerank_score?:number|null;top_cosine_similarity?:number|null;top_keyword_matches?:number}
export interface Evidence {excerpts:Source[];coverage:unknown;mode:string;retrieval?:RetrievalStats}
export interface DocumentAnswer {reply:string;sources:Source[];seconds:number;citations_present:boolean;truncated:boolean;mode?:string;retrieval?:RetrievalStats}

export function useDocuments(){
 const {api,connected,docs,library,refresh,setError}=useLab();
 const [selected,setSelected]=useState<string[]>([]),[embed,setEmbed]=useState(true),[replace,setReplace]=useState('');
 const [collection,setCollection]=useState('General'),[folder,setFolder]=useState(''),[tags,setTags]=useState('');
 const [collections,setCollections]=useState<Array<{name:string;documents:number}>>([]),[folders,setFolders]=useState<FolderItem[]>([]);
 const [selectedCollection,setSelectedCollection]=useState(''),[selectedFolder,setSelectedFolder]=useState('');
 const [question,setQuestion]=useState(''),[mode,setMode]=useState('hybrid'),[busy,setBusy]=useState(false),[progress,setProgress]=useState('');
 const [detail,setDetail]=useState<Doc|null>(null),[versions,setVersions]=useState<Doc[]>([]);
 const [evidence,setEvidence]=useState<Evidence|null>(null),[answer,setAnswer]=useState<DocumentAnswer|null>(null),[source,setSource]=useState<Source|null>(null);

 async function loadTaxonomy(){if(!connected)return;try{const [c,f]=await Promise.all([api.get<{collections:Array<{name:string;documents:number}>}>('/library/collections'),api.get<{folders:FolderItem[]}>('/library/folders')]);setCollections(c.collections);setFolders(f.folders);}catch{setCollections([]);setFolders([]);}}
 useEffect(()=>{void loadTaxonomy();},[connected,api,docs.length]);

 async function upload(file:File){setBusy(true);setProgress('Importing, extracting and indexing…');setError('');try{const result=await api.post<Doc&{duplicate?:boolean}>('/library/documents',{name:file.name,data_base64:await base64File(file),embed,replace_id:replace||null,force:false,collection:collection.trim()||'General',folder:folder.trim(),tags:tags.split(',').map(v=>v.trim()).filter(Boolean).slice(0,10),metadata:{}});setProgress(result.duplicate?'Already imported.':'Encrypted, indexed and versioned.');await refresh();await loadTaxonomy();}catch(error){setProgress('Import failed');setError((error as Error).message);}finally{setBusy(false);}}
 async function query(ask=false){if(!question.trim())return;setBusy(true);setError('');setProgress(ask?'Processing document question…':'Retrieving local evidence…');const payload={question,document_ids:selected,collections:selectedCollection?[selectedCollection]:[],folders:selectedFolder?[selectedFolder]:[],mode,max_tokens:512};try{if(ask){setAnswer(await api.post('/library/ask',payload));setEvidence(null);}else{setEvidence(await api.post('/library/search',payload));setAnswer(null);}setProgress('Complete');}catch(error){setProgress('Request failed');setError((error as Error).message);}finally{setBusy(false);}}
 async function download(doc:Doc,version?:number){try{const path=version?'/library/documents/'+doc.id+'/versions/'+version+'/download':'/library/documents/'+doc.id+'/download';const response=await api.fetch(path);const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download=version?'v'+version+'-'+doc.name:doc.name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){setError((error as Error).message);}}
 async function openDetail(doc:Doc){setDetail(doc);setVersions([]);try{setVersions(await api.get<Doc[]>('/library/documents/'+doc.id+'/versions'));}catch(error){setError((error as Error).message);}}
 async function restoreVersion(doc:Doc,version:number){setBusy(true);setProgress('Restoring historical version…');try{const restored=await api.post<Doc>('/library/documents/'+doc.id+'/versions/'+version+'/restore',{});setDetail(restored);setVersions(await api.get<Doc[]>('/library/documents/'+doc.id+'/versions'));await refresh();setProgress('Restored as version '+restored.version+'.');}catch(error){setError((error as Error).message);setProgress('Restore failed');}finally{setBusy(false);}}
 async function reindex(doc:Doc){setBusy(true);setProgress('Re-indexing…');try{await api.post('/library/documents/'+doc.id+'/reindex',{});await refresh();setProgress('Re-indexed as a new version.');}catch(error){setError((error as Error).message);}finally{setBusy(false);}}
 async function remove(doc:Doc){try{await api.remove('/library/documents/'+doc.id);setSelected(items=>items.filter(id=>id!==doc.id));await refresh();}catch(error){setError((error as Error).message);}}
 return {connected,docs,library,selected,setSelected,embed,setEmbed,replace,setReplace,collection,setCollection,folder,setFolder,tags,setTags,collections,folders,selectedCollection,setSelectedCollection,selectedFolder,setSelectedFolder,question,setQuestion,mode,setMode,busy,progress,detail,setDetail,versions,evidence,answer,source,setSource,refresh,upload,query,download,openDetail,restoreVersion,reindex,remove};
}
