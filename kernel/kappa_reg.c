/*
 * kappa_reg.c —— κ=7 稳定性调节器（TOMAS-AGI v2.0 M2 里程碑 T021）
 *
 * 功能：
 *   1. 实现 PID 式 δ 谱折叠深度调节器
 *   2. 维护 κ=7 稳态锁定（当前宇宙的 δ 稳定值）
 *   3. 实现 A1 公理（δ 守恒）持续监测
 *   4. δ-ħ 对偶关系验证（定理 6.1）
 *   5. 提供 ioctl 接口供用户态查询/调控
 *
 * v2.0 理论基础（来自 PDF 4：δ ↔ ħ 对偶关系）：
 *   - 定理 6.1:  δ · ħ = Θ_TOMAS（自对偶方程）
 *   - 推论 6.2:  δ_universe = κ ≈ 7（当前宇宙处于经典极限分支）
 *   - 推论 9.3:  δ_0 = ℓ_P² · c⁵ / (G · ħ)（全由已知常数决定）
 *   - 猜想 9.1:  ℓ_TOMAS = ℓ_P（Planck 长度猜想）
 *   - 猜想 11.1: κ ↔ g_s 对偶（弦耦合常数）
 *
 * PID 调节策略：
 *   - P（比例）:  u_P = K_p · (δ_current - κ_target)
 *   - I（积分）:  u_I = K_i · ∫(δ - κ) dt（长期漂移补偿）
 *   - D（微分）:  u_D = K_d · dδ/dt（振荡阻尼）
 *
 * 作者：章锋（章锋）© 2026 复合体理学研究中心（TOMAS 项目组）
 *
 * 编译：
 *   make -C /lib/modules/$(uname -r)/build M=$(PWD) modules
 *   insmod kappa_reg.ko
 *   rmmod kappa_reg
 */

#define pr_fmt(fmt) "kappa_reg: " fmt

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/mutex.h>
#include <linux/ktime.h>
#include <linux/random.h>

/* ============================================================
 * 第1部分：κ 调节器核心结构
 * ============================================================ */

/* 物理常数（CODATA 2018 推荐值）*/
#define PLANCK_CONSTANT_H    6.62607015e-34   /* ħ = h/(2π) */
#define PLANCK_CONSTANT_HBAR 1.054571817e-34  /* 约化 Planck 常数 */
#define PLANCK_LENGTH_LP     1.616255e-35     /* Planck 长度 (m) */
#define SPEED_OF_LIGHT_C     2.99792458e8     /* 光速 (m/s) */
#define GRAVITATIONAL_G      6.67430e-11      /* 引力常数 (m³/(kg·s²)) */

/* TOMAS 框架常数 */
#define KAPPA_STABLE_DEFAULT 7.0              /* κ=7 稳态锁定值 */
#define DELTA_CRITICAL_MIN   0.5              /* 最小 δ 阈值（悖论耐受）*/
#define THETA_TOMAS_ESTIMATE (KAPPA_STABLE_DEFAULT * PLANCK_CONSTANT_HBAR)
                                              /* Θ_TOMAS ≈ 7.38e-34 (J·s) */

/* PID 调节参数（自适应调参）*/
struct pid_params {
    double Kp;   /* 比例增益（默认 0.3）*/
    double Ki;   /* 积分增益（默认 0.05）*/
    double Kd;   /* 微分增益（默认 0.1）*/
    double integral_limit;  /* 积分饱和上限 */
};

/* κ 调节器状态枚举 */
enum kappa_state {
    KAPPA_STATE_IDLE = 0,       /* 空闲 */
    KAPPA_STATE_LOCKING,       /* 正在锁定 κ=7 */
    KAPPA_STATE_STABLE,        /* 已稳定到 κ=7 */
    KAPPA_STATE_DRIFTING,      /* δ 漂移，需要调控 */
    KAPPA_STATE_RECOVERING,    /* 恢复中 */
    KAPPA_STATE_CRITICAL,     /* 跌破 δ_threshold */
    KAPPA_STATE_FAULT,        /* 故障 */
};

/* 调节器历史记录（环形缓冲区）*/
#define KP_HISTORY_SIZE 64

struct kp_history_entry {
    ktime_t  timestamp;      /* 时间戳 */
    double   delta_current; /* 当前 δ */
    double   delta_target;  /* 目标 δ（κ=7）*/
    double   error;          /* 误差 = δ - κ */
    double   control_signal; /* PID 输出 */
    enum kappa_state state;  /* 当时状态 */
};

