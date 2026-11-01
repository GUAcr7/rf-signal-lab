"""Double-click run-demo.cmd; startup errors remain in exports/startup-error.log."""
from pathlib import Path
import sys
import traceback


if __name__=='__main__':
    try:
        from viewer import main
        raise SystemExit(main())
    except Exception:
        message=traceback.format_exc();folder=Path(__file__).resolve().parent/'exports';folder.mkdir(exist_ok=True)
        (folder/'startup-error.log').write_text(message,encoding='utf-8')
        print(message)
        print('Please read README.md. Install Python dependencies with setup.cmd first if needed.')
        sys.exit(1)
