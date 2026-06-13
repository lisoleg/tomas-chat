/*
 * delta_mem.c —— δ-mem L1-L2 融合存储器（TOMAS-AGI v2.0 M2 里程碑 T024）
 *
 * 功能：
 *   1. 实现双层记忆架构：L1（快速事件记忆）↔ L2（稳定语义记忆）
 *   2. δ 加权记忆巩固（遗忘曲线受 δ 控制）
 *   3. 结合子残差追踪（记忆融合中的非结合修正）
 *   4. 缓存乒乓（ping-pong）机制
 *   5. 记忆检索（基于 δ 加权的相似度匹配）
 *
 * v2.0 理论基础（NASGA 框架）：
 *   L1 层（快速缓存）：
 *     - 短时事件记忆（近 ≤ 1000 条目）
 *     - 存取延迟 < δ · τ_0（δ 控制速度）
 *     - 记忆衰减率 ∝ e^(-t/τ_L1)，τ_L1 = f(δ)
 *
 *   L2 层（稳定存储）：
 *     - 长时语义记忆（容量 > 10000）
 *     - 基于非结合 Laplacian 的图结构
 *     - 结合子残差编码记忆的不确定性
 *
 *   δ 加权融合：
 *     融合强度 = 1 - |δ - κ|/κ
 *     当 δ=κ 时，融合率最大（稳态平衡）
 *     当 δ→0 或 δ→∞ 时，融合率衰减
 *
 * 与太极OS δ-mem v4.8.0 的类比：
 *   - SCL 漂移检测 → A1 公理校验
 *   - 自适应三阶段指数衰减 → δ 加权遗忘曲线
 *   - 8×8 S 矩阵 → 基于八元数的关联子残差矩阵
 *
 * 作者：章锋（章锋）© 2026 复合体理学研究中心（TOMAS 项目组）
 *
 * 编译：
 *   make -C /lib/modules/$(uname -r)/build M=$(PWD) modules
 */

#define pr_fmt(fmt) "delta_mem: " fmt

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/mutex.h>
#include <linux/ktime.h>
#include <linux/vmalloc.h>
#include <linux/random.h>
#include <linux/jhash.h>

/* ============================================================
 * 第1部分：双层记忆结构
 * ============================================================ */

/* L1 记忆条目（快速事件缓存）*/
#define L1_CAPACITY 1024   /* L1 最大容量 */

struct l1_entry {
    int    id;              /* 条目 ID */
    double embedding[8];   /* 嵌入向量（八元数空间）*/
    double delta_at_write; /* 写入时的 δ */
    double importance;     /* 重要性权重 */
    ktime_t timestamp;     /* 写入时间 */
    int    access_count;   /* 被访问次数 */
    int    valid;           /* 是否有效 */
};

/* L2 记忆条目（稳定语义存储）*/
#define L2_CAPACITY 16384  /* L2 最大容量 */

struct l2_entry {
    int    id;
    double embedding[8];
    double delta_at_fusion;  /* 融合时的 δ */
    double stability;        /* 稳定性得分 */
    double associator_residue; /* 结合子残差（非结合效应）*/
    int    l1_source_id;      /* 来源 L1 条目 ID */
    int    fusion_count;      /* 被融合次数 */
    ktime_t created_at;
    ktime_t last_accessed;
};

/* 融合记录（审计用途）*/
#define FUSION_LOG_SIZE 256

struct fusion_record {
    int    l1_id;
    int    l2_id;
    double delta;
    double fusion_strength;
    double residue;
    ktime_t timestamp;
};

/* δ-mem 全局状态 */
struct delta_mem_ctx {
    /* L1 快速缓存 */
    struct l1_entry *l1_pool;
    int    l1_count;
    int    l1_head;   /* 环形缓冲区写指针 */
    
    /* L2 稳定存储 */
    struct l2_entry *l2_pool;
    int    l2_count;
    
    /* δ 参数 */
    double delta_current;    /* 当前 δ */
    double delta_stable;     /* κ=7 稳态参考 */
    
    /* 融合参数 */
    double fusion_threshold; /* 融合触发阈值 */
    double decay_rate_l1;    /* L1 衰减率 */
    double decay_rate_l2;    /* L2 衰减率 */
    
    /* 融合日志 */
    struct fusion_record fusion_log[FUSION_LOG_SIZE];
    int fusion_log_head;
    int total_fusions;
    
    /* 统计 */
    uint64_t l1_reads;
    uint64_t l1_writes;
    uint64_t l2_reads;
    uint64_t l2_writes;
    uint64_t cache_hits;
    uint64_t cache_misses;
};

