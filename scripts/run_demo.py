"""Run a minimal demo: start a master and two workers as subprocesses."""
import subprocess
import sys
import time
import os

here = os.path.dirname(os.path.dirname(__file__))
python = sys.executable

procs = []
try:
    print('Starting master...')
    p_master = subprocess.Popen([python, '-m', 'src.master', '--port', '6000'])
    procs.append(p_master)
    time.sleep(0.5)
    print('Starting worker 1...')
    p1 = subprocess.Popen([python, '-m', 'src.worker', '--master', '127.0.0.1:6000', '--worker-uuid', 'w-1'])
    procs.append(p1)
    time.sleep(0.2)
    print('Starting worker 2...')
    p2 = subprocess.Popen([python, '-m', 'src.worker', '--master', '127.0.0.1:6000', '--worker-uuid', 'w-2'])
    procs.append(p2)
    print('Demo running for 5s...')
    time.sleep(5)
finally:
    print('Terminating processes...')
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
