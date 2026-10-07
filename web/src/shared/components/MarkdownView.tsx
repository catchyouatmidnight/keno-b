import {Button,Collapse,Space,Tag} from 'antd';
import {Copy,ExternalLink,FileText} from 'lucide-react';
import {isValidElement,type ReactNode} from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type {Context,Source} from '../types';

function safeUrl(url?:string){try{const parsed=new URL(url||'');return ['http:','https:'].includes(parsed.protocol)?parsed.href:undefined;}catch{return undefined;}}
function CodeBlock({children}:{children:ReactNode}){const child=Array.isArray(children)?children[0]:children;let language='code',plain='';if(isValidElement(child)){const props=child.props as {className?:string;children?:ReactNode};language=(props.className||'').replace(/^language-/,'')||'code';plain=String(props.children||'').replace(/\n$/,'');}return <div className="my-3 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950"><div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2 font-mono text-[10px] text-zinc-500"><span>{language}</span><Button type="text" size="small" icon={<Copy size={13}/>} onClick={()=>void navigator.clipboard.writeText(plain)}>Copy</Button></div><pre className="overflow-auto p-3 font-mono text-xs leading-6">{children}</pre></div>;}

export function MarkdownView({text,sources=[],onSource}:{text:string;sources?:Source[];onSource?:(source:Source)=>void}){
 const content=text.replace(/\[(S\d+)\](?!\()/g,(match,id)=>sources.some(source=>source.source_id===id)?`[${id}](#source-${id})`:match);
 return <div className="break-words text-[14px] leading-7 text-zinc-100"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
  p:({children})=><p className="mb-3 last:mb-0">{children}</p>,h1:({children})=><h1 className="my-4 text-xl font-semibold">{children}</h1>,h2:({children})=><h2 className="my-4 text-lg font-semibold">{children}</h2>,h3:({children})=><h3 className="my-3 text-base font-semibold">{children}</h3>,ul:({children})=><ul className="my-3 list-disc space-y-1 pl-6">{children}</ul>,ol:({children})=><ol className="my-3 list-decimal space-y-1 pl-6">{children}</ol>,blockquote:({children})=><blockquote className="my-3 border-l-2 border-zinc-700 pl-4 text-zinc-400">{children}</blockquote>,table:({children})=><div className="my-3 overflow-x-auto"><table className="min-w-full text-left text-xs">{children}</table></div>,th:({children})=><th className="border-b border-zinc-700 p-2 text-zinc-400">{children}</th>,td:({children})=><td className="border-b border-zinc-800 p-2 align-top">{children}</td>,a:({href,children})=>{const source=href?.startsWith('#source-')?sources.find(item=>item.source_id===href.slice(8)):undefined;return source?<Button type="link" size="small" className="!h-auto !p-0" onClick={()=>onSource?.(source)}>{children}</Button>:<a className="text-zinc-200 underline underline-offset-2" href={href} target="_blank" rel="noopener noreferrer">{children}</a>;},img:({alt})=><span className="text-zinc-500">[Image: {alt||'external image disabled'}]</span>,pre:({children})=><CodeBlock>{children}</CodeBlock>}}>{content}</ReactMarkdown></div>;
}

export function Sources({context,onSource}:{context:Context;onSource:(source:Source)=>void}){
 const list=[...(context.document_sources||[]),...(context.visual_sources||[])],unique=list.filter((source,index)=>list.findIndex(other=>other.attachment_id===source.attachment_id&&other.page===source.page&&other.chunk===source.chunk)===index),web=context.web_sources||[],verify=context.web_verification as {verified_from?:number;conflict?:boolean;status?:string;cache_hit?:boolean}|undefined,count=unique.length+web.length;
 if(!count&&!verify)return null;
 const label=<Space size={6}>Sources · {count}{(verify?.verified_from||0)>=2&&<Tag>Verified from {verify?.verified_from}</Tag>}{verify?.conflict&&<Tag>Conflict</Tag>}{verify?.cache_hit&&<Tag>Cached</Tag>}</Space>;
 return <Collapse ghost size="small" className="!mt-3" items={[{key:'sources',label,children:<Space wrap>{unique.map((source,index)=><Button size="small" icon={<FileText size={12}/>} key={index} onClick={()=>onSource(source)}>{source.name}{source.page?` · p.${source.page}`:source.locator?` · ${source.locator}`:''}</Button>)}{web.map((source,index)=><Button key={index} size="small" icon={<ExternalLink size={12}/>} href={safeUrl(source.url)} target="_blank">{source.title||source.url}</Button>)}</Space>}]} />;
}
