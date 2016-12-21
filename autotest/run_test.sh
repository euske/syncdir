#!/bin/sh
PYTHON=python3
SYNCDIR="$PYTHON run_syncdir.py -c../syncdir3.py -i -B_backup -T_trash -C_ignore"
TESTBASE=testdir

# Create test directories
TESTDIR="${TESTBASE}.`date +'%Y%m%d%H%M%S'`"
D1=$TESTDIR/d1
D2=$TESTDIR/d2
mkdir $TESTDIR
mkdir $D1
mkdir $D2
echo "*** testdir: $TESTDIR"

# Creating new files
#   D1/foo
#   D1/ttt/t
#   D2/bar
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
#   D1/foo
#   D1/bar
#   D1/ttt/t
#   D2/foo
#   D2/bar
#   D2/ttt/t

# Ignoring files
#   D1/foo
#   D1/bar
#   D1/ttt/t
#   D1/.xxx
#   D1/a.yyy
#   D1/a.zzz
#   D2/foo
#   D2/bar
#   D2/ttt/t
echo "*** ignoring files"
echo xxx > $D1/.xxx
echo yyy > $D1/a.yyy
echo zzz > $D1/a.zzz
$SYNCDIR -E '*.yyy' $D1 $D2
[ ! -f $D2/.xxx ] || exit 301
[ ! -f $D2/a.yyy ] || exit 302
cmp $D1/a.zzz $D2/a.zzz || exit 303
sleep 1
#   D1/foo
#   D1/bar
#   D1/ttt/t
#   D1/.xxx
#   D1/a.yyy
#   D1/a.zzz
#   D2/foo
#   D2/bar
#   D2/ttt/t
#   D2/a.zzz

# Updating files
#   D1/foo
#   D1/bar
#   D1/ttt/t
#   D1/.xxx
#   D1/a.yyy
#   D1/a.zzz
#   D2/foo
#   D2/bar
#   D2/ttt/t
#   D2/a.zzz
echo "*** updating files"
cp $D1/foo $TESTDIR/foo
echo fooo > $D1/foo
cp $D1/bar $TESTDIR/bar
cp $TESTDIR/bar $D1/bar
$SYNCDIR $D1 $D2
cmp $D1/bar $TESTDIR/bar || exit 201
cmp $D1/bar $D2/bar || exit 202
cmp $D1/foo $D2/foo || exit 203
cmp $TESTDIR/foo $D2/_backup/foo.backup.* || exit 304
sleep 1
#   D1/foo
#   D1/bar
#   D1/ttt/t
#   D1/.xxx
#   D1/a.yyy
#   D1/a.zzz
#   D2/foo
#   D2/bar
#   D2/ttt/t
#   D2/a.yyy
#   D2/a.zzz
#   D2/_backup/foo.backup.*

# Ignoring cases
#   D1/FOO
#   D1/bar
#   D1/ttt/t
#   D1/.xxx
#   D1/a.yyy
#   D1/a.zzz
#   D2/foo
#   D2/Bar
#   D2/ttt/t
#   D2/a.yyy
#   D2/a.zzz
#   D2/_backup/foo.backup.*
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
#   D1/foo
#   D1/bar
#   D1/ttt/t
#   D1/.xxx
#   D1/a.yyy
#   D1/a.zzz
#   D2/foo
#   D2/bar
#   D2/ttt/t
#   D2/a.yyy
#   D2/a.zzz
#   D2/_backup/foo.backup.*

# Excluding files
#   D1/foo
#   D1/bar
#   D1/ttt/t
#   D1/.xxx
#   D1/a.yyy
#   D1/a.zzz
#   D2/foo
#   D2/bar
#   D2/ttt/t
#   D2/a.yyy
#   D2/a.zzz
#   D2/_backup/foo.backup.*
echo "*** excluding files"
echo foo > $D1/_ignore
echo t > $D2/ttt/_ignore
rm $D1/ttt/t
echo foooo > $D1/foo
echo xxxx > $D1/a.zzz
echo yyyy > $D2/a.zzz
$SYNCDIR -E '*.zzz' $D1 $D2
[ ! -f $D1/ttt/t ] || exit 501
cmp $D1/foo $D2/foo && exit 502
cmp $D1/a.zzz $D2/a.zzz && exit 503
rm $D1/_ignore
rm $D2/ttt/_ignore
echo t > $D1/ttt/t
sleep 1
#   D1/foo
#   D1/bar
#   D1/ttt/t
#   D1/.xxx
#   D1/a.yyy
#   D1/a.zzz
#   D2/foo
#   D2/bar
#   D2/ttt/t
#   D2/a.yyy
#   D2/a.zzz
#   D2/_backup/foo.backup.*

# Trashing files
#   D1/_trash/foo
#   D1/bar
#   D1/_trash/ttt/t
#   D1/.xxx
#   D1/a.yyy
#   D1/a.zzz
#   D2/foo
#   D2/_trash/bar
#   D2/ttt/t
#   D2/a.yyy
#   D2/a.zzz
#   D2/_backup/foo.backup.*
echo "*** trashing files"
mkdir $D1/_trash
mkdir $D2/_trash
mv $D1/foo $D1/_trash/foo
mv $D1/ttt $D1/_trash/ttt
mv $D2/bar $D2/_trash/bar
$SYNCDIR $D1 $D2
[ ! -f $D1/_trash/foo ] || exit 601
[ ! -f $D1/_trash/ttt/t ] || exit 602
[ ! -f $D2/_trash/bar ] || exit 603
[ ! -f $D2/foo ] || exit 604
[ ! -f $D2/ttt/t ] || exit 605
[ ! -f $D1/bar ] || exit 606
sleep 1
#   D1/.xxx
#   D1/a.yyy
#   D1/a.zzz
#   D2/a.yyy
#   D2/a.zzz

# cleanup
#echo "*** cleanup"
#rm -r $TESTDIR
