import {t,translateMessage} from './i18n';
import {useTranslation} from 'react-i18next';
import { useEffect, useRef, useState, memo } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { CaseData, Selection, Vec3 } from './types';
import { modeName, url } from './types';
export type Transform = {
    scale: number;
    x: number;
    y: number;
};
const cache = new Map<string, Promise<HTMLImageElement>>();
function image(path: string) {
    let hit = cache.get(path);
    if (hit)
        return hit;
    hit = new Promise<HTMLImageElement>((resolve, reject) => { const im = new Image(); im.onload = () => resolve(im); im.onerror = () => { cache.delete(path); reject(new Error(t("\u56FE\u7247\u8D44\u6E90\u7F3A\u5931\uFF1A{{v0}}", { v0: path }))); }; im.crossOrigin = 'anonymous'; im.src = url(path); });
    cache.set(path, hit);
    while (cache.size > 36)
        cache.delete(cache.keys().next().value as string);
    return hit;
}
export const Viewer = memo(function Viewer({ data, k, mode, onMode, onSlice, opacity, contour, transform, onTransform, selection, index, onPick, seed, roi }: {
    onPick?: (point:Vec3)=>void;
    seed?: Vec3|null;
    roi?: number[]|null;
    data: CaseData;
    k: number;
    mode: string;
    onMode: (v: string) => void;
    onSlice: (delta: number) => void;
    opacity: number;
    contour: boolean;
    transform: Transform;
    onTransform: Dispatch<SetStateAction<Transform>>;
    selection: Selection;
    index: number;
}) {
    useTranslation();
    const canvas = useRef<HTMLCanvasElement>(null);
    const stage = useRef<HTMLDivElement>(null);
    const [status, setStatus] = useState(t("\u52A0\u8F7D\u5F53\u524D\u5207\u7247\u2026"));
    const drag = useRef<{
        x: number;
        y: number;
    } | null>(null);
    // Explicit physical-aspect contain fit. A size-container in a flex/grid child
    // previously resolved to zero for the second quad row in short windows.
    const [fit, setFit] = useState({ width: 0, height: 0 });
    useEffect(() => {
        const el = stage.current;
        if (!el)
            return;
        const observer = new ResizeObserver(([entry]) => {
            const { width, height } = entry.contentRect;
            const aspect = data.spatial.display_aspect;
            const w = Math.max(0, Math.min(width, height * aspect));
            setFit({ width: w, height: w / aspect });
        });
        observer.observe(el);
        return () => observer.disconnect();
    }, [data.spatial.display_aspect]);
    useEffect(() => {
        let cancelled = false;
        setStatus(t("\u52A0\u8F7D\u5F53\u524D\u5207\u7247\u2026"));
        const suffix = `${String(k).padStart(3, '0')}.png`;
        const paths = [`${data.asset_base}/ct/${suffix}`];
        if (mode !== 'ct')
            paths.push(`${data.methods.find(m=>m.id===(mode.endsWith('_error')?mode.slice(0,-6):mode))?.asset_base??data.asset_base}/${mode}/${suffix}`);
        const selectedMethod = selection && data.methods.find(m => m.id === selection.method);
        const componentSet = selectedMethod && (selection?.kind === 'fp' ? selectedMethod.fp_components : selectedMethod.components);
        if (componentSet)
            paths.push(`${selectedMethod?.mesh_base??data.mesh_base}/${componentSet.labels_path}/${suffix}`);
        Promise.all(paths.map(image)).then(images => {
            if (cancelled || !canvas.current)
                return;
            if (images.some(im => im.width !== data.spatial.shape[0] || im.height !== data.spatial.shape[1]))
                throw new Error(t("\u5F71\u50CF\u56FE\u5C42\u5C3A\u5BF8\u4E0D\u4E00\u81F4\uFF1B\u62D2\u7EDD\u62C9\u4F38\u5BF9\u9F50\u3002"));
            const c = canvas.current;
            c.width = images[0].width;
            c.height = images[0].height;
            const ctx = c.getContext('2d', { willReadFrequently: true })!;
            ctx.imageSmoothingEnabled = false;
            ctx.drawImage(images[0], 0, 0);
            if (mode !== 'ct') {
                const temp = document.createElement('canvas');
                temp.width = c.width;
                temp.height = c.height;
                const t = temp.getContext('2d', { willReadFrequently: true })!;
                t.drawImage(images[1], 0, 0);
                if (contour) {
                    const px = t.getImageData(0, 0, c.width, c.height);
                    const src = new Uint8ClampedArray(px.data);
                    const w = c.width, h = c.height;
                    for (let y = 0; y < h; y++)
                        for (let x = 0; x < w; x++) {
                            const q = (y * w + x) * 4;
                            if (!src[q + 3])
                                continue;
                            let edge = x === 0 || y === 0 || x === w - 1 || y === h - 1;
                            for (const n of [-w, w, -1, 1]) {
                                const p = q + n * 4;
                                if (src[p + 3] !== src[q + 3] || src[p] !== src[q] || src[p + 1] !== src[q + 1] || src[p + 2] !== src[q + 2])
                                    edge = true;
                            }
                            if (!edge)
                                px.data[q + 3] = 0;
                        }
                    t.putImageData(px, 0, 0);
                }
                ctx.globalAlpha = opacity;
                ctx.drawImage(temp, 0, 0);
                ctx.globalAlpha = 1;
            }
            if (componentSet && selection) {
                const t = document.createElement('canvas');
                t.width = c.width;
                t.height = c.height;
                const tc = t.getContext('2d', { willReadFrequently: true })!;
                tc.drawImage(images[images.length - 1], 0, 0);
                const pixels = tc.getImageData(0, 0, c.width, c.height);
                for (let q = 0; q < pixels.data.length; q += 4) {
                    const id = pixels.data[q] + pixels.data[q + 1] * 256;
                    pixels.data[q] = 70;
                    pixels.data[q + 1] = 255;
                    pixels.data[q + 2] = 207;
                    pixels.data[q + 3] = id === selection.id ? 210 : 0;
                }
                tc.putImageData(pixels, 0, 0);
                ctx.drawImage(t, 0, 0);
            }
            setStatus('');
        }).catch(e => { if (!cancelled)
            setStatus(e.message); });
        return () => { cancelled = true; };
    }, [data, k, mode, opacity, contour, selection]);
    useEffect(() => { const el = stage.current; if (!el)
        return; const wheel = (event: WheelEvent) => { event.preventDefault(); if (event.ctrlKey || event.shiftKey) {
        onTransform(t => ({ ...t, scale: Math.min(8, Math.max(.5, t.scale * (event.deltaY < 0 ? 1.12 : 1 / 1.12))) }));
    }
    else if (event.deltaY !== 0)
        onSlice(event.deltaY > 0 ? 1 : -1); }; el.addEventListener('wheel', wheel, { passive: false }); return () => el.removeEventListener('wheel', wheel); }, [onSlice, onTransform]);
    return <section className="viewport" aria-label={t("\u89C6\u56FE {{v0}}", { v0: index + 1 })}>
    <div className="viewport-bar"><span className="view-number">0{index + 1}</span><select aria-label={t("\u89C6\u56FE {{v0}} \u5185\u5BB9", { v0: index + 1 })} value={mode} onChange={e => onMode(e.target.value)}>{data.display_modes.map(m => <option key={m} value={m}>{modeName(m, data.methods)}</option>)}</select><span className="mono">k={k}</span></div>
    <div ref={stage} className="image-stage" data-testid={`stage-${index}`} data-transform={`${transform.scale},${transform.x},${transform.y}`} data-slice={k} onPointerDown={e => { if (e.button !== 0)
        return; if(onPick){const box=canvas.current?.getBoundingClientRect();if(box&&!status&&box.width&&box.height){const u=(e.clientX-box.left)/box.width,v=(e.clientY-box.top)/box.height;if(u>=0&&u<1&&v>=0&&v<1)onPick([Math.floor(u*data.spatial.shape[0]),data.spatial.shape[1]-1-Math.floor(v*data.spatial.shape[1]),k])}return;} e.currentTarget.setPointerCapture(e.pointerId); drag.current = { x: e.clientX, y: e.clientY }; }} onPointerMove={e => { if (!drag.current || !fit.width || !fit.height)
        return; const dx = e.clientX - drag.current.x, dy = e.clientY - drag.current.y; drag.current = { x: e.clientX, y: e.clientY }; onTransform(t => ({ ...t, x: t.x + dx / fit.width, y: t.y + dy / fit.height })); }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onDoubleClick={() => onTransform({ scale: 1, x: 0, y: 0 })}>
      <div className="image-fit" style={{ width: fit.width, height: fit.height, transform: `translate(${transform.x * fit.width}px,${transform.y * fit.height}px) scale(${transform.scale})`, visibility: status ? 'hidden' : 'visible' }}><canvas ref={canvas} aria-label={`${data.case_id} ${modeName(mode, data.methods)} k=${k}`}/>{(seed||roi)&&<svg className="selection-overlay" viewBox={`0 0 ${data.spatial.shape[0]} ${data.spatial.shape[1]}`} preserveAspectRatio="none" aria-label={t('Seed and ROI overlay')}>{roi&&k>=roi[4]&&k<roi[5]&&<rect x={roi[0]} y={data.spatial.shape[1]-roi[3]} width={roi[1]-roi[0]} height={roi[3]-roi[2]} fill="none" stroke="#46ffcf" strokeWidth="1.5"/>}{seed&&seed[2]===k&&<g stroke="#ff6779" strokeWidth="1.5"><path d={`M ${seed[0]-6+.5} ${data.spatial.shape[1]-seed[1]-.5} h 12 M ${seed[0]+.5} ${data.spatial.shape[1]-seed[1]-6-.5} v 12`}/><circle cx={seed[0]+.5} cy={data.spatial.shape[1]-seed[1]-.5} r="3" fill="none"/></g>}</svg>}</div>
      <span className="orientation top">A</span><span className="orientation bottom">P</span><span className="orientation left">L</span><span className="orientation right">R</span>
      <span className="image-caption">closest-RAS · {Math.round(transform.scale * 100)}%</span><span className="window-caption">HU {data.hu_window.join(' / ')}</span>
      {status && <div className="image-status" role="status">{translateMessage(status)}</div>}
    </div>
  </section>;
});
