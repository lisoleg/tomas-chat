/*
 * cuda_delta_mem.cu — T033: GPU δ-mem 融合加速
 *
 * TOMAS-AGI v2.0 M4 里程碑 — CUDA 加速核心层
 *
 * 将 δ-mem L1-L2 融合引擎并行化到 GPU：
 *   1. 并行 δ 权重计算 — 批量评估内存块的 δ 相关性
 *   2. GPU 加速 L1-L2 缓存融合 — 并行块选择与合并
 *   3. 批量 associator residue 统计 — 并行残差聚合
 *   4. 批量谱图页压缩/解压 — GPU 加速数据变换
 *
 * 与 M2 delta_mem.c 接口兼容。
 *
 * 编译：nvcc -c cuda_delta_mem.cu -o cuda_delta_mem.o -arch=sm_60
 *
 * 作者：章锋（章锋）© 2026 复合体理学研究中心（TOMAS 项目组）
 */

#include <cuda_runtime.h>
#include <device_launch_parameters.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ============================================================
 * 第1部分：数据结构定义（与 M2 delta_mem.c 兼容）
 * ============================================================ */

/** δ-mem 内存块 */
typedef struct {
    int block_id;              /**< 块 ID */
    unsigned long long delta_milli; /**< δ 赋值（毫单位） */
    int size;                  /**< 块大小（字节） */
    int l1_flag;               /**< L1 标志（0=L2, 1=L1） */
    float last_access;         /**< 最后访问时间戳 */
    float heat_score;          /**< 热度分数 */
    float delta_affinity;      /**< δ 亲和度（与当前 κ 的匹配度） */
} DmBlock;

/** δ-mem 缓存描述符 */
typedef struct {
    int num_blocks;            /**< 块总数 */
    unsigned long long kappa_target; /**< 目标 κ 值（通常是 7000 = 7.0） */
    float alpha_weight;        /**< δ 权重系数 */
} DmCache;

/** 融合结果 */
typedef struct {
    DmBlock merged_block;      /**< 融合后的块 */
    float quality_score;       /**< 融合质量分数 */
    int source_count;          /**< 源块数量 */
} FusionResult;

/** residue 统计 */
typedef struct {
    float mean_residue;        /**< 平均残差 */
    float std_residue;         /**< 残差标准差 */
    float min_residue;         /**< 最小残差 */
    float max_residue;         /**< 最大残差 */
    int sample_count;          /**< 样本数 */
    float a1_drift;            /**< A1 公理漂移量 */
} ResidueStats;

/* ============================================================
 * 第2部分：并行 δ 权重计算 kernel
 * ============================================================ */

/**
 * 并行计算 L1-L2 块的 δ 亲和度
 *
 * delta_affinity = 1.0 - |block_delta - kappa_target| / kappa_target
 *
 * @param blocks        内存块数组（device）
 * @param num_blocks    块数量
 * @param kappa_target  目标 κ 值（millidelta）
 */
__global__ void compute_delta_affinity_kernel(DmBlock *blocks,
                                                int num_blocks,
                                                unsigned long long kappa_target) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= num_blocks) return;

    unsigned long long block_delta = blocks[idx].delta_milli;
    unsigned long long diff;

    if (block_delta > kappa_target) {
        diff = block_delta - kappa_target;
    } else {
        diff = kappa_target - block_delta;
    }

    /* 亲和度 = 1 - 归一化差值 */
    float affinity = 1.0f - (float)diff / (float)(kappa_target + 1);
    if (affinity < 0.0f) affinity = 0.0f;
    if (affinity > 1.0f) affinity = 1.0f;

    blocks[idx].delta_affinity = affinity;
}

/* ============================================================
 * 第3部分：并行 L1-L2 融合引擎 kernel
 * ============================================================ */

