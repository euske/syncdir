#!/usr/bin/env python
import sys
import os
import os.path
import re
import stat
import time
import fnmatch
import hashlib
import logging
import struct
import marshal
import binascii

# "loc" is an OS-independent pathname.
SEP = '/'
def path2loc(path):
    return SEP.join(path.split(os.path.sep))
def loc2path(loc):
    return os.path.sep.join(loc.split(SEP))

def readExcls(dirpath, fp):
    pol = 0
    names = []
    for line in fp:
        line = line.strip()
        if line.startswith('+'):
            if pol < 0:
                raise ValueError('conflicting: %r' % line)
            pol = +1
            names.append(line[1:])
        elif line.startswith('-'):
            if 0 < pol:
                raise ValueError('conflicting: %r' % line)
            pol = -1
            names.append(line[1:])
        else:
            raise ValueError('invalid: %r' % line)
    if pol <= 0:
        return names
    else:
        names0 = set(os.listdir(dirpath))
        return list(names0.difference(names))


##  ExcludeDB
##
class ExcludeDB:

    def __init__(self):
        self.globalpat = []
        self.localpat = {}
        return

    def add_global(self, pat):
        regex = fnmatch.translate(pat)
        self.globalpat.append((pat, re.compile(regex)))
        return

    def clear_locals(self):
        self.localpat.clear()
        return

    def add_local(self, k, pats):
        if k in self.localpat:
            pats0 = self.localpat[k]
        else:
            pats0 = self.localpat[k] = {}
        for pat in pats:
            if pat in pats0: continue
            regex = fnmatch.translate(pat)
            pats0[pat] = re.compile(regex)
        return

    def is_excluded(self, k, name):
        for (_,regex) in self.globalpat:
            if regex.match(name): return True
        if k in self.localpat:
            for regex in self.localpat[k].values():
                if regex.match(name): return True
        return False


