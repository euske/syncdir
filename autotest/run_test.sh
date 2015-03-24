#!/bin/sh
PYTHON=python2
SYNCDIR="$PYTHON run_syncdir.py -c../syncdir.py -i -B_backup -T_trash"
TESTBASE=testdir

# create test directories
TESTDIR="${TESTBASE}.`date +'%Y%m%d%H%M%S'`"
D1=$TESTDIR/d1
D2=$TESTDIR/d2
mkdir $TESTDIR
mkdir $D1
mkdir $D2
echo "*** testdir: $TESTDIR"

# creating new files
echo "*** creating new files"
echo foo > $D1/foo
mkdir $D1/ttt
echo t > $D1/ttt/t
$SYNCDIR -n $D1 $D2
[ ! -f $D2/foo ] || exit 101
$SYNCDIR $D1 $D2
cmp $D1/foo $D2/foo || exit 102
cmp $D1/ttt/t $D2/ttt/t || exit 103
echo bar > $D2/bar
$SYNCDIR $D1 $D2
cmp $D1/bar $D2/bar || exit 104
sleep 1

# ignoring files
echo "*** ignoring files"
echo xxx > $D1/.xxx
echo yyy > $D1/a.yyy
echo zzz > $D1/a.zzz
$SYNCDIR -Iyyy $D1 $D2
[ ! -f $D2/.xxx ] || exit 301
[ ! -f $D2/a.yyy ] || exit 302
cmp $D1/a.zzz $D2/a.zzz || exit 303
sleep 1

# updating files
echo "*** updating files"
cp $D1/foo $TESTDIR/foo
echo foooo > $D1/foo
cp $D1/bar $TESTDIR/bar
cp $TESTDIR/bar $D1/bar
$SYNCDIR $D1 $D2
cmp $D1/bar $TESTDIR/bar || exit 201
cmp $D1/bar $D2/bar || exit 202
cmp $D1/foo $D2/foo || exit 203
cmp $TESTDIR/foo $D2/_backup/foo.backup.* || exit 304
sleep 1

# ignoring cases
echo "*** ignoring cases"
mv $D1/foo $D1/FOO
mv $D2/bar $D2/Bar
$SYNCDIR $D1 $D2
[ ! -f $D2/FOO ] || exit 401
[ ! -f $D1/Bar ] || exit 402
cmp $D1/FOO $D2/foo || exit 403
cmp $D1/bar $D2/Bar || exit 404
mv $D1/FOO $D1/foo
mv $D2/Bar $D2/bar
sleep 1

# trashing files
echo "*** trashing files"
mkdir $D1/_trash
mkdir $D2/_trash
mv $D1/foo $D1/_trash/foo
mv $D1/ttt $D1/_trash/ttt
mv $D2/bar $D2/_trash/bar
$SYNCDIR $D1 $D2
[ ! -f $D2/foo ] || exit 501
[ ! -f $D2/ttt ] || exit 502
[ ! -f $D1/bar ] || exit 503
sleep 1

# cleanup
#echo "*** cleanup"
#rm -r $TESTDIR
