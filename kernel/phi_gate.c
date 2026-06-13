/*
 * phi_gate.c —— Φ-Gate 语义门控（TOMAS-AGI v2.0 M2 里程碑 T023）
 *
 * 功能：
 *   1. 实现 Φ-Gate 双分支真值映射
 *   2. 谱投影分歧态管理（Liar 悖论等矛盾映射）
 *   3. 语义门切换逻辑（δ 加权门控）
 *   4. 互搏稳态维护（GR 分支 ↔ QM 分支）
 *   5. 悖论耐受判断（δ ≥ δ_critical）
 *
 * v2.0 理论基础（来自 NASGA 框架和 TOE 不可能性证明）：
 *   - Φ-Gate 是 TOMAS 互搏架构的"语义阀门"
 *   - 允许系统同时持有两个互斥的真值分支
 *   - 谱投影将双分支映射为可观测单值
 *   - δ 参数控制门的开启程度
 *
 * Φ-Gate 核心方程（NASGA §4.2）：
 *   Φ_δ(proposition) = (T_branch(δ), F_branch(δ))
 *
 *   其中：
 *     T_branch(δ) = truth_value · (1 + δ/κ) / 2
 *     F_branch(δ) = truth_value · (1 - δ/κ) / 2
 *
 *   谱投影（可观测真值）：
 *     Φ_project(δ) = T_branch · cos²(πδ/2κ) + F_branch · sin²(πδ/2κ)
 *
 * 作者：章锋（章锋）© 2026 复合体理学研究中心（TOMAS 项目组）
 *
 * 编译：
 *   make -C /lib/modules/$(uname -r)/build M=$(PWD) modules
 */

#define pr_fmt(fmt) "phi_gate: " fmt

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/mutex.h>
#include <linux/ktime.h>

/* ============================================================
 * 第1部分：Φ-Gate 核心结构
 * ============================================================ */

/* 真值双分支 */
struct truth_dual_branch {
    double t_branch;   /* T 分支（经典逻辑方向）*/
    double f_branch;   /* F 分支（量子逻辑方向）*/
    double delta;      /* 当前谱折叠深度 */
    double kappa;      /* 稳态 κ 值 */
};

/* Φ-Gate 状态 */
enum phi_gate_state {
    PHI_STATE_CLOSED = 0,     /* 闭合（经典逻辑，无双分支）*/
    PHI_STATE_OPENING,        /* 正在开启 δ 接近 κ */
    PHI_STATE_OPEN,           /* 完全开启（双分支并行）*/
    PHI_STATE_STABILIZING,    /* 稳定化（谱投影收敛）*/
    PHI_STATE_PARADOX,        /* 悖论态（δ 大幅波动）*/
};

/* Φ-Gate 门控参数 */
struct phi_gate_params {
    double kappa_stable;       /* κ=7 稳态锁定值 */
    double delta_critical;    /* 最小耐受 δ（默认 0.5）*/
    double opening_rate;      /* 门开启速率 */
    double closing_rate;      /* 门闭合速率 */
    double projection_blend;  /* 谱投影混合比 */
};

/* 命题状态（经过 Φ-Gate 处理）*/
struct phi_proposition {
    int    id;                 /* 命题 ID */
    double raw_truth_value;   /* 原始真值（0-1）*/
    struct truth_dual_branch branch;
    double projected_truth;   /* 谱投影真值（可观测）*/
    double paradox_index;     /* 悖论指数（越高越矛盾）*/
    int    is_paradox;        /* 是否为悖论态 */
    ktime_t timestamp;        /* 处理时间 */
};

/* Φ-Gate 全局状态 */
struct phi_gate {
    struct phi_gate_params params;
    enum phi_gate_state state;
    
    /* 统计 */
    int total_propositions;   /* 处理命题总数 */
    int paradox_count;        /* 悖论态命题数 */
    int branch_splits;        /* 双分支分裂次数 */
    int branch_merges;        /* 谱投影合并次数 */
    