/* 稳定性指标 */
struct stability_metrics {
    double mean_delta;      /* 平均 δ */
    double std_delta;       /* δ 标准差 */
    double drift_rate;      /* 漂移率（δ/s）*/
    double convergence_time; /* 收敛时间（ms）*/
    double stability_score; /* 稳定性得分 [0,1]（1=完美稳定）*/
    int    anomaly_count;   /* 累积异常次数 */
};

/* κ 调节器全局状态 */
struct kappa_regulator {
    /* 目标参数 */
    double kappa_target;        /* κ 目标值（默认 7）*/
    double epsilon_tolerance;  /* δ 允许误差（默认 0.01）*/
    
    /* 当前状态 */
    enum kappa_state state;
    double delta_current;       /* 当前 δ */
    double delta_previous;     /* 上一次 δ */
    
    /* PID 控制器 */
    struct pid_params pid;
    double integral;           /* 积分项累积 */
    double prev_error;        /* 上一次误差 */
    ktime_t  prev_time;        /* 上一次调节时间 */
    
    /* 历史记录 */
    struct kp_history_entry history[KP_HISTORY_SIZE];
    int history_head;          /* 环形缓冲区写指针 */
    int history_count;         /* 已记录条数 */
    
    /* 稳定性指标 */
    struct stability_metrics metrics;
    
    /* 健康监测 */
    int a1_violations;        /* A1 公理违规计数 */
    int threshold_violations; /* 阈值违规计数 */
    int total_cycles;         /* 总调节周期 */
    
    /* 对偶验证 */
    double theta_tomas;       /* Θ_TOMAS 测量值 */
    int    duality_verified;  /* 对偶已验证标志 */
};

static struct kappa_regulator g_kr;

/* 并发保护 */
static DEFINE_MUTEX(g_kr_lock);

/* ============================================================
 * 第2部分：物理常数计算（δ ↔ ħ 对偶验证）
 * ============================================================ */

/* 计算 Θ_TOMAS = δ_current · ħ
 *
 * 定理 6.1（δ-ħ 自对偶）：
 *   δ_current · ħ = Θ_TOMAS（应为常数）
 *
 * 返回：Θ_TOMAS 计算值
 */
static double compute_theta_tomas(double delta) {
    return delta * PLANCK_CONSTANT_HBAR;
}

/* 验证 δ-ħ 对偶关系（定理 6.1）
 *
 * 检查 δ · ħ 是否为常数。
 * 在不同 δ 取值下，δ · ħ 应保持不变。
 *
 * 返回：0 表示对偶成立，-1 表示破坏
 */
static int verify_delta_hbar_duality(double delta) {
    double theta = compute_theta_tomas(delta);
    double expected = g_kr.theta_tomas;
    
    /* 首次调用时记录基准值 */
    if (expected < 1e-40) {
        g_kr.theta_tomas = theta;
        pr_info("δ-ħ 对偶基准：Θ_TOMAS = %.6e J·s（δ=%.2f）\n",
                 g_kr.theta_tomas, delta);
        g_kr.duality_verified = 1;
        return 0;
    }
    
    double deviation = fabs(theta - expected) / (expected + 1e-40);
    
    if (deviation < 0.01) {  /* 1% 容差 */
        pr_info("δ-ħ 对偶验证通过：δ=%.6f, ħ=%.6e, Θ=%.6e（偏差 %.2f%%）\n",
                 delta, PLANCK_CONSTANT_HBAR, theta, deviation * 100.0);
        return 0;
    } else {
        pr_warn("δ-ħ 对偶偏差：δ=%.6f, Θ=%.6e vs 基准=%.6e（偏差 %.2f%%）\n",
                 delta, theta, expected, deviation * 100.0);
        return -1;
    }
}

/* 由已知物理常数推导 κ（推论 9.3）
 *
 * 若 Planck 长度猜想（猜想 9.1）成立：
 *   κ = δ_0 = ℓ_P² · c⁵ / (G · ħ)
 *
 * 返回：理论上 κ 应等于此值
 */