##  SyncDir
##
class SyncDir:

    class ProtocolError(Exception): pass

    # bufsize_local: for scanning local files.
    bufsize_local = 65536
    # bufsize_wire: for sending/receiving data over network.
    bufsize_wire = 4096

    def __init__(self, logger, fp_send, fp_recv,
                 dryrun=False, configfile=None, excldb=None,
                 ignorecase=False, followlink=False, timeskew=0,
                 backupdir=None, trashdir=None, codec='utf-8'):
        self.logger = logger
        self.dryrun = dryrun
        self.configfile = configfile
        self.excldb = excldb
        self.ignorecase = ignorecase
        self.followlink = followlink
        self.timeskew = timeskew
        self.backupdir = backupdir
        self.trashdir = trashdir
        self.codec = codec
        self._fp_send = fp_send
        self._fp_recv = fp_recv
        return

    def is_dir_valid(self, k, name):
        if name.startswith('.'): return False
        if name == self.backupdir or name == self.trashdir: return False
        if self.excldb is not None:
            if self.excldb.is_excluded(k, name): return False
        return True
    
    def is_file_valid(self, k, name):
        if name.startswith('.'): return False
        if name == self.configfile: return False
        if self.excldb is not None:
            if self.excldb.is_excluded(k, name): return False
        return True

    def _getkey(self, loc):
        if self.ignorecase:
            return loc.lower()
        else:
            return loc

    def _send(self, x):
        #self.logger.debug(' send: %r' % x)
        self._fp_send.write(x)
        self._fp_send.flush()
        return
    def _recv(self, n):
        x = self._fp_recv.read(n)
        #self.logger.debug(' recv: %r' % x)
        return x
    
    def _send_obj(self, obj):
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(' send_obj: %r' % (obj,))
        s = marshal.dumps(obj)
        self._send(b'+'+struct.pack('<i', len(s))+s)
        return
    def _recv_obj(self):
        x = self._recv(5)
        if not x.startswith(b'+'): raise self.ProtocolError
        (n,) = struct.unpack('<xi', x)
        s = self._recv(n)
        obj = marshal.loads(s)
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(' recv_obj: %r' % (obj,))
        return obj
    
    def _read_config(self, basedir):
        def walk(relpath0):
            path0 = os.path.join(basedir, relpath0)
            try:
                files = os.listdir(path0)
            except OSError as e:
                self.logger.error('walk: not found: %r: %r' % (path0, e))
                return
            for name in files:
                path1 = os.path.join(path0, name)
                relpath1 = os.path.join(relpath0, name)
                if not self.followlink and os.path.islink(path1):
                    # is a symlink (and ignored).
                    pass
                elif name.startswith('.'):
                    pass
                elif os.path.isdir(path1):
                    # is a directory.
                    if name == self.backupdir or name == self.trashdir: 
                        pass
                    else:
                        for e in walk(relpath1):
                            yield e
                elif name == self.configfile:
                    # load a config file.
                    with open(path1) as fp:
                        try:
                            excls = readExcls(path0, fp)
                            yield (relpath0, excls)
                        except ValueError as e:
                            self.logger.error(' read_config: %r: %r' % (path1, e))
        return walk('.')

    def _send_config(self, confs):
        self._recv_phase = 0
        # Assuming each entry fits in one packet.
        for (relpath, excls) in confs:
            loc = path2loc(relpath)
            k = self._getkey(loc)
            self.excldb.add_local(k, excls)
            self.logger.debug(' send_config: %r: %r' % (loc, excls))
            self._send_obj((loc, excls))
            self._recv_config()
        self._send_obj(None)
        while self._recv_config():
            pass
        return

    def _recv_config(self):
        if self._recv_phase != 0: return False
        # Assuming each entry fits in one packet.
        obj = self._recv_obj()
        if obj is None:
            self._recv_phase = 1
            return False
        try:
            (loc, excls) = obj
        except ValueError:
            raise self.ProtocolError
        self.logger.debug(' recv_config: %r: %r' % (loc, excls))
        k = self._getkey(loc)
        self.excldb.add_local(k, excls)
        return True

    def _gen_list(self, basedir):
        def walk(relpath0, trashbase=None, trashrel0=None):
            # trashbase: the original dirname of a trashed file.
            if trashbase is None:
                path0 = os.path.join(basedir, relpath0)
            else:
                trashpath = os.path.join(self.trashdir, trashrel0)
                path0 = os.path.join(basedir, os.path.join(trashbase, trashpath))
            try:
                files = os.listdir(path0)
            except OSError as e:
                self.logger.error('walk: not found: %r: %r' % (path0, e))
                return
            k = self._getkey(path2loc(relpath0))
            for name in files:
                path1 = os.path.join(path0, name)
                relpath1 = os.path.join(relpath0, name)
                if trashrel0 is None:
                    trashrel1 = None
                else:
                    trashrel1 = os.path.join(trashrel0, name)
                if not self.followlink and os.path.islink(path1):
                    # is a symlink (and ignored).
                    pass
                elif os.path.isdir(path1):
                    # is a directory.
                    if name == self.trashdir and trashbase is None:
                        # List trashed files.
                        for e in walk(relpath0, trashbase=relpath0, trashrel0='.'):
                            yield e
                    elif self.is_dir_valid(k, name):
                        for e in walk(relpath1, trashbase=trashbase, trashrel0=trashrel1):
                            yield e
                elif (os.path.isfile(path1) and
                      self.is_file_valid(k, name)):
                    # is a regular file.
                    try:
                        st = os.stat(path1)
                        st_size = st[stat.ST_SIZE]
                        st_mtime = st[stat.ST_MTIME]
                        with open(path1, 'rb') as fp:
                            h = hashlib.md5()
                            while True:
                                data = fp.read(self.bufsize_local)
                                if not data: break
                                h.update(data)
                            if trashbase is not None:
                                # the file is in trash.
                                st_size = st_mtime = None
                            yield (relpath1, trashbase, trashrel1,
                                   st_size, st_mtime, h.digest())
                    except (IOError, OSError):
                        pass
        return walk('.')

    def _send_list(self, send_files):
        self._recv_phase = 0
        self._recv_files = {}
        # Assuming each entry fits in one packet.
        for (relpath, _, _, size, mtime, digest) in send_files.values():
            loc = path2loc(relpath)
            self.logger.debug(' send_list: %r' % relpath)
            self._send_obj((loc, size, mtime, digest))
            self._recv_list()
        self._send_obj(None)
        while self._recv_list():
            pass
        return

    def _recv_list(self):
        if self._recv_phase != 0: return False
        # Assuming each entry fits in one packet.
        obj = self._recv_obj()
        if obj is None:
            self._recv_phase = 1
            return False
        try:
            (loc, size, mtime, digest) = obj
        except ValueError:
            raise self.ProtocolError
        relpath = loc2path(loc)
        self.logger.debug(' recv_list: %r' % relpath)
        k = self._getkey(loc)
        self._recv_files[k] = (relpath, size, mtime, digest)
        return True

    def _send_file(self, basedir, fp, size, digest):
        h = hashlib.md5()
        while size:
            # Send one packet.
            bufsize = min(size, self.bufsize_wire)
            data = fp.read(bufsize)
            if not data: raise self.ProtocolError('file size is changed')
            h.update(data)
            size -= len(data)
            self._send(data)
            if 0 < size:
                # receive one packet.
                self._recv_file(basedir)
        if digest != h.digest():
            raise self.ProtocolError('sending file is changed')
        self._recv_file(basedir)
        return

    def _recv_file(self, basedir):
        # Process only one packet and return.
        if self._rfile_bytes is not None:
            # receive a portion of a file.
            bufsize = min(self._rfile_bytes, self.bufsize_wire)
            data = self._recv(bufsize)
            self._rfile_bytes -= bufsize
            assert 0 <= self._rfile_bytes
            assert self._rfile_hash is not None
            self._rfile_hash.update(data)
            if self._rfile_fp is not None:
                self._rfile_fp.write(data)
            if 0 < self._rfile_bytes: return True
            # finish receiving a file.
            self._rfile_bytes = None
            if self._rfile_fp is not None:
                assert self._rfile_info is not None
                (dstpath,digest) = self._rfile_info
                tmppath = self._rfile_fp.name
                if digest != self._rfile_hash.digest():
                    raise self.ProtocolError('received file is different')
                self._rfile_fp.close()
                self._rfile_fp = None
                if self.backupdir and os.path.isfile(dstpath):
                    self._backup_file(os.path.dirname(dstpath), dstpath, 'backup')
                try:
                    os.rename(tmppath, dstpath)
                except (IOError, OSError) as e:
                    self.logger.error('recv: rename %r: %r' % (dstpath, e))
            return True
        assert self._rfile_bytes is None
        assert self._rfile_fp is None
        
        if self._rfile_queue:
            # setup a new file to receive.
            k = self._recv_obj()
            (relpath0,size0,mtime0,digest0) = self._recv_files[k]
            assert k in self._rfile_queue
            path = os.path.join(basedir, relpath0)
            self._rfile_queue.remove(k)
            self._rfile_info = (path, digest0)
            self._rfile_bytes = size0
            self._rfile_hash = hashlib.md5()
            try:
                self.logger.info('recv: %r (%s)' % (path, size0))
                if not self.dryrun:
                    tmpname = 'tmp'+binascii.hexlify(digest0).decode('ascii')
                    tmppath = os.path.join(os.path.dirname(path), tmpname)
                    self._rfile_fp = open(tmppath, 'wb')
            except (IOError, OSError) as e:
                self.logger.error('recv: %r: %r' % (path, e))
            return True

        assert not self._rfile_queue
        return False

    def _backup_file(self, backupbase, path, prefix):
        assert self.backupdir
        backupdir = os.path.join(backupbase, self.backupdir)
        if not os.path.isdir(backupdir):
            try:
                os.mkdir(backupdir)
            except (IOError, OSError) as e:
                self.logger.error('recv: mkdir %r: %r' % (backupdir, e))
                return
        try:
            timestamp = time.strftime('%Y%m%d%H%M%S')
            name = os.path.basename(path)+'.'+prefix+'.'+timestamp
            dstpath = os.path.join(backupdir, name)
            os.rename(path, dstpath)
        except (IOError, OSError) as e:
            self.logger.error('recv: backup %r -> %r: %r' % (path, dstpath, e))
        return

    def run(self, basedir):
        self.logger.info('listing: %r...' % basedir)
        # read the config files.
        self.excldb.clear_locals()
        if self.configfile is not None:
            self._send_config(self._read_config(basedir))
        # send/recv the file list.
        send_files = {}
        for (relpath, trashbase, trashrel, size, mtime, digest) in self._gen_list(basedir):
            loc = path2loc(relpath)
            k = self._getkey(loc)
            send_files[k] = (relpath, trashbase, trashrel, size, mtime, digest)
        self._send_list(send_files)
        # compute the difference.
        send_new = []
        recv_new = []
        send_update = []
        recv_update = []
        trashed = []
        for (k,(relpath0,trashbase0,trashrel0,size0,mtime0,digest0)) in send_files.items():
            if k in self._recv_files:
                (relpath1,size1,mtime1,digest1) = self._recv_files[k]
                if mtime0 is None and mtime1 is None:
                    # both files are trashed.
                    pass
                elif mtime0 is None:
                    # the obsolete sender file will be trashed. do nothing.
                    pass
                elif mtime1 is None:
                    # the obsolete receiver file will be trashed.
                    trashed.append((os.path.dirname(relpath0), relpath0))
                elif digest0 == digest1:
                    # the two files are the same. do nothing.
                    pass
                else:
                    if mtime1+self.timeskew < mtime0:
                        # the sender file is newer.
                        send_update.append(k)
                    elif mtime0+self.timeskew < mtime1:
                        # the receiver file is newer.
                        recv_update.append(k)
                    else:
                        # unable to decide which file is newer. leave them alone.
                        pass
            else:
                if mtime0 is not None:
                    send_new.append(k)
            if mtime0 is None:
                # clean up the sending trashed file.
                assert self.trashdir
                relpath = os.path.join(trashbase0, os.path.join(self.trashdir, trashrel0))
                trashed.append((trashbase0, relpath))
        for (k,(_,_,mtime1,_)) in self._recv_files.items():
            if k not in send_files:
                if mtime1 is not None:
                    recv_new.append(k)
        self.logger.info('sending: %d new, %d update...' %
                         (len(send_new), len(send_update)))
        self.logger.info('receiving: %d new, %d update, %d trashed...' %
                         (len(recv_new), len(recv_update), len(trashed)))
        # deleting files.
        for (backupbase,relpath) in trashed:
            path = os.path.join(basedir, relpath)
            self.logger.info('removing: %r' % path)
            if not self.dryrun:
                if self.backupdir:
                    self._backup_file(os.path.join(basedir, backupbase), path, 'trash')
                else:
                    os.remove(path)
        # create receiving directories.
        self._rfile_queue = set(recv_new + recv_update)
        dirs = set()
        for k in self._rfile_queue:
            if k in dirs: continue
            dirs.add(k)
            (relpath,_,_,_) = self._recv_files[k]
            path = os.path.join(basedir, os.path.dirname(relpath))
            if os.path.isdir(path): continue
            self.logger.info('mkdir: %r' % path)
            if not self.dryrun:
                try:
                    os.makedirs(path)
                except OSError as e:
                    self.logger.error('mkdir: %r: %r' % (path, e))
        # send/recv the files.
        self._rfile_info = None
        self._rfile_bytes = None
        self._rfile_hash = None
        self._rfile_fp = None
        for k in (send_new + send_update):
            try:
                (relpath0,_,_,size0,mtime0,digest0) = send_files[k]
                assert size0 is not None
                assert mtime0 is not None
                path = os.path.join(basedir, relpath0)
                self.logger.info('send: %r (%s)' % (path, size0))
                with open(path, 'rb') as fp:
                    # send one packet.
                    self._send_obj(k)
                    # receive one packet.
                    self._recv_file(basedir)
                    self._send_file(basedir, fp, size0, digest0)
            except (IOError, OSError) as e:
                self.logger.error('send: %r: %r' % (path, e))
        while self._recv_file(basedir):
            pass
        return

