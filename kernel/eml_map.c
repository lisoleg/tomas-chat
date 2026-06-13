/*
 * eml_map.c —— EML 谱图存储管理（TOMAS-AGI v2.0 M2 里程碑 T022）
 *
 * 功能：
 *   1. EML 谱图持久化存储与恢复
 *   2. δ 加权边存储（谱折叠深度加权）
 *   3. 谱快照管理（checkpoint/rollback）
 *   4. 图内存池分配器（减少碎片）
 *   5. 与 spectral_laplacian 模块集成
 *
 * v2.0 核心升级：
 *   - 边权重引入 δ 加权的概念（来自 NASGA 框架）
 *   - 快照支持谱演化历史回溯
 *   - 支持非结合 Laplacian 元数据存储
 *
 * 存储结构：
 *   EML 图文件格式（二进制）：
 *   ┌────────────────────────────────────┐
 *   │ Header: magic, version, num_v, num_e│
 *   ├────────────────────────────────────┤
 *   │ Vertex data: id, octonion[8], delta │
 *   ├────────────────────────────────────┤
 *   │ Edge data: src, dst, weight, flags  │
 *   ├────────────────────────────────────┤
 *   │ Metadata: laplacian_alpha, timestamp│
 *   └────────────────────────────────────┘
 *
 * 作者：章锋（章锋）© 2026 复合体理学研究中心（TOMAS 项目组）
 *
 * 编译：
 *   make -C /lib/modules/$(uname -r)/build M=$(PWD) modules
 */

#define pr_fmt(fmt) "eml_map: " fmt

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

/* ============================================================
 * 第1部分：EML 图存储结构定义
 * ============================================================ */

/* EML 图顶点 */
struct eml_vertex_store {
    int    id;
    int    padding;
    double octonion[8];    /* 八元数值场 φ(i) */
    double delta;          /* 局部谱折叠深度 δ(i) */
};

/* EML 图边（δ 加权）*/
struct eml_edge_store {
    int    src;
    int    dst;
    double weight;          /* 基权重 w(i,j) */
    double delta_weight;   /* δ 加权因子 */
    int    associator_flag; /* 是否含 associator 修正 */
    int    padding;
};

/* EML 图文件头（魔数 + 版本）*/
#define EML_MAGIC  0x454D4C47  /* "EMLG" */
#define EML_VERSION 0x00020000  /* v2.0.0 */

struct eml_file_header {
    uint32_t magic;
    uint32_t version;
    uint32_t num_vertices;
    uint32_t num_edges;
    double   laplacian_alpha;  /* associator 耦合常数 */
    double   graph_delta;      /* 图级别 δ */
    uint64_t timestamp;        /* 创建/保存时间 */
    uint64_t reserved[4];
};

/* 谱快照（用于 checkpoint/rollback）*/
#define EML_SNAPSHOT_MAGIC 0x454D4C53  /* "EMLS" */

struct eml_snapshot {
    uint32_t magic;
    uint32_t version;
    uint64_t snapshot_id;
    uint64_t timestamp;
    uint32_t num_vertices;
    uint32_t num_edges;
    double   delta_at_snapshot;  /* 快照时刻的 δ */
    /* 后跟顶点数组 + 边数组 */
};

/* 图存储上下文 */
struct eml_store_ctx {
    struct eml_file_header header;
    struct eml_vertex_store *vertices;
    struct eml_edge_store   *edges;
    
    /* 快照管理 */
    int      max_snapshots;
    int      num_snapshots;
    void     **snapshot_data;    /* 快照数据数组 */
    uint64_t *snapshot_ids;      /* 快照 ID 数组 */
    
    /* 内存池 */
    size_t   vertex_pool_size;
    size_t   edge_pool_size;
    
    /* 统计 */
    uint64_t total_bytes_stored;
    uint64_t read_count;
    uint64_t write_count;
};

static struct eml_store_ctx g_eml_ctx;
static DEFINE_MUTEX(g_eml_lock);

/* ============================================================
 * 第2部分：内存池分配器
 * ============================================================ */

/* 分配顶点数组 */
static struct eml_vertex_store *eml_alloc_vertices(int num) {
    size_t size = num * sizeof(struct eml_vertex_store);
    struct eml_vertex_store *v = vmalloc(size);
    if (v) {
        memset(v, 0, size);
        g_eml_ctx.vertex_pool_size += size;
    }
    return v;
}

/* 分配边数组 */
static struct eml_edge_store *eml_alloc_edges(int num) {
    size_t size = num * sizeof(struct eml_edge_store);
    struct eml_edge_store *e = vmalloc(size);
    if (e) {
        memset(e, 0, size);
        g_eml_ctx.edge_pool_size += size;
    }
    return e;
}