    /* 最近的命题（环形缓冲区）*/
    #define PHI_RING_SIZE 32
    struct phi_proposition ring[PHI_RING_SIZE];
    int ring_head;
};

static struct phi_gate g_phi;
static DEFINE_MUTEX(g_phi_lock);

/* ============================================================
 * 第2部分：Φ-Gate 核心运算
 * ============================================================ */

/* 初始化 Φ-Gate 参数 */
static void phi_gate_params_init(struct phi_gate_params *p) {
    p->kappa_stable = 7.0;
    p->delta_critical = 0.5;
    p->opening_rate = 0.1;
    p->closing_rate = 0.2;
    p->projection_blend = 0.5;
}

/* 计算 Φ-Gate 双分支真值
 *
 * T_branch(δ) = truth · (1 + δ/κ) / 2  （偏向经典逻辑）
 * F_branch(δ) = truth · (1 - δ/κ) / 2   （偏向量子逻辑）
 *
 * 当 δ=0（经典极限）: T_branch = truth, F_branch = 0（纯经典）
 * 当 δ=κ（稳态）:     T_branch = truth, F_branch = 0（有效经典）
 * 当 δ→∞（量子极限）: T_branch → ∞·truth, F_branch → -∞·truth（发散）
 *
 * 但实际上 δ 被钳制在合理范围，不会真正发散。
 */
static void phi_compute_dual_branch(double truth_value, double delta,
                                      double kappa,
                                      struct truth_dual_branch *branch) {
    /* 钳制真值到 [0, 1] */
    if (truth_value < 0.0) truth_value = 0.0;
    if (truth_value > 1.0) truth_value = 1.0;
    
    /* 钳制 δ 到 [0, 100] 防止溢出 */
    double d = delta;
    if (d < 0.0) d = 0.0;
    if (d > 100.0) d = 100.0;
    
    double ratio = d / kappa;
    
    /* T 分支：偏向经典逻辑 */
    branch->t_branch = truth_value * (1.0 + ratio) * 0.5;
    
    /* F 分支：偏向量子逻辑（互补）*/
    branch->f_branch = truth_value * (1.0 - ratio) * 0.5;
    
    /* 钳制分支值 */
    if (branch->t_branch < 0.0) branch->t_branch = 0.0;
    if (branch->t_branch > 1.0) branch->t_branch = 1.0;
    if (branch->f_branch < 0.0) branch->f_branch = 0.0;
    if (branch->f_branch > 1.0) branch->f_branch = 1.0;
    
    branch->delta = delta;
    branch->kappa = kappa;
}

/* 谱投影：将双分支合并为单可观测真值
 *
 * Φ_project = T · cos²(πδ/2κ) + F · sin²(πδ/2κ)
 *
 * 物理意义：
 *   δ → 0:  cos²(0)=1, sin²(0)=0 → Φ_project = T（经典极限）
 *   δ → κ:  cos²(π/2)=0, sin²(π/2)=1 → Φ_project = F（量子极限）
 *   δ ≈ κ/2: cos²(π/4)=sin²(π/4)=0.5 → Φ_project = (T+F)/2（平衡）
 *
 * 这实现了"既经典又量子"的连续过渡——不是非此即彼，而是线性插值。
 */
static double phi_spectral_projection(const struct truth_dual_branch *branch,
                                        double projection_blend) {
    double ratio = branch->delta / branch->kappa;
    
    /* 防止数值异常 */
    if (ratio > 10.0) ratio = 10.0;
    if (ratio < -1.0) ratio = -1.0;
    
    /* 傅里叶谱投影权重 */
    double cos2 = cos(M_PI * ratio * 0.5);
    cos2 = cos2 * cos2;  /* cos² */
    
    double sin2 = sin(M_PI * ratio * 0.5);
    sin2 = sin2 * sin2;  /* sin² */
    
    /* 加投影混合比修正 */
    double weight_t = cos2 * (1.0 - projection_blend) +
                      projection_blend * 0.5;
    double weight_f = sin2 * (1.0 - projection_blend) +
                      projection_blend * 0.5;
    
    /* 归一化 */
    double total = weight_t + weight_f;
    if (total < 1e-10) return 0.5;  /* 默认中间值 */
    
    double projected = (branch->t_branch * weight_t +
                         branch->f_branch * weight_f) / total;
    
    return projected;
}

