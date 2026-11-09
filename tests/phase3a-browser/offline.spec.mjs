import fs from 'node:fs';import path from 'node:path';
import {test,expect} from '../../frontend/node_modules/@playwright/test/index.mjs';
test('actual stopped Python backend preserves static analytics and native imaging',async({page,request})=>{
 const offline=await request.get('http://127.0.0.1:8008/api/v1/health',{timeout:1500}).then(()=>false,()=>true);expect(offline).toBe(true);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.addInitScript(()=>localStorage.setItem('medseg.language.v1','en'));
 await page.goto('/');await expect(page).toHaveTitle(/MedSeg-Lab/);await expect(page.getByTestId('stage-0')).toBeVisible();await expect(page.locator('vite-error-overlay')).toHaveCount(0);
 await page.getByRole('button',{name:'Training Workspace',exact:true}).click();await expect(page.getByText('Training backend unavailable',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Run preflight',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Training Analytics',exact:true}).click();await expect(page.locator('.algorithm-status')).toContainText('Offline: static training catalog');await page.getByLabel('Training experiment',{exact:true}).selectOption('final27');await expect(page.getByTestId('point-final27-17')).toBeVisible();
 await page.getByRole('button',{name:'2D comparison',exact:true}).click();await expect(page.getByTestId('stage-1')).toBeVisible();await page.getByRole('button',{name:'3D surfaces',exact:true}).click();await expect(page.locator('.surface-stage canvas')).toBeVisible();
 const shots=process.env.MEDSEG_ACCEPTANCE_SHOTS||path.resolve('../docs/phase3a/screenshots');fs.mkdirSync(shots,{recursive:true});await page.screenshot({path:shots+'/phase3a-actual-offline.png'});expect(errors).toEqual([]);
});
