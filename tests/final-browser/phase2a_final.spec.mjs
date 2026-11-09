import {test,expect} from '../../frontend/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../..'),out=root+'/docs/phase2a-final';
const evidence=JSON.parse(fs.readFileSync(out+'/independent-api.json','utf8'));
const shots=out+'/screenshots';fs.mkdirSync(shots,{recursive:true});
const API='http://127.0.0.1:8008/api/v1',source=evidence.spatial;
function audit(page){const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['warning','error'].includes(m.type()))errors.push(m.text())});return errors}
async function ready(page){await expect(page.locator('.image-status')).toHaveCount(0)}
async function start(page){await page.goto('/');await expect(page).toHaveTitle(/MedSeg-Lab/);await ready(page);await page.getByRole('button',{name:'Algorithm Workbench',exact:true}).click();await expect(page.getByText('Local computation service connected',{exact:true})).toBeVisible();await ready(page)}
async function range(page,k){await page.getByLabel('Algorithm axial slice',{exact:true}).evaluate((el,v)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,String(v));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}))},k);await expect(page.getByTestId('stage-10')).toHaveAttribute('data-slice',String(k));await ready(page)}
async function choose(page,p,index=10){
 const stage=page.getByTestId('stage-'+index);await stage.scrollIntoViewIfNeeded();await ready(page);
 const bounds=await stage.boundingBox(),image=await stage.locator('canvas').boundingBox();
 // Independent forward projection of the known source voxel center. The
 // application performs inverse picking; expected geometry comes from NiBabel.
 const x=image.x+(p[0]+.5)/source.shape[0]*image.width,y=image.y+(source.shape[1]-p[1]-.5)/source.shape[1]*image.height;
 expect(x).toBeGreaterThan(bounds.x);expect(x).toBeLessThan(bounds.x+bounds.width);expect(y).toBeGreaterThan(bounds.y);expect(y).toBeLessThan(bounds.y+bounds.height);
 await page.mouse.click(x,y);
 const actual=await Promise.all(['i','j','k'].map(axis=>page.getByLabel('Seed '+axis,{exact:true}).inputValue()));expect(actual.map(Number)).toEqual(p);
 const world=source.canonical_affine.slice(0,3).map(row=>row[0]*p[0]+row[1]*p[1]+row[2]*p[2]+row[3]);for(const mm of world)await expect(page.getByTestId('seed-world')).toContainText(mm.toFixed(2));
 return {expected:p,actual:actual.map(Number),ras_mm:world,stage:index,bounds,image,click:[x,y],transform:await stage.getAttribute('data-transform')};
}

test('independent CT coordinates across fit, zoom, pan, slices, single/dual/quad, sidebar and resize',async({page})=>{
 const errors=audit(page);await start(page);const records=[];
 for(const [width,height] of [[1920,1080],[1366,768]]){
  await page.setViewportSize({width,height});await page.getByRole('button',{name:'Hide cases',exact:true}).click();await page.getByRole('button',{name:'Show cases',exact:true}).click();
  for(const layout of [1,2,4]){
   await page.getByRole('button',{name:{1:'Single',2:'Dual',4:'Quad'}[layout],exact:true}).click();
   for(const [mode,p] of [['fit',[75,100,2]],['in',[390,330,12]],['out',[114,218,25]]]){
    await range(page,p[2]);await page.getByRole('button',{name:'Reset view',exact:true}).click();await page.getByRole('button',{name:'Pan / zoom',exact:true}).click();
    const target=page.getByTestId('stage-'+(10+layout-1));await target.scrollIntoViewIfNeeded();await target.hover();
    if(mode!=='fit'){await page.keyboard.down('Control');for(let i=0;i<3;i++)await page.mouse.wheel(0,mode==='in'?-100:100);await page.keyboard.up('Control')}
    const b=await target.boundingBox();await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2+22,b.y+b.height/2-13,{steps:4});await page.mouse.up();
    await page.getByRole('button',{name:'Set seed',exact:true}).click();records.push({width,height,layout,mode,...await choose(page,p,10+layout-1)});
    // Repeat exactly the same anatomical anchor through every transformation.
    await range(page,17);await page.getByRole('button',{name:'Set seed',exact:true}).click();records.push({width,height,layout,mode,anchor:true,...await choose(page,[114,218,17],10+layout-1)});
   }
  }
 }
 await page.getByRole('button',{name:'Single',exact:true}).click();await page.getByRole('button',{name:'Reset view',exact:true}).click();await range(page,8);await page.getByRole('button',{name:'Set ROI corners',exact:true}).click();
 async function roiPoint(i,j){const stage=page.getByTestId('stage-10');await stage.scrollIntoViewIfNeeded();await ready(page);const b=await stage.locator('canvas').boundingBox();await page.mouse.click(b.x+(i+.5)/512*b.width,b.y+(511-j+.5)/512*b.height)}
 await roiPoint(62,140);await range(page,26);await roiPoint(215,338);for(const [axis,value] of Object.entries({i0:62,i1:216,j0:140,j1:339,k0:8,k1:27}))await expect(page.getByLabel('ROI '+axis,{exact:true})).toHaveValue(String(value));
 await page.getByLabel('Seed i',{exact:true}).fill('-1');const response=page.waitForResponse(r=>r.url()===API+'/jobs'&&r.request().method()==='POST');await page.getByRole('button',{name:'Run Traditional V2',exact:true}).click();expect((await response).status()).toBe(422);await expect(page.getByRole('alert')).toContainText('Seed is outside');
 await page.getByRole('button',{name:'Clear seed / ROI',exact:true}).click();await expect(page.getByLabel('Seed i',{exact:true})).toHaveValue('');await expect(page.getByLabel('ROI i0',{exact:true})).toHaveValue('');await page.getByRole('button',{name:'Load archived CT-only selection',exact:true}).click();await expect(page.getByTestId('seed-readout')).toContainText('114, 218, 17');await page.screenshot({path:shots+'/independent-picking.png'});
 expect(errors.filter(e=>!e.includes('422'))).toEqual([]);fs.writeFileSync(out+'/seed-matrix.json',JSON.stringify({source,points:records,roi:[62,216,140,339,8,27],invalid_seed_http:422},null,2));
});