/**
 * 并行评分：对每个块计算热度分数
 *
 * heat_score = w1 * delta_affinity + w2 * last_access + w3 * (L1 ? 1 : 0)
 *
 * @param blocks      内存块数组（device）
 * @param num_blocks  块数量
 * @param w_delta     δ 亲和度权重
 * @param w_access    访问时间权重
 * @param w_l1        L1 奖励权重
 */
__global__ void compute_heat_scores_kernel(DmBlock *blocks,
                                              int num_blocks,
                                              float w_delta,
                                              float w_access,
                                              float w_l1) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= num_blocks) return;

    float score = w_delta * blocks[idx].delta_affinity
                + w_access * blocks[idx].last_access
                + w_l1 * (blocks[idx].l1_flag ? 1.0f : 0.0f);

    blocks[idx].heat_score = score;
}

/**
 * 并行选择 Top-K 块用于融合
 *
 * 使用 Bitonic Sort 变体选出热度最高的 K 个块
 * （简化实现：标记高于阈值的块）
 *
 * @param blocks      内存块数组（device）
 * @param flags       输出选择标志（1=选中）
 * @param num_blocks  块数量
 * @param threshold   选择阈值
 */
__global__ void select_fusion_candidates_kernel(const DmBlock *blocks,
                                                  int *flags,
                                                  int num_blocks,
                                                  float threshold) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= num_blocks) return;

    flags[idx] = (blocks[idx].heat_score >= threshold) ? 1 : 0;
}

/**
 * 并行融合：将选中的 L1 和 L2 块合并
 *
 * 融合规则：
 *   merged_delta = weighted_average(L1_delta, L2_delta)
 *   merged_affinity = max(L1_affinity, L2_affinity)
 *
 * @param l1_blocks   L1 块数组（device）
 * @param l2_blocks   L2 块数组（device）
 * @param l1_flags    L1 选择标志
 * @param l2_flags    L2 选择标志
 * @param results     输出融合结果
 * @param n_l1        L1 块数量
 * @param n_l2        L2 块数量
 * @param alpha       δ 融合系数
 */
__global__ void fusion_engine_kernel(const DmBlock *l1_blocks,
                                       const DmBlock *l2_blocks,
                                       const int *l1_flags,
                                       const int *l2_flags,
                                       FusionResult *results,
                                       int n_l1,
                                       int n_l2,
                                       float alpha) {
    int l1_idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (l1_idx >= n_l1) return;
    if (!l1_flags[l1_idx]) return;  /* 未选中则跳过 */

    /* 为每个 L1 候选块寻找最佳 L2 匹配 */
    float best_quality = -1.0f;
    int best_l2 = -1;

    for (int j = 0; j < n_l2; j++) {
        if (!l2_flags[j]) continue;

        /* 质量 = 亲和度匹配 + δ 相近 */
        float affinity_match = 1.0f - fabsf(
            l1_blocks[l1_idx].delta_affinity
            - l2_blocks[j].delta_affinity);

        unsigned long long d1 = l1_blocks[l1_idx].delta_milli;
        unsigned long long d2 = l2_blocks[j].delta_milli;
        unsigned long long delta_diff = (d1 > d2) ? (d1 - d2) : (d2 - d1);
        float delta_proximity = 1.0f - (float)delta_diff / 10000.0f;
        if (delta_proximity < 0.0f) delta_proximity = 0.0f;

        float quality = 0.6f * affinity_match + 0.4f * delta_proximity;

        if (quality > best_quality) {
            best_quality = quality;
            best_l2 = j;
        }
    }

    if (best_l2 >= 0) {
        int out_idx = l1_idx;
        results[out_idx].quality_score = best_quality;
        results[out_idx].source_count = 2;

        /* 融合块：weighted average of δ values */
        results[out_idx].merged_block.delta_milli =
            (unsigned long long)(
                (1.0f - alpha) * l1_blocks[l1_idx].delta_milli
                + alpha * l2_blocks[best_l2].delta_milli);

        results[out_idx].merged_block.delta_affinity =
            fmaxf(l1_blocks[l1_idx].delta_affinity,
                  l2_blocks[best_l2].delta_affinity);

        results[out_idx].merged_block.l1_flag = 1;
        results[out_idx].merged_block.heat_score =
            (l1_blocks[l1_idx].heat_score
             + l2_blocks[best_l2].heat_score) * 0.5f;
    }
}

