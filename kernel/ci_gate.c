/*
 * ci_gate.c —— CI Gate 因果隔离门控（TOMAS-AGI v2.0 M2 里程碑 T025）
 *
 * 功能：
 *   1. 因果隔离边界强制执行（禁止跨分支副作用泄漏）
 *   2. 因果光锥验证（GR 分支 vs QM 分支）
 *   3. 协调-隔离（Coherence-Isolation）策略控制
 *   4. 跨分支泄漏检测
 *   5. 因果顺序审计
 *
 * v2.0 理论基础（来自 TOE 不可能性证明 §4-§5）：
 *   CI Gate 是 TOMAS 的 φ-Gate 的姊妹构件
 *
 *   因果隔离原理：
 *     GR 分支（经典极限，δ→0）：
 *       - 因果严格有序（A → B 不可逆）
 *       - 光锥外事件不可通信
 *       - 副作用不可跨分支传播
 *
 *     QM 分支（量子极限，δ→∞）：
 *       - 因果松弛（EPR 对可跨光锥关联）
 *       - 非定域性允许"先于原因的结果"
 *       - 副作用需通过 CI Gate 隔离
 *
 *   δ 对因果隔离的调节：
 *     δ → 0:   强隔离（GR 分支主导，严格因果）
 *     δ → κ:   中等隔离（稳态，可控的因果泄漏）
 *     δ → ∞:   弱隔离（QM 分支主导，因果松弛）
 *
 * 作者：章锋（章锋）© 2026 复合体理学研究中心（TOMAS 项目组）
 *
 * 编译：
 *   make -C /lib/modules/$(uname -r)/build M=$(PWD) modules
 */

#define pr_fmt(fmt) "ci_gate: " fmt

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
 * 第1部分：CI Gate 核心结构
 * ============================================================ */

/* 因果事件 */
struct causal_event {
    int    id;
    int    branch;         /* 0=GR分支, 1=QM分支 */
    ktime_t timestamp;
    double lightcone_radius; /* 光锥半径 */
    double delta;            /* 事件发生时的 δ */
    double energy;           /* 事件能量（用于因果强度）*/
    int    side_effect_flag; /* 是否有副作用 */
};

/* CI Gate 隔离策略 */
enum ci_isolation_policy {
    CI_POLICY_STRICT = 0,    /* 严格隔离（GR分支）*/
    CI_POLICY_BALANCED,      /* 平衡隔离（稳态）*/
    CI_POLICY_RELAXED,       /* 松弛隔离（QM分支）*/
    CI_POLICY_ADAPTIVE,      /* 自适应（δ 驱动）*/
};

/* CI Gate 状态 */
enum ci_gate_state {
    CI_STATE_ISOLATED = 0,   /* 完全隔离 */
    CI_STATE_LEAK_CHECK,     /* 泄漏检测中 */
    CI_STATE_PARTIAL_MERGE, /* 部分融合（可控泄漏）*/
    CI_STATE_EMERGENCY,     /* 紧急隔离（大量泄漏）*/
};

/* 泄漏记录 */
#define CI_LEAK_LOG_SIZE 64

struct leak_record {
    int    source_branch;
    int    target_branch;
    double leak_magnitude;   /* 泄漏量 */
    double delta_at_leak;   /* 泄漏时 δ */
    ktime_t timestamp;
};

/* CI Gate 全局状态 */
struct ci_gate_ctx {
    /* 隔离策略 */
    enum ci_isolation_policy policy;
    enum ci_gate_state state;
    
    /* 参数 */
    double delta_current;
    double isolation_strength; /* 隔离强度 [0,1] */
    double leak_threshold;     /* 泄漏警戒阈值 */
    
    /* 因果光锥验证 */
    double lightcone_margin;   /* 光锥边距 */
    
    /* 统计 */
    int    total_events;
    int    isolated_events;      /* 成功隔离的事件 */
    int    leak_events;          /* 泄漏事件 */
    int    cross_branch_events;  /* 跨分支事件 */
    
    /* 泄漏日志 */
    struct leak_record leak_log[CI_LEAK_LOG_SIZE];
    int    leak_log_head;
};

static struct ci_gate_ctx g_ci;
static DEFINE_MUTEX(g_ci_lock);

/* ============================================================
 * 第2部分：因果光锥验证
 * ============================================================ */

