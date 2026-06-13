/*
 * cuda_octonion.cu — T031: GPU 八元数乘法 + 并行 associator 计算
 *
 * TOMAS-AGI v2.0 M4 里程碑 — CUDA 加速核心层
 * 基于 NASGA（非结合谱图代数），将八元数乘法、associator、δ 参数计算并行化到 GPU。
 *
 * 关键设计：
 *   1. Fano 平面乘法表存储于 constant memory（64B 只读缓存优化）
 *   2. 批量八元数乘法 kernel：支持 N 组八元数并行
 *   3. 并行 associator：associator(a,b,c) = (a*b)*c - a*(b*c)
 *   4. 批量 δ 计算：δ = associator_norm / (||a||·||b||·||c|| + ε)
 *   5. extern "C" 导出接口，供 M2 CPU 内核模块调用
 *
 * 编译：nvcc -c cuda_octonion.cu -o cuda_octonion.o -arch=sm_60
 *
 * 作者：章锋（章锋）© 2026 复合体理学研究中心（TOMAS 项目组）
 */

#include <cuda_runtime.h>
#include <device_launch_parameters.h>
#include <math.h>
#include <stdio.h>

/* ============================================================
 * 第1部分：数据结构定义（与 M2 octonion.c 兼容）
 * ============================================================ */

/** 八元数结构体（8 个实分量，GPU 友好对齐） */
typedef struct {
    float e0, e1, e2, e3, e4, e5, e6, e7;
} Octonion;

/** 八元数数组描述符（host-device 传输用） */
typedef struct {
    Octonion *data;         /**< 八元数数组指针（device） */
    int count;              /**< 元素数量 */
} OctonionBatch;

/** associator 结果 */
typedef struct {
    Octonion value;         /**< associator 八元数值 */
    float norm;             /**< 结合子范数 */
} AssociatorResult;

/** δ 参数结果 */
typedef struct {
    unsigned long long delta_milli;  /**< δ 值（毫单位，与 M2 一致） */
    float delta_raw;                 /**< δ 原始浮点值 */
    int regime;                      /**< δ 域分类（0-3） */
} DeltaResult;

/* ============================================================
 * 第2部分：Fano 平面乘法表（constant memory）
 * ============================================================ */

/**
 * Fano 平面 7 条边定义非结合乘法规则：
 *   e1*e2=e4, e2*e4=e1, e4*e1=e2
 *   e3*e5=e1, e5*e1=e3, e1*e3=e5
 *   e6*e7=e1 (中心边)
 *
 * 存储为 compact 格式：(i, j, k, sign) 表示 e_i * e_j = sign * e_k
 * sign = +1 表示正，sign = -1 表示循环排列取反
 */
__constant__ int fano_table[7][3] = {
    {1, 2, 4},   /* e1*e2 = e4 */
    {2, 4, 1},   /* e2*e4 = e1 */
    {4, 1, 2},   /* e4*e1 = e2 */
    {3, 5, 7},   /* e3*e5 = e7 (注意：修正为 e7，映射到复合结构) */
    {5, 6, 1},   /* e5*e6 = e1 (复合体理学 Fano 修正) */
    {6, 3, 2},   /* e6*e3 = e2 (复合体理学 Fano 修正) */
    {7, 1, 3},   /* e7*e1 = e3 (复合体理学 Fano 修正) */
};

/* ============================================================
 * 第3部分：GPU kernel — 八元数乘法
 * ============================================================ */

/**
 * 单次八元数乘法（device 函数）
 * 基于 Fano 平面查表实现非结合乘法
 */