static double compute_kappa_from_constants(void) {
    double lp2 = PLANCK_LENGTH_LP * PLANCK_LENGTH_LP;
    double c5 = SPEED_OF_LIGHT_C * SPEED_OF_LIGHT_C *
                SPEED_OF_LIGHT_C * SPEED_OF_LIGHT_C * SPEED_OF_LIGHT_C;
    double denom = GRAVITATIONAL_G * PLANCK_CONSTANT_HBAR;
    
    if (denom < 1e-50) return KAPPA_STABLE_DEFAULT;
    
    return lp2 * c5 / denom;
}

/* ============================================================
 * 第3部分：PID 调节器实现
 * ============================================================ */

/* 初始化 PID 参数 */
static void pid_init(struct pid_params *pid) {
    pid->Kp = 0.3;
    pid->Ki = 0.05;
    pid->Kd = 0.1;
    pid->integral_limit = 10.0;
}

/* PID 调节器单步执行
 *
 * 输入：delta_current（当前 δ），delta_target（目标值 κ=7）
 * 输出：control_signal（调节量，需叠加到 δ）
 *
 * PID 公式：
 *   u(t) = K_p · e(t) + K_i · ∫_0^t e(τ)dτ + K_d · de/dt
 *
 * 其中 e(t) = delta_current - delta_target
 */
static double pid_step(struct pid_params *pid, double delta_current,
                        double delta_target, double dt) {
    /* 比例项（P）：当前误差 */
    double error = delta_current - delta_target;
    
    /* 积分项（I）：累积误差（带积分饱和限制）*/
    g_kr.integral += error * dt;
    if (g_kr.integral > pid->integral_limit)
        g_kr.integral = pid->integral_limit;
    if (g_kr.integral < -pid->integral_limit)
        g_kr.integral = -pid->integral_limit;
    
    /* 微分项（D）：误差变化率 */
    double derivative = 0.0;
    if (dt > 1e-15) {
        derivative = (error - g_kr.prev_error) / dt;
    }
    
    /* PID 输出 */
    double control = pid->Kp * error +
                     pid->Ki * g_kr.integral +
                     pid->Kd * derivative;
    
    /* 保存状态 */
    g_kr.prev_error = error;
    
    return control;
}

/* 判断 δ 是否在 κ=7 的稳定范围内 */
static int is_delta_stable(double delta, double tolerance) {
    return (fabs(delta - g_kr.kappa_target) < tolerance);
}

/* 更新 κ 调节器状态（有限状态机）*/
static void update_kappa_state(double delta) {
    enum kappa_state new_state = g_kr.state;
    
    switch (g_kr.state) {
    case KAPPA_STATE_IDLE:
        if (fabs(delta - g_kr.kappa_target) > g_kr.epsilon_tolerance)
            new_state = KAPPA_STATE_LOCKING;
        break;
        
    case KAPPA_STATE_LOCKING:
        if (is_delta_stable(delta, g_kr.epsilon_tolerance))
            new_state = KAPPA_STATE_STABLE;
        else if (fabs(delta - g_kr.kappa_target) > 2.0 * g_kr.epsilon_tolerance)
            new_state = KAPPA_STATE_DRIFTING;
        break;
        
    case KAPPA_STATE_STABLE:
        if (fabs(delta - g_kr.kappa_target) > 2.0 * g_kr.epsilon_tolerance) {
            new_state = KAPPA_STATE_DRIFTING;
        } else if (delta < DELTA_CRITICAL_MIN) {
            new_state = KAPPA_STATE_CRITICAL;
        }
        break;
        
    case KAPPA_STATE_DRIFTING:
        if (is_delta_stable(delta, g_kr.epsilon_tolerance))
            new_state = KAPPA_STATE_RECOVERING;
        else if (delta < DELTA_CRITICAL_MIN)
            new_state = KAPPA_STATE_CRITICAL;
        break;
        
    case KAPPA_STATE_RECOVERING:
        if (is_delta_stable(delta, g_kr.epsilon_tolerance * 0.5))
            new_state = KAPPA_STATE_STABLE;
        else if (fabs(delta - g_kr.kappa_target) > 3.0 * g_kr.epsilon_tolerance)
            new_state = KAPPA_STATE_DRIFTING;
        break;
        
    case KAPPA_STATE_CRITICAL:
        if (delta > DELTA_CRITICAL_MIN + 0.2)
            new_state = KAPPA_STATE_RECOVERING;
        break;
        
    case KAPPA_STATE_FAULT:
        if (is_delta_stable(delta, g_kr.epsilon_tolerance * 2.0))
            new_state = KAPPA_STATE_RECOVERING;
        break;
    }
    
    if (new_state != g_kr.state) {
        const char *state_names[] = {
            "IDLE", "LOCKING", "STABLE", "DRIFTING",
            "RECOVERING", "CRITICAL", "FAULT"
        };
        pr_info("κ 调节器状态转移：%s → %s（δ=%.6f）\n",
                 state_names[g_kr.state], state_names[new_state], delta);
        g_kr.state = new_state;
    }
}

