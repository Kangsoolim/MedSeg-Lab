"""Disposable compute process. No HTTP or arbitrary command execution."""
import sys
from pathlib import Path
from backend.config import ROOT, run_path
from backend.training_adapter import MonaiResidualUNet, EventWriter


def main(directory):
    directory=run_path(ROOT/'runs',Path(directory))
    try:
        adapter=MonaiResidualUNet(directory)
        adapter.emit_events('status',status='preparing')
        adapter.validate_configuration()
        adapter.prepare_dataset()
        adapter.initialize_model()
        adapter.resume()
        status=adapter.train()
        adapter.export_results()
        adapter.emit_events('terminal',status=status,epoch=adapter.state['epoch'],step=adapter.state['global_step'],stop_reason=adapter.reason)
        return 0
    except Exception as error:
        # Keep traceback private; public events intentionally omit filesystem paths.
        import traceback
        traceback.print_exc()
        EventWriter(directory).emit('terminal',status='failed',error=type(error).__name__,message='Training failed; inspect private worker log / 训练失败，请检查本地工作进程日志')
        return 1


if __name__=='__main__':
    raise SystemExit(main(sys.argv[1]))
