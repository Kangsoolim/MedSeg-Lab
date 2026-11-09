import {test,expect} from '../../frontend/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../..');
const catalog=JSON.parse(fs.readFileSync(root+'/frontend/public/training/catalog.json','utf8'));
const original=catalog.source_root;
const final=catalog.experiments.find(r=>r.experiment_id==='final27');
const shots=process.env.MEDSEG_SCREENSHOTS || '../tests/browser-results/phase2b-screenshots';
async function start(page,workspace='Training Analytics'){
 await page.addInitScript(()=>localStorage.setItem('medseg.language.v1','en'));
 await page.goto('/');await expect(page).toHaveTitle(/MedSeg-Lab/);await expect(page.getByTestId('stage-0')).toBeVisible();await page.getByRole('button',{name:workspace,exact:true}).click();await expect(page.getByRole('heading',{name:workspace,exact:true})).toBeVisible();
 await expect(page.locator('vite-error-overlay')).toHaveCount(0);
 await expect(page.locator('.research-workspace')).toContainText('Historical data only');
}
function audit(page){const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type())&&!/net::ERR_FAILED|Failed to fetch|Failed to load resource/.test(m.text()))errors.push(m.text())});return errors}
async function trainingReady(page){await expect(page.getByTestId('point-final27-17')).toBeVisible()}

test('real E17 E20 E27 values, checkpoint provenance and six empty predictions',async({page})=>{
 const errors=audit(page);await start(page);await trainingReady(page);await expect(page.locator('[data-testid^="point-final27-"]')).toHaveCount(27);
 for(const n of [17,20,27]){
  await page.getByRole('button',{name:'E'+n,exact:true}).click();const e=final.epochs.find(e=>e.epoch===n);const detail=page.getByTestId('epoch-detail');
  await expect(detail.getByRole('heading')).toHaveText('final27 · Epoch '+n);await expect(detail).toContainText(String(e.metrics.train_loss));await expect(detail).toContainText(String(e.metrics.val_mean_dice));
  await detail.getByText('Checkpoint metadata',{exact:true}).click();await expect(detail.locator('pre').first()).toContainText(e.checkpoint.sha256);
  if(n===20){await expect(detail).toContainText('Empty validation predictions: 6 / 6');await expect(detail).toContainText('Hypotheses, not established causes');await expect(detail.locator('tbody tr')).toHaveCount(6);for(const row of await detail.locator('tbody tr').all())await expect(row.locator('td').nth(5)).toHaveText('0');await page.screenshot({path:shots+'/phase2b-e20.png'})}
  if(n===27){await expect(detail).toContainText('Final patience count=10');await expect(detail).toContainText('min_delta=0.0001')}
 }
 await page.getByTestId('point-final27-17').click();await expect(page.getByTestId('epoch-detail').getByRole('heading')).toHaveText('final27 · Epoch 17');expect(errors).toEqual([]);
});

test('raw curve filter, zoom, hover, missing metric and source-preserving CSV/SVG downloads',async({page})=>{
 const errors=audit(page);await start(page);await trainingReady(page);await page.getByLabel('Metric',{exact:true}).selectOption('train_loss');
 await page.getByLabel('Epoch from',{exact:true}).fill('15');await expect(page.locator('[data-testid^="point-final27-"]')).toHaveCount(13);
 await page.getByTestId('point-final27-17').hover();await expect(page.locator('.training-readout')).toContainText(String(final.epochs[16].metrics.train_loss));
 await page.getByLabel('Raw data points',{exact:true}).uncheck();await expect(page.getByTestId('point-final27-18')).toHaveAttribute('fill','transparent');
 const svgPromise=page.waitForEvent('download');await page.getByRole('button',{name:'Export chart (SVG)',exact:true}).click();const svg=await svgPromise;const svgPath=root+'/docs/phase2b/exported-chart.svg';await svg.saveAs(svgPath);const text=fs.readFileSync(svgPath,'utf8');expect(text).toContain('<metadata>');expect(text).toContain('"smoothing":false');expect(text).toContain(final.split_id);
 const csvPromise=page.waitForEvent('download');await page.getByRole('button',{name:'Export metrics (CSV)',exact:true}).click();const csv=await csvPromise;const csvPath=root+'/docs/phase2b/exported-metrics.csv';await csv.saveAs(csvPath);const data=fs.readFileSync(csvPath,'utf8');expect(data).toContain('source_sha256');expect(data).toContain('0.890504926063714');expect(data).toContain('history.csv');expect(data).toContain('mean_patient_native_3d');
 await page.getByLabel('Metric',{exact:true}).selectOption('val_loss');await expect(page.locator('.training-chart')).toContainText('Not Recorded');expect(errors).toEqual([]);
});

