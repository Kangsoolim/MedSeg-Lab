import {test,expect} from '../../frontend/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs';import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../..'),shots=process.env.MEDSEG_ACCEPTANCE_SHOTS||`${root}/docs/screenshots/phase1_1`;
const cases=Object.fromEntries(['spleen_8','spleen_59','spleen_17'].map(id=>[id,JSON.parse(fs.readFileSync(`${root}/frontend/public/demo/${id}/case.json`,'utf8'))]));
async function loaded(p){await expect(p.getByTestId('stage-0')).toBeVisible();await expect(p.locator('.image-status')).toHaveCount(0)}
async function start(p){await p.goto('/');await expect(p).toHaveTitle(/MedSeg-Lab/);await loaded(p)}
async function range(p,label,value){await p.getByLabel(label,{exact:true}).evaluate((el,v)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}))},String(value))}
async function hash(p,index=0){return p.locator('.image-fit canvas').nth(index).evaluate(c=>{let h=2166136261;for(const v of c.getContext('2d').getImageData(0,0,c.width,c.height).data)h=Math.imul(h^v,16777619);return h>>>0})}
function audit(p){const errors=[],remote=[];p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(['error','warning'].includes(m.type()))errors.push(m.text())});p.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5173/')&&!r.url().startsWith('data:'))remote.push(r.url())});return {errors,remote}}
async function geometry(p){return p.locator('.image-stage').evaluateAll(ss=>ss.map(s=>{const c=s.querySelector('canvas'),r=s.getBoundingClientRect(),b=c.getBoundingClientRect();return {stage:[r.x,r.y,r.width,r.height],canvas:[b.x,b.y,b.width,b.height],bitmap:[c.width,c.height],transform:s.dataset.transform,slice:s.dataset.slice}}))}

