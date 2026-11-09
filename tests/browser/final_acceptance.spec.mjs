import {test,expect} from '../../frontend/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs';import path from 'node:path';
import * as THREE from '../../frontend/node_modules/three/build/three.module.js';
const root=path.resolve(import.meta.dirname,'../..');
const evidence=path.join(root,'docs/final-acceptance');fs.mkdirSync(evidence,{recursive:true});
const shots=process.env.MEDSEG_ACCEPTANCE_SHOTS||path.join(root,'docs/screenshots/final-acceptance');fs.mkdirSync(shots,{recursive:true});
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const manifests=Object.fromEntries(['spleen_8','spleen_59','spleen_17'].map(id=>[id,read(`${root}/frontend/public/demo/${id}/case.json`)]));
async function loaded(p){await expect(p.getByTestId('stage-0')).toBeVisible();await expect(p.locator('.image-status')).toHaveCount(0);await p.evaluate(()=>document.fonts.ready)}
async function start(p){await p.goto('/');await expect(p).toHaveTitle(/MedSeg-Lab/);await loaded(p);await expect(p.locator('vite-error-overlay')).toHaveCount(0)}
async function range(p,label,value){await p.getByLabel(label,{exact:true}).evaluate((el,v)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}))},String(value))}
const hash=async c=>c.evaluate(c=>{const g=c.getContext('webgl2')||c.getContext('webgl');const px=new Uint8Array(g.drawingBufferWidth*g.drawingBufferHeight*4);g.readPixels(0,0,g.drawingBufferWidth,g.drawingBufferHeight,g.RGBA,g.UNSIGNED_BYTE,px);let h=2166136261;for(const x of px)h=Math.imul(h^x,16777619);return h>>>0});
function audit(p){const errors=[],remote=[];p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(['error','warning'].includes(m.type()))errors.push(m.text())});p.on('request',r=>{if(!/^http:\/\/127\.0\.0\.1:(5173|5174)\//.test(r.url())&&!r.url().startsWith('data:'))remote.push(r.url())});return {errors,remote}}

test('analysis method keeps selected error imagery and true curve synchronized',async({page})=>{
 await start(page);await page.getByRole('navigation',{name:'Select case'}).getByRole('button',{name:/spleen_17/}).click();await loaded(page);
 await page.getByRole('button',{name:'Spatial errors',exact:true}).click();await page.getByLabel('View 2 content',{exact:true}).selectOption('unet_error');await page.getByTestId('chart-slice-50').click();await loaded(page);
 await page.getByLabel('Analysis method',{exact:true}).selectOption('traditional');
 await expect(page.getByLabel('View 2 content',{exact:true})).toHaveValue('traditional_error');
 await page.getByLabel('Error curve units',{exact:true}).selectOption('voxels');
 const row=manifests.spleen_17.methods[0].analysis.slices[50];
 await expect(page.getByTestId('chart-readout')).toContainText(`FP ${row.fp_voxels}`);await expect(page.getByTestId('chart-readout')).toContainText(`FN ${row.fn_voxels}`);
 await expect(page.getByTestId('slice-position')).toContainText(`s=${manifests.spleen_17.spatial.slice_positions_mm[50].toFixed(1)} mm`);
 await page.screenshot({path:`${shots}/analysis-method-traditional.png`});
 // Explicit comparison-panel choices are preserved when using the independent compare workspace.
 await page.getByRole('button',{name:'2D comparison',exact:true}).click();await page.getByLabel('View 2 content',{exact:true}).selectOption('traditional');await page.getByLabel('Analysis method',{exact:true}).selectOption('unet');await expect(page.getByLabel('View 2 content',{exact:true})).toHaveValue('traditional');
 // Entering analysis after independently changing the comparison method must
 // initialize its primary error panel to the currently selected method too.
 await page.getByRole('button',{name:'Spatial errors',exact:true}).click();await expect(page.getByLabel('View 2 content',{exact:true})).toHaveValue('unet_error');
});

test('actual CT bitmap fills measured fit, every layout and viewport',async({page})=>{
 const a=audit(page);const report=[];
 for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[390,844]]){
  await page.setViewportSize({width,height});await start(page);
  for(const [n,label] of [[1,'Single'],[2,'Dual'],[4,'Quad']]){
   await page.getByRole('button',{name:label,exact:true}).click();await expect(page.locator('.image-stage')).toHaveCount(n);
   for(let i=0;i<n;i++)await page.getByLabel(`View ${i+1} content`,{exact:true}).selectOption('ct');await loaded(page);
   const measurements=await page.locator('.image-fit canvas').evaluateAll(async cs=>{
    const im=new Image();im.src='/demo/spleen_8/ct/017.png';await im.decode();const reference=document.createElement('canvas');reference.width=im.width;reference.height=im.height;reference.getContext('2d').drawImage(im,0,0);const expected=reference.getContext('2d').getImageData(0,0,im.width,im.height).data;
    return cs.map(c=>{const r=c.getBoundingClientRect(),s=c.closest('.image-stage').getBoundingClientRect();const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let differences=0,nonuniform=0,minX=c.width,minY=c.height,maxX=-1,maxY=-1;for(let i=0;i<p.length;i+=4){if(p[i]!==expected[i]||p[i+1]!==expected[i+1]||p[i+2]!==expected[i+2]||p[i+3]!==expected[i+3])differences++;if(p[i]>0&&p[i]<255){nonuniform++;const q=i/4,x=q%c.width,y=Math.floor(q/c.width);minX=Math.min(minX,x);minY=Math.min(minY,y);maxX=Math.max(maxX,x);maxY=Math.max(maxY,y)}}return {ct_display_px:[r.width,r.height],stage_px:[s.width,s.height],bitmap:[c.width,c.height],pixel_differences_from_real_ct:differences,nonuniform_ct_pixels:nonuniform,nonuniform_bounds_native:[minX,minY,maxX,maxY],contain:r.left>=s.left-.1&&r.top>=s.top-.1&&r.right<=s.right+.1&&r.bottom<=s.bottom+.1}})
   });
   for(const m of measurements){expect(m.ct_display_px[0]).toBeGreaterThanOrEqual(300);expect(m.ct_display_px[1]).toBeGreaterThanOrEqual(300);expect(m.pixel_differences_from_real_ct).toBe(0);expect(m.nonuniform_ct_pixels).toBeGreaterThan(50000);expect(m.contain).toBe(true);expect(m.bitmap).toEqual([512,512]);expect(m.ct_display_px[0]/m.ct_display_px[1]).toBeCloseTo(1,4)}
   await page.screenshot({path:`${shots}/ct-${label.toLowerCase()}-${width}x${height}.png`,fullPage:width===390});
   if(n===4&&width>760){await page.getByRole('button',{name:'Upper / lower views',exact:false}).click();await expect(page.getByTestId('stage-3')).toBeInViewport({ratio:1});await page.screenshot({path:`${shots}/ct-quad-lower-${width}x${height}.png`})}
   report.push({viewport:[width,height],layout:n,measurements});
  }
 }
 fs.writeFileSync(`${evidence}/actual-ct-sizes.json`,JSON.stringify(report,null,2));expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});

test('actual 3D pixels respond to camera and all layers, FP selection returns to correct 2D voxels',async({page})=>{
 const a=audit(page);await page.setViewportSize({width:1920,height:1080});await start(page);await page.getByRole('navigation',{name:'Select case'}).getByRole('button',{name:/spleen_17/}).click();await loaded(page);await page.getByRole('button',{name:'3D surfaces',exact:true}).click();await expect(page.locator('.surface-footer')).toContainText('Real surfaces loaded');const canvas=page.getByTestId('surface-canvas');await expect(canvas).toHaveAttribute('data-surface-count','32');
 const initial=await hash(canvas);const b=await canvas.boundingBox();await canvas.hover();await page.mouse.down();await page.mouse.move(b.x+b.width*.65,b.y+b.height*.6,{steps:8});await page.mouse.up();await expect.poll(()=>hash(canvas)).not.toBe(initial);
 let before=await hash(canvas);await canvas.hover();await page.mouse.wheel(0,140);await expect.poll(()=>hash(canvas)).not.toBe(before);before=await hash(canvas);await page.mouse.down({button:'right'});await page.mouse.move(b.x+b.width*.55,b.y+b.height*.55,{steps:8});await page.mouse.up({button:'right'});await expect.poll(()=>hash(canvas)).not.toBe(before);
 const layerProof=[];for(const name of ['GT','Traditional V2','U-Net']){const check=page.locator('.layer-controls label').filter({hasText:name}).getByRole('checkbox');await check.scrollIntoViewIfNeeded();const visible=await hash(canvas),beforeGeometry=await canvas.evaluate(c=>({camera:c.dataset.camera,width:c.width,height:c.height}));await check.uncheck();await expect.poll(()=>hash(canvas)).not.toBe(visible);const hidden=await hash(canvas);await check.check();await expect(check).toBeChecked();await expect.poll(()=>hash(canvas)).not.toBe(hidden);layerProof.push({name,visible,hidden,restored:await hash(canvas),beforeGeometry,afterGeometry:await canvas.evaluate(c=>({camera:c.dataset.camera,width:c.width,height:c.height}))})}fs.writeFileSync(path.join(evidence,'layer-pixels.json'),JSON.stringify(layerProof,null,2));
 await page.getByRole('button',{name:'Reset 3D view',exact:true}).click();await page.getByRole('button',{name:'T2',exact:true}).click();await expect(page.locator('.component-detail')).toContainText('entire component is FP');await expect(page.getByLabel('3D linked slice',{exact:true})).toHaveValue('50');await expect.poll(()=>hash(canvas)).not.toBe(initial);await page.locator('.main-content').evaluate(el=>el.scrollTop=0);await page.screenshot({path:`${shots}/surface-t2-fp.png`});
 const comp=manifests.spleen_17.methods.find(m=>m.id==='unet').fp_components.components[0];
 // Isolate the opaque selected FP mesh so overlapping translucent prediction layers
 // cannot obscure the highlight color used by the independent projection check.
 for(const name of ['GT','Traditional V2','U-Net'])await page.locator('.layer-controls label').filter({hasText:name}).getByRole('checkbox').uncheck();
 await expect.poll(()=>canvas.evaluate(c=>{const gl=c.getContext('webgl2'),p=new Uint8Array(c.width*c.height*4);gl.readPixels(0,0,c.width,c.height,gl.RGBA,gl.UNSIGNED_BYTE,p);let count=0;for(let q=0;q<p.length;q+=4)if(p[q+1]>p[q]+30&&p[q+2]>p[q]+30&&p[q+1]>=p[q+2])count++;return count})).toBeGreaterThan(100);
 await page.locator('.main-content').evaluate(el=>el.scrollTop=0);await page.screenshot({path:`${shots}/surface-t2-fp-isolated.png`});
 const sceneCase=manifests.spleen_17,allBounds=[sceneCase.gt_mesh,...sceneCase.methods.flatMap(m=>m.components.components.map(c=>c.mesh))].map(m=>m.bounds_ras_mm);
 const worldBox=new THREE.Box3();for(const [lo,hi] of allBounds){worldBox.expandByPoint(new THREE.Vector3(...lo));worldBox.expandByPoint(new THREE.Vector3(...hi))}
 const dims=await canvas.evaluate(c=>[c.width,c.height]);const camera=new THREE.PerspectiveCamera(38,dims[0]/dims[1],.1,10000);camera.up.set(0,0,1);camera.position.set(...(await canvas.getAttribute('data-camera')).split(',').map(Number));camera.lookAt(worldBox.getCenter(new THREE.Vector3()));camera.updateMatrixWorld();
 const raw=fs.readFileSync(`${root}/frontend/public/demo/spleen_17/meshes/${comp.mesh.path}`),nv=raw.readUInt32LE(0),points=[];for(let i=0;i<nv;i++){const p=new THREE.Vector3(raw.readFloatLE(8+i*12),raw.readFloatLE(12+i*12),raw.readFloatLE(16+i*12)).project(camera);points.push([(p.x+1)*dims[0]/2,(p.y+1)*dims[1]/2])}
 const bounds=[Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))];
 const mint=await canvas.evaluate((c,bounds)=>{const gl=c.getContext('webgl2');const p=new Uint8Array(c.width*c.height*4);gl.readPixels(0,0,c.width,c.height,gl.RGBA,gl.UNSIGNED_BYTE,p);let selected=0,outside=0;for(let q=0;q<p.length;q+=4)if(p[q+1]>p[q]+30&&p[q+2]>p[q]+30&&p[q+1]>=p[q+2]){selected++;const x=q/4%c.width,y=Math.floor(q/4/c.width);if(x<bounds[0]-4||x>bounds[2]+4||y<bounds[1]-4||y>bounds[3]+4)outside++}return {selected,outside}},bounds);
 expect(mint.selected).toBeGreaterThan(100);expect(mint.outside).toBe(0);fs.writeFileSync(`${evidence}/3d-highlight-projection.json`,JSON.stringify({bounds,mint,definition:'project every real FP mesh vertex with independent Three camera; selected mint pixels must lie within source projection'},null,2));await page.getByRole('button',{name:'2D comparison',exact:true}).click();await loaded(page);await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice','50');
 const pixels=await page.locator('.image-fit canvas').first().evaluate(async(c,labelsPath)=>{const im=new Image();im.src=labelsPath;await im.decode();const t=document.createElement('canvas');t.width=im.width;t.height=im.height;t.getContext('2d').drawImage(im,0,0);const label=t.getContext('2d').getImageData(0,0,t.width,t.height).data;const actual=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let selected=0,wrong=0;for(let i=0;i<label.length;i+=4)if(label[i]+256*label[i+1]===1){selected++;if(actual[i+1]<200||actual[i+2]<160||actual[i]>110)wrong++}return {selected,wrong}},`/demo/spleen_17/meshes/labels/unet_fp/050.png`);
 expect(pixels.selected).toBeGreaterThan(0);expect(pixels.wrong).toBe(0);await page.screenshot({path:`${shots}/t2-2d-highlight.png`});
 await page.getByLabel('Highlight component',{exact:true}).selectOption('prediction:30');await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice',String(manifests.spleen_17.methods.find(m=>m.id==='unet').components.components[29].representative_k));
 fs.writeFileSync(`${evidence}/3d-2d-pixel-proof.json`,JSON.stringify({t2_fp_component:comp.id,t2_slice:50,pixels,all_surfaces:32,camera_and_layer_pixels_changed:true},null,2));expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});

