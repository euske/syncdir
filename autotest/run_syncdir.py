#!/usr/bin/env python
import sys
import os
import subprocess

def getpipe():
    (r,w) = os.pipe()
    fpr = os.fdopen(r, 'rb')
    fpw = os.fdopen(w, 'wb')
    return (fpr,fpw)

def main(argv):
    import getopt
    def usage():
        print ('usage: %s [-c cmdline] [-d] [-n] [-i] [-I exts] [-B backupdir] [-T trashdir] '
               'src dst' % argv[0])
        return 100
    try:
        (opts, args) = getopt.getopt(argv[1:], 'c:dniI:B:T:')
    except getopt.GetoptError:
        return usage()
    ropts = []
    cmdline = 'syncdir.py'
    for (k, v) in opts:
        if k == '-c':
            cmdline = v
        elif k == '-d':
            ropts.append(k)
        elif k == '-n':
            ropts.append(k)
        elif k == '-i':
            ropts.append(k)
        elif k == '-I':
            ropts.append(k)
            ropts.append(v)
        elif k == '-B':
            ropts.append(k)
            ropts.append(v)
        elif k == '-T':
            ropts.append(k)
            ropts.append(v)
    #
    if len(args) != 2: return usage()
    src = args.pop(0)
    dst = args.pop(0)
    (p1r,p1w) = getpipe()
    (p2r,p2w) = getpipe()
    rargs = [sys.executable,cmdline]+ropts
    sys.stderr.write('running: %r\n' % rargs)
    proc1 = subprocess.Popen(rargs+[src], stdin=p1r, stdout=p2w)
    proc2 = subprocess.Popen(rargs+[dst], stdin=p2r, stdout=p1w)
    proc1.wait()
    proc2.wait()
    return 0

if __name__ == '__main__': sys.exit(main(sys.argv))
