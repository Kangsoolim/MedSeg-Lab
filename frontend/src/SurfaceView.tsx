import {t,translateMessage,methodName} from './i18n';
import {useTranslation} from 'react-i18next';
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import type { CaseData, MeshInfo, Selection } from './types';
import { COLORS, url, fmt } from './types';
async function geometry(path: string, signal: AbortSignal) {
    const r = await fetch(url(path), { signal });
    if (!r.ok)
        throw new Error(t("\u4E09\u7EF4\u7F51\u683C\u7F3A\u5931 ({{v0}}): {{v1}}", { v0: r.status, v1: path }));
    const b = await r.arrayBuffer();
    if (b.byteLength < 8)
        throw new Error(t("\u7F51\u683C\u5934\u635F\u574F"));
    const h = new DataView(b);
    const nv = h.getUint32(0, true), nf = h.getUint32(4, true);
    if (!nv || !nf || b.byteLength !== 8 + nv * 12 + nf * 12)
        throw new Error(t("\u7F51\u683C\u957F\u5EA6\u4E0E\u9876\u70B9/\u4E09\u89D2\u9762\u6570\u91CF\u4E0D\u7B26"));
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(b, 8, nv * 3), 3));
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(b, 8 + nv * 12, nf * 3), 1));
    g.computeVertexNormals();
    g.computeBoundingBox();
    return g;
}
export default function SurfaceView({ data, k, selection, onSelect }: {
    data: CaseData;
    k: number;
    selection: Selection;
    onSelect: (s: Selection) => void;
}) {
    useTranslation();
    const host = useRef<HTMLDivElement>(null);
    const sceneRef = useRef<{
        scene: THREE.Scene;
        render: () => void;
        camera: THREE.PerspectiveCamera;
        controls: OrbitControls;
        surfaces: THREE.Mesh[];
        fit: () => void;
    } | null>(null);
    const [status, setStatus] = useState(t("\u6B63\u5728\u52A0\u8F7D\u771F\u5B9E\u8868\u9762\u2026"));
    const [error, setError] = useState('');
    const [ready, setReady] = useState(false);
    const [layers, setLayers] = useState<Record<string, {
        visible: boolean;
        opacity: number;
    }>>(() => Object.fromEntries(['gt', ...data.methods.map(m => m.id)].map(id => [id, { visible: true, opacity: id === 'gt' ? .35 : .65 }])));
    const [plane, setPlane] = useState(true);
    useEffect(() => {
        const controller = new AbortController();
        const el = host.current!;
        let disposed = false;
        let renderer: THREE.WebGLRenderer;
        let controls: OrbitControls;
        const scene = new THREE.Scene();
        scene.background = new THREE.Color('#101b2b');
        try {
            renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            renderer.domElement.setAttribute('aria-label', t("\u771F\u5B9E\u4E09\u7EF4\u8868\u9762\u4EA4\u4E92\u753B\u5E03"));
            renderer.domElement.dataset.testid = 'surface-canvas';
            el.append(renderer.domElement);
        }
        catch (e) {
            setError(t("WebGL \u521D\u59CB\u5316\u5931\u8D25\uFF1A{{v0}}", { v0: String(e) }));
            return () => controller.abort();
        }
        const camera = new THREE.PerspectiveCamera(38, 1, .1, 10000);
        camera.up.set(0, 0, 1);
        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = false;
        const render = () => { if (disposed)
            return; renderer.render(scene, camera); renderer.domElement.dataset.camera = camera.position.toArray().map(v => v.toFixed(3)).join(','); };
        controls.addEventListener('change', render);
        for (const t of data.targets) {
            const marker = new THREE.Mesh(new THREE.SphereGeometry(1.5, 12, 8), new THREE.MeshBasicMaterial({ color: t.name === 'T2' ? '#46ffcf' : '#7acbff', depthTest: false }));
            marker.position.set(...t.ras_mm);
            marker.renderOrder = 10;
            scene.add(marker);
            const labelCanvas = document.createElement('canvas');
            labelCanvas.width = 96;
            labelCanvas.height = 48;
            const ctx = labelCanvas.getContext('2d')!;
            ctx.fillStyle = t.name === 'T2' ? '#46ffcf' : '#7acbff';
            ctx.font = 'bold 28px sans-serif';
            ctx.fillText(t.name, 8, 32);
            const texture = new THREE.CanvasTexture(labelCanvas);
            const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true }));
            label.position.set(t.ras_mm[0] + 7, t.ras_mm[1], t.ras_mm[2] + 4);
            label.scale.set(12, 6, 1);
            label.renderOrder = 11;
            scene.add(label);
        }
        scene.add(new THREE.AmbientLight(0xffffff, 1.6));
        const light = new THREE.DirectionalLight(0xffffff, 2.5);
        light.position.set(1, -1, 2);
        camera.add(light);
        scene.add(camera);
        const surfaces: THREE.Mesh[] = [];
        const box = new THREE.Box3();
        const fit = () => { if (box.isEmpty())
            return; const center = box.getCenter(new THREE.Vector3()); const size = box.getSize(new THREE.Vector3()); const radius = Math.max(size.x, size.y, size.z, 10); controls.target.copy(center); camera.position.copy(center).add(new THREE.Vector3(radius * 1.15, -radius * 1.65, radius * .95)); camera.near = Math.max(.01, radius / 1000); camera.far = radius * 30; camera.updateProjectionMatrix(); controls.update(); render(); };
        sceneRef.current = { scene, render, camera, controls, surfaces, fit };
        const resize = () => { const w = el.clientWidth, h = el.clientHeight; if (!w || !h)
            return; renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix(); render(); };
        const observer = new ResizeObserver(resize);
        observer.observe(el);
        resize();
        const resources: {
            method: string;
            id: number;
            info: MeshInfo;
        }[] = [];
        if (data.gt_mesh?.status === 'ready')
            resources.push({ method: 'gt', id: 0, info: data.gt_mesh });
        for (const m of data.methods)
            for (const c of m.components.components)
                if (c.mesh.status === 'ready')
                    resources.push({ method: m.id, id: c.id, info: c.mesh });
        let loaded = 0;
        Promise.all(resources.map(async (r) => {
            const g = await geometry(`${data.methods.find(m=>m.id===r.method)?.mesh_base??data.mesh_base}/${r.info.path}`, controller.signal);
            if (disposed) {
                g.dispose();
                return;
            }
            const material = new THREE.MeshStandardMaterial({ color: COLORS[data.methods.find(m => m.id === r.method)?.color_key ?? r.method] ?? COLORS.unet, transparent: true, opacity: r.method === 'gt' ? .35 : .65, side: THREE.DoubleSide, roughness: .72, metalness: .04, depthWrite: false });
            const mesh = new THREE.Mesh(g, material);
            mesh.userData = { method: r.method, id: r.id };
            scene.add(mesh);
            surfaces.push(mesh);
            box.expandByObject(mesh);
            loaded++;
            setStatus(t("\u771F\u5B9E\u8868\u9762 {{v0}} / {{v1}}", { v0: loaded, v1: resources.length }));
        })).then(() => { if (disposed)
            return; fit(); setReady(true); setStatus(''); renderer.domElement.dataset.surfaceCount = String(surfaces.length); render(); }).catch(e => { if (e.name !== 'AbortError' && !disposed)
            setError(t("\u4E09\u7EF4\u52A0\u8F7D\u5931\u8D25\uFF1A{{v0}}", { v0: e.message })); });
        const down = { x: 0, y: 0 };
        const pointerDown = (e: PointerEvent) => { down.x = e.clientX; down.y = e.clientY; };
        const pointerUp = (e: PointerEvent) => { if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4)
            return; const rect = renderer.domElement.getBoundingClientRect(); const pointer = new THREE.Vector2((e.clientX - rect.left) / rect.width * 2 - 1, -(e.clientY - rect.top) / rect.height * 2 + 1); const ray = new THREE.Raycaster(); ray.setFromCamera(pointer, camera); const hit = ray.intersectObjects(surfaces.filter(s => s.visible && s.userData.method !== 'gt'))[0]; if (hit)
            onSelect({ method: hit.object.userData.method, kind: 'prediction', id: hit.object.userData.id }); };
        renderer.domElement.addEventListener('pointerdown', pointerDown);
        renderer.domElement.addEventListener('pointerup', pointerUp);
        return () => { disposed = true; controller.abort(); observer.disconnect(); controls.dispose(); renderer.domElement.removeEventListener('pointerdown', pointerDown); renderer.domElement.removeEventListener('pointerup', pointerUp); scene.traverse(o => { if (o instanceof THREE.Sprite) {
            o.material.map?.dispose();
            o.material.dispose();
        } if (o instanceof THREE.Mesh || o instanceof THREE.Line) {
            o.geometry.dispose();
            const mats = Array.isArray(o.material) ? o.material : [o.material];
            mats.forEach(m => m.dispose());
        } }); renderer.dispose(); renderer.domElement.remove(); sceneRef.current = null; };
    }, [data, onSelect]);
    useEffect(() => { const s = sceneRef.current; if (!s)
        return; for (const mesh of s.surfaces) {
        const layer = layers[mesh.userData.method];
        const selected = selection?.kind === 'prediction' && mesh.userData.method === selection.method && mesh.userData.id === selection.id;
        mesh.visible = layer?.visible ?? true;
        const mat = mesh.material as THREE.MeshStandardMaterial;
        mat.opacity = selected ? .95 : layer?.opacity ?? .65;
        mat.emissive.set(selected ? '#16ad89' : '#000000');
        mat.emissiveIntensity = selected ? .45 : 0;
    } s.render(); }, [layers, selection, ready]);
    useEffect(() => { const s = sceneRef.current; if (!s)
        return; const a = data.spatial.affine; const [nx, ny] = data.spatial.shape; const points = [[-.5, -.5, k], [nx - .5, -.5, k], [nx - .5, ny - .5, k], [-.5, ny - .5, k], [-.5, -.5, k]].map(([x, y, z]) => new THREE.Vector3(a[0][0] * x + a[0][1] * y + a[0][2] * z + a[0][3], a[1][0] * x + a[1][1] * y + a[1][2] * z + a[1][3], a[2][0] * x + a[2][1] * y + a[2][2] * z + a[2][3])); const g = new THREE.BufferGeometry().setFromPoints(points); const material = new THREE.LineBasicMaterial({ color: '#50cbea', transparent: true, opacity: .55 }); const line = new THREE.Line(g, material); line.visible = plane; s.scene.add(line); s.render(); return () => { s.scene.remove(line); g.dispose(); material.dispose(); s.render(); }; }, [data, k, plane, ready]);
    useEffect(() => {
        const s = sceneRef.current;
        if (!s || selection?.kind !== 'fp')
            return;
        const method = data.methods.find(m => m.id === selection.method);
        const c = method?.fp_components?.components.find(c => c.id === selection.id);
        if (!c?.mesh.path)
            return;
        const controller = new AbortController();
        let mesh: THREE.Mesh | undefined;
        geometry(`${data.methods.find(m=>m.id===selection.method)?.mesh_base??data.mesh_base}/${c.mesh.path}`, controller.signal).then(g => { if (controller.signal.aborted) {
            g.dispose();
            return;
        } mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: '#46ffcf', emissive: '#16ad89', emissiveIntensity: .65, depthTest:false, depthWrite:false, side: THREE.DoubleSide })); mesh.renderOrder=100; s.scene.add(mesh); s.render(); }).catch(e => { if (e.name !== 'AbortError')
            setError(e.message); });
        return () => { controller.abort(); if (mesh) {
            s.scene.remove(mesh);
            mesh.geometry.dispose();
            (mesh.material as THREE.Material).dispose();
            s.render();
        } };
    }, [data, selection, ready]);
    return <div className="surface-workspace"><div className="surface-controls"><div className="layer-controls">{['gt', ...data.methods.map(m => m.id)].map(id => <label key={id}><input type="checkbox" checked={layers[id].visible} disabled={id === 'gt' && !data.gt_mesh} onChange={e => setLayers(l => ({ ...l, [id]: { ...l[id], visible: e.target.checked } }))}/><i className="dot" style={{ background: COLORS[data.methods.find(m => m.id === id)?.color_key ?? id] }}/>{id === 'gt' ? 'GT' : methodName(data.methods.find(m => m.id === id)!)}<input aria-label={t("{{v0}} \u4E09\u7EF4\u900F\u660E\u5EA6", { v0: id })} type="range" min="0" max="100" value={Math.round(layers[id].opacity * 100)} onChange={e => setLayers(l => ({ ...l, [id]: { ...l[id], opacity: Number(e.target.value) / 100 } }))}/></label>)}</div><button onClick={() => sceneRef.current?.fit()}>{t("\u6062\u590D\u4E09\u7EF4\u89C6\u91CE")}</button><label><input type="checkbox" checked={plane} onChange={e => setPlane(e.target.checked)}/>{t("\u5207\u7247\u5E73\u9762")}</label></div>
 <div className="surface-stage" ref={host}>{status && !error && <span className="surface-status">{translateMessage(status)}</span>}<span className="surface-note">{t("RAS / mm \u00B7 \u5DE6\u952E\u65CB\u8F6C \u00B7 \u53F3\u952E\u5E73\u79FB \u00B7 \u6EDA\u8F6E\u7F29\u653E \u00B7 \u70B9\u51FB\u9884\u6D4B\u9009\u62E9\u5206\u91CF")}</span><span className="surface-orientation">R → X　 A → Y　 S → Z</span></div>
 {error && <div role="alert" className="error">{translateMessage(error)}{t("\u3002\u8BF7\u67E5\u770B\u4E0B\u65B9\u771F\u5B9E\u9759\u6001\u5907\u7528\u56FE\u3002")}</div>}
 {!data.gt_mesh && <p className="notice">{t("GT \u4E09\u7EF4\u7F51\u683C\u4E0D\u53EF\u7528\uFF1B\u672A\u751F\u6210\u66FF\u4EE3\u6A21\u578B\u3002")}</p>}
 <div className="surface-footer"><span>{ready ? t("\u771F\u5B9E\u8868\u9762\u5DF2\u52A0\u8F7D") : t("\u8868\u9762\u52A0\u8F7D\u4E2D")}{t("\u00B7 \u6240\u6709\u9884\u6D4B\u5206\u91CF\u4FDD\u7559 \u00B7 \u4E0D\u5E73\u6ED1\u3001\u4E0D\u7B80\u5316 \u00B7 \u5171\u540C affine \u4E0E\u6BEB\u7C73\u5C3A\u5EA6")}</span><span>{t("\u5F53\u524D\u5207\u7247 s =")}{fmt(data.spatial.slice_positions_mm[k], 1)} mm</span></div>
 <details className="static-backup"><summary>{t("\u5DF2\u9A8C\u6536\u9759\u6001\u4E09\u7EF4\u5907\u7528\u56FE\uFF08\u975E\u4EA4\u4E92\uFF09")}</summary><div>{data.static_figures.map((path, i) => <a key={path} href={url(path)} target="_blank" rel="noreferrer"><img src={url(path)} alt={t("\u9759\u6001 {{v0}}\u659C\u89C6", { v0: i === 0 ? t("\u524D") : t("\u540E") })}/></a>)}{!data.static_figures.length && <p>{t("\u6B64\u5BFC\u5165\u75C5\u4F8B\u6CA1\u6709\u9759\u6001\u5907\u7528\u56FE\u3002")}</p>}</div></details></div>;
}
