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

def main():
    stdinfd = sys.stdin.fileno()
    stdoutfd = sys.stdout.fileno()

    try:
        serverf = None
        stdinattr = None
        stdoutattr = None

        serverf = open(sys.argv[1], 'r+b', 0)
        serverfd = serverf.fileno()

        stdinattr = termios.tcgetattr(stdinfd)
        tty.setraw(stdinfd)
        tty.setcbreak(stdinfd)

        tty.setraw(stdoutfd)
        tty.setcbreak(stdoutfd)

        stdinf = os.fdopen(stdinfd, 'rb', 0)
        stdoutf = os.fdopen(stdoutfd, 'wb', 0)

        poller = select.poll()
        poller.register(serverfd, select.POLLIN | select.POLLPRI | select.POLLERR)
        poller.register(stdinfd, select.POLLIN | select.POLLPRI | select.POLLERR)
        while True:
            polled = poller.poll(100)
            for fd, event in polled:
                if event == select.POLLERR:
                    raise PollError('POLLERR event')
                    return
                if fd == serverfd:
                    b = serverf.read(1)
                    stdoutf.write(b)
                elif fd == stdinfd:
                    b = stdinf.read(1)
                    serverf.write(b)
    finally:
        if serverf:
            serverf.close()
        if stdinattr:
            termios.tcsetattr(stdinfd, termios.TCSAFLUSH, stdinattr)
        if stdoutattr:
            termios.tcsetattr(stdoutfd, termios.TCSAFLUSH, stdoutattr)


if __name__ == '__main__':
    main()