# main
def main(argv):
    import getopt
    def usage():
        print ('usage: %s [-d] [-l logfile] [-p user@host:port] [-c cmdline] '
               '[-n] [-i] [-E dirs] [-L] [-B backupdir] [-T trashdir] '
               '[-C configfile] [-Q timeskew] [dir ...]' % argv[0])
        return 100
    try:
        (opts, args) = getopt.getopt(argv[1:], 'dl:p:c:niE:LB:T:C:Q:')
    except getopt.GetoptError:
        return usage()
    #
    loglevel = logging.INFO
    logfile = None
    host = None
    port = 22
    username = None
    cmdline = 'syncdir.py'
    ropts = []
    dryrun = False
    ignorecase = False
    followlink = False
    backupdir = '.backup'
    trashdir = '.trash'
    configfile = '.config'
    timeskew = 5
    excldb = ExcludeDB()
    for (k, v) in opts:
        if k == '-d': loglevel = logging.DEBUG
        elif k == '-l': logfile = v
        elif k == '-p':
            (username,_,v) = v.partition('@')
            (host,_,v) = v.partition(':')
            if v:
                port = int(v)
        elif k == '-c': cmdline = v
        elif k == '-n':
            dryrun = True
            ropts.append(k)
        elif k == '-i':
            ignorecase = True
            ropts.append(k)
        elif k == '-L':
            followlink = True
            ropts.append(k)
        elif k == '-E':
            for name in v.split(','):
                excldb.add_global(name)
            ropts.append(k)
            ropts.append(v)
        elif k == '-B':
            backupdir = v
            ropts.append(k)
            ropts.append(v)
        elif k == '-T':
            trashdir = v
            ropts.append(k)
            ropts.append(v)
        elif k == '-C':
            configfile = v
            ropts.append(k)
            ropts.append(v)
        elif k == '-Q':
            timeskew = int(v)
            ropts.append(k)
            ropts.append(v)
    if not args: return usage()
    
    logging.basicConfig(level=loglevel, filename=logfile)
    name = 'SyncDir(%d)' % os.getpid()
    logger = logging.getLogger(name)
    if username is not None and host is not None:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        rargs = [cmdline]+ropts+list(map(path2loc, args))
        logging.info('connecting: %s@%s:%s...' % (username, host, port)) 
        client.connect(host, port, username, allow_agent=True)
        logging.info('exec_command: %r...' % rargs)
        (stdin,stdout,stderr) = client.exec_command(' '.join(rargs))
        sync = SyncDir(logger, stdin, stdout,
                       dryrun=dryrun, configfile=configfile, excldb=excldb,
                       ignorecase=ignorecase, followlink=followlink,
                       timeskew=timeskew,
                       backupdir=backupdir, trashdir=trashdir)
        for arg1 in args:
            sync.run(arg1)
        stdout.close()
        stdin.close()
        stderr.close()
    else:
        sync = SyncDir(logger, sys.stdout.buffer, sys.stdin.buffer,
                       dryrun=dryrun, configfile=configfile, excldb=excldb,
                       ignorecase=ignorecase, followlink=followlink, 
                       timeskew=timeskew,
                       backupdir=backupdir, trashdir=trashdir)
        for arg1 in args:
            sync.run(loc2path(arg1))
    return 0

if __name__ == '__main__': sys.exit(main(sys.argv))
