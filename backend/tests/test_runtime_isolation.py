"""A spawned base interpreter must see exactly the explicit environment paths."""
import json
import subprocess
import sys
from backend.runtime import process_runtime

def test_spawn_does_not_reinitialize_site_packages():
    executable,env=process_runtime()
    child=json.loads(subprocess.check_output([executable,'-S','-B','-c',"import json,sys; print(json.dumps({'path':sys.path,'no_site':sys.flags.no_site}))"],env=env,text=True))
    assert child['no_site']==1
    expected={p.casefold().replace('\\','/') for p in sys.path if p}
    assert all(p.casefold().replace('\\','/') in expected for p in child['path'] if 'site-packages' in p)