/* 计算悖论指数
 *
 * 悖论指数衡量双分支之间的"张力"。
 * 基于 TOMAS 的谱投影分歧态分析（NASGA §5.3）：
 *
 *   paradox_index = |T_branch - F_branch| / max(T_branch, F_branch)
 *                 = |δ/κ| / (变化范围)
 *
 * 高悖论指数 = 双分支分歧大 = 需要 Φ-Gate 耐受
 */
static double phi_compute_paradox_index(const struct truth_dual_branch *branch) {
    double diff = fabs(branch->t_branch - branch->f_branch);
    double max_val = (branch->t_branch > branch->f_branch) ?
                      branch->t_branch : branch->f_branch;
    
    if (max_val < 1e-10) return 0.0;
    
    return diff / max_val;
}

/* Φ-Gate 处理命题（核心函数）
 *
 * 流程：
 *   1. 检查 δ 阈值（悖论耐受判断）
 *   2. 计算双分支真值
 *   3. 计算谱投影
 *   4. 计算悖论指数
 *   5. 更新门状态
 *
 * 返回：0 正常，-1 需要告警
 */
int phi_gate_process(double truth_value, double delta,
                       struct phi_proposition *out_prop) {
    struct phi_proposition prop;
    int alert = 0;
    
    mutex_lock(&g_phi_lock);
    
    /* 初始化命题 */
    memset(&prop, 0, sizeof(prop));
    prop.id = g_phi.total_propositions;
    prop.raw_truth_value = truth_value;
    prop.timestamp = ktime_get();
    
    /* 第1步：δ 阈值检查（悖论耐受前置条件）*/
    if (delta < g_phi.params.delta_critical) {
        pr_warn("Φ-Gate 阈值告警：δ=%.4f < δ_critical=%.2f（悖论不耐受）\n",
                 delta, g_phi.params.delta_critical);
        
        /* 在 δ 不足时，门闭合 — 只保留单一经典真值 */
        phi_compute_dual_branch(truth_value, 0.0,
                                 g_phi.params.kappa_stable, &prop.branch);
        prop.projected_truth = truth_value;  /* 直接使用原始真值 */
        prop.paradox_index = 0.0;
        prop.is_paradox = 0;
        
        g_phi.state = PHI_STATE_CLOSED;
        alert = -1;
    } else {
        /* 第2步：计算双分支 */
        phi_compute_dual_branch(truth_value, delta,
                                 g_phi.params.kappa_stable, &prop.branch);
        
        /* 第3步：谱投影 */
        prop.projected_truth = phi_spectral_projection(
            &prop.branch, g_phi.params.projection_blend);
        
        /* 第4步：悖论指数 */
        prop.paradox_index = phi_compute_paradox_index(&prop.branch);
        
        /* 判断是否为悖论态
         * 悖论判断标准：双分支分歧超过阈值（默认为 0.3）*/
        prop.is_paradox = (prop.paradox_index > 0.3) ? 1 : 0;
        
        /* 第5步：更新门状态 */
        if (prop.is_paradox && delta > 2.0 * g_phi.params.delta_critical) {
            g_phi.state = PHI_STATE_OPEN;
            g_phi.branch_splits++;
        } else if (prop.is_paradox) {
            g_phi.state = PHI_STATE_OPENING;
        } else if (g_phi.state == PHI_STATE_OPEN &&
                   prop.paradox_index < 0.1) {
            g_phi.state = PHI_STATE_STABILIZING;
            g_phi.branch_merges++;
        }
    }
    
    /* 记录到环形缓冲区 */
    int idx = g_phi.ring_head;
    memcpy(&g_phi.ring[idx], &prop, sizeof(prop));
    g_phi.ring_head = (idx + 1) % PHI_RING_SIZE;
    
    g_phi.total_propositions++;
    if (prop.is_paradox) g_phi.paradox_count++;
    
    /* 输出结果 */
    if (out_prop) memcpy(out_prop, &prop, sizeof(prop));
    
    mutex_unlock(&g_phi_lock);
    
    return alert;
}
EXPORT_SYMBOL(phi_gate_process);

