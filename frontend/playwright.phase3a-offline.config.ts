import {defineConfig} from '@playwright/test';
import base from './playwright.phase3a.config';
export default defineConfig({...base,testMatch:'offline.spec.mjs',outputDir:'../tests/browser-results/phase3a-offline',reporter:[['list'],['json',{outputFile:'../docs/phase3a/actual-offline-browser-results.json'}]]});
