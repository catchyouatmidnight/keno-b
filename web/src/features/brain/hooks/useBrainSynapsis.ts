import {useEffect,useState} from 'react';
import {useLab,type CognitivePhase} from '../../../app/providers/LabProvider';

function stagePhase(stage:string):CognitivePhase{return stage==='reasoning'||stage==='route_started'||stage==='tool'?'thinking':stage==='retrieval'||stage==='vision'?'occipital':stage==='memory_search'||stage==='memory_save'?'memory':stage==='generation'?'responding':'idle';}

export function useBrainSynapsis(){
 const {cognitive,status,api}=useLab();
 const [live,setLive]=useState<{stage:string;detail:string;intensity:number;duration_seconds?:number;started_at?:string;at?:string;previous?:{stage:string;duration_seconds:number;intensity:number}}|null>(null);
 const [latest,setLatest]=useState<Record<string,unknown>|null>(null);
 const [clock,setClock]=useState(()=>Date.now());
 useEffect(()=>{const control=new AbortController();let buffer='';async function listen(){try{const response=await api.fetch('/cognitive',{signal:control.signal});if(!response.body)return;const reader=response.body.getReader(),decoder=new TextDecoder();while(!control.signal.aborted){const chunk=await reader.read();if(chunk.done)break;buffer+=decoder.decode(chunk.value,{stream:true});for(;;){const end=buffer.indexOf('\n\n');if(end<0)break;const block=buffer.slice(0,end);buffer=buffer.slice(end+2);const type=block.match(/^event:\s*(.+)$/m)?.[1];const raw=block.match(/^data:\s*(.+)$/m)?.[1];if(type==='cognitive'&&raw){try{setLive(JSON.parse(raw));setClock(Date.now());}catch{}}}}}catch(error){if(!control.signal.aborted)console.debug('cognitive stream unavailable',error);}}void listen();return()=>control.abort();},[api]);
 useEffect(()=>{if(!live||live.stage==='idle')return;const timer=setInterval(()=>setClock(Date.now()),250);return()=>clearInterval(timer);},[live?.stage,live?.started_at]);
 useEffect(()=>{if(!status)return;let active=true;void api.get<{items:Array<{context:Record<string,unknown>}>}>('/lab/runs?limit=1&status=complete').then(result=>{if(active)setLatest(result.items[0]?.context||null);}).catch(()=>{});return()=>{active=false;};},[api,status?.generating]);
 const stale=Date.now()-cognitive.updated_at>120000;
 const phase:CognitivePhase=live?stagePhase(live.stage):(status?.generating&&stale?'thinking':stale?'idle':cognitive.phase);
 const started=live?.started_at?Date.parse(live.started_at):NaN;
 const elapsed=phase==='idle'?0:Math.max(live?.duration_seconds||0,Number.isFinite(started)?Math.max(0,(clock-started)/1000):0);
 const visualPulse=phase==='idle'?0:Math.min(1,.45+Math.log1p(elapsed)*.1);
 return {cognitive,status,live,latest,phase,elapsed,visualPulse};
}
