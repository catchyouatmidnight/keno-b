export function randomId(cryptoSource=globalThis.crypto){
 if(typeof cryptoSource?.randomUUID==='function')return cryptoSource.randomUUID();
 if(typeof cryptoSource?.getRandomValues==='function'){
  const bytes=new Uint8Array(16);cryptoSource.getRandomValues(bytes);bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=[...bytes].map(value=>value.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
 }
 return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,char=>{const value=Math.floor(Math.random()*16);return (char==='x'?value:(value&3)|8).toString(16);});
}