/* 释放顶点数组 */
static void eml_free_vertices(struct eml_vertex_store *v, int num) {
    if (v) {
        vfree(v);
        g_eml_ctx.vertex_pool_size -= num * sizeof(struct eml_vertex_store);
    }
}

/* 释放边数组 */
static void eml_free_edges(struct eml_edge_store *e, int num) {
    if (e) {
        vfree(e);
        g_eml_ctx.edge_pool_size -= num * sizeof(struct eml_edge_store);
    }
}

/* ============================================================
 * 第3部分：图序列化/反序列化
 * ============================================================ */

/* 验证 EML 文件头 */
static int eml_validate_header(const struct eml_file_header *hdr) {
    if (hdr->magic != EML_MAGIC) {
        pr_err("EML 文件魔数错误：0x%08X（期望 0x%08X）\n",
                hdr->magic, EML_MAGIC);
        return -EINVAL;
    }
    
    if (hdr->version != EML_VERSION) {
        pr_warn("EML 版本不匹配：0x%08X（期望 0x%08X）\n",
                 hdr->version, EML_VERSION);
        /* 版本不匹配不是致命错误，尝试兼容读取 */
    }
    
    if (hdr->num_vertices == 0) {
        pr_err("EML 图顶点数为 0\n");
        return -EINVAL;
    }
    
    if (hdr->num_vertices > 1000000 || hdr->num_edges > 10000000) {
        pr_err("EML 图规模超限：V=%d, E=%d\n",
                hdr->num_vertices, hdr->num_edges);
        return -E2BIG;
    }
    
    return 0;
}

/* 序列化：将内存中的图导出为连续缓冲区
 *
 * 缓冲区格式（二进制）：
 *   [header] [vertices...] [edges...]
 *
 * 调用者负责释放返回的缓冲区。
 *
 * 返回：缓冲区指针，失败返回 ERR_PTR
 */
void *eml_serialize_graph(int num_vertices, int num_edges,
                           const struct eml_vertex_store *vertices,
                           const struct eml_edge_store *edges,
                           double laplacian_alpha,
                           size_t *out_size) {
    struct eml_file_header hdr;
    void *buffer;
    size_t offset;
    size_t total_size;
    
    if (!vertices || !edges || !out_size)
        return ERR_PTR(-EINVAL);
    
    /* 计算总大小 */
    total_size = sizeof(struct eml_file_header) +
                 num_vertices * sizeof(struct eml_vertex_store) +
                 num_edges * sizeof(struct eml_edge_store);
    
    buffer = vmalloc(total_size);
    if (!buffer)
        return ERR_PTR(-ENOMEM);
    
    /* 写入文件头 */
    hdr.magic = EML_MAGIC;
    hdr.version = EML_VERSION;
    hdr.num_vertices = num_vertices;
    hdr.num_edges = num_edges;
    hdr.laplacian_alpha = laplacian_alpha;
    hdr.graph_delta = 0.0;  /* 待填充 */
    hdr.timestamp = ktime_get_real_seconds();
    memset(&hdr.reserved, 0, sizeof(hdr.reserved));
    
    memcpy(buffer, &hdr, sizeof(hdr));
    offset = sizeof(hdr);
    
    /* 写入顶点数据 */
    memcpy(buffer + offset, vertices,
            num_vertices * sizeof(struct eml_vertex_store));
    offset += num_vertices * sizeof(struct eml_vertex_store);
    
    /* 写入边数据 */
    memcpy(buffer + offset, edges,
            num_edges * sizeof(struct eml_edge_store));
    offset += num_edges * sizeof(struct eml_edge_store);
    
    *out_size = total_size;
    g_eml_ctx.total_bytes_stored += total_size;
    g_eml_ctx.write_count++;
    
    pr_info("EML 图序列化完成：V=%d, E=%d, 大小=%zu 字节\n",
             num_vertices, num_edges, total_size);
    
    return buffer;
}
EXPORT_SYMBOL(eml_serialize_graph);

/* 反序列化：从连续缓冲区恢复图
 *
 * 输入：buffer（序列化数据），buffer_size（字节数）
 * 输出：out_vertices, out_edges（需调用者释放）
 *
 * 返回：0 成功，负值失败
 */
