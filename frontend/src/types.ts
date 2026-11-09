import {t,methodName} from './i18n';
export type Vec3 = [
    number,
    number,
    number
];
export type MeshInfo = {
    status: string;
    path?: string;
    vertices: number;
    triangles: number;
    bounds_ras_mm?: [
        Vec3,
        Vec3
    ];
    sha256?: string;
};
export type Component = {
    id: number;
    voxels: number;
    volume_ml: number;
    bbox_ijk: [
        Vec3,
        Vec3
    ];
    bbox_ras_mm: [
        Vec3,
        Vec3
    ];
    centroid_ras_mm: Vec3;
    representative_k: number;
    gt_intersection_voxels: number | null;
    min_distance_to_largest_prediction_mm: number;
    separated_over_20mm: boolean;
    min_distance_to_gt_mm?: number | null;
    max_distance_to_gt_mm?: number | null;
    contains_gt_distant_over_20mm?: boolean | null;
    mesh: MeshInfo;
};
export type Components = {
    connectivity: 26;
    count: number;
    components: Component[];
    labels_path: string;
    gt_available: boolean;
    distance_definition: string;
};
export type SliceError = {
    k: number;
    fp_voxels: number;
    fn_voxels: number;
    tp_voxels: number;
    fp_mm2: number;
    fn_mm2: number;
    tp_mm2: number;
};
export type Analysis = {
    slices: SliceError[];
    volume: {
        gt_ml: number;
        pred_ml: number;
        fp_ml: number;
        fn_ml: number;
        net_error_ml: number;
        absolute_error_ml: number;
    };
    metrics: Record<string, number | null>;
};
export type Method = {
    asset_base?: string;
    mesh_base?: string;
    result_status?: string;
    id: string;
    name: string;
    version: string;
    color_key: string;
    components: Components;
    fp_components: Components | null;
    analysis: Analysis | null;
    frozen_metrics: Record<string, string> | null;
    computed_pred_volume_ml?: number;
    source: Record<string, unknown>;
};
export type Spatial = {
    shape: Vec3;
    affine: number[][];
    spacing_mm: Vec3;
    axis_codes: string[];
    unit: string;
    slice_centers_ras_mm: Vec3[];
    slice_positions_mm: number[];
    slice_normal_ras: Vec3;
    display_aspect: number;
    native_affine: number[][];
    to_ras_ornt: number[][];
};
export type Target = {
    name: string;
    label: string;
    native: Vec3;
    slice: number;
    ras_mm: Vec3;
    canonical_ijk: Vec3;
    prediction_component_ids?: Record<string, number>;
    fp_component_ids?: Record<string, number>;
    gt_foreground?: boolean;
    distance_to_gt_mm?: number;
};
export type CaseData = {
    result_status?: string;
    run_id?: string;
    case_id: string;
    title: string;
    analysis_note: string;
    spatial: Spatial;
    default_slice: number;
    targets: Target[];
    methods: Method[];
    gt_mesh: MeshInfo | null;
    has_gt: boolean;
    status: string;
    blocked_reason?: string | null;
    asset_base: string;
    mesh_base: string;
    display_modes: string[];
    static_figures: string[];
    ct_source: Record<string, unknown>;
    gt_source: Record<string, unknown> | null;
    b1_build_id?: string;
    generated_at: string;
    hu_window: [
        number,
        number
    ];
};
export type CaseEntry = {
    case_id: string;
    title: string;
    manifest: string;
};
export type IndexData = {
    schema_version: string;
    cases: CaseEntry[];
    frozen_summary?: Record<string, string>[];
    metric_source?: string;
    metric_source_sha256?: string;
};
export type Selection = {
    method: string;
    kind: 'prediction' | 'fp';
    id: number;
} | null;
export const COLORS: Record<string, string> = { gt: '#17658b', traditional: '#aa720d', unet: '#7450a6', tp: '#2185b5', fp: '#e56839', fn: '#e4b637' };
export const modeName=(mode:string,methods:Method[])=>{const id=mode.endsWith('_error')?mode.slice(0,-6):mode;const method=methods.find(m=>m.id===id);const name=method?methodName(method):id;return mode==='ct'?t('原始 CT'):mode==='gt'?'GT':mode.endsWith('_error')?t('{{v0}} 误差',{v0:name}):name};
export const url=(path:string)=>path.startsWith('http://127.0.0.1:8008/')||path.startsWith('/')?path:`/${path}`;
export const fmt=(value:unknown,digits=3)=>value!==null&&value!==undefined&&Number.isFinite(Number(value))?Number(value).toFixed(digits):'—';
