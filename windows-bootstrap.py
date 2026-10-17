"""Prepare Conda DLL search paths before importing the application; no activation needed."""
import os
from pathlib import Path
import runpy
import re
import sys

_dll_handles = []
prefix = Path(sys.prefix)
if os.name == 'nt' and (prefix / 'conda-meta').is_dir():
    locations = [prefix, prefix/'Library/mingw-w64/bin', prefix/'Library/usr/bin',
                 prefix/'Library/bin', prefix/'Scripts', prefix/'bin']
    existing = [str(p) for p in locations if p.is_dir()]
    os.environ['PATH'] = os.pathsep.join(existing + [os.environ.get('PATH', '')])
    os.environ['CONDA_PREFIX'] = str(prefix)
    if hasattr(os, 'add_dll_directory'):
        for path in existing:
            _dll_handles.append(os.add_dll_directory(path))

if __name__ == '__main__':
    if sys.argv[1:] == ['--check']:
        import yaml
        version = tuple(int(p) for p in re.findall(r'\d+', yaml.__version__)[:3])
        if sys.version_info < (3, 10) or not ((6, 0, 2) <= version < (7,)):
            raise SystemExit('Python >=3.10 and PyYAML >=6.0.2,<7 are required')
        print(f'Runtime OK: Python {sys.version.split()[0]}, PyYAML {yaml.__version__}')
    else:
        if len(sys.argv) < 2:
            raise SystemExit('Usage: windows-bootstrap.py SCRIPT [ARGS]')
        script = Path(sys.argv[1]).resolve()
        sys.argv = sys.argv[1:]
        sys.path.insert(0, str(script.parent))
        runpy.run_path(str(script), run_name='__main__')