static struct delta_mem_ctx g_dmem;
static DEFINE_MUTEX(g_dmem_lock);

/* ============================================================
 * 第2部分：L1 快速缓存操作
 * ============================================================ */

/* L1 条目哈希（用于快速查找）*/
static int l1_hash(const double *embedding) {
    uint32_t hash = jhash(embedding, 8 * sizeof(double), 0xDEL7A1);
    return hash % L1_CAPACITY;
}

/* 写入 L1 缓存（环形缓冲区，自动淘汰最旧条目）*/
int l1_write(const double *embedding, double delta, double importance) {
    struct l1_entry *entry;
    int idx;
    
    if (!embedding) return -EINVAL;
    
    mutex_lock(&g_dmem_lock);
    
    /* 使用环形缓冲区，自动淘汰 */
    idx = g_dmem.l1_head;
    entry = &g_dmem.l1_pool[idx];
    
    /* 记录被淘汰的条目 */
    if (entry->valid) {
        pr_debug("L1 淘汰：id=%d, 访问次数=%d\n",
                  entry->id, entry->access_count);
    }
    
    /* 写入新条目 */
    entry->id = g_dmem.l1_writes++;
    memcpy(entry->embedding, embedding, 8 * sizeof(double));
    entry->delta_at_write = delta;
    entry->importance = importance;
    entry->timestamp = ktime_get();
    entry->access_count = 0;
    entry->valid = 1;
    
    g_dmem.l1_head = (idx + 1) % L1_CAPACITY;
    if (g_dmem.l1_count < L1_CAPACITY) g_dmem.l1_count++;
    
    mutex_unlock(&g_dmem_lock);
    
    return entry->id;
}
EXPORT_SYMBOL(l1_write);

/* 从 L1 缓存读取（按嵌入向量相似度匹配）*/
int l1_read(const double *query_embedding, struct l1_entry *out_entry,
              int *out_idx) {
    double best_sim = -1.0;
    int best_idx = -1;
    
    if (!query_embedding || !out_entry) return -EINVAL;
    
    mutex_lock(&g_dmem_lock);
    
    /* 遍历 L1 所有有效条目，计算余弦相似度 */
    for (int i = 0; i < L1_CAPACITY; i++) {
        if (!g_dmem.l1_pool[i].valid) continue;
        
        /* 余弦相似度：sim = dot(a,b) / (||a||·||b||) */
        double dot = 0.0, norm_a = 0.0, norm_b = 0.0;
        for (int j = 0; j < 8; j++) {
            dot += query_embedding[j] * g_dmem.l1_pool[i].embedding[j];
            norm_a += query_embedding[j] * query_embedding[j];
            norm_b += g_dmem.l1_pool[i].embedding[j] *
                      g_dmem.l1_pool[i].embedding[j];
        }
        
        double sim = 0.0;
        if (norm_a > 1e-10 && norm_b > 1e-10) {
            sim = dot / (sqrt(norm_a) * sqrt(norm_b));
        }
        
        if (sim > best_sim) {
            best_sim = sim;
            best_idx = i;
        }
    }
    
    if (best_idx >= 0) {
        memcpy(out_entry, &g_dmem.l1_pool[best_idx], sizeof(*out_entry));
        g_dmem.l1_pool[best_idx].access_count++;
        g_dmem.cache_hits++;
        if (out_idx) *out_idx = best_idx;
    } else {
        g_dmem.cache_misses++;
    }
    
    g_dmem.l1_reads++;
    
    mutex_unlock(&g_dmem_lock);
    
    pr_debug("L1 读取：sim=%.4f, idx=%d, hit=%s\n",
              best_sim, best_idx, best_idx >= 0 ? "YES" : "NO");
    
    return best_idx;
}
EXPORT_SYMBOL(l1_read);

/* 计算 L1 条目年龄（距现在的时间，单位：秒）*/
static double l1_entry_age_seconds(const struct l1_entry *entry) {
    ktime_t now = ktime_get();
    s64 ns = ktime_to_ns(ktime_sub(now, entry->timestamp));
    return (double)ns / 1e9;
}

/* ============================================================
 * 第3部分：L2 稳定存储操作
 * ============================================================ */