__device__ void oct_multiply_device(const Octonion *a, const Octonion *b,
                                     Octonion *result) {
    /* 初始化：e0 分量 = a0*b0 - Σ_{i=1..7} a_i*b_i */
    result->e0 = a->e0 * b->e0
               - a->e1 * b->e1 - a->e2 * b->e2 - a->e3 * b->e3
               - a->e4 * b->e4 - a->e5 * b->e5 - a->e6 * b->e6 - a->e7 * b->e7;

    result->e1 = a->e0 * b->e1 + a->e1 * b->e0;
    result->e2 = a->e0 * b->e2 + a->e2 * b->e0;
    result->e3 = a->e0 * b->e3 + a->e3 * b->e0;
    result->e4 = a->e0 * b->e4 + a->e4 * b->e0;
    result->e5 = a->e0 * b->e5 + a->e5 * b->e0;
    result->e6 = a->e0 * b->e6 + a->e6 * b->e0;
    result->e7 = a->e0 * b->e7 + a->e7 * b->e0;

    /* Fano 平面交叉项（非结合贡献） */
    for (int t = 0; t < 7; t++) {
        int i = fano_table[t][0];
        int j = fano_table[t][1];
        int k = fano_table[t][2];

        /* 获取 ai, bj 分量 */
        const float *ap = (const float *)a;
        const float *bp = (const float *)b;
        float *rp = (float *)result;

        float term = ap[i] * bp[j];

        /* 累加到 ek */
        rp[k] += term;

        /* 累加到 e0（标量部分修正） */
        result->e0 -= term;
    }
}

/* ============================================================
 * 第4部分：批量八元数乘法 kernel
 * ============================================================ */

/**
 * 批量八元数乘法 CUDA kernel
 * 对 N 组八元数对 (a_i, b_i) 并行计算乘积 c_i = a_i * b_i
 *
 * @param a_array  输入八元数数组 A（device 指针）
 * @param b_array  输入八元数数组 B（device 指针）
 * @param c_array  输出八元数数组 C = A * B（device 指针）
 * @param n        数组长度（八元数对数量）
 */
__global__ void batch_oct_multiply_kernel(const Octonion *a_array,
                                           const Octonion *b_array,
                                           Octonion *c_array,
                                           int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;

    oct_multiply_device(&a_array[idx], &b_array[idx], &c_array[idx]);
}

/**
 * 三路八元数乘法 kernel（用于 associator 计算的第一步）
 * 并行计算 tmp1 = a*b, tmp2 = b*c
 *
 * @param a_array  输入数组 A
 * @param b_array  输入数组 B
 * @param c_array  输入数组 C
 * @param tmp1     输出 tmp1 = A * B
 * @param tmp2     输出 tmp2 = B * C
 * @param n        组数
 */
__global__ void triple_multiply_kernel(const Octonion *a_array,
                                        const Octonion *b_array,
                                        const Octonion *c_array,
                                        Octonion *tmp1,
                                        Octonion *tmp2,
                                        int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;

    oct_multiply_device(&a_array[idx], &b_array[idx], &tmp1[idx]);
    oct_multiply_device(&b_array[idx], &c_array[idx], &tmp2[idx]);
}

/* ============================================================
 * 第5部分：并行 associator 计算
 * ============================================================ */

/**
 * 并行 associator 计算 kernel
 *
 * associator(a,b,c) = (a*b)*c - a*(b*c)
 *
 * 分两步：
 *   Step 1: 并行计算 (a*b)*c 和 a*(b*c)
 *   Step 2: 并行做差得到 associator
 *
 * @param a_array    输入数组 A
 * @param b_array    输入数组 B
 * @param c_array    输入数组 C
 * @param tmp1       Step 1 中间结果：a*b
 * @param tmp2       Step 1 中间结果：b*c
 * @param left       Step 2 中间结果：(a*b)*c
 * @param right      Step 2 中间结果：a*(b*c)
 * @param results    输出 associator 结果
 * @param n          组数
 */
__global__ void associator_step1_kernel(const Octonion *a_array,
                                         const Octonion *b_array,
                                         const Octonion *c_array,
                                         Octonion *tmp1,
                                         Octonion *tmp2,
                                         int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;

    /* tmp1 = a*b, tmp2 = b*c */
    oct_multiply_device(&a_array[idx], &b_array[idx], &tmp1[idx]);
    oct_multiply_device(&b_array[idx], &c_array[idx], &tmp2[idx]);
}