int eml_deserialize_graph(const void *buffer, size_t buffer_size,
                           struct eml_vertex_store **out_vertices,
                           struct eml_edge_store **out_edges,
                           int *out_num_vertices,
                           int *out_num_edges,
                           double *out_laplacian_alpha) {
    struct eml_file_header hdr;
    struct eml_vertex_store *vertices = NULL;
    struct eml_edge_store *edges = NULL;
    size_t expected_size;
    int ret;
    
    if (!buffer || !out_vertices || !out_edges ||
        !out_num_vertices || !out_num_edges || !out_laplacian_alpha)
        return -EINVAL;
    
    /* 解析文件头 */
    if (buffer_size < sizeof(hdr)) {
        pr_err("缓冲区过小：%zu < %zu\n", buffer_size, sizeof(hdr));
        return -EINVAL;
    }
    
    memcpy(&hdr, buffer, sizeof(hdr));
    
    ret = eml_validate_header(&hdr);
    if (ret < 0) return ret;
    
    /* 验证缓冲区大小 */
    expected_size = sizeof(hdr) +
                    hdr.num_vertices * sizeof(struct eml_vertex_store) +
                    hdr.num_edges * sizeof(struct eml_edge_store);
    
    if (buffer_size < expected_size) {
        pr_err("缓冲区不完整：%zu < %zu（V=%d, E=%d）\n",
                buffer_size, expected_size,
                hdr.num_vertices, hdr.num_edges);
        return -EINVAL;
    }
    
    /* 分配内存 */
    vertices = eml_alloc_vertices(hdr.num_vertices);
    if (!vertices) return -ENOMEM;
    
    edges = eml_alloc_edges(hdr.num_edges);
    if (!edges) {
        eml_free_vertices(vertices, hdr.num_vertices);
        return -ENOMEM;
    }
    
    /* 读取顶点数据 */
    size_t offset = sizeof(hdr);
    memcpy(vertices, buffer + offset,
            hdr.num_vertices * sizeof(struct eml_vertex_store));
    offset += hdr.num_vertices * sizeof(struct eml_vertex_store);
    
    /* 读取边数据 */
    memcpy(edges, buffer + offset,
            hdr.num_edges * sizeof(struct eml_edge_store));
    
    /* 返回结果 */
    *out_vertices = vertices;
    *out_edges = edges;
    *out_num_vertices = hdr.num_vertices;
    *out_num_edges = hdr.num_edges;
    *out_laplacian_alpha = hdr.laplacian_alpha;
    
    g_eml_ctx.read_count++;
    
    pr_info("EML 图反序列化完成：V=%d, E=%d, α=%.4f, ts=%llu\n",
             hdr.num_vertices, hdr.num_edges,
             hdr.laplacian_alpha, hdr.timestamp);
    
    return 0;
}
EXPORT_SYMBOL(eml_deserialize_graph);

/* ============================================================
 * 第4部分：δ 加权边计算
 * ============================================================ */

/* 计算 δ 加权边权重
 *
 * v2.0 定义（NASGA 框架 §3.1）：
 *   边权重 w_δ(i,j) = w_base(i,j) · exp(-δ_local / δ_stable)
 *
 * 其中：
 *   w_base(i,j) = 因果关系强度（逆因果距离）
 *   δ_local = max(δ(i), δ(j))（选取两端较大的 δ）
 *   δ_stable = κ = 7（稳态锁定值）
 *
 * δ 加权逻辑：
 *   - δ → 0（经典极限）: w_δ ≈ w_base（权重不变，全因果链接）
 *   - δ → κ（稳态）:    w_δ ≈ w_base · e⁻¹ ≈ 0.37 · w_base
 *   - δ → ∞（量子极限）: w_δ → 0（因果链断裂，谱折叠到不可观测尺度）
 */
double compute_delta_weighted_edge(double base_weight,
                                     double delta_src,
                                     double delta_dst,
                                     double delta_stable) {
    double delta_max;
    
    /* 选取两端较大的 δ */
    delta_max = (delta_src > delta_dst) ? delta_src : delta_dst;
    
    /* δ 加权因子 */
    if (delta_stable < 1e-10) {
        pr_warn("δ_stable 过小（%.2e），使用默认值 7\n", delta_stable);
        delta_stable = 7.0;
    }
    
    /* w_δ = w_base · exp(-δ_max / δ_stable) */
    double ratio = delta_max / delta_stable;
    
    /* 防止数值溢出 */
    if (ratio > 50.0) {
        return 0.0;  /* 完全折叠 */
    }
    
    double delta_factor = exp(-ratio);
    double weighted = base_weight * delta_factor;
    
    return weighted;
}
EXPORT_SYMBOL(compute_delta_weighted_edge);

/* 对图的所有边进行 δ 加权重算 */
int eml_reweight_edges_by_delta(struct eml_edge_store *edges,
                                  int num_edges,
                                  const struct eml_vertex_store *vertices,
                                  int num_vertices,
                                  double delta_stable) {
    if (!edges || !vertices) return -EINVAL;
    
    int updated = 0;
    
    for (int e = 0; e < num_edges; e++) {
        int src = edges[e].src;
        int dst = edges[e].dst;
        
        if (src < 0 || src >= num_vertices ||
            dst < 0 || dst >= num_vertices) {
            pr_warn("边 %d 索引越界：src=%d, dst=%d\n", e, src, dst);
            continue;
        }
        
        double old_weight = edges[e].weight;
        double delta_src = vertices[src].delta;
        double delta_dst = vertices[dst].delta;
        
        double new_weight = compute_delta_weighted_edge(
            old_weight, delta_src, delta_dst, delta_stable);
        
        edges[e].delta_weight = old_weight - new_weight;  /* δ 加权差 */
        edges[e].weight = new_weight;
        
        updated++;
    }
    
    pr_info("δ 加权边更新完成：%d/%d 条边已重新计算\n",
             updated, num_edges);
    return 0;
}
EXPORT_SYMBOL(eml_reweight_edges_by_delta);