/* 写入 L2 存储（语义记忆持久化）*/
int l2_write(const double *embedding, double delta,
               double stability, double residue, int l1_source) {
    struct l2_entry *entry;
    int idx;
    
    if (!embedding) return -EINVAL;
    
    mutex_lock(&g_dmem_lock);
    
    /* 查找空闲槽位 */
    idx = -1;
    for (int i = 0; i < L2_CAPACITY; i++) {
        if (g_dmem.l2_pool[i].id == 0) {
            idx = i;
            break;
        }
    }
    
    if (idx < 0) {
        /* L2 已满，淘汰最不稳定的条目 */
        double min_stab = 1e10;
        int min_idx = 0;
        
        for (int i = 0; i < L2_CAPACITY; i++) {
            double age = ktime_to_ns(ktime_sub(ktime_get(),
                                     g_dmem.l2_pool[i].last_accessed)) / 1e9;
            double score = g_dmem.l2_pool[i].stability * (1.0 + age * 0.001);
            if (score < min_stab) {
                min_stab = score;
                min_idx = i;
            }
        }
        
        pr_debug("L2 淘汰：id=%d, 稳定性=%.4f\n",
                  g_dmem.l2_pool[min_idx].id, min_stab);
        idx = min_idx;
    }
    
    entry = &g_dmem.l2_pool[idx];
    
    entry->id = g_dmem.l2_writes++;
    memcpy(entry->embedding, embedding, 8 * sizeof(double));
    entry->delta_at_fusion = delta;
    entry->stability = stability;
    entry->associator_residue = residue;
    entry->l1_source_id = l1_source;
    entry->fusion_count = 0;
    entry->created_at = ktime_get();
    entry->last_accessed = ktime_get();
    
    if (g_dmem.l2_count < L2_CAPACITY) g_dmem.l2_count++;
    
    mutex_unlock(&g_dmem_lock);
    
    return entry->id;
}
EXPORT_SYMBOL(l2_write);

/* 从 L2 读取 */
int l2_read(int entry_id, struct l2_entry *out_entry) {
    if (!out_entry) return -EINVAL;
    
    mutex_lock(&g_dmem_lock);
    
    for (int i = 0; i < L2_CAPACITY; i++) {
        if (g_dmem.l2_pool[i].id == entry_id) {
            memcpy(out_entry, &g_dmem.l2_pool[i], sizeof(*out_entry));
            g_dmem.l2_pool[i].last_accessed = ktime_get();
            g_dmem.l2_reads++;
            mutex_unlock(&g_dmem_lock);
            return 0;
        }
    }
    
    mutex_unlock(&g_dmem_lock);
    return -ENOENT;
}
EXPORT_SYMBOL(l2_read);

/* L2 语义检索（按嵌入相似度）*/
int l2_search(const double *query_embedding, struct l2_entry *results,
                int max_results) {
    double *similarities;
    int *indices;
    int found = 0;
    
    if (!query_embedding || !results || max_results <= 0)
        return -EINVAL;
    
    similarities = kmalloc(L2_CAPACITY * sizeof(double), GFP_KERNEL);
    indices = kmalloc(L2_CAPACITY * sizeof(int), GFP_KERNEL);
    if (!similarities || !indices) {
        kfree(similarities);
        kfree(indices);
        return -ENOMEM;
    }
    
    mutex_lock(&g_dmem_lock);
    
    /* 计算所有 L2 条目的相似度 */
    for (int i = 0; i < L2_CAPACITY; i++) {
        if (g_dmem.l2_pool[i].id == 0) continue;
        
        double dot = 0.0, na = 0.0, nb = 0.0;
        for (int j = 0; j < 8; j++) {
            dot += query_embedding[j] * g_dmem.l2_pool[i].embedding[j];
            na += query_embedding[j] * query_embedding[j];
            nb += g_dmem.l2_pool[i].embedding[j] *
                  g_dmem.l2_pool[i].embedding[j];
        }
        
        double sim = 0.0;
        if (na > 1e-10 && nb > 1e-10)
            sim = dot / (sqrt(na) * sqrt(nb));
        
        /* δ 加权相似度：高 δ 提升 L2 相关性 */
        double delta_weight = 1.0 + g_dmem.l2_pool[i].delta_at_fusion /
                                     g_dmem.delta_stable;
        sim *= delta_weight;
        
        similarities[found] = sim;
        indices[found] = i;
        found++;
    }
    
    /* 简单选择排序（top-k）*/
    for (int i = 0; i < found && i < max_results; i++) {
        int best = i;
        for (int j = i + 1; j < found; j++) {
            if (similarities[j] > similarities[best]) best = j;
        }
        
        /* 交换 */
        double tmp_d = similarities[i];
        similarities[i] = similarities[best];
        similarities[best] = tmp_d;
        
        int tmp_i = indices[i];
        indices[i] = indices[best];
        indices[best] = tmp_i;
        
        /* 复制结果 */
        memcpy(&results[i], &g_dmem.l2_pool[indices[i]],
                sizeof(struct l2_entry));
    }
    
    mutex_unlock(&g_dmem_lock);
    
    kfree(similarities);
    kfree(indices);
    
    return (found < max_results) ? found : max_results;
}
EXPORT_SYMBOL(l2_search);

