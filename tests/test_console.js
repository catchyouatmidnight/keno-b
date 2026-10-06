'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.value='';this.textContent='';this.classList={toggle(){}};this.open=false;}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;this.textContent='';}
  addEventListener(){} add(item){this.append(item);} before(){} after(){} remove(){} focus(){} reset(){}
  close(){this.open=false;} showModal(){this.open=true;}
}
function descendants(el){return [el,...el.children.flatMap(descendants)];}
const ids=new Map(),storage=new Map(),calls=[];
const context={document:{getElementById:id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);},createElement:tag=>new Element(tag),createTextNode:text=>Object.assign(new Element('#text'),{textContent:text}),querySelectorAll:()=>[]},window:{location:{href:'http://localhost:19081/'}},URL,localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},setInterval:()=>1,clearInterval(){},setTimeout,requestAnimationFrame:callback=>{callback();return 1;},Option:class extends Element{constructor(text,value){super('option');this.textContent=text;this.value=value;}},performance,AbortController,TextDecoder,crypto,confirm:()=>true};
vm.createContext(context);
vm.runInContext(fs.readFileSync('app/static/markdown.js','utf8'),context);
context.KenoMarkdown=context.window.KenoMarkdown;
const output=new Element();
context.KenoMarkdown.render(output,'# Title\n**Bold**\n```html\n<script>secret()</script>\n```\n[bad](javascript:alert)\n[ok](https://example.org/)\n<img src="https://tracking.example/">\n| A | B |\n| --- | --- |\n| 1 | 2 |');
const nodes=descendants(output);
assert(nodes.some(n=>n.tagName==='h1'));assert(nodes.some(n=>n.tagName==='strong'));assert(nodes.some(n=>n.tagName==='table'));
assert.equal(nodes.filter(n=>n.tagName==='a').length,1);
assert.equal(nodes.find(n=>n.tagName==='a').href,'https://example.org/');
assert(!nodes.some(n=>['script','img'].includes(n.tagName)));
assert(nodes.some(n=>n.tagName==='code'&&n.textContent.includes('<script>')));
// Model-generated Markdown often repeats "1." and separates items by blanks.
// One ordered-list node lets the browser show 1, 2, 3 instead of restarting.
context.KenoMarkdown.render(output,'1. **Current state**\n\n1. Memory optimization\nwrapped item detail\n\n1. Secure onboarding\n\nReferences: local document');
assert.equal(output.children.filter(n=>n.tagName==='ol').length,1);
const ordered=output.children.find(n=>n.tagName==='ol');
assert.equal(ordered.start,1);assert.equal(ordered.children.length,3);
assert(descendants(ordered.children[1]).some(n=>n.textContent==='wrapped item detail'));
assert.equal(output.children.at(-1).tagName,'p');
context.KenoMarkdown.render(output,'3. Third\n\n4. Fourth\n\nSeparate paragraph\n\n1. New list');
const separate=output.children.filter(n=>n.tagName==='ol');
assert.equal(separate.length,2);assert.equal(separate[0].start,3);assert.equal(separate[0].children.length,2);assert.equal(separate[1].start,1);
context.KenoMarkdown.render(output,'- First\n\n- Second\n\n1. Ordered');
assert.equal(output.children[0].tagName,'ul');assert.equal(output.children[0].children.length,2);assert.equal(output.children[1].tagName,'ol');
const apiKey='simulated-local-key';storage.set('keno.serverAccessKey',apiKey);
context.fetch=async(path,options)=>{calls.push([path,options.headers.Authorization]);let data=[];
  if(path.endsWith('/status'))data={router_ready:true,model_ready:true};
  if(path.endsWith('/profile'))data={name:'Owner',background:'',preferences:''};
  if(path.endsWith('/identity'))data={name:'Keno',personality:'',response_examples:''};
  if(path.endsWith('/tools/settings'))data={automatic_memory:true,weather_enabled:false,search_enabled:false};
  return {ok:true,json:async()=>data};};
vm.runInContext(fs.readFileSync('app/static/app.js','utf8'),context);
setImmediate(()=>{
  assert(calls.some(([path])=>path.endsWith('/tools/settings')));
  assert(calls.every(([,auth])=>auth==='Bearer '+apiKey));
  assert.equal(ids.get('token').value,'');assert.equal(ids.get('automaticMemory').checked,true);
  assert.equal(storage.get('keno.serverAccessKey'),apiKey);
  ids.get('disconnect').onclick();assert(!storage.has('keno.serverAccessKey'));
  assert.equal(ids.get('messages').children.length,0);
  console.log('Markdown safety and saved-key reconnect checks passed.');
});
