import i18n from 'i18next';
import {initReactI18next} from 'react-i18next';
import type {Method} from './types';
import {messages,legacy} from './messages';
import {workbenchMessages} from './workbenchMessages';
import {experimentMessages} from './experimentMessages';
import {trainingMessages} from './trainingMessages';
const en:Record<string,string>={},zh:Record<string,string>={};
for(const [english,chinese] of Object.entries({...messages,...workbenchMessages,...experimentMessages,...trainingMessages})){en[english]=english;zh[english]=chinese}
Object.assign(en,{training:'Training Run',inference:'Inference Run',traditional:'Traditional Segmentation Run',frozen:'Frozen Reference Result',archived_history:'Archived history',imported_history:'Imported history',interactive_experimental:'Interactive Experimental Run',frozen_reference:'Frozen reference',train_loss:'Training Loss',val_mean_dice:'Validation Dice',learning_rate:'Learning Rate',val_empty_cases:'Empty prediction cases',val_pred_volume_ml:'Validation predicted volume',epoch_seconds:'Epoch duration',epoch_amp_skipped_steps:'AMP skipped updates',soft_dice_native_3d_mean:'Post-hoc Soft Dice',bad_epochs:'Patience count',val_loss:'Validation Loss'});
for(const [chinese,english] of Object.entries(legacy)){en[chinese]=english;zh[chinese]=chinese}
Object.assign(en,{live_training:'Live Training Run',resumed_training:'Resumed Training Run'});
let language='en';try{language=localStorage.getItem('medseg.language.v1')==='zh'?'zh':'en'}catch{/* storage may be disabled */}
void i18n.use(initReactI18next).init({resources:{en:{translation:en},zh:{translation:zh}},lng:language,fallbackLng:'en',keySeparator:false,nsSeparator:false,interpolation:{escapeValue:false},returnEmptyString:false});
function syncLanguage(lng:string){document.documentElement.lang=lng==='zh'?'zh-CN':'en';document.title=lng==='zh'?'MedSeg-Lab · 医学影像分割':'MedSeg-Lab · Medical Image Segmentation';try{localStorage.setItem('medseg.language.v1',lng)}catch{/* language switching still works */}}
i18n.on('languageChanged',syncLanguage);syncLanguage(language);
export const t=(key:string,values?:Record<string,unknown>):string=>String(i18n.t(key,values??{}));
// Errors/loading state are kept as messages, not a reason to remount a viewer.
// Reverse interpolation lets already-visible runtime messages change language.
const templates=Object.entries({...messages,...workbenchMessages,...experimentMessages,...Object.fromEntries(Object.entries(legacy).map(([a,b])=>[b,a]))});
export function translateMessage(value:string):string{
 for(const [a,b] of templates){const source=i18n.resolvedLanguage==='zh'?a:b,target=i18n.resolvedLanguage==='zh'?b:a;
  if(value===source)return target;
  if(!source.includes('{{'))continue;
  const slots=[...source.matchAll(/\{\{(\w+)\}\}/g)].map(m=>m[1]);
  const regex=source.split(/\{\{\w+\}\}/).map(s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('(.*?)');
  const match=new RegExp(`^${regex}$`).exec(value);if(match)return target.replace(/\{\{(\w+)\}\}/g,(_,key)=>translateMessage(match[slots.indexOf(key)+1]??''));
 }
 return value;
}
export const methodName=(method:Pick<Method,'name'|'result_status'>)=>{const name=method.name==='传统 V2'?t('Traditional V2'):method.name.startsWith('Interactive Experimental Run')?t('Interactive Experimental Run')+method.name.slice('Interactive Experimental Run'.length):translateMessage(method.name);return method.result_status==='frozen_comparator'?t('Frozen comparator')+' · '+name:name};
const caseLabels:Record<string,{title:string;note:string}>={
 spleen_8:{title:'U-Net closely matches GT',note:'U-Net has good 3D overlap; V2 still shows over- and under-segmentation. Inspect slices and 3D shape together, rather than volume alone.'},
 spleen_59:{title:'Traditional method over-segments',note:'V2 predicts excess volume and additional 3D regions. U-Net has a small net volume bias, but FP and FN remain and can cancel.'},
 spleen_17:{title:'Distant false positives; V2 Dice exceeds U-Net',note:'U-Net has high Recall but lower Precision, with predictions outside the target. V2 has a higher Dice but still misses tissue; both methods have limitations.'}
};
export const caseText=(id:string,kind:'title'|'note',fallback:string)=>caseLabels[id]?t(caseLabels[id][kind]):translateMessage(fallback);
export default i18n;