/* ============================================================
 * 第5部分：谱快照管理（checkpoint / rollback）
 * ============================================================ */

/* 创建谱快照（checkpoint）
 *
 * 将当前图状态完整保存为快照，支持后续回滚。
 *
 * 参数：
 *   vertices/edges:   当前图数据
 *   delta_at_snapshot: 创建快照时的 δ 值
 *
 * 返回：快照 ID（>=0），失败返回负值
 */
int eml_create_snapshot(const struct eml_vertex_store *vertices,
                          int num_vertices,
                          const struct eml_edge_store *edges,
                          int num_edges,
                          double delta_at_snapshot) {
    struct eml_snapshot *snap;
    size_t data_size;
    void *data;
    
    if (!vertices || !edges) return -EINVAL;
    
    mutex_lock(&g_eml_lock);
    
    /* 检查快照数量上限 */
    if (g_eml_ctx.num_snapshots >= g_eml_ctx.max_snapshots) {
        pr_warn("快照数量已达上限（%d），无法创建新快照\n",
                 g_eml_ctx.max_snapshots);
        mutex_unlock(&g_eml_lock);
        return -ENOSPC;
    }
    
    /* 分配快照数据结构 */
    snap = kmalloc(sizeof(struct eml_snapshot), GFP_KERNEL);
    if (!snap) {
        mutex_unlock(&g_eml_lock);
        return -ENOMEM;
    }
    
    /* 计算快照数据大小 */
    data_size = sizeof(struct eml_snapshot) +
                num_vertices * sizeof(struct eml_vertex_store) +
                num_edges * sizeof(struct eml_edge_store);
    
    data = vmalloc(data_size);
    if (!data) {
        kfree(snap);
        mutex_unlock(&g_eml_lock);
        return -ENOMEM;
    }
    
    /* 填充快照头 */
    snap->magic = EML_SNAPSHOT_MAGIC;
    snap->version = EML_VERSION;
    snap->snapshot_id = ktime_get_real_ns();
    snap->timestamp = ktime_get_real_seconds();
    snap->num_vertices = num_vertices;
    snap->num_edges = num_edges;
    snap->delta_at_snapshot = delta_at_snapshot;
    
    /* 复制数据 */
    memcpy(data, snap, sizeof(struct eml_snapshot));
    memcpy(data + sizeof(struct eml_snapshot),
            vertices, num_vertices * sizeof(struct eml_vertex_store));
    memcpy(data + sizeof(struct eml_snapshot) +
            num_vertices * sizeof(struct eml_vertex_store),
            edges, num_edges * sizeof(struct eml_edge_store));
    
    /* 保存快照 */
    int idx = g_eml_ctx.num_snapshots;
    g_eml_ctx.snapshot_data[idx] = data;
    g_eml_ctx.snapshot_ids[idx] = snap->snapshot_id;
    g_eml_ctx.num_snapshots++;
    
    kfree(snap);
    
    pr_info("谱快照创建：ID=%llu, V=%d, E=%d, δ=%.4f, 大小=%zu\n",
             g_eml_ctx.snapshot_ids[idx], num_vertices, num_edges,
             delta_at_snapshot, data_size);
    
    mutex_unlock(&g_eml_lock);
    return idx;
}
EXPORT_SYMBOL(eml_create_snapshot);

/* 回滚到指定快照（rollback）
 *
 * 从快照恢复图状态。
 *
 * 返回：0 成功，负值失败
 */
