#!/usr/bin/env python3
import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest

import pexpect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = '\x07'  # ^G


class DvtmTest(unittest.TestCase):
    # per test changes to the environment dvtm is started with
    ENV = {
        'test_auto_direct_color': {'TERM': 'xterm-256color',
                                   'COLORTERM': 'truecolor'},
        'test_auto_direct_color_disabled': {'TERM': 'xterm-256color',
                                            'COLORTERM': 'truecolor',
                                            'DVTM_TRUECOLOR': '0'},
    }

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
        # dvtm's own terminfo entries, including the direct color fallback
        subprocess.run(['tic', '-x', '-o', self.tmp,
                        os.path.join(ROOT, 'dvtm.info')], check=True)
        env = dict(os.environ, SHELL='/bin/sh', PS1='$ ', ENV='', TERM='xterm',
                   COLORTERM='', DVTM_TRUECOLOR='', DVTM_EDITOR=self.editor,
                   TERMINFO=self.tmp,
                   PATH=ROOT + os.pathsep + os.environ['PATH'])
        env.update(self.ENV.get(self._testMethodName, {}))
        cmd = (f'exec {ROOT}/dvtm -c {self.cmdfifo} -s {self.status} '
               f'2>{self.stderr}')
        self.p = pexpect.spawn('/bin/sh', ['-c', cmd], env=env,
                               dimensions=(24, 80), encoding='utf-8',
                               timeout=10)
        if self._testMethodName == 'test_color_query':
            # play the outer terminal answering dvtm's startup queries
            self.p.expect_exact('\x1b[c')
            self.p.send('\x1b]10;rgb:dddd/eeee/ffff\x1b\\'
                        '\x1b]11;rgb:1111/2222/3333\x07\x1b[?62;22c')
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

    def test_auto_direct_color(self):
        # $COLORTERM makes dvtm use a direct color variant of xterm-256color
        self.p.send("printf '\\033[38;2;255;0;1mred-%d\\n' $((6*7))\r")
        self.p.expect(r'\x1b\[38[;:]2[;:]+255[;:]0[;:]1mred-42')

    def test_auto_direct_color_disabled(self):
        self.p.send("printf '\\033[38;2;255;0;1mred-%d\\n' $((6*7))\r")
        self.p.expect_exact('\x1b[38;5;196mred-42')

    def test_color_query(self):
        # programs inside dvtm get the outer terminal's colors
        self.sh("stty raw -echo; printf '\\033]11;?\\007'; "
                "dd bs=1 count=25 2>/dev/null | tr -d '\\033'; stty sane; echo",
                ']11;rgb:1111/2222/3333\\')
        self.sh("stty raw -echo; printf '\\033]10;?\\007'; "
                "dd bs=1 count=25 2>/dev/null | tr -d '\\033'; stty sane; echo",
                ']10;rgb:dddd/eeee/ffff\\')

    def test_device_attributes(self):
        # answered so nested programs, like dvtm itself, need not wait
        self.sh("stty raw -echo; printf '\\033[c'; "
                "dd bs=1 count=7 2>/dev/null | tr -d '\\033'; stty sane; echo",
                '[?1;2c')

    def test_cmd_fifo(self):
        with open(self.cmdfifo, 'w') as f:
            f.write("create 'echo from-$((6*7)); sleep 60' title-x\n")
        self.p.expect_exact('title-x')
        self.p.expect_exact('from-42')

    def test_cmd_fifo_split_writes(self):
        fd = os.open(self.cmdfifo, os.O_WRONLY)
        os.write(fd, b"create 'echo split-$((6*7)); sleep 60' ti")
        time.sleep(0.5)
        os.write(fd, b"tle-y\n")
        os.close(fd)
        self.p.expect_exact('title-y')
        self.p.expect_exact('split-42')

    def test_cmd_fifo_long_input(self):
        with open(self.cmdfifo, 'w') as f:
            f.write("create 'echo ok-$((6*7)); sleep 60' " + 'x' * 600 + '\n')
        self.p.expect_exact('ok-42')

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