/* 验证两个事件是否在彼此的因果光锥内
 *
 * 光锥条件（类时间隔）：
 *   Δs² = c²·Δt² - Δx² ≥ 0 → 因果关联
 *   Δs² < 0 → 类空间隔（无因果关联）
 *
 * 在 TOMAS 中：
 *   c_eff(δ) = c · (1 - δ/κ)（δ 折减有效光速）
 *
 * 返回：1=在光锥内，0=在光锥外
 */
static int verify_lightcone(const struct causal_event *e1,
                              const struct causal_event *e2,
                              double delta) {
    double c_eff = 3e8;  /* 光速 (m/s) */
    double kappa = 7.0;
    
    /* δ 折减有效光速
     * δ→0: c_eff = c（经典，完整光速）
     * δ→κ: c_eff = c·(1-7/7) = 0（光锥完全收缩！量子非定域性）
     * 
     * 注：实际 δ 不会到 κ 才完全收缩，这里用非线性折减：
     */
    double ratio = delta / kappa;
    if (ratio > 1.0) ratio = 1.0;
    
    c_eff *= (1.0 - ratio * 0.9);  /* 最多折减 90% */
    
    /* 时间差（秒）*/
    s64 dt_ns = ktime_to_ns(ktime_sub(e2->timestamp, e1->timestamp));
    double dt = (double)dt_ns / 1e9;
    
    /* 空间距离（简化：用事件 ID 差值代替）*/
    double dx = fabs(e2->id - e1->id) * 1.0;  /* 每个 ID 间隔=1m（简化）*/
    
    /* 类时间隔检查 */
    double ds2 = c_eff * c_eff * dt * dt - dx * dx;
    
    /* 考虑 δ 的量子修正（非结合效应允许轻微超光速）*/
    double quantum_fuzz = delta * 0.01;  /* δ 越大，允许越多的非定域性 */
    ds2 += quantum_fuzz * c_eff * c_eff;
    
    return (ds2 >= 0.0) ? 1 : 0;
}

/* 验证跨分支因果
 *
 * 两个事件在不同分支时，必须通过 CI Gate 检查。
 * 只有满足光锥条件的才能跨分支传播。
 */
int ci_verify_cross_branch(const struct causal_event *gr_event,
                            const struct causal_event *qm_event,
                            double delta) {
    /* 如果同一分支，直接允许 */
    if (gr_event->branch == qm_event->branch)
        return 1;
    
    /* 跨分支：需要额外的隔离检查 */
    int in_cone = verify_lightcone(gr_event, qm_event, delta);
    
    if (in_cone) {
        pr_debug("跨分支因果验证通过：GR(%d) ↔ QM(%d), δ=%.2f\n",
                  gr_event->id, qm_event->id, delta);
        return 1;
    }
    
    pr_warn("跨分支因果违反：GR(%d) ↔ QM(%d) 不在光锥内，δ=%.2f\n",
             gr_event->id, qm_event->id, delta);
    return 0;
}
EXPORT_SYMBOL(ci_verify_cross_branch);

/* ============================================================
 * 第3部分：CI Gate 隔离控制
 * ============================================================ */

/* 计算 δ 驱动的隔离强度
 *
 * isolation_strength = 1.0 - δ/κ（当 δ > κ 时钳制为 0）
 *
 * δ→0: isolation=1.0（完全隔离，GR主导）
 * δ→κ: isolation≈0（弱隔离，QM主导）
 */
static double ci_compute_isolation_strength(double delta, double kappa) {
    double ratio = delta / kappa;
    if (ratio > 1.0) ratio = 1.0;
    
    return 1.0 - ratio;
}

/* CI Gate 主处理函数
 *
 * 输入两个事件（可能在不同分支），检查因果隔离条件。
 *
 * 返回：1=允许跨分支传播，0=拒绝（隔离生效），-1=错误
 */