for(const [width,height] of [[1920,1080],[1366,768],[1440,900],[390,844]])test(`readable single dual quad and containment ${width}x${height}`,async({page})=>{
 const a=audit(page);await page.setViewportSize({width,height});await start(page);const report=[];
 for(const [n,label] of [[1,'Single'],[2,'Dual'],[4,'Quad']]){
  await page.getByRole('button',{name:label,exact:true}).click();await expect(page.locator('.image-stage')).toHaveCount(n);await loaded(page);
  const sizes=await geometry(page);for(const {canvas:[x,y,w,h],stage:[sx,sy,sw,sh],bitmap} of sizes){expect(w).toBeGreaterThanOrEqual(300);expect(h).toBeGreaterThanOrEqual(300);expect(w/h).toBeCloseTo(cases.spleen_8.spatial.display_aspect,3);expect(x).toBeGreaterThanOrEqual(sx-.1);expect(y).toBeGreaterThanOrEqual(sy-.1);expect(x+w).toBeLessThanOrEqual(sx+sw+.1);expect(y+h).toBeLessThanOrEqual(sy+sh+.1);expect(bitmap).toEqual([512,512])}
  if(width>760&&n>1){expect(sizes[0].stage[2]).toBeCloseTo(sizes[1].stage[2],1);expect(sizes[0].stage[3]).toBeCloseTo(sizes[1].stage[3],1)}
  if(width<=760&&n>1)expect(sizes[1].stage[1]).toBeGreaterThan(sizes[0].stage[1]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  if(n===2||n===4)await page.screenshot({path:`${shots}/${label.toLowerCase()}-${width}x${height}.png`,fullPage:width<=760});
  if(n===4&&width>760){await page.getByRole('button',{name:'Upper / lower views',exact:false}).click();await expect.poll(async()=>page.getByTestId('viewport-scroll').evaluate(el=>Math.abs(el.scrollTop-(el.scrollHeight-el.clientHeight))<=1)).toBe(true);await expect(page.getByTestId('stage-3')).toBeInViewport({ratio:1});expect(await hash(page,3)).not.toBe(0);await page.screenshot({path:`${shots}/quad-lower-${width}x${height}.png`})}
  report.push({layout:n,sizes});
 }
 fs.writeFileSync(`${root}/docs/phase1_1-layout-${width}.json`,JSON.stringify(report,null,2));expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});

test('default English, persistent language and scientific state across all workspaces',async({page})=>{
 const a=audit(page);await start(page);await expect(page.locator('html')).toHaveAttribute('lang','en');await page.getByRole('navigation',{name:'Select case'}).getByRole('button',{name:/spleen_17/}).click();await loaded(page);
 await range(page,'Synchronized axial slice',50);await page.getByRole('button',{name:'Quad',exact:true}).click();await loaded(page);await page.getByRole('button',{name:'Zoom in',exact:true}).click();
 await page.getByLabel('View 3 content',{exact:true}).selectOption('ct');await loaded(page);const before=await geometry(page),pixels=await hash(page);const precise=String(cases.spleen_17.methods.find(m=>m.id==='unet').frozen_metrics.dice_3d);
 await expect(page.getByTestId('metric-dice_3d')).toHaveAttribute('title',precise);await expect(page.getByTestId('metric-dice_3d')).toHaveText(Number(precise).toFixed(4));
 await page.getByRole('button',{name:'中文',exact:true}).click();await expect(page.locator('html')).toHaveAttribute('lang','zh-CN');await expect(page.getByRole('heading',{name:'分割结果比较',exact:true})).toBeVisible();await expect(page.getByLabel('视图 3 内容',{exact:true})).toHaveValue('ct');
 expect((await geometry(page)).map(x=>[x.slice,x.transform])).toEqual(before.map(x=>[x.slice,x.transform]));expect(await hash(page)).toBe(pixels);
 await page.screenshot({path:`${shots}/research-zh.png`});await page.getByRole('button',{name:'空间误差',exact:true}).click();await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice','50');await page.getByRole('button',{name:'二维比较',exact:true}).click();
 await expect(page.getByTestId('stage-0')).toHaveAttribute('data-transform','1.2,0,0');await page.getByRole('button',{name:'EN',exact:true}).click();await expect(page.getByLabel('View 3 content',{exact:true})).toHaveValue('ct');await page.screenshot({path:`${shots}/research-en.png`});
 await page.reload();await loaded(page);await expect(page.locator('html')).toHaveAttribute('lang','en');await page.getByRole('button',{name:'中文',exact:true}).click();await page.reload();await loaded(page);await expect(page.locator('html')).toHaveAttribute('lang','zh-CN');expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});

test('resize, independent sidebars, focus and presentation retain normalized pan and zoom',async({page})=>{
 const a=audit(page);await page.setViewportSize({width:1920,height:1080});await start(page);await range(page,'Synchronized axial slice',15);await page.getByRole('button',{name:'Zoom in',exact:true}).click();
 const b=await page.getByTestId('stage-0').boundingBox();await page.mouse.move(b.x+120,b.y+120);await page.mouse.down();await page.mouse.move(b.x+170,b.y+145,{steps:6});await page.mouse.up();const state=await page.getByTestId('stage-0').getAttribute('data-transform');
 for(const [width,height] of [[1366,768],[1440,900],[1920,1080]]){await page.setViewportSize({width,height});await expect(page.getByTestId('stage-0')).toHaveAttribute('data-transform',state);await expect(page.getByTestId('stage-1')).toHaveAttribute('data-transform',state)}
 const normal=(await page.getByTestId('stage-0').boundingBox()).width;await page.getByRole('button',{name:'Hide cases',exact:true}).click();await page.getByRole('button',{name:'Hide settings',exact:true}).click();expect((await page.getByTestId('stage-0').boundingBox()).width).toBeGreaterThan(normal);
 await page.getByRole('button',{name:'Expand imaging workspace',exact:true}).click();await expect(page.locator('.workbench')).toHaveClass(/image-focus/);await page.keyboard.press('Escape');await expect(page.locator('.workbench')).not.toHaveClass(/image-focus/);
 await page.getByRole('button',{name:'Show cases',exact:true}).click();await page.getByRole('button',{name:'Show settings',exact:true}).click();await page.getByRole('button',{name:'Presentation',exact:true}).click();await expect(page.locator('.sidebar')).toBeHidden();await expect(page.locator('.inspector')).toBeHidden();await expect(page.locator('.presentation-metrics')).toContainText('Dice');await expect(page.getByTestId('stage-0')).toHaveAttribute('data-transform',state);await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice','15');await page.screenshot({path:`${shots}/presentation-1920x1080.png`});
 await page.getByRole('button',{name:'Return to research',exact:true}).click();await expect(page.locator('.sidebar')).toBeVisible();await expect(page.locator('.inspector')).toBeVisible();await expect(page.getByTestId('stage-0')).toHaveAttribute('data-transform',state);await page.getByRole('button',{name:'Reset view',exact:true}).click();await expect(page.getByTestId('stage-0')).toHaveAttribute('data-transform','1,0,0');expect(a.errors).toEqual([]);
});

test('collapsed error chart opens, navigates and preserves image readability',async({page})=>{
 await start(page);await expect(page.locator('.error-chart')).toHaveCount(0);await page.getByRole('button',{name:'Slice error curve',exact:false}).click();await expect(page.locator('.error-chart')).toBeVisible();await page.getByTestId('chart-slice-13').click();await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice','13');const sizes=await geometry(page);expect(sizes[0].canvas[3]).toBeGreaterThanOrEqual(300);await page.getByRole('button',{name:'Slice error curve',exact:false}).click();await expect(page.locator('.error-chart')).toHaveCount(0);await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice','13');
});

