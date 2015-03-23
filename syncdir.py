#!/usr/bin/env python
import sys
import os
import os.path
import stat
import time
import hashlib
import logging
import cPickle as pickle


# netstring(x)
def netstring(x):
    if hasattr(x, '__iter__'):
        return ''.join( netstring(y) for y in x )
    else:
        x = str(x)   
        return '%d:%s,' % (len(x), x)


##  NetstringParser
##
class NetstringParser(object):
    
    def __init__(self):
        self.results = []
        self.reset()
        return

    def reset(self):
        self._data = ''
        self._length = 0
        self._parse = self._parse_len
        return
        
    def feed(self, s):
        i = 0
        while i < len(s):
            i = self._parse(s, i)
        return
        
    def _parse_len(self, s, i):
        while i < len(s):
            c = s[i]
            if c < '0' or '9' < c:
                self._parse = self._parse_sep
                break
            self._length *= 10
            self._length += ord(c)-48
            i += 1
        return i
        
    def _parse_sep(self, s, i):
        if s[i] != ':': raise SyntaxError(i)
        self._parse = self._parse_data
        return i+1
        
    def _parse_data(self, s, i):
        n = min(self._length, len(s)-i)
        self._data += s[i:i+n]
        self._length -= n
        if self._length == 0:
            self._parse = self._parse_end
        return i+n
        
    def _parse_end(self, s, i):
        if s[i] != ',': raise SyntaxError(i)
        self.results.append(self._data)
        self.reset()
        return i+1


