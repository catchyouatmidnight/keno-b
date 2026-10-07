import assert from 'node:assert/strict';
import test from 'node:test';
import {randomId} from '../src/id.mjs';

test('randomId works when crypto.randomUUID is unavailable',()=>{
 let n=0;
 const id=randomId({getRandomValues(bytes){for(let i=0;i<bytes.length;i++)bytes[i]=(n++*17+3)&255;return bytes;}});
 assert.match(id,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});
