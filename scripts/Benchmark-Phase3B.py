"""Source/Git/license and controlled performance audit. Writes only private evidence."""
import sys,json,re,subprocess,uuid,time,statistics,importlib.metadata as md
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from backend.config import settings,write,read,sha
from backend.service import Store
from backend.training_service import TrainingManager
from backend.training_adapter import EventWriter

def git(*args):return subprocess.check_output(['git',*args],cwd=R)
def measure(fn):
    values=[]
    for _ in range(3):
        start=time.perf_counter();result=fn();values.append(time.perf_counter()-start)
    return dict(median_seconds=statistics.median(values),samples=values,count=len(result) if isinstance(result,list) else result)

if sys.argv[-1]=='perf':
    cfg=settings();cfg.update(source_root='',checkpoint='',runs=str(R/'runs'/('phase3b_scale_'+uuid.uuid4().hex)))
    s=Store(cfg);s.training=TrainingManager(s)
    rid=str(uuid.uuid4());d=s.training.path(rid);d.mkdir();write(d/'record.json',dict(run_id=rid,status='completed',created_at='2026-11-09'))
    writer=EventWriter(d)
    for i in range(5000):writer.emit('batch',epoch=i//100+1,train_loss=1.,message='Controlled telemetry scale fixture; not medical training')
    def baseline(after=0):
        files=sorted(s.training.path(rid,'events').glob('*.json'));selected=[p for p in files if int(p.stem)>after]
        return [read(s.training.path(rid,'events',p.name)) for p in selected[:500]]
    def full():return [read(s.training.path(rid,'events',p.name)) for p in sorted((d/'events').glob('*.json'))]
    first=time.perf_counter();s.index.events(rid);cold=time.perf_counter()-first
    result=dict(fixture='5000 controlled batch events; no research results',cold_index_seconds=cold,before_page=measure(lambda:baseline(4500)),after_page=measure(lambda:s.index.events(rid,4500)),before_projection=measure(full),after_projection=measure(lambda:s.index.projection_events(rid)))
    from backend.storage import listing
    for i in range(200):
        run=str(uuid.uuid4());write(s.path(run,'record.json'),dict(run_id=run,status='completed',created_at='2026-11-09T00:00:00Z',parameters={'controlled_fixture':[0]*1000}))
    result['runs_page']=measure(lambda:listing(s,kind='inference',limit=25)['items'])
    result['runs_total']=listing(s,kind='inference',limit=25)['total']
    write(R/'docs/phase3b/performance.json',result);s.training.close();s.close();print(json.dumps(result,indent=2));sys.exit()

