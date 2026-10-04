'use strict';
const $ = id => document.getElementById(id);
const ACCESS_KEY_STORAGE = 'keno.serverAccessKey';
function savedKey() { try { return localStorage.getItem(ACCESS_KEY_STORAGE) || ''; } catch { return ''; } }
function rememberKey(value) { try { localStorage.setItem(ACCESS_KEY_STORAGE, value); return true; } catch { return false; } }
function forgetKey() { try { localStorage.removeItem(ACCESS_KEY_STORAGE); } catch { /* Storage may be blocked. */ } }
let key = '', conversationId = '', controller = null, sourceConversation = null;
let retry = null, busy = false, poll = null, uploading = false;
let attachmentSelection = new Set();
const notice = text => { $('notice').textContent = text; };
async function api(path, options = {}) {
  if (!key) throw new Error('Connect with your server access key first.');
  const response = await fetch('/api/v1' + path, {...options, headers: {
    'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', ...options.headers
  }});
  if (!response.ok) {
    if (response.status === 401) {
      forgetKey(); key = ''; $('token').value = ''; clearInterval(poll);
      $('status').textContent = 'Access key rejected';
    }
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
  const content = document.createElement('span'); content.className='message-content'; content._raw=text;
  if(role==='assistant') KenoMarkdown.render(content,text); else content.textContent=text;
  element.append(label, content); $('messages').append(element);
  $('messages').scrollTop = $('messages').scrollHeight; return content;
}
function renderAnswer(output, text, immediate=false) {
  output._raw=text;
  if(immediate) { KenoMarkdown.render(output,text);return; }
  if(output._frame)return;
  output._frame=requestAnimationFrame(()=>{output._frame=null;KenoMarkdown.render(output,output._raw);$('messages').scrollTop=$('messages').scrollHeight;});
}
function toolActivity(output, events, committed=false) {
  if(!events?.length)return;
  if(!output._activity) { output._activity=document.createElement('details');output._activity.className='tool-activity';output.before(output._activity); }
  output._activity.replaceChildren();const summary=document.createElement('summary');
  summary.textContent='Tools · '+events.length+(events.some(e=>e.status==='running')?' · Working':'');output._activity.append(summary);
  const labels={memory_search:'Search memories',memory_save:committed?'Save memory':'Prepare memory',memory_forget:committed?'Forget memory':'Prepare forgetting',document_search:'Search document',document_read:'Read pages',document_overview:'Review document text',calculator:'Calculate',weather:'Weather lookup',web_search:'Web search'};
  for(const item of events) { const row=document.createElement('div');row.textContent=(labels[item.name]||item.name)+(item.memory_key?' · '+item.memory_key:'')+' · '+item.status;output._activity.append(row); }
}
let previewUrl=null,previewGeneration=0;
function closeSource() { previewGeneration++;$('sourceDialog').close();if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null; }
$('closeSource').onclick=closeSource;
$('sourceDialog').addEventListener('close',()=>{previewGeneration++;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;});
async function openSource(source) {
  const generation=++previewGeneration;
  if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;
  $('sourceTitle').textContent=source.name+(source.page?' · Page '+source.page:'');$('sourceBody').replaceChildren();
  if(!$('sourceDialog').open)$('sourceDialog').showModal();
  const response=await api('/attachments/'+encodeURIComponent(source.attachment_id)+'/pages/'+(source.page||1));
  if(generation!==previewGeneration||!$('sourceDialog').open)return;
  if(response.headers.get('content-type')?.includes('application/json')) { const data=await response.json();if(generation!==previewGeneration)return;const pre=document.createElement('pre');pre.textContent=data.text;$('sourceBody').append(pre); }
  else { const blob=await response.blob();if(generation!==previewGeneration)return;previewUrl=URL.createObjectURL(blob);const image=document.createElement('img');image.src=previewUrl;image.alt=$('sourceTitle').textContent;$('sourceBody').append(image); }
}
function addSources(output, context) {
  if(output._sources)output._sources.remove();
  const sources=[...(context.document_sources||[]),...(context.visual_sources||[])],links=context.web_sources||[];
  if(!sources.length&&!links.length)return;
  const footer=document.createElement('div');footer.className='sources';output._sources=footer;output.after(footer);
  const seen=new Set();
  for(const source of sources) { const key=source.attachment_id+':'+source.page;if(seen.has(key))continue;seen.add(key);
    const button=document.createElement('button');button.className='secondary';button.textContent=source.name+(source.page?' p.'+source.page:'');button.onclick=handle(()=>openSource(source));footer.append(button); }
  for(const source of links) { try { const url=new URL(source.url);if(!['http:','https:'].includes(url.protocol))continue;const link=document.createElement('a');link.textContent=source.title||url.hostname;link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';footer.append(link); } catch {} }
}
async function refreshStatus() {
  const data = await json('/status');
  $('status').textContent = !data.router_ready ? 'Laya loading / unavailable' : data.model_ready ? (data.generating ? 'Generating' : 'Model ready') : 'Model loading / unavailable';
}
async function refreshConversations() {
  const rows = await json('/conversations'); $('conversations').replaceChildren();
  for (const row of rows) { const option = new Option(row.title, row.id); $('conversations').add(option); }
  if (!rows.some(row => row.id === conversationId)) conversationId = rows[0]?.id || '';
  $('conversations').value = conversationId;
}
async function loadConversation() {
  $('messages').replaceChildren(); attachmentSelection.clear(); $('attachmentList').replaceChildren(); if (!conversationId) return;
  const data = await json('/conversations/' + conversationId);
  for (const turn of data.turns) {
    message('user', turn.user_text);
    const output=message('assistant', turn.status === 'complete' ? turn.assistant_text : 'Response interrupted or failed. Resend your message to retry.');
    if(turn.status==='complete') { const context=JSON.parse(turn.metadata||'{}');toolActivity(output,context.tool_calls,true);addSources(output,context); }
  }
  await refreshAttachments(true);
}
async function refreshAttachments(selectRecent=false) {
  const rows=await json('/conversations/'+conversationId+'/attachments');
  if(selectRecent) attachmentSelection=new Set(rows.slice(-4).map(row=>row.id));
  $('attachmentList').replaceChildren();
  for(const row of rows) {
    const item=document.createElement('div'); item.className='attachment';
    const label=document.createElement('label'), input=document.createElement('input');
    input.type='checkbox'; input.checked=attachmentSelection.has(row.id);
    input.onchange=()=>{ if(busy||uploading) { input.checked=attachmentSelection.has(row.id); return; } if(input.checked) { if(attachmentSelection.size>=4) { input.checked=false; notice('Select up to four files per message.'); return; } attachmentSelection.add(row.id); } else attachmentSelection.delete(row.id); retry=null; };
    label.append(input,document.createTextNode(row.name+(row.pages?' · '+row.pages+' page(s)':'')));
    const remove=document.createElement('button'); remove.type='button'; remove.className='secondary'; remove.textContent='Remove';
    remove.onclick=handle(async()=>{ if(busy||uploading) throw new Error('Wait for the active request first.'); await json('/attachments/'+row.id,{method:'DELETE'}); attachmentSelection.delete(row.id); retry=null; await refreshAttachments(); });
    item.append(label,remove); $('attachmentList').append(item);
  }
}
$('files').onchange=handle(async()=>{
  if(busy||uploading) throw new Error('Wait for the active request first.');
  const files=Array.from($('files').files); if(!files.length) return;
  uploading=true; $('send').disabled=true;
  try {
    if(!conversationId) await newChat();
    for(const file of files) {
      if(file.size>8*1024*1024) throw new Error(file.name+' exceeds 8 MB.');
      notice('Reading '+file.name+' locally…');
      const data=await new Promise((resolve,reject)=>{ const reader=new FileReader(); reader.onload=()=>resolve(String(reader.result).split(',')[1]); reader.onerror=()=>reject(new Error('Could not read file')); reader.readAsDataURL(file); });
      const row=await json('/attachments',{method:'POST',body:JSON.stringify({conversation_id:conversationId,name:file.name,data_base64:data})});
      if(attachmentSelection.size<4) attachmentSelection.add(row.id);
      retry=null; await refreshAttachments();
    }
    notice('Files stored on your server. Selected files will be included in your next message.');
  } finally { uploading=false; $('send').disabled=false; $('files').value=''; }
});
async function newChat() {
  const data = await json('/conversations', {method:'POST', body:JSON.stringify({title:'Chat · ' + new Date().toLocaleString()})});
  conversationId = data.id; retry = null; await refreshConversations(); await loadConversation();
}
async function connect() {
  if (busy||uploading) throw new Error('Stop the active response first.');
  clearInterval(poll); key = $('token').value.trim();
  await refreshStatus();
  const remembered = rememberKey(key);
  const [profile, identity, toolSettings] = await Promise.all([json('/profile'), json('/identity'), json('/tools/settings')]);
  $('profileName').value=profile.name; $('background').value=profile.background; $('preferences').value=profile.preferences;
  $('assistantName').value=identity.name; $('personality').value=identity.personality; $('examples').value=identity.response_examples;
  $('automaticMemory').checked=toolSettings.automatic_memory;$('weatherEnabled').checked=toolSettings.weather_enabled;$('searchEnabled').checked=toolSettings.search_enabled;
  await refreshConversations(); await loadConversation(); await refreshMemories(); $('token').value='';
  notice(remembered ? 'Connected. Access key saved in this browser.' : 'Connected for this tab. Browser storage is blocked, so the key cannot be remembered.');
  poll=setInterval(() => refreshStatus().catch(() => { $('status').textContent='Connection lost'; }), 10000);
}
$('connect').onclick = handle(connect);
$('disconnect').onclick = () => { if(uploading) { notice('Wait for the file upload to finish.'); return; } controller?.abort(); closeSource();clearInterval(poll); forgetKey(); key=''; $('token').value=''; conversationId=''; retry=null; attachmentSelection.clear(); $('attachmentList').replaceChildren(); $('messages').replaceChildren(); $('memoryList').replaceChildren(); $('conversations').replaceChildren(); for (const id of ['profileName','background','preferences','assistantName','personality','examples','memoryKey','memoryContent']) $(id).value=''; $('status').textContent='Disconnected'; notice('Disconnected and saved key forgotten.'); };
document.querySelectorAll('[data-tab]').forEach(button => button.onclick=() => {
  document.querySelectorAll('.tab').forEach(tab => tab.classList.toggle('active', tab.id===button.dataset.tab));
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b===button));
});
$('newChat').onclick=handle(async () => { if (busy||uploading) throw new Error('Stop the active response first.'); await newChat(); });
$('conversations').onchange=handle(async () => { if (busy||uploading) { $('conversations').value=conversationId; throw new Error('Stop the active response first.'); } conversationId=$('conversations').value; retry=null; await loadConversation(); });
$('deleteChat').onclick=handle(async () => {
  if (busy||uploading) throw new Error('Stop the active response first.');
  if (!conversationId || !confirm('Delete this conversation? Saved memories remain.')) return;
  await json('/conversations/'+conversationId,{method:'DELETE'}); conversationId=''; retry=null; await refreshConversations(); await loadConversation();
});
$('stop').onclick=() => controller?.abort();
$('chatForm').onsubmit=handle(async () => {
  if (busy||uploading) return;
  const text=$('message').value.trim(); if (!text) return;
  if (!conversationId) await newChat();
  const ids=Array.from(attachmentSelection).sort();
  const requestId=retry?.text===text && retry?.conversation===conversationId && JSON.stringify(retry.ids)===JSON.stringify(ids) ? retry.id : crypto.randomUUID();
  retry={text,conversation:conversationId,id:requestId,ids};
  busy=true; $('send').disabled=true; $('stop').disabled=false; controller=new AbortController();
  message('user',text); const output=message('assistant',''); let completed=false, firstWord=null, memoryChanged=false;const activities=new Map();
  const requestStarted=performance.now();
  notice('Processing request locally…');
  try {
    const response=await api('/chat',{method:'POST',signal:controller.signal,body:JSON.stringify({conversation_id:conversationId,message:text,request_id:requestId,stream:true,attachment_ids:ids,max_tokens:Number($('outputLimit').value)})});
    const reader=response.body.getReader(), decoder=new TextDecoder(); let buffer='';
    function consume(block) {
      const lines=block.split('\n'); const name=lines.find(line=>line.startsWith('event:'))?.slice(6).trim();
      const raw=lines.filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');
      if (!raw) return; const data=JSON.parse(raw);
      if(name==='delta') { if(firstWord===null) firstWord=(performance.now()-requestStarted)/1000;renderAnswer(output,output._raw+data.text); }
      if(name==='tool') { activities.set(data.index,data);toolActivity(output,Array.from(activities.values())); }
      if(name==='context') { const sources=[...(data.document_sources||[]),...(data.visual_sources||[])]; $('context').textContent='Memories: '+(data.memory_keys.join(', ')||'none')+' · History turns: '+data.history_turns+(sources.length?' · Sources: '+Array.from(new Set(sources.map(s=>s.name+(s.page?' p.'+s.page:'')))).join(', '):''); notice(data.route?.thinking?'Analyzing locally…':'Responding locally…'); }
      if(name==='error') throw new Error(data.detail);
      if(name==='done') { completed=true;renderAnswer(output,data.reply,true);toolActivity(output,data.context.tool_calls,true);addSources(output,data.context);memoryChanged=!!data.context.memory_changes?.length;retry=null; $('message').value=''; const timings='First word '+(firstWord??data.context.first_token_seconds??0).toFixed(2)+'s · Total '+(data.context.total_seconds??data.context.elapsed_seconds??0)+'s'; notice(data.context.finish_reason==='length'?'Response reached its output limit and may be unfinished. Select a longer output and ask again. · '+timings:'Saved · '+timings); }
    }
    while(true) {
      const {value,done}=await reader.read(); buffer+=decoder.decode(value,{stream:!done}).replace(/\r\n/g,'\n');
      let split; while((split=buffer.indexOf('\n\n'))>=0) { consume(buffer.slice(0,split)); buffer=buffer.slice(split+2); }
      if(done) break;
    }
    if(!completed) throw new Error('Connection ended before completion. Resend to retry.');
    if(memoryChanged)await refreshMemories();
  } catch(error) {
    notice(error.name==='AbortError'?'Stopped. Resend the same message to retry.':error.message);
    if(!completed)renderAnswer(output,output._raw+'\n[Incomplete response — not a confirmed saved answer]',true);
  } finally { busy=false; $('send').disabled=false; $('stop').disabled=true; controller=null; }
});
$('profileForm').onsubmit=handle(async()=>{ await put('/profile',{name:$('profileName').value,background:$('background').value,preferences:$('preferences').value}); notice('Profile saved.'); });
$('identityForm').onsubmit=handle(async()=>{ await put('/identity',{name:$('assistantName').value,personality:$('personality').value,response_examples:$('examples').value}); notice('Personality saved.'); });
$('toolsForm').onsubmit=handle(async()=>{await put('/tools/settings',{automatic_memory:$('automaticMemory').checked,weather_enabled:$('weatherEnabled').checked,search_enabled:$('searchEnabled').checked});notice('Tool settings saved.');});
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
const rememberedAccessKey = savedKey();
if (rememberedAccessKey) {
  $('token').value = rememberedAccessKey;
  handle(connect)();
}