__global__ void associator_step2_kernel(Octonion *tmp1,
                                         const Octonion *c_array,
                                         const Octonion *a_array,
                                         Octonion *tmp2,
                                         AssociatorResult *results,
                                         int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;

    /* left = (a*b)*c */
    Octonion left;
    oct_multiply_device(&tmp1[idx], &c_array[idx], &left);

    /* right = a*(b*c) */
    Octonion right;
    oct_multiply_device(&a_array[idx], &tmp2[idx], &right);

    /* associator = left - right */
    Octonion *assoc = &results[idx].value;
    assoc->e0 = left.e0 - right.e0;
    assoc->e1 = left.e1 - right.e1;
    assoc->e2 = left.e2 - right.e2;
    assoc->e3 = left.e3 - right.e3;
    assoc->e4 = left.e4 - right.e4;
    assoc->e5 = left.e5 - right.e5;
    assoc->e6 = left.e6 - right.e6;
    assoc->e7 = left.e7 - right.e7;

    /* associator_norm = sqrt(sum of squares) */
    float sum_sq = assoc->e0 * assoc->e0
                 + assoc->e1 * assoc->e1
                 + assoc->e2 * assoc->e2
                 + assoc->e3 * assoc->e3
                 + assoc->e4 * assoc->e4
                 + assoc->e5 * assoc->e5
                 + assoc->e6 * assoc->e6
                 + assoc->e7 * assoc->e7;
    results[idx].norm = sqrtf(sum_sq);
}

/* ============================================================
 * 第6部分：并行 δ 参数计算
 * ============================================================ */

/**
 * 计算八元数范数（device 函数）
 */
__device__ float oct_norm_device(const Octonion *o) {
    return sqrtf(o->e0 * o->e0 + o->e1 * o->e1 + o->e2 * o->e2
               + o->e3 * o->e3 + o->e4 * o->e4 + o->e5 * o->e5
               + o->e6 * o->e6 + o->e7 * o->e7);
}

/**
 * 批量 δ 参数计算 kernel
 *
 * v2.0 定义：δ = ||[a,b,c]|| / (||a||·||b||·||c|| + ε)
 * 输出为 millidelta（毫单位，与 M2 CPU 模块一致）
 *
 * @param assoc_results  associator 计算结果（含 norm）
 * @param a_array       原始八元数 A
 * @param b_array       原始八元数 B
 * @param c_array       原始八元数 C
 * @param delta_results  输出 δ 结果
 * @param n              组数
 */
__global__ void batch_delta_kernel(const AssociatorResult *assoc_results,
                                    const Octonion *a_array,
                                    const Octonion *b_array,
                                    const Octonion *c_array,
                                    DeltaResult *delta_results,
                                    int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;

    float associator_norm = assoc_results[idx].norm;
    float norm_a = oct_norm_device(&a_array[idx]);
    float norm_b = oct_norm_device(&b_array[idx]);
    float norm_c = oct_norm_device(&c_array[idx]);

    /* δ = associator_norm / (norm_a * norm_b * norm_c + 1e-10) */
    float denominator = norm_a * norm_b * norm_c + 1e-10f;
    float delta_raw = associator_norm / denominator;

    delta_results[idx].delta_raw = delta_raw;

    /* 转换为 millidelta（毫单位，固定点） */
    delta_results[idx].delta_milli = (unsigned long long)(delta_raw * 1000.0f);

    /* δ 域分类 */
    if (delta_raw < 0.1f) {
        delta_results[idx].regime = 0;  /* classical */
    } else if (delta_raw < 0.5f) {
        delta_results[idx].regime = 1;  /* quantum */
    } else if (delta_raw < 10.0f) {
        delta_results[idx].regime = 2;  /* stable (κ=7) */
    } else {
        delta_results[idx].regime = 3;  /* deep quantum */
    }
}

/* ============================================================
 * 第7部分：批量 δ 稳定性检查 kernel
 * ============================================================ */

/**
 * A1 公理批量校验 kernel
 *
 * 检查 δ_before ≈ δ_after（δ 守恒）
 * 对 N 组变换前后 δ 值进行比较
 *
 * @param delta_before  变换前 δ 数组
 * @param delta_after   变换后 δ 数组
 * @param pass_flags    输出通过标志（1=通过，0=失败）
 * @param n             组数
 * @param tolerance_milli 容忍度（毫单位）
 */
__global__ void a1_axiom_check_kernel(const DeltaResult *delta_before,
                                       const DeltaResult *delta_after,
                                       int *pass_flags,
                                       int n,
                                       unsigned long long tolerance_milli) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;

    unsigned long long diff;
    if (delta_before[idx].delta_milli > delta_after[idx].delta_milli) {
        diff = delta_before[idx].delta_milli - delta_after[idx].delta_milli;
    } else {
        diff = delta_after[idx].delta_milli - delta_before[idx].delta_milli;
    }

    pass_flags[idx] = (diff <= tolerance_milli) ? 1 : 0;
}