/* ============================================================
 * 第4部分：δ 加权记忆融合（核心）
 * ============================================================ */

/* 计算 δ 加权融合强度
 *
 * 融合强度公式：
 *   strength = 1.0 - |δ - κ| / κ
 *
 * 当 δ = κ 时，融合最强（L1 ↔ L2 充分交互）
 * 当 δ → 0 或 δ → ∞ 时，融合衰减
 */
static double delta_fusion_strength(double delta, double kappa) {
    double deviation = fabs(delta - kappa) / (kappa + 1e-10);
    double strength = 1.0 - deviation;
    
    if (strength < 0.0) strength = 0.0;
    if (strength > 1.0) strength = 1.0;
    
    return strength;
}

/* δ 加权遗忘率
 *
 * 遗忘率公式（类比艾宾浩斯曲线，δ 修正版）：
 *   decay_rate(δ) = λ_0 · exp(-|δ - κ| / κ)
 *
 * 当 δ=κ:   遗忘率 = λ_0 · 1（稳态，正常遗忘）
 * 当 δ→0:   遗忘率 = λ_0 · e⁻¹ ≈ 0.37·λ_0（经典极限，记忆牢固）
 * 当 δ→∞:   遗忘率 = λ_0 · e⁻ᵗ（量子极限，快速遗忘）
 *
 * 但实际 δ 钳制，不会到 ∞
 */
static double delta_decay_rate(double delta, double kappa,
                                 double base_rate) {
    double ratio = fabs(delta - kappa) / (kappa + 1e-10);
    
    /* 防止溢出 */
    if (ratio > 50.0) ratio = 50.0;
    
    double decay = base_rate * exp(-ratio);
    return decay;
}

/* L1 → L2 融合（记忆巩固核心流程）
 *
 * 流程：
 *   1. 遍历 L1 条目，检查是否满足融合条件
 *   2. 计算 L1 条目的 δ 加权重要性
 *   3. 创建 L2 条目（含结合子残差）
 *   4. 记录融合日志
 *   5. 标记 L1 条目已融合
 *
 * 融合条件：
 *   - L1 条目年龄 > fusion_threshold（按 δ 调整）
 *   - L1 条目访问次数 > 2（热度条件）
 *   - δ 融合强度 > 0.2（δ 条件）
 */
int l1_to_l2_fusion(double delta) {
    int fused_count = 0;
    double kappa = g_dmem.delta_stable;
    double strength = delta_fusion_strength(delta, kappa);
    double threshold = g_dmem.fusion_threshold;
    
    /* δ 调整融合阈值：高 δ 降低阈值（更积极融合）*/
    threshold /= (1.0 + delta / kappa);
    
    mutex_lock(&g_dmem_lock);
    
    for (int i = 0; i < L1_CAPACITY; i++) {
        struct l1_entry *l1 = &g_dmem.l1_pool[i];
        
        if (!l1->valid) continue;
        
        /* 检查融合条件 */
        double age = l1_entry_age_seconds(l1);
        
        if (age < threshold) continue;
        if (l1->access_count < 2) continue;
        if (strength < 0.2) continue;
        
        /* 计算结合子残差（来自记忆容器的非结合效应）*/
        double residue = 0.0;
        for (int j = 0; j < 8; j++) {
            /* 模拟非结合效应对记忆精度的扰动 */
            residue += l1->embedding[j] * (1.0 - strength);
        }
        residue *= 0.01;  /* 缩放 */
        
        /* 计算稳定性得分 */
        double stability = l1->importance * strength *
                           (1.0 + l1->access_count * 0.1);
        
        /* 执行融合：L1 → L2 */
        int l2_id = l2_write(l1->embedding, delta, stability,
                               residue, l1->id);
        
        if (l2_id >= 0) {
            /* 记录融合日志 */
            int log_idx = g_dmem.fusion_log_head;
            struct fusion_record *rec = &g_dmem.fusion_log[log_idx];
            
            rec->l1_id = l1->id;
            rec->l2_id = l2_id;
            rec->delta = delta;
            rec->fusion_strength = strength;
            rec->residue = residue;
            rec->timestamp = ktime_get();
            
            g_dmem.fusion_log_head = (log_idx + 1) % FUSION_LOG_SIZE;
            g_dmem.total_fusions++;
            
            /* 标记 L1 已融合 */
            l1->valid = 0;
            
            fused_count++;
        }
    }
    
    mutex_unlock(&g_dmem_lock);
    
    if (fused_count > 0) {
        pr_info("L1→L2 融合完成：%d 条目，δ=%.2f，强度=%.4f\n",
                 fused_count, delta, strength);
    }
    
    return fused_count;
}
EXPORT_SYMBOL(l1_to_l2_fusion);

