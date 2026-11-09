"""Copy source-only working files to a separate ROOT and independently installed venv.

Does not copy Git state, ignored data, node_modules, config or environments.
Re-running refreshes source files only; it never deletes prior artifacts.
"""
from pathlib import Path
import subprocess
import shutil
ROOT=Path(__file__).resolve().parents[1]
target=ROOT/'.release-qa/clean-install'
if target.resolve().parent!= (ROOT/'.release-qa').resolve():raise ValueError('Invalid QA boundary')
target.mkdir(parents=True,exist_ok=True)
files=set()
for args in [('ls-files','-z'),('ls-files','--others','--exclude-standard','-z')]:
    files.update(subprocess.check_output(['git',*args],cwd=ROOT).decode().split('\0'))
for name in files-{''}:
    source=ROOT/name
    if not source.is_file():continue
    dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
print(target)