test('extra real CLI-import packages browse without mocks and preserve original three cases',async({page})=>{
 const a=audit(page);await page.goto('http://127.0.0.1:5174/');await loaded(page);const catalog=read(`${evidence}/catalog.json`);const out=read(`${catalog.directory}/index.json`);expect(out.cases).toHaveLength(5);
 for(const record of catalog.cases){const c=read(`${catalog.directory}/${record.case_id}/case.json`);await page.getByRole('navigation',{name:'Select case'}).getByRole('button',{name:new RegExp(record.case_id)}).click();await loaded(page);await expect(page.locator('h1')).toHaveText('Segmentation Comparison');await expect(page.getByLabel('Analysis method',{exact:true})).toHaveValue('archived_v2');
  if(record.has_gt){await expect(page.getByTestId('metric-dice_3d')).toHaveAttribute('title',String(record.analysis.dice_3d));await expect(page.getByTestId('metric-iou_3d')).toHaveAttribute('title',String(record.analysis.iou_3d));await page.getByRole('button',{name:'Spatial errors',exact:true}).click();await expect(page.locator('.volume-values')).toContainText(record.prediction_ml.toFixed(3));await page.getByTestId('chart-slice-10').click();await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice','10')}
  else{await expect(page.getByTestId('metric-dice_3d')).toHaveCount(0);await expect(page.getByLabel('View 1 content',{exact:true}).locator('option')).toHaveCount(2);await page.getByRole('button',{name:'Spatial errors',exact:true}).click();await expect(page.locator('.volume-values')).toHaveCount(0);await expect(page.locator('.analysis-empty').first()).toContainText('GT unavailable');await page.getByRole('button',{name:'Presentation',exact:true}).click();await expect(page.locator('.presentation-metrics')).not.toContainText('Dice');await page.getByRole('button',{name:'Return to research',exact:true}).click()}
  await page.getByRole('button',{name:'2D comparison',exact:true}).click();await page.getByLabel('View 1 content',{exact:true}).selectOption('archived_v2');await page.getByRole('button',{name:'Representative slice',exact:true}).click();await loaded(page);await page.screenshot({path:`${shots}/${record.case_id}.png`});
  await page.getByRole('button',{name:'3D surfaces',exact:true}).click();await expect(page.locator('.surface-footer')).toContainText('Real surfaces loaded');await expect(page.getByTestId('surface-canvas')).toHaveAttribute('data-surface-count',String(record.components+(record.has_gt?1:0)));
 }
 for(const [id,c] of Object.entries(manifests)){await page.getByRole('navigation',{name:'Select case'}).getByRole('button',{name:new RegExp(id)}).click();await loaded(page);await expect(page.getByTestId('metric-dice_3d')).toHaveAttribute('title',String(c.methods.at(-1).frozen_metrics.dice_3d))}
 expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});




test('bilingual method, slice, panel and normalized view retain state without navigation',async({page})=>{
 const a=audit(page);await start(page);await page.getByRole('navigation',{name:'Select case'}).getByRole('button',{name:/spleen_17/}).click();await loaded(page);await page.getByLabel('Analysis method',{exact:true}).selectOption('traditional');await range(page,'Synchronized axial slice',50);await page.getByRole('button',{name:'Zoom in',exact:true}).click();await page.getByLabel('View 1 content',{exact:true}).selectOption('ct');await loaded(page);
 const transform=await page.getByTestId('stage-0').getAttribute('data-transform');let navigations=0;page.on('framenavigated',()=>navigations++);
 for(const [button,lang,methodLabel,viewLabel,tab] of [['中文','zh-CN','分析方法','视图 1 内容','空间误差'],['EN','en','Analysis method','View 1 content','Spatial errors']]){await page.getByRole('button',{name:button,exact:true}).click();await expect(page.locator('html')).toHaveAttribute('lang',lang);await expect(page.getByLabel(methodLabel,{exact:true})).toHaveValue('traditional');await expect(page.getByLabel(viewLabel,{exact:true})).toHaveValue('ct');await expect(page.getByTestId('stage-0')).toHaveAttribute('data-transform',transform);await expect(page.getByTestId('stage-0')).toHaveAttribute('data-slice','50');await page.getByRole('button',{name:tab,exact:true}).click();await page.screenshot({path:`${shots}/analysis-${lang}.png`})}
 expect(navigations).toBe(0);expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
});

test('headed Chrome window restores, maximizes and resizes actual native window',async({playwright})=>{
 const browser=await playwright.chromium.launch({headless:false,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--enable-unsafe-swiftshader']});
 try{
  const context=await browser.newContext({viewport:null});const p=await context.newPage();const a=audit(p);await start(p);const session=await context.newCDPSession(p);const {windowId}=await session.send('Browser.getWindowForTarget');const states=[];
  await session.send('Browser.setWindowBounds',{windowId,bounds:{windowState:'normal'}});await session.send('Browser.setWindowBounds',{windowId,bounds:{width:1440,height:900}});await p.getByRole('button',{name:'Quad',exact:true}).click();await loaded(p);
  for(const windowState of ['maximized','normal']){await session.send('Browser.setWindowBounds',{windowId,bounds:{windowState}});await expect.poll(async()=>(await session.send('Browser.getWindowBounds',{windowId})).bounds.windowState).toBe(windowState);await expect.poll(async()=>p.locator('.image-fit canvas').first().evaluate(c=>c.getBoundingClientRect().width)).toBeGreaterThanOrEqual(300);states.push({windowState,bounds:(await session.send('Browser.getWindowBounds',{windowId})).bounds,viewport:await p.evaluate(()=>[innerWidth,innerHeight])});await p.screenshot({path:`${shots}/native-window-${windowState}.png`})}
  fs.writeFileSync(`${evidence}/native-window.json`,JSON.stringify(states,null,2));expect(a.errors).toEqual([]);expect(a.remote).toEqual([]);
 }finally{await browser.close()}
});



