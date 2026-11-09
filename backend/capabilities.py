"""Optional computation resources do not gate imaging/API startup."""
import importlib.util
from pathlib import Path

def capabilities(cfg):
    def installed(name):
        try:return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):return False
    neural=installed('torch') and installed('monai') and installed('yaml') and installed('matplotlib')
    return dict(traditional_v2=installed('SimpleITK'),unet_e17=neural and bool(cfg.get('checkpoint')) and Path(cfg['checkpoint']).is_file(),
        training=neural,course_adapter=bool(cfg.get('source_root')),input_roots_configured=bool(cfg.get('input_roots')),
        neural_runtime=neural,checkpoint_configured=bool(cfg.get('checkpoint')),devices=['cpu'],
        device_note='CPU supported. CUDA availability is checked by preflight; AMP requires CUDA. Exact resume requires the saved environment/device.')
