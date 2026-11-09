import {defineConfig} from '@playwright/test';
import path from 'node:path';
import base from './playwright.phase3a-final.config';
process.env.MEDSEG_ACCEPTANCE_SHOTS=path.resolve('../docs/phase3a-final/screenshots');
export default defineConfig({...base,testDir:'../tests/phase3a-browser',testMatch:'offline.spec.mjs',outputDir:'../tests/browser-results/phase3a-final-offline',reporter:[['list'],['json',{outputFile:'../docs/phase3a-final/offline-browser-results.json'}]]});
