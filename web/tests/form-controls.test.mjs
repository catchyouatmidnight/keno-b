import assert from 'node:assert/strict';
import {readdir,readFile} from 'node:fs/promises';
import test from 'node:test';

test('React pages use the shared Ant Design form controls',async()=>{
 const root=new URL('../src/',import.meta.url);
 for(const name of (await readdir(root)).filter(name=>name.endsWith('.tsx'))){
  const source=await readFile(new URL(name,root),'utf8');
  assert.doesNotMatch(source,/<(?:input|select|textarea)\b/,name+' contains a native form control');
 }
});
