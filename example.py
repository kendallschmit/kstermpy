import sys
import tty
import os
import select
import termios
import time

import kstermpy

ENCODING = 'utf-8'

def eprint(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)
    sys.stderr.flush()


def input_loop(ksterm):
    stdinattr = None
    try:
        stdinfd = sys.stdin.fileno()
        stdinattr = termios.tcgetattr(stdinfd)
        tty.setraw(stdinfd)
        tty.setcbreak(stdinfd)

        stdinf = os.fdopen(stdinfd, 'rb', 0)

        poller = select.poll()
        poller.register(stdinfd, select.POLLIN | select.POLLPRI | select.POLLERR)
        while True:
            polled = poller.poll()
            for fd, event in polled:
                if event == select.POLLERR:
                    raise Exception('POLLERR in InputLoop')
                if fd == stdinfd:
                    b = stdinf.read(1)
                    ksterm.send_input(b)
    finally:
        if stdinattr:
            termios.tcsetattr(stdinfd, termios.TCSAFLUSH, stdinattr)


def main():
    def printline(line=''):
        sys.stdout.buffer.write(line.encode(ENCODING) + b'\r\n')


    def ksterm_ready():
        global updates
        printline()
        rows, state = ksterm.get_state()
        rows[state.currow][state.curcol] = '_'
        printline('TOP '.ljust(ksterm.width + 4, '-'))
        for i, r in enumerate(rows):
            line = ''.join(r)
            printline(f'{i + 1:2d} |{line}|')
        printline('BOT '.ljust(ksterm.width + 4, '-'))
        printline(str(state))
        sys.stdout.buffer.flush()

    ksterm = None
    try:
        ksterm = kstermpy.Term(ksterm_ready)
        ksterm.open()

        input_loop(ksterm)
    except kstermpy.TermClosed:
        pass
    finally:
        if ksterm:
            ksterm.close()


if __name__ == '__main__':
    main()
