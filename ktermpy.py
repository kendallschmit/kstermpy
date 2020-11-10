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

TERM = 'ktermpy'
ENCODING = 'utf-8'
POLL_FLAGS_READ = select.POLLIN | select.POLLPRI | select.POLLERR

MODE_CHAR = 'CHAR'
MODE_ESC = 'ESC'
MODE_BRACKET = 'BRACKET'

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


class Term:
    def __init__(self, width=80, height=24):
        self.termf = None
        self.readpipe = None
        self.writepipe = None
        self.thread = None

        self.width = width
        self.height = height
        self.rows = [[' ' for col in range(self.width)] for row in range(self.height)]

        self.charbuf = b''
        self.escbuf = ''

        pass


    def open(self):
        self.done = False

        self.currow = 0
        self.curcol = 0
        self.mode = MODE_CHAR

        pid, fd = os.forkpty()
        if pid == 0:
            os.execle('/bin/login', '/bin/login', { 'TERM': TERM })
            os._exit()
        eprint('child pid:', pid)

        self.termf = os.fdopen(fd, 'r+b', 0)

        rfd, wfd = os.pipe()
        self.readpipe = os.fdopen(rfd, 'rb', 0)
        self.writepipe = os.fdopen(wfd, 'wb', 0)

        self.thread = threading.Thread(target=self.operate)
        self.thread.start()


    def send_input(self, buf):
        try:
            self.writepipe.write(buf)
            eprint('in: ', buf, sep='')
        except Exception:
            raise TermClosed()


    def get_state(self):
        if self.done:
            raise TermClosed()
        info = {
            'currow': self.currow,
            'curcol': self.curcol,
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
                        self.charbuf += self.termf.read(1)
                        c = None
                        try:
                            c = self.charbuf.decode(ENCODING)
                        except Exception:
                            pass
                        if c:
                            self.handle_input(c)
                            self.charbuf = b''
                        elif len(self.charbuf) > 6:
                            self.charbuf = b''
                    elif fd == readpipefd:
                        b = self.readpipe.read(1)
                        self.termf.write(b)
        finally:
            self.done = True
            self.readpipe.close()


    def write_cell(self, cell):
        if self.currow < 0 or self.currow >= self.height:
            return
        if self.curcol < 0 or self.curcol >= self.width:
            return
        self.rows[self.currow][self.curcol] = cell


    def shift_rows(self):
        self.rows.pop(0)
        self.rows.append([' ' for col in range(self.width)])


    def handle_input(self, c):
        if self.mode == MODE_CHAR:
            self.handle_char(c)
        elif self.mode == MODE_ESC:
            self.handle_esc(c)
        elif self.mode == MODE_BRACKET:
            self.handle_bracket(c)


    def handle_char(self, c):
        eprint('out:', c.encode(ENCODING), sep='')
        if c == BELL:
            pass
        elif c == ANSI_ESC:
            self.mode = MODE_ESC
        elif c == '\n':
            if self.currow < self.height - 1:
                self.currow += 1
            else:
                self.shift_rows()
        elif c == '\t':
            self.write_cell(' ')
            self.curcol += 1
            while self.curcol % TAB_WIDTH != 0:
                self.write_cell(' ')
                self.curcol += 1
        elif c == '\r':
            self.curcol = 0
        elif c == '\b':
            self.curcol -= 1
            self.curcol = max(0, self.curcol)
        else:
            self.write_cell(c)
            self.curcol += 1


    def handle_esc(self, c):
        if c == '[':
            self.mode = MODE_BRACKET
        else:
            self.write_cell(c)
            self.mode = MODE_CHAR


    def handle_bracket(self, c):
        if c not in '[01234567890;=':
            self.do_escbuf(c)
            self.mode = MODE_CHAR
        else:
            self.escbuf += c


    def do_escbuf(self, cmd):
        eprint('escbuf:', self.escbuf)
        if cmd == 'H':
            try:
                row, col = self.escbuf.split(';')
                self.currow = int(row) - 1
                self.curcol = int(col) - 1
            except Exception as e:
                eprint('Escape error:', e)
        self.escbuf = ''
