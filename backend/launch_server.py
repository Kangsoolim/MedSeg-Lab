"""Owned launcher shutdown channel; never accepts commands from HTTP."""
import sys
import threading
import time
import uvicorn
from backend.config import ROOT, run_path

if __name__=='__main__':
    stop=run_path(ROOT/'runs',ROOT/'runs'/sys.argv[1])
    server=uvicorn.Server(uvicorn.Config('backend.app:app',host='127.0.0.1',port=8008))
    def watch():
        while not server.should_exit:
            if stop.exists():server.should_exit=True;return
            time.sleep(.2)
    threading.Thread(target=watch,daemon=True).start()
    try:server.run()
    finally:stop.unlink(missing_ok=True)
