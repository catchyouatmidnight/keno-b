import {sanitize} from '../../metrics.mjs';
export function JsonView({value}:{value:unknown}){return <pre className="max-h-[520px] overflow-auto rounded-lg border border-zinc-800 bg-zinc-950 p-3 font-mono text-[10px] leading-7 whitespace-pre-wrap break-words">{JSON.stringify(sanitize(value),null,2)}</pre>;}