test('new real runs reopen after actual restart, compare in 2D/3D, highlight and export',async({page,request})=>{
 const errors=audit(page);await start(page);await page.getByRole('button',{name:'Run History',exact:true}).click();await page.reload();await page.getByRole('button',{name:'Algorithm Workbench',exact:true}).click();await page.getByRole('button',{name:'Run History',exact:true}).click();
 const ids=evidence.real_comparisons.slice(0,2).map(r=>r.run_id);for(const id of ids)await page.getByLabel('Compare '+id,{exact:true}).check();await page.getByRole('button',{name:'Compare selected runs',exact:true}).click();await expect(page.getByLabel('Analysis method',{exact:true}).locator('option')).toHaveCount(4);await ready(page);await page.getByRole('button',{name:'Spatial errors',exact:true}).click();await page.getByLabel('Analysis method',{exact:true}).selectOption('run_'+ids[1].replaceAll('-','_'));await expect(page.getByTestId('metric-dice_3d')).toHaveText('0.9536');
 await page.getByRole('button',{name:'3D surfaces',exact:true}).click();await expect(page.locator('.surface-footer')).toContainText('Real surfaces loaded');await page.getByLabel('Highlight component',{exact:true}).selectOption('fp:1');
 const mintPixels=()=>page.getByTestId('surface-canvas').evaluate(canvas=>{const temp=document.createElement('canvas');temp.width=canvas.width;temp.height=canvas.height;const ctx=temp.getContext('2d');ctx.drawImage(canvas,0,0);const a=ctx.getImageData(0,0,temp.width,temp.height).data;let n=0;for(let i=0;i<a.length;i+=4)if(a[i+1]>a[i]+40&&a[i+1]>a[i+2]-10&&a[i]<150)n++;return n});
 await expect.poll(mintPixels).toBeGreaterThan(0);const highlightPixels=await mintPixels();await page.screenshot({path:shots+'/reopened-runs-3d-highlight.png'});const exported=await request.get(API+'/runs/'+ids[0]+'/export');expect(exported.status()).toBe(200);expect((await exported.body()).subarray(0,2).toString()).toBe('PK');
 await page.getByRole('button',{name:'Algorithm Workbench',exact:true}).click();await page.getByRole('button',{name:'Run History',exact:true}).click();const row=page.locator('tr').filter({has:page.getByRole('button',{name:evidence.no_gt.run_id.slice(0,8),exact:true})});await row.getByRole('button',{name:'Open',exact:true}).click();await expect(page.locator('.work-heading')).toContainText(evidence.no_gt.case_id);await expect(page.getByTestId('metric-dice_3d')).toHaveCount(0);await expect(page.locator('.legend')).not.toContainText('FP · false positive');await page.screenshot({path:shots+'/reopened-no-gt.png'});
 // Catalog extension points to the actual just-computed package, never a
 // fabricated image/result. Check every wrapped text rectangle fits the sidebar.
 await page.route('**/demo/index.json',async route=>{const response=await route.fetch();const index=await response.json();index.cases.push({case_id:evidence.no_gt.case_id,title:evidence.no_gt.case_id,manifest:API+'/runs/'+evidence.no_gt.run_id+'/files/package/case.json'});await route.fulfill({response,json:index})});await page.reload();const label=page.locator('.sidebar nav strong').filter({hasText:evidence.no_gt.case_id});await expect(label).toHaveText(evidence.no_gt.case_id);await label.scrollIntoViewIfNeeded();const textFit=await label.evaluate(el=>{const b=el.getBoundingClientRect(),r=document.createRange();r.selectNodeContents(el);return {clientWidth:el.clientWidth,scrollWidth:el.scrollWidth,rectangles:[...r.getClientRects()].map(x=>({left:x.left-b.left,right:x.right-b.left,width:x.width})),text:el.textContent}});expect(textFit.scrollWidth).toBeLessThanOrEqual(textFit.clientWidth+1);for(const r of textFit.rectangles){expect(r.left).toBeGreaterThanOrEqual(-1);expect(r.right).toBeLessThanOrEqual(textFit.clientWidth+1)}await page.screenshot({path:shots+'/long-case-id.png'});fs.writeFileSync(out+'/p2-display.json',JSON.stringify({highlightPixels,textFit},null,2));expect(errors).toEqual([]);
});

