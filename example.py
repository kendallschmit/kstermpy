import sys
import tty
import os
import select
import termios
import time

import kstermpy


def eprint(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)
    sys.stderr.flush()


def input_loop(ksterm):
    stdinattr = None
    try:
        stdinfd = sys.stdin.fileno()
        stdinattr = termios.tcgetattr(stdinfd)

        tty.setcbreak(stdinfd)
        tty.setraw(stdinfd)
        attr = termios.tcgetattr(stdinfd)
        attr[1] |= termios.OPOST
        termios.tcsetattr(stdinfd, termios.TCSANOW, attr)

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
    silent = '--silent' in sys.argv

    def ksterm_ready():
        print()
        rows, state = ksterm.get_state()
        rows[state.currow][state.curcol] = '_'
        print('TOP '.ljust(ksterm.width + 4, '-'))
        for i, r in enumerate(rows):
            line = ''.join(r)
            print(f'{i + 1:2d} |{line}|')
        print('BOT '.ljust(ksterm.width + 4, '-'))
        print(str(state))
        sys.stdout.buffer.flush()

    ksterm = None
    try:
        ksterm = kstermpy.Term(ksterm_ready, silent=silent)
        ksterm.open()

        input_loop(ksterm)
    except kstermpy.TermClosed:
        pass
    finally:
        if ksterm:
            ksterm.close()


if __name__ == '__main__':
    main()