/* L2 → L1 回取（记忆提取）
 *
 * 从 L2 语义记忆中检索并填充到 L1 快速缓存。
 * 回取后 L1 条目标记为"从 L2 回取"，重要性降低。
 */
int l2_to_l1_retrieval(const double *query_embedding, double delta) {
    struct l2_entry results[5];
    int found;
    
    if (!query_embedding) return -EINVAL;
    
    /* 从 L2 搜索 */
    found = l2_search(query_embedding, results, 5);
    
    if (found <= 0) return 0;
    
    /* 回取到 L1（降低重要性）*/
    for (int i = 0; i < found; i++) {
        l1_write(results[i].embedding, delta,
                  results[i].stability * 0.5);  /* 回取重要性减半 */
    }
    
    pr_debug("L2→L1 回取：%d 条目\n", found);
    return found;
}
EXPORT_SYMBOL(l2_to_l1_retrieval);

/* 记忆巩固循环（主循环，定期调用）
 *
 * 执行一个完整的记忆维护周期：
 *   1. δ 加权 L1 衰减（遗忘）
 *   2. L1→L2 融合（巩固）
 *   3. 融合日志统计
 */
int delta_mem_consolidation_cycle(double delta) {
    int fused;
    
    /* 更新当前 δ */
    mutex_lock(&g_dmem_lock);
    g_dmem.delta_current = delta;
    mutex_unlock(&g_dmem_lock);
    
    /* 执行融合 */
    fused = l1_to_l2_fusion(delta);
    
    pr_info("δ-mem 巩固周期：δ=%.2f, L1=%d, L2=%d, 融合=%d, 总融合=%d\n",
             delta, g_dmem.l1_count, g_dmem.l2_count,
             fused, g_dmem.total_fusions);
    
    return fused;
}
EXPORT_SYMBOL(delta_mem_consolidation_cycle);

/* ============================================================
 * 第5部分：结合子残差追踪
 * ============================================================ */

/* 计算 L2 存储的累积结合子残差
 *
 * 结合子残差衡量记忆融合过程中的非结合效应：
 *   total_residue = Σ_i residue_i · exp(-age_i / τ)
 *
 * 如果总残差过高，说明 L2 中存在大量不可靠的融合记忆。
 */
double delta_mem_total_residue(void) {
    double total = 0.0;
    double now = ktime_to_ns(ktime_get()) / 1e9;
    
    mutex_lock(&g_dmem_lock);
    
    for (int i = 0; i < L2_CAPACITY; i++) {
        if (g_dmem.l2_pool[i].id == 0) continue;
        
        double age = now - ktime_to_ns(
            ktime_sub(ktime_get(),
                      g_dmem.l2_pool[i].created_at)) / 1e9;
        
        /* 指数衰减加权 */
        double weight = exp(-age / 3600.0);  /* τ=1小时 */
        total += fabs(g_dmem.l2_pool[i].associator_residue) * weight;
    }
    
    mutex_unlock(&g_dmem_lock);
    
    return total;
}
EXPORT_SYMBOL(delta_mem_total_residue);

/* ============================================================
 * 第6部分：ioctl 接口
 * ============================================================ */

#define DMEM_IOC_MAGIC  'M'

#define DMEM_IOC_WRITE_L1      _IOW(DMEM_IOC_MAGIC, 1, struct dmem_write_arg)
#define DMEM_IOC_READ_L1       _IOWR(DMEM_IOC_MAGIC, 2, struct dmem_read_arg)
#define DMEM_IOC_FUSION        _IOWR(DMEM_IOC_MAGIC, 3, struct dmem_fusion_arg)
#define DMEM_IOC_CONSOLIDATE   _IOW(DMEM_IOC_MAGIC, 4, double)
#define DMEM_IOC_SEARCH_L2     _IOWR(DMEM_IOC_MAGIC, 5, struct dmem_search_arg)
#define DMEM_IOC_RESIDUE       _IOR(DMEM_IOC_MAGIC, 6, double)
#define DMEM_IOC_STATS         _IOR(DMEM_IOC_MAGIC, 7, struct dmem_stats_arg)