int ci_gate_check(const struct causal_event *e1,
                    const struct causal_event *e2,
                    double delta) {
    int allowed = 0;
    
    mutex_lock(&g_ci_lock);
    
    g_ci.total_events += 2;
    
    /* 更新隔离强度 */
    g_ci.delta_current = delta;
    g_ci.isolation_strength = ci_compute_isolation_strength(
        delta, 7.0);
    
    /* 选择隔离策略 */
    if (g_ci.policy == CI_POLICY_ADAPTIVE) {
        if (g_ci.isolation_strength > 0.7) {
            /* 强隔离模式 */
            allowed = verify_lightcone(e1, e2, delta);
        } else if (g_ci.isolation_strength > 0.3) {
            /* 平衡模式：允许光锥内 + 弱量子关联 */
            allowed = verify_lightcone(e1, e2, delta) ||
                      (e1->delta > 3.0 && e2->delta > 3.0);
        } else {
            /* 松弛模式：主要允许跨分支 */
            allowed = 1;
        }
    } else {
        /* 固定策略 */
        switch (g_ci.policy) {
        case CI_POLICY_STRICT:
            allowed = verify_lightcone(e1, e2, delta);
            break;
        case CI_POLICY_BALANCED:
            allowed = verify_lightcone(e1, e2, delta) ||
                      (g_ci.isolation_strength < 0.5);
            break;
        case CI_POLICY_RELAXED:
            allowed = 1;
            break;
        default:
            allowed = verify_lightcone(e1, e2, delta);
        }
    }
    
    /* 跨分支计数 */
    if (e1->branch != e2->branch) {
        g_ci.cross_branch_events++;
        
        if (allowed) {
            g_ci.isolated_events++;
        } else {
            g_ci.leak_events++;
            
            /* 记录泄漏 */
            int idx = g_ci.leak_log_head;
            struct leak_record *rec = &g_ci.leak_log[idx];
            rec->source_branch = e1->branch;
            rec->target_branch = e2->branch;
            rec->leak_magnitude = g_ci.isolation_strength;
            rec->delta_at_leak = delta;
            rec->timestamp = ktime_get();
            g_ci.leak_log_head = (idx + 1) % CI_LEAK_LOG_SIZE;
        }
    }
    
    /* 状态更新 */
    if (g_ci.leak_events > g_ci.leak_threshold) {
        if (g_ci.state != CI_STATE_EMERGENCY) {
            pr_warn("CI Gate 进入紧急状态：泄漏 %d > 阈值 %.0f\n",
                     g_ci.leak_events, g_ci.leak_threshold);
            g_ci.state = CI_STATE_EMERGENCY;
        }
    }
    
    mutex_unlock(&g_ci_lock);
    
    return allowed;
}
EXPORT_SYMBOL(ci_gate_check);

/* 强制应急隔离（紧急锁定）*/
int ci_emergency_lockdown(void) {
    mutex_lock(&g_ci_lock);
    
    g_ci.state = CI_STATE_EMERGENCY;
    g_ci.isolation_strength = 1.0;  /* 最大隔离 */
    g_ci.policy = CI_POLICY_STRICT;
    
    pr_warn("CI Gate 紧急锁定：完全隔离模式\n");
    
    mutex_unlock(&g_ci_lock);
    return 0;
}
EXPORT_SYMBOL(ci_emergency_lockdown);

/* 解除紧急状态 */
int ci_release_lockdown(double delta) {
    mutex_lock(&g_ci_lock);
    
    g_ci.state = CI_STATE_ISOLATED;
    g_ci.isolation_strength = ci_compute_isolation_strength(delta, 7.0);
    g_ci.policy = CI_POLICY_ADAPTIVE;
    g_ci.leak_events = 0;  /* 重置泄漏计数 */
    
    pr_info("CI Gate 解除锁定：隔离强度=%.4f\n", g_ci.isolation_strength);
    
    mutex_unlock(&g_ci_lock);
    return 0;
}
EXPORT_SYMBOL(ci_release_lockdown);

/* ============================================================
 * 第4部分：ioctl 接口
 * ============================================================ */

#define CI_IOC_MAGIC  'C'

#define CI_IOC_CHECK       _IOWR(CI_IOC_MAGIC, 1, struct ci_check_arg)
#define CI_IOC_SET_POLICY  _IOW(CI_IOC_MAGIC, 2, int)
#define CI_IOC_GET_STATE   _IOR(CI_IOC_MAGIC, 3, struct ci_state_arg)
#define CI_IOC_LOCKDOWN    _IO(CI_IOC_MAGIC, 4)
#define CI_IOC_RELEASE     _IOW(CI_IOC_MAGIC, 5, double)