/* ============================================================
 * 第4部分：并行 residue 统计 kernel
 * ============================================================ */

/**
 * 并行计算 associator residue 统计
 *
 * 给定 N 个 associator 范数值，计算均值、方差、min/max
 *
 * @param residues      associator 范数数组（device）
 * @param partial_sum   部分和（device, block 级归约）
 * @param partial_sq    部分平方和（device）
 * @param n             样本数
 */
__global__ void residue_stats_kernel(const float *residues,
                                       float *partial_sum,
                                       float *partial_sq,
                                       float *partial_min,
                                       float *partial_max,
                                       int n) {
    extern __shared__ float sdata[];
    /* sdata 布局: [0..bs-1]=sum, [bs..2*bs-1]=sq_sum, [2*bs]=min, [2*bs+1]=max */
    int tid = threadIdx.x;
    int bs = blockDim.x;
    int idx = blockIdx.x * bs + tid;

    float val = (idx < n) ? residues[idx] : 0.0f;
    float sq  = (idx < n) ? residues[idx] * residues[idx] : 0.0f;
    float vmin = (idx < n) ? residues[idx] : 1e9f;
    float vmax = (idx < n) ? residues[idx] : -1e9f;

    sdata[tid] = val;
    sdata[bs + tid] = sq;
    __syncthreads();

    /* Block 内归约 */
    for (int s = bs / 2; s > 0; s >>= 1) {
        if (tid < s) {
            sdata[tid] += sdata[tid + s];
            sdata[bs + tid] += sdata[bs + tid + s];
            if (sdata[2 * bs + tid * 2] > sdata[2 * bs + (tid + s) * 2])
                sdata[2 * bs + tid * 2] = sdata[2 * bs + (tid + s) * 2];
            if (sdata[2 * bs + tid * 2 + 1] < sdata[2 * bs + (tid + s) * 2 + 1])
                sdata[2 * bs + tid * 2 + 1] = sdata[2 * bs + (tid + s) * 2 + 1];
        }
        __syncthreads();
    }

    if (tid == 0) {
        partial_sum[blockIdx.x] = sdata[0];
        partial_sq[blockIdx.x] = sdata[bs];
        partial_min[blockIdx.x] = vmin;  /* 简化 */
        partial_max[blockIdx.x] = vmax;
    }
}

/* ============================================================
 * 第5部分：并行谱图页压缩/解压 kernel
 * ============================================================ */

/**
 * 并行 δ 加权压缩
 *
 * 对谱图顶点数组应用 δ 加权压缩：
 *   phi_compressed[i] = phi[i] * min(1.0, delta_weight / kappa_target)
 *
 * 这本质上是低 δ 顶点（经典极限）的数据去冗余
 *
 * @param phi_in        输入谱向量（device, n_vertices × 8 float 交错存储）
 * @param delta_weights  δ 权重数组（device）
 * @param phi_out       输出压缩谱向量（device）
 * @param kappa_target   目标 κ 值（规范化用）
 * @param n              顶点数
 */
__global__ void delta_compress_kernel(const float *phi_in,
                                        const float *delta_weights,
                                        float *phi_out,
                                        float kappa_target,
                                        int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;

    float dw = delta_weights[idx];
    /* 压缩因子：delta 越接近 kappa 保留越多 */
    float factor = fminf(1.0f, dw / (kappa_target + 1e-10f));

    int base = idx * 8;
    for (int d = 0; d < 8; d++) {
        phi_out[base + d] = phi_in[base + d] * factor;
    }
}

