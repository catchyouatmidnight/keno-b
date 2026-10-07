import assert from 'node:assert/strict';
import {readdir,readFile,stat} from 'node:fs/promises';
import test from 'node:test';

async function files(root){
 const result=[];
 for(const name of await readdir(root)){const url=new URL(name,root);const info=await stat(url);if(info.isDirectory())result.push(...await files(new URL(name+'/',root)));else if(/\.(?:ts|tsx)$/.test(name))result.push(url);}
 return result;
}
test('frontend uses local shadcn UI boundaries',async()=>{
 const root=new URL('../src/',import.meta.url);
 for(const file of await files(root)){
  const source=await readFile(file,'utf8'),path=file.pathname,name=path.split('/').pop();
  assert.doesNotMatch(source,/<form\b|<\/form>/i,name+' uses a form element');
  assert.doesNotMatch(source,/from\s*['"]antd['"]/,name+' still imports AntD');
  if(!path.includes('/shared/ui/'))assert.doesNotMatch(source,/<(?:input|select|textarea)\b/,name+' bypasses shared shadcn UI primitives');
 }
});
test('root feature entry files stay thin',async()=>{
 const root=new URL('../src/',import.meta.url);
 for(const name of ['Playground.tsx','Documents.tsx','Memory.tsx','Settings.tsx','Benchmarks.tsx','BrainSynapsis.tsx','Workspace.tsx','App.tsx']){
  const source=await readFile(new URL(name,root),'utf8');
  assert(source.length<500,name+' should only re-export its feature module');
 }
});