test('separate branches, best epochs and descriptive multi-experiment comparison',async({page})=>{
 const errors=audit(page);await start(page);await trainingReady(page);await page.getByLabel('Compare old14',{exact:true}).check();await page.getByLabel('Compare shuffle14',{exact:true}).check();
 await expect(page.getByTestId('experiment-comparison').locator('tbody tr')).toHaveCount(3);await expect(page.locator('.research-workspace')).toContainText('check training budgets');
 await page.getByTestId('point-old14-11').click();await expect(page.getByTestId('epoch-detail').getByRole('heading')).toHaveText('old14 · Epoch 11');await expect(page.getByTestId('epoch-detail')).toContainText('Best validation model');
 await page.getByText('Verified training lineage and sources',{exact:true}).click();await expect(page.locator('.research-workspace')).toContainText('modified-code AMP continuation');await page.screenshot({path:shots+'/phase2b-comparison.png'});expect(errors).toEqual([]);
});

test('English default and Chinese controls retain the exact selected epoch',async({page})=>{
 const errors=audit(page);await start(page);await trainingReady(page);await page.getByRole('button',{name:'E20',exact:true}).click();await page.getByRole('button',{name:'中文',exact:true}).click();await expect(page.getByRole('heading',{name:'训练分析',exact:true})).toBeVisible();await expect(page.getByTestId('epoch-detail').getByRole('heading')).toHaveText('final27 · 轮次 20');await expect(page.getByRole('button',{name:'导出指标（CSV）',exact:true})).toBeVisible();await expect(page.getByTestId('epoch-detail')).toContainText('尚未确立根因');await page.screenshot({path:shots+'/phase2b-chinese.png'});await page.getByRole('button',{name:'EN',exact:true}).click();await expect(page.getByTestId('epoch-detail').getByRole('heading')).toHaveText('final27 · Epoch 20');expect(errors).toEqual([]);
});

test('unified experiment type, algorithm/date filters, sort and checkpoint detail',async({page,request})=>{
 const count=(await (await request.get('http://127.0.0.1:8008/api/v1/experiments')).json()).filter(r=>r.type==='training').length;const errors=audit(page);await start(page,'Experiments');await expect(page.locator('.algorithm-status')).toContainText('Local service connected');await page.getByLabel('Experiment type',{exact:true}).selectOption('training');await expect(page.getByTestId('experiment-list').locator('tbody tr')).toHaveCount(count);
 await page.getByLabel('Algorithm filter',{exact:true}).selectOption('MONAI 2D U-Net');await page.getByLabel('From date',{exact:true}).fill('2026-10-21');await page.getByLabel('To date',{exact:true}).fill('2026-10-21');await expect(page.getByTestId('experiment-list').locator('tbody tr')).toHaveCount(3);
 await page.getByLabel('Sort',{exact:true}).selectOption('name');await page.getByRole('button',{name:'final27',exact:true}).click();await expect(page.locator('.research-card[open] pre')).toContainText('966a5e59e57d82bd');expect(errors).toEqual([]);
});

