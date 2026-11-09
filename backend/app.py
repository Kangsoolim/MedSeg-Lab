"""Local HTTP API. No medical data is uploaded outside this machine."""
import mimetypes
import os
import shutil
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from backend.config import ROOT, settings
from backend.contracts import JobRequest, ImportRequest
from backend.service import Store, BusyError
from backend.experiments import HistoryImport, import_history, unified_records, export_csv

ORIGINS = ['http://127.0.0.1:5173','http://127.0.0.1:4173','http://localhost:5173']

def create_app(cfg=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(cfg or settings())
        from backend.training_service import TrainingManager
        app.state.store.training = TrainingManager(app.state.store)
        yield
        app.state.store.training.close()
        app.state.store.close()
    app = FastAPI(title='MedSeg-Lab local computation',lifespan=lifespan)
    app.add_middleware(CORSMiddleware,allow_origins=ORIGINS,allow_methods=['GET','POST','DELETE'],allow_headers=['Content-Type','X-MedSeg-Token'])
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

    @app.middleware('http')
    async def local_boundary(request: Request, call_next):
        origin = request.headers.get('origin')
        if origin and origin not in ORIGINS:
            return JSONResponse({'detail':'Origin is not an allowed local frontend'},status_code=403)
        if request.method in ('POST','DELETE') and request.headers.get('x-medseg-token') != request.app.state.store.token:
            return JSONResponse({'detail':'Local session token required; reconnect to health endpoint'},status_code=403)
        limit=1100000 if request.url.path == '/api/v1/experiments/import' else 65536
        try:declared=int(request.headers.get('content-length','0'))
        except ValueError:return JSONResponse({'detail':'Invalid Content-Length'},status_code=422)
        if declared<0:return JSONResponse({'detail':'Invalid Content-Length'},status_code=422)
        if declared>limit:return JSONResponse({'detail':f'Request body exceeds {limit} bytes / 请求体超限'},status_code=413)
        if request.method in ('POST','DELETE'):
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>limit:return JSONResponse({'detail':f'Request body exceeds {limit} bytes / 请求体超限'},status_code=413)
                chunks.append(chunk)
            request._body=b''.join(chunks)
        response = await call_next(request)
        response.headers['Cache-Control']='no-store'
        return response

    @app.exception_handler(ValueError)
    async def invalid(request,error):
        return JSONResponse({'detail':str(error)},status_code=409 if isinstance(error,BusyError) else 422)

    @app.exception_handler(FileNotFoundError)
    async def missing(request,error):
        return JSONResponse({'detail':str(error)},status_code=404)

    @app.get('/api/v1/health')
    def health(request: Request):
        s = request.app.state.store
        return dict(status='ok',service_pid=os.getpid(),api_edition='phase3b',version='phase2a-v1',token=s.token,active=s.active['id'] if s.active else None,
                    capabilities=__import__('backend.capabilities',fromlist=['capabilities']).capabilities(s.cfg),checkpoint_exists=bool(s.cfg.get('checkpoint')) and Path(s.cfg['checkpoint']).is_file(),storage_warnings=s.storage_warnings,limits={k:s.cfg[k] for k in ['max_voxels','max_file_bytes','max_storage_bytes','timeout_seconds']})

    @app.get('/api/v1/storage')
    def storage_list(request: Request,kind: str='',status: str='',since: str='',until: str='',offset: int=0,limit: int=50,archived: str=''):
        from backend.storage import listing
        return listing(request.app.state.store,kind,status,since,until,offset,limit,archived)

    @app.get('/api/v1/storage/{kind}/{rid}')
    def storage_plan(kind: str,rid: str,request: Request):
        from backend.storage import plan
        return plan(request.app.state.store,kind,rid)

    @app.post('/api/v1/storage/{kind}/{rid}/{action}')
    def storage_action(kind: str,rid: str,action: str,request: Request,confirm: str='',plan_sha256: str=''):
        from backend.storage import operate
        return operate(request.app.state.store,kind,rid,action,confirm,plan_sha256)

    @app.get('/api/v1/cases')
    def cases(request: Request): return list(request.app.state.store.cases.values())

    @app.post('/api/v1/cases',status_code=201)
    def register(body: ImportRequest,request: Request): return request.app.state.store.register(body)

    @app.post('/api/v1/cases/{cid}/analysis')
    def aligned_analysis(cid: str,body: list[str],request: Request):
        from backend.import_analysis import analyze
        return analyze(request.app.state.store,cid,body)

    @app.get('/api/v1/inputs/{cid}/ct/{filename}')
    def preview(cid: str,filename: str,request: Request):
        import re
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',cid) or not re.fullmatch(r'\d{3,5}\.png',filename):
            raise HTTPException(404)
        return FileResponse(request.app.state.store.path('inputs',cid,'ct',filename))

    @app.get('/api/v1/runs')
    def history(request: Request): return request.app.state.store.list()

    @app.post('/api/v1/jobs',status_code=202)
    def submit(body: JobRequest,request: Request): return request.app.state.store.submit(body)

    @app.get('/api/v1/jobs/{rid}')
    def job(rid: str,request: Request): return request.app.state.store.get(rid)

    @app.post('/api/v1/jobs/{rid}/cancel')
    def cancel(rid: str,request: Request): return request.app.state.store.cancel(rid)

    @app.get('/api/v1/runs/{rid}/files/{file:path}')
    def artifact(rid: str,file: str,request: Request):
        store = request.app.state.store
        record = store.record(rid)
        if record['status'] != 'completed': raise HTTPException(409,'Only completed results are published')
        root = store.path(rid)
        target = store.path(rid,file)
        if not target.is_relative_to(root) or target.suffix not in ('.json','.png','.mesh','.gz') or not target.is_file():
            raise HTTPException(404,'Artifact unavailable')
        return FileResponse(target,media_type=mimetypes.guess_type(target)[0] or 'application/octet-stream')

    @app.get('/api/v1/runs/{rid}/export')
    def export(rid: str,request: Request):
        store = request.app.state.store
        if store.record(rid)['status'] != 'completed': raise HTTPException(409,'Run is not completed')
        out = store.path(rid)
        target = store.path(rid,'export.zip')
        # Export is generated explicitly, never copied into the course project.
        with store.lock:
            if not target.exists():
                temp=out/'export.zip.tmp'
                store.path(rid,'export.zip.tmp')
                with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
                    for file in out.iterdir():
                        store.path(rid,file.name)
                        if file.suffix in ('.json','.gz','.log'): z.write(file,file.name)
                temp.replace(target)
        return FileResponse(target,filename=f'medseg-{rid}.zip')

    @app.delete('/api/v1/runs/{rid}')
    def delete(rid: str,request: Request,confirm: str='',plan_sha256: str=''):
        store = request.app.state.store
        with store.lock:
            from backend.storage import operate
            operate(store,'inference',rid,'delete',confirm,plan_sha256)
        return {'deleted':rid}
    @app.get('/api/v1/experiments')
    def experiments(request: Request): return unified_records(request.app.state.store)

    @app.post('/api/v1/experiments/import',status_code=201)
    def history_import(body: HistoryImport,request: Request): return import_history(request.app.state.store,body)

    @app.get('/api/v1/experiments/{eid}')
    def experiment(eid: str,request: Request):
        record=next((r for r in unified_records(request.app.state.store) if r['experiment_id']==eid),None)
        if record is None: raise HTTPException(404,'Unknown experiment')
        return record

    @app.get('/api/v1/experiments/{eid}/source')
    def experiment_source(eid: str,request: Request):
        import hashlib
        from backend.config import read
        record=experiment(eid,request)
        if record.get('source_artifact')!='source.json':raise HTTPException(404,'Original import content unavailable / 原始导入内容不可用')
        payload=read(request.app.state.store.path('experiments',record['experiment_id'],'source.json'))
        content=payload['content']
        if hashlib.sha256(content.encode('utf-8')).hexdigest()!=record['sources'][0]['sha256']:raise HTTPException(409,'Imported source hash mismatch / 导入来源哈希不匹配')
        return Response(content,media_type='text/plain; charset=utf-8')

    @app.get('/api/v1/experiments/{eid}/export')
    def experiment_export(eid: str,request: Request,format: str='json'):
        record=experiment(eid,request)
        if format=='csv': return Response(export_csv(record),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=experiment.csv'})
        if format!='json': raise HTTPException(422,'Expected json or csv')
        return JSONResponse(record,headers={'Content-Disposition':'attachment; filename=experiment.json'})
    @app.post('/api/v1/experiments/{eid}/epochs/{epoch}/analysis/{case_id}')
    def historical_analysis(eid: str,epoch: int,case_id: str,request: Request):
        from backend.historical import open_historical
        return open_historical(request.app.state.store,eid,epoch,case_id)

    @app.get('/api/v1/historical/{key}/files/{file:path}')
    def historical_file(key: str,file: str,request: Request):
        import re
        from backend.config import read
        if not re.fullmatch(r'[a-f0-9]{32}',key): raise HTTPException(404)
        store=request.app.state.store
        manifest=store.path('historical',key,'case.json')
        if not manifest.exists() or read(manifest).get('result_status')!='historical_verified': raise HTTPException(409,'Historical package not ready')
        target=store.path('historical',key,file)
        if not target.is_file() or target.suffix not in ('.json','.png','.mesh'):raise HTTPException(404)
        return FileResponse(target)
    from backend.training_contracts import ResumePreflight, StartTraining

    @app.get('/api/v1/training/catalog')
    def training_catalog(request: Request):
        from backend.training_data import catalog
        return catalog(request.app.state.store)

    @app.post('/api/v1/training/preflight')
    def training_preflight(body: ResumePreflight,request: Request):
        return request.app.state.store.training.preflight(body)

    @app.post('/api/v1/training/runs',status_code=202)
    def training_start(body: StartTraining,request: Request):
        return request.app.state.store.training.start(body)

    @app.get('/api/v1/training/runs')
    def training_list(request: Request):
        return request.app.state.store.training.list()

    @app.get('/api/v1/training/runs/{rid}')
    def training_record(rid: str,request: Request):
        return request.app.state.store.training.projection(rid)

    @app.get('/api/v1/training/runs/{rid}/events')
    def training_events(rid: str,request: Request,after: int=0):
        if after<0:raise ValueError('Invalid event cursor / 事件游标无效')
        manager=request.app.state.store.training
        events=manager.events(rid,after)
        return dict(events=events,next_sequence=events[-1]['sequence'] if events else after)

    @app.post('/api/v1/training/runs/{rid}/stop')
    def training_stop(rid: str,request: Request):
        return request.app.state.store.training.stop(rid)

    @app.post('/api/v1/training/runs/{rid}/force')
    def training_force(rid: str,request: Request,confirm: str=''):
        if confirm!=rid:raise ValueError('Confirm Run ID; partial epoch may be lost / 需确认Run ID，可能丢失未保存轮次')
        manager=request.app.state.store.training
        record=manager.record(rid)
        if record['status']!='stopping':raise BusyError('Request graceful stop first / 请先请求安全停止')
        from datetime import datetime,timezone
        if (datetime.now(timezone.utc)-datetime.fromisoformat(record['stop_requested_at'])).total_seconds()<15:
            raise BusyError('Allow 15 seconds for graceful stop / 请先等待15秒安全停止')
        return manager.stop(rid,force=True)

    @app.get('/api/v1/training/runs/{rid}/logs')
    def training_logs(rid: str,request: Request):
        import json
        manager=request.app.state.store.training
        return Response('\n'.join(json.dumps(e,ensure_ascii=False) for e in manager.events(rid,0,None)),media_type='application/x-ndjson',
                        headers={'Content-Disposition':f'attachment; filename=training-{rid}.jsonl'})

    @app.get('/api/v1/training/runs/{rid}/export')
    def training_export(rid: str,request: Request):
        import uuid
        from backend.config import write
        store=request.app.state.store;manager=store.training
        with store.lock:
            record=manager.record(rid)
            if record['status'] in ('queued','preparing','running','stopping'):raise BusyError('Stop training before exporting / 导出前请先停止训练')
            directory=manager.path(rid)
            store.inspect_tree(directory)
            write(manager.path(rid,'experiment.json'),manager.projection(rid))
            target=manager.path(rid,'export.zip')
            temp=manager.path(rid,'export-'+uuid.uuid4().hex+'.tmp')
            with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
                for path in directory.rglob('*'):
                    relative=path.relative_to(directory)
                    if path.is_file() and path.suffix in ('.json','.pt','.gz','.csv') and 'mpl' not in relative.parts:
                        archive.write(manager.path(rid,str(relative)),str(relative))
            temp.replace(target)
        return FileResponse(target,filename=f'training-{rid}.zip')

    @app.post('/api/v1/training/runs/{rid}/preview/{epoch}/{cid}')
    def training_preview(rid: str,epoch: int,cid: str,request: Request):
        from backend.config import read,write,sha
        from data_tools.export_package import export_case
        store=request.app.state.store;manager=store.training
        run=manager.projection(rid)
        point=next((e for e in run['epochs'] if e['epoch']==epoch and e.get('preview_available')),None)
        if not point:raise HTTPException(404,'No preview generated for this Epoch / 此轮次未生成预览')
        spec=read(manager.path(rid,'spec.json'))
        if cid not in spec['data']['val_ids']:raise ValueError('Validation cases only / 仅限验证病例')
        # A committed checkpoint can precede its epoch_end event at crash time.
        # The child's verified inherited history authorizes the real ancestor
        # artifact even when that ancestor lacks the final telemetry event.
        while spec['resume'] and epoch<=spec['resume']['epoch']:
            rid=spec['resume']['run_id']
            spec=read(manager.path(rid,'spec.json'))
        entry=spec['data']['entries'][cid]
        for key in ('ct','gt'):
            if sha(entry[key])!=entry[key+'_sha256']:raise ValueError('Preview source changed / 预览来源已变化')
        mask=manager.path(rid,f'validation_epoch_{epoch:03d}',cid,'prediction.nii.gz')
        directory=manager.path(rid,'previews',str(epoch),cid)
        with store.lock:
            manifest=manager.path(rid,'previews',str(epoch),cid,'case.json')
            if manifest.exists():return read(manifest)
            store.capacity()
            package=export_case(dict(case_id=cid,ct=entry['ct'],gt=entry['gt'],predictions=[dict(id='live_unet',name='Validation prediction',version=rid+f' / E{epoch}',path=str(mask),color_key='unet')]),directory)
            base=f'http://127.0.0.1:8008/api/v1/training/runs/{rid}/files/previews/{epoch}/{cid}'
            package.update(asset_base=base,mesh_base=base+'/meshes',result_status='interactive_experimental',
                           training_source=dict(run_id=rid,epoch=epoch,prediction_sha256=sha(mask),scope='full native 3D validation case'))
            write(manifest,package)
            return package

    @app.get('/api/v1/training/runs/{rid}/files/{file:path}')
    def training_asset(rid: str,file: str,request: Request):
        if not file.startswith('previews/'):raise HTTPException(404)
        path=request.app.state.store.training.path(rid,file)
        if not path.is_file() or path.suffix not in ('.json','.png','.mesh'):raise HTTPException(404)
        return FileResponse(path)

    return app

app = create_app()
