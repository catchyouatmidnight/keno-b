import {type CSSProperties} from 'react';
import {Activity,BrainCircuit,Database,Eye,MessageSquareText} from 'lucide-react';
import type {CognitivePhase} from '../../app/providers/LabProvider';
import {useBrainSynapsis} from './hooks/useBrainSynapsis';

type Point=[number,number,number?];

const lobes=[
 {phase:'thinking' as CognitivePhase,name:'Parietal Lobe',subtitle:'Thinking / Reasoning',detail:'Processes information, makes connections, and reasons through complex problems.',Icon:BrainCircuit},
 {phase:'occipital' as CognitivePhase,name:'Occipital Lobe',subtitle:'Images / Documents / Retrievals',detail:'Handles visual understanding, document analysis, and information retrieval.',Icon:Eye},
 {phase:'responding' as CognitivePhase,name:'Frontal Lobe',subtitle:'Responding',detail:'Plans, organizes, and generates responses.',Icon:MessageSquareText},
 {phase:'memory' as CognitivePhase,name:'Temporal Lobe',subtitle:'Saving / Retrieving Memory',detail:'Stores and retrieves relevant memory context.',Icon:Database},
];

const outlines={
 brain:'M154 314 C111 292 92 249 105 207 C118 168 151 142 195 138 C218 103 258 81 304 85 C342 58 393 56 432 80 C476 55 533 61 571 89 C619 76 674 95 700 135 C742 145 774 181 772 222 C804 253 804 302 779 336 C776 378 741 414 700 426 C675 453 627 461 590 448 C552 470 503 471 467 448 C422 469 365 466 329 440 C284 451 238 438 213 404 C174 397 145 371 142 338 C134 329 141 319 154 314 Z',
 frontal:'M154 314 C111 292 92 249 105 207 C118 168 151 142 195 138 C218 103 258 81 304 85 C337 92 358 113 363 146 C351 178 353 218 366 255 C346 294 316 324 279 344 C231 351 188 339 154 314 Z',
 parietal:'M304 85 C343 58 394 56 432 80 C476 55 533 61 571 89 C615 79 658 92 687 121 C706 149 704 180 687 210 C660 236 621 253 576 256 C531 257 488 245 451 224 C420 205 390 177 363 146 C359 113 337 92 304 85 Z',
 temporal:'M279 344 C315 324 345 293 366 255 C409 244 452 250 486 268 C526 289 551 321 551 356 C548 394 515 429 467 448 C422 469 365 466 329 440 C284 451 238 438 213 404 C221 378 243 357 279 344 Z',
 occipital:'M687 210 C707 183 707 151 687 121 C714 128 740 145 756 167 C772 190 777 211 772 222 C804 253 804 302 779 336 C776 378 741 414 700 426 C672 420 650 404 637 383 C621 354 622 319 639 291 C653 266 670 237 687 210 Z'
} as const;

const points:Record<Exclude<CognitivePhase,'idle'>,Point[]>={
 responding:[[160,234,6],[188,190,4],[222,160,5],[256,127,4],[292,118,5],[323,148,7],[300,192,4],[250,207,6],[198,229,4],[172,278,5],[217,300,6],[265,284,4],[315,252,5],[327,314,4]],
 thinking:[[348,110,4],[388,87,6],[433,105,4],[472,88,5],[516,111,7],[558,103,4],[606,122,6],[632,159,4],[590,177,5],[540,157,4],[491,171,6],[447,151,4],[404,176,5],[377,208,4],[430,218,6],[486,210,4],[548,221,5],[606,204,4]],
 memory:[[278,354,5],[314,324,4],[350,304,6],[392,298,4],[438,307,5],[482,326,7],[507,355,4],[484,390,5],[448,417,4],[405,427,6],[362,416,4],[323,397,5],[294,380,4]],
 occipital:[[653,246,4],[686,219,6],[717,224,4],[744,251,5],[755,287,7],[739,323,4],[711,350,6],[673,366,4],[651,336,5],[641,300,4],[690,289,6],[720,279,4]]
};

const folds=[
 'M184 180 C222 196 248 185 270 163','M151 249 C195 259 223 245 248 220','M204 318 C236 297 270 298 302 310',
 'M333 112 C357 130 376 131 397 113','M398 91 C425 112 448 117 471 103','M462 130 C493 149 520 149 545 132',
 'M525 96 C552 120 581 126 608 115','M568 164 C594 184 624 185 648 170','M377 198 C412 188 441 190 467 206',
 'M320 351 C352 337 384 342 412 358','M372 294 C407 315 438 318 470 305','M421 391 C454 375 485 376 510 394',
 'M654 250 C681 264 710 260 734 242','M648 313 C678 299 707 304 731 326'
];