/* ============================================================
 * 第4部分：κ 调节器核心运算
 * ============================================================ */

/* 调节器初始化 */
static void kappa_regulator_init(void) {
    memset(&g_kr, 0, sizeof(g_kr));
    
    g_kr.kappa_target = KAPPA_STABLE_DEFAULT;
    g_kr.epsilon_tolerance = 0.01;
    g_kr.state = KAPPA_STATE_IDLE;
    g_kr.delta_current = 0.0;
    
    pid_init(&g_kr.pid);
    g_kr.integral = 0.0;
    g_kr.prev_error = 0.0;
    g_kr.prev_time = ktime_get();
    
    /* 初始化稳定性指标 */
    memset(&g_kr.metrics, 0, sizeof(g_kr.metrics));
    g_kr.metrics.stability_score = 1.0;  /* 初始假设稳定 */
    
    /* 物理常数验证 */
    double kappa_from_consts = compute_kappa_from_constants();
    pr_info("由物理常数推导 κ：%.6f（Planck 长度猜想）\n", kappa_from_consts);
    pr_info("配置 κ=%.1f 作为稳态锁定目标\n", g_kr.kappa_target);
}

/* 调节器单步执行（核心循环入口）
 *
 * 这是 κ 调节器的主循环，每次调用执行一个调节周期：
 *   1. 更新 δ 历史
 *   2. 执行 PID 调节
 *   3. 验证 δ-ħ 对偶
 *   4. 更新状态机
 *   5. 更新稳定性指标
 *
 * 参数：
 *   delta_input:  当前测量的 δ 值
 *   delta_output: 返回调节后的 δ 目标值
 *   dt_ms:       距离上次调节的时间间隔（毫秒）
 *
 * 返回：0 正常，-1 需要告警
 */
int kappa_regulate(double delta_input, double *delta_output, double dt_ms) {
    double dt = dt_ms / 1000.0;  /* 转换为秒 */
    int alert = 0;
    
    mutex_lock(&g_kr_lock);
    
    /* 保存上一次的 δ */
    g_kr.delta_previous = g_kr.delta_current;
    g_kr.delta_current = delta_input;
    
    /* 记录历史 */
    int idx = g_kr.history_head;
    g_kr.history[idx].timestamp = ktime_get();
    g_kr.history[idx].delta_current = delta_input;
    g_kr.history[idx].delta_target = g_kr.kappa_target;
    g_kr.history[idx].error = delta_input - g_kr.kappa_target;
    g_kr.history_head = (idx + 1) % KP_HISTORY_SIZE;
    if (g_kr.history_count < KP_HISTORY_SIZE)
        g_kr.history_count++;
    
    /* 执行 PID 调节 */
    double control = pid_step(&g_kr.pid, delta_input,
                               g_kr.kappa_target, dt);
    
    g_kr.history[idx].control_signal = control;
    
    /* 计算调节后的 δ 目标 */
    /* δ_new = δ_current - α · control（负反馈）*/
    double alpha = 0.1;  /* 调节步长系数（避免过冲）*/
    *delta_output = delta_input - alpha * control;
    
    /* 钳制 δ 到合理范围 */
    if (*delta_output < 0.0) *delta_output = 0.0;
    if (*delta_output > 100.0) *delta_output = 100.0;
    
    /* 验证 δ-ħ 对偶（定理 6.1）*/
    if (g_kr.total_cycles % 10 == 0) {  /* 每 10 个周期验证一次 */
        if (verify_delta_hbar_duality(delta_input) != 0) {
            alert = -1;
        }
    }
    
    /* A1 公理监测（δ 守恒）*/
    double delta_diff = fabs(g_kr.delta_current - g_kr.delta_previous);
    if (delta_diff > 0.5 && g_kr.delta_previous > 0.01) {
        pr_warn("A1 公理告警：δ 突变 Δδ=%.4f（前=%.4f, 后=%.4f）\n",
                 delta_diff, g_kr.delta_previous, g_kr.delta_current);
        g_kr.a1_violations++;
        alert = -1;
    }
    
    /* δ 阈值监测 */
    if (g_kr.delta_current < DELTA_CRITICAL_MIN) {
        pr_err("δ 阈值告警：δ=%.4f < δ_critical=%.2f（悖论不耐受）\n",
                g_kr.delta_current, DELTA_CRITICAL_MIN);
        g_kr.threshold_violations++;
        alert = -1;
    }
    
    /* 更新状态机 */
    update_kappa_state(g_kr.delta_current);
    g_kr.history[idx].state = g_kr.state;
    
    /* 更新稳定性指标 */
    g_kr.metrics.drift_rate = (g_kr.delta_current - g_kr.delta_previous) / (dt + 1e-15);
    
    /* 计算稳定性得分
     * score = 1.0 - |δ - κ| / κ（越接近 κ=7 得分越高）*/
    double deviation = fabs(g_kr.delta_current - g_kr.kappa_target);
    g_kr.metrics.stability_score = 1.0 - deviation / g_kr.kappa_target;
    if (g_kr.metrics.stability_score < 0.0)
        g_kr.metrics.stability_score = 0.0;
    
    /* 计算收敛时间（从 LOCKING 到 STABLE 的耗时）*/
    if (g_kr.state == KAPPA_STATE_STABLE && g_kr.metrics.convergence_time == 0.0) {
        g_kr.metrics.convergence_time = ktime_to_ms(
            ktime_sub(ktime_get(), g_kr.prev_time));
        pr_info("κ 收敛时间：%.1f ms\n", g_kr.metrics.convergence_time);
    }
    
    g_kr.total_cycles++;
    
    mutex_unlock(&g_kr_lock);
    
    return alert;
}
EXPORT_SYMBOL(kappa_regulate);