##  SyncDir
##
class SyncDir(object):

    class ProtocolError(Exception): pass

    # bufsize_local: for scanning local files.
    bufsize_local = 65536
    # bufsize_wire: for sending/receiving data over network.
    bufsize_wire = 4096

    def __init__(self, logger, fp_send, fp_recv,
                 dryrun=False, backupdir=None, trashdir=None):
        self.logger = logger
        self.dryrun = dryrun
        self.backupdir = backupdir
        self.trashdir = trashdir
        self._fp_send = fp_send
        self._fp_recv = fp_recv
        return

    def is_dir_valid(self, dirpath, name):
        return (not name.startswith('.') and
                (name != self.backupdir and
                 name != self.trashdir))
    
    def is_file_valid(self, dirpath, name):
        return not name.startswith('.')

    def _send(self, x):
        #self.logger.debug(' send: %r' % x)
        self._fp_send.write(x)
        self._fp_send.flush()
        return
    def _recv(self, n):
        x = self._fp_recv.read(n)
        #self.logger.debug(' recv: %r' % x)
        return x
    
    def _send_str(self, s):
        self.logger.debug(' send_str: %r' % s)
        self._send(netstring(s))
        return
    def _recv_str(self):
        parser = NetstringParser()
        while not parser.results:
            c = self._recv(1)
            if not c: raise self.ProtocolError
            try:
                parser.feed(c)
            except SyntaxError:
                raise self.ProtocolError
        s = parser.results.pop()
        self.logger.debug(' recv_str: %r' % s)
        return s

    def _send_obj(self, obj):
        s = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
        self._send_str(s)
        return
    def _recv_obj(self):
        s = self._recv_str()
        return pickle.loads(s)
    
    def _gen_list(self, basedir):
        for (dirpath,dirnames,filenames) in os.walk(basedir):
            dirnames[:] = [ name for name in dirnames
                            if self.is_dir_valid(dirpath, name) ]
            for name in filenames:
                if not self.is_file_valid(dirpath, name): continue
                path = os.path.join(dirpath, name)
                if not os.path.isfile(path): continue
                try:
                    st = os.stat(path)
                    st_size = st[stat.ST_SIZE]
                    st_mtime = st[stat.ST_MTIME]
                    fp = open(path, 'rb')
                    try:
                        h = hashlib.md5()
                        while True:
                            data = fp.read(self.bufsize_local)
                            if not data: break
                            h.update(data)
                        relpath = os.path.relpath(path, basedir)
                        yield (relpath, st_size, st_mtime, h.digest())
                    finally:
                        fp.close()
                except (IOError, OSError):
                    pass
        return

    def _send_list(self, basedir):
        send_files = {}
        # Assuming each entry fits in one packet.
        for (relpath, size, mtime, digest) in self._gen_list(basedir):
            k = tuple(relpath.split(os.path.sep))
            path = os.path.join(basedir, relpath)
            send_files[k] = (path, size, mtime, digest)
            self._send_obj((k, size, mtime, digest))
            self._recv_list(basedir)
        self._send_obj(None)
        while self._recv_list(basedir):
            pass
        return send_files

    def _recv_list(self, basedir):
        if self._recv_phase != 0: return False
        # Assuming each entry fits in one packet.
        obj = self._recv_obj()
        if obj is None:
            self._recv_phase = 1
            return False
        try:
            (k, size, mtime, digest) = obj
            relpath = os.path.sep.join(k)
            path = os.path.join(basedir, relpath)
        except ValueError:
            raise self.ProtocolError
        self._recv_files[k] = (path, size, mtime, digest)
        return True

    def _send_file(self, fp, size):
        while size:
            # send one packet.
            bufsize = min(size, self.bufsize_wire)
            data = fp.read(bufsize)
            if not data: raise self.ProtocolError('file size changed')
            size -= len(data)
            self._send(data)
            if 0 < size:
                # receive one packet.
                self._recv_file()
        self._recv_file()
        return

    def _recv_file(self):
        # process only one packet and return.
        if self._rfile_bytes is not None:
            bufsize = min(self._rfile_bytes, self.bufsize_wire)
            data = self._recv(bufsize)
            self._rfile_bytes -= bufsize
            assert 0 <= self._rfile_bytes
            if self._rfile_fp is not None:
                self._rfile_fp.write(data)
            if 0 < self._rfile_bytes: return True
            self._rfile_bytes = None
            if self._rfile_fp is not None:
                path = self._rfile_fp.name
                self._rfile_fp.close()
                self._rfile_fp = None
                if (self.backupdir is not None and
                    os.path.isfile(self._rfile_path)):
                    self._backup_file(self._rfile_path)
                try:
                    os.rename(path, self._rfile_path)
                except (IOError, OSError), e:
                    self.logger.error('recv: rename %r: %r' % (path, e))
            return True
        assert self._rfile_bytes is None
        assert self._rfile_fp is None
        
        if self._rfile_queue:
            k = self._recv_obj()
            (path,size0,mtime0,digest0) = self._recv_files[k]
            assert k in self._rfile_queue
            self._rfile_queue.remove(k)
            self._rfile_bytes = size0
            self._rfile_path = path
            try:
                self.logger.info('recv: %r (%s)' % (path, size0))
                if not self.dryrun:
                    tmppath = os.path.join(os.path.dirname(path),
                                           'tmp'+digest0.encode('hex'))
                    self._rfile_fp = open(tmppath, 'wb')
            except (IOError, OSError), e:
                self.logger.error('recv: %r: %r' % (path, e))
            return True

        assert not self._rfile_queue
        return False

    def _backup_file(self, path):
        assert self.backupdir is not None
        backupdir = os.path.join(os.path.dirname(path), self.backupdir)
        if not os.path.isdir(backupdir):
            try:
                os.mkdir(backupdir)
            except (IOError, OSError), e:
                self.logger.error('recv: mkdir %r: %r' % (backupdir, e))
                return
        try:
            timestamp = time.strftime('%Y%m%d%H%M%S')
            name = os.path.basename(path)+'.backup'+timestamp
            dstpath = os.path.join(backupdir, name)
            os.rename(path, dstpath)
        except (IOError, OSError), e:
            self.logger.error('recv: backup %r -> %r: %r' % (path, dstpath, e))
        return

    def run(self, basedir):
        self.logger.info('listing: %r...' % basedir)
        # send/recv the file list.
        self._recv_phase = 0
        self._recv_files = {}
        send_files = self._send_list(basedir)
        # compute the difference.
        send_new = []
        recv_new = []
        send_update = []
        recv_update = []
        for (k,(path,size0,mtime0,digest0)) in send_files.iteritems():
            if k in self._recv_files:
                (_,size1,mtime1,digest1) = self._recv_files[k]
                if digest0 != digest1:
                    if mtime1 < mtime0:
                        send_update.append(k)
                    else:
                        recv_update.append(k)
            else:
                send_new.append(k)
        for k in self._recv_files.iterkeys():
            if k not in send_files:
                recv_new.append(k)
        self.logger.info('sending: %d new, %d update...' %
                         (len(send_new), len(send_update)))
        self.logger.info('receiving: %d new, %d update...' %
                         (len(recv_new), len(recv_update)))
        # create receiving directories.
        self._rfile_queue = set(recv_new + recv_update)
        dirs = set()
        for k in self._rfile_queue:
            if k in dirs: continue
            dirs.add(k)
            (path,_,_,_) = self._recv_files[k]
            path = os.path.dirname(path)
            if os.path.isdir(path): continue
            self.logger.info('mkdir: %r' % path)
            if not self.dryrun:
                try:
                    os.makedirs(path)
                except OSError, e:
                    self.logger.error('mkdir: %r: %r' % (path, e))
        # send/recv the files.
        self._rfile_bytes = None
        self._rfile_fp = None
        for k in (send_new + send_update):
            try:
                (path,size0,mtime0,digest0) = send_files[k]
                self.logger.info('send: %r (%s)' % (path, size0))
                fp = open(path, 'rb')
                # send one packet.
                self._send_obj(k)
                # receive one packet.
                self._recv_file()
                try:
                    self._send_file(fp, size0)
                finally:
                    fp.close()
            except (IOError, OSError), e:
                self.logger.error('send: %r: %r' % (path, e))
        while self._recv_file():
            pass
        return

