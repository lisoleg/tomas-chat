# uscsfs/Makefile —— TOMAS-AGI v2.0 USCS 文件系统子目录
#
# 用法：
#   make -C /lib/modules/$(uname -r)/build M=$(PWD) modules
#
# 依赖：
#   - 父目录的 M2 模块必须先编译（octonion.c, eml_map.c, delta_mem.c, phi_gate.c）
#   - 本目录模块编译后，需手动 insmod（按依赖顺序）

obj-m := super.o inode.o file.o mmap.o

KDIR ?= /lib/modules/$(shell uname -r)/build

all:
	$(MAKE) -C $(KDIR) M=$(shell pwd) modules

clean:
	$(MAKE) -C $(KDIR) M=$(shell pwd) clean

# 依赖顺序：先编译父目录 M2 模块
dep:
	$(MAKE) -C .. all

# 插入模块（按依赖顺序）
insmod:
	sudo insmod ../octonion.ko
	sudo insmod ../eml_map.ko
	sudo insmod ../delta_mem.ko
	sudo insmod ../phi_gate.ko
	sudo insmod super.ko
	sudo insmod inode.ko
	sudo insmod file.ko
	sudo insmod mmap.ko
	sudo insmod ../tproc_core.ko

# 卸载模块（逆序）
rmmod:
	sudo rmmod tproc_core 2>/dev/null || true
	sudo rmmod mmap 2>/dev/null || true
	sudo rmmod file 2>/dev/null || true
	sudo rmmod inode 2>/dev/null || true
	sudo rmmod super 2>/dev/null || true
	sudo rmmod phi_gate 2>/dev/null || true
	sudo rmmod delta_mem 2>/dev/null || true
	sudo rmmod eml_map 2>/dev/null || true
	sudo rmmod octonion 2>/dev/null || true

.PHONY: all clean dep insmod rmmod