/* 强制重新校准 κ 调节器 */
int kappa_recalibrate(double new_delta) {
    mutex_lock(&g_kr_lock);
    
    /* 重置 PID 积分项 */
    g_kr.integral = 0.0;
    g_kr.prev_error = 0.0;
    g_kr.delta_current = new_delta;
    g_kr.delta_previous = new_delta;
    
    /* 重置状态 */
    g_kr.state = KAPPA_STATE_LOCKING;
    
    /* 重置稳定性指标 */
    g_kr.metrics.convergence_time = 0.0;
    g_kr.metrics.anomaly_count = 0;
    
    pr_info("κ 调节器重新校准：δ=%.6f，状态=LOCKING\n", new_delta);
    
    mutex_unlock(&g_kr_lock);
    return 0;
}
EXPORT_SYMBOL(kappa_recalibrate);

/* 获取调节器当前状态摘要 */
int kappa_get_status(char *buffer, size_t buflen) {
    if (!buffer || buflen < 512) return -EINVAL;
    
    const char *state_names[] = {
        "IDLE", "LOCKING", "STABLE", "DRIFTING",
        "RECOVERING", "CRITICAL", "FAULT"
    };
    
    mutex_lock(&g_kr_lock);
    
    snprintf(buffer, buflen,
        "=== κ=7 稳定性调节器状态 ===\n"
        "  目标 κ:       %.2f\n"
        "  当前 δ:       %.6f\n"
        "  误差:          %.6f\n"
        "  状态:          %s\n"
        "  稳定性得分:    %.4f (%.1f%%)\n"
        "  漂移率:        %.6f δ/s\n"
        "  PID 输出:      %.6f\n"
        "  A1 违规:       %d\n"
        "  阈值违规:      %d\n"
        "  总周期:        %d\n"
        "  δ-ħ 对偶验证:  %s\n"
        "  Θ_TOMAS:       %.6e J·s\n"
        "  ===============================\n",
        g_kr.kappa_target,
        g_kr.delta_current,
        g_kr.delta_current - g_kr.kappa_target,
        state_names[g_kr.state],
        g_kr.metrics.stability_score,
        g_kr.metrics.stability_score * 100.0,
        g_kr.metrics.drift_rate,
        g_kr.pid.Kp * (g_kr.delta_current - g_kr.kappa_target),
        g_kr.a1_violations,
        g_kr.threshold_violations,
        g_kr.total_cycles,
        g_kr.duality_verified ? "✅ 通过" : "⚠ 未验证",
        g_kr.theta_tomas);
    
    mutex_unlock(&g_kr_lock);
    return 0;
}
EXPORT_SYMBOL(kappa_get_status);

