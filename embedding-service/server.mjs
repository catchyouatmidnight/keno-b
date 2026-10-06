import http from 'node:http';
import {pipeline,env} from '@huggingface/transformers';
env.allowRemoteModels=false;
env.allowLocalModels=true;
env.localModelPath=process.env.KENO_EMBED_MODEL_ROOT||'/models/';
env.useBrowserCache=false;
env.useFSCache=false;
const MODEL='Xenova/multilingual-e5-small';
let extractor,busy=false;
try{extractor=await pipeline('feature-extraction',MODEL,{dtype:'q8',device:'cpu',session_options:{intraOpNumThreads:2,interOpNumThreads:1}});}
catch{process.stderr.write('Embedding model not loaded. Run download-embedding.py and restart.\n');}
export const server=http.createServer(async(req,res)=>{
  const reply=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(data));};
  if(req.method==='GET'&&req.url==='/health')return reply(extractor?200:503,{ready:!!extractor,model:MODEL,dimensions:384});
  if(req.method!=='POST'||req.url!=='/embed')return reply(404,{error:'Not found'});
  if(!extractor)return reply(503,{error:'Local embedding model unavailable'});
  if(busy)return reply(429,{error:'Embedding service busy'});
  busy=true;
  try{
    let body='',bytes=0;
    for await(const chunk of req){bytes+=chunk.length;if(bytes>100000)throw Error('Too large');body+=chunk;}
    const data=JSON.parse(body);
    if(!Array.isArray(data.texts)||data.texts.length<1||data.texts.length>16||!['query','passage'].includes(data.kind)||data.texts.some(t=>typeof t!=='string'||t.length>2000||!t.trim()))throw Error('Invalid request');
    const result=await extractor(data.texts.map(t=>data.kind+': '+t),{pooling:'mean',normalize:true,truncation:true,max_length:512});
    reply(200,{model:MODEL,dimensions:384,vectors:result.tolist()});
  }catch{reply(422,{error:'Embedding request failed'});}finally{busy=false;}
});
server.requestTimeout=120000;
server.listen(Number(process.env.KENO_EMBED_PORT||8080),'0.0.0.0');