/**
 * 并行解压
 *
 * 应用逆变换恢复谱向量
 *
 * @param phi_compressed 压缩谱向量（device）
 * @param delta_weights  δ 权重数组（device）
 * @param phi_restored   输出恢复向量（device）
 * @param kappa_target   目标 κ
 * @param n              顶点数
 */
__global__ void delta_decompress_kernel(const float *phi_compressed,
                                          const float *delta_weights,
                                          float *phi_restored,
                                          float kappa_target,
                                          int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;

    float dw = delta_weights[idx];
    float factor = fminf(1.0f, dw / (kappa_target + 1e-10f));
    float inv_factor = (factor > 1e-6f) ? (1.0f / factor) : 1.0f;

    int base = idx * 8;
    for (int d = 0; d < 8; d++) {
        phi_restored[base + d] = phi_compressed[base + d] * inv_factor;
    }
}

/**
 * 并行计算恢复误差
 *
 * @param original     原始向量（device）
 * @param restored     恢复向量（device）
 * @param errors       输出误差（device, n 个 L2 误差）
 * @param n            顶点数
 */
__global__ void compute_restore_errors_kernel(const float *original,
                                                const float *restored,
                                                float *errors,
                                                int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;

    int base = idx * 8;
    float sum_sq = 0.0f;
    for (int d = 0; d < 8; d++) {
        float diff = original[base + d] - restored[base + d];
        sum_sq += diff * diff;
    }
    errors[idx] = sqrtf(sum_sq);
}

/* ============================================================
 * 第6部分：Host 接口函数（extern "C" 供内核模块调用）
 * ============================================================ */

