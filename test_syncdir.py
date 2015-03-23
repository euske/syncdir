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
    args = argv[1:]
    src = args.pop(0)
    dst = args.pop(0)
    rargs = ['python2','syncdir.py','-B','_backup']
    (p1r,p1w) = getpipe()
    (p2r,p2w) = getpipe()
    proc1 = subprocess.Popen(rargs+[src], stdin=p1r, stdout=p2w)
    proc2 = subprocess.Popen(rargs+[dst], stdin=p2r, stdout=p1w)
    proc1.wait()
    proc2.wait()
    return 0

if __name__ == '__main__': sys.exit(main(sys.argv))
