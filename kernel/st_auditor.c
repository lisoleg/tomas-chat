/*
 * st_auditor.c — T026: ST (Subjective Tendency) Auditor
 * 太乙互搏 AGI 内核模块 — 主观倾向审计器
 *
 * 模块职责：
 *   1. 监控双分支推理的系统性倾向漂移
 *   2. 计算分支平衡度、倾向性指标
 *   3. 审计日志记录与告警
 *   4. 与 Φ-Gate、δ-mem、κ-reg 联动
 *
 * 理论背景 (TOMAS-AGI v2.0):
 *   - 互搏架构要求双分支在 δ≈7 稳态下维持平衡
 *   - 如果某分支持续获胜（倾向漂移 > θ_alert），则触发审计告警
 *   - 审计器独立于推理核心，提供第三方监督
 *
 * 作者: 齐活林 (Qi)
 * 版本: v1.0
 * 日期: 2026-06-13
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/list.h>
#include <linux/slab.h>
#include <linux/timekeeping.h>
#include <linux/cdev.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/sched.h>

/* ================================================================
 * 1. 常量与宏定义
 * ================================================================ */

#define ST_AUDITOR_NAME         "st_auditor"
#define ST_AUDITOR_VERSION      "1.0"

/* 默认参数 */
#define ST_DEFAULT_WINDOW_SIZE    64      /* 滑动窗口大小（回合数） */
#define ST_DEFAULT_ALERT_THRESH   0.35    /* 倾向漂移告警阈值（|bias| > θ_alert） */
#define ST_DEFAULT_DRIFT_WARN     0.25    /* 倾向漂移预警阈值 */
#define ST_MAX_LOG_ENTRIES        1024    /* 最大审计日志条目数 */
#define ST_MAX_BRANCHES           2       /* 双分支架构，不可变 */

/* ioctl 命令 */
#define ST_IOC_MAGIC              'S'
#define ST_IOC_GET_REPORT         _IOR(ST_IOC_MAGIC, 1, struct st_audit_report)
#define ST_IOC_GET_STATS          _IOR(ST_IOC_MAGIC, 2, struct st_tendency_stats)
#define ST_IOC_SET_THRESH         _IOW(ST_IOC_MAGIC, 3, struct st_threshold_config)
#define ST_IOC_RESET_ALL          _IO(ST_IOC_MAGIC, 4)
#define ST_IOC_SUBMIT_ROUND       _IOW(ST_IOC_MAGIC, 5, struct st_round_result)
#define ST_IOC_GET_LOG            _IOWR(ST_IOC_MAGIC, 6, struct st_log_query)
#define ST_IOC_GET_DRIFT          _IOR(ST_IOC_MAGIC, 7, struct st_drift_report)

/* 审计严重性等级 */
enum st_severity {
    ST_SEV_INFO     = 0,  /* 信息 */
    ST_SEV_WARN     = 1,  /* 预警 */
    ST_SEV_ALERT    = 2,  /* 告警（需要关注） */
    ST_SEV_CRITICAL = 3,  /* 严重（需立即干预） */
};

/* 倾向漂移方向 */
enum st_drift_direction {
    ST_DRIFT_NEUTRAL    = 0,  /* 中性 */
    ST_DRIFT_TO_BRANCH_A = 1, /* 倾向分支 A */
    ST_DRIFT_TO_BRANCH_B = -1,/* 倾向分支 B */
};

/* ================================================================
 * 2. 数据结构
 * ================================================================ */

/** 分支标识 (A/B) */
enum st_branch {
    ST_BRANCH_A = 0,
    ST_BRANCH_B = 1,
};

/** 单回合结果 */
struct st_round_result {
    u64     round_id;               /* 回合 ID */
    u8      winner;                 /* 获胜分支：0=A, 1=B, 2=平局 */
    s64     score_a;                /* 分支 A 得分 */
    s64     score_b;                /* 分支 B 得分 */
    u64     delta_ns;               /* τA (纳秒): 分支 A 用时 */
    u64     delta_b_ns;             /* τB (纳秒): 分支 B 用时 */
    s64     timestamp_ns;           /* 时间戳 */
    u8      phi_gate_state;         /* Φ-Gate 快照 */
    u8      delta_regime;           /* δ 域快照 */
};

