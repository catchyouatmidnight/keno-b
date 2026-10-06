#!/usr/bin/env python3
"""Pinned public weights only; never reads or uploads user documents."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.request
REPO='Xenova/multilingual-e5-small'
REVISION='761b726dd34fb83930e26aab4e9ac3899aa1fa78'
FILES=['config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','quant_config.json','onnx/model_quantized.onnx']
root=Path(__file__).resolve().parents[1]/'models'/'embedding'/REPO

def verify(path,entry):
    if not path.exists() or path.stat().st_size!=entry['size']:return False
    data=path.read_bytes()
    actual=hashlib.sha256(data).hexdigest() if entry.get('lfs') else hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    expected=entry['lfs']['sha256'] if entry.get('lfs') else entry['blobId']
    return actual==expected

metadata=json.load(urllib.request.urlopen(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true',timeout=30))
entries={s['rfilename']:s for s in metadata['siblings']}
root.mkdir(parents=True,exist_ok=True)
missing=[name for name in FILES if not verify(root/name,entries[name])]
if shutil.disk_usage(root).free<sum(entries[f]['size'] for f in missing)+128*1024*1024:raise SystemExit('Not enough free disk space')
for name in missing:
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True);temporary=target.with_suffix(target.suffix+'.part')
    try:
        with urllib.request.urlopen(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}',timeout=120) as response,temporary.open('wb') as output:
            while chunk:=response.read(1024*1024):output.write(chunk)
        if not verify(temporary,entries[name]):raise ValueError('Model size/checksum mismatch')
        os.replace(temporary,target);print('Verified '+name,flush=True)
    finally:temporary.unlink(missing_ok=True)
(root/'keno-model-manifest.json').write_text(json.dumps({'repo':REPO,'revision':REVISION,'files':FILES},indent=2))
print('Local embedding model ready. No personal data was sent.')