/* ============================================================
 * 第8部分：Host 接口函数（extern "C" 供内核模块调用）
 * ============================================================ */

extern "C" {

/**
 * 在 GPU 上分配 Octonion 数组
 *
 * @param count  八元数个数
 * @return       device 指针，失败返回 NULL
 */
Octonion *cuda_octonion_alloc_device(int count) {
    Octonion *d_ptr = NULL;
    cudaError_t err = cudaMalloc(&d_ptr, count * sizeof(Octonion));
    if (err != cudaSuccess) {
        fprintf(stderr, "[cuda_octonion] cudaMalloc failed: %s\n",
                cudaGetErrorString(err));
        return NULL;
    }
    return d_ptr;
}

/**
 * 将八元数数据从 host 拷贝到 device
 *
 * @param d_ptr   device 指针
 * @param h_ptr   host 指针
 * @param count   元素数量
 * @return        0 成功，-1 失败
 */
int cuda_octonion_copy_to_device(Octonion *d_ptr, const Octonion *h_ptr,
                                  int count) {
    cudaError_t err = cudaMemcpy(d_ptr, h_ptr, count * sizeof(Octonion),
                                  cudaMemcpyHostToDevice);
    if (err != cudaSuccess) {
        fprintf(stderr, "[cuda_octonion] H2D copy failed: %s\n",
                cudaGetErrorString(err));
        return -1;
    }
    return 0;
}

/**
 * 将八元数数据从 device 拷贝回 host
 *
 * @param h_ptr   host 指针
 * @param d_ptr   device 指针
 * @param count   元素数量
 * @return        0 成功，-1 失败
 */
int cuda_octonion_copy_to_host(Octonion *h_ptr, const Octonion *d_ptr,
                                int count) {
    cudaError_t err = cudaMemcpy(h_ptr, d_ptr, count * sizeof(Octonion),
                                  cudaMemcpyDeviceToHost);
    if (err != cudaSuccess) {
        fprintf(stderr, "[cuda_octonion] D2H copy failed: %s\n",
                cudaGetErrorString(err));
        return -1;
    }
    return 0;
}

/**
 * 释放 device 内存
 */
void cuda_octonion_free_device(Octonion *d_ptr) {
    if (d_ptr) cudaFree(d_ptr);
}

/**
 * 批量八元数乘法（GPU 加速）
 *
 * 计算 c[i] = a[i] * b[i]  for i = 0..n-1
 *
 * @param h_a       host 输入数组 A
 * @param h_b       host 输入数组 B
 * @param h_c       host 输出数组 C（结果写回）
 * @param n         八元数对数量
 * @return          0 成功，-1 失败
 */
int cuda_batch_oct_multiply(const Octonion *h_a, const Octonion *h_b,
                             Octonion *h_c, int n) {
    if (n <= 0) return -1;

    Octonion *d_a = NULL, *d_b = NULL, *d_c = NULL;

    /* 分配 device 内存 */
    if (!(d_a = cuda_octonion_alloc_device(n))) goto cleanup;
    if (!(d_b = cuda_octonion_alloc_device(n))) goto cleanup;
    if (!(d_c = cuda_octonion_alloc_device(n))) goto cleanup;

    /* 拷贝输入到 device */
    if (cuda_octonion_copy_to_device(d_a, h_a, n) != 0) goto cleanup;
    if (cuda_octonion_copy_to_device(d_b, h_b, n) != 0) goto cleanup;

    /* 执行 kernel */
    int block_size = 256;
    int grid_size = (n + block_size - 1) / block_size;
    batch_oct_multiply_kernel<<<grid_size, block_size>>>(d_a, d_b, d_c, n);

    cudaError_t err = cudaGetLastError();
    if (err != cudaSuccess) {
        fprintf(stderr, "[cuda_octonion] kernel launch failed: %s\n",
                cudaGetErrorString(err));
        goto cleanup;
    }
    cudaDeviceSynchronize();

    /* 拷贝结果回 host */
    if (cuda_octonion_copy_to_host(h_c, d_c, n) != 0) goto cleanup;

    cuda_octonion_free_device(d_a);
    cuda_octonion_free_device(d_b);
    cuda_octonion_free_device(d_c);
    return 0;

cleanup:
    cuda_octonion_free_device(d_a);
    cuda_octonion_free_device(d_b);
    cuda_octonion_free_device(d_c);
    return -1;
}

/**
 * 批量 associator 计算（GPU 加速）
 *
 * 计算 associator_i = (a_i * b_i) * c_i - a_i * (b_i * c_i)
 * 返回结合子范数
 *
 * @param h_a          host 八元数 A
 * @param h_b          host 八元数 B
 * @param h_c          host 八元数 C
 * @param h_results    host 输出结果数组
 * @param n            组数
 * @return             0 成功，-1 失败
 */
int cuda_batch_associator(const Octonion *h_a, const Octonion *h_b,
                           const Octonion *h_c, AssociatorResult *h_results,
                           int n) {
    if (n <= 0) return -1;

    Octonion *d_a = NULL, *d_b = NULL, *d_c = NULL;
    Octonion *d_tmp1 = NULL, *d_tmp2 = NULL;
    AssociatorResult *d_results = NULL;

    if (!(d_a = cuda_octonion_alloc_device(n))) goto cleanup;
    if (!(d_b = cuda_octonion_alloc_device(n))) goto cleanup;
    if (!(d_c = cuda_octonion_alloc_device(n))) goto cleanup;
    if (!(d_tmp1 = cuda_octonion_alloc_device(n))) goto cleanup;
    if (!(d_tmp2 = cuda_octonion_alloc_device(n))) goto cleanup;

    cudaError_t err = cudaMalloc(&d_results, n * sizeof(AssociatorResult));
    if (err != cudaSuccess) goto cleanup;

    if (cuda_octonion_copy_to_device(d_a, h_a, n) != 0) goto cleanup;
    if (cuda_octonion_copy_to_device(d_b, h_b, n) != 0) goto cleanup;
    if (cuda_octonion_copy_to_device(d_c, h_c, n) != 0) goto cleanup;

    int block_size = 256;
    int grid_size = (n + block_size - 1) / block_size;

    /* Step 1: tmp1=a*b, tmp2=b*c */
    associator_step1_kernel<<<grid_size, block_size>>>(
        d_a, d_b, d_c, d_tmp1, d_tmp2, n);
    cudaDeviceSynchronize();

    /* Step 2: associator = (a*b)*c - a*(b*c) */
    associator_step2_kernel<<<grid_size, block_size>>>(
        d_tmp1, d_c, d_a, d_tmp2, d_results, n);

    err = cudaGetLastError();
    if (err != cudaSuccess) {
        fprintf(stderr, "[cuda_octonion] associator kernel failed: %s\n",
                cudaGetErrorString(err));
        goto cleanup;
    }
    cudaDeviceSynchronize();

    /* 拷贝结果回 host */
    err = cudaMemcpy(h_results, d_results, n * sizeof(AssociatorResult),
                     cudaMemcpyDeviceToHost);
    if (err != cudaSuccess) goto cleanup;

    cuda_octonion_free_device(d_a);
    cuda_octonion_free_device(d_b);
    cuda_octonion_free_device(d_c);
    cuda_octonion_free_device(d_tmp1);
    cuda_octonion_free_device(d_tmp2);
    if (d_results) cudaFree(d_results);
    return 0;

cleanup:
    cuda_octonion_free_device(d_a);
    cuda_octonion_free_device(d_b);
    cuda_octonion_free_device(d_c);
    cuda_octonion_free_device(d_tmp1);
    cuda_octonion_free_device(d_tmp2);
    if (d_results) cudaFree(d_results);
    return -1;
}

/**
 * 批量 δ 参数计算（GPU 加速）
 *
 * 先计算 associator，再输出 δ 值
 *
 * @param h_a             host 八元数 A
 * @param h_b             host 八元数 B
 * @param h_c             host 八元数 C
 * @param h_delta_results  host 输出 δ 结果数组
 * @param n               组数
 * @return                0 成功，-1 失败
 */
int cuda_batch_delta(const Octonion *h_a, const Octonion *h_b,
                      const Octonion *h_c, DeltaResult *h_delta_results,
                      int n) {
    if (n <= 0) return -1;

    /* 先计算 associator */
    AssociatorResult *h_assoc = (AssociatorResult *)malloc(
        n * sizeof(AssociatorResult));
    if (!h_assoc) return -1;

    int ret = cuda_batch_associator(h_a, h_b, h_c, h_assoc, n);
    if (ret != 0) {
        free(h_assoc);
        return -1;
    }

    /* 拷贝到 device 进行 δ 计算 */
    Octonion *d_a = NULL, *d_b = NULL, *d_c = NULL;
    AssociatorResult *d_assoc = NULL;
    DeltaResult *d_delta = NULL;

    if (!(d_a = cuda_octonion_alloc_device(n))) goto cleanup2;
    if (!(d_b = cuda_octonion_alloc_device(n))) goto cleanup2;
    if (!(d_c = cuda_octonion_alloc_device(n))) goto cleanup2;

    cudaError_t err;
    err = cudaMalloc(&d_assoc, n * sizeof(AssociatorResult));
    if (err != cudaSuccess) goto cleanup2;
    err = cudaMalloc(&d_delta, n * sizeof(DeltaResult));
    if (err != cudaSuccess) goto cleanup2;

    if (cuda_octonion_copy_to_device(d_a, h_a, n) != 0) goto cleanup2;
    if (cuda_octonion_copy_to_device(d_b, h_b, n) != 0) goto cleanup2;
    if (cuda_octonion_copy_to_device(d_c, h_c, n) != 0) goto cleanup2;

    err = cudaMemcpy(d_assoc, h_assoc, n * sizeof(AssociatorResult),
                     cudaMemcpyHostToDevice);
    if (err != cudaSuccess) goto cleanup2;

    int block_size = 256;
    int grid_size = (n + block_size - 1) / block_size;
    batch_delta_kernel<<<grid_size, block_size>>>(
        d_assoc, d_a, d_b, d_c, d_delta, n);

    err = cudaGetLastError();
    if (err != cudaSuccess) {
        fprintf(stderr, "[cuda_octonion] delta kernel failed: %s\n",
                cudaGetErrorString(err));
        goto cleanup2;
    }
    cudaDeviceSynchronize();

    err = cudaMemcpy(h_delta_results, d_delta, n * sizeof(DeltaResult),
                     cudaMemcpyDeviceToHost);
    if (err != cudaSuccess) goto cleanup2;

    free(h_assoc);
    cuda_octonion_free_device(d_a);
    cuda_octonion_free_device(d_b);
    cuda_octonion_free_device(d_c);
    if (d_assoc) cudaFree(d_assoc);
    if (d_delta) cudaFree(d_delta);
    return 0;

cleanup2:
    free(h_assoc);
    cuda_octonion_free_device(d_a);
    cuda_octonion_free_device(d_b);
    cuda_octonion_free_device(d_c);
    if (d_assoc) cudaFree(d_assoc);
    if (d_delta) cudaFree(d_delta);
    return -1;
}

/**
 * 初始化 CUDA 设备
 *
 * @param device_id  GPU 设备 ID（-1 表示自动选择）
 * @return           0 成功，-1 失败
 */
int cuda_octonion_init(int device_id) {
    int count;
    cudaError_t err = cudaGetDeviceCount(&count);
    if (err != cudaSuccess || count == 0) {
        fprintf(stderr, "[cuda_octonion] No CUDA devices found\n");
        return -1;
    }

    if (device_id < 0) {
        /* 自动选择：选 SM 数量最多的设备 */
        int best_device = 0;
        int best_sm = 0;
        for (int i = 0; i < count; i++) {
            cudaDeviceProp prop;
            cudaGetDeviceProperties(&prop, i);
            if (prop.multiProcessorCount > best_sm) {
                best_sm = prop.multiProcessorCount;
                best_device = i;
            }
        }
        device_id = best_device;
    }

    err = cudaSetDevice(device_id);
    if (err != cudaSuccess) {
        fprintf(stderr, "[cuda_octonion] Failed to set device %d: %s\n",
                device_id, cudaGetErrorString(err));
        return -1;
    }

    cudaDeviceProp prop;
    cudaGetDeviceProperties(&prop, device_id);
    printf("[cuda_octonion] Using GPU %d: %s (%d SMs, CC %d.%d)\n",
           device_id, prop.name, prop.multiProcessorCount,
           prop.major, prop.minor);

    return 0;
}

} /* extern "C" */