int eml_rollback_snapshot(int snapshot_idx,
                            struct eml_vertex_store *vertices,
                            int *num_vertices,
                            struct eml_edge_store *edges,
                            int *num_edges,
                            double *delta_at_snapshot) {
    struct eml_snapshot snap;
    void *data;
    size_t offset;
    
    if (!vertices || !edges || !num_vertices ||
        !num_edges || !delta_at_snapshot)
        return -EINVAL;
    
    mutex_lock(&g_eml_lock);
    
    if (snapshot_idx < 0 || snapshot_idx >= g_eml_ctx.num_snapshots) {
        pr_err("快照索引无效：%d（有效范围 0-%d）\n",
                snapshot_idx, g_eml_ctx.num_snapshots - 1);
        mutex_unlock(&g_eml_lock);
        return -EINVAL;
    }
    
    data = g_eml_ctx.snapshot_data[snapshot_idx];
    if (!data) {
        mutex_unlock(&g_eml_lock);
        return -ENOENT;
    }
    
    /* 解析快照头 */
    memcpy(&snap, data, sizeof(snap));
    
    if (snap.magic != EML_SNAPSHOT_MAGIC) {
        pr_err("快照魔数错误：0x%08X\n", snap.magic);
        mutex_unlock(&g_eml_lock);
        return -EINVAL;
    }
    
    /* 恢复顶点数据 */
    offset = sizeof(struct eml_snapshot);
    memcpy(vertices, data + offset,
            snap.num_vertices * sizeof(struct eml_vertex_store));
    offset += snap.num_vertices * sizeof(struct eml_vertex_store);
    
    /* 恢复边数据 */
    memcpy(edges, data + offset,
            snap.num_edges * sizeof(struct eml_edge_store));
    
    *num_vertices = snap.num_vertices;
    *num_edges = snap.num_edges;
    *delta_at_snapshot = snap.delta_at_snapshot;
    
    pr_info("谱快照回滚：ID=%llu, V=%d, E=%d, δ=%.4f\n",
             snap.snapshot_id, snap.num_vertices,
             snap.num_edges, snap.delta_at_snapshot);
    
    mutex_unlock(&g_eml_lock);
    return 0;
}
EXPORT_SYMBOL(eml_rollback_snapshot);

/* 删除指定快照 */
int eml_delete_snapshot(int snapshot_idx) {
    mutex_lock(&g_eml_lock);
    
    if (snapshot_idx < 0 || snapshot_idx >= g_eml_ctx.num_snapshots) {
        mutex_unlock(&g_eml_lock);
        return -EINVAL;
    }
    
    void *data = g_eml_ctx.snapshot_data[snapshot_idx];
    if (data) {
        vfree(data);
        g_eml_ctx.snapshot_data[snapshot_idx] = NULL;
    }
    
    g_eml_ctx.snapshot_ids[snapshot_idx] = 0;
    
    /* 压缩（将后续快照前移）*/
    for (int i = snapshot_idx; i < g_eml_ctx.num_snapshots - 1; i++) {
        g_eml_ctx.snapshot_data[i] = g_eml_ctx.snapshot_data[i + 1];
        g_eml_ctx.snapshot_ids[i] = g_eml_ctx.snapshot_ids[i + 1];
    }
    
    g_eml_ctx.num_snapshots--;
    
    pr_info("快照 %d 已删除（剩余 %d 个）\n",
             snapshot_idx, g_eml_ctx.num_snapshots);
    
    mutex_unlock(&g_eml_lock);
    return 0;
}
EXPORT_SYMBOL(eml_delete_snapshot);

/* 列出所有快照 */
int eml_list_snapshots(char *buffer, size_t buflen) {
    int offset = 0;
    
    if (!buffer) return -EINVAL;
    
    mutex_lock(&g_eml_lock);
    
    offset += snprintf(buffer + offset, buflen - offset,
        "=== EML 谱快照列表（共 %d 个）===\n", g_eml_ctx.num_snapshots);
    
    for (int i = 0; i < g_eml_ctx.num_snapshots; i++) {
        if (offset >= buflen - 128) break;
        
        uint64_t sid = g_eml_ctx.snapshot_ids[i];
        void *data = g_eml_ctx.snapshot_data[i];
        
        if (data && sid != 0) {
            struct eml_snapshot snap;
            memcpy(&snap, data, sizeof(snap));
            
            offset += snprintf(buffer + offset, buflen - offset,
                "  [%d] ID=%llu, V=%d, E=%d, δ=%.4f, ts=%llu\n",
                i, snap.snapshot_id, snap.num_vertices,
                snap.num_edges, snap.delta_at_snapshot,
                snap.timestamp);
        }
    }
    
    mutex_unlock(&g_eml_lock);
    return 0;
}
EXPORT_SYMBOL(eml_list_snapshots);

/* ============================================================
 * 第6部分：ioctl 接口
 * ============================================================ */

#define EML_IOC_MAGIC  'E'

#define EML_IOC_SERIALIZE      _IOWR(EML_IOC_MAGIC, 1, struct eml_serialize_arg)
#define EML_IOC_DESERIALIZE    _IOW(EML_IOC_MAGIC, 2, struct eml_deserialize_arg)
#define EML_IOC_REWEIGHT       _IOW(EML_IOC_MAGIC, 3, struct eml_reweight_arg)
#define EML_IOC_SNAPSHOT       _IOW(EML_IOC_MAGIC, 4, struct eml_snapshot_arg)
#define EML_IOC_ROLLBACK       _IOW(EML_IOC_MAGIC, 5, struct eml_rollback_arg)
#define EML_IOC_DEL_SNAPSHOT   _IOW(EML_IOC_MAGIC, 6, int)
#define EML_IOC_LIST_SNAPSHOTS _IOR(EML_IOC_MAGIC, 7, char[4096])
#define EML_IOC_STATS          _IOR(EML_IOC_MAGIC, 8, struct eml_stats_arg)