test('real optional-GT import fixture suppresses all evaluation metrics',async({page})=>{
 const data=JSON.parse(fs.readFileSync(`${root}/docs/phase1_1-real-no-gt-manifest.json`,'utf8'));await page.route('**/demo/spleen_8/case.json',r=>r.fulfill({json:data}));await start(page);await expect(page.getByTestId('metric-dice_3d')).toHaveCount(0);await expect(page.getByLabel('View 1 content',{exact:true}).locator('option')).toHaveCount(2);await page.getByRole('button',{name:'Spatial errors',exact:true}).click();await expect(page.locator('.analysis-empty').first()).toContainText('GT unavailable');await expect(page.locator('.volume-values')).toHaveCount(0);await page.getByRole('button',{name:'Presentation',exact:true}).click();await expect(page.locator('.presentation-metrics')).not.toContainText('Dice');
});

test('missing image is a localized failure; stale pixels remain hidden',async({page})=>{
 await page.route('**/demo/spleen_8/gt/017.png',r=>r.fulfill({status:404,body:'missing'}));await page.goto('/');await expect(page.locator('.image-status').first()).toContainText('Image asset missing');await expect(page.locator('.image-fit').first()).toHaveCSS('visibility','hidden');await page.getByRole('button',{name:'中文',exact:true}).click();await expect(page.locator('.image-status').first()).toContainText('图片资源缺失');
});

test('decoded layer with wrong dimensions is rejected without stretching',async({page})=>{
 const actualStatic=fs.readFileSync(`${root}/frontend/public/${cases.spleen_8.static_figures[0]}`);await page.route('**/demo/spleen_8/gt/017.png',r=>r.fulfill({status:200,contentType:'image/png',body:actualStatic}));await page.goto('/');await expect(page.locator('.image-status').first()).toContainText('Image layer dimensions differ');await expect(page.locator('.image-fit').first()).toHaveCSS('visibility','hidden');
});

test('invalid physical aspect is rejected and error changes language without reload',async({page})=>{
 const c=structuredClone(cases.spleen_8);c.spatial.display_aspect=2;await page.route('**/demo/spleen_8/case.json',r=>r.fulfill({json:c}));await page.goto('/');await expect(page.getByRole('alert')).toContainText('Physical display aspect');await page.getByRole('button',{name:'中文',exact:true}).click();await expect(page.getByRole('alert')).toContainText('物理显示比例');await expect(page.locator('.image-stage')).toHaveCount(0);
});

test('English analysis and 3D contain no untranslated UI, language retains 3D camera',async({page})=>{
 const a=audit(page);await page.setViewportSize({width:1920,height:1080});await start(page);await page.getByRole('navigation',{name:'Select case'}).getByRole('button',{name:/spleen_17/}).click();await loaded(page);await page.getByRole('button',{name:'Spatial errors',exact:true}).click();
 const untranslated=async()=>page.locator('body').evaluate(el=>{const w=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);const result=[];let n;while(n=w.nextNode()){if(/[\u3400-\u9fff]/.test(n.textContent)&&n.textContent.trim()!=='中文'&&n.parentElement?.getClientRects().length&&getComputedStyle(n.parentElement).visibility!=='hidden')result.push(n.textContent)}return result});
 expect(await untranslated()).toEqual([]);await page.getByRole('button',{name:'3D surfaces',exact:true}).click();await expect(page.locator('.surface-footer')).toContainText('Real surfaces loaded',{timeout:60000});const c=page.getByTestId('surface-canvas');await expect(c).toHaveAttribute('data-surface-count','32');const b=await c.boundingBox();await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2+70,b.y+b.height/2+35,{steps:8});await page.mouse.up();const camera=await c.getAttribute('data-camera');expect(await untranslated()).toEqual([]);await page.screenshot({path:`${shots}/surface-en-1920x1080.png`});await page.getByRole('button',{name:'中文',exact:true}).click();await expect(c).toHaveAttribute('data-camera',camera);await page.getByRole('button',{name:'EN',exact:true}).click();await expect(c).toHaveAttribute('data-camera',camera);expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});



