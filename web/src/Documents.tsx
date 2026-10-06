import {useEffect,useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {Upload,Search,MessageSquare,Trash2,Download,FileText,History,RotateCcw} from 'lucide-react';
import {useLab} from './store';
import {base64File} from './api';
import {Button,Empty,Json,Markdown,SourcePreview} from './components';
import {display,seconds} from './metrics.mjs';
import type {Doc,Source} from './types';

interface FolderItem {path:string;documents:number;depth:number}
interface RetrievalStats {seconds:number;candidate_count:number;ranked_count:number;returned:number;match_strength:number;confidence:number;confidence_kind:string;top_rerank_score?:number|null;top_cosine_similarity?:number|null;top_keyword_matches?:number}

export default function Documents(){
 const {api,connected,docs,library,refresh,setError}=useLab(),navigate=useNavigate();
 const [selected,setSelected]=useState<string[]>([]),[embed,setEmbed]=useState(true),[replace,setReplace]=useState('');
 const [collection,setCollection]=useState('General'),[folder,setFolder]=useState(''),[tags,setTags]=useState('');
 const [collections,setCollections]=useState<Array<{name:string;documents:number}>>([]),[folders,setFolders]=useState<FolderItem[]>([]);
 const [selectedCollection,setSelectedCollection]=useState(''),[selectedFolder,setSelectedFolder]=useState('');
 const [question,setQuestion]=useState(''),[mode,setMode]=useState('hybrid'),[busy,setBusy]=useState(false),[progress,setProgress]=useState('');
 const [detail,setDetail]=useState<Doc|null>(null),[versions,setVersions]=useState<Doc[]>([]);
 const [evidence,setEvidence]=useState<{excerpts:Source[];coverage:unknown;mode:string;retrieval:RetrievalStats}|null>(null);
 const [answer,setAnswer]=useState<{reply:string;sources:Source[];seconds:number;citations_present:boolean;truncated:boolean;mode?:string;retrieval?:RetrievalStats}|null>(null),[source,setSource]=useState<Source|null>(null);

 async function loadTaxonomy(){
  if(!connected)return;
  try{
   const [c,f]=await Promise.all([
    api.get<{collections:Array<{name:string;documents:number}>}>('/library/collections'),
    api.get<{folders:FolderItem[]}>('/library/folders'),
   ]);
   setCollections(c.collections);setFolders(f.folders);
  }catch{setCollections([]);setFolders([]);}
 }
 useEffect(()=>{void loadTaxonomy();},[connected,api,docs.length]);

 async function upload(file:File|undefined){
  if(!file)return;setBusy(true);setProgress('Importing, extracting and indexing…');setError('');
  try{
   const result=await api.post<Doc&{duplicate?:boolean}>('/library/documents',{
    name:file.name,data_base64:await base64File(file),embed,replace_id:replace||null,force:false,
    collection:collection.trim()||'General',folder:folder.trim(),tags:tags.split(',').map(v=>v.trim()).filter(Boolean).slice(0,10),metadata:{}
   });
   setProgress(result.duplicate?'Already imported.':'Encrypted, indexed and versioned.');
   await refresh();await loadTaxonomy();
  }catch(e){setProgress('Import failed');setError((e as Error).message);}finally{setBusy(false);}
 }

 async function query(ask=false){
  if(!question.trim())return;setBusy(true);setError('');setProgress(ask?'Processing document question…':'Retrieving local evidence…');
  const payload={question,document_ids:selected,collections:selectedCollection?[selectedCollection]:[],folders:selectedFolder?[selectedFolder]:[],mode,max_tokens:512};
  try{
   if(ask){setAnswer(await api.post('/library/ask',payload));}
   else{setEvidence(await api.post('/library/search',payload));setAnswer(null);}
   setProgress('Complete');
  }catch(e){setProgress('Request failed');setError((e as Error).message);}finally{setBusy(false);}
 }

 async function download(d:Doc){
  try{const r=await api.fetch('/library/documents/'+d.id+'/download');const u=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=u;a.download=d.name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
  catch(e){setError((e as Error).message);}
 }

 async function openDetail(d:Doc){
  setDetail(d);setVersions([]);
  try{setVersions(await api.get<Doc[]>('/library/documents/'+d.id+'/versions'));}catch(e){setError((e as Error).message);}
 }

 async function downloadVersion(d:Doc,version:number){
  try{const r=await api.fetch('/library/documents/'+d.id+'/versions/'+version+'/download');const u=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=u;a.download='v'+version+'-'+d.name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
  catch(e){setError((e as Error).message);}
 }

 async function restoreVersion(d:Doc,version:number){
  if(!confirm('Restore version '+version+' as a new current version?'))return;
  setBusy(true);setProgress('Restoring historical version…');
  try{
   const restored=await api.post<Doc>('/library/documents/'+d.id+'/versions/'+version+'/restore',{});
   setDetail(restored);setVersions(await api.get<Doc[]>('/library/documents/'+d.id+'/versions'));
   await refresh();setProgress('Restored as version '+restored.version+'.');
  }catch(e){setError((e as Error).message);setProgress('Restore failed');}finally{setBusy(false);}
 }

 const folderLabel=(item:FolderItem)=>'· '.repeat(Math.max(0,item.depth-1))+item.path+' · '+item.documents;

 return <><div className="page-heading"><div><h1>Documents</h1><p>Encrypted originals, folder hierarchy, version history and local hybrid retrieval.</p></div><Button onClick={()=>void refresh()} disabled={!connected||busy}>Refresh</Button></div>
 <div className="status-banner"><span className={'status-dot '+(library?.ready?'complete':'failed')}/><strong>{library?.ready?'Automatic encryption ready':'Document pipeline unavailable'}</strong><span>{library?.detail||library?.encryption||'Connect to inspect configuration.'}</span></div>
 <div className="document-layout"><section>
  <div className="panel import-panel"><div><h2>Import document</h2><small>{library?.formats?.join(' · ')||'Supported formats unavailable until connected.'}</small></div><div className="actions wrap">
   <label className="upload-button button primary"><Upload size={15}/>Choose file<input type="file" disabled={!connected||!library?.ready||busy} accept={library?.formats?.join(',')} onChange={e=>{void upload(e.target.files?.[0]);e.target.value='';}}/></label>
   <label className="check"><input type="checkbox" checked={embed} onChange={e=>setEmbed(e.target.checked)}/>Build embeddings</label>
   <input aria-label="Document collection" value={collection} onChange={e=>setCollection(e.target.value)} placeholder="Collection"/>
   <input aria-label="Document folder" value={folder} onChange={e=>setFolder(e.target.value)} placeholder="Folder, e.g. Projects/Keno"/>
   <input aria-label="Document tags" value={tags} onChange={e=>setTags(e.target.value)} placeholder="tags, comma, separated"/>
   <select value={replace} onChange={e=>setReplace(e.target.value)}><option value="">Import new document</option>{docs.map(d=><option key={d.id} value={d.id}>Replace as next version · {d.name}</option>)}</select>
  </div><p className="muted small">Folder paths support up to six levels. Replacing a document keeps encrypted historical versions that can be inspected, downloaded or restored.</p><small aria-live="polite">{progress}</small></div>
  <div className="panel table-panel"><div className="section-heading"><h2>Library</h2><span className="muted">{docs.length} documents</span></div>{!docs.length?<Empty title="No documents yet">Import a supported file to test retrieval.</Empty>:<div className="table-scroll"><table><thead><tr><th>Select</th><th>Document</th><th>Classification</th><th>Index</th><th>Actions</th></tr></thead><tbody>{docs.map(d=><tr key={d.id}>
   <td><input type="checkbox" aria-label={'Select '+d.name} checked={selected.includes(d.id)} onChange={e=>setSelected(old=>e.target.checked?[...old,d.id].slice(0,10):old.filter(id=>id!==d.id))}/></td>
   <td><button className="text-button" onClick={()=>void openDetail(d)}>{d.name}</button><small>{d.format.toUpperCase()} · v{d.version} · {d.collection||'General'}{d.folder?' · '+d.folder:''} · {(d.tags||[]).join(', ')||'no tags'} · {d.source_bytes===null||d.source_bytes===undefined?'Size unavailable':(d.source_bytes/1024).toFixed(1)+' KB'}</small></td>
   <td>{d.category}<small>{d.topic}</small></td><td>{d.passages} passages<small>{d.embedding_model?'Embedded':'Keyword only'} · encrypted</small></td>
   <td><div className="actions"><Button ariaLabel="Ask about document" onClick={()=>navigate('/playground?doc='+d.id)}><MessageSquare size={14}/></Button><Button ariaLabel="Download document" onClick={()=>void download(d)}><Download size={14}/></Button><Button ariaLabel="Re-index document" disabled={busy} onClick={()=>{setBusy(true);setProgress('Re-indexing…');void api.post('/library/documents/'+d.id+'/reindex',{}).then(()=>refresh()).then(()=>setProgress('Re-indexed as a new version.')).catch(e=>setError(e.message)).finally(()=>setBusy(false));}}><Search size={14}/></Button><Button ariaLabel="Delete document" disabled={busy} onClick={()=>{if(confirm('Delete '+d.name+' and its encrypted version history? Backups may retain copies.'))void api.remove('/library/documents/'+d.id).then(()=>{setSelected(old=>old.filter(id=>id!==d.id));return refresh();}).catch(e=>setError(e.message));}}><Trash2 size={14}/></Button></div></td>
  </tr>)}</tbody></table></div>}</div>
  {detail&&<section className="panel"><div className="section-heading"><div><h2>{detail.name}</h2><p className="muted small">{detail.folder||'Root folder'} · {detail.collection||'General'} · current v{detail.version}</p></div><Button onClick={()=>{setDetail(null);setVersions([]);}}>Close</Button></div>
   <div className="metric-grid"><div>Sections <strong>{display(detail.section_count)}</strong></div><div>Indexing time <strong>{seconds(detail.indexing_seconds)}</strong></div><div>Versions <strong>{versions.length||1}</strong></div></div>
   <p className="muted">{detail.classification}</p>{detail.warnings.map((w,i)=><p className="warning" key={i}>{w}</p>)}
   <div className="actions"><Button onClick={()=>setSource({document_id:detail.id,name:detail.name,index:0})}><FileText size={14}/>First passage</Button></div>
   <h3><History size={14}/> Version history</h3>{versions.length?<div className="version-list">{versions.map(v=><div className="version-row" key={v.version}><div><strong>v{v.version}{v.current?' · current':''}</strong><small>{v.archived_at||v.imported_at||'Timestamp unavailable'} · {v.embedding_model?'embedded':'keyword only'}{v.folder?' · '+v.folder:''}</small></div><div className="actions"><Button ariaLabel={'Download version '+v.version} onClick={()=>void downloadVersion(detail,v.version)}><Download size={13}/></Button>{!v.current&&<Button ariaLabel={'Restore version '+v.version} disabled={busy} onClick={()=>void restoreVersion(detail,v.version)}><RotateCcw size={13}/>Restore</Button>}</div></div>)}</div>:<p className="muted small">Loading version history…</p>}
   <details><summary>Document metadata</summary><Json value={detail}/></details>
  </section>}
 </section>
 <section className="panel retrieval"><h2>Retrieval inspector</h2><p className="muted small">{selected.length?selected.length+' selected documents':'Search all imported documents'}</p><textarea value={question} onChange={e=>setQuestion(e.target.value)} placeholder="What should we look for?" maxLength={2000}/>
  <div className="actions wrap"><select aria-label="Collection filter" value={selectedCollection} onChange={e=>setSelectedCollection(e.target.value)}><option value="">All collections</option>{collections.map(c=><option key={c.name} value={c.name}>{c.name} · {c.documents}</option>)}</select>
   <select aria-label="Folder filter" value={selectedFolder} onChange={e=>setSelectedFolder(e.target.value)}><option value="">All folders</option>{folders.map(f=><option key={f.path} value={f.path}>{folderLabel(f)}</option>)}</select>
   <select value={mode} onChange={e=>setMode(e.target.value)}><option value="hybrid">Semantic + keyword (auto fallback)</option><option value="keyword">Keyword only</option></select><Button onClick={()=>void query()} disabled={!connected||busy||!question.trim()}><Search size={14}/>Retrieve</Button><Button onClick={()=>void query(true)} disabled={!connected||busy||!question.trim()}>Ask</Button>
  </div>
  {evidence&&<><p className="muted small">Mode: {evidence.mode}. Hybrid uses semantic + keyword evidence when embeddings are available, then reranks exact/lexical matches; it falls back to keyword when embeddings are unavailable.</p><div className="retrieval-diagnostics"><span>{seconds(evidence.retrieval.seconds)} retrieval</span><span>{Math.round(evidence.retrieval.match_strength*100)}% match strength</span><span>{evidence.retrieval.candidate_count} candidates</span><span>{evidence.retrieval.returned} returned</span></div>{evidence.excerpts.map((s,i)=><article className="passage" key={i}><button className="text-button" onClick={()=>setSource(s)}>[{s.source_id}] {s.name}</button><small>{s.locator} · rank {display(s.rank)}{s.folder?' · '+String(s.folder):''}</small><div className="score-row"><span>Keyword {display(s.keyword_matches)}</span><span>Cosine {display(s.cosine_similarity)}</span><span>Rerank {display(s.rerank_score??s.fusion_score)}</span></div><p>{s.text}</p></article>)}<details><summary>Raw retrieval response</summary><Json value={evidence}/></details></>}
  {answer&&<><Markdown text={answer.reply} sources={answer.sources} onSource={setSource}/>{answer.retrieval&&<div className="retrieval-diagnostics"><span>{seconds(answer.retrieval.seconds)} retrieval</span><span>{Math.round(answer.retrieval.match_strength*100)}% match strength</span><span>{answer.retrieval.candidate_count} candidates</span></div>}<p className="muted small">{seconds(answer.seconds)} total · {answer.citations_present?'Citation markers supplied':'No recognized citation markers'} · {answer.truncated?'Output truncated · ':''}not saved to chat history</p>{answer.sources.map((s,i)=><button className="source-link" key={i} onClick={()=>setSource(s)}>[{s.source_id}] {s.name} · {s.locator}</button>)}</>}
 </section></div>{source&&<SourcePreview source={source} onClose={()=>setSource(null)}/>}</>;
}