/** 审计日志条目 */
struct st_log_entry {
    struct list_head    list;
    u64                 round_id;
    s64                 timestamp_ns;
    enum st_severity    severity;
    enum st_drift_direction direction;
    s64                 bias_value;     /* 当前偏置值 (×1000) */
    s64                 drift_rate;     /* 漂移速率 (per 100 rounds × 1000) */
    char                message[128];   /* 审计信息 */
};

/** 倾向性统计 */
struct st_tendency_stats {
    u64     total_rounds;           /* 总回合数 */
    u64     wins_a;                 /* 分支 A 胜场 */
    u64     wins_b;                 /* 分支 B 胜场 */
    u64     draws;                  /* 平局 */
    s64     bias_ratio;             /* 偏置比率 (×1000)：1000*(A-B)/(A+B) */
    s64     drift_per_100;          /* 每100回合漂移率 (×1000) */
    s64     avg_score_diff;         /* 平均得分差 (×1000) */
    u64     avg_time_ratio_a_to_b;  /* 平均用时比 τA/τB (×1000) */
    u64     consecutive_same;       /* 连续相同胜者回合数 */
    u8      current_direction;      /* 当前漂移方向 */
    u8      alert_active;           /* 告警是否激活 */
    u32     alert_count;            /* 累计告警次数 */
};

/** 审计报告（完整） */
#define ST_REPORT_TYPE_LEN 64
struct st_audit_report {
    char                report_type[ST_REPORT_TYPE_LEN];
    struct st_tendency_stats stats;
    u64                 report_timestamp_ns;
    u8                  health_status;  /* 0=健康, 1=需关注, 2=异常, 3=严重 */
    u8                  recommendation; /* 0=无, 1=调整κ, 2=重置δ, 3=注入噪声 */
    u32                 log_entry_count;
    u64                 last_alert_round;
};

/** ioctl 阈值配置 */
struct st_threshold_config {
    s64     alert_threshold_bias;   /* 告警偏置阈值 (×1000), 默认 350 */
    s64     warn_threshold_bias;    /* 预警偏置阈值 (×1000), 默认 250 */
    u32     drift_window_size;      /* 漂移计算窗口大小, 默认 100 */
    u8      enable_auto_correction; /* 是否启用自动修正 */
};

/** ioctl 日志查询 */
struct st_log_query {
    u32     offset;                 /* 起始偏移 */
    u32     count;                  /* 请求条数 */
    u32     returned;               /* [OUT] 实际返回条数 */
    struct st_log_entry __user *entries; /* [OUT] 日志条目数组 */
};

/** 漂移报告 */
struct st_drift_report {
    s64     current_bias;           /* 当前偏置 (×1000) */
    s64     drift_rate;             /* 漂移率 (per 100) */
    s64     drift_acceleration;     /* 漂移加速度 */
    u8      direction;              /* 漂移方向 */
    u8      trend;                  /* 趋势：0=收敛, 1=发散, 2=振荡 */
    u32     time_to_alert_rounds;  /* 按当前速率到达告警的预估回合数 */
};

/* ================================================================
 * 3. 滑动窗口 — 倾向漂移计算引擎
 * ================================================================ */

/**
 * st_sliding_window — 用于存储最近 N 回合的结果，计算漂移
 *
 * 核心算法：
 *   bias(t) = (wins_A − wins_B) / (wins_A + wins_B)  [滑动窗口内]
 *   drift(t) = bias(t) − bias(t−Δ)                    [Δ=窗口大小的漂移窗口]
 *   acceleration(t) = drift(t) − drift(t−1)
 *
 * 自动修正策略：
 *   若 |drift| > θ_alert 且 continuous_consecutive > N_safe:
 *     1. 记录告警日志
 *     2. 若 enable_auto_correction，发送修正建议给 κ_reg 或 δ_mem
 *     3. 持续监控，3回合内未恢复则升级为 CRITICAL
 */
struct st_sliding_window {
    struct st_round_result *buffer;     /* 环形缓冲区 */
    u32     head;                       /* 写入指针 */
    u32     count;                      /* 当前有效条目数 */
    u32     size;                       /* 窗口大小 */
    u64     wins_a;
    u64     wins_b;
    u64     draws;
    u32     consecutive_same;           /* 连续相同胜者 */
    u8      last_winner;               /* 上回合胜者 (0=A, 1=B, 2=Draw) */
};

