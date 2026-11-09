import {test,expect} from '../../frontend/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../..');
const manifests=Object.fromEntries(['spleen_8','spleen_59','spleen_17'].map(id=>[id,JSON.parse(fs.readFileSync(`${root}/frontend/public/demo/${id}/case.json`,'utf8'))]));
const shots=process.env.MEDSEG_ACCEPTANCE_SHOTS||`${root}/docs/screenshots/phase1_1`;
test.beforeEach(async({page})=>{await page.addInitScript(()=>localStorage.setItem('medseg.language.v1','zh'))});
async function range(page,label,value){await page.getByLabel(label,{exact:true}).evaluate((el,v)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}))},value)}
async function loaded(page){await expect(page.getByTestId('stage-0')).toBeVisible();await expect(page.locator('.image-status')).toHaveCount(0)}
async function start(page){await page.goto('/');await expect(page).toHaveTitle(/MedSeg-Lab/);await loaded(page)}
function audit(page){const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'||m.type()==='warning')errors.push(m.text())});const remote=[];page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5173/')&&!r.url().startsWith('data:'))remote.push(r.url())});return {errors,remote}}
async function canvasHash(page,index=0){return await page.locator('.image-fit canvas').nth(index).evaluate(c=>{const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let h=2166136261;for(const v of p)h=Math.imul(h^v,16777619);return h>>>0})}
test('three real cases, six modes, first/middle/last slices, frozen metric identity',async({page})=>{
 const a=audit(page);await start(page);
 for(const [id,c] of Object.entries(manifests)){
  await page.getByRole('navigation',{name:'病例选择'}).getByRole('button',{name:new RegExp(id)}).click();await loaded(page);
  await expect(page.getByTestId('metric-dice_3d')).toHaveText(Number(c.methods.find(m=>m.id==='unet').frozen_metrics.dice_3d).toFixed(4));
  for(const k of [0,Math.floor(c.spatial.shape[2]/2),c.spatial.shape[2]-1]){
   await range(page,'同步轴位切片',String(k));await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice',String(k));
   const hashes=[];
   for(const mode of c.display_modes){await page.getByLabel('视图 1 内容',{exact:true}).selectOption(mode);await loaded(page);hashes.push(await canvasHash(page));}
   expect(hashes.length).toBe(6);
  }
  await page.getByLabel('分析方法',{exact:true}).selectOption('traditional');await expect(page.getByTestId('metric-dice_3d')).toHaveText(Number(c.methods[0].frozen_metrics.dice_3d).toFixed(4));
 }
 expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});
