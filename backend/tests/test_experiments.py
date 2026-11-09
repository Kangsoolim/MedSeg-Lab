"""Phase 2B source accuracy, import validation and backward-compatible persistence."""
import csv
import importlib.util
import json
import unittest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import ROOT, read, sha, settings
from backend.experiments import HistoryImport, TrainingEvent, normalize_import, static_catalog

DEFS={'val_mean_dice':{'definition':'Fixture only: patient Dice','unit':'ratio','aggregation':'mean_patient'}}

def body(**changes):
    value=dict(experiment_id='fixture_'+uuid.uuid4().hex,format='csv',source_name='controlled-test-fixture.csv',
               content='epoch,metric_name,metric_value\n1,val_mean_dice,0.5\n2,val_mean_dice,\n',definitions=DEFS)
    value.update(changes);return value

class ImportValidation(unittest.TestCase):
    def test_missing_values_remain_null_and_sources_preserved(self):
        result=normalize_import(HistoryImport(**body()))
        self.assertIsNone(result['epochs'][1]['metrics']['val_mean_dice'])
        self.assertEqual(result['epochs'][0]['sources']['val_mean_dice']['line'],2)
        self.assertEqual(len(result['sources'][0]['sha256']),64)
        self.assertTrue(result['warnings'])

    def test_long_json_jsonl_and_wide_mapping(self):
        rows=[{'round':1,'score':0.5},{'round':2,'score':0.6}]
        for fmt,content in [('json',json.dumps(rows)),('jsonl','\n'.join(json.dumps(r) for r in rows)),('csv','round,score\n1,0.5\n2,0.6')]:
            value=normalize_import(HistoryImport(**body(format=fmt,content=content,mapping={'epoch':'round'},metrics={'val_mean_dice':'score'})))
            self.assertEqual([e['metrics']['val_mean_dice'] for e in value['epochs']],[.5,.6])

    def test_reject_nonfinite_duplicate_conflicting_and_invalid_rows(self):
        contents=['epoch,metric_name,metric_value\n1,val_mean_dice,NaN','epoch,metric_name,metric_value\n1,val_mean_dice,Infinity',
                  'epoch,metric_name,metric_value\n1,val_mean_dice,0.5\n1,val_mean_dice,0.6',
                  'epoch,metric_name,metric_value\n-1,val_mean_dice,0.5','epoch,metric_name,metric_value\n1.5,val_mean_dice,0.5',
                  'epoch,metric_name,metric_value\n1,unknown,1','epoch,metric_value\n1,1',
                  'epoch,metric_name,metric_value\n1,val_mean_dice,','epoch,metric_name,metric_value,experiment_id\n1,val_mean_dice,0.5,wrong']
        for content in contents:
            with self.subTest(content=content),self.assertRaises(ValueError):normalize_import(HistoryImport(**body(content=content)))
        for fmt,content in [('json','{broken'),('json','{}'),('jsonl','{"bad":')]:
            with self.assertRaises(ValueError):normalize_import(HistoryImport(**body(format=fmt,content=content)))

    def test_duplicate_headers_json_keys_conflicting_timestamps_and_reserved_ids(self):
        for options in [
            {'content':'epoch,metric_name,metric_value,metric_value\n1,val_mean_dice,0.2,0.5'},
            {'format':'json','content':'[{"epoch":1,"metric_name":"val_mean_dice","metric_value":0.2,"metric_value":0.5}]'},
            {'content':'epoch,metric_name,metric_value,timestamp\n1,val_mean_dice,0.5,2026-10-21T00:00:00Z\n1,other,0.6,2026-10-22T00:00:00Z','definitions':{**DEFS,'other':DEFS['val_mean_dice']}},
            {'experiment_id':'CON'}]:
            with self.subTest(options=options),self.assertRaises(ValueError):normalize_import(HistoryImport(**body(**options)))

    def test_jsonl_physical_lines_and_json_record_index_are_not_fabricated(self):
        content='\n'+json.dumps({'epoch':1,'metric_name':'val_mean_dice','metric_value':0.5})+'\n'
        result=normalize_import(HistoryImport(**body(format='jsonl',content=content)))
        self.assertEqual(result['epochs'][0]['sources']['val_mean_dice']['line'],2)
        result=normalize_import(HistoryImport(**body(format='json',content=json.dumps([{'epoch':1,'metric_name':'val_mean_dice','metric_value':0.5}]))))
        source=result['epochs'][0]['sources']['val_mean_dice']
        self.assertNotIn('line',source)
        self.assertEqual(source['record_index'],1)

    def test_definition_and_future_event_contract(self):
        with self.assertRaises(ValueError):normalize_import(HistoryImport(**body(definitions={'val_mean_dice':{'unit':'ratio'}})))
        self.assertEqual(TrainingEvent(run_id='test',epoch=1,event_type='metric',metric_name='loss',metric_value=1).epoch,1)
        with self.assertRaises(ValueError):TrainingEvent(run_id='../bad',epoch=1,event_type='metric')
        with self.assertRaises(ValueError):TrainingEvent(run_id='test',epoch=1,event_type='metric',metric_value=float('nan'))