# main
def main(argv):
    import getopt
    def usage():
        print ('usage: %s [-d] [-l logfile] [-p user@host:port] [-c cmdline] '
               '[-n] [-B backupdir] [-T trashdir] '
               '[dir ...]' % argv[0])
        return 100
    try:
        (opts, args) = getopt.getopt(argv[1:], 'dl:p:c:nB:T:')
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
    backupdir = None
    trashdir = None
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
        elif k == '-B':
            backupdir = v
            ropts.append(k)
            ropts.append(v)
        elif k == '-T':
            trashdir = v
            ropts.append(k)
            ropts.append(v)
    if not args: return usage()
    
    logging.basicConfig(level=loglevel, filename=logfile, filemode='a')
    name = 'SyncDir(%d)' % os.getpid()
    logger = logging.getLogger(name)
    if username is not None and host is not None:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        path = args.pop(0)
        rargs = [cmdline]+ropts+path.split(os.path.sep)
        logging.info('connecting: %s@%s:%s...' % (username, host, port)) 
        client.connect(host, port, username, allow_agent=True)
        logging.info('exec_command: %r...' % rargs)
        (stdin,stdout,stderr) = client.exec_command(' '.join(rargs))
        sync = SyncDir(logger, stdin, stdout,
                       dryrun=dryrun, backupdir=backupdir, trashdir=trashdir)
        sync.run(unicode(path))
        stdout.close()
        stdin.close()
        stderr.close()
    else:
        sync = SyncDir(logger, sys.stdout, sys.stdin,
                       dryrun=dryrun, backupdir=backupdir, trashdir=trashdir)
        path = os.path.sep.join(args)
        sync.run(unicode(path))
    return 0

if __name__ == '__main__': sys.exit(main(sys.argv))