test('dual and quad sync, real wheel, zoom, pan, reset, opacity and contours',async({page})=>{
 const a=audit(page);await start(page);await page.getByRole('button',{name:'四宫格',exact:true}).click();await expect(page.locator('.image-stage')).toHaveCount(4);await loaded(page);
 const initial=Number(await page.getByTestId('stage-0').getAttribute('data-slice'));await page.getByTestId('stage-0').hover();await page.mouse.wheel(0,100);
 await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice',String(initial+1));for(let i=1;i<4;i++)await expect(page.getByTestId(`stage-${i}`)).toHaveAttribute('data-slice',String(initial+1));
 await page.getByRole('button',{name:'放大',exact:true}).click();for(let i=0;i<4;i++)await expect(page.getByTestId(`stage-${i}`)).toHaveAttribute('data-transform','1.2,0,0');
 const box=await page.getByTestId('stage-0').boundingBox();await page.mouse.move(box.x+100,box.y+70);await page.mouse.down();await page.mouse.move(box.x+130,box.y+90,{steps:4});await page.mouse.up();
 const t=await page.getByTestId('stage-0').getAttribute('data-transform');expect(t).not.toBe('1.2,0,0');for(let i=1;i<4;i++)await expect(page.getByTestId(`stage-${i}`)).toHaveAttribute('data-transform',t);
 await page.getByRole('button',{name:'恢复视野',exact:true}).click();await expect(page.getByTestId('stage-0')).toHaveAttribute('data-transform','1,0,0');
 await page.getByRole('button',{name:'双视图',exact:true}).click();await range(page,'同步轴位切片','17');await loaded(page);await page.getByLabel('视图 1 内容',{exact:true}).selectOption('gt');await loaded(page);
 const overlay=await canvasHash(page);await range(page,'掩膜透明度','0');await loaded(page);const ct=await canvasHash(page);expect(ct).not.toBe(overlay);
 await range(page,'掩膜透明度','100');await page.getByLabel('轮廓显示',{exact:true}).check();await loaded(page);const contour=await canvasHash(page);expect(contour).not.toBe(ct);await page.getByLabel('轮廓显示',{exact:true}).uncheck();await loaded(page);expect(await canvasHash(page)).not.toBe(contour);
 expect(a.errors).toEqual([]);
});
test('real error chart jump, volume cancellation, saved T1/T2 and component highlight',async({page})=>{
 const a=audit(page);await start(page);await page.getByRole('navigation',{name:'病例选择'}).getByRole('button',{name:/spleen_17/}).click();await loaded(page);
 await page.getByRole('button',{name:'空间误差',exact:true}).click();await page.getByTestId('chart-slice-50').click();await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice','50');await expect(page.getByTestId('chart-readout')).toContainText('k=50');
 await page.getByRole('button',{name:'T1 · k=71',exact:true}).click();await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice','71');await page.getByRole('button',{name:'T2 · k=50',exact:true}).click();await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice','50');
 const t2=manifests.spleen_17.targets.find(t=>t.name==='T2');await page.getByLabel('高亮分量',{exact:true}).selectOption(`fp:${t2.fp_component_ids.unet}`);await loaded(page);await expect(page.locator('.component-detail')).toContainText('全部为 FP');await expect(page.locator('.component-detail')).toContainText('距 GT');
 await page.locator('.main-content').evaluate(el=>el.scrollTop=0);await page.screenshot({path:`${shots}/analysis-spleen17.png`,fullPage:false});
 await page.getByRole('navigation',{name:'病例选择'}).getByRole('button',{name:/spleen_59/}).click();await loaded(page);await page.getByRole('button',{name:'空间误差',exact:true}).click();await expect(page.locator('.volume-values')).toContainText('33.276');await expect(page.locator('.volume-values')).toContainText('33.977');await expect(page.locator('.volume-values')).toContainText('-0.701');
 expect(a.errors).toEqual([]);
});
test('real interactive 3D, every component, orbit zoom pan, layer controls and highlight',async({page})=>{
 const a=audit(page);await start(page);await page.getByRole('navigation',{name:'病例选择'}).getByRole('button',{name:/spleen_17/}).click();await loaded(page);await page.getByRole('button',{name:'三维视图',exact:true}).click();
 await expect(page.locator('.surface-footer')).toContainText('真实表面已加载',{timeout:60000});const canvas=page.getByTestId('surface-canvas');await expect(canvas).toBeVisible();await expect(canvas).toHaveAttribute('data-surface-count','32');
 const initial=await canvas.getAttribute('data-camera');const b=await canvas.boundingBox();await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2+90,b.y+b.height/2+30,{steps:10});await page.mouse.up();await expect(canvas).not.toHaveAttribute('data-camera',initial);
 const rotated=await canvas.getAttribute('data-camera');await canvas.hover();await page.mouse.wheel(0,140);await expect(canvas).not.toHaveAttribute('data-camera',rotated);
 const zoomed=await canvas.getAttribute('data-camera');await page.mouse.down({button:'right'});await page.mouse.move(b.x+b.width/2+30,b.y+b.height/2+20,{steps:5});await page.mouse.up({button:'right'});await expect(canvas).not.toHaveAttribute('data-camera',zoomed);
 await range(page,'gt 三维透明度','15');await range(page,'traditional 三维透明度','25');await range(page,'unet 三维透明度','85');
 await page.locator('.layer-controls label').filter({hasText:'GT'}).getByRole('checkbox').uncheck();await page.locator('.layer-controls label').filter({hasText:'GT'}).getByRole('checkbox').check();
 await page.getByLabel('高亮分量',{exact:true}).selectOption('prediction:30');await expect(page.locator('.component-detail')).toContainText('#30');await range(page,'三维联动切片','50');await page.getByRole('button',{name:'恢复三维视野',exact:true}).click();
 await page.screenshot({path:`${shots}/surface-spleen17.png`,fullPage:false});expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});