/**
 * st_sliding_window_init — 初始化滑动窗口
 */
static int st_sliding_window_init(struct st_sliding_window *sw, u32 size)
{
    sw->buffer = kzalloc(sizeof(struct st_round_result) * size, GFP_KERNEL);
    if (!sw->buffer)
        return -ENOMEM;
    sw->head = 0;
    sw->count = 0;
    sw->size = size;
    sw->wins_a = 0;
    sw->wins_b = 0;
    sw->draws = 0;
    sw->consecutive_same = 0;
    sw->last_winner = 2; /* 初始：无胜者 */
    return 0;
}

/**
 * st_sliding_window_push — 推入一回合结果
 *
 * 环形缓冲区：如果已满，evict 最旧的条目，减去其统计贡献。
 *
 * @sw:     滑动窗口
 * @result: 新的回合结果
 */
static void st_sliding_window_push(struct st_sliding_window *sw,
                                   const struct st_round_result *result)
{
    struct st_round_result *old;

    /* 如果窗口已满，驱逐最旧条目 */
    if (sw->count == sw->size) {
        u32 old_idx = (sw->head) % sw->size;
        old = &sw->buffer[old_idx];

        if (old->winner == 0)
            sw->wins_a--;
        else if (old->winner == 1)
            sw->wins_b--;
        else
            sw->draws--;
    }

    /* 写入新条目 */
    sw->buffer[sw->head % sw->size] = *result;

    if (result->winner == 0)
        sw->wins_a++;
    else if (result->winner == 1)
        sw->wins_b++;
    else
        sw->draws++;

    /* 更新连续相同胜者计数 */
    if (result->winner != 2 && result->winner == sw->last_winner)
        sw->consecutive_same++;
    else
        sw->consecutive_same = (result->winner != 2) ? 1 : 0;

    sw->last_winner = result->winner;
    sw->head++;

    if (sw->count < sw->size)
        sw->count++;
}

/**
 * st_compute_bias — 计算当前偏置值
 *
 * bias = (wins_A - wins_B) / (wins_A + wins_B) * 1000
 * 正值 → 倾向 A，负值 → 倾向 B，0 → 完全平衡
 *
 * @sw: 滑动窗口
 * @return: bias × 1000，若无足够数据返回 0
 */
static s64 st_compute_bias(struct st_sliding_window *sw)
{
    u64 total = sw->wins_a + sw->wins_b;

    if (total == 0)
        return 0;

    return (s64)((sw->wins_a - sw->wins_b) * 1000) / (s64)total;
}

/**
 * st_compute_drift_rate — 计算漂移速率
 *
 * 在当前窗口内，按子窗口计算偏置变化率。
 * 将窗口分为两半，比较前一半的 bias 与后一半的 bias。
 *
 * drift = (bias_second_half - bias_first_half) / (half_window_size)
 *         × 100 [per 100 rounds]
 *
 * @sw: 滑动窗口
 * @return: drift_rate × 1000
 */
static s64 st_compute_drift_rate(struct st_sliding_window *sw)
{
    u32 half = sw->count / 2;
    u64 wins_a_first = 0, wins_b_first = 0;
    u64 wins_a_second = 0, wins_b_second = 0;
    s64 bias_first, bias_second;
    u32 i;
    struct st_round_result *r;

    if (sw->count < 4)
        return 0;

    /* 前一半 */
    for (i = 0; i < half; i++) {
        u32 idx = (sw->head - sw->count + i) % sw->size;
        r = &sw->buffer[idx];
        if (r->winner == 0)
            wins_a_first++;
        else if (r->winner == 1)
            wins_b_first++;
    }

    /* 后一半 */
    for (i = half; i < sw->count; i++) {
        u32 idx = (sw->head - sw->count + i) % sw->size;
        r = &sw->buffer[idx];
        if (r->winner == 0)
            wins_a_second++;
        else if (r->winner == 1)
            wins_b_second++;
    }

    bias_first = (wins_a_first + wins_b_first > 0)
        ? (s64)((wins_a_first - wins_b_first) * 1000) /
          (s64)(wins_a_first + wins_b_first) : 0;

    bias_second = (wins_a_second + wins_b_second > 0)
        ? (s64)((wins_a_second - wins_b_second) * 1000) /
          (s64)(wins_a_second + wins_b_second) : 0;

    /* drift per 100 rounds */
    return (bias_second - bias_first) * 100 / (s64)(half > 0 ? half : 1);
}