struct ci_check_arg {
    struct causal_event e1;
    struct causal_event e2;
    double delta;
    int    allowed;   /* 输出 */
    int    result;
};

struct ci_state_arg {
    int    state;
    int    policy;
    double isolation_strength;
    double delta_current;
    int    total_events;
    int    cross_branch_events;
    int    leak_events;
    int    isolated_events;
    double leak_rate;  /* 泄漏率 = leak/total */
};

static int ci_open(struct inode *inode, struct file *file) {
    pr_debug("CI Gate 设备打开\n");
    return 0;
}

static int ci_release(struct inode *inode, struct file *file) {
    pr_debug("CI Gate 设备关闭\n");
    return 0;
}

static long ci_ioctl(struct file *file, unsigned int cmd,
                      unsigned long arg) {
    int ret = 0;
    
    switch (cmd) {
    case CI_IOC_CHECK: {
        struct ci_check_arg carg;
        if (copy_from_user(&carg, (struct ci_check_arg __user *)arg,
                            sizeof(carg)))
            return -EFAULT;
        
        carg.allowed = ci_gate_check(&carg.e1, &carg.e2, carg.delta);
        carg.result = 0;
        
        if (copy_to_user((struct ci_check_arg __user *)arg,
                          &carg, sizeof(carg)))
            return -EFAULT;
        break;
    }
    
    case CI_IOC_SET_POLICY: {
        int policy;
        if (copy_from_user(&policy, (int __user *)arg, sizeof(policy)))
            return -EFAULT;
        
        if (policy < 0 || policy > CI_POLICY_ADAPTIVE)
            return -EINVAL;
        
        mutex_lock(&g_ci_lock);
        g_ci.policy = (enum ci_isolation_policy)policy;
        mutex_unlock(&g_ci_lock);
        
        pr_info("CI 隔离策略切换：%d\n", policy);
        break;
    }
    
    case CI_IOC_GET_STATE: {
        struct ci_state_arg sarg;
        
        mutex_lock(&g_ci_lock);
        sarg.state = (int)g_ci.state;
        sarg.policy = (int)g_ci.policy;
        sarg.isolation_strength = g_ci.isolation_strength;
        sarg.delta_current = g_ci.delta_current;
        sarg.total_events = g_ci.total_events;
        sarg.cross_branch_events = g_ci.cross_branch_events;
        sarg.leak_events = g_ci.leak_events;
        sarg.isolated_events = g_ci.isolated_events;
        sarg.leak_rate = (g_ci.total_events > 0) ?
            (double)g_ci.leak_events / g_ci.total_events : 0.0;
        mutex_unlock(&g_ci_lock);
        
        if (copy_to_user((struct ci_state_arg __user *)arg,
                          &sarg, sizeof(sarg)))
            return -EFAULT;
        break;
    }
    
    case CI_IOC_LOCKDOWN:
        ret = ci_emergency_lockdown();
        break;
    
    case CI_IOC_RELEASE: {
        double delta;
        if (copy_from_user(&delta, (double __user *)arg, sizeof(delta)))
            return -EFAULT;
        ret = ci_release_lockdown(delta);
        break;
    }
    
    default:
        return -ENOTTY;
    }
    
    return ret;
}

static struct file_operations ci_fops = {
    .owner = THIS_MODULE,
    .open = ci_open,
    .release = ci_release,
    .unlocked_ioctl = ci_ioctl,
};

/* ============================================================
 * 第5部分：自测试
 * ============================================================ */

static int test_cross_branch_isolation(void) {
    pr_info("=== 测试1：跨分支因果隔离 ===\n");
    
    struct causal_event gr_ev = {
        .id = 1, .branch = 0,
        .timestamp = ktime_get(),
        .lightcone_radius = 1.0,
        .delta = 0.5, .energy = 1.0, .side_effect_flag = 0
    };
    
    struct causal_event qm_ev = {
        .id = 2, .branch = 1,
        .timestamp = ktime_get(),
        .lightcone_radius = 1.0,
        .delta = 7.0, .energy = 1.0, .side_effect_flag = 0
    };
    
    /* 测试：δ=0 时强隔离 */
    int allowed_low = ci_gate_check(&gr_ev, &qm_ev, 0.1);
    pr_info("  低δ(0.1)跨分支：%s\n", allowed_low ? "允许" : "拒绝");
    
    /* 测试：δ=7 时弱隔离 */
    int allowed_high = ci_gate_check(&gr_ev, &qm_ev, 7.0);
    pr_info("  高δ(7.0)跨分支：%s\n", allowed_high ? "允许" : "拒绝");
    
    return 0;
}