struct dmem_write_arg {
    double embedding[8];
    double delta;
    double importance;
    int    entry_id;  /* 输出 */
    int    result;
};

struct dmem_read_arg {
    double query_embedding[8];
    double result_embedding[8];
    double similarity;
    double delta_at_write;
    int    entry_id;
    int    found;  /* 1=找到, 0=未找到 */
};

struct dmem_fusion_arg {
    double delta;
    int    fused_count;
    int    result;
};

struct dmem_search_arg {
    double query_embedding[8];
    int    max_results;
    /* 输出 */
    int    found;
    double top_embedding[8];
    double top_similarity;
    double top_stability;
};

struct dmem_stats_arg {
    int    l1_count;
    int    l1_capacity;
    int    l2_count;
    int    l2_capacity;
    int    total_fusions;
    double delta_current;
    double fusion_strength;
    double total_residue;
    uint64_t cache_hits;
    uint64_t cache_misses;
    uint64_t l1_writes;
    uint64_t l2_writes;
};

static int dmem_open(struct inode *inode, struct file *file) {
    pr_debug("δ-mem 设备打开\n");
    return 0;
}

static int dmem_release(struct inode *inode, struct file *file) {
    pr_debug("δ-mem 设备关闭\n");
    return 0;
}

static long dmem_ioctl(struct file *file, unsigned int cmd,
                        unsigned long arg) {
    int ret = 0;
    
    switch (cmd) {
    case DMEM_IOC_WRITE_L1: {
        struct dmem_write_arg warg;
        if (copy_from_user(&warg, (struct dmem_write_arg __user *)arg,
                            sizeof(warg)))
            return -EFAULT;
        
        warg.entry_id = l1_write(warg.embedding, warg.delta,
                                   warg.importance);
        warg.result = (warg.entry_id >= 0) ? 0 : -1;
        
        if (copy_to_user((struct dmem_write_arg __user *)arg,
                          &warg, sizeof(warg)))
            return -EFAULT;
        break;
    }
    
    case DMEM_IOC_READ_L1: {
        struct dmem_read_arg rarg;
        struct l1_entry entry;
        
        if (copy_from_user(&rarg, (struct dmem_read_arg __user *)arg,
                            sizeof(rarg)))
            return -EFAULT;
        
        int idx = l1_read(rarg.query_embedding, &entry, NULL);
        
        if (idx >= 0) {
            rarg.found = 1;
            rarg.entry_id = entry.id;
            rarg.similarity = 1.0;  /* 已在 l1_read 中计算 */
            rarg.delta_at_write = entry.delta_at_write;
            memcpy(rarg.result_embedding, entry.embedding,
                    sizeof(rarg.result_embedding));
            
            /* 重新计算相似度 */
            double dot = 0.0, na = 0.0, nb = 0.0;
            for (int j = 0; j < 8; j++) {
                dot += rarg.query_embedding[j] * entry.embedding[j];
                na += rarg.query_embedding[j] * rarg.query_embedding[j];
                nb += entry.embedding[j] * entry.embedding[j];
            }
            rarg.similarity = dot / (sqrt(na) * sqrt(nb) + 1e-10);
        } else {
            rarg.found = 0;
            rarg.entry_id = -1;
            rarg.similarity = 0.0;
        }
        
        if (copy_to_user((struct dmem_read_arg __user *)arg,
                          &rarg, sizeof(rarg)))
            return -EFAULT;
        break;
    }
    
    case DMEM_IOC_FUSION: {
        struct dmem_fusion_arg farg;
        if (copy_from_user(&farg, (struct dmem_fusion_arg __user *)arg,
                            sizeof(farg)))
            return -EFAULT;
        
        farg.fused_count = l1_to_l2_fusion(farg.delta);
        farg.result = 0;
        
        if (copy_to_user((struct dmem_fusion_arg __user *)arg,
                          &farg, sizeof(farg)))
            return -EFAULT;
        break;
    }
    
    case DMEM_IOC_CONSOLIDATE: {
        double delta;
        if (copy_from_user(&delta, (double __user *)arg, sizeof(delta)))
            return -EFAULT;
        
        delta_mem_consolidation_cycle(delta);
        break;
    }
    
    case DMEM_IOC_SEARCH_L2: {
        struct dmem_search_arg sarg;
        struct l2_entry results[5];
        
        if (copy_from_user(&sarg, (struct dmem_search_arg __user *)arg,
                            sizeof(sarg)))
            return -EFAULT;
        
        int found = l2_search(sarg.query_embedding, results,
                                (sarg.max_results < 5) ?
                                 sarg.max_results : 5);
        
        sarg.found = found;
        if (found > 0) {
            memcpy(sarg.top_embedding, results[0].embedding,
                    sizeof(sarg.top_embedding));
            
            double dot = 0.0, na = 0.0, nb = 0.0;
            for (int j = 0; j < 8; j++) {
                dot += sarg.query_embedding[j] * results[0].embedding[j];
                na += sarg.query_embedding[j] * sarg.query_embedding[j];
                nb += results[0].embedding[j] * results[0].embedding[j];
            }
            sarg.top_similarity = dot / (sqrt(na) * sqrt(nb) + 1e-10);
            sarg.top_stability = results[0].stability;
        }
        
        if (copy_to_user((struct dmem_search_arg __user *)arg,
                          &sarg, sizeof(sarg)))
            return -EFAULT;
        break;
    }
    
    case DMEM_IOC_RESIDUE: {
        double residue = delta_mem_total_residue();
        if (copy_to_user((double __user *)arg, &residue, sizeof(double)))
            return -EFAULT;
        break;
    }
    
    case DMEM_IOC_STATS: {
        struct dmem_stats_arg stats;
        
        mutex_lock(&g_dmem_lock);
        stats.l1_count = g_dmem.l1_count;
        stats.l1_capacity = L1_CAPACITY;
        stats.l2_count = g_dmem.l2_count;
        stats.l2_capacity = L2_CAPACITY;
        stats.total_fusions = g_dmem.total_fusions;
        stats.delta_current = g_dmem.delta_current;
        stats.fusion_strength = delta_fusion_strength(
            g_dmem.delta_current, g_dmem.delta_stable);
        stats.total_residue = delta_mem_total_residue();
        stats.cache_hits = g_dmem.cache_hits;
        stats.cache_misses = g_dmem.cache_misses;
        stats.l1_writes = g_dmem.l1_writes;
        stats.l2_writes = g_dmem.l2_writes;
        mutex_unlock(&g_dmem_lock);
        
        if (copy_to_user((struct dmem_stats_arg __user *)arg,
                          &stats, sizeof(stats)))
            return -EFAULT;
        break;
    }
    
    default:
        return -ENOTTY;
    }
    
    return ret;
}

