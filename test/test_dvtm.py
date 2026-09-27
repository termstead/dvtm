#!/usr/bin/env python3
import os
import shutil
import stat
import tempfile
import time
import unittest

import pexpect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = '\x07'  # ^G


class DvtmTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cmdfifo = os.path.join(self.tmp, 'cmd')
        self.status = os.path.join(self.tmp, 'status')
        self.stderr = os.path.join(self.tmp, 'stderr')
        self.editor = os.path.join(self.tmp, 'editor')
        with open(self.editor, 'w') as f:
            # dvtm-editor only reads the file back if its mtime changed
            f.write('#!/bin/sh\nsleep 1.1\neval f=\\${$#}\n'
                    'echo "echo pasted-\\$((6*7))" > "$f"\n')
        os.chmod(self.editor, stat.S_IRWXU)
        env = dict(os.environ, SHELL='/bin/sh', PS1='$ ', ENV='', TERM='xterm',
                   DVTM_EDITOR=self.editor,
                   PATH=ROOT + os.pathsep + os.environ['PATH'])
        cmd = (f'exec {ROOT}/dvtm -c {self.cmdfifo} -s {self.status} '
               f'2>{self.stderr}')
        self.p = pexpect.spawn('/bin/sh', ['-c', cmd], env=env,
                               dimensions=(24, 80), encoding='utf-8',
                               timeout=10)
        self.p.expect_exact('$ ')

    def tearDown(self):
        if self.p.isalive():
            self.p.send(MOD + 'qq')
            self.p.expect(pexpect.EOF)
        self.p.close()
        with open(self.stderr) as f:
            log = f.read()
        shutil.rmtree(self.tmp)
        self.assertNotIn('Sanitizer', log)
        self.assertNotIn('runtime error', log)
        self.assertEqual(self.p.exitstatus, 0, log)

    def sh(self, line, expect):
        self.p.send(line + '\r')
        self.p.expect_exact(expect)

    def test_shell(self):
        self.sh('echo $((6*7))xyz', '42xyz')

    def test_create_and_kill(self):
        self.p.send(MOD + 'c')
        self.p.expect_exact('#2]')
        self.sh('echo id-$DVTM_WINDOW_ID', 'id-2')
        self.p.send(MOD + 'xx')
        time.sleep(0.5)
        self.sh('echo id-$DVTM_WINDOW_ID', 'id-1')

    def test_truecolor(self):
        self.sh('echo $COLORTERM-$((6*7))', 'truecolor-42')
        # 24-bit red is shown as the closest color the outer terminal has
        self.p.send("printf '\\033[38;2;255;0;0mred-%d\\n' $((6*7))\r")
        self.p.expect_exact('\x1b[31mred-42')

    def test_cmd_fifo(self):
        with open(self.cmdfifo, 'w') as f:
            f.write("create 'echo from-$((6*7)); sleep 60' title-x\n")
        self.p.expect_exact('title-x')
        self.p.expect_exact('from-42')

    def test_status_fifo(self):
        with open(self.status, 'w') as f:
            f.write('hello-status\n')
        self.p.expect_exact('hello-status')

    def test_copy_and_paste(self):
        self.sh('echo some-output', 'some-output')
        self.p.send(MOD + 'e')
        time.sleep(3)
        self.p.send(MOD + 'p')
        self.p.expect_exact('pasted-42')

    def test_layouts_and_resize(self):
        for _ in range(3):
            self.p.send(MOD + 'c')
        self.p.expect_exact('#4]')
        for key in 'gbmf .':
            self.p.send(MOD + key)
        for rows, cols in ((10, 30), (3, 5), (50, 200), (24, 80)):
            self.p.setwinsize(rows, cols)
            time.sleep(0.2)
        self.sh('seq 1000 | tail -1', '1000')


if __name__ == '__main__':
    unittest.main(verbosity=2)
