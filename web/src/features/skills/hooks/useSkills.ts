import {useEffect,useState} from 'react';
import {useLab} from '../../../app/providers/LabProvider';
import type {Skill,SkillMatch} from '../../../shared/types';

export const starterSkill=`---
name: Research Brief
description: Search the web when enabled and produce a concise evidence-grounded brief.
triggers:
  - research brief
  - investigate this
requires:
  - web_search
  - web_inspect
risk: low
---
# Research Brief

Search for the user's requested topic.
Inspect the strongest relevant results.
Summarize only supported facts and mention conflicts or missing evidence.
Keep the final brief concise.
`;

export function useSkills(){
 const {api,connected,setError}=useLab();
 const [skills,setSkills]=useState<Skill[]>([]),[busy,setBusy]=useState(false),[open,setOpen]=useState(false),[editingId,setEditingId]=useState<string|null>(null),[markdown,setMarkdown]=useState(starterSkill),[history,setHistory]=useState<Skill[]>([]),[historyOpen,setHistoryOpen]=useState(false),[matchQuery,setMatchQuery]=useState(''),[match,setMatch]=useState<SkillMatch|null>(null);
 async function load(){if(!connected){setSkills([]);return;}try{setSkills(await api.get<Skill[]>('/skills'));}catch(e){setError((e as Error).message);}}
 useEffect(()=>{void load();},[connected]);
 function create(){setEditingId(null);setMarkdown(starterSkill);setOpen(true);}
 function edit(skill:Skill){setEditingId(skill.id);setMarkdown(skill.source_markdown);setOpen(true);}
 async function save(){setBusy(true);try{await api.post<Skill>(editingId?'/skills/'+editingId+'/import':'/skills/import',{markdown});setOpen(false);await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function toggle(skill:Skill){setBusy(true);try{await api.put('/skills/'+skill.id+'/enabled',{enabled:!skill.enabled});await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function remove(skill:Skill){setBusy(true);try{await api.remove('/skills/'+skill.id);await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function showHistory(skill:Skill){try{setHistory(await api.get<Skill[]>('/skills/'+skill.id+'/history'));setEditingId(skill.id);setHistoryOpen(true);}catch(e){setError((e as Error).message);}}
 async function restore(version:number){if(!editingId)return;setBusy(true);try{await api.post('/skills/'+editingId+'/history/'+version+'/restore',{});setHistory(await api.get<Skill[]>('/skills/'+editingId+'/history'));await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function testMatch(){if(!matchQuery.trim())return;try{setMatch(await api.get<SkillMatch>('/skills/match?q='+encodeURIComponent(matchQuery.trim())));}catch(e){setError((e as Error).message);}}
 async function loadFile(file:File){try{const text=await file.text();setMarkdown(text);setOpen(true);}catch{setError('Could not read skill file.');}}
 return {connected,skills,busy,open,setOpen,editingId,markdown,setMarkdown,history,historyOpen,setHistoryOpen,matchQuery,setMatchQuery,match,create,edit,save,toggle,remove,showHistory,restore,testMatch,loadFile};
}
