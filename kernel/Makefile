# TOMAS-AGI v2.0 内核模块 Makefile（M2 里程碑）
#
# 用法：
#   make -C /lib/modules/$(uname -r)/build M=$(PWD) modules   # 编译
#   make -C /lib/modules/$(uname -r)/build M=$(PWD) clean     # 清理
#
# 要求：
#   - Linux 内核 5.10+（建议 6.1+）
#   - 内核头文件已安装
#   - CONFIG_MODULES 已启用

obj-m := tproc_core.o \
         octonion.o \
         spectral_laplacian.o \
         asym_residue.o \
         kappa_reg.o \
         eml_map.o \
         phi_gate.o \
         delta_mem.o \
         ci_gate.o \
         st_auditor.o \
         uscsfs/super.o \
         uscsfs/inode.o \
         uscsfs/file.o \
         uscsfs/mmap.o

KERNEL_DIR ?= /lib/modules/$(shell uname -r)/build

all:
	$(MAKE) -C $(KERNEL_DIR) M=$(shell pwd) modules

clean:
	$(MAKE) -C $(KERNEL_DIR) M=$(shell pwd) clean

# ============================================================
# M4 CUDA 模块编译规则
# ============================================================
# 需要 NVIDIA CUDA Toolkit（nvcc）
# 编译：make cuda

NVCC ?= nvcc
CUDA_ARCH ?= sm_60
CUDA_FLAGS := -arch=$(CUDA_ARCH) -O2 -DTEST

CUDA_OBJ := cuda_octonion.o cuda_laplacian.o cuda_delta_mem.o

cuda: $(CUDA_OBJ)
	@echo "M4 CUDA modules built: $(CUDA_OBJ)"

cuda_octonion.o: cuda_octonion.cu
	$(NVCC) -c $< -o $@ $(CUDA_FLAGS)

cuda_laplacian.o: cuda_laplacian.cu
	$(NVCC) -c $< -o $@ $(CUDA_FLAGS)

cuda_delta_mem.o: cuda_delta_mem.cu
	$(NVCC) -c $< -o $@ $(CUDA_FLAGS)

cuda-test: $(CUDA_OBJ)
	$(NVCC) $(CUDA_OBJ) -o cuda_test $(CUDA_FLAGS)
	./cuda_test

cuda-clean:
	rm -f $(CUDA_OBJ) cuda_test

# 编译用户态测试程序（用于在 Windows 上验证核心逻辑）
# 使用 GCC 或 Clang（非内核环境）
test: test_user.c
	gcc -std=c11 -Wall -O2 -o test_user test_user.c -lm
	./test_user

# 安装模块
install:
	$(MAKE) -C $(KERNEL_DIR) M=$(shell pwd) modules_install
	depmod -a

# 插入模块（按依赖顺序）
insmod:
	sudo insmod octonion.ko
	sudo insmod spectral_laplacian.ko
	sudo insmod asym_residue.ko
	sudo insmod kappa_reg.ko
	sudo insmod eml_map.ko
	sudo insmod phi_gate.ko
	sudo insmod delta_mem.ko
	sudo insmod ci_gate.ko
	sudo insmod st_auditor.ko
	sudo insmod tproc_core.ko

# 卸载模块（逆序）
rmmod:
	sudo rmmod tproc_core
	sudo rmmod st_auditor
	sudo rmmod ci_gate
	sudo rmmod delta_mem
	sudo rmmod phi_gate
	sudo rmmod eml_map
	sudo rmmod kappa_reg
	sudo rmmod asym_residue
	sudo rmmod spectral_laplacian
	sudo rmmod octonion

# 查看内核日志
log:
	dmesg | tail -50

.PHONY: all clean test install insmod rmmod log
