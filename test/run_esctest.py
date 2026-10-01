#!/usr/bin/env python3
"""Run esctest (https://github.com/ThomasDickey/esctest2) inside dvtm.

usage: run_esctest.py /path/to/esctest2 [extra esctest.py arguments]

Prints the failing tests and a summary. Exits 0 even when tests fail, since
this is a conformance report and not a gate.
"""
import os
import re
import shlex
import sys
import tempfile
import time

import pexpect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMEOUT = 1500


def main():
    esctest = os.path.join(os.path.abspath(sys.argv[1]), 'esctest')
    extra = sys.argv[2:] or ['--max-vt-level', '4']
    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, 'out')
    done = os.path.join(tmp, 'done')
    log = os.path.join(tmp, 'log')
    shell = os.path.join(tmp, 'shell')
    cmd = ' '.join(['python3', 'esctest.py', '--expected-terminal', 'xterm',
                    '--logfile', shlex.quote(log), '--no-print-logs'] +
                   [shlex.quote(a) for a in extra])
    with open(shell, 'w') as f:
        f.write(f'#!/bin/sh\ncd {shlex.quote(esctest)}\n'
                f'{cmd} 2> {shlex.quote(out)}\n'
                f'touch {shlex.quote(done)}\nsleep 60\n')
    os.chmod(shell, 0o755)

    env = dict(os.environ, SHELL=shell, TERM='xterm')
    p = pexpect.spawn(os.path.join(ROOT, 'dvtm'), env=env, dimensions=(25, 80))
    start = time.time()
    while not os.path.exists(done) and time.time() - start < TIMEOUT:
        try:
            p.read_nonblocking(65536, 0.5)
        except (pexpect.TIMEOUT, pexpect.EOF):
            pass
    p.terminate(force=True)

    if not os.path.exists(done):
        print('esctest did not finish')
        return 0
    with open(out, errors='replace') as f:
        text = f.read()
    with open(log, errors='replace') as f:
        failed = re.findall(r'^\*\*\* TEST (\S+) FAILED', f.read(), re.M)
    for name in failed:
        print('FAILED', name)
    if not failed:
        print(text[-2000:])
    print(f'{len(failed)} test(s) failed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