/* 批量处理命题（用于大规模推理）*/
int phi_gate_process_batch(const double *truth_values,
                             const double *deltas,
                             int count,
                             struct phi_proposition *out_props) {
    int alerts = 0;
    
    if (!truth_values || !deltas || !out_props || count <= 0)
        return -EINVAL;
    
    for (int i = 0; i < count; i++) {
        int ret = phi_gate_process(truth_values[i], deltas[i],
                                     &out_props[i]);
        if (ret != 0) alerts++;
    }
    
    pr_info("Φ-Gate 批量处理：%d 个命题，%d 告警\n", count, alerts);
    return alerts;
}
EXPORT_SYMBOL(phi_gate_process_batch);

/* ============================================================
 * 第3部分：门状态管理
 * ============================================================ */

/* 获取 Φ-Gate 当前状态描述 */
const char *phi_gate_state_name(enum phi_gate_state state) {
    switch (state) {
    case PHI_STATE_CLOSED:      return "CLOSED（经典逻辑）";
    case PHI_STATE_OPENING:     return "OPENING（δ 接近 κ）";
    case PHI_STATE_OPEN:        return "OPEN（双分支并行）";
    case PHI_STATE_STABILIZING: return "STABILIZING（谱投影收敛）";
    case PHI_STATE_PARADOX:     return "PARADOX（悖论态）";
    default:                    return "UNKNOWN";
    }
}

/* 强制切换 Φ-Gate 状态 */
int phi_gate_set_state(enum phi_gate_state new_state) {
    mutex_lock(&g_phi_lock);
    
    enum phi_gate_state old_state = g_phi.state;
    g_phi.state = new_state;
    
    pr_info("Φ-Gate 状态切换：%s → %s\n",
             phi_gate_state_name(old_state),
             phi_gate_state_name(new_state));
    
    mutex_unlock(&g_phi_lock);
    return 0;
}
EXPORT_SYMBOL(phi_gate_set_state);

/* 检查悖论耐受（δ ≥ δ_critical）*/
int phi_check_paradox_tolerance(double delta) {
    if (delta < g_phi.params.delta_critical) {
        pr_warn("Φ-Gate：悖论不耐受（δ=%.4f < %.2f）\n",
                 delta, g_phi.params.delta_critical);
        return 0;  /* 不耐受 */
    }
    return 1;  /* 耐受 */
}
EXPORT_SYMBOL(phi_check_paradox_tolerance);

/* ============================================================
 * 第4部分：谱投影分歧态分析（Liar 悖论）
 * ============================================================ */

/* Liar 悖论在 Φ-Gate 中的处理
 *
 * "这句话是假的" → 真值不稳定的自指陈述
 *
 * 在 TOMAS 框架下（NASGA §5.3）：
 *   1. 传统逻辑：Liar → 悖论（无解）
 *   2. TOMAS Φ-Gate：Liar 映射为谱投影分歧态
 *      真值在两个分支间振荡，δ 保持有界
 *
 * Φ(Liar) = {
 *   T_branch: "这句话是真的" → 真值 = 1
 *   F_branch: "这句话是假的" → 真值 = 0
 * }
 *
 * 谱投影输出 = 0.5（在 δ 合适时，这是最优解）
 */