test('refresh during real inference preserves task and cancellation terminates its actual process',async({page,request})=>{
 const errors=audit(page);await start(page);await page.getByRole('button',{name:'U-Net Inference',exact:true}).click();await page.getByLabel('Algorithm input',{exact:true}).selectOption('spleen_17');await ready(page);await page.getByLabel('Device',{exact:true}).selectOption('cpu');const response=page.waitForResponse(r=>r.url()===API+'/jobs'&&r.request().method()==='POST');await page.getByRole('button',{name:'Run U-Net Inference',exact:true}).click();const submitted=await (await response).json();
 await expect.poll(async()=>{const r=await (await request.get(API+'/jobs/'+submitted.run_id)).json();return r.progress?.stage},{timeout:120000}).toBe('inference');await page.reload();await page.getByRole('button',{name:'Algorithm Workbench',exact:true}).click();await expect(page.locator('.run-detail')).toContainText(submitted.run_id);await page.getByRole('button',{name:'Cancel task',exact:true}).click();await expect(page.getByRole('heading',{name:'Run status: cancelled',exact:true})).toBeVisible();
 const row=await (await request.get(API+'/jobs/'+submitted.run_id)).json();expect(row.status).toBe('cancelled');const {execFileSync}=await import('node:child_process');const exists=execFileSync(process.env.MEDSEG_TEST_PYTHON || (()=>{throw Error('Set MEDSEG_TEST_PYTHON to the test interpreter')})(),['-B','-c','import psutil,sys; print(psutil.pid_exists(int(sys.argv[1])))',String(row.pid)],{encoding:'utf8'});expect(exists.trim()).toBe('False');fs.writeFileSync(out+'/browser-refresh-cancel.json',JSON.stringify({run_id:submitted.run_id,pid:row.pid,status:row.status,process_exists:false},null,2));expect(errors).toEqual([]);
});

test('actual backend shutdown preserves frozen analysis and clear disconnected state',async({page})=>{
 fs.writeFileSync(out+'/browser.done','finished backend-dependent browser checks');await expect.poll(async()=>{try{await fetch(API+'/health',{signal:AbortSignal.timeout(1000)});return false}catch{return true}},{timeout:30000}).toBe(true);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/');await ready(page);await page.getByRole('button',{name:'Algorithm Workbench',exact:true}).click();await expect(page.getByText('Local computation service disconnected',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Run Traditional V2',exact:true})).toBeDisabled();await page.getByRole('button',{name:'2D comparison',exact:true}).click();await ready(page);await page.getByRole('button',{name:'Spatial errors',exact:true}).click();await expect(page.locator('.chart-panel')).toBeVisible();await page.getByRole('button',{name:'3D surfaces',exact:true}).click();await expect(page.locator('.surface-footer')).toContainText('Real surfaces loaded');await page.screenshot({path:shots+'/actual-service-offline.png'});expect(errors).toEqual([]);
});
