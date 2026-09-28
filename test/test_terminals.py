#!/usr/bin/env python3
"""Run dvtm inside real terminal emulators and check the colors they show.

X11 terminals run on a virtual Xvfb display and are checked by looking for
exact pixel values in a screenshot, tmux by reading back its pane content.
Terminals which are not installed are skipped.
"""
import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DVTM = os.path.join(ROOT, 'dvtm')

TRUECOLOR = (255, 0, 1)   # a 24-bit color no palette contains
NEAREST = (255, 0, 0)     # its closest 256 color palette entry (196)
THEME = (0x12, 0x34, 0x56)  # bright red (color 9) of the terminal's theme

# paint bars with a 24-bit background color and the theme's bright red
BARS = ("printf '\\033[48;2;255;0;1m%40s\\033[0m\\n\\033[101m%40s\\033[0m\\n'; "
        "sleep 60")

# how to start each terminal: its command line prefix running a program
TERMINALS = {
    # xterm removes $COLORTERM, direct color has to be selected through $TERM
    'xterm': ['xterm', '-tn', 'xterm-256color', '-xrm', '*color9: #123456', '-e'],
    'xterm-direct': ['xterm', '-tn', 'xterm-direct256', '-xrm', '*color9: #123456', '-e'],
    'kitty': ['kitty', '--config', 'NONE', '-o', 'shell_integration=disabled',
              '-o', 'color9=#123456'],
    'alacritty': ['alacritty', '-o', 'colors.bright.red="#123456"', '-e'],
}


def screenshot(display):
    """Return the set of (r, g, b) colors on the screen."""
    xwd = subprocess.run(['xwd', '-root', '-silent', '-display', display],
                         capture_output=True, check=True).stdout
    header = struct.unpack('>25I', xwd[:100])
    size, lsb_first, bpp, stride = header[0], header[7] == 0, header[11], header[12]
    width, height, ncolors = header[4], header[5], header[19]
    assert bpp in (24, 32), bpp
    data = xwd[size + ncolors * 12:]
    # keep the three color bytes of each pixel, as r, g, b
    step = bpp // 8
    rows = [data[y * stride:y * stride + width * step] for y in range(height)]
    pixels = b''.join(rows)
    if lsb_first:
        b, g, r = pixels[0::step], pixels[1::step], pixels[2::step]
    else:
        r, g, b = pixels[step - 3::step], pixels[step - 2::step], pixels[step - 1::step]
    return set(zip(r, g, b))


class TerminalTest(unittest.TestCase):
    display = None

    @classmethod
    def setUpClass(cls):
        if not shutil.which('Xvfb') or not shutil.which('xwd'):
            return
        cls.display = ':%d' % (90 + os.getpid() % 100)
        cls.xvfb = subprocess.Popen(['Xvfb', cls.display, '-screen', '0',
                                     '1024x768x24', '-nolisten', 'tcp'],
                                    stderr=subprocess.DEVNULL)
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        if cls.display:
            cls.xvfb.terminate()
            cls.xvfb.wait()

    def run_terminal(self, name, env=None):
        """Start dvtm in the terminal, return the colors it shows."""
        if not self.display:
            self.skipTest('Xvfb or xwd missing')
        if not shutil.which(TERMINALS[name][0]):
            self.skipTest(name + ' missing')
        tmp = tempfile.mkdtemp()
        full_env = dict(os.environ, DISPLAY=self.display, SHELL='/bin/sh',
                        LIBGL_ALWAYS_SOFTWARE='1', XDG_RUNTIME_DIR=tmp,
                        COLORTERM='truecolor', **(env or {}))
        full_env.pop('TERM', None)
        term = subprocess.Popen(TERMINALS[name] + [DVTM, BARS], env=full_env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            # wait until the bars are drawn
            for _ in range(60):
                time.sleep(0.5)
                self.assertIsNone(term.poll(), name + ' exited')
                colors = screenshot(self.display)
                if TRUECOLOR in colors or NEAREST in colors:
                    time.sleep(0.5)
                    return screenshot(self.display)
            self.fail(name + ' showed neither color')
        finally:
            term.terminate()
            term.wait()
            shutil.rmtree(tmp)

    def check_truecolor(self, name):
        colors = self.run_terminal(name)
        self.assertIn(TRUECOLOR, colors)

    def check_theme(self, name):
        self.assertIn(THEME, self.run_terminal(name))

    def check_disabled(self, name):
        colors = self.run_terminal(name, {'DVTM_TRUECOLOR': '0'})
        self.assertIn(NEAREST, colors)
        self.assertNotIn(TRUECOLOR, colors)
        self.assertIn(THEME, colors)

    def test_xterm_nearest(self):
        colors = self.run_terminal('xterm')
        self.assertIn(NEAREST, colors)
        self.assertIn(THEME, colors)

    def test_xterm_direct_truecolor(self):
        self.check_truecolor('xterm-direct')

    def test_xterm_direct_theme(self):
        self.check_theme('xterm-direct')

    def test_kitty_truecolor(self):
        self.check_truecolor('kitty')

    def test_kitty_theme(self):
        self.check_theme('kitty')

    def test_kitty_disabled(self):
        self.check_disabled('kitty')

    def test_alacritty_truecolor(self):
        self.check_truecolor('alacritty')

    def test_alacritty_theme(self):
        self.check_theme('alacritty')

    def test_alacritty_disabled(self):
        self.check_disabled('alacritty')


class TmuxTest(unittest.TestCase):
    """tmux as the outer terminal, its pane content is read back directly."""

    def setUp(self):
        if not shutil.which('tmux'):
            self.skipTest('tmux missing')
        self.tmux = ['tmux', '-L', 'dvtm-test-%d' % os.getpid(), '-f', '/dev/null']

    def tearDown(self):
        subprocess.run(self.tmux + ['kill-server'], stderr=subprocess.DEVNULL)

    def pane(self, env):
        env_args = [arg for k, v in env.items() for arg in ('-e', k + '=' + v)]
        subprocess.run(self.tmux + ['new-session', '-d', '-x', '80', '-y', '24']
                       + env_args + [DVTM, BARS], check=True,
                       env=dict(os.environ, SHELL='/bin/sh'))
        for _ in range(40):
            time.sleep(0.25)
            content = subprocess.run(self.tmux + ['capture-pane', '-p', '-e'],
                                     capture_output=True, text=True).stdout
            if re.search(r'\x1b\[[0-9;:]*48[;:]', content):
                return content
        self.fail('no colors shown: ' + repr(content))

    def test_truecolor(self):
        content = self.pane({'COLORTERM': 'truecolor'})
        self.assertIn('48;2;255;0;1', content)

    def test_disabled(self):
        content = self.pane({'COLORTERM': 'truecolor', 'DVTM_TRUECOLOR': '0'})
        self.assertIn('48;5;196', content)
        self.assertNotIn('48;2;255;0;1', content)


if __name__ == '__main__':
    unittest.main(verbosity=2)
