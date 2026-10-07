import type {ChatRequest,ChatResult} from '../types';
export class ApiError extends Error {constructor(message:string,public status:number){super(message);}}
export class ApiClient {
  constructor(public key=''){}
  async fetch(path:string,options:RequestInit={}){if(!this.key)throw new ApiError('Connect to the backend first.',401);const response=await fetch('/api/v1'+path,{...options,cache:'no-store',headers:{Authorization:'Bearer '+this.key,...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});if(!response.ok){let data:{detail?:unknown}={};try{data=await response.json();}catch{/* non-JSON gateway failure */}throw new ApiError(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||`HTTP ${response.status}`),response.status);}return response;}
  async get<T>(path:string,signal?:AbortSignal):Promise<T>{return (await this.fetch(path,{signal})).json();}
  async post<T>(path:string,body:unknown={},signal?:AbortSignal):Promise<T>{return (await this.fetch(path,{method:'POST',body:JSON.stringify(body),signal})).json();}
  async put<T>(path:string,body:unknown):Promise<T>{return (await this.fetch(path,{method:'PUT',body:JSON.stringify(body)})).json();}
  async remove(path:string){return (await this.fetch(path,{method:'DELETE'})).json();}
  async chat(body:ChatRequest,signal:AbortSignal,onEvent:(name:string,data:Record<string,unknown>)=>void):Promise<ChatResult>{
    const response=await this.fetch('/chat',{method:'POST',body:JSON.stringify(body),signal});
    if(!response.body)throw Error('Streaming response unavailable');
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',result:ChatResult|undefined;
    const consume=(block:string)=>{const lines=block.split('\n'),name=lines.find(l=>l.startsWith('event:'))?.slice(6).trim();const raw=lines.filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');if(!name||!raw)return;const data=JSON.parse(raw);onEvent(name,data);if(name==='error')throw Error(data.detail||'Local inference failed');if(name==='done')result=data;};
    try{while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value,{stream:!done}).replace(/\r\n/g,'\n');let index;while((index=buffer.indexOf('\n\n'))>=0){consume(buffer.slice(0,index));buffer=buffer.slice(index+2);}if(done)break;}if(buffer.trim())consume(buffer);if(!result)throw Error('Response interrupted. Partial output was not confirmed saved.');return result;}finally{reader.releaseLock();}
  }
}
export async function base64File(file:File){if(!file.size||file.size>8*1024*1024)throw Error('Files must be between 1 byte and 8 MB.');return new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Could not read file'));reader.readAsDataURL(file);});}