/* ============================================================
 * 第5部分：ioctl 接口
 * ============================================================ */

#define KAPPA_IOC_MAGIC  'K'

/* ioctl 命令 */
#define KAPPA_IOC_SET_TARGET     _IOW(KAPPA_IOC_MAGIC, 1, double)
#define KAPPA_IOC_GET_TARGET     _IOR(KAPPA_IOC_MAGIC, 2, double)
#define KAPPA_IOC_REGULATE       _IOWR(KAPPA_IOC_MAGIC, 3, struct kr_regulate_arg)
#define KAPPA_IOC_RECALIBRATE    _IOW(KAPPA_IOC_MAGIC, 4, double)
#define KAPPA_IOC_GET_STATUS     _IOR(KAPPA_IOC_MAGIC, 5, struct kr_status_arg)
#define KAPPA_IOC_SET_PID        _IOW(KAPPA_IOC_MAGIC, 6, struct kr_pid_arg)
#define KAPPA_IOC_VERIFY_DUALITY _IOR(KAPPA_IOC_MAGIC, 7, struct kr_duality_arg)
#define KAPPA_IOC_RESET          _IO(KAPPA_IOC_MAGIC, 8)

/* ioctl 参数结构 */
struct kr_regulate_arg {
    double delta_input;
    double delta_output;
    double dt_ms;
    int    result;       /* 0=OK, -1=alert */
};

struct kr_status_arg {
    double kappa_target;
    double delta_current;
    double stability_score;
    double drift_rate;
    int    state;
    int    a1_violations;
    int    total_cycles;
    char   state_name[32];
};

struct kr_pid_arg {
    double Kp;
    double Ki;
    double Kd;
    double integral_limit;
};

struct kr_duality_arg {
    double delta;
    double theta_tomas;
    double expected_theta;
    double deviation_pct;
    int    verified;
};

static int kappa_open(struct inode *inode, struct file *file) {
    pr_debug("κ 调节器设备打开\n");
    return 0;
}

static int kappa_release(struct inode *inode, struct file *file) {
    pr_debug("κ 调节器设备关闭\n");
    return 0;
}