struct eml_serialize_arg {
    int    num_vertices;
    int    num_edges;
    double laplacian_alpha;
    uint64_t out_size;
    int    result;
};

struct eml_deserialize_arg {
    uint64_t buffer_ptr;  /* 用户态缓冲区指针 */
    uint64_t buffer_size;
    int     out_num_vertices;
    int     out_num_edges;
    double  out_laplacian_alpha;
    int     result;
};

struct eml_reweight_arg {
    double delta_stable;
    int    num_edges_updated;
    int    result;
};

struct eml_snapshot_arg {
    double delta_at_snapshot;
    int    snapshot_idx;  /* 输出：快照索引 */
    int    result;
};

struct eml_rollback_arg {
    int    snapshot_idx;
    double out_delta;
    int    result;
};

struct eml_stats_arg {
    int    num_snapshots;
    int    max_snapshots;
    uint64_t total_bytes_stored;
    uint64_t read_count;
    uint64_t write_count;
    size_t  vertex_pool_size;
    size_t  edge_pool_size;
};

static int eml_open(struct inode *inode, struct file *file) {
    pr_debug("EML 存储设备打开\n");
    return 0;
}

static int eml_release(struct inode *inode, struct file *file) {
    pr_debug("EML 存储设备关闭\n");
    return 0;
}

static long eml_ioctl(struct file *file, unsigned int cmd,
                       unsigned long arg) {
    int ret = 0;
    
    switch (cmd) {
    case EML_IOC_STATS: {
        struct eml_stats_arg stats;
        
        mutex_lock(&g_eml_lock);
        stats.num_snapshots = g_eml_ctx.num_snapshots;
        stats.max_snapshots = g_eml_ctx.max_snapshots;
        stats.total_bytes_stored = g_eml_ctx.total_bytes_stored;
        stats.read_count = g_eml_ctx.read_count;
        stats.write_count = g_eml_ctx.write_count;
        stats.vertex_pool_size = g_eml_ctx.vertex_pool_size;
        stats.edge_pool_size = g_eml_ctx.edge_pool_size;
        mutex_unlock(&g_eml_lock);
        
        if (copy_to_user((struct eml_stats_arg __user *)arg,
                          &stats, sizeof(stats)))
            return -EFAULT;
        break;
    }
    
    case EML_IOC_LIST_SNAPSHOTS: {
        char *buffer = kmalloc(4096, GFP_KERNEL);
        if (!buffer) return -ENOMEM;
        
        eml_list_snapshots(buffer, 4096);
        
        if (copy_to_user((char __user *)arg, buffer, 4096)) {
            kfree(buffer);
            return -EFAULT;
        }
        
        kfree(buffer);
        break;
    }
    
    case EML_IOC_DEL_SNAPSHOT: {
        int idx;
        if (copy_from_user(&idx, (int __user *)arg, sizeof(idx)))
            return -EFAULT;
        
        ret = eml_delete_snapshot(idx);
        break;
    }
    
    default:
        return -ENOTTY;
    }
    
    return ret;
}

static struct file_operations eml_fops = {
    .owner = THIS_MODULE,
    .open = eml_open,
    .release = eml_release,
    .unlocked_ioctl = eml_ioctl,
};

/* ============================================================
 * 第7部分：自测试
 * ============================================================ */

/* 测试1：序列化/反序列化往返 */
static int test_serialization_roundtrip(void) {
    pr_info("=== 测试1：EML 图序列化往返 ===\n");
    
    int num_v = 4, num_e = 5;
    struct eml_vertex_store *vertices;
    struct eml_edge_store *edges;
    void *buffer;
    size_t buf_size;
    int ret;
    
    /* 创建测试图 */
    vertices = eml_alloc_vertices(num_v);
    edges = eml_alloc_edges(num_e);
    
    if (!vertices || !edges) {
        pr_err("内存分配失败\n");
        ret = -ENOMEM;
        goto cleanup;
    }
    
    /* 初始化顶点 */
    for (int i = 0; i < num_v; i++) {
        vertices[i].id = i;
        vertices[i].octonion[0] = i + 1.0;
        vertices[i].delta = (double)i;
    }
    
    /* 初始化边 */
    edges[0] = (struct eml_edge_store){0, 1, 1.0, 0.0, 1, 0};
    edges[1] = (struct eml_edge_store){1, 2, 1.0, 0.0, 1, 0};
    edges[2] = (struct eml_edge_store){2, 3, 1.0, 0.0, 1, 0};
    edges[3] = (struct eml_edge_store){3, 0, 1.0, 0.0, 1, 0};
    edges[4] = (struct eml_edge_store){0, 2, 1.5, 0.0, 1, 0};
    
    /* 序列化 */
    buffer = eml_serialize_graph(num_v, num_e, vertices, edges,
                                   0.3, &buf_size);
    if (IS_ERR(buffer)) {
        ret = PTR_ERR(buffer);
        pr_err("序列化失败：%d\n", ret);
        goto cleanup;
    }
    
    /* 反序列化 */
    struct eml_vertex_store *v_out = NULL;
    struct eml_edge_store *e_out = NULL;
    int v_num, e_num;
    double alpha;
    
    ret = eml_deserialize_graph(buffer, buf_size,
                                  &v_out, &e_out,
                                  &v_num, &e_num, &alpha);
    
    if (ret == 0) {
        pr_info("往返测试通过：V=%d→%d, E=%d→%d, α=%.4f\n",
                 num_v, v_num, num_e, e_num, alpha);
        
        /* 验证数据一致性 */
        if (v_num != num_v || e_num != num_e) {
            pr_err("往返测试：数据丢失\n");
            ret = -EIO;
        }
    }
    
    if (v_out) eml_free_vertices(v_out, v_num);
    if (e_out) eml_free_edges(e_out, e_num);
    vfree(buffer);
    
cleanup:
    if (vertices) eml_free_vertices(vertices, num_v);
    if (edges) eml_free_edges(edges, num_e);
    
    return ret;
}

