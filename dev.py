"""Run the frontend and backend together: python3 dev.py."""

import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def main():
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not python.is_file():
        sys.exit('Missing .venv. Follow the Python setup in backend/README.md first.')
    if not npm or not (ROOT / 'frontend/node_modules').is_dir():
        sys.exit('Install Node.js, then run npm install in frontend/ first.')

    commands = [
        ([str(python), '-m', 'uvicorn', 'backend.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000'], ROOT),
        ([npm, 'run', 'dev', '--', '--port', '5173', '--strictPort'], ROOT / 'frontend'),
    ]
    processes = []
    exit_code = 0
    print('Starting both servers. Open http://localhost:5173 once ready. Ctrl+C stops both.', flush=True)
    try:
        for command, cwd in commands:
            processes.append(subprocess.Popen(command, cwd=cwd, start_new_session=os.name != 'nt'))
        while True:
            for process in processes:
                status = process.poll()
                if status is not None:
                    print('A server stopped; shutting down both servers.', flush=True)
                    return status or 1
            time.sleep(0.25)
    except KeyboardInterrupt:
        print('\nStopping both servers…', flush=True)
    finally:
        for process in processes:
            if os.name == 'nt':
                if process.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    process.kill()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait()
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
