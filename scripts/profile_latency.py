#!/usr/bin/env python3
"""Profile Keno-B latency on the deployed host without external dependencies."""
import argparse, json, os, time, urllib.request

def request(url, key, path, payload):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url.rstrip("/") + path, data=data, headers={"Content-Type":"application/json","Authorization":"Bearer "+key})
    with urllib.request.urlopen(req, timeout=600) as response:
        return json.loads(response.read())

def pct(values, p):
    if not values: return None
    data=sorted(values); pos=(len(data)-1)*p; lo=int(pos); hi=min(len(data)-1,lo+1)
    return data[lo]+(data[hi]-data[lo])*(pos-lo)

def fmt(value, suffix="s"):
    return "—" if value is None else f"{value:.3f}{suffix}"

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default=os.environ.get("KENO_URL","http://127.0.0.1:18081/api/v1"))
    parser.add_argument("--key",default=os.environ.get("KENO_SERVER_KEY",""))
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--prompt",default="Explain in one concise paragraph why the sky appears blue.")
    args=parser.parse_args()
    if not args.key: raise SystemExit("Set KENO_SERVER_KEY or pass --key")
    rows=[]
    for mode in ("fast","balanced","deep"):
        for index in range(args.repeats):
            session=request(args.url,args.key,"/conversations",{"title":f"Latency profile {mode} {index+1}"})
            started=time.perf_counter()
            result=request(args.url,args.key,"/chat",{"conversation_id":session["id"],"message":args.prompt,"request_id":f"profile-{mode}-{time.time_ns()}","stream":False,"max_tokens":256,"execution_mode":mode,"attachment_ids":[],"library_document_ids":[]})
            elapsed=time.perf_counter()-started; context=result.get("context",{})
            rows.append({"mode":mode,"wall":elapsed,"first":context.get("first_token_seconds"),"total":context.get("total_seconds"),"prompt_eval":context.get("prompt_eval_seconds"),"generation":context.get("generation_seconds"),"retrieval":context.get("context_retrieval_seconds",context.get("retrieval_seconds")),"tok_s":context.get("generation_tokens_per_second")})
    print("mode       n   first p50/p95      total p50/p95      prompt     generation  retrieval   tok/s")
    for mode in ("fast","balanced","deep"):
        items=[r for r in rows if r["mode"]==mode]
        vals=lambda key:[float(r[key]) for r in items if isinstance(r.get(key),(int,float))]
        speed=pct(vals("tok_s"),.5)
        print(f"{mode:<10} {len(items):<3} {fmt(pct(vals('first'),.5)):>7}/{fmt(pct(vals('first'),.95)):<7}  {fmt(pct(vals('total'),.5)):>7}/{fmt(pct(vals('total'),.95)):<7}  {fmt(pct(vals('prompt_eval'),.5)):>8}  {fmt(pct(vals('generation'),.5)):>10}  {fmt(pct(vals('retrieval'),.5)):>9}  {('—' if speed is None else f'{speed:.1f}')}")
    print("\nJSON:")
    print(json.dumps(rows,indent=2))
if __name__=="__main__": main()