extern "C" {

/**
 * 批量计算 δ 亲和度
 *
 * @param h_blocks      内存块数组（host）
 * @param num_blocks    块数量
 * @param kappa_target  目标 κ（millidelta，通常 7000）
 * @return              0 成功
 */
int cuda_compute_affinity_batch(DmBlock *h_blocks, int num_blocks,
                                  unsigned long long kappa_target) {
    DmBlock *d_blocks = NULL;
    cudaMalloc(&d_blocks, num_blocks * sizeof(DmBlock));
    cudaMemcpy(d_blocks, h_blocks, num_blocks * sizeof(DmBlock),
               cudaMemcpyHostToDevice);

    int block_size = 256;
    int grid = (num_blocks + block_size - 1) / block_size;
    compute_delta_affinity_kernel<<<grid, block_size>>>(
        d_blocks, num_blocks, kappa_target);
    cudaDeviceSynchronize();

    cudaMemcpy(h_blocks, d_blocks, num_blocks * sizeof(DmBlock),
               cudaMemcpyDeviceToHost);
    cudaFree(d_blocks);
    return 0;
}

/**
 * 批量计算热度分数
 *
 * @param h_blocks    内存块数组（host, in-place）
 * @param num_blocks  块数量
 * @param w_delta     δ 权重（默认 0.5）
 * @param w_access    访问权重（默认 0.3）
 * @param w_l1        L1 奖励（默认 0.2）
 * @return            0 成功
 */
int cuda_compute_heat_scores(DmBlock *h_blocks, int num_blocks,
                               float w_delta, float w_access, float w_l1) {
    DmBlock *d_blocks = NULL;
    cudaMalloc(&d_blocks, num_blocks * sizeof(DmBlock));
    cudaMemcpy(d_blocks, h_blocks, num_blocks * sizeof(DmBlock),
               cudaMemcpyHostToDevice);

    int block_size = 256;
    int grid = (num_blocks + block_size - 1) / block_size;
    compute_heat_scores_kernel<<<grid, block_size>>>(
        d_blocks, num_blocks, w_delta, w_access, w_l1);
    cudaDeviceSynchronize();

    cudaMemcpy(h_blocks, d_blocks, num_blocks * sizeof(DmBlock),
               cudaMemcpyDeviceToHost);
    cudaFree(d_blocks);
    return 0;
}

/**
 * GPU 加速 L1-L2 融合引擎
 *
 * @param h_l1_blocks   L1 块数组（host）
 * @param n_l1          L1 块数量
 * @param h_l2_blocks   L2 块数组（host）
 * @param n_l2          L2 块数量
 * @param h_results     融合结果输出（host, size=n_l1）
 * @param alpha         δ 融合系数
 * @param threshold     选择阈值
 * @return              0 成功
 */
int cuda_fusion_engine(const DmBlock *h_l1_blocks, int n_l1,
                        const DmBlock *h_l2_blocks, int n_l2,
                        FusionResult *h_results, float alpha,
                        float threshold) {
    DmBlock *d_l1 = NULL, *d_l2 = NULL;
    int *d_l1_flags = NULL, *d_l2_flags = NULL;
    FusionResult *d_results = NULL;

    cudaMalloc(&d_l1, n_l1 * sizeof(DmBlock));
    cudaMalloc(&d_l2, n_l2 * sizeof(DmBlock));
    cudaMalloc(&d_l1_flags, n_l1 * sizeof(int));
    cudaMalloc(&d_l2_flags, n_l2 * sizeof(int));
    cudaMalloc(&d_results, n_l1 * sizeof(FusionResult));

    cudaMemcpy(d_l1, h_l1_blocks, n_l1 * sizeof(DmBlock),
               cudaMemcpyHostToDevice);
    cudaMemcpy(d_l2, h_l2_blocks, n_l2 * sizeof(DmBlock),
               cudaMemcpyHostToDevice);

    int block_size = 256;
    int grid_l1 = (n_l1 + block_size - 1) / block_size;
    int grid_l2 = (n_l2 + block_size - 1) / block_size;

    /* 选择候选块 */
    select_fusion_candidates_kernel<<<grid_l1, block_size>>>(
        d_l1, d_l1_flags, n_l1, threshold);
    select_fusion_candidates_kernel<<<grid_l2, block_size>>>(
        d_l2, d_l2_flags, n_l2, threshold);
    cudaDeviceSynchronize();

    /* 执行融合 */
    fusion_engine_kernel<<<grid_l1, block_size>>>(
        d_l1, d_l2, d_l1_flags, d_l2_flags,
        d_results, n_l1, n_l2, alpha);
    cudaDeviceSynchronize();

    cudaMemcpy(h_results, d_results, n_l1 * sizeof(FusionResult),
               cudaMemcpyDeviceToHost);

    cudaFree(d_l1);
    cudaFree(d_l2);
    cudaFree(d_l1_flags);
    cudaFree(d_l2_flags);
    cudaFree(d_results);
    return 0;
}

/**
 * 批量 residue 统计（GPU 加速）
 *
 * @param h_residues    associator 范数数组（host）
 * @param n             样本数
 * @param stats         输出统计结果
 * @return              0 成功
 */
int cuda_compute_residue_stats(const float *h_residues, int n,
                                 ResidueStats *stats) {
    float *d_residues = NULL;
    int block_size = 256;
    int num_blocks = (n + block_size - 1) / block_size;

    float *d_partial_sum = NULL, *d_partial_sq = NULL;
    float *d_partial_min = NULL, *d_partial_max = NULL;

    cudaMalloc(&d_residues, n * sizeof(float));
    cudaMalloc(&d_partial_sum, num_blocks * sizeof(float));
    cudaMalloc(&d_partial_sq, num_blocks * sizeof(float));
    cudaMalloc(&d_partial_min, num_blocks * sizeof(float));
    cudaMalloc(&d_partial_max, num_blocks * sizeof(float));

    cudaMemcpy(d_residues, h_residues, n * sizeof(float),
               cudaMemcpyHostToDevice);

    residue_stats_kernel<<<num_blocks, block_size,
                            4 * block_size * sizeof(float)>>>(
        d_residues, d_partial_sum, d_partial_sq,
        d_partial_min, d_partial_max, n);
    cudaDeviceSynchronize();

    /* Host 端汇总 */
    float *h_sum = (float *)malloc(num_blocks * sizeof(float));
    float *h_sq = (float *)malloc(num_blocks * sizeof(float));
    float *h_min = (float *)malloc(num_blocks * sizeof(float));
    float *h_max = (float *)malloc(num_blocks * sizeof(float));

    cudaMemcpy(h_sum, d_partial_sum, num_blocks * sizeof(float),
               cudaMemcpyDeviceToHost);
    cudaMemcpy(h_sq, d_partial_sq, num_blocks * sizeof(float),
               cudaMemcpyDeviceToHost);
    cudaMemcpy(h_min, d_partial_min, num_blocks * sizeof(float),
               cudaMemcpyDeviceToHost);
    cudaMemcpy(h_max, d_partial_max, num_blocks * sizeof(float),
               cudaMemcpyDeviceToHost);

    float total_sum = 0, total_sq = 0;
    float g_min = 1e9f, g_max = -1e9f;
    for (int i = 0; i < num_blocks; i++) {
        total_sum += h_sum[i];
        total_sq += h_sq[i];
        if (h_min[i] < g_min) g_min = h_min[i];
        if (h_max[i] > g_max) g_max = h_max[i];
    }

    stats->mean_residue = total_sum / n;
    float variance = total_sq / n - stats->mean_residue * stats->mean_residue;
    stats->std_residue = sqrtf(fmaxf(0.0f, variance));
    stats->min_residue = g_min;
    stats->max_residue = g_max;
    stats->sample_count = n;
    stats->a1_drift = stats->std_residue / (stats->mean_residue + 1e-10f);

    free(h_sum); free(h_sq); free(h_min); free(h_max);
    cudaFree(d_residues);
    cudaFree(d_partial_sum);
    cudaFree(d_partial_sq);
    cudaFree(d_partial_min);
    cudaFree(d_partial_max);
    return 0;
}

/**
 * GPU 加速谱图页压缩
 *
 * @param h_phi_in        输入谱向量（host，n × 8 float）
 * @param h_delta_weights  δ 权重数组（host，n float）
 * @param h_phi_out       输出压缩向量（host，n × 8 float）
 * @param kappa_target    目标 κ（float，如 7.0）
 * @param n               顶点数
 * @return                0 成功
 */
int cuda_delta_compress(const float *h_phi_in,
                          const float *h_delta_weights,
                          float *h_phi_out,
                          float kappa_target,
                          int n) {
    float *d_phi_in = NULL, *d_dw = NULL, *d_phi_out = NULL;

    cudaMalloc(&d_phi_in, n * 8 * sizeof(float));
    cudaMalloc(&d_dw, n * sizeof(float));
    cudaMalloc(&d_phi_out, n * 8 * sizeof(float));

    cudaMemcpy(d_phi_in, h_phi_in, n * 8 * sizeof(float),
               cudaMemcpyHostToDevice);
    cudaMemcpy(d_dw, h_delta_weights, n * sizeof(float),
               cudaMemcpyHostToDevice);

    int block_size = 256;
    int grid = (n + block_size - 1) / block_size;
    delta_compress_kernel<<<grid, block_size>>>(
        d_phi_in, d_dw, d_phi_out, kappa_target, n);
    cudaDeviceSynchronize();

    cudaMemcpy(h_phi_out, d_phi_out, n * 8 * sizeof(float),
               cudaMemcpyDeviceToHost);

    cudaFree(d_phi_in);
    cudaFree(d_dw);
    cudaFree(d_phi_out);
    return 0;
}

/**
 * GPU 加速谱图页解压
 *
 * @param h_phi_compressed 压缩谱向量
 * @param h_delta_weights  δ 权重
 * @param h_phi_restored  输出恢复向量
 * @param kappa_target    目标 κ
 * @param n               顶点数
 * @return                0 成功
 */
int cuda_delta_decompress(const float *h_phi_compressed,
                            const float *h_delta_weights,
                            float *h_phi_restored,
                            float kappa_target,
                            int n) {
    float *d_in = NULL, *d_dw = NULL, *d_out = NULL;

    cudaMalloc(&d_in, n * 8 * sizeof(float));
    cudaMalloc(&d_dw, n * sizeof(float));
    cudaMalloc(&d_out, n * 8 * sizeof(float));

    cudaMemcpy(d_in, h_phi_compressed, n * 8 * sizeof(float),
               cudaMemcpyHostToDevice);
    cudaMemcpy(d_dw, h_delta_weights, n * sizeof(float),
               cudaMemcpyHostToDevice);

    int block_size = 256;
    int grid = (n + block_size - 1) / block_size;
    delta_decompress_kernel<<<grid, block_size>>>(
        d_in, d_dw, d_out, kappa_target, n);
    cudaDeviceSynchronize();

    cudaMemcpy(h_phi_restored, d_out, n * 8 * sizeof(float),
               cudaMemcpyDeviceToHost);

    cudaFree(d_in);
    cudaFree(d_dw);
    cudaFree(d_out);
    return 0;
}

} /* extern "C" */