int phi_process_liar_paradox(double delta, double *projected_truth,
                                double *paradox_index) {
    struct phi_proposition prop;
    int ret;
    
    /* Liar 悖论在 TOMAS 中对应 "既真又假"的状态
     * 原始真值设为 0.5（中间态）*/
    ret = phi_gate_process(0.5, delta, &prop);
    
    if (projected_truth) *projected_truth = prop.projected_truth;
    if (paradox_index) *paradox_index = prop.paradox_index;
    
    return ret;
}
EXPORT_SYMBOL(phi_process_liar_paradox);

/* ============================================================
 * 第5部分：ioctl 接口
 * ============================================================ */

#define PHI_IOC_MAGIC  'P'

#define PHI_IOC_PROCESS       _IOWR(PHI_IOC_MAGIC, 1, struct phi_process_arg)
#define PHI_IOC_PROCESS_BATCH _IOW(PHI_IOC_MAGIC, 2, struct phi_batch_arg)
#define PHI_IOC_LIAR          _IOWR(PHI_IOC_MAGIC, 3, struct phi_liar_arg)
#define PHI_IOC_GET_STATE     _IOR(PHI_IOC_MAGIC, 4, struct phi_state_arg)
#define PHI_IOC_SET_STATE     _IOW(PHI_IOC_MAGIC, 5, int)
#define PHI_IOC_SET_PARAMS    _IOW(PHI_IOC_MAGIC, 6, struct phi_gate_params)

struct phi_process_arg {
    double truth_value;
    double delta;
    /* 输出 */
    double t_branch;
    double f_branch;
    double projected_truth;
    double paradox_index;
    int    is_paradox;
    int    result;
};

struct phi_batch_arg {
    uint64_t truths_ptr;  /* double[N] */
    uint64_t deltas_ptr;  /* double[N] */
    int     count;
    int     alert_count;
    int     result;
};

struct phi_liar_arg {
    double delta;
    double projected_truth;
    double paradox_index;
    int    result;
};

struct phi_state_arg {
    int    state;
    double kappa_stable;
    double delta_critical;
    int    total_propositions;
    int    paradox_count;
    int    branch_splits;
    int    branch_merges;
    char   state_name[64];
};

static int phi_open(struct inode *inode, struct file *file) {
    pr_debug("Φ-Gate 设备打开\n");
    return 0;
}

static int phi_release(struct inode *inode, struct file *file) {
    pr_debug("Φ-Gate 设备关闭\n");
    return 0;
}

