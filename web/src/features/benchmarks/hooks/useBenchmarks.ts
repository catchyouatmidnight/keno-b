import {useEffect,useRef,useState} from 'react';
import {useLab} from '../../../app/providers/LabProvider';
import {randomId} from '../../../id.mjs';
import {checksFor,number,percentile} from '../../../metrics.mjs';
import {seeds} from '../../../seeds';
import {preferences} from '../../../preferences.mjs';
import type {Case,Check,Result,Session,ChatResult} from '../../../shared/types';

export const freshCase={title:'',suite:'Custom',input:'',setup:[],attachment_ids:[],library_document_ids:[],expected:'',assertions:[{kind:'manual',value:''}],timeout:preferences().timeout,tags:[],intent:'fresh'};
export function verdict(result:Result){const tested=result.checks.filter(check=>check.passed!==null);if(result.status!=='complete')return false;if(!tested.length)return null;return tested.every(check=>check.passed);}

export function useBenchmarks(){
 const lab=useLab(),[chosen,setChosen]=useState<string[]>([]),[repetitions,setRepetitions]=useState(preferences().repetitions),[busy,setBusy]=useState(false),[progress,setProgress]=useState(''),[editor,setEditor]=useState(JSON.stringify(freshCase,null,2)),[fixture,setFixture]=useState<string[]>([]),[showEditor,setShowEditor]=useState(false),[batch,setBatch]=useState(''),[baseline,setBaseline]=useState(''),[benchmarkMode,setBenchmarkMode]=useState<'fast'|'balanced'|'deep'>('balanced');
 const control=useRef<AbortController|null>(null),canceled=useRef(false),alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;canceled.current=true;control.current?.abort();};},[]);
 async function seed(){setBusy(true);try{for(const test of seeds)if(!lab.cases.some(item=>item.title===test.title&&item.suite===test.suite))await lab.api.post('/lab/cases',{...test,library_document_ids:test.tags.includes('requires-document')?fixture:[]});await lab.refresh();}catch(error){lab.setError((error as Error).message);}finally{setBusy(false);}}
 async function save(){try{await lab.api.post('/lab/cases',JSON.parse(editor));await lab.refresh();setShowEditor(false);}catch(error){lab.setError((error as Error).message);}}
 async function remove(id:string){try{await lab.api.remove('/lab/cases/'+id);await lab.refresh();}catch(error){lab.setError((error as Error).message);}}
 async function review(id:string,quality:number){try{const current=lab.results.find(item=>item.id===id);await lab.api.put('/lab/results/'+id+'/review',{quality,note:current?.review?.note||''});await lab.refresh();}catch(error){lab.setError((error as Error).message);}}
 async function run(){
  const tests=lab.cases.filter(item=>chosen.includes(item.id));if(!tests.length)return;setBusy(true);lab.setError('');canceled.current=false;const batchId=randomId();setBatch(batchId);
  try{const snapshot=await lab.api.post<{id:string}>('/lab/snapshots');
   for(const test of tests){let repeatSession='';for(let repetition=1;repetition<=repetitions;repetition++){const started=performance.now();let session=test.attachment_ids.length?test.conversation_id||'':'';let requestId:string|null=null,first:number|null=null,response:ChatResult|undefined,status:'complete'|'failed'|'canceled'='complete',error:string|null=null,checks:Check[]=[];control.current=new AbortController();const timer=setTimeout(()=>control.current?.abort('timeout'),test.timeout*1000);
    try{if(canceled.current){status='canceled';error='Canceled before start';}else{setProgress(`${test.title} · ${repetition}/${repetitions}`);const libs=test.library_document_ids||[];if(test.tags.includes('requires-document')&&!libs.length&&!test.attachment_ids.length)throw Error('Attach a document fixture before running this case.');if(test.tags.includes('requires-multiple-documents')&&libs.length+test.attachment_ids.length<2)throw Error('This case requires two document fixtures.');if(test.intent==='repeat'&&repeatSession)session=repeatSession;if(!session){const created=await lab.api.post<Session>('/conversations',{title:`Benchmark · ${test.title}`},control.current.signal);session=created.id;}if(test.intent==='repeat')repeatSession=session;if(test.intent!=='repeat'||repetition===1){for(const setup of test.setup)await lab.api.chat({conversation_id:session,message:setup,request_id:randomId(),stream:true,max_tokens:256,attachment_ids:test.attachment_ids,library_document_ids:libs,execution_mode:benchmarkMode},control.current.signal,()=>{});}requestId=randomId();response=await lab.api.chat({conversation_id:session,message:test.input,request_id:requestId,stream:true,max_tokens:512,attachment_ids:test.attachment_ids,library_document_ids:libs,execution_mode:benchmarkMode},control.current.signal,name=>{if(name==='delta'&&first===null)first=(performance.now()-started)/1000;});checks=checksFor(test,response.reply,response.context,{first,total:(performance.now()-started)/1000});}}
    catch(e){status=canceled.current?'canceled':'failed';error=(e as Error).name==='AbortError'?'Request aborted or timed out. Partial output is not confirmed saved.':(e as Error).message;}finally{clearTimeout(timer);}
    if(requestId&&!response){try{const sessionData=await lab.api.get<Session>('/conversations/'+session);if(!sessionData.turns?.some(turn=>turn.request_id===requestId))requestId=null;}catch{requestId=null;}}
    await lab.api.post('/lab/results',{batch_id:batchId,case_id:test.id,snapshot_id:snapshot.id,request_id:requestId,conversation_id:session||null,status,checks,browser_seconds:(performance.now()-started)/1000,browser_first_token_seconds:first,error,repetition});await lab.refresh();if(!alive.current)return;
   }}
   setProgress(canceled.current?'Benchmark canceled. Recorded results retained.':'Benchmark completed.');
  }catch(error){lab.setError((error as Error).message);}finally{if(alive.current)setBusy(false);}
 }
 const batches=[...new Set(lab.results.map(result=>result.batch_id))],current=lab.results.filter(result=>!batch||result.batch_id===batch),old=lab.results.filter(result=>baseline&&result.batch_id===baseline),scored=current.filter(result=>verdict(result)!==null),pass=scored.filter(result=>verdict(result)).length;
 const values=(key:string)=>current.map(result=>number(result.run?.context[key])).filter((value):value is number=>value!==null);
 const first=values('first_token_seconds'),total=values('total_seconds'),promptEval=values('prompt_eval_seconds'),generation=values('generation_seconds'),retrieval=values('context_retrieval_seconds').length?values('context_retrieval_seconds'):values('retrieval_seconds'),throughput=values('generation_tokens_per_second'),utilization=values('context_utilization');
 const delta=(metric:'first_token_seconds'|'total_seconds')=>{const a=percentile(current.map(result=>number(result.run?.context[metric])),.5),b=percentile(old.map(result=>number(result.run?.context[metric])),.5);return a!==null&&b!==null?(a-b).toFixed(2)+'s':'Unavailable';};
 const modeStats=['fast','balanced','deep'].map(mode=>{const items=current.filter(result=>result.run?.context.execution_mode===mode);const vals=(key:string)=>items.map(result=>number(result.run?.context[key]));return {mode,runs:items.length,first:percentile(vals('first_token_seconds'),.5),total:percentile(vals('total_seconds'),.5),throughput:percentile(vals('generation_tokens_per_second'),.5)};});
 return {...lab,chosen,setChosen,repetitions,setRepetitions,busy,progress,editor,setEditor,fixture,setFixture,showEditor,setShowEditor,batch,setBatch,baseline,setBaseline,benchmarkMode,setBenchmarkMode,control,canceled,seed,save,remove,review,run,batches,current,old,scored,pass,first,total,promptEval,generation,retrieval,throughput,utilization,modeStats,delta};
}
