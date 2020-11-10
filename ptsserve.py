import sys
import tty
import os
import select

import ktermpy

ENCODING = 'utf-8'

def eprint(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)
    sys.stderr.flush()


def main():
    stdinfd = sys.stdin.fileno()

    try:
        kterm = None
        masterf = None

        kterm = ktermpy.Term()
        kterm.open()

        masterfd, slavefd = os.openpty()
        tty.setraw(masterfd)
        tty.setcbreak(masterfd)
        masterf = os.fdopen(masterfd, 'w+b', 0)

        def printline(line=''):
            masterf.write(line.encode(ENCODING) + b'\r\n')

        slavepath = os.ttyname(slavefd)
        eprint('slave pty:', slavepath)

        poller = select.poll()
        poller.register(masterfd, select.POLLIN | select.POLLPRI | select.POLLERR)
        while True:
            polled = poller.poll(100)
            for fd, event in polled:
                if event == select.POLLERR:
                    raise PollError('POLLERR event')
                    return
                if fd == masterfd:
                    b = masterf.read(1)
                    kterm.send_input(b)

            printline()
            rows, state = kterm.get_state()
            rows[state.currow][state.curcol] = '_'
            printline('TOP '.ljust(kterm.width + 4, '-'))
            for i, r in enumerate(rows):
                line = ''.join(r)
                printline(f'{i + 1:2d} |{line}|')
            printline('BOT '.ljust(kterm.width + 4, '-'))
            printline(str(state))
    except ktermpy.TermClosed:
        pass
    finally:
        if masterf:
            masterf.close()
        if kterm:
            kterm.close()


if __name__ == '__main__':
    main()
