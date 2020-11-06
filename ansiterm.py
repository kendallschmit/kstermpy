import sys
import select
import threading
import os
import subprocess
import copy
import termios
import tty
import traceback

ENCODING = 'utf-8'
POLL_FLAGS_READ = select.POLLIN | select.POLLPRI | select.POLLERR

MODE_CHAR = 'CHAR'
MODE_ESC = 'ESC'
MODE_BRACKET = 'BRACKET'

BELL = b'\x07'
ANSI_ESC = b'\x1b'

TAB_WIDTH = 8

def eprint(*args, **kwargs):
    print(*args, **kwargs, end='\r\n', file=sys.stderr)


class PollError(Exception):
    pass


class TermClosed(Exception):
    pass


class AnsiTerm:
    def __init__(self, width=80, height=24):
        self.termf = None
        self.readpipe = None
        self.writepipe = None
        self.thread = None

        self.width = width
        self.height = height
        self.rows = [[' ' for col in range(self.width)] for row in range(self.height)]

        pass


    def open(self):
        self.done = False

        self.currow = 0
        self.curcol = 0
        self.mode = MODE_CHAR

        pid, fd = os.forkpty()
        if pid == 0:
            os.execl('/bin/login', '/bin/login')

        self.termf = os.fdopen(fd, 'r+b', 0)

        rfd, wfd = os.pipe()
        self.readpipe = os.fdopen(rfd, 'rb', 0)
        self.writepipe = os.fdopen(wfd, 'wb', 0)

        self.thread = threading.Thread(target=self.operate)
        self.thread.start()


    def send_input(self, buf):
        try:
            self.writepipe.write(buf)
            eprint('in: ', buf)
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
                        b = self.termf.read(1)
                        self.handle_byte(b)
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
        self.rows[self.currow][self.curcol] = cell.decode(ENCODING)


    def shift_rows(self):
        self.rows.pop(0)
        self.rows.append([' ' for col in range(self.width)])


    def handle_byte(self, b):
        if self.mode == MODE_CHAR:
            self.handle_char(b)
        elif self.mode == MODE_ESC:
            self.handle_esc(b)
        elif self.mode == MODE_BRACKET:
            self.handle_bracket(b)


    def handle_char(self, b):
        eprint('out:', b)
        if b == BELL:
            pass
        elif b == ANSI_ESC:
            self.mode = MODE_ESC
        elif b == b'\n':
            if self.currow < self.height - 1:
                self.currow += 1
            else:
                self.shift_rows()
        elif b == b'\t':
            self.write_cell(b' ')
            self.curcol += 1
            while col % TAB_WIDTH != 0:
                self.write_cell(b' ')
                self.curcol += 1
        elif b == b'\r':
            self.curcol = 0
        elif b == b'\b':
            self.write_cell(b' ')
            self.curcol -= 1
            self.curcol = max(0, self.curcol)
        else:
            self.write_cell(b)
            self.curcol += 1


    def handle_esc(self, b):
        if b == b'[':
            self.mode = MODE_BRACKET
        else:
            self.write_cell(b)
            self.mode = MODE_CHAR


    def handle_bracket(self, b):
        if (b < b'0' or b > b'9') and b != b';' and b != b'=':
            self.mode = MODE_CHAR


def main():
    stdinfd = sys.stdin.fileno()

    try:
        stdinattr = None
        ansiterm = None
        outf = None

        stdinattr = termios.tcgetattr(stdinfd)
        tty.setraw(stdinfd)
        tty.setcbreak(stdinfd)

        stdinfd = sys.stdin.fileno()
        stdinf = os.fdopen(stdinfd, 'rb', 0)

        ansiterm = AnsiTerm()
        ansiterm.open()

        outf = open('/tmp/aoeu', 'w')
        def outprint(line):
            outf.write(line + '\r\n')
            outf.flush()

        poller = select.poll()
        poller.register(stdinf, select.POLLIN | select.POLLPRI | select.POLLERR)
        while True:
            polled = poller.poll(100)
            for fd, event in polled:
                if event == select.POLLERR:
                    raise PollError('POLLERR event')
                    return
                if fd == stdinfd:
                    b = stdinf.read(1)
                    ansiterm.send_input(b)

            outprint('\n\n\n')
            rows, info = ansiterm.get_state()
            outprint('TOP '.ljust(ansiterm.width + 4, '-'))
            for i, r in enumerate(rows):
                line = ''.join(r)
                outprint(f'{i:2d} |{line}|')
            outprint('BOT '.ljust(ansiterm.width + 4, '-'))
            outprint(str(info) + '\n')
    except TermClosed:
        raise
    finally:
        if stdinattr:
            termios.tcsetattr(stdinfd, termios.TCSAFLUSH, stdinattr)
        if ansiterm:
            ansiterm.close()


if __name__ == '__main__':
    main()