/**
 * st_compute_drift_acceleration — 计算漂移加速度
 *
 * 将窗口分为三份，比较各份的偏置变化率。
 *
 * @sw: 滑动窗口
 * @return: acceleration × 1000 (每100回合²)
 */
static s64 st_compute_drift_acceleration(struct st_sliding_window *sw)
{
    u32 third = sw->count / 3;
    s64 bias_segments[3];
    u32 seg, i;
    struct st_round_result *r;

    if (sw->count < 9)
        return 0;

    for (seg = 0; seg < 3; seg++) {
        u64 wins_a = 0, wins_b = 0;
        u32 start = seg * third;
        u32 end = (seg + 1) * third;

        for (i = start; i < end && i < sw->count; i++) {
            u32 idx = (sw->head - sw->count + i) % sw->size;
            r = &sw->buffer[idx];
            if (r->winner == 0)
                wins_a++;
            else if (r->winner == 1)
                wins_b++;
        }

        bias_segments[seg] = (wins_a + wins_b > 0)
            ? (s64)((wins_a - wins_b) * 1000) / (s64)(wins_a + wins_b) : 0;
    }

    /* acceleration = (Δbias_3 − Δbias_2) - (Δbias_2 − Δbias_1) */
    return ((bias_segments[2] - bias_segments[1]) -
            (bias_segments[1] - bias_segments[0])) * 100 / (s64)(third * third);
}

/**
 * st_determine_trend — 判断漂移趋势
 *
 * @acceleration: 漂移加速度
 * @return: 0=收敛, 1=发散, 2=振荡
 */
static u8 st_determine_trend(s64 acceleration)
{
    s64 abs_acc = acceleration < 0 ? -acceleration : acceleration;
    if (abs_acc < 10)
        return 0; /* 收敛/稳定 */
    if (acceleration > 0)
        return 1; /* 发散（加速漂移） */
    return 2;     /* 振荡（减速漂移） */
}

/**
 * st_destroy_window — 销毁滑动窗口
 */
static void st_destroy_window(struct st_sliding_window *sw)
{
    kfree(sw->buffer);
    sw->buffer = NULL;
    sw->size = 0;
    sw->count = 0;
}

/* ================================================================
 * 4. 审计日志管理
 * ================================================================ */

/**
 * st_auditor_dev — ST Auditor 设备实例
 *
 * 全局单例，管理所有审计状态。
 */
static struct st_auditor_dev {
    struct st_sliding_window    window;
    struct list_head            log_head;       /* 审计日志链表头 */
    u32                         log_count;      /* 当前日志条目数 */
    u32                         log_max;        /* 最大日志条目数 */
    struct st_threshold_config  thresholds;     /* 阈值配置 */
    u32                         alert_count;    /* 累计告警次数 */
    u64                         last_alert_round;
    u8                          alert_active;
    u8                          enable_auto_correction;
    spinlock_t                  lock;           /* 并发保护 */
} st_dev;

/**
 * st_add_log_entry — 添加审计日志条目
 *
 * 如果日志已满，移除最旧的条目（FIFO）。
 *
 * @severity:  严重性等级
 * @direction: 漂移方向
 * @bias:      当前偏置值
 * @drift:     漂移速率
 * @msg:       审计信息
 */
static void st_add_log_entry(enum st_severity severity,
                             enum st_drift_direction direction,
                             s64 bias, s64 drift, const char *msg)
{
    struct st_log_entry *entry;

    if (st_dev.log_count >= st_dev.log_max) {
        /* 移除最旧的条目 */
        struct st_log_entry *old, *tmp;
        list_for_each_entry_safe(old, tmp, &st_dev.log_head, list) {
            list_del(&old->list);
            st_dev.log_count--;
            kfree(old);
            break;
        }
    }

    entry = kzalloc(sizeof(*entry), GFP_KERNEL);
    if (!entry)
        return;

    entry->round_id = st_dev.window.count > 0
        ? st_dev.window.buffer[(st_dev.window.head - 1) % st_dev.window.size].round_id
        : 0;
    entry->timestamp_ns = ktime_get_real_ns();
    entry->severity = severity;
    entry->direction = direction;
    entry->bias_value = bias;
    entry->drift_rate = drift;
    strscpy(entry->message, msg, sizeof(entry->message));

    list_add_tail(&entry->list, &st_dev.log_head);
    st_dev.log_count++;
}