test('1366x768, 1920x1080 and 390x844 actual rendering and presentation',async({page})=>{
 const a=audit(page);
 for(const [width,height] of [[1366,768],[1920,1080],[390,844]]){
  await page.setViewportSize({width,height});await start(page);await expect(page.getByRole('heading',{name:'分割结果比较',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const sizes=await page.locator('.image-fit canvas').evaluateAll(cs=>cs.map(c=>{const b=c.getBoundingClientRect();return [b.width,b.height]}));for(const [w,h] of sizes){expect(w).toBeGreaterThan(100);expect(h).toBeGreaterThan(100);expect(Math.abs(w/h-1)).toBeLessThan(.02)}
  await page.screenshot({path:`${shots}/workstation-${width}x${height}.png`,fullPage:width===390});
 }
 await page.setViewportSize({width:1366,height:768});await page.getByRole('button',{name:'演示模式',exact:true}).click();await expect(page.locator('.app')).toHaveClass(/presentation/);await page.screenshot({path:`${shots}/presentation-1366x768.png`});await page.getByRole('button',{name:'返回研究模式',exact:true}).click();expect(a.errors).toEqual([]);
});
test('missing image is explicit and old frame is hidden',async({page})=>{
 await page.route('**/demo/spleen_8/ct/017.png',r=>r.fulfill({status:404,body:'missing'}));await page.goto('/');await expect(page.locator('.image-status').first()).toContainText('图片资源缺失');await expect(page.locator('.image-fit').first()).toHaveCSS('visibility','hidden');
});
test('invalid spatial package is rejected clearly',async({page})=>{
 const bad=structuredClone(manifests.spleen_8);bad.spatial.unit='unknown';await page.route('**/demo/spleen_8/case.json',r=>r.fulfill({json:bad}));await page.goto('/');await expect(page.getByRole('alert')).toContainText('空间清单无效');await expect(page.locator('.image-stage')).toHaveCount(0);
});
test('no-GT package never exposes Dice or FP/FN',async({page})=>{
 const c=structuredClone(manifests.spleen_8);c.has_gt=false;c.gt_mesh=null;c.gt_source=null;c.display_modes=['ct','unet'];c.methods=c.methods.filter(m=>m.id==='unet');for(const m of c.methods){m.analysis=null;m.fp_components=null;m.frozen_metrics=null;m.components.gt_available=false;}await page.route('**/demo/spleen_8/case.json',r=>r.fulfill({json:c}));await start(page);await expect(page.getByTestId('metric-dice_3d')).toHaveCount(0);await page.getByRole('button',{name:'切片误差曲线',exact:false}).click();await expect(page.locator('.analysis-empty').first()).toContainText('没有可用 GT');await expect(page.getByLabel('视图 1 内容',{exact:true}).locator('option')).toHaveCount(2);
});

test('missing 3D mesh reports a real error and retains static backup',async({page})=>{await page.route('**/demo/spleen_8/meshes/gt.mesh',r=>r.fulfill({status:404,body:'missing'}));await start(page);await page.getByRole('button',{name:'三维视图',exact:true}).click();await expect(page.getByRole('alert')).toContainText('三维加载失败');await expect(page.getByRole('alert')).toContainText('404');await page.getByText('已验收静态三维备用图（非交互）',{exact:true}).click();await expect(page.locator('.static-backup img').first()).toBeVisible()});