class SourceAccuracy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=static_catalog();cls.source=Path(settings()['source_root'])
        if not cls.catalog['experiments']:raise unittest.SkipTest('Generate real local training catalog first')

    def test_all_epochs_match_independently_read_original_csv(self):
        for experiment in self.catalog['experiments']:
            source=self.source/experiment['sources'][0]['path']
            rows=list(csv.DictReader(source.open(encoding='utf-8-sig')))
            self.assertEqual(len(rows),len(experiment['epochs']))
            for original,normalized in zip(rows,experiment['epochs'],strict=True):
                self.assertEqual(int(original['epoch']),normalized['epoch'])
                for metric in ['train_loss','val_mean_dice','learning_rate','val_empty_cases','bad_epochs']:
                    self.assertEqual(float(original[metric]),normalized['metrics'][metric])
            self.assertNotIn('val_loss',experiment['definitions'])

    def test_key_epochs_patient_counts_and_real_assets(self):
        final=next(r for r in self.catalog['experiments'] if r['experiment_id']=='final27')
        e17,e20,e27=[next(e for e in final['epochs'] if e['epoch']==n) for n in [17,20,27]]
        self.assertAlmostEqual(e17['metrics']['val_mean_dice'],.890504926063714,places=14)
        self.assertEqual(max(final['epochs'],key=lambda e:e['metrics']['val_mean_dice'])['epoch'],17)
        self.assertEqual(len(e20['patients']),6);self.assertTrue(all(p['pred_voxels']==0 for p in e20['patients']))
        self.assertEqual(e20['metrics']['val_mean_dice'],0)
        self.assertEqual(e20['metrics']['epoch_amp_skipped_steps'],5)
        import nibabel as nib
        import numpy as np
        for prediction in e20['predictions']:
            image=nib.load(self.source/prediction['path'])
            self.assertEqual(int(np.count_nonzero(np.asanyarray(image.dataobj))),0)
        self.assertEqual(len(e20['predictions']),6);self.assertEqual(e20['checkpoint']['epoch'],20)
        self.assertEqual(e27['metrics']['bad_epochs'],10)
        self.assertEqual(final['early_stopping']['patience'],10);self.assertEqual(final['early_stopping']['min_delta'],.0001)
        self.assertEqual(final['early_stopping']['monitor'],'val_mean_dice')
        self.assertIn('early_stopping',e27['flags'])
        for e in [e17,e20,e27]:
            v=read(self.source/e['sources']['patient_metrics']['path'])
            self.assertEqual(v['rows'],e['patients'])
            self.assertAlmostEqual(sum(p['dice_3d'] for p in v['rows'])/6,e['metrics']['val_mean_dice'],places=14)
            for p in e['predictions']:self.assertEqual(sha(self.source/p['path']),p['sha256'])

    def test_lineage_keeps_old_branch_separate_and_soft_dice_gap(self):
        final=next(r for r in self.catalog['experiments'] if r['experiment_id']=='final27')
        self.assertEqual({e['stage'] for e in final['epochs']},{'legacy3','amp4','shared9','shuffle14','final27'})
        self.assertNotIn('old14',{e['stage'] for e in final['epochs']})
        self.assertIsNone(final['epochs'][1]['metrics']['soft_dice_native_3d_mean'])
        self.assertTrue(self.catalog['lineage_verification']['checkpoint_history_exact'])
        self.assertTrue(all(e['history_exact'] for e in self.catalog['lineage']))
        self.assertTrue(all(self.catalog['lineage_verification']['full_device_restore'].values()))

