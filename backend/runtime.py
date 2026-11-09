"""Use the actual Windows interpreter, avoiding the venv redirector process.

Import paths preserve the active venv's packages. PID and OS resource ownership
therefore refer to the process executing the algorithm, rather than its launcher.
Call the returned executable with -S: the explicit PYTHONPATH carries the venv
packages; re-running site initialization would leak the base interpreter packages.
"""
import os
import sys
from pathlib import Path

def process_runtime():
    executable=getattr(sys,'_base_executable',sys.executable) if sys.platform=='win32' else sys.executable
    environment=dict(os.environ)
    paths=[str(Path(__file__).resolve().parents[1]),*(str(Path(p or os.getcwd()).absolute()) for p in sys.path)]
    environment['PYTHONPATH']=os.pathsep.join(dict.fromkeys(paths))
    return executable,environment

if __name__=='__main__':
    import json
    exe,env=process_runtime();print(json.dumps({'executable':exe,'pythonpath':env['PYTHONPATH']}))