const activeCenter:Record<Exclude<CognitivePhase,'idle'>,[number,number]>={
 thinking:[510,158],occipital:[710,292],responding:[245,225],memory:[407,352]
};

function OrbCluster({phase,active}:{phase:Exclude<CognitivePhase,'idle'>;active:boolean}){
 const list=points[phase];
 return <g className={'orb-cluster '+phase+(active?' active':'')}>
  {list.map((p,i)=>{const q=list[(i+3)%list.length];return <line key={'l'+i} x1={p[0]} y1={p[1]} x2={q[0]} y2={q[1]}/>)}
  {list.map((p,i)=><g key={'o'+i} className="brain-orb" style={{'--orb-delay':((i%7)*.11)+'s'} as CSSProperties}><circle className="orb-halo" cx={p[0]} cy={p[1]} r={(p[2]||4)*2.25}/><circle className="orb-body" cx={p[0]} cy={p[1]} r={(p[2]||4)*1.2}/><circle className="orb-shine" cx={p[0]-(p[2]||4)*.35} cy={p[1]-(p[2]||4)*.35} r={Math.max(1,(p[2]||4)*.3)}/></g>)}
 </g>;
}

function BrainMap({active,intensity}:{active:CognitivePhase;intensity:number}){
 const live=active==='idle'?null:active;
 const center=live?activeCenter[live]:null;
 const style={'--brain-intensity':String(intensity),'--brain-speed':Math.max(.65,1.9-intensity).toFixed(2)+'s'} as CSSProperties;
 return <div className="anatomy-stage" style={style}>
  <svg className="brain-anatomy" viewBox="0 0 900 560" role="img" aria-label="Animated brain-shaped cognitive activity map">
   <defs>
    <filter id="softGlow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="7" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="nodeGlow" x="-150%" y="-150%" width="400%" height="400%"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter><radialGradient id="orbFill" cx="32%" cy="28%" r="74%"><stop offset="0%" stopColor="#fff"/><stop offset="22%" stopColor="#d4d4d8"/><stop offset="62%" stopColor="#71717a"/><stop offset="100%" stopColor="#27272a"/></radialGradient>
    <clipPath id="brainClip"><path d={outlines.brain}/></clipPath>
   </defs>
   <g className="brain-silhouette">
    <path className="brain-shell" d={outlines.brain}/>
    <path className={'brain-lobe frontal '+(live==='responding'?'active':'')} d={outlines.frontal}/>
    <path className={'brain-lobe parietal '+(live==='thinking'?'active':'')} d={outlines.parietal}/>
    <path className={'brain-lobe temporal '+(live==='memory'?'active':'')} d={outlines.temporal}/>
    <path className={'brain-lobe occipital '+(live==='occipital'?'active':'')} d={outlines.occipital}/>
    <path className="brain-cerebellum" d="M585 410 C618 386 671 389 705 414 C723 431 720 460 696 477 C661 499 612 493 584 467 C568 452 568 428 585 410 Z"/>
    <path className="brain-stem" d="M495 432 C512 429 532 436 542 452 C548 474 547 506 559 535 L522 535 C509 504 493 480 475 463 C468 450 479 436 495 432 Z"/>
    {folds.map((d,i)=><path className="brain-fold" d={d} key={i}/>)}
   </g>
   <g clipPath="url(#brainClip)">
    <OrbCluster phase="responding" active={live==='responding'}/>
    <OrbCluster phase="thinking" active={live==='thinking'}/>
    <OrbCluster phase="memory" active={live==='memory'}/>
    <OrbCluster phase="occipital" active={live==='occipital'}/>
    <path className="cross-synapse" d="M232 226 C335 178 445 169 548 177 S684 235 714 292"/>
    <path className="cross-synapse" d="M302 361 C400 325 490 314 650 302"/>
    <path className="cross-synapse" d="M298 148 C382 226 445 287 479 388"/>
   </g>
   {center&&<g className={'activity-core '+live} transform={'translate('+center[0]+' '+center[1]+')'}>
    <circle className="core-glow" r="22"/><circle className="core-dot" r="7"/>
    <circle className="core-ring r1" r="34"/><circle className="core-ring r2" r="50"/><circle className="core-ring r3" r="66"/>
   </g>}
   {live&&<g className={'incoming-signals '+live}>
    <path d={live==='responding'?'M58 72 C96 104 148 153 245 225':live==='thinking'?'M802 44 C711 62 625 93 510 158':live==='occipital'?'M845 192 C801 214 765 247 710 292':'M110 500 C207 460 302 412 407 352'}/>
    <path d={live==='responding'?'M38 328 C104 308 166 274 245 225':live==='thinking'?'M760 4 C691 55 615 110 510 158':live==='occipital'?'M858 392 C812 360 769 326 710 292':'M205 528 C267 467 328 407 407 352'}/>
   </g>}
   <g className="brain-labels">
    <path d="M158 226 H82"/><text x="26" y="220">FRONTAL</text><text x="26" y="236">LOBE</text>
    <path d="M558 130 H673"/><text x="684" y="126">PARIETAL</text><text x="684" y="142">LOBE</text>
    <path d="M720 292 H817"/><text x="828" y="288">OCCIPITAL</text><text x="828" y="304">LOBE</text>
    <path d="M318 390 H176"/><text x="106" y="386">TEMPORAL</text><text x="106" y="402">LOBE</text>
    <path d="M647 462 H760"/><text x="770" y="466">CEREBELLUM</text>
    <path d="M524 510 H420"/><text x="343" y="514">BRAIN STEM</text>
   </g>
  </svg>
 </div>;
}

export default function BrainPage(){
 const {phase,live,cognitive,elapsed,visualPulse,latest}=useBrainSynapsis();
 const current=lobes.find(l=>l.phase===phase);
 const numeric=(key:string)=>{const value=latest?.[key];return typeof value==='number'?value:null;};
 const seconds=(key:string)=>{const value=numeric(key);return value===null?'—':value.toFixed(3)+'s';};
 const rate=(key:string)=>{const value=numeric(key);return value===null?'—':value.toFixed(1)+'/s';};
 const prompt=numeric('prompt_tokens'),context=numeric('effective_context_size'),toolCalls=Array.isArray(latest?.tool_calls)?latest.tool_calls.length:0;
 const utilization=numeric('context_utilization'),cache=numeric('cache_usage');
 return <div className="brain-page"><div className="brain-layout">
  <section className="brain-hero">
   <div className="brain-kicker">COGNITIVE ENGINE</div>
   <div className="brain-heading"><div><h1>Brain Synapsis</h1><p>Live cognitive activity map</p></div><div className={'brain-state '+(phase!=='idle'?'active':'')}><Activity size={16}/><div><strong>{phase==='idle'?'Idle':live?.stage.replaceAll('_',' ')||cognitive.label}</strong><small>{current?current.name+' Active · '+elapsed.toFixed(1)+'s':'No active region'}</small></div></div></div>
   <BrainMap active={phase} intensity={visualPulse}/>
   <div className="brain-metrics" aria-label="Measured latest-run metrics">
    <div><small>First token</small><strong>{seconds('first_token_seconds')}</strong></div>
    <div><small>Prompt eval</small><strong>{seconds('prompt_eval_seconds')}</strong><em>{rate('prompt_tokens_per_second')}</em></div>
    <div><small>Generation</small><strong>{seconds('generation_seconds')}</strong><em>{rate('generation_tokens_per_second')}</em></div>
    <div><small>Context</small><strong>{prompt===null||context===null?'—':prompt+' / '+context}</strong><em>{utilization===null?'—':Math.round(utilization*100)+'%'}</em></div>
    <div><small>Retrieval</small><strong>{seconds('context_retrieval_seconds')}</strong><em>{toolCalls+' tool call'+(toolCalls===1?'':'s')}</em></div>
    <div><small>Prompt cache</small><strong>{cache===null?'—':Math.round(cache*100)+'%'}</strong><em>{String(latest?.execution_mode||'—')}</em></div>
   </div>
  </section>
  <aside className="brain-regions">
   <div className="brain-regions-title"><Activity size={16}/><div><h2>BRAIN REGIONS & AGENT STATES</h2><p>Each region reflects a different part of Keno-B's active pipeline.</p></div></div>
   {lobes.map(({phase:p,name,subtitle,detail,Icon})=><article key={p} className={'brain-region-card '+(phase===p?'active':'')}><div className="region-icon"><Icon size={28}/></div><div><div className="region-card-head"><h3>{name}</h3><span><b/> {phase===p?'ACTIVE':'INACTIVE'}</span></div><strong>{subtitle}</strong><p>{detail}</p></div></article>)}
  </aside>
 </div><p className="brain-note">The animated pulse is visual only. Timing, throughput, context, retrieval and cache values are measured from the latest completed run.</p></div>;
}