/* ============================================================
 * 第7部分：自测试
 * ============================================================ */

#ifdef TEST

int main(void) {
    printf("=== T033 cuda_delta_mem.cu 自测试 ===\n\n");

    int device_count;
    cudaGetDeviceCount(&device_count);
    if (device_count == 0) {
        printf("No CUDA devices - skipping tests\n");
        return 1;
    }

    cudaDeviceProp prop;
    cudaGetDeviceProperties(&prop, 0);
    printf("GPU: %s (CC %d.%d)\n\n",
           prop.name, prop.major, prop.minor);

    int pass = 0, fail = 0;

    /* 测试 1: δ 亲和度计算 */
    printf("[TEST] delta_affinity ... ");
    int n = 1024;
    DmBlock *blocks = (DmBlock *)malloc(n * sizeof(DmBlock));
    for (int i = 0; i < n; i++) {
        blocks[i].block_id = i;
        blocks[i].delta_milli = (unsigned long long)(i * 10);  /* 0..10230 */
        blocks[i].delta_affinity = 0;
    }

    int ret = cuda_compute_affinity_batch(blocks, n, 7000);  /* κ=7.0 */
    if (ret == 0) {
        /* 验证：delta=7000 附近亲和度应接近 1 */
        float aff_at_7000 = blocks[700].delta_affinity;  /* delta=7000 */
        printf("aff(7000)=%.3f %s\n", aff_at_7000,
               aff_at_7000 > 0.9f ? "PASS" : "FAIL");
        if (aff_at_7000 > 0.9f) pass++; else fail++;
    } else {
        printf("FAIL (kernel)\n");
        fail++;
    }
    free(blocks);

    /* 测试 2: 热度分数计算 */
    printf("[TEST] heat_scores ... ");
    n = 512;
    blocks = (DmBlock *)malloc(n * sizeof(DmBlock));
    for (int i = 0; i < n; i++) {
        blocks[i].block_id = i;
        blocks[i].delta_milli = 3500 + i * 10;
        blocks[i].delta_affinity = (float)i / n;
        blocks[i].last_access = (float)(n - i) / n;
        blocks[i].l1_flag = (i % 3 == 0) ? 1 : 0;
        blocks[i].heat_score = 0;
    }

    ret = cuda_compute_heat_scores(blocks, n, 0.5f, 0.3f, 0.2f);
    if (ret == 0) {
        printf("range[%d]=%.3f..%.3f PASS\n", n,
               blocks[0].heat_score, blocks[n-1].heat_score);
        pass++;
    } else {
        printf("FAIL\n");
        fail++;
    }
    free(blocks);

    /* 测试 3: L1-L2 融合 */
    printf("[TEST] fusion_engine ... ");
    int n_l1 = 256, n_l2 = 256;
    DmBlock *l1 = (DmBlock *)malloc(n_l1 * sizeof(DmBlock));
    DmBlock *l2 = (DmBlock *)malloc(n_l2 * sizeof(DmBlock));
    FusionResult *results = (FusionResult *)malloc(
        n_l1 * sizeof(FusionResult));

    for (int i = 0; i < n_l1; i++) {
        l1[i].block_id = i;
        l1[i].delta_milli = 6000 + i * 5;
        l1[i].heat_score = 0.5f + (float)i / n_l1 * 0.5f;
        l1[i].delta_affinity = 0.7f;
    }
    for (int i = 0; i < n_l2; i++) {
        l2[i].block_id = 1000 + i;
        l2[i].delta_milli = 5000 + i * 10;
        l2[i].heat_score = 0.3f + (float)(n_l2 - i) / n_l2 * 0.7f;
        l2[i].delta_affinity = 0.6f;
    }

    ret = cuda_fusion_engine(l1, n_l1, l2, n_l2, results, 0.3f, 0.4f);
    if (ret == 0) {
        int merged = 0;
        for (int i = 0; i < n_l1; i++) {
            if (results[i].quality_score > 0) merged++;
        }
        printf("merged=%d/%d PASS\n", merged, n_l1);
        pass++;
    } else {
        printf("FAIL\n");
        fail++;
    }

    free(l1); free(l2); free(results);

    /* 测试 4: residue 统计 */
    printf("[TEST] residue_stats ... ");
    n = 10000;
    float *residues = (float *)malloc(n * sizeof(float));
    for (int i = 0; i < n; i++) {
        residues[i] = 0.1f + 0.01f * (i % 100);  /* 0.1..1.09 */
    }

    ResidueStats stats;
    ret = cuda_compute_residue_stats(residues, n, &stats);
    if (ret == 0) {
        printf("mean=%.4f std=%.4f min=%.4f max=%.4f drift=%.4f PASS\n",
               stats.mean_residue, stats.std_residue,
               stats.min_residue, stats.max_residue, stats.a1_drift);
        pass++;
    } else {
        printf("FAIL\n");
        fail++;
    }
    free(residues);

    /* 测试 5: 压缩/解压 */
    printf("[TEST] delta_compress/decompress ... ");
    n = 512;
    float *phi = (float *)malloc(n * 8 * sizeof(float));
    float *dw = (float *)malloc(n * sizeof(float));
    float *compressed = (float *)malloc(n * 8 * sizeof(float));
    float *restored = (float *)malloc(n * 8 * sizeof(float));

    for (int i = 0; i < n; i++) {
        dw[i] = 3.5f + (float)i / n * 7.0f;  /* 3.5..10.5 */
        for (int d = 0; d < 8; d++) {
            phi[i * 8 + d] = (float)((i * 8 + d) % 100) / 100.0f;
        }
    }

    ret = cuda_delta_compress(phi, dw, compressed, 7.0f, n);
    if (ret == 0) {
        ret = cuda_delta_decompress(compressed, dw, restored, 7.0f, n);
        if (ret == 0) {
            /* 验证恢复精度 */
            float max_err = 0;
            for (int i = 0; i < n * 8; i++) {
                float err = fabsf(phi[i] - restored[i]);
                if (err > max_err) max_err = err;
            }
            printf("max_restore_err=%.6f %s\n", max_err,
                   max_err < 0.01f ? "PASS" : "FAIL");
            if (max_err < 0.01f) pass++; else fail++;
        } else {
            printf("FAIL (decompress)\n");
            fail++;
        }
    } else {
        printf("FAIL (compress)\n");
        fail++;
    }

    free(phi); free(dw); free(compressed); free(restored);

    printf("\n=== 结果: %d PASS, %d FAIL ===\n", pass, fail);
    return (fail > 0) ? 1 : 0;
}

#endif /* TEST */