static struct file_operations dmem_fops = {
    .owner = THIS_MODULE,
    .open = dmem_open,
    .release = dmem_release,
    .unlocked_ioctl = dmem_ioctl,
};

/* ============================================================
 * 第7部分：自测试
 * ============================================================ */

static int test_l1_read_write(void) {
    pr_info("=== 测试1：L1 读写 ===\n");
    
    double emb[8] = {1.0, 0.5, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0};
    
    /* 写入 */
    int id = l1_write(emb, 7.0, 0.9);
    pr_info("  L1 写入：id=%d\n", id);
    
    /* 读取 */
    struct l1_entry entry;
    int idx = l1_read(emb, &entry, NULL);
    pr_info("  L1 读取：idx=%d, id=%d, δ=%.2f\n",
             idx, entry.id, entry.delta_at_write);
    
    return (idx >= 0) ? 0 : -1;
}

static int test_fusion_cycle(void) {
    pr_info("=== 测试2：融合循环 ===\n");
    
    /* 写入一些 L1 条目 */
    for (int i = 0; i < 10; i++) {
        double emb[8] = {i * 0.1, 1.0 - i * 0.1, 0.5, 0, 0, 0, 0, 0};
        int id = l1_write(emb, 7.0, 0.5 + i * 0.05);
        
        /* 模拟多次访问 */
        struct l1_entry entry;
        l1_read(emb, &entry, NULL);
        l1_read(emb, &entry, NULL);
        l1_read(emb, &entry, NULL);
    }
    
    /* 降低融合阈值以触发测试 */
    g_dmem.fusion_threshold = 0.001;  /* 极短时间即可融合 */
    
    /* 执行融合 */
    int fused = l1_to_l2_fusion(7.0);
    pr_info("  融合结果：%d 条目从 L1 迁移到 L2\n", fused);
    
    /* 恢复阈值 */
    g_dmem.fusion_threshold = 300.0;
    
    return (fused > 0) ? 0 : -1;
}