/* ================================================================
 * 5. 核心审计逻辑
 * ================================================================ */

/**
 * st_audit_round — 审计一个推理回合
 *
 * 每次双分支推理完成后调用。执行以下检查：
 *   1. 计算当前 bias
 *   2. 计算 drift rate
 *   3. 判断是否触发告警
 *   4. 若是，记录日志 + 触发修正建议
 *
 * @result: 回合结果
 * @return: 审计严重性
 */
static enum st_severity st_audit_round(const struct st_round_result *result)
{
    s64 bias, drift, acceleration;
    enum st_severity sev = ST_SEV_INFO;
    enum st_drift_direction direction = ST_DRIFT_NEUTRAL;

    /* 推入滑动窗口 */
    st_sliding_window_push(&st_dev.window, result);

    /* 需要足够的数据 */
    if (st_dev.window.count < 4)
        return ST_SEV_INFO;

    /* 计算指标 */
    bias = st_compute_bias(&st_dev.window);
    drift = st_compute_drift_rate(&st_dev.window);
    acceleration = st_compute_drift_acceleration(&st_dev.window);

    /* 确定方向 */
    if (bias > 0)
        direction = ST_DRIFT_TO_BRANCH_A;
    else if (bias < 0)
        direction = ST_DRIFT_TO_BRANCH_B;

    /* 告警判定 */
    if (bias > st_dev.thresholds.alert_threshold_bias ||
        bias < -st_dev.thresholds.alert_threshold_bias) {
        sev = ST_SEV_ALERT;
        st_dev.alert_count++;
        st_dev.last_alert_round = result->round_id;
        st_dev.alert_active = 1;
    } else if (bias > st_dev.thresholds.warn_threshold_bias ||
               bias < -st_dev.thresholds.warn_threshold_bias) {
        sev = ST_SEV_WARN;
    }

    /* 严重判定：连续10+回合同方向漂移 + 发散趋势 */
    if (st_dev.window.consecutive_same >= 10 &&
        st_determine_trend(acceleration) == 1) {
        sev = ST_SEV_CRITICAL;
    }

    /* 记录日志 */
    if (sev >= ST_SEV_WARN) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "Round %llu: bias=%lld drift=%lld accel=%lld dir=%d consec=%u",
                 result->round_id, bias, drift, acceleration,
                 direction, st_dev.window.consecutive_same);
        st_add_log_entry(sev, direction, bias, drift, msg);
    }

    return sev;
}

/**
 * st_get_current_stats — 获取当前倾向性统计
 */
static void st_get_current_stats(struct st_tendency_stats *stats)
{
    memset(stats, 0, sizeof(*stats));

    stats->total_rounds = st_dev.window.count;
    stats->wins_a = st_dev.window.wins_a;
    stats->wins_b = st_dev.window.wins_b;
    stats->draws = st_dev.window.draws;
    stats->bias_ratio = st_compute_bias(&st_dev.window);
    stats->drift_per_100 = st_compute_drift_rate(&st_dev.window);
    stats->consecutive_same = st_dev.window.consecutive_same;

    /* 平均得分差 */
    if (st_dev.window.count > 0) {
        s64 total_diff = 0;
        u32 i;
        for (i = 0; i < st_dev.window.count; i++) {
            u32 idx = (st_dev.window.head - st_dev.window.count + i)
                      % st_dev.window.size;
            struct st_round_result *r = &st_dev.window.buffer[idx];
            total_diff += r->score_a - r->score_b;
        }
        stats->avg_score_diff = total_diff * 1000 / (s64)st_dev.window.count;
    }

    /* 漂移方向 */
    if (stats->bias_ratio > 100)
        stats->current_direction = (u8)ST_DRIFT_TO_BRANCH_A;
    else if (stats->bias_ratio < -100)
        stats->current_direction = (u8)ST_DRIFT_TO_BRANCH_B;
    else
        stats->current_direction = (u8)ST_DRIFT_NEUTRAL;

    stats->alert_active = st_dev.alert_active ? 1 : 0;
    stats->alert_count = st_dev.alert_count;
}

