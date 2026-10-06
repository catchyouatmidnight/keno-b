import {Activity,BrainCircuit,Database,Eye,MessageSquareText} from 'lucide-react';
import {useLab,type CognitivePhase} from './store';

const lobes=[
 {phase:'thinking' as CognitivePhase,name:'Parietal Lobe',subtitle:'Thinking / Reasoning',detail:'Processes information, makes connections, and reasons through complex problems.',Icon:BrainCircuit},
 {phase:'occipital' as CognitivePhase,name:'Occipital Lobe',subtitle:'Images / Documents / Retrievals',detail:'Handles visual understanding, document analysis, and information retrieval.',Icon:Eye},
 {phase:'responding' as CognitivePhase,name:'Frontal Lobe',subtitle:'Responding',detail:'Plans, organizes, and generates responses.',Icon:MessageSquareText},
 {phase:'memory' as CognitivePhase,name:'Temporal Lobe',subtitle:'Saving / Retrieving Memory',detail:'Stores and retrieves relevant memory context.',Icon:Database},
];

const nodes=[[18,34],[23,26],[29,22],[35,27],[40,36],[33,43],[24,47],[18,53],[27,57],[36,54],[44,49],[48,39],[46,25],[54,21],[61,24],[68,29],[72,38],[65,42],[57,36],[53,31],[77,43],[79,52],[73,57],[65,53],[38,60],[46,57],[54,60],[61,65],[55,71],[46,72],[36,68],[29,63],[67,64],[74,66],[72,73],[65,75]];

function BrainMap({active}:{active:CognitivePhase}){
 return <div className={'synapse-brain phase-'+active}>
  <svg className="synapse-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
   {nodes.slice(0,28).map((n,i)=>{const b=nodes[(i*7+9)%nodes.length];return <line key={i} x1={n[0]} y1={n[1]} x2={b[0]} y2={b[1]}/>})}
  </svg>
  <div className="brain-haze"/>
  {nodes.map((n,i)=><span key={i} className="synapse-node" style={{left:n[0]+'%',top:n[1]+'%'}}/>)}
  <div className={'lobe-zone frontal '+(active==='responding'?'active':'')}><span>FRONTAL<br/>LOBE</span></div>
  <div className={'lobe-zone parietal '+(active==='thinking'?'active':'')}><span>PARIETAL<br/>LOBE</span></div>
  <div className={'lobe-zone occipital '+(active==='occipital'?'active':'')}><span>OCCIPITAL<br/>LOBE</span></div>
  <div className={'lobe-zone temporal '+(active==='memory'?'active':'')}><span>TEMPORAL<br/>LOBE</span></div>
  {active!=='idle'&&<><span className={'pulse-ring '+active}/><span className={'pulse-ring delay '+active}/>{[0,1,2,3,4].map(i=><i key={i} className={'signal-particle p'+i+' '+active}/>)}</>}
 </div>;
}

export default function BrainSynapsis(){
 const {cognitive,status}=useLab();
 const stale=Date.now()-cognitive.updated_at>120000;
 const phase:CognitivePhase=status?.generating&&stale?'thinking':stale?'idle':cognitive.phase;
 const current=lobes.find(l=>l.phase===phase);
 return <div className="brain-page"><div className="brain-layout">
  <section className="brain-hero">
   <div className="brain-kicker">COGNITIVE ENGINE</div>
   <div className="brain-heading"><div><h1>Brain Synapsis</h1><p>Live cognitive activity map</p></div><div className={'brain-state '+(phase!=='idle'?'active':'')}><Activity size={16}/><div><strong>{phase==='idle'?'Idle':cognitive.label}</strong><small>{current?current.name+' Active':'No active region'}</small></div></div></div>
   <BrainMap active={phase}/>
  </section>
  <aside className="brain-regions">
   <div className="brain-regions-title"><Activity size={16}/><div><h2>BRAIN REGIONS & AGENT STATES</h2><p>Each region reflects a different part of Keno-B's active pipeline.</p></div></div>
   {lobes.map(({phase:p,name,subtitle,detail,Icon})=><article key={p} className={'brain-region-card '+(phase===p?'active':'')}><div className="region-icon"><Icon size={28}/></div><div><div className="region-card-head"><h3>{name}</h3><span><b/> {phase===p?'ACTIVE':'INACTIVE'}</span></div><strong>{subtitle}</strong><p>{detail}</p></div></article>)}
  </aside>
 </div><p className="brain-note">Open Brain Synapsis in a second tab while using Chat to watch the regions change live.</p></div>;
}