test('existing inference runs retain E17 model link, comparable results reopen in 2D and 3D',async({page,request})=>{
 const errors=audit(page);const rows=await (await request.get('http://127.0.0.1:8008/api/v1/experiments')).json();const a=rows.find(r=>r.type==='inference'&&r.case_ids?.[0]==='spleen_8'&&r.manifest&&r.gt_available);const b=rows.find(r=>r.type==='traditional'&&r.case_ids?.[0]==='spleen_8'&&r.manifest&&r.gt_available);expect(a).toBeTruthy();expect(b).toBeTruthy();expect(a.training_experiment_id).toBe('final27');
 await start(page,'Experiments');await expect(page.locator('.algorithm-status')).toContainText('Local service connected');await page.getByLabel('Compare final27',{exact:true}).uncheck();for(const r of [a,b])await page.getByLabel('Compare '+r.experiment_id,{exact:true}).check();await expect(page.getByTestId('experiment-comparison').locator('tbody tr')).toHaveCount(2);await page.getByRole('button',{name:'Open comparable results in analysis',exact:true}).click();await expect(page.getByRole('heading',{name:'Segmentation Comparison',exact:true})).toBeVisible();await expect(page.locator('.image-status')).toHaveCount(0);await page.getByRole('button',{name:'3D surfaces',exact:true}).click();await expect(page.locator('.surface-stage canvas')).toBeVisible();expect(errors).toEqual([]);
});

test('different cases are marked not directly comparable and missing-GT metrics remain absent',async({page,request})=>{
 const rows=await (await request.get('http://127.0.0.1:8008/api/v1/experiments')).json();const a=rows.find(r=>r.type==='inference'&&r.case_ids?.[0]==='spleen_8'&&r.manifest);const b=rows.find(r=>r.type==='traditional'&&r.manifest&&!r.gt_available);expect(b).toBeTruthy();
 await start(page,'Experiments');await expect(page.locator('.algorithm-status')).toContainText('Local service connected');await page.getByLabel('Compare final27',{exact:true}).uncheck();for(const r of [a,b])await page.getByLabel('Compare '+r.experiment_id,{exact:true}).check();await expect(page.locator('.comparison')).toContainText('Not directly comparable');await expect(page.getByRole('button',{name:'Open comparable results in analysis',exact:true})).toBeDisabled();const row=page.getByTestId('experiment-comparison').locator('tbody tr').filter({hasText:b.experiment_id});await expect(row.locator('td').nth(6)).toHaveText('Not Recorded');
});

test('actual CSV import, duplicate rejection and browser reload recover all original 27 epochs',async({page})=>{
 const errors=audit(page);await start(page);await trainingReady(page);const id='qa_real_history_'+Date.now();await page.getByText('Import training history',{exact:true}).click();await page.getByLabel('Experiment ID',{exact:true}).fill(id);const raw=fs.readFileSync(path.join(original,final.sources[0].path),'utf8').trimEnd().split(/\r?\n/);const adapted=raw.map((line,i)=>line+','+(i===0?'source_stage,import_audit_id':final.epochs[i-1].stage+','+id)).join('\n');await page.getByLabel('Log file',{exact:true}).setInputFiles({name:'real_history_with_stage_and_import_audit_id.csv',mimeType:'text/csv',buffer:Buffer.from(adapted)});
 await page.getByLabel('Field mapping (canonical to input column)',{exact:true}).fill(JSON.stringify({epoch:'epoch',stage:'source_stage'}));await page.getByLabel('Wide metrics (optional name to column)',{exact:true}).fill(JSON.stringify({train_loss:'train_loss',val_mean_dice:'val_mean_dice',learning_rate:'learning_rate'}));await page.getByLabel('Metric definitions (required)',{exact:true}).fill(JSON.stringify(Object.fromEntries(['train_loss','val_mean_dice','learning_rate'].map(k=>[k,final.definitions[k]]))));await page.getByLabel('Metadata: dataset, split_id, case_ids, hyperparameters',{exact:true}).fill(JSON.stringify({dataset:final.dataset,split_id:final.split_id,case_ids:final.case_ids,hyperparameters:final.hyperparameters,qa:true,original_source:final.sources[0],adapter:'Original CSV values plus explicit verified source_stage column'}));
 await page.getByRole('button',{name:'Validate and persist import',exact:true}).click();await expect(page.locator('.import-log')).toContainText('Imported and saved: '+id,{timeout:130000});await page.getByRole('button',{name:'Validate and persist import',exact:true}).click();await expect(page.locator('.import-log')).toContainText('Experiment ID already exists');
 await page.reload();await page.getByRole('button',{name:'Training Analytics',exact:true}).click();await expect(page.getByLabel('Training experiment',{exact:true}).locator('option[value="'+id+'"]')).toHaveCount(1);await page.getByLabel('Training experiment',{exact:true}).selectOption(id);await expect(page.locator(`[data-testid^="point-${id}-"]`)).toHaveCount(27);await page.getByRole('button',{name:'E17',exact:true}).click();await expect(page.getByTestId('epoch-detail')).toContainText('0.890504926063714');expect(errors).toEqual([]);
});