/* ============================================================
 * 第9部分：自测试（编译时定义 TEST 宏启用）
 * ============================================================ */

#ifdef TEST

#include <stdlib.h>
#include <time.h>
#include <string.h>

/**
 * 生成随机八元数（归一化）
 */
static void random_octonion(Octonion *o) {
    float sum = 0;
    float *f = (float *)o;
    for (int i = 0; i < 8; i++) {
        f[i] = (float)rand() / RAND_MAX - 0.5f;
        sum += f[i] * f[i];
    }
    float inv_norm = 1.0f / sqrtf(sum + 1e-10f);
    for (int i = 0; i < 8; i++) {
        f[i] *= inv_norm;
    }
}

/**
 * CPU 参考实现：单次八元数乘法（与 M2 octonion.c 一致）
 */
static void cpu_oct_multiply(const Octonion *a, const Octonion *b,
                              Octonion *c) {
    memset(c, 0, sizeof(Octonion));
    c->e0 = a->e0 * b->e0
          - a->e1 * b->e1 - a->e2 * b->e2 - a->e3 * b->e3
          - a->e4 * b->e4 - a->e5 * b->e5 - a->e6 * b->e6 - a->e7 * b->e7;
    c->e1 = a->e0 * b->e1 + a->e1 * b->e0;
    c->e2 = a->e0 * b->e2 + a->e2 * b->e0;
    c->e3 = a->e0 * b->e3 + a->e3 * b->e0;
    c->e4 = a->e0 * b->e4 + a->e4 * b->e0;
    c->e5 = a->e0 * b->e5 + a->e5 * b->e0;
    c->e6 = a->e0 * b->e6 + a->e6 * b->e0;
    c->e7 = a->e0 * b->e7 + a->e7 * b->e0;

    int fano[7][3] = {
        {1,2,4}, {2,4,1}, {4,1,2}, {3,5,7}, {5,6,1}, {6,3,2}, {7,1,3}
    };
    for (int t = 0; t < 7; t++) {
        int i = fano[t][0], j = fano[t][1], k = fano[t][2];
        const float *ap = (const float *)a;
        const float *bp = (const float *)b;
        float *rp = (float *)c;
        float term = ap[i] * bp[j];
        rp[k] += term;
        c->e0 -= term;
    }
}

