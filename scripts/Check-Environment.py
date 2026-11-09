"""Required imports are checked separately from optional neural capabilities."""
import importlib
import json
import sys
required=['fastapi','uvicorn','numpy','scipy','nibabel','SimpleITK','skimage','PIL','psutil','jsonschema']
missing=[]
for name in required:
    try:importlib.import_module(name)
    except ImportError as e:missing.append(str(e))
print(json.dumps(dict(python=sys.version.split()[0],missing=missing,optional_neural='Install with Setup-Phase3B.ps1 -Neural or -Cuda'),indent=2))
sys.exit(bool(missing))
