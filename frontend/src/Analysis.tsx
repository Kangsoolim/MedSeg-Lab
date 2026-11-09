import {t,methodName} from './i18n';
import {useTranslation} from 'react-i18next';
import { useState } from 'react';
import type { CaseData, Method, Selection } from './types';
import { COLORS, fmt } from './types';
export function ErrorChart({ data, method, k, onSlice, compact = false }: {
    data: CaseData;
    method: Method;
    k: number;
    onSlice: (k: number) => void;
    compact?: boolean;
}) {
    useTranslation();
    const [unit, setUnit] = useState<'mm2' | 'voxels'>('mm2');
    const rows = method.analysis?.slices;
    if (!rows)
        return <div className="analysis-empty">{t("\u6CA1\u6709\u53EF\u7528 GT\uFF0C\u672A\u8BA1\u7B97\u9010\u5207\u7247 FP/FN\u3002\u5F71\u50CF\u4E0E\u9884\u6D4B\u4ECD\u53EF\u6D4F\u89C8\u3002")}</div>;
    const w = 760, h = compact ? 132 : 190, left = 48, right = 14, top = 15, bottom = 28;
    const chartW = w - left - right, chartH = h - top - bottom;
    const max = Math.max(1, ...rows.flatMap(r => [r[`fp_${unit}`], r[`fn_${unit}`]]));
    const x = (i: number) => left + (i + .5) / rows.length * chartW;
    const y = (v: number) => top + chartH - v / max * chartH;
    const path = (kind: 'fp' | 'fn') => rows.map((r, i) => `${i ? 'L' : 'M'}${x(i).toFixed(2)},${y(r[`${kind}_${unit}`]).toFixed(2)}`).join(' ');
    const current = rows[k];
    return <section className={`chart-panel ${compact ? 'compact' : ''}`} aria-label={t("\u9010\u5207\u7247\u771F\u5B9E\u8BEF\u5DEE")}>
  <div className="section-heading"><h3>{t("\u5207\u7247\u8BEF\u5DEE\u66F2\u7EBF")}<span className="muted">{methodName(method)}</span></h3><div className="chart-legend"><span><i className="dot" style={{ background: COLORS.fp }}/>FP</span><span><i className="dot" style={{ background: COLORS.fn }}/>FN</span><select aria-label={t("\u8BEF\u5DEE\u66F2\u7EBF\u5355\u4F4D")} value={unit} onChange={e => setUnit(e.target.value as 'mm2' | 'voxels')}><option value="mm2">{t("\u9762\u79EF mm\u00B2")}</option><option value="voxels">{t("\u4F53\u7D20\u6570")}</option></select></div></div>
  <svg className="error-chart" viewBox={`0 0 ${w} ${h}`} aria-label={t("\u70B9\u51FB\u771F\u5B9E\u5207\u7247\u8DF3\u8F6C\u5F71\u50CF")} role="group">
   {[0, .5, 1].map(f => <g key={f}><line x1={left} x2={w - right} y1={y(max * f)} y2={y(max * f)} stroke="#e7edf5"/><text x={left - 8} y={y(max * f) + 4} textAnchor="end">{Math.round(max * f)}</text></g>)}
   <path d={path('fp')} fill="none" stroke={COLORS.fp} strokeWidth="2"/><path d={path('fn')} fill="none" stroke={COLORS.fn} strokeWidth="2"/>
   <line x1={x(k)} x2={x(k)} y1={top} y2={h - bottom} stroke="#226ce2" strokeDasharray="4 3"/>
   {[0, Math.floor(rows.length / 2), rows.length - 1].map(i => <text key={i} x={x(i)} y={h - 7} textAnchor="middle">k={i} · {fmt(data.spatial.slice_positions_mm[i], 1)} mm</text>)}
   {rows.map((r, i) => <rect className="chart-hit" key={i} role="button" tabIndex={i === k ? 0 : -1} aria-label={t("\u8DF3\u8F6C\u5207\u7247 k={{v0}}", { v0: i })} data-testid={`chart-slice-${i}`} x={left + i / rows.length * chartW} y={top} width={chartW / rows.length} height={chartH} fill="transparent" onClick={() => onSlice(i)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ')
        onSlice(i); if (e.key === 'ArrowRight')
        onSlice(Math.min(rows.length - 1, i + 1)); if (e.key === 'ArrowLeft')
        onSlice(Math.max(0, i - 1)); }}><title>{`k=${i} · s=${fmt(data.spatial.slice_positions_mm[i], 1)} mm · FP ${r.fp_voxels} / FN ${r.fn_voxels} / TP ${r.tp_voxels} voxels`}</title></rect>)}
  </svg><p className="chart-readout mono" data-testid="chart-readout">k={k} · s={fmt(data.spatial.slice_positions_mm[k], 1)} mm　 FP {fmt(current[`fp_${unit}`], unit === 'voxels' ? 0 : 1)}　 FN {fmt(current[`fn_${unit}`], unit === 'voxels' ? 0 : 1)}　 TP {fmt(current[`tp_${unit}`], unit === 'voxels' ? 0 : 1)} {unit === 'mm2' ? 'mm²' : 'voxels'}</p>
 </section>;
}
export function VolumeAnalysis({ method }: {
    method: Method;
}) {
    useTranslation();
    const v = method.analysis?.volume;
    if (!v)
        return <section className="volume-analysis"><h3>{t('Prediction volume')}</h3><strong>{fmt(method.computed_pred_volume_ml??method.components.components.reduce((sum,c)=>sum+c.volume_ml,0))} mL</strong><p className="notice">{t("GT \u4E0D\u53EF\u7528\uFF0C\u771F\u5B9E\u4F53\u79EF\u8BEF\u5DEE\u5206\u89E3\u672A\u751F\u6210\u3002")}</p></section>;
    const fields: [
        string,
        number,
        string
    ][] = [[t("GT \u4F53\u79EF"), v.gt_ml, 'gt'], [t("\u9884\u6D4B\u4F53\u79EF"), v.pred_ml, method.color_key], [t("FP \u4F53\u79EF"), v.fp_ml, 'fp'], [t("FN \u4F53\u79EF"), v.fn_ml, 'fn'], [t("\u51C0\u4F53\u79EF\u8BEF\u5DEE"), v.net_error_ml, ''], [t("\u7EDD\u5BF9\u4F53\u79EF\u8BEF\u5DEE"), v.absolute_error_ml, '']];
    return <section className="volume-analysis"><div className="section-heading"><h3>{t("\u4F53\u79EF\u8BEF\u5DEE\u5206\u89E3")}</h3><span className="data-label">{t("\u65B0\u589E\u4F53\u7D20\u5206\u6790 \u00B7 mL")}</span></div><div className="volume-values">{fields.map(([label, value, color]) => <div key={label}><span>{label}</span><strong style={{ color: COLORS[color] }}>{fmt(value)}</strong></div>)}</div><p className="small">{t("\u51C0\u4F53\u79EF\u8BEF\u5DEE = FP \u2212 FN\u3002\u4E24\u79CD\u9519\u8BEF\u53EF\u80FD\u76F8\u4E92\u62B5\u6D88\uFF1B\u7EDD\u5BF9\u4F53\u79EF\u8BEF\u5DEE\u4E0D\u7B49\u4E8E FP + FN\u3002")}</p></section>;
}
export function ComponentTable({ method, selection, onSelect }: {
    method: Method;
    selection: Selection;
    onSelect: (s: Selection) => void;
}) {
    useTranslation();
    const [kind, setKind] = useState<'prediction' | 'fp'>('prediction');
    const [page, setPage] = useState(0);
    const set = kind === 'fp' ? method.fp_components : method.components;
    const rows = set?.components ?? [];
    const pageSize = 8;
    return <section className="component-table"><div className="section-heading"><h3>{t("\u4E09\u7EF4\u8FDE\u901A\u5206\u91CF")}<span className="muted">{t("26 \u8FDE\u901A")}</span></h3><select aria-label={t("\u5206\u91CF\u7C7B\u578B")} value={kind} onChange={e => { setKind(e.target.value as 'prediction' | 'fp'); setPage(0); }}><option value="prediction">{t("\u9884\u6D4B\u524D\u666F")}</option><option value="fp" disabled={!method.fp_components}>{t("FP \u533A\u57DF")}</option></select></div><p className="small">{t("\u5171")}{rows.length}{t("\u4E2A\uFF1B\u6309\u4F53\u79EF\u964D\u5E8F\u3002\u9884\u6D4B\u5206\u91CF\u53EF\u80FD\u5305\u542B TP\uFF0C\u4E0D\u80FD\u5C06\u6240\u6709\u5206\u91CF\u90FD\u89C6\u4E3A FP\u3002")}</p>
 <div className="table-scroll"><table><thead><tr><th>{t("\u5206\u91CF")}</th><th>{t("\u4F53\u79EF mL")}</th><th>{t("GT \u76F8\u4EA4 voxels")}</th><th>{t("\u5207\u7247\u8303\u56F4 k")}</th><th>{t("\u5230\u6700\u5927\u5206\u91CF mm")}</th></tr></thead><tbody>{rows.slice(page * pageSize, (page + 1) * pageSize).map(c => <tr key={c.id} className={selection?.method === method.id && selection.kind === kind && selection.id === c.id ? 'selected-row' : ''} onClick={() => onSelect({ method: method.id, kind, id: c.id })}><td><button className="text-button" onClick={e => { e.stopPropagation(); onSelect({ method: method.id, kind, id: c.id }); }}>#{c.id}</button></td><td>{fmt(c.volume_ml)}</td><td>{c.gt_intersection_voxels ?? t("\u672A\u8BA1\u7B97")}</td><td>{c.bbox_ijk[0][2]}–{c.bbox_ijk[1][2]}</td><td>{fmt(c.min_distance_to_largest_prediction_mm, 1)}</td></tr>)}</tbody></table></div>
 <div className="pagination"><span>{t("\u6700\u5C0F\u4F53\u7D20\u4E2D\u5FC3\u8DDD\u79BB\uFF1B20 mm \u4EC5\u4F5C\u63CF\u8FF0\uFF0C\u975E\u4E34\u5E8A\u9608\u503C\u3002")}</span><button disabled={page === 0} onClick={() => setPage(p => p - 1)}>{t("\u4E0A\u4E00\u9875")}</button><span>{rows.length ? Math.min(page + 1, Math.ceil(rows.length / pageSize)) : 0} / {Math.ceil(rows.length / pageSize)}</span><button disabled={(page + 1) * pageSize >= rows.length} onClick={() => setPage(p => p + 1)}>{t("\u4E0B\u4E00\u9875")}</button></div></section>;
}