class ExperimentAPI(unittest.TestCase):
    def setUp(self):
        self.cfg=settings();self.directory=ROOT/'runs'/('phase2b_test_'+uuid.uuid4().hex);self.cfg['runs']=str(self.directory)
        self.app=create_app(self.cfg);self.client=TestClient(self.app);self.client.__enter__()
        self.client.headers['X-MedSeg-Token']=self.client.get('/api/v1/health').json()['token']
    def tearDown(self):self.client.__exit__(None,None,None)
    def test_import_duplicate_export_and_restart_recovery(self):
        value=body();response=self.client.post('/api/v1/experiments/import',json=value)
        self.assertEqual(response.status_code,201,response.text);record=response.json();eid=value['experiment_id']
        self.assertEqual(self.client.post('/api/v1/experiments/import',json=value).status_code,409)
        value2={**value,'experiment_id':'different_id'}
        self.assertEqual(self.client.post('/api/v1/experiments/import',json=value2).status_code,409)
        exported=self.client.get(f'/api/v1/experiments/{eid}/export?format=csv')
        rows=list(csv.DictReader(exported.text.splitlines()));self.assertEqual(rows[0]['source_sha256'],record['sources'][0]['sha256'])
        self.assertEqual(rows[1]['metric_value'],'');self.assertTrue(rows[0]['definition']);self.assertTrue(rows[0]['metadata_json'])
        self.assertEqual(self.client.get(f'/api/v1/experiments/{eid}/export').json(),record)
        self.client.__exit__(None,None,None)
        self.app=create_app(self.cfg);self.client=TestClient(self.app);self.client.__enter__()
        self.assertEqual(self.client.get(f'/api/v1/experiments/{eid}').json(),record)
        path=self.directory/'experiments'/eid/'experiment.json';path.write_text('broken',encoding='utf-8')
        self.assertEqual(self.client.get(f'/api/v1/experiments/{eid}').json(),record)
        self.assertTrue(list(path.parent.glob('experiment.corrupt.*.json')))

    def test_legacy_history_projection_never_rewrites_original_records(self):
        from backend.config import write
        rid=str(uuid.uuid4());directory=self.directory/rid;directory.mkdir()
        case=next(iter(self.app.state.store.cases.values()))
        record={'run_id':rid,'case_id':case['case_id'],'algorithm':'unet_e17','parameters':{},'status':'completed','created_at':'2026-10-21T00:00:00Z','started_at':None,'ended_at':None,'result':{'checkpoint_sha256':'966a5e59e57d82bd9813ea411735b82256fe6be7114af2d9cde655684d6bfee4','metrics':None,'gt_available':False}}
        write(directory/'record.json',record);write(directory/'spec.json',{'input':case,'source_hashes':{}})
        digest=sha(directory/'record.json')
        rows=self.client.get('/api/v1/experiments').json();projection=next(r for r in rows if r['experiment_id']==rid)
        self.assertEqual(projection['type'],'inference');self.assertIsNone(projection['metrics'].get('dice_3d'))
        self.assertEqual(projection['training_experiment_id'],'final27');self.assertEqual(sha(directory/'record.json'),digest)
        self.assertEqual(self.client.get('/api/v1/runs').json()[0]['run_id'],rid)

    def test_security_invalid_files_and_unavailable_historical_assets(self):
        self.assertEqual(self.client.post('/api/v1/experiments/import',json=body(),headers={'X-MedSeg-Token':''}).status_code,403)
        self.assertEqual(self.client.post('/api/v1/experiments/import',json=body(experiment_id='../escape')).status_code,422)
        self.assertEqual(self.client.post('/api/v1/experiments/import',json=body(content='broken')).status_code,422)
        self.assertEqual(self.client.get('/api/v1/experiments/unknown').status_code,404)
        self.assertEqual(self.client.post('/api/v1/experiments/final27/epochs/20/analysis/not_a_case').status_code,404)
        self.assertEqual(self.client.get('/api/v1/historical/bad/files/case.json').status_code,404)
