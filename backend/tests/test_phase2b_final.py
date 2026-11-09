"""Negative metadata fixtures and real-log import checks for final acceptance."""
import csv,io,json,unittest,uuid,hashlib
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import ROOT,settings,sha,read
from backend.experiments import HistoryImport,normalize_import,export_csv
DEFS={'loss':{'definition':'Controlled metadata-only fixture, not medical results','unit':'loss','aggregation':'epoch'}}
def payload(**extra):
 return dict(experiment_id='final_fixture_'+uuid.uuid4().hex,format='json',content=json.dumps([{'epoch':1,'metric_name':'loss','metric_value':-.25}]),source_name='controlled.txt',definitions=DEFS)|extra
class StrictHistory(unittest.TestCase):
 def test_malformed_metadata_and_row_types_rejected(self):
  for metadata in [{'started_at':{}},{'case_ids':'abc'},{'case_ids':[1]},{'hyperparameters':[]},{'split_id':[]},{'ended_at':'bad-date'},{'device':False}]:
   with self.subTest(metadata=metadata),self.assertRaises(ValueError):normalize_import(HistoryImport(**payload(metadata=metadata)))
  for changes in [{'metric_name':[]},{'timestamp':{}},{'stage':[]},{'metric_value':True},{'metric_value':{}}]:
   content=json.dumps([dict(epoch=1,metric_name='loss',metric_value=.5)|changes])
   with self.subTest(changes=changes),self.assertRaises(ValueError):normalize_import(HistoryImport(**payload(content=content)))
 def test_truncated_csv_and_missing_mapped_column_rejected(self):
  for content,metrics in [('epoch,metric_name,metric_value\n1,loss',{}),('epoch,score\n1,.5',{'loss':'score','other':'absent'})]:
   with self.subTest(content=content),self.assertRaises(ValueError):normalize_import(HistoryImport(**payload(format='csv',content=content,metrics=metrics,definitions=DEFS|{'other':DEFS['loss']})))
 def test_export_formula_text_and_negative_numeric_value(self):
  r=normalize_import(HistoryImport(**payload(source_name=' \n=HYPERLINK("x")',content=json.dumps([{'epoch':1,'metric_name':'loss','metric_value':-.25,'stage':'  =1+1'}]))))
  rows=list(csv.DictReader(io.StringIO(export_csv(r))))
  self.assertEqual(rows[0]['metric_value'],'-0.25')
  self.assertTrue(rows[0]['source'].startswith("'"));self.assertTrue(rows[0]['stage'].startswith("'"))