/**
 * st_build_full_report — 构建完整审计报告
 */
static void st_build_full_report(struct st_audit_report *report)
{
    memset(report, 0, sizeof(*report));

    strscpy(report->report_type, "ST_AUDIT_FULL", sizeof(report->report_type));
    st_get_current_stats(&report->stats);
    report->report_timestamp_ns = ktime_get_real_ns();

    /* 健康状态判定 */
    if (st_dev.alert_count > 10)
        report->health_status = 3;  /* 严重 */
    else if (st_dev.alert_active)
        report->health_status = 2;  /* 异常 */
    else if (report->stats.bias_ratio > st_dev.thresholds.warn_threshold_bias ||
             report->stats.bias_ratio < -st_dev.thresholds.warn_threshold_bias)
        report->health_status = 1;  /* 需关注 */
    else
        report->health_status = 0;  /* 健康 */

    /* 修正建议 */
    if (report->health_status == 3) {
        /* 严重：重置 δ 并注入噪声 */
        report->recommendation = 3;
    } else if (report->health_status >= 2) {
        /* 异常：调整 κ 或重置 δ */
        report->recommendation = (report->stats.drift_per_100 > 500) ? 2 : 1;
    } else {
        report->recommendation = 0;
    }

    report->log_entry_count = st_dev.log_count;
    report->last_alert_round = st_dev.last_alert_round;
}

/**
 * st_build_drift_report — 构建漂移报告
 */
static void st_build_drift_report(struct st_drift_report *report)
{
    s64 bias, drift, accel;

    memset(report, 0, sizeof(*report));

    bias = st_compute_bias(&st_dev.window);
    drift = st_compute_drift_rate(&st_dev.window);
    accel = st_compute_drift_acceleration(&st_dev.window);

    report->current_bias = bias;
    report->drift_rate = drift;
    report->drift_acceleration = accel;
    report->direction = (bias > 0) ? (u8)ST_DRIFT_TO_BRANCH_A :
                        (bias < 0) ? (u8)ST_DRIFT_TO_BRANCH_B :
                        (u8)ST_DRIFT_NEUTRAL;
    report->trend = st_determine_trend(accel);

    /* 估算到达告警阈值的回合数 */
    if (drift != 0) {
        s64 target = (report->direction == (u8)ST_DRIFT_TO_BRANCH_A)
            ? st_dev.thresholds.alert_threshold_bias
            : -st_dev.thresholds.alert_threshold_bias;
        s64 gap = target - bias;
        report->time_to_alert_rounds = (u32)(gap * 100 / drift);
        if (report->time_to_alert_rounds > 10000)
            report->time_to_alert_rounds = 0; /* 太远，忽略 */
    }
}

/**
 * st_update_thresholds — 更新阈值配置
 */
static void st_update_thresholds(const struct st_threshold_config *cfg)
{
    if (cfg->alert_threshold_bias > 0)
        st_dev.thresholds.alert_threshold_bias = cfg->alert_threshold_bias;

    if (cfg->warn_threshold_bias > 0)
        st_dev.thresholds.warn_threshold_bias = cfg->warn_threshold_bias;

    if (cfg->drift_window_size > 0)
        st_dev.thresholds.drift_window_size = cfg->drift_window_size;

    st_dev.thresholds.enable_auto_correction = cfg->enable_auto_correction;
    st_dev.enable_auto_correction = cfg->enable_auto_correction;
}

/**
 * st_reset_all — 重置所有审计状态
 */
static void st_reset_all(void)
{
    st_dev.window.head = 0;
    st_dev.window.count = 0;
    st_dev.window.wins_a = 0;
    st_dev.window.wins_b = 0;
    st_dev.window.draws = 0;
    st_dev.window.consecutive_same = 0;
    st_dev.window.last_winner = 2;
    st_dev.alert_count = 0;
    st_dev.alert_active = 0;
    st_dev.last_alert_round = 0;

    /* 清空日志 */
    {
        struct st_log_entry *entry, *tmp;
        list_for_each_entry_safe(entry, tmp, &st_dev.log_head, list) {
            list_del(&entry->list);
            kfree(entry);
        }
        st_dev.log_count = 0;
    }
}

