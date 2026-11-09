"""One disposable process per job: cancellation terminates real computation."""
import os
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('MKL_NUM_THREADS', '4')
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from backend.config import read, write

def main():
    out = Path(sys.argv[1]).resolve()
    spec = read(out/'spec.json')
    def stage(name, **values):
        event = dict(stage=name, at=datetime.now(timezone.utc).isoformat(), **values)
        write(out/'progress.json', event)
        print(event, flush=True)
    try:
        from backend.algorithms import execute
        execute(spec, out, stage)
    except BaseException as error:
        write(out/'error.json', {'type':type(error).__name__, 'message':str(error), 'traceback':traceback.format_exc()})
        traceback.print_exc()
        raise SystemExit(1)

if __name__ == '__main__': main()
