import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'../tests/browser',testIgnore:['final_acceptance.spec.mjs','phase2a.spec.mjs'],outputDir:'../tests/browser-results',timeout:90000,expect:{timeout:15000},workers:1,reporter:[['list'],['json',{outputFile:'../docs/browser-results.json'}]],use:{baseURL:'http://127.0.0.1:5173',viewport:{width:1366,height:768},launchOptions:{executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--enable-unsafe-swiftshader']},trace:'retain-on-failure'}});