/* ================================================================
 * 6. 字符设备驱动
 * ================================================================ */

static dev_t st_devt;
static struct cdev st_cdev;
static struct class *st_class;

static int st_open(struct inode *inode, struct file *filp)
{
    filp->private_data = &st_dev;
    return 0;
}

static int st_release(struct inode *inode, struct file *filp)
{
    return 0;
}

static long st_ioctl(struct file *filp, unsigned int cmd, unsigned long arg)
{
    struct st_auditor_dev *dev = filp->private_data;
    unsigned long flags;
    int ret = 0;

    if (!dev || _IOC_TYPE(cmd) != ST_IOC_MAGIC)
        return -ENOTTY;

    spin_lock_irqsave(&dev->lock, flags);

    switch (cmd) {
    case ST_IOC_GET_REPORT: {
        struct st_audit_report report;
        st_build_full_report(&report);
        spin_unlock_irqrestore(&dev->lock, flags);
        if (copy_to_user((void __user *)arg, &report, sizeof(report)))
            return -EFAULT;
        return 0;
    }

    case ST_IOC_GET_STATS: {
        struct st_tendency_stats stats;
        st_get_current_stats(&stats);
        spin_unlock_irqrestore(&dev->lock, flags);
        if (copy_to_user((void __user *)arg, &stats, sizeof(stats)))
            return -EFAULT;
        return 0;
    }

    case ST_IOC_SET_THRESH: {
        struct st_threshold_config cfg;
        spin_unlock_irqrestore(&dev->lock, flags);
        if (copy_from_user(&cfg, (void __user *)arg, sizeof(cfg)))
            return -EFAULT;
        spin_lock_irqsave(&dev->lock, flags);
        st_update_thresholds(&cfg);
        spin_unlock_irqrestore(&dev->lock, flags);
        return 0;
    }

    case ST_IOC_RESET_ALL:
        st_reset_all();
        spin_unlock_irqrestore(&dev->lock, flags);
        return 0;

    case ST_IOC_SUBMIT_ROUND: {
        struct st_round_result result;
        spin_unlock_irqrestore(&dev->lock, flags);
        if (copy_from_user(&result, (void __user *)arg, sizeof(result)))
            return -EFAULT;
        spin_lock_irqsave(&dev->lock, flags);
        st_audit_round(&result);
        spin_unlock_irqrestore(&dev->lock, flags);
        return 0;
    }

    case ST_IOC_GET_LOG: {
        struct st_log_query query;
        struct st_log_entry *entry;
        u32 i = 0;

        spin_unlock_irqrestore(&dev->lock, flags);
        if (copy_from_user(&query, (void __user *)arg, sizeof(query)))
            return -EFAULT;
        spin_lock_irqsave(&dev->lock, flags);

        query.returned = 0;
        list_for_each_entry(entry, &dev->log_head, list) {
            if (i >= query.offset && i < query.offset + query.count) {
                if (copy_to_user(&query.entries[query.returned],
                                 entry, sizeof(*entry))) {
                    ret = -EFAULT;
                    break;
                }
                query.returned++;
            }
            i++;
        }

        spin_unlock_irqrestore(&dev->lock, flags);
        if (ret == 0) {
            if (copy_to_user((void __user *)arg, &query, sizeof(query)))
                return -EFAULT;
        }
        return ret;
    }

    case ST_IOC_GET_DRIFT: {
        struct st_drift_report report;
        st_build_drift_report(&report);
        spin_unlock_irqrestore(&dev->lock, flags);
        if (copy_to_user((void __user *)arg, &report, sizeof(report)))
            return -EFAULT;
        return 0;
    }

    default:
        spin_unlock_irqrestore(&dev->lock, flags);
        return -ENOTTY;
    }
}

static const struct file_operations st_fops = {
    .owner          = THIS_MODULE,
    .open           = st_open,
    .release        = st_release,
    .unlocked_ioctl = st_ioctl,
};

