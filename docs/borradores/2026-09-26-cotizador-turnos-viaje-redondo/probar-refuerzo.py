"""Recrea el candidato y prueba solo SQLite temporal y transporte simulado."""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, tempfile

root=Path(__file__).resolve().parent
manifest=json.loads((root/'manifest-bandeja.json').read_text())
base=Path(manifest['base_path'])
def sha(b): return hashlib.sha256(b).hexdigest()

with tempfile.TemporaryDirectory(prefix='cotizador-refuerzo-') as folder:
    candidate=Path(folder)
    for name,hashes in manifest['files'].items():
        content=(base/name).read_bytes()
        if sha(content)!=hashes['before_sha256']:
            raise RuntimeError('El código base cambió; revisar el parche antes de reproducir: '+name)
        dest=candidate/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
    patch=str(root/'cotizador-bandeja.patch')
    subprocess.run(['git','apply','--check',patch],cwd=candidate,check=True,capture_output=True,text=True)
    subprocess.run(['git','apply',patch],cwd=candidate,check=True,capture_output=True,text=True)
    for name,hashes in manifest['files'].items():
        assert sha((candidate/name).read_bytes())==hashes['after_sha256'],name
    shutil.copy2(root/'refuerzo.test.mjs',candidate/'test/refuerzo.test.mjs')
    tests=subprocess.run(['node','--disable-warning=ExperimentalWarning','--experimental-loader',str(root/'loader-sdk-local.mjs'),
        '--test',*[str(p) for p in sorted((candidate/'test').glob('*.test.mjs'))]],cwd=candidate,capture_output=True,text=True)
    if tests.returncode:
        raise RuntimeError(tests.stdout+'\n'+tests.stderr)
    env=dict(os.environ,COTIZADOR_STORE=str(candidate/'src/store.js'))
    probe=subprocess.run(['node',str(root/'verificar-borrador.mjs')],env=env,cwd=candidate,check=True,capture_output=True,text=True)
    diagnostic=json.loads(probe.stdout)
    assert diagnostic['summary']['gap']==0,diagnostic
    def count(label):
        matches=re.findall(r'(?:ℹ|#) '+label+r' (\d+)',tests.stdout)
        assert matches,(label,tests.stdout)
        return int(matches[-1])
    result={'status':'draft_verified_not_applied','tests':count('tests'),'pass':count('pass'),'fail':count('fail'),
        'diagnostic':diagnostic,'test_output':tests.stdout,
        'live_plugin_unchanged':all(sha((base/f).read_bytes())==h['before_sha256'] for f,h in manifest['files'].items()),
        'live_api_requests':0,'real_channel_messages':0,'live_database_writes':0}
    assert result['live_plugin_unchanged']
    print(json.dumps(result,indent=2,ensure_ascii=False))
