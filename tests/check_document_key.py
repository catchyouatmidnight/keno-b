"""Dependency-light executable checks for environment keys and legacy migration."""
import ast
from contextlib import contextmanager,redirect_stdout
import getpass
import importlib.util
import io
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('document_key_script',ROOT/'scripts/document-key.py')
script=importlib.util.module_from_spec(spec);spec.loader.exec_module(script)
class HTTPException(Exception):
    def __init__(self,status_code,detail):self.status_code=status_code;self.detail=detail
scope=dict(globals(),KEY_MARKER=script.MARKER,KEY_CHECK=script.CHECK)
source=ast.parse((ROOT/'app/library.py').read_text())
exec(compile(ast.Module(body=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in {'initialize','seal','unseal','document_key'}],type_ignores=[]),'app/library.py','exec'),scope)


def check():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);env=root/'.env';database=root/'keno.db';env.write_text('KENO_API_KEY=test-only\nKENO_DOCUMENT_KEY=\nPORT=18081\n')
        @contextmanager
        def db():
            with sqlite3.connect(database) as c:yield c
        scope['main']=lambda:SimpleNamespace(db=db)
        def run(*flags,password=None):
            output=io.StringIO()
            with patch.object(sys,'argv',['document-key.py','--env',str(env),'--database',str(database),*flags]),patch.object(getpass,'getpass',return_value=password),redirect_stdout(output):script.run()
            return output.getvalue()
        text=run();value=re.search(r'^KENO_DOCUMENT_KEY=(.*)$',env.read_text(),re.M)[1]
        assert len(value)==64 and value not in text and env.stat().st_mode&0o777==0o600
        before=env.read_bytes();run();assert env.read_bytes()==before
        with patch.dict(os.environ,{'KENO_DOCUMENT_KEY':value}):key=scope['document_key']();assert key.hex()==value
        with patch.dict(os.environ,{'KENO_DOCUMENT_KEY':'cd'*32}):
            try:scope['document_key']()
            except HTTPException as e:assert e.status_code==503
            else:raise AssertionError('Wrong key accepted')
        env.write_text('KENO_API_KEY=test-only\n')
        try:run()
        except SystemExit:pass
        else:raise AssertionError('Missing existing key regenerated')
        assert 'KENO_DOCUMENT_KEY' not in env.read_text()
        # Legacy migration: wrong password changes nothing; correct password keeps documents.
        old=secrets.token_bytes(32);salt=secrets.token_bytes(16)
        wrapping=Scrypt(salt=salt,length=32,n=32768,r=8,p=1).derive(b'previous-password-123')
        with db() as c:
            c.execute('UPDATE vault_config SET salt=?,wrapped=?',(salt,scope['seal'](wrapping,old,'keno-vault-key-v1')))
            c.execute('INSERT INTO vault_documents VALUES (?,?)',('one',scope['seal'](old,b'private record','document:one')))
            c.execute('INSERT INTO vault_originals VALUES (?,?)',('one',scope['seal'](old,b'private original','original:one')))
        original=database.read_bytes();env_before=env.read_bytes()
        for flags,password in [((),None),(('--migrate-legacy','--backend-stopped'),'wrong-password')]:
            try:run(*flags,password=password)
            except SystemExit:pass
            else:raise AssertionError('Legacy access incorrectly migrated')
            assert database.read_bytes()==original and env.read_bytes()==env_before
        run('--migrate-legacy','--backend-stopped',password='previous-password-123')
        value=re.search(r'^KENO_DOCUMENT_KEY=(.*)$',env.read_text(),re.M)[1]
        with patch.dict(os.environ,{'KENO_DOCUMENT_KEY':value}):
            key=scope['document_key']();assert key==old
            with db() as c:
                for table,prefix,expected in [('vault_documents','document:','private record'),('vault_originals','original:','private original')]:
                    record=c.execute('SELECT payload FROM '+table).fetchone()[0]
                    assert scope['unseal'](key,record,prefix+'one').decode()==expected
        run();assert value in env.read_text()
    print('Persistent key, blank env entry, permissions, no secret output, key mismatch, lost-key protection and legacy migration checks passed.')


if __name__=='__main__':check()