test('offline reload retains real static curves and original frozen analysis',async({page})=>{
 if(!process.env.PHASE2B_ACTUAL_OFFLINE)await page.route('http://127.0.0.1:8008/**',route=>route.abort());await start(page);await trainingReady(page);await expect(page.locator('.algorithm-status')).toContainText('Offline: static training catalog');await page.getByRole('button',{name:'E20',exact:true}).click();await expect(page.getByTestId('epoch-detail')).toContainText('Empty validation predictions: 6 / 6');await page.getByText('Import training history',{exact:true}).click();await expect(page.getByRole('button',{name:'Validate and persist import',exact:true})).toBeDisabled();await page.screenshot({path:shots+'/phase2b-offline.png'});await page.getByRole('button',{name:'2D comparison',exact:true}).click();await expect(page.getByTestId('stage-0')).toBeVisible();await expect(page.locator('.image-status')).toHaveCount(0);
});

test('real saved E20 empty mask opens existing 2D and 3D without new inference',async({page})=>{
 const errors=audit(page);await start(page);await trainingReady(page);await page.getByRole('button',{name:'E20',exact:true}).click();await expect(page.locator('.algorithm-status')).toContainText('Local service connected');const row=page.getByTestId('epoch-detail').locator('tbody tr').filter({hasText:'spleen_9'});await row.getByRole('button',{name:'Open saved prediction',exact:true}).click();await expect(page.getByRole('heading',{name:'Segmentation Comparison',exact:true})).toBeVisible({timeout:150000});await expect(page.locator('.case-source')).toContainText('Historical saved prediction');await expect(page.getByTestId('metric-dice_3d')).toHaveText('0.0000');await expect(page.locator('.image-status')).toHaveCount(0);await page.getByRole('button',{name:'3D surfaces',exact:true}).click();await expect(page.locator('.surface-stage canvas')).toBeVisible();await page.screenshot({path:shots+'/phase2b-e20-real-mask.png'});expect(errors).toEqual([]);
});

test('desktop and mobile layouts keep new controls accessible without document overflow',async({page})=>{
 const errors=audit(page);await start(page);await trainingReady(page);await expect(page.locator('.algorithm-status')).toContainText('Local service connected');for(const size of [{width:1366,height:768},{width:390,height:844}]){await page.setViewportSize(size);await expect(page.getByLabel('Training experiment',{exact:true})).toBeVisible();const widths=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth}));expect(widths.scroll).toBeLessThanOrEqual(widths.width+1);await page.screenshot({path:shots+`/phase2b-${size.width}.png`})}expect(errors).toEqual([]);
});



test('controlled incompatible-unit metadata fixture keeps real values on separate axes',async({page})=>{
 // Negative metadata fixture in an isolated browser only; no persistent import or changed metric values.
 const fixture=structuredClone(catalog);fixture.experiments.find(r=>r.experiment_id==='old14').definitions.val_mean_dice.unit='incompatible unit (test fixture)';
 await page.route('**/training/catalog.json',route=>route.fulfill({json:fixture}));
 await page.route('http://127.0.0.1:8008/**',route=>route.abort());
 await start(page);await trainingReady(page);await page.getByLabel('Compare old14',{exact:true}).check();await expect(page.locator('.research-workspace')).toContainText('Different metric units: shown on separate axes.');await expect(page.getByTestId('training-chart')).toHaveCount(2);
});