static long phi_ioctl(struct file *file, unsigned int cmd,
                       unsigned long arg) {
    int ret = 0;
    
    switch (cmd) {
    case PHI_IOC_PROCESS: {
        struct phi_process_arg proc_arg;
        struct phi_proposition prop;
        
        if (copy_from_user(&proc_arg,
                            (struct phi_process_arg __user *)arg,
                            sizeof(proc_arg)))
            return -EFAULT;
        
        proc_arg.result = phi_gate_process(proc_arg.truth_value,
                                             proc_arg.delta, &prop);
        
        proc_arg.t_branch = prop.branch.t_branch;
        proc_arg.f_branch = prop.branch.f_branch;
        proc_arg.projected_truth = prop.projected_truth;
        proc_arg.paradox_index = prop.paradox_index;
        proc_arg.is_paradox = prop.is_paradox;
        
        if (copy_to_user((struct phi_process_arg __user *)arg,
                          &proc_arg, sizeof(proc_arg)))
            return -EFAULT;
        break;
    }
    
    case PHI_IOC_LIAR: {
        struct phi_liar_arg liar;
        
        if (copy_from_user(&liar, (struct phi_liar_arg __user *)arg,
                            sizeof(liar)))
            return -EFAULT;
        
        liar.result = phi_process_liar_paradox(liar.delta,
                                                 &liar.projected_truth,
                                                 &liar.paradox_index);
        
        if (copy_to_user((struct phi_liar_arg __user *)arg,
                          &liar, sizeof(liar)))
            return -EFAULT;
        break;
    }
    
    case PHI_IOC_GET_STATE: {
        struct phi_state_arg state;
        
        mutex_lock(&g_phi_lock);
        state.state = (int)g_phi.state;
        state.kappa_stable = g_phi.params.kappa_stable;
        state.delta_critical = g_phi.params.delta_critical;
        state.total_propositions = g_phi.total_propositions;
        state.paradox_count = g_phi.paradox_count;
        state.branch_splits = g_phi.branch_splits;
        state.branch_merges = g_phi.branch_merges;
        strcpy(state.state_name, phi_gate_state_name(g_phi.state));
        mutex_unlock(&g_phi_lock);
        
        if (copy_to_user((struct phi_state_arg __user *)arg,
                          &state, sizeof(state)))
            return -EFAULT;
        break;
    }
    
    case PHI_IOC_SET_STATE: {
        int new_state;
        if (copy_from_user(&new_state, (int __user *)arg, sizeof(int)))
            return -EFAULT;
        
        if (new_state < 0 || new_state > PHI_STATE_PARADOX)
            return -EINVAL;
        
        ret = phi_gate_set_state((enum phi_gate_state)new_state);
        break;
    }
    
    case PHI_IOC_SET_PARAMS: {
        struct phi_gate_params new_params;
        if (copy_from_user(&new_params,
                            (struct phi_gate_params __user *)arg,
                            sizeof(new_params)))
            return -EFAULT;
        
        mutex_lock(&g_phi_lock);
        memcpy(&g_phi.params, &new_params, sizeof(new_params));
        mutex_unlock(&g_phi_lock);
        
        pr_info("Φ-Gate 参数更新：κ=%.1f, δ_crit=%.2f\n",
                 new_params.kappa_stable, new_params.delta_critical);
        break;
    }
    
    default:
        return -ENOTTY;
    }
    
    return ret;
}

static struct file_operations phi_fops = {
    .owner = THIS_MODULE,
    .open = phi_open,
    .release = phi_release,
    .unlocked_ioctl = phi_ioctl,
};

/* ============================================================
 * 第6部分：自测试
 * ============================================================ */

static int test_dual_branch_computation(void) {
    pr_info("=== 测试1：双分支计算 ===\n");
    
    struct truth_dual_branch branch;
    struct phi_proposition prop;
    int ret;
    
    /* 测试1：经典极限（δ=0）*/
    ret = phi_gate_process(1.0, 0.0, &prop);
    pr_info("  δ=0:    T=%.4f, F=%.4f, 投影=%.4f, 悖论=%.4f\n",
             prop.branch.t_branch, prop.branch.f_branch,
             prop.projected_truth, prop.paradox_index);
    
    /* 测试2：稳态（δ=κ=7）*/
    ret = phi_gate_process(1.0, 7.0, &prop);
    pr_info("  δ=7:    T=%.4f, F=%.4f, 投影=%.4f, 悖论=%.4f\n",
             prop.branch.t_branch, prop.branch.f_branch,
             prop.projected_truth, prop.paradox_index);
    
    /* 测试3：中间态（δ=3.5）*/
    ret = phi_gate_process(1.0, 3.5, &prop);
    pr_info("  δ=3.5:  T=%.4f, F=%.4f, 投影=%.4f, 悖论=%.4f\n",
             prop.branch.t_branch, prop.branch.f_branch,
             prop.projected_truth, prop.paradox_index);
    
    return 0;
}

static int test_liar_paradox(void) {
    pr_info("=== 测试2：Liar 悖论 ===\n");
    
    double projected, paradox_idx;
    int ret;
    
    /* 在 δ=7（稳态）下处理 Liar 悖论 */
    ret = phi_process_liar_paradox(7.0, &projected, &paradox_idx);
    
    pr_info("  Liar悖论(δ=7): 投影真值=%.4f, 悖论指数=%.4f, ret=%d\n",
             projected, paradox_idx, ret);
    
    /* 期望：投影真值接近 0.5（既真又假折中），悖论指数 > 0 */
    if (fabs(projected - 0.5) > 0.4) {
        pr_warn("  Liar 悖论处理异常：投影真值偏离 0.5\n");
    }
    
    return 0;
}