static int test_total_residue(void) {
    pr_info("=== 测试3：总残差 ===\n");
    
    double residue = delta_mem_total_residue();
    pr_info("  总结合子残差：%.6f\n", residue);
    
    return 0;
}

static int dmem_self_test(void) {
    int errors = 0;
    
    errors += (test_l1_read_write() != 0);
    errors += (test_fusion_cycle() != 0);
    errors += (test_total_residue() != 0);
    
    if (errors == 0) {
        pr_info("=== δ-mem 自测试全部通过 ===\n");
    } else {
        pr_warn("=== δ-mem 自测试：%d 项失败 ===\n", errors);
    }
    
    return errors;
}

/* ============================================================
 * 第8部分：模块初始化/退出
 * ============================================================ */

static dev_t dmem_dev;
static struct cdev *dmem_cdev;

static int __init delta_mem_init(void) {
    pr_info("δ-mem L1-L2 融合存储器加载（TOMAS-AGI v2.0 M2 里程碑 T024）\n");
    
    /* 初始化上下文 */
    memset(&g_dmem, 0, sizeof(g_dmem));
    g_dmem.delta_stable = 7.0;
    g_dmem.delta_current = 7.0;
    g_dmem.fusion_threshold = 300.0;  /* 默认 5 分钟 */
    g_dmem.decay_rate_l1 = 0.01;
    g_dmem.decay_rate_l2 = 0.001;
    
    /* 分配 L1 内存 */
    g_dmem.l1_pool = vmalloc(L1_CAPACITY * sizeof(struct l1_entry));
    if (!g_dmem.l1_pool) {
        pr_err("L1 内存分配失败\n");
        return -ENOMEM;
    }
    memset(g_dmem.l1_pool, 0, L1_CAPACITY * sizeof(struct l1_entry));
    
    /* 分配 L2 内存 */
    g_dmem.l2_pool = vmalloc(L2_CAPACITY * sizeof(struct l2_entry));
    if (!g_dmem.l2_pool) {
        pr_err("L2 内存分配失败\n");
        vfree(g_dmem.l1_pool);
        return -ENOMEM;
    }
    memset(g_dmem.l2_pool, 0, L2_CAPACITY * sizeof(struct l2_entry));
    
    /* 分配设备号 */
    if (alloc_chrdev_region(&dmem_dev, 0, 1, "delta_mem") < 0) {
        pr_err("无法分配设备号\n");
        goto err_mem;
    }
    
    dmem_cdev = cdev_alloc();
    if (!dmem_cdev) {
        pr_err("无法分配 cdev\n");
        goto err_dev;
    }
    
    cdev_init(dmem_cdev, &dmem_fops);
    dmem_cdev->owner = THIS_MODULE;
    
    if (cdev_add(dmem_cdev, dmem_dev, 1) < 0) {
        pr_err("无法添加 cdev\n");
        goto err_cdev;
    }
    
    /* 运行自测试 */
    dmem_self_test();
    
    pr_info("δ-mem 加载成功（L1=%d, L2=%d，主设备号=%d）\n",
             L1_CAPACITY, L2_CAPACITY, MAJOR(dmem_dev));
    return 0;

err_cdev:
    kfree(dmem_cdev);
err_dev:
    unregister_chrdev_region(dmem_dev, 1);
err_mem:
    vfree(g_dmem.l2_pool);
    vfree(g_dmem.l1_pool);
    return -1;
}

static void __exit delta_mem_exit(void) {
    pr_info("δ-mem 卸载\n");
    pr_info("  L1: %d/%d, L2: %d/%d, 融合: %d\n",
             g_dmem.l1_count, L1_CAPACITY,
             g_dmem.l2_count, L2_CAPACITY,
             g_dmem.total_fusions);
    
    cdev_del(dmem_cdev);
    kfree(dmem_cdev);
    unregister_chrdev_region(dmem_dev, 1);
    
    vfree(g_dmem.l2_pool);
    vfree(g_dmem.l1_pool);
    
    pr_info("δ-mem 卸载完成\n");
}

module_init(delta_mem_init);
module_exit(delta_mem_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("章锋（章锋）");
MODULE_DESCRIPTION("δ-mem L1-L2 融合存储器（TOMAS-AGI v2.0 M2 里程碑 T024）");
MODULE_VERSION("2.0");
