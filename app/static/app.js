'use strict';
const $ = id => document.getElementById(id);
let key = '', conversationId = '', controller = null, sourceConversation = null;
let retry = null, busy = false, poll = null;
const notice = text => { $('notice').textContent = text; };
async function api(path, options = {}) {
  if (!key) throw new Error('Connect with your server access key first.');
  const response = await fetch('/api/v1' + path, {...options, headers: {
    'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', ...options.headers
  }});
  if (!response.ok) {
    let data; try { data = await response.json(); } catch { data = {}; }
    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || 'Request failed'));
  }
  return response;
}
const json = async (path, options) => (await api(path, options)).json();
const put = (path, value) => json(path, {method: 'PUT', body: JSON.stringify(value)});
function handle(fn) { return async event => { event?.preventDefault(); try { await fn(event); } catch (error) { notice(error.message); } }; }
function message(role, text) {
  const element = document.createElement('div'); element.className = 'message ' + role;
  const label = document.createElement('span'); label.className = 'role'; label.textContent = role;
  const content = document.createElement('span'); content.textContent = text;
  element.append(label, content); $('messages').append(element);
  $('messages').scrollTop = $('messages').scrollHeight; return content;
}
async function refreshStatus() {
  const data = await json('/status');
  $('status').textContent = data.model_ready ? (data.generating ? 'Generating' : 'Model ready') : 'Model loading / unavailable';
}
async function refreshConversations() {
  const rows = await json('/conversations'); $('conversations').replaceChildren();
  for (const row of rows) { const option = new Option(row.title, row.id); $('conversations').add(option); }
  if (!rows.some(row => row.id === conversationId)) conversationId = rows[0]?.id || '';
  $('conversations').value = conversationId;
}
async function loadConversation() {
  $('messages').replaceChildren(); if (!conversationId) return;
  const data = await json('/conversations/' + conversationId);
  for (const turn of data.turns) {
    message('user', turn.user_text);
    message('assistant', turn.status === 'complete' ? turn.assistant_text : 'Response interrupted or failed. Resend your message to retry.');
  }
}
async function newChat() {
  const data = await json('/conversations', {method:'POST', body:JSON.stringify({title:'Chat · ' + new Date().toLocaleString()})});
  conversationId = data.id; retry = null; await refreshConversations(); await loadConversation();
}
$('connect').onclick = handle(async () => {
  if (busy) throw new Error('Stop the active response first.');
  clearInterval(poll); key = $('token').value.trim();
  await refreshStatus();
  const [profile, identity] = await Promise.all([json('/profile'), json('/identity')]);
  $('profileName').value=profile.name; $('background').value=profile.background; $('preferences').value=profile.preferences;
  $('assistantName').value=identity.name; $('personality').value=identity.personality; $('examples').value=identity.response_examples;
  await refreshConversations(); await loadConversation(); await refreshMemories(); $('token').value=''; notice('Connected.');
  poll=setInterval(() => refreshStatus().catch(() => { $('status').textContent='Connection lost'; }), 10000);
});
$('disconnect').onclick = () => { controller?.abort(); clearInterval(poll); key=''; $('token').value=''; conversationId=''; retry=null; $('messages').replaceChildren(); $('memoryList').replaceChildren(); $('conversations').replaceChildren(); for (const id of ['profileName','background','preferences','assistantName','personality','examples','memoryKey','memoryContent']) $(id).value=''; $('status').textContent='Disconnected'; notice('Disconnected.'); };
document.querySelectorAll('[data-tab]').forEach(button => button.onclick=() => {
  document.querySelectorAll('.tab').forEach(tab => tab.classList.toggle('active', tab.id===button.dataset.tab));
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b===button));
});
$('newChat').onclick=handle(async () => { if (busy) throw new Error('Stop the active response first.'); await newChat(); });
$('conversations').onchange=handle(async () => { if (busy) { $('conversations').value=conversationId; throw new Error('Stop the active response first.'); } conversationId=$('conversations').value; retry=null; await loadConversation(); });
$('deleteChat').onclick=handle(async () => {
  if (busy) throw new Error('Stop the active response first.');
  if (!conversationId || !confirm('Delete this conversation? Saved memories remain.')) return;
  await json('/conversations/'+conversationId,{method:'DELETE'}); conversationId=''; retry=null; await refreshConversations(); await loadConversation();
});
$('stop').onclick=() => controller?.abort();
$('chatForm').onsubmit=handle(async () => {
  if (busy) return;
  const text=$('message').value.trim(); if (!text) return;
  if (!conversationId) await newChat();
  const requestId=retry?.text===text && retry?.conversation===conversationId ? retry.id : crypto.randomUUID();
  retry={text,conversation:conversationId,id:requestId};
  busy=true; $('send').disabled=true; $('stop').disabled=false; controller=new AbortController();
  message('user',text); const output=message('assistant',''); let completed=false;
  notice('Generating locally…');
  try {
    const response=await api('/chat',{method:'POST',signal:controller.signal,body:JSON.stringify({conversation_id:conversationId,message:text,request_id:requestId,stream:true})});
    const reader=response.body.getReader(), decoder=new TextDecoder(); let buffer='';
    function consume(block) {
      const lines=block.split('\n'); const name=lines.find(line=>line.startsWith('event:'))?.slice(6).trim();
      const raw=lines.filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');
      if (!raw) return; const data=JSON.parse(raw);
      if(name==='delta') { output.textContent+=data.text; $('messages').scrollTop=$('messages').scrollHeight; }
      if(name==='context') $('context').textContent='Memories: '+(data.memory_keys.join(', ')||'none')+' · History turns: '+data.history_turns;
      if(name==='error') throw new Error(data.detail);
      if(name==='done') { completed=true; output.textContent=data.reply; retry=null; $('message').value=''; notice('Saved · '+(data.context.elapsed_seconds||0)+'s'); }
    }
    while(true) {
      const {value,done}=await reader.read(); buffer+=decoder.decode(value,{stream:!done}).replace(/\r\n/g,'\n');
      let split; while((split=buffer.indexOf('\n\n'))>=0) { consume(buffer.slice(0,split)); buffer=buffer.slice(split+2); }
      if(done) break;
    }
    if(!completed) throw new Error('Connection ended before completion. Resend to retry.');
  } catch(error) {
    notice(error.name==='AbortError'?'Stopped. Resend the same message to retry.':error.message);
    if(!completed) output.textContent+='\n[Incomplete response — not a confirmed saved answer]';
  } finally { busy=false; $('send').disabled=false; $('stop').disabled=true; controller=null; }
});
$('profileForm').onsubmit=handle(async()=>{ await put('/profile',{name:$('profileName').value,background:$('background').value,preferences:$('preferences').value}); notice('Profile saved.'); });
$('identityForm').onsubmit=handle(async()=>{ await put('/identity',{name:$('assistantName').value,personality:$('personality').value,response_examples:$('examples').value}); notice('Personality saved.'); });
function clearMemory() { $('memoryForm').reset(); sourceConversation=null; }
$('clearMemory').onclick=clearMemory;
$('memoryForm').onsubmit=handle(async()=>{
  const memoryKey=$('memoryKey').value;
  await put('/memories/'+encodeURIComponent(memoryKey),{key:memoryKey,content:$('memoryContent').value,category:$('category').value,pinned:$('pinned').checked,source_conversation_id:sourceConversation,expires_at:$('expiry').value?new Date($('expiry').value).toISOString():null});
  clearMemory(); await refreshMemories(); notice('Memory saved.');
});
async function refreshMemories() {
  const rows=await json('/memories?q='+encodeURIComponent($('search').value)); $('memoryList').replaceChildren();
  if(!rows.length) { const p=document.createElement('p'); p.className='muted'; p.textContent='No matching memories.'; $('memoryList').append(p); }
  for(const row of rows) {
    const card=document.createElement('div'); card.className='panel memory-card';
    const title=document.createElement('strong'); title.textContent=row.key+(row.pinned?' · pinned':'');
    const text=document.createElement('p'); text.textContent=row.content;
    const meta=document.createElement('small'); meta.textContent=row.category+' · Updated '+new Date(row.updated_at).toLocaleString()+(row.expires_at?' · Expires '+new Date(row.expires_at).toLocaleString():'');
    const actions=document.createElement('div'); actions.className='row';
    const edit=document.createElement('button'); edit.className='secondary'; edit.textContent='Edit'; edit.onclick=()=>{
      $('memoryKey').value=row.key; $('memoryContent').value=row.content; $('category').value=row.category; $('pinned').checked=!!row.pinned; sourceConversation=row.source_conversation_id;
      $('expiry').value=row.expires_at?new Date(new Date(row.expires_at)-new Date(row.expires_at).getTimezoneOffset()*60000).toISOString().slice(0,16):'';
      $('memoryKey').focus();
    };
    const remove=document.createElement('button'); remove.className='secondary'; remove.textContent='Delete'; remove.onclick=handle(async()=>{if(!confirm('Delete '+row.key+'?'))return; await json('/memories/'+encodeURIComponent(row.key),{method:'DELETE'}); await refreshMemories(); notice('Memory deleted.');});
    actions.append(edit,remove); card.append(title,text,meta,actions); $('memoryList').append(card);
  }
}
$('refreshMemories').onclick=handle(refreshMemories);
async function download(path,filename) { const blob=await (await api(path)).blob(); const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
$('schema').onclick=handle(()=>download('/openapi.json','keno-openapi.json'));
$('backup').onclick=handle(()=>download('/backup','keno-backup.sqlite3'));