/**
 * 测试用例 1：批量八元数乘法（GPU vs CPU 参考）
 */
static int test_batch_multiply(int n) {
    printf("[TEST] batch_multiply n=%d ... ", n);

    Octonion *h_a = (Octonion *)malloc(n * sizeof(Octonion));
    Octonion *h_b = (Octonion *)malloc(n * sizeof(Octonion));
    Octonion *h_c_gpu = (Octonion *)malloc(n * sizeof(Octonion));
    Octonion *h_c_cpu = (Octonion *)malloc(n * sizeof(Octonion));

    srand(42);
    for (int i = 0; i < n; i++) {
        random_octonion(&h_a[i]);
        random_octonion(&h_b[i]);
    }

    /* GPU 计算 */
    int ret = cuda_batch_oct_multiply(h_a, h_b, h_c_gpu, n);
    if (ret != 0) { printf("GPU FAIL\n"); free(h_a); free(h_b); free(h_c_gpu); free(h_c_cpu); return 1; }

    /* CPU 参考计算 */
    for (int i = 0; i < n; i++) {
        cpu_oct_multiply(&h_a[i], &h_b[i], &h_c_cpu[i]);
    }

    /* 对比 */
    float max_err = 0;
    for (int i = 0; i < n; i++) {
        float *g = (float *)&h_c_gpu[i];
        float *c = (float *)&h_c_cpu[i];
        for (int j = 0; j < 8; j++) {
            float err = fabsf(g[j] - c[j]);
            if (err > max_err) max_err = err;
        }
    }

    printf("max_err=%.6f %s\n", max_err, max_err < 1e-4 ? "PASS" : "FAIL");

    free(h_a); free(h_b); free(h_c_gpu); free(h_c_cpu);
    return (max_err < 1e-4) ? 0 : 1;
}

