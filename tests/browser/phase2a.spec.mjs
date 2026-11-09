import {test,expect} from '../../frontend/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../..');
const shots=process.env.MEDSEG_ACCEPTANCE_SHOTS||root+'/docs/screenshots/phase2a';
const evidence=JSON.parse(fs.readFileSync(root+'/docs/phase2a/real-comparison.json','utf8'));
const extra=JSON.parse(fs.readFileSync(root+'/docs/phase2a/new-case.json','utf8'));
const API='http://127.0.0.1:8008/api/v1';
async function range(page,label,v){await page.getByLabel(label,{exact:true}).evaluate((el,v)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,String(v));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}))},v)}
async function start(page){await page.goto('/');await expect(page).toHaveTitle(/MedSeg-Lab/);await expect(page.getByTestId('stage-0')).toBeVisible();await expect(page.locator('.image-status')).toHaveCount(0);await page.getByRole('button',{name:'Algorithm Workbench',exact:true}).click();await expect(page.getByText('Local computation service connected',{exact:true})).toBeVisible();await expect(page.getByTestId('stage-10')).toBeVisible();await expect(page.locator('.image-status')).toHaveCount(0)}
async function pickVoxel(page,i,j){await expect(page.locator('.image-status')).toHaveCount(0);await expect(page.locator('.algorithm-ct .image-fit')).toHaveCSS('visibility','visible');const box=await page.locator('.algorithm-ct canvas').boundingBox();await page.mouse.click(box.x+(i+.5)/512*box.width,box.y+(511-j+.5)/512*box.height)}
function audit(page){const errors=[],remote=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))errors.push(m.text())});page.on('request',r=>{if(!/^http:\/\/127\.0\.0\.1:(5173|8008)\//.test(r.url())&&!r.url().startsWith('data:'))remote.push(r.url())});return {errors,remote}}

test('seed inverse mapping after real zoom/pan, ROI depth and clear, bilingual state',async({page})=>{
 const a=audit(page);await start(page);await range(page,'Algorithm axial slice',17);
 await page.getByTestId('stage-10').hover();await page.keyboard.down('Control');await page.mouse.wheel(0,-120);await page.keyboard.up('Control');
 const stage=await page.getByTestId('stage-10').boundingBox();await page.mouse.move(stage.x+stage.width/2,stage.y+stage.height/2);await page.mouse.down();await page.mouse.move(stage.x+stage.width/2+16,stage.y+stage.height/2-12,{steps:5});await page.mouse.up();
 await page.getByRole('button',{name:'Set seed',exact:true}).click();await pickVoxel(page,114,218);
 await expect(page.getByTestId('seed-readout')).toContainText('114, 218, 17');
 const manifest=JSON.parse(fs.readFileSync(root+'/frontend/public/demo/spleen_8/case.json','utf8'));
 const ras=manifest.spatial.affine.slice(0,3).map(r=>r[0]*114+r[1]*218+r[2]*17+r[3]);for(const v of ras)await expect(page.getByTestId('seed-world')).toContainText(v.toFixed(2));
 await page.getByRole('button',{name:'Reset view',exact:true}).click();await range(page,'Algorithm axial slice',8);await page.getByRole('button',{name:'Set ROI corners',exact:true}).click();await pickVoxel(page,62,140);await range(page,'Algorithm axial slice',26);await pickVoxel(page,215,338);
 for(const [label,value] of Object.entries({i0:62,i1:216,j0:140,j1:339,k0:8,k1:27}))await expect(page.getByLabel('ROI '+label,{exact:true})).toHaveValue(String(value));
 await page.getByRole('button',{name:'中文',exact:true}).click();await expect(page.getByRole('button',{name:'运行传统 V2',exact:true})).toBeEnabled();await expect(page.getByTestId('seed-readout')).toContainText('114, 218, 17');await page.screenshot({path:shots+'/phase2a-seed-zh.png'});
 await page.getByRole('button',{name:'清除 Seed / ROI',exact:true}).click();await expect(page.getByLabel('Seed i',{exact:true})).toHaveValue('');await expect(page.getByRole('button',{name:'运行传统 V2',exact:true})).toBeDisabled();expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});

test('real V2 browser submission, progress, completion, open analysis, export',async({page,request})=>{
 const a=audit(page);await start(page);await page.getByRole('button',{name:'Load archived CT-only selection',exact:true}).click();
 const response=page.waitForResponse(r=>r.url()===API+'/jobs'&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Run Traditional V2',exact:true}).click();const submitted=await (await response).json();
 await expect(page.getByRole('button',{name:'Run Traditional V2',exact:true})).toBeDisabled();await expect(page.getByRole('heading',{name:'Run status: completed',exact:true})).toBeVisible({timeout:120000});
 const actual=await (await request.get(API+'/jobs/'+submitted.run_id)).json();expect(actual.result.foreground_voxels).toBe(118846);expect(actual.result.metrics.dice_3d).toBe(evidence[0].dice);
 const exported=await request.get(API+'/runs/'+submitted.run_id+'/export');expect(exported.status()).toBe(200);expect((await exported.body()).subarray(0,2).toString()).toBe('PK');
 await page.getByRole('button',{name:'Open in analysis workspace',exact:true}).click();await expect(page.getByRole('heading',{name:'Segmentation Comparison',exact:true})).toBeVisible();await expect(page.locator('.case-source')).toContainText('Interactive Experimental Run');await expect(page.getByTestId('metric-dice_3d')).toHaveText('0.7814');await expect(page.locator('.image-status')).toHaveCount(0);
 await page.screenshot({path:shots+'/phase2a-real-v2.png'});expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});

test('real E17 browser inference with cancellation and retry CPU',async({page,request})=>{
 const a=audit(page);await start(page);await page.getByRole('button',{name:'U-Net Inference',exact:true}).click();
 let response=page.waitForResponse(r=>r.url()===API+'/jobs'&&r.request().method()==='POST');await page.getByRole('button',{name:'Run U-Net Inference',exact:true}).click();const first=await (await response).json();
 await page.getByRole('button',{name:'Cancel task',exact:true}).click();await expect(page.getByRole('heading',{name:'Run status: cancelled',exact:true})).toBeVisible();
 expect((await (await request.get(API+'/jobs/'+first.run_id)).json()).status).toBe('cancelled');
 await page.getByRole('button',{name:'中文',exact:true}).click();await expect(page.getByRole('alert')).toContainText('用户已取消；计算进程已停止');await page.getByRole('button',{name:'EN',exact:true}).click();
 await page.getByLabel('Device',{exact:true}).selectOption('cpu');response=page.waitForResponse(r=>r.url()===API+'/jobs'&&r.request().method()==='POST');await page.getByRole('button',{name:'Run U-Net Inference',exact:true}).click();const next=await (await response).json();
 await expect(page.getByRole('heading',{name:'Run status: completed',exact:true})).toBeVisible({timeout:120000});
 const result=(await (await request.get(API+'/jobs/'+next.run_id)).json()).result;expect(result.device).toBe('cpu');expect(result.checkpoint_sha256).toBe(evidence[1].checkpoint_sha256);expect(result.foreground_voxels).toBe(106192);
 await page.screenshot({path:shots+'/phase2a-e17-complete.png'});expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});

test('persistent history, two-run comparison, errors and real 3D',async({page})=>{
 const a=audit(page);await start(page);await page.getByRole('button',{name:'Run History',exact:true}).click();await page.reload();await page.getByRole('button',{name:'Algorithm Workbench',exact:true}).click();await page.getByRole('button',{name:'Run History',exact:true}).click();
 const ids=[evidence[0].run_id,evidence[1].run_id];for(const id of ids)await page.getByLabel('Compare '+id,{exact:true}).check();
 await page.getByRole('button',{name:'Compare selected runs',exact:true}).click();await expect(page.getByLabel('Analysis method',{exact:true}).locator('option')).toHaveCount(4);await expect(page.locator('.image-status')).toHaveCount(0);
 await page.getByRole('button',{name:'Spatial errors',exact:true}).click();await expect(page.locator('.chart-panel')).toBeVisible();await page.getByLabel('Analysis method',{exact:true}).selectOption('run_'+ids[0].replaceAll('-','_'));await expect(page.getByTestId('metric-dice_3d')).toHaveText('0.7814');await expect(page.locator('.image-status')).toHaveCount(0);
 await page.getByRole('button',{name:'3D surfaces',exact:true}).click();await expect(page.locator('.surface-footer')).toContainText('Real surfaces loaded',{timeout:60000});await page.screenshot({path:shots+'/phase2a-run-compare-3d.png'});
 expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});

test('additional real spleen3 result opens and local-only responsive panels',async({page})=>{
 const a=audit(page);await start(page);await page.getByRole('button',{name:'Run History',exact:true}).click();const row=page.locator('tr').filter({has:page.getByRole('button',{name:extra.run_id.slice(0,8),exact:true})});await row.getByRole('button',{name:'Open',exact:true}).click();
 await expect(page.locator('.work-heading')).toContainText(extra.case_id);await expect(page.getByTestId('metric-dice_3d')).toHaveText('0.8567');await expect(page.locator('.image-status')).toHaveCount(0);await page.screenshot({path:shots+'/phase2a-new-case.png'});
 await page.getByRole('button',{name:'Algorithm Workbench',exact:true}).click();for(const [width,height] of [[1366,768],[390,844]]){await page.setViewportSize({width,height});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:shots+`/phase2a-${width}.png`,fullPage:width===390})}
 expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});

test('real CT-only import and V2 output have volume and no overlap or FP metrics',async({page,request})=>{
 const a=audit(page);await start(page);await page.getByText('Register local CT (optional GT)',{exact:true}).click();
 const cid='nogt_'+Date.now();await page.getByLabel('Input ID',{exact:true}).fill(cid);await page.getByLabel('CT path',{exact:true}).fill(process.env.MEDSEG_TEST_CT || (()=>{throw Error('Set MEDSEG_TEST_CT to an authorized external CT')})());
 await page.getByRole('button',{name:'Register CT',exact:true}).click();await expect(page.getByLabel('Algorithm input',{exact:true})).toHaveValue(cid);await expect(page.locator('.image-status')).toHaveCount(0);
 for(const [label,value] of Object.entries({'Seed i':114,'Seed j':218,'Seed k':17,'ROI i0':62,'ROI i1':216,'ROI j0':140,'ROI j1':339,'ROI k0':8,'ROI k1':27}))await page.getByLabel(label,{exact:true}).fill(String(value));
 const response=page.waitForResponse(r=>r.url()===API+'/jobs'&&r.request().method()==='POST');await page.getByRole('button',{name:'Run Traditional V2',exact:true}).click();const submitted=await (await response).json();
 await expect(page.getByRole('heading',{name:'Run status: completed',exact:true})).toBeVisible({timeout:120000});const run=(await (await request.get(API+'/jobs/'+submitted.run_id)).json());expect(run.result.gt_available).toBe(false);expect(run.result.metrics).toBeNull();expect(run.result.foreground_voxels).toBe(118846);
 await page.getByRole('button',{name:'Open in analysis workspace',exact:true}).click();await expect(page.locator('.case-source')).toContainText('No GT');await expect(page.getByTestId('metric-dice_3d')).toHaveCount(0);await expect(page.locator('.legend')).not.toContainText('FP · false positive');await expect(page.locator('.legend')).not.toContainText('TP · overlap');await expect(page.getByText('Overlap metrics require GT',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Spatial errors',exact:true}).click();await expect(page.locator('.volume-analysis')).toContainText('549.487');await page.screenshot({path:shots+'/phase2a-no-gt.png'});
 expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);fs.writeFileSync((process.env.MEDSEG_REGRESSION_OUTPUT||root+'/docs/phase2a')+'/no-gt.json',JSON.stringify({case_id:cid,run_id:run.run_id,metrics:run.result.metrics,volume_ml:run.result.volume_ml},null,2));
});

test('disconnected backend preserves frozen 2D, errors and 3D',async({page})=>{
 await page.route('http://127.0.0.1:8008/**',r=>r.abort('connectionrefused'));await page.goto('/');await expect(page.getByTestId('stage-0')).toBeVisible();await page.getByRole('button',{name:'Algorithm Workbench',exact:true}).click();await expect(page.getByText('Local computation service disconnected',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Run Traditional V2',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'2D comparison',exact:true}).click();await range(page,'Synchronized axial slice',19);await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice','19');await expect(page.locator('.image-status')).toHaveCount(0);
 await page.getByRole('button',{name:'Spatial errors',exact:true}).click();await expect(page.locator('.chart-panel')).toBeVisible();await page.getByRole('button',{name:'3D surfaces',exact:true}).click();await expect(page.locator('.surface-footer')).toContainText('Real surfaces loaded',{timeout:60000});await page.screenshot({path:shots+'/phase2a-offline.png'});
});