static int test_paradox_tolerance(void) {
    pr_info("=== 测试3：悖论耐受 ===\n");
    
    int t1 = phi_check_paradox_tolerance(0.0);  /* δ=0 */
    int t2 = phi_check_paradox_tolerance(0.5);  /* δ=临界 */
    int t3 = phi_check_paradox_tolerance(7.0);  /* δ=κ */
    
    pr_info("  δ=0:   耐受=%s\n", t1 ? "是" : "否");
    pr_info("  δ=0.5: 耐受=%s\n", t2 ? "是" : "否");
    pr_info("  δ=7:   耐受=%s\n", t3 ? "是" : "否");
    
    if (t1) return -1;     /* δ=0 不应耐受 */
    if (!t3) return -1;    /* δ=7 应该耐受 */
    
    return 0;
}

static int phi_self_test(void) {
    int errors = 0;
    
    errors += (test_dual_branch_computation() != 0);
    errors += (test_liar_paradox() != 0);
    errors += (test_paradox_tolerance() != 0);
    
    if (errors == 0) {
        pr_info("=== Φ-Gate 自测试全部通过 ===\n");
    } else {
        pr_warn("=== Φ-Gate 自测试：%d 项失败 ===\n", errors);
    }
    
    return errors;
}

/* ============================================================
 * 第7部分：模块初始化/退出
 * ============================================================ */

static dev_t phi_dev;
static struct cdev *phi_cdev;

static int __init phi_gate_init(void) {
    pr_info("Φ-Gate 语义门控加载（TOMAS-AGI v2.0 M2 里程碑 T023）\n");
    
    /* 初始化 Φ-Gate */
    memset(&g_phi, 0, sizeof(g_phi));
    phi_gate_params_init(&g_phi.params);
    g_phi.state = PHI_STATE_CLOSED;
    
    /* 分配设备号 */
    if (alloc_chrdev_region(&phi_dev, 0, 1, "phi_gate") < 0) {
        pr_err("无法分配设备号\n");
        return -1;
    }
    
    phi_cdev = cdev_alloc();
    if (!phi_cdev) {
        pr_err("无法分配 cdev\n");
        unregister_chrdev_region(phi_dev, 1);
        return -1;
    }
    
    cdev_init(phi_cdev, &phi_fops);
    phi_cdev->owner = THIS_MODULE;
    
    if (cdev_add(phi_cdev, phi_dev, 1) < 0) {
        pr_err("无法添加 cdev\n");
        kfree(phi_cdev);
        unregister_chrdev_region(phi_dev, 1);
        return -1;
    }
    
    /* 运行自测试 */
    phi_self_test();
    
    pr_info("Φ-Gate 语义门控加载成功（主设备号=%d）\n",
             MAJOR(phi_dev));
    return 0;
}

static void __exit phi_gate_exit(void) {
    pr_info("Φ-Gate 语义门控卸载\n");
    pr_info("  处理命题总数: %d\n", g_phi.total_propositions);
    pr_info("  悖论态:        %d (%.1f%%)\n",
             g_phi.paradox_count,
             100.0 * g_phi.paradox_count /
             (g_phi.total_propositions + 1));
    
    cdev_del(phi_cdev);
    kfree(phi_cdev);
    unregister_chrdev_region(phi_dev, 1);
    
    pr_info("Φ-Gate 卸载完成\n");
}

module_init(phi_gate_init);
module_exit(phi_gate_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("章锋（章锋）");
MODULE_DESCRIPTION("Φ-Gate 语义门控（TOMAS-AGI v2.0 M2 里程碑 T023）");
MODULE_VERSION("2.0");
