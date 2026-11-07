CROSS_CC ?= aarch64-linux-gnu-gcc
CFLAGS ?= -static -O2

loop_test_arm64: loop_test.c
	$(CROSS_CC) $(CFLAGS) -o $@ $<

clean:
	rm -f loop_test_arm64