class FinalAPI(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.cfg=settings();cls.cfg['runs']=str(ROOT/'runs'/('final_api_'+uuid.uuid4().hex));cls.app=create_app(cls.cfg);cls.client=TestClient(cls.app);cls.client.__enter__();cls.client.headers['X-MedSeg-Token']=cls.client.get('/api/v1/health').json()['token']
 @classmethod
 def tearDownClass(cls):cls.client.__exit__(None,None,None)
 def test_bad_import_does_not_pollute_and_returns_422(self):
  before={p:sha(p) for p in Path(self.cfg['runs']).glob('experiments/*/experiment.json')}
  for changes in [{'metadata':{'started_at':{}}},{'content':'[{"epoch":1,"metric_name":[],"metric_value":1}]'},{'content':'[{"epoch":1'}]:
   response=self.client.post('/api/v1/experiments/import',json=payload(**changes));self.assertEqual(response.status_code,422,response.text)
  self.assertEqual(before,{p:sha(p) for p in Path(self.cfg['runs']).glob('experiments/*/experiment.json')})
 def test_all_formats_real_values_source_receipt_and_conflict(self):
  source=Path(settings()['source_root'])/'outputs/unet_runs/unet_stage7_global_batch_shuffle_seed42/history.csv'
  original=list(csv.DictReader(source.open(encoding='utf-8-sig')))
  for fmt in ['csv','json','jsonl']:
   data=[{'epoch':int(r['epoch']),'loss':float(r['train_loss']),'format_audit':fmt} for r in original]
   if fmt=='csv':
    out=io.StringIO();w=csv.DictWriter(out,fieldnames=list(data[0]));w.writeheader();w.writerows(data);content=out.getvalue()
   elif fmt=='json':content=json.dumps(data)
   else:content='\n'.join(json.dumps(row) for row in data)
   body=payload(format=fmt,content=content,mapping={'epoch':'epoch'},metrics={'loss':'loss'},metadata={'original_source':str(source),'original_sha256':sha(source)})
   response=self.client.post('/api/v1/experiments/import',json=body);self.assertEqual(response.status_code,201,response.text);eid=body['experiment_id'];r=response.json()
   self.assertEqual([e['metrics']['loss'] for e in r['epochs']],[float(row['train_loss']) for row in original])
   self.assertEqual(self.client.post('/api/v1/experiments/import',json=body).status_code,409)
   self.assertEqual(self.client.post('/api/v1/experiments/import',json=body|{'content':content.replace(str(data[0]['loss']),'0.74',1)}).status_code,409)
   self.assertEqual(self.client.get(f'/api/v1/experiments/{eid}/source').text,content)
   export=self.client.get(f'/api/v1/experiments/{eid}/export').json();self.assertEqual(export,r)
 def test_actual_body_size_limit_with_chunked_payload(self):
  response=self.client.post('/api/v1/experiments/import',content=iter([b' '*600000,b' '*600000]),headers={'Content-Type':'application/json'})
  self.assertEqual(response.status_code,413)
 def test_ids_are_unique_across_training_inference_and_reference_types(self):
  from backend.config import write
  rid=str(uuid.uuid4());directory=Path(self.cfg['runs'])/rid
  case=next(iter(self.app.state.store.cases.values()))
  write(directory/'record.json',{'run_id':rid,'case_id':case['case_id'],'algorithm':'unet_e17','parameters':{},'status':'cancelled','created_at':'2026-11-06T00:00:00Z'})
  write(directory/'spec.json',{'input':case,'source_hashes':{}})
  frozen=next(r for r in self.client.get('/api/v1/experiments').json() if r['type']=='frozen')
  for eid in [rid,frozen['experiment_id']]:
   before=sha(directory/'record.json')
   response=self.client.post('/api/v1/experiments/import',json=payload(experiment_id=eid))
   self.assertEqual(response.status_code,409,response.text)
   self.assertEqual(sha(directory/'record.json'),before)
 def test_content_row_limits_and_nonfinite_metadata(self):
  for body in [payload(content='x'*1000001),payload(format='csv',content='epoch,value\n'+'\n'.join(f'{n},1' for n in range(20001)),mapping={'epoch':'epoch'},metrics={'loss':'value'})]:
   r=self.client.post('/api/v1/experiments/import',json=body);self.assertEqual(r.status_code,422,r.text[:100])
  with self.assertRaises(ValueError):normalize_import(HistoryImport(**payload(metadata={'hyperparameters':{'rate':float('inf')}})))
 def test_frozen_records_identify_the_selected_method(self):
  records=self.client.get('/api/v1/experiments').json()
  frozen=[r for r in records if r['type']=='frozen'];self.assertTrue(frozen)
  self.assertTrue(all(r.get('method_id') for r in frozen))


class MetricUnits(unittest.TestCase):
 def test_inference_volume_time_and_frozen_numeric_schema(self):
  cfg=settings();cfg['runs']=str(ROOT/'runs'/('final_units_'+uuid.uuid4().hex))
  with TestClient(create_app(cfg)) as client:
   records=client.get('/api/v1/experiments').json()
   frozen=next(r for r in records if r['type']=='frozen')
   self.assertTrue(all(v is None or isinstance(v,(int,float)) for v in frozen['metrics'].values()))
   self.assertNotIn('case_id',frozen['metrics'])
   values=list(csv.DictReader(io.StringIO(client.get('/api/v1/experiments/'+frozen['experiment_id']+'/export?format=csv').text)))
   self.assertEqual(next(r for r in values if r['metric_name']=='pred_volume_ml')['unit'],'mL')
   self.assertEqual(next(r for r in values if r['metric_name']=='tp_voxels')['unit'],'voxels')
   self.assertEqual(frozen['definitions']['runtime_seconds']['unit'],'s')

 def test_imported_analysis_is_not_mislabeled_as_frozen(self):
  from unittest.mock import patch
  from backend import experiments
  original_read=experiments.read
  index=original_read(ROOT/'frontend/public/demo/index.json');entry=index['cases'][0];target=ROOT/'frontend/public'/entry['manifest']
  manifest=original_read(target)
  def controlled_read(path):
   value=original_read(path)
   if Path(path)==target:
    for method in value['methods']:method['frozen_metrics']=None
   return value
  cfg=settings();cfg['runs']=str(ROOT/'runs'/('final_classification_'+uuid.uuid4().hex))
  with TestClient(create_app(cfg)) as client,patch('backend.experiments.read',side_effect=controlled_read):
   projected=client.get('/api/v1/experiments').json()
   for method in manifest['methods']:
    row=next(r for r in projected if r['experiment_id']=='frozen_'+entry['case_id']+'_'+method['id'])
    self.assertEqual(row['source_kind'],'imported_analysis');self.assertEqual(row['type'],'inference')
    self.assertEqual(row['metrics']['dice_3d'],method['analysis']['metrics']['dice_3d'])


class SharingRead(unittest.TestCase):
 def test_transient_windows_read_sharing_violation_is_retried(self):
  from unittest.mock import patch
  from backend.config import read
  with patch('pathlib.Path.read_text',side_effect=[PermissionError('controlled sharing violation'),'{"epoch":17}']) as reader,patch('backend.config.time.sleep'):
   self.assertEqual(read('controlled-test.json'),{'epoch':17});self.assertEqual(reader.call_count,2)
 def test_permanent_read_denial_is_bounded_and_corruption_is_not_hidden(self):
  from unittest.mock import patch
  from backend.config import read
  with patch('pathlib.Path.read_text',side_effect=PermissionError('controlled permanent denial')) as reader,patch('backend.config.time.sleep'):
   with self.assertRaises(PermissionError):read('controlled-test.json')
   self.assertEqual(reader.call_count,51)
  with patch('pathlib.Path.read_text',return_value='broken') as reader:
   with self.assertRaises(json.JSONDecodeError):read('controlled-test.json')
   self.assertEqual(reader.call_count,1)

 def test_job_api_reads_progress_through_transient_denials(self):
  from unittest.mock import patch
  from backend.config import write
  cfg=settings();cfg['runs']=str(ROOT/'runs'/('final_read_api_'+uuid.uuid4().hex));rid=str(uuid.uuid4())
  with TestClient(create_app(cfg)) as client:
   path=Path(cfg['runs'])/rid
   write(path/'record.json',{'run_id':rid,'case_id':'controlled_lifecycle_fixture','algorithm':'unet_e17','status':'running','parameters':{},'created_at':'2026-11-06T00:00:00Z'})
   write(path/'progress.json',{'stage':'controlled-progress-read'})
   original=Path.read_text;denied=[]
   def transient(p,*args,**kwargs):
    if p.name=='progress.json' and len(denied)<2:denied.append(1);raise PermissionError('controlled sharing denial')
    return original(p,*args,**kwargs)
   with patch('pathlib.Path.read_text',transient),patch('backend.config.time.sleep'):
    response=client.get('/api/v1/jobs/'+rid)
   self.assertEqual(response.status_code,200,response.text)
   self.assertEqual(response.json()['progress']['stage'],'controlled-progress-read');self.assertEqual(len(denied),2)
