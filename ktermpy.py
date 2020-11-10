import sys
import select
import threading
import os
import subprocess
import copy
import termios
import tty
import re

import pty
import time

TERM = 'kstermpy'
ENCODING = 'utf-8'
POLL_FLAGS_READ = select.POLLIN | select.POLLPRI | select.POLLERR

STATE_NORMAL = 'NORMAL'
STATE_ESC = 'ESC'
STATE_BRACKET = 'BRACKET'

BELL = '\u0007'
ANSI_ESC = '\u001b'

TAB_WIDTH = 8

def eprint(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)
    sys.stderr.flush()


class PollError(Exception):
    pass


class TermClosed(Exception):
    pass


def clamp_index(n, maximum):
    return max(0, (min(n, maximum - 1)))


def utf8read(f):
    buf = f.read(1)
    first = int(buf[0])
    flag = 0x80
    if first & flag:
        remaining = 0
        flag = flag >> 1
        while first & flag:
            flag = flag >> 1
            remaining += 1
        #eprint(f'UTF-8: size {remaining + 1}')
        buf += f.read(remaining)
    c = buf.decode(ENCODING)
    return c


class Term:
    def __init__(self, width=80, height=24):
        self.termf = None
        self.readpipe = None
        self.writepipe = None
        self.thread = None

        self.width = width
        self.height = height

        self.escbuf = ''

        self.clear()

        pass


    def open(self):
        self.done = False

        self.currow = 0
        self.curcol = 0
        self.mode = STATE_NORMAL

        pid, fd = os.forkpty()
        if pid == 0:
            os.execle('/bin/login', '/bin/login', { 'TERM': TERM })
            os._exit()

        self.termf = os.fdopen(fd, 'r+b', 0)

        rfd, wfd = os.pipe()
        self.readpipe = os.fdopen(rfd, 'rb', 0)
        self.writepipe = os.fdopen(wfd, 'wb', 0)

        self.thread = threading.Thread(target=self.operate)
        self.thread.start()


    def send_input(self, buf):
        try:
            self.writepipe.write(buf)
        except Exception:
            raise TermClosed()


    def get_state(self):
        if self.done:
            raise TermClosed()
        info = {
            'currow': clamp_index(self.currow, self.height),
            'curcol': clamp_index(self.curcol, self.width),
            'mode': self.mode,
        }
        return copy.deepcopy(self.rows), info


    def close(self):
        self.done = True
        if self.writepipe:
            self.writepipe.close()
        if self.thread:
            self.thread.join()


    def operate(self):
        termfd = self.termf.fileno()
        readpipefd = self.readpipe.fileno()
        poller = select.poll()
        poller.register(termfd, POLL_FLAGS_READ)
        poller.register(readpipefd, POLL_FLAGS_READ)
        try:
            while not self.done:
                polled = poller.poll(1000)
                for fd, event in polled:
                    if event == select.POLLERR:
                        raise PollError('POLLERR event')
                    if fd == termfd:
                        c = utf8read(self.termf)
                        self.handle(c)
                    elif fd == readpipefd:
                        b = self.readpipe.read(1)
                        self.termf.write(b)
        finally:
            self.done = True
            self.readpipe.close()


    def set_currow(self, n):
        self.currow = clamp_index(n, self.height)


    def move_currow(self, n):
        self.set_currow(self.currow + n)


    def set_curcol(self, n):
        self.curcol = clamp_index(n, self.width)


    def move_curcol(self, n):
        self.set_curcol(self.curcol + n)


    def newline(self):
        if self.currow < self.height - 1:
            self.move_currow(1)
        else:
            self.shift_rows()

    def tab(self):
        self.write_cell(' ')
        self.curcol += 1
        while self.curcol % TAB_WIDTH != 0:
            self.write_cell(' ')
            self.curcol += 1


    def wrap(self):
        self.newline()
        self.curcol = 0


    def write_cell(self, cell):
        if self.curcol >= self.width:
            self.wrap()
        self.rows[self.currow][self.curcol] = cell
        self.curcol += 1


    def clear(self):
        self.rows = [[' ' for col in range(self.width)] for row in range(self.height)]
        self.currow = 0
        self.curcol = 0


    def shift_rows(self):
        self.rows.pop(0)
        self.rows.append([' ' for col in range(self.width)])


    def handle(self, c):
        if self.mode == STATE_NORMAL:
            self.handle_normal(c)
        elif self.mode == STATE_ESC:
            self.handle_esc(c)
        elif self.mode == STATE_BRACKET:
            self.handle_bracket(c)


    def handle_normal(self, c):
        if c == ANSI_ESC:
            self.mode = STATE_ESC
        elif c == BELL:
            pass
        elif c == '\n':
            self.newline()
        elif c == '\t':
            self.tab()
        elif c == '\r':
            self.curcol = 0
        elif c == '\b':
            self.move_curcol(-1)
        else:
            self.write_cell(c)


    def handle_esc(self, c):
        if c == '[':
            self.mode = STATE_BRACKET
        else:
            self.write_cell(c)
            self.mode = STATE_NORMAL


    def handle_bracket(self, c):
        if c not in '01234567890;=':
            self.do_escbuf(c)
            self.mode = STATE_NORMAL
        else:
            self.escbuf += c


    def do_escbuf(self, cmd):
        eprint('ESC[', self.escbuf, cmd, end='\t')
        args = self.escbuf.split(';')
        if cmd == 'A':
            n = (min(1, int(args[0])))
            self.move_currow(-n)
        elif cmd == 'B':
            n = (min(1, int(args[0])))
            self.move_currow(n)
        elif cmd == 'C':
            n = (min(1, int(args[0])))
            self.move_curcol(n)
        elif cmd == 'D':
            n = (min(1, int(args[0])))
            self.move_curcol(-n)
        elif cmd == 'H' or cmd == 'f':
            try:
                row, col = args
                self.set_currow(int(row) - 1)
                self.set_curcol(int(col) - 1)
            except Exception:
                self.currow = 0
                self.curcol = 0
        elif cmd == 'K':
            for col in range(self.curcol, self.width):
                if self.height > self.currow:
                    self.rows[self.currow][col] = ' '
        elif cmd == 'J':
            self.clear()


        self.escbuf = ''