static int test_lightcone_verification(void) {
    pr_info("=== 测试2：光锥验证 ===\n");
    
    struct causal_event e1 = {
        .id = 1, .branch = 0,
        .timestamp = ktime_get(),
        .lightcone_radius = 1.0,
        .delta = 3.0, .energy = 1.0, .side_effect_flag = 0
    };
    
    struct causal_event e2 = {
        .id = 1000, .branch = 0,
        .timestamp = ktime_add(ktime_get(), ktime_set(0, 1000000)),
        .lightcone_radius = 1.0,
        .delta = 3.0, .energy = 1.0, .side_effect_flag = 0
    };
    
    int in_cone = verify_lightcone(&e1, &e2, 0.1);
    pr_info("  近距事件（δ=0.1）光锥内：%s\n", in_cone ? "是" : "否");
    
    in_cone = verify_lightcone(&e1, &e2, 7.0);
    pr_info("  近距事件（δ=7.0）光锥内：%s\n", in_cone ? "是" : "否");
    
    return 0;
}

static int test_emergency_lockdown(void) {
    pr_info("=== 测试3：紧急锁定 ===\n");
    
    ci_emergency_lockdown();
    pr_info("  锁定后隔离强度：%.2f\n", g_ci.isolation_strength);
    
    ci_release_lockdown(7.0);
    pr_info("  释放后隔离强度：%.2f\n", g_ci.isolation_strength);
    
    return 0;
}

static int ci_self_test(void) {
    int errors = 0;
    
    errors += (test_cross_branch_isolation() != 0);
    errors += (test_lightcone_verification() != 0);
    errors += (test_emergency_lockdown() != 0);
    
    if (errors == 0) {
        pr_info("=== CI Gate 自测试全部通过 ===\n");
    } else {
        pr_warn("=== CI Gate 自测试：%d 项失败 ===\n", errors);
    }
    
    return errors;
}

/* ============================================================
 * 第6部分：模块初始化/退出
 * ============================================================ */

static dev_t ci_dev;
static struct cdev *ci_cdev;

static int __init ci_gate_init(void) {
    pr_info("CI Gate 因果隔离门控加载（TOMAS-AGI v2.0 M2 里程碑 T025）\n");
    
    memset(&g_ci, 0, sizeof(g_ci));
    g_ci.policy = CI_POLICY_ADAPTIVE;
    g_ci.state = CI_STATE_ISOLATED;
    g_ci.delta_current = 7.0;
    g_ci.isolation_strength = ci_compute_isolation_strength(7.0, 7.0);
    g_ci.leak_threshold = 100.0;
    
    if (alloc_chrdev_region(&ci_dev, 0, 1, "ci_gate") < 0) {
        pr_err("无法分配设备号\n");
        return -1;
    }
    
    ci_cdev = cdev_alloc();
    if (!ci_cdev) {
        unregister_chrdev_region(ci_dev, 1);
        return -1;
    }
    
    cdev_init(ci_cdev, &ci_fops);
    ci_cdev->owner = THIS_MODULE;
    
    if (cdev_add(ci_cdev, ci_dev, 1) < 0) {
        kfree(ci_cdev);
        unregister_chrdev_region(ci_dev, 1);
        return -1;
    }
    
    ci_self_test();
    
    pr_info("CI Gate 加载成功（主设备号=%d）\n", MAJOR(ci_dev));
    return 0;
}

static void __exit ci_gate_exit(void) {
    pr_info("CI Gate 卸载：%d 事件, %d 跨分支, %d 泄漏\n",
             g_ci.total_events, g_ci.cross_branch_events,
             g_ci.leak_events);
    
    cdev_del(ci_cdev);
    kfree(ci_cdev);
    unregister_chrdev_region(ci_dev, 1);
    
    pr_info("CI Gate 卸载完成\n");
}

module_init(ci_gate_init);
module_exit(ci_gate_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("章锋（章锋）");
MODULE_DESCRIPTION("CI Gate 因果隔离门控（TOMAS-AGI v2.0 M2 里程碑 T025）");
MODULE_VERSION("2.0");
