# Makefile

all:

test:
	cd autotest; ./run_test.sh

clean:
	cd autotest; $(RM) -r testdir.*
