#!/usr/bin/env python3
"""Create one persistent document key without printing it; optionally migrate a stopped legacy library."""
import argparse
import getpass
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile

MARKER=b'env-key-v1'
CHECK=b'keno-document-key-v1'
AAD=b'keno-document-key-check-v1'


def save_env(path,text,key):
    lines=text.splitlines()
    output=[line for line in lines if not re.match(r'^\s*(?:export\s+)?KENO_DOCUMENT_KEY\s*=',line)]
    output.append('KENO_DOCUMENT_KEY='+key.hex())
    owner=path.stat()
    fd,name=tempfile.mkstemp(prefix='.keno-env-',dir=path.parent)
    try:
        if os.geteuid()==0:os.fchown(fd,owner.st_uid,owner.st_gid)
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as stream:stream.write('\n'.join(output)+'\n')
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env',type=Path,default=Path('.env'))
    parser.add_argument('--database',type=Path,default=Path('data/keno.db'))
    parser.add_argument('--migrate-legacy',action='store_true')
    parser.add_argument('--backend-stopped',action='store_true')
    args=parser.parse_args()
    if not args.env.is_file():raise SystemExit('Create .env using setup.sh first')
    text=args.env.read_text()
    values=re.findall(r'^[ \t]*(?:export[ \t]+)?KENO_DOCUMENT_KEY[ \t]*=[ \t]*([^\n]*)',text,re.M)
    if len(values)>1:raise SystemExit('Remove duplicate KENO_DOCUMENT_KEY entries; no key was changed')
    value=values[0].strip().strip('"\'') if values else ''
    if value and not re.fullmatch(r'[0-9a-fA-F]{64}',value):raise SystemExit('Existing KENO_DOCUMENT_KEY is invalid; no key was changed')
    key=bytes.fromhex(value) if value else None
    row=None;has_documents=False
    if args.database.parent.exists() and not os.access(args.database.parent,os.R_OK|os.X_OK):
        raise SystemExit('Database directory is unreadable. Run sudo python3 scripts/document-key.py; no key was changed.')
    if args.database.exists():
        with sqlite3.connect('file:'+str(args.database)+'?mode=ro',uri=True) as c:
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'vault_config' in tables:row=c.execute('SELECT salt,wrapped FROM vault_config WHERE id=1').fetchone()
            if 'vault_documents' in tables:has_documents=bool(c.execute('SELECT 1 FROM vault_documents LIMIT 1').fetchone())
    if row and row[0]!=MARKER:
        if not args.migrate_legacy or not args.backend_stopped:
            raise SystemExit('Legacy password library found. Back up, stop backend, then run with --migrate-legacy --backend-stopped. No key was changed.')
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
            from cryptography.exceptions import InvalidTag
        except ImportError:raise SystemExit('Migration needs Python cryptography installed; no key was changed')
        password=getpass.getpass('Previous document password (hidden): ')
        wrapping=Scrypt(salt=row[0],length=32,n=32768,r=8,p=1).derive(password.encode())
        try:old=AESGCM(wrapping).decrypt(row[1][:12],row[1][12:],b'keno-vault-key-v1')
        except InvalidTag:raise SystemExit('Incorrect previous password; no key was changed')
        key=key or old
        def seal(data,aad):
            nonce=os.urandom(12);return nonce+AESGCM(key).encrypt(nonce,data,aad)
        with sqlite3.connect(args.database) as c:
            c.execute('BEGIN IMMEDIATE')
            for table,prefix in [('vault_documents','document:'),('vault_originals','original:')]:
                for identity,payload in c.execute('SELECT id,payload FROM '+table).fetchall():
                    try:plain=AESGCM(old).decrypt(payload[:12],payload[12:],(prefix+identity).encode())
                    except InvalidTag:raise SystemExit('Legacy document failed authentication; migration rolled back')
                    c.execute('UPDATE '+table+' SET payload=? WHERE id=?',(seal(plain,(prefix+identity).encode()),identity))
            # Write the key before committing DB changes. Interrupted migration can be rerun.
            save_env(args.env,text,key)
            c.execute('UPDATE vault_config SET salt=?,wrapped=? WHERE id=1',(MARKER,seal(CHECK,AAD)))
        print('Legacy documents migrated. Recreate backend to load the environment key.')
        return
    if not key:
        if row or has_documents:raise SystemExit('Existing encrypted library needs its original KENO_DOCUMENT_KEY. Restore that key; no replacement was generated.')
        key=secrets.token_bytes(32);save_env(args.env,text,key)
        print('Created persistent document key in .env. Keep it with your backups.')
    else:
        os.chmod(args.env,0o600)
        print('Keeping existing document key.')


if __name__=='__main__':run()