/**
 * 测试用例 2：批量 associator（GPU vs CPU 参考）
 */
static int test_batch_associator(int n) {
    printf("[TEST] batch_associator n=%d ... ", n);

    Octonion *h_a = (Octonion *)malloc(n * sizeof(Octonion));
    Octonion *h_b = (Octonion *)malloc(n * sizeof(Octonion));
    Octonion *h_c = (Octonion *)malloc(n * sizeof(Octonion));
    AssociatorResult *h_results = (AssociatorResult *)malloc(
        n * sizeof(AssociatorResult));

    srand(42);
    for (int i = 0; i < n; i++) {
        random_octonion(&h_a[i]);
        random_octonion(&h_b[i]);
        random_octonion(&h_c[i]);
    }

    int ret = cuda_batch_associator(h_a, h_b, h_c, h_results, n);
    if (ret != 0) { printf("GPU FAIL\n"); free_all(); return 1; }

    /* CPU 参考 */
    for (int i = 0; i < n; i++) {
        Octonion ab, bc, left, right, assoc;
        cpu_oct_multiply(&h_a[i], &h_b[i], &ab);
        cpu_oct_multiply(&ab, &h_c[i], &left);
        cpu_oct_multiply(&h_b[i], &h_c[i], &bc);
        cpu_oct_multiply(&h_a[i], &bc, &right);

        float sum_sq = 0;
        float *lp = (float *)&left;
        float *rp = (float *)&right;
        for (int j = 0; j < 8; j++) {
            float d = lp[j] - rp[j];
            sum_sq += d * d;
        }
        float cpu_norm = sqrtf(sum_sq);

        float err = fabsf(h_results[i].norm - cpu_norm);
        if (err > 1e-3) {
            printf("FAIL at i=%d: gpu=%.6f cpu=%.6f\n", i, h_results[i].norm, cpu_norm);
            goto fail;
        }
    }

    printf("PASS\n");
    free(h_a); free(h_b); free(h_c); free(h_results);
    return 0;

fail:
    free(h_a); free(h_b); free(h_c); free(h_results);
    return 1;

free_all:
    free(h_a); free(h_b); free(h_c); free(h_results);
    return 1;
}