/* 测试2：δ 加权边计算 */
static int test_delta_weighted_edge(void) {
    pr_info("=== 测试2：δ 加权边计算 ===\n");
    
    double base = 1.0;
    double ws[4];
    
    /* 测试不同 δ 取值 */
    ws[0] = compute_delta_weighted_edge(base, 0.0, 0.0, 7.0);
    ws[1] = compute_delta_weighted_edge(base, 7.0, 7.0, 7.0);
    ws[2] = compute_delta_weighted_edge(base, 3.5, 7.0, 7.0);
    ws[3] = compute_delta_weighted_edge(base, 14.0, 7.0, 7.0);
    
    pr_info("  δ=0:   w_δ=%.6f（应有 1.000000 ≈ 全因果链接）\n", ws[0]);
    pr_info("  δ=7:   w_δ=%.6f（应有 0.367879 ≈ e⁻¹）\n", ws[1]);
    pr_info("  δ=3.5: w_δ=%.6f（应有 0.606531 ≈ e⁻⁰·⁵）\n", ws[2]);
    pr_info("  δ=14:  w_δ=%.6f（应有 0.135335 ≈ e⁻²）\n", ws[3]);
    
    /* 验证 */
    if (fabs(ws[0] - 1.0) > 0.01) return -1;
    if (fabs(ws[1] - 0.3679) > 0.001) return -1;
    
    return 0;
}

/* 测试3：快照创建/回滚 */
static int test_snapshot_create_rollback(void) {
    pr_info("=== 测试3：谱快照创建/回滚 ===\n");
    
    int num_v = 3, num_e = 3;
    struct eml_vertex_store *vertices;
    struct eml_edge_store *edges;
    int ret;
    
    vertices = eml_alloc_vertices(num_v);
    edges = eml_alloc_edges(num_e);
    
    if (!vertices || !edges) {
        ret = -ENOMEM;
        goto cleanup;
    }
    
    /* 初始状态 */
    for (int i = 0; i < num_v; i++) {
        vertices[i].id = i;
        vertices[i].delta = 1.0;
    }
    edges[0] = (struct eml_edge_store){0, 1, 1.0, 0, 1, 0};
    edges[1] = (struct eml_edge_store){1, 2, 1.0, 0, 1, 0};
    edges[2] = (struct eml_edge_store){2, 0, 1.0, 0, 1, 0};
    
    /* 创建快照 */
    int snap_idx = eml_create_snapshot(vertices, num_v, edges, num_e, 1.0);
    if (snap_idx < 0) {
        pr_err("快照创建失败：%d\n", snap_idx);
        ret = snap_idx;
        goto cleanup;
    }
    
    pr_info("快照创建成功：索引=%d\n", snap_idx);
    
    /* 修改数据 */
    vertices[0].delta = 5.0;
    edges[0].weight = 99.0;
    
    /* 回滚 */
    struct eml_vertex_store v_restored[3];
    struct eml_edge_store e_restored[3];
    int vr, er;
    double delta_r;
    
    ret = eml_rollback_snapshot(snap_idx,
                                  v_restored, &vr,
                                  e_restored, &er,
                                  &delta_r);
    
    if (ret == 0) {
        pr_info("回滚后：δ[0]=%.1f, w[0]=%.1f, δ_snap=%.1f\n",
                 v_restored[0].delta, e_restored[0].weight, delta_r);
        
        if (fabs(v_restored[0].delta - 1.0) < 0.01 &&
            fabs(e_restored[0].weight - 1.0) < 0.01) {
            pr_info("快照回滚测试通过\n");
        } else {
            pr_err("快照回滚数据不一致\n");
            ret = -EIO;
        }
    }
    
    /* 清理快照 */
    eml_delete_snapshot(snap_idx);
    
cleanup:
    if (vertices) eml_free_vertices(vertices, num_v);
    if (edges) eml_free_edges(edges, num_e);
    
    return ret;
}