/* ================================================================
 * 7. 模块初始化与退出
 * ================================================================ */

/**
 * st_auditor_init — 模块加载
 */
static int __init st_auditor_init(void)
{
    int ret;

    pr_info("[ST Auditor] Initializing TOMAS-AGI Subjective Tendency Auditor v%s\n",
            ST_AUDITOR_VERSION);

    /* 初始化全局状态 */
    memset(&st_dev, 0, sizeof(st_dev));
    ret = st_sliding_window_init(&st_dev.window, ST_DEFAULT_WINDOW_SIZE);
    if (ret) {
        pr_err("[ST Auditor] Failed to allocate sliding window\n");
        return ret;
    }

    INIT_LIST_HEAD(&st_dev.log_head);
    st_dev.log_count = 0;
    st_dev.log_max = ST_MAX_LOG_ENTRIES;
    st_dev.alert_count = 0;
    st_dev.alert_active = 0;
    st_dev.last_alert_round = 0;
    st_dev.enable_auto_correction = 0;
    spin_lock_init(&st_dev.lock);

    /* 默认阈值 */
    st_dev.thresholds.alert_threshold_bias = ST_DEFAULT_ALERT_THRESH * 1000;
    st_dev.thresholds.warn_threshold_bias = ST_DEFAULT_DRIFT_WARN * 1000;
    st_dev.thresholds.drift_window_size = 100;
    st_dev.thresholds.enable_auto_correction = 0;

    /* 分配设备号 */
    ret = alloc_chrdev_region(&st_devt, 0, 1, ST_AUDITOR_NAME);
    if (ret) {
        pr_err("[ST Auditor] alloc_chrdev_region failed: %d\n", ret);
        goto err_window;
    }

    cdev_init(&st_cdev, &st_fops);
    st_cdev.owner = THIS_MODULE;

    ret = cdev_add(&st_cdev, st_devt, 1);
    if (ret) {
        pr_err("[ST Auditor] cdev_add failed: %d\n", ret);
        goto err_devt;
    }

    st_class = class_create(ST_AUDITOR_NAME);
    if (IS_ERR(st_class)) {
        ret = PTR_ERR(st_class);
        pr_err("[ST Auditor] class_create failed: %d\n", ret);
        goto err_cdev;
    }

    if (IS_ERR(device_create(st_class, NULL, st_devt, NULL,
                             ST_AUDITOR_NAME))) {
        ret = PTR_ERR(device_create(st_class, NULL, st_devt, NULL,
                                    ST_AUDITOR_NAME));
        pr_err("[ST Auditor] device_create failed: %d\n", ret);
        goto err_class;
    }

    pr_info("[ST Auditor] Ready — dev=/dev/%s, window=%u, alert_thresh=%lld, warn_thresh=%lld\n",
            ST_AUDITOR_NAME,
            ST_DEFAULT_WINDOW_SIZE,
            st_dev.thresholds.alert_threshold_bias,
            st_dev.thresholds.warn_threshold_bias);

    return 0;

err_class:
    class_destroy(st_class);
err_cdev:
    cdev_del(&st_cdev);
err_devt:
    unregister_chrdev_region(st_devt, 1);
err_window:
    st_destroy_window(&st_dev.window);
    return ret;
}

/**
 * st_auditor_exit — 模块卸载
 */
static void __exit st_auditor_exit(void)
{
    pr_info("[ST Auditor] Shutting down...\n");

    device_destroy(st_class, st_devt);
    class_destroy(st_class);
    cdev_del(&st_cdev);
    unregister_chrdev_region(st_devt, 1);

    /* 清空日志 */
    {
        struct st_log_entry *entry, *tmp;
        list_for_each_entry_safe(entry, tmp, &st_dev.log_head, list) {
            list_del(&entry->list);
            kfree(entry);
        }
    }

    st_destroy_window(&st_dev.window);

    pr_info("[ST Auditor] Module removed. Total alerts: %u\n",
            st_dev.alert_count);
}

module_init(st_auditor_init);
module_exit(st_auditor_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("齐活林 (Qi)");
MODULE_DESCRIPTION("TOMAS-AGI ST Auditor — Subjective Tendency Audit Kernel Module");
MODULE_VERSION(ST_AUDITOR_VERSION);