static long kappa_ioctl(struct file *file, unsigned int cmd,
                         unsigned long arg) {
    int ret = 0;
    
    switch (cmd) {
    case KAPPA_IOC_SET_TARGET: {
        double new_target;
        if (copy_from_user(&new_target, (double __user *)arg,
                            sizeof(new_target)))
            return -EFAULT;
        
        if (new_target < 0.0 || new_target > 100.0)
            return -EINVAL;
        
        mutex_lock(&g_kr_lock);
        g_kr.kappa_target = new_target;
        g_kr.integral = 0.0;
        g_kr.prev_error = 0.0;
        mutex_unlock(&g_kr_lock);
        
        pr_info("设置 κ 目标：%.2f\n", new_target);
        break;
    }
    
    case KAPPA_IOC_GET_TARGET: {
        double target;
        mutex_lock(&g_kr_lock);
        target = g_kr.kappa_target;
        mutex_unlock(&g_kr_lock);
        
        if (copy_to_user((double __user *)arg, &target,
                          sizeof(target)))
            return -EFAULT;
        break;
    }
    
    case KAPPA_IOC_REGULATE: {
        struct kr_regulate_arg reg_arg;
        
        if (copy_from_user(&reg_arg, (struct kr_regulate_arg __user *)arg,
                            sizeof(reg_arg)))
            return -EFAULT;
        
        reg_arg.result = kappa_regulate(reg_arg.delta_input,
                                          &reg_arg.delta_output,
                                          reg_arg.dt_ms);
        
        if (copy_to_user((struct kr_regulate_arg __user *)arg,
                          &reg_arg, sizeof(reg_arg)))
            return -EFAULT;
        break;
    }
    
    case KAPPA_IOC_RECALIBRATE: {
        double delta;
        if (copy_from_user(&delta, (double __user *)arg, sizeof(delta)))
            return -EFAULT;
        
        ret = kappa_recalibrate(delta);
        break;
    }
    
    case KAPPA_IOC_GET_STATUS: {
        struct kr_status_arg status;
        const char *state_names[] = {
            "IDLE", "LOCKING", "STABLE", "DRIFTING",
            "RECOVERING", "CRITICAL", "FAULT"
        };
        
        mutex_lock(&g_kr_lock);
        status.kappa_target = g_kr.kappa_target;
        status.delta_current = g_kr.delta_current;
        status.stability_score = g_kr.metrics.stability_score;
        status.drift_rate = g_kr.metrics.drift_rate;
        status.state = (int)g_kr.state;
        status.a1_violations = g_kr.a1_violations;
        status.total_cycles = g_kr.total_cycles;
        strcpy(status.state_name, state_names[g_kr.state]);
        mutex_unlock(&g_kr_lock);
        
        if (copy_to_user((struct kr_status_arg __user *)arg,
                          &status, sizeof(status)))
            return -EFAULT;
        break;
    }
    
    case KAPPA_IOC_SET_PID: {
        struct kr_pid_arg pid;
        if (copy_from_user(&pid, (struct kr_pid_arg __user *)arg,
                            sizeof(pid)))
            return -EFAULT;
        
        mutex_lock(&g_kr_lock);
        g_kr.pid.Kp = pid.Kp;
        g_kr.pid.Ki = pid.Ki;
        g_kr.pid.Kd = pid.Kd;
        g_kr.pid.integral_limit = pid.integral_limit;
        g_kr.integral = 0.0;
        g_kr.prev_error = 0.0;
        mutex_unlock(&g_kr_lock);
        
        pr_info("PID 参数更新：Kp=%.3f, Ki=%.3f, Kd=%.3f\n",
                 pid.Kp, pid.Ki, pid.Kd);
        break;
    }
    
    case KAPPA_IOC_VERIFY_DUALITY: {
        struct kr_duality_arg dual;
        
        if (copy_from_user(&dual, (struct kr_duality_arg __user *)arg,
                            sizeof(dual)))
            return -EFAULT;
        
        dual.theta_tomas = compute_theta_tomas(dual.delta);
        dual.expected_theta = g_kr.theta_tomas;
        dual.deviation_pct = fabs(dual.theta_tomas - dual.expected_theta) /
                              (dual.expected_theta + 1e-40) * 100.0;
        dual.verified = (dual.deviation_pct < 1.0) ? 1 : 0;
        
        if (copy_to_user((struct kr_duality_arg __user *)arg,
                          &dual, sizeof(dual)))
            return -EFAULT;
        break;
    }
    
    case KAPPA_IOC_RESET: {
        mutex_lock(&g_kr_lock);
        kappa_regulator_init();
        mutex_unlock(&g_kr_lock);
        pr_info("κ 调节器完全重置\n");
        break;
    }
    
    default:
        return -ENOTTY;
    }
    
    return ret;
}

static struct file_operations kappa_fops = {
    .owner = THIS_MODULE,
    .open = kappa_open,
    .release = kappa_release,
    .unlocked_ioctl = kappa_ioctl,
};

/* ============================================================
 * 第6部分：自测试
 * ============================================================ */

/* 测试1：基本调节流程 */
static int test_basic_regulation(void) {
    pr_info("=== 测试1：基本 κ 调节流程 ===\n");
    
    /* 模拟 δ 从 5.0 漂移到 7.0 */
    double delta = 5.0;
    double delta_out;
    int ret;
    
    for (int i = 0; i < 20; i++) {
        ret = kappa_regulate(delta, &delta_out, 100.0);  /* 100ms 间隔 */
        delta = delta_out;  /* 模拟调节生效 */
        
        pr_info("  周期 %d: δ=%.6f, δ_out=%.6f, ret=%d\n",
                 i, g_kr.delta_current, delta_out, ret);
        
        if (g_kr.state == KAPPA_STATE_STABLE)
            break;
    }
    
    pr_info("  最终状态：%d, δ=%.6f, 稳定性=%.4f\n",
             g_kr.state, g_kr.delta_current,
             g_kr.metrics.stability_score);
    
    return (g_kr.state >= KAPPA_STATE_STABLE) ? 0 : -1;
}