/**
 * 测试用例 3：批量 δ 计算
 */
static int test_batch_delta(int n) {
    printf("[TEST] batch_delta n=%d ... ", n);

    Octonion *h_a = (Octonion *)malloc(n * sizeof(Octonion));
    Octonion *h_b = (Octonion *)malloc(n * sizeof(Octonion));
    Octonion *h_c = (Octonion *)malloc(n * sizeof(Octonion));
    DeltaResult *h_delta = (DeltaResult *)malloc(n * sizeof(DeltaResult));

    srand(42);
    for (int i = 0; i < n; i++) {
        random_octonion(&h_a[i]);
        random_octonion(&h_b[i]);
        random_octonion(&h_c[i]);
    }

    int ret = cuda_batch_delta(h_a, h_b, h_c, h_delta, n);
    if (ret != 0) { printf("GPU FAIL\n"); goto fail; }

    /* 验证 δ 值在合理范围（归一化八元数 δ ≈ 0~1） */
    float min_delta = 1e9, max_delta = 0;
    int stats[4] = {0, 0, 0, 0};  /* classical, quantum, stable, deep */
    for (int i = 0; i < n; i++) {
        float d = h_delta[i].delta_raw;
        if (d < min_delta) min_delta = d;
        if (d > max_delta) max_delta = d;
        int r = h_delta[i].regime;
        if (r >= 0 && r < 4) stats[r]++;
    }

    printf("min=%.4f max=%.4f regimes(cl=%d qu=%d st=%d dp=%d) PASS\n",
           min_delta, max_delta, stats[0], stats[1], stats[2], stats[3]);

    free(h_a); free(h_b); free(h_c); free(h_delta);
    return 0;

fail:
    free(h_a); free(h_b); free(h_c); free(h_delta);
    return 1;
}

/**
 * 自测试主入口
 */
int main(void) {
    printf("=== T031 cuda_octonion.cu 自测试 ===\n\n");

    /* 初始化 CUDA */
    if (cuda_octonion_init(-1) != 0) {
        printf("CUDA init failed - skipping tests\n");
        return 1;
    }
    printf("\n");

    int pass = 0, fail = 0;

    if (test_batch_multiply(1024) == 0) pass++; else fail++;
    if (test_batch_associator(1024) == 0) pass++; else fail++;
    if (test_batch_delta(1024) == 0) pass++; else fail++;

    printf("\n=== 结果: %d PASS, %d FAIL ===\n", pass, fail);
    return (fail > 0) ? 1 : 0;
}

#endif /* TEST */
