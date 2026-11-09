import original from './playwright.final_acceptance.config';
import {defineConfig} from '@playwright/test';
export default defineConfig({...original,testIgnore:'phase2a.spec.mjs',outputDir:'../tests/browser-results/phase2a-regression',reporter:[['list'],['json',{outputFile:'../docs/phase2a/regression-browser-results.json'}]]});
