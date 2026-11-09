import {t} from './i18n';
import { useEffect, useState } from 'react';
import type { CaseData, IndexData } from './types';
export async function jsonFile<T>(path: string, signal?: AbortSignal): Promise<T> {
    const r = await fetch(path.startsWith('http://127.0.0.1:8008/')||path.startsWith('/')?path:`/${path}`, { signal });
    if (!r.ok)
        throw new Error(t("\u6570\u636E\u6587\u4EF6\u52A0\u8F7D\u5931\u8D25 ({{v0}}): {{v1}}", { v0: r.status, v1: path }));
    const value = await r.json();
    return value as T;
}
export function validateCase(c: CaseData) {
    if (!c || !c.case_id || !Array.isArray(c.methods) || !c.methods.length || !c.spatial)
        throw new Error(t("\u75C5\u4F8B Schema \u7F3A\u5931\uFF1Acase_id / methods / spatial"));
    const s = c.spatial;
    const expectedAspect=s.shape?.[0]*s.spacing_mm?.[0]/(s.shape?.[1]*s.spacing_mm?.[1]);
    if(!Number.isFinite(s.display_aspect)||s.display_aspect<=0||Math.abs(s.display_aspect-expectedAspect)>1e-6)throw new Error(t('物理显示比例与空间清单不一致'));
    if(!c.has_gt&&(c.display_modes?.includes('gt')||c.display_modes?.some(m=>m.endsWith('_error'))||c.methods.some(m=>m.frozen_metrics||m.fp_components)))throw new Error(t('图层模式与 GT 状态不一致'));
    if (!Array.isArray(s.shape) || s.shape.length !== 3 || s.shape.some(n => !Number.isInteger(n) || n < 1) || s.unit !== 'mm' || s.axis_codes.join('') !== 'RAS')
        throw new Error(t("\u7A7A\u95F4\u6E05\u5355\u65E0\u6548\uFF1A\u9700\u8981 closest-RAS \u4E09\u7EF4 mm \u7F51\u683C"));
    if (!Array.isArray(s.affine) || s.affine.length !== 4 || s.affine.some(row => row.length !== 4 || row.some(x => !Number.isFinite(x))) || s.spacing_mm.some(x => !Number.isFinite(x) || x <= 0))
        throw new Error(t("\u7A7A\u95F4 affine / spacing \u65E0\u6548"));
    if (s.slice_positions_mm.length !== s.shape[2] || s.slice_centers_ras_mm.length !== s.shape[2])
        throw new Error(t("\u5207\u7247\u7269\u7406\u4F4D\u7F6E\u6570\u91CF\u4E0E shape \u4E0D\u4E00\u81F4"));
    if (c.default_slice < 0 || c.default_slice >= s.shape[2] || !c.display_modes.includes('ct'))
        throw new Error(t("\u5207\u7247\u8303\u56F4\u6216 CT \u6A21\u5F0F\u65E0\u6548"));
    for (const m of c.methods) {
        if (m.analysis && !c.has_gt)
            throw new Error(t("\u65E0 GT \u7684\u6570\u636E\u4E0D\u80FD\u58F0\u660E\u8BEF\u5DEE\u5206\u6790"));
        if (m.analysis && m.analysis.slices.length !== s.shape[2])
            throw new Error(t("\u8BEF\u5DEE\u5207\u7247\u6570\u91CF\u4E0D\u5339\u914D"));
        if (m.components.connectivity !== 26 || m.components.count !== m.components.components.length)
            throw new Error(t("\u8FDE\u901A\u5206\u91CF\u6E05\u5355\u4E0D\u5339\u914D"));
    }
    return c;
}
export function useIndex() {
    const [index, setIndex] = useState<IndexData | null>(null);
    const [error, setError] = useState('');
    useEffect(() => {
        const controller = new AbortController();
        fetch('/demo/index.json',{signal:controller.signal}).then(async response=>{if(response.status===404)return {schema_version:'1.0',cases:[]} as IndexData;if(!response.ok)throw new Error('Cannot load optional demo package');const text=await response.text();if(text.trimStart().startsWith('<!doctype html')||text.trimStart().startsWith('<html'))return {schema_version:'1.0',cases:[]} as IndexData;return JSON.parse(text) as IndexData;}).then(i => {
            if (i.schema_version !== '1.0' || !Array.isArray(i.cases))
                throw new Error(t("\u6570\u636E\u5305\u7D22\u5F15\u65E0\u6548\u6216\u6CA1\u6709\u75C5\u4F8B"));
            setIndex(i);
        }).catch(e => { if (e.name !== 'AbortError')
            setError(String(e.message)); });
        return () => controller.abort();
    }, []);
    return { index, error };
}
export function useCase(path: string) {
    const [data, setData] = useState<CaseData | null>(null);
    const [error, setError] = useState('');
    useEffect(() => { const controller = new AbortController(); setData(null); setError(''); jsonFile<CaseData>(path, controller.signal).then(validateCase).then(setData).catch(e => { if (e.name !== 'AbortError')
        setError(e.message); }); return () => controller.abort(); }, [path]);
    return { data, error };
}