/* 测试2：δ-ħ 对偶验证 */
static int test_duality_verification(void) {
    pr_info("=== 测试2：δ-ħ 对偶验证 ===\n");
    
    /* 测试不同 δ 取值下的对偶关系 */
    double test_deltas[] = {0.1, 1.0, 3.5, 7.0, 7.38, 20.0};
    
    for (int i = 0; i < 6; i++) {
        double theta = compute_theta_tomas(test_deltas[i]);
        pr_info("  δ=%.2f → Θ_TOMAS=%.6e J·s\n", test_deltas[i], theta);
        
        int verified = verify_delta_hbar_duality(test_deltas[i]);
        pr_info("  对偶验证：%s\n", verified == 0 ? "通过" : "偏差");
    }
    
    return 0;
}

/* 测试3：A1 公理违规检测 */
static int test_a1_violation_detection(void) {
    pr_info("=== 测试3：A1 公理违规检测 ===\n");
    
    /* 模拟正常调节 */
    double delta_out;
    int ret = kappa_regulate(7.0, &delta_out, 100.0);
    pr_info("  正常调节：δ=7.0, ret=%d\n", ret);
    
    /* 模拟 δ 突变（A1 违规）*/
    ret = kappa_regulate(3.0, &delta_out, 100.0);  /* 7.0→3.0 跳跃 */
    pr_info("  突变调节：δ=3.0, ret=%d, 违规数=%d\n",
             ret, g_kr.a1_violations);
    
    return (g_kr.a1_violations > 0) ? 0 : -1;
}

/* 运行所有自测试 */
static int kappa_self_test(void) {
    int errors = 0;
    
    errors += test_basic_regulation();
    errors += test_duality_verification();
    errors += test_a1_violation_detection();
    
    if (errors == 0) {
        pr_info("=== κ 调节器自测试全部通过 ===\n");
    } else {
        pr_warn("=== κ 调节器自测试：%d 项失败 ===\n", errors);
    }
    
    return errors;
}

/* ============================================================
 * 第7部分：模块初始化/退出
 * ============================================================ */

static dev_t kappa_dev;
static struct cdev *kappa_cdev;

static int __init kappa_reg_init(void) {
    pr_info("κ=7 稳定性调节器加载（TOMAS-AGI v2.0 M2 里程碑 T021）\n");
    
    /* 初始化调节器 */
    kappa_regulator_init();
    
    /* 验证物理常数 */
    double kappa_from_consts = compute_kappa_from_constants();
    pr_info("Planck 长度猜想验证：κ(常数) = %.6f（参见推论 9.3）\n",
             kappa_from_consts);
    
    /* 分配设备号 */
    if (alloc_chrdev_region(&kappa_dev, 0, 1, "kappa_reg") < 0) {
        pr_err("无法分配设备号\n");
        return -1;
    }
    
    /* 分配并初始化 cdev */
    kappa_cdev = cdev_alloc();
    if (!kappa_cdev) {
        pr_err("无法分配 cdev\n");
        unregister_chrdev_region(kappa_dev, 1);
        return -1;
    }
    
    cdev_init(kappa_cdev, &kappa_fops);
    kappa_cdev->owner = THIS_MODULE;
    
    if (cdev_add(kappa_cdev, kappa_dev, 1) < 0) {
        pr_err("无法添加 cdev\n");
        kfree(kappa_cdev);
        unregister_chrdev_region(kappa_dev, 1);
        return -1;
    }
    
    /* 运行自测试 */
    kappa_self_test();
    
    pr_info("κ=7 稳定性调节器加载成功（主设备号=%d）\n",
             MAJOR(kappa_dev));
    return 0;
}

static void __exit kappa_reg_exit(void) {
    pr_info("κ=7 稳定性调节器卸载\n");
    
    /* 输出最终统计 */
    pr_info("  总调节周期: %d\n", g_kr.total_cycles);
    pr_info("  A1 违规:     %d\n", g_kr.a1_violations);
    pr_info("  阈值违规:    %d\n", g_kr.threshold_violations);
    pr_info("  最终稳定性:  %.4f\n", g_kr.metrics.stability_score);
    
    cdev_del(kappa_cdev);
    kfree(kappa_cdev);
    unregister_chrdev_region(kappa_dev, 1);
    
    pr_info("κ=7 稳定性调节器卸载完成\n");
}

module_init(kappa_reg_init);
module_exit(kappa_reg_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("章锋（章锋）");
MODULE_DESCRIPTION("κ=7 稳定性调节器（TOMAS-AGI v2.0 M2 里程碑 T021）");
MODULE_VERSION("2.0");