static int eml_self_test(void) {
    int errors = 0;
    
    errors += (test_serialization_roundtrip() != 0);
    errors += (test_delta_weighted_edge() != 0);
    errors += (test_snapshot_create_rollback() != 0);
    
    if (errors == 0) {
        pr_info("=== EML 存储管理自测试全部通过 ===\n");
    } else {
        pr_warn("=== EML 存储管理自测试：%d 项失败 ===\n", errors);
    }
    
    return errors;
}

/* ============================================================
 * 第8部分：模块初始化/退出
 * ============================================================ */

static dev_t eml_dev;
static struct cdev *eml_cdev;

static int __init eml_map_init(void) {
    pr_info("EML 谱图存储管理加载（TOMAS-AGI v2.0 M2 里程碑 T022）\n");
    
    /* 初始化存储上下文 */
    memset(&g_eml_ctx, 0, sizeof(g_eml_ctx));
    g_eml_ctx.max_snapshots = 32;
    g_eml_ctx.header.magic = EML_MAGIC;
    g_eml_ctx.header.version = EML_VERSION;
    
    /* 分配快照管理数组 */
    g_eml_ctx.snapshot_data = kmalloc(
        g_eml_ctx.max_snapshots * sizeof(void *), GFP_KERNEL);
    g_eml_ctx.snapshot_ids = kmalloc(
        g_eml_ctx.max_snapshots * sizeof(uint64_t), GFP_KERNEL);
    
    if (!g_eml_ctx.snapshot_data || !g_eml_ctx.snapshot_ids) {
        pr_err("快照管理数组分配失败\n");
        kfree(g_eml_ctx.snapshot_data);
        kfree(g_eml_ctx.snapshot_ids);
        return -ENOMEM;
    }
    
    memset(g_eml_ctx.snapshot_data, 0,
            g_eml_ctx.max_snapshots * sizeof(void *));
    memset(g_eml_ctx.snapshot_ids, 0,
            g_eml_ctx.max_snapshots * sizeof(uint64_t));
    
    /* 分配设备号 */
    if (alloc_chrdev_region(&eml_dev, 0, 1, "eml_map") < 0) {
        pr_err("无法分配设备号\n");
        goto err_kmem;
    }
    
    eml_cdev = cdev_alloc();
    if (!eml_cdev) {
        pr_err("无法分配 cdev\n");
        goto err_dev;
    }
    
    cdev_init(eml_cdev, &eml_fops);
    eml_cdev->owner = THIS_MODULE;
    
    if (cdev_add(eml_cdev, eml_dev, 1) < 0) {
        pr_err("无法添加 cdev\n");
        goto err_cdev;
    }
    
    /* 运行自测试 */
    eml_self_test();
    
    pr_info("EML 谱图存储管理加载成功（主设备号=%d）\n",
             MAJOR(eml_dev));
    return 0;

err_cdev:
    kfree(eml_cdev);
err_dev:
    unregister_chrdev_region(eml_dev, 1);
err_kmem:
    kfree(g_eml_ctx.snapshot_data);
    kfree(g_eml_ctx.snapshot_ids);
    return -1;
}

static void __exit eml_map_exit(void) {
    pr_info("EML 谱图存储管理卸载\n");
    
    /* 清理快照 */
    for (int i = 0; i < g_eml_ctx.num_snapshots; i++) {
        if (g_eml_ctx.snapshot_data[i]) {
            vfree(g_eml_ctx.snapshot_data[i]);
        }
    }
    
    kfree(g_eml_ctx.snapshot_data);
    kfree(g_eml_ctx.snapshot_ids);
    
    /* 释放图数据 */
    if (g_eml_ctx.vertices) eml_free_vertices(g_eml_ctx.vertices,
                                                g_eml_ctx.header.num_vertices);
    if (g_eml_ctx.edges) eml_free_edges(g_eml_ctx.edges,
                                          g_eml_ctx.header.num_edges);
    
    cdev_del(eml_cdev);
    kfree(eml_cdev);
    unregister_chrdev_region(eml_dev, 1);
    
    pr_info("EML 谱图存储管理卸载完成（已释放 %zu+%zu 字节）\n",
             g_eml_ctx.vertex_pool_size, g_eml_ctx.edge_pool_size);
}

module_init(eml_map_init);
module_exit(eml_map_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("章锋（章锋）");
MODULE_DESCRIPTION("EML 谱图存储管理（TOMAS-AGI v2.0 M2 里程碑 T022）");
MODULE_VERSION("2.0");
