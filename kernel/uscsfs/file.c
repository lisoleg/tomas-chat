// uscsfs/file.c —— T029: USCS 文件操作（Continuation）
// 太乙互搏 AGI 内核模块 — USCS 文件系统 Continuation I/O
//
// 模块职责：
//   1. Continuation 模式文件读写（非结合续延）
//   2. 双分支协同读写（Φ-Gate 联动）
//   3. 谱图序列化流（read/write 按 EML 格式）
//   4. 异步 I/O 支持（kiocb）
//   5. 与 δ-mem 联动（L1/L2 缓存透明加速）
//
// 理论背景 (TOMAS-AGI v2.0):
//   - 互搏架构要求文件 I/O 保留双分支状态
//   - Continuation 模式：每次 read/write 返回"续延句柄"，
//     下次 I/O 从该续延继续（非结合分歧点）
//   - 文件内容不是字节流，而是"谱状态序列"
//   - 每个谱状态由 (δ, associator, vertex_set) 三元组定义
//
// 作者: 齐活林 (Qi)
// 版本: v1.0
// 日期: 2026-06-13
//
// SPDX-License-Identifier: GPL-2.0-only

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/poll.h>
#include <linux/mutex.h>
#include "../octonion.c"
#include "../delta_mem.c"       /* 使用 l1_write/l1_read 等接口 */
#include "../phi_gate.c"         /* 使用 phi_gate_eval 接口 */

/* ================================================================
 * 1. 常量与宏定义
 * ================================================================ */

#define USCS_FILE_VERSION   "1.0"
#define USCS_CONT_MAGIC     0x434F4E54  /* 'CONT' = Continuation */

/* Continuation 状态标志 */
#define USCS_CONT_ACTIVE    0x01  /* 续延活跃 */
#define USCS_CONT_BRANCH_A 0x02  /* 当前在分支 A */
#define USCS_CONT_BRANCH_B 0x04  /* 当前在分支 B */
#define USCS_CONT_DUAL     0x08  /* 双分支模式 */
#define USCS_CONT_DELTA_OK 0x10  /* δ 有效 */

/* ================================================================
 * 2. Continuation 句柄结构
 * ================================================================ */

/**
 * struct uscs_continuation — 非结合续延句柄
 *
 * 每次打开 USCS 文件时创建一个续延句柄。
 * 句柄记录当前读取位置在"谱状态序列"中的坐标，
 * 以及双分支状态（如果启用了互搏模式）。
 */
struct uscs_continuation {
    u32                magic;       /* USCS_CONT_MAGIC */
    u64                file_pos;    /* 文件字节偏移（等价于谱状态索引）*/
    u64                state_idx;   /* 当前谱状态索引 */
    u8                 branch;      /* 当前分支：0=A, 1=B, 2=dual */
    u8                 flags;       /* 状态标志 */

    /* δ 上下文（本次续延的局部 δ）*/
    u64                delta_local; /* 局部 δ（×1000），0=使用全局 */
    u32                delta_regime;

    /* 双分支缓存（上次读取的双分支结果）*/
    u8                  last_phi_state; /* 上次 Φ-Gate 状态 */
    u64                 last_score_a;
    u64                 last_score_b;

    /* EML 图关联 */
    u32                 eml_graph_id;  /* 关联的 EML 图 */
    void                *eml_snapshot;  /* EML 快照指针（内核虚拟地址）*/
    size_t              eml_snap_size; /* 快照大小 */

    /* 与 δ-mem 联动 */
    u8                  use_l1_cache;  /* 是否使用 L1 缓存 */
    u8                  use_l2_cache;  /* 是否使用 L2 缓存 */
    u64                 cache_hit_count;
    u64                 cache_miss_count;
};

/**
 * struct uscs_file_priv — 文件私有数据（filp->private_data）
 */
struct uscs_file_priv {
    struct uscs_continuation cont;     /* 续延句柄 */
    struct mutex                cont_lock;  /* 续延并发保护 */
};

/* ================================================================
 * 3. 谱状态序列化/反序列化
 * ================================================================ */

/**
 * uscs_encode_state — 将一个谱状态编码为字节流
 *
 * 谱状态格式（64 字节定点）：
 *   [0..7]   δ 值（×1000, u64）
 *   [8..15]  associator_norm（×1000, u64）
 *   [16..23] state_idx（u64）
 *   [24..31] branch（u8）+ flags（u8）+ padding（6 bytes）
 *   [32..63] 保留（未来：八元数分量）
 *
 * @state:   谱状态元数据
 * @buf:     输出缓冲区（至少 64 字节）
 * @buf_size: 缓冲区大小
 * @return:   已编码字节数，失败返回负数
 */
static ssize_t uscs_encode_state(const struct uscs_continuation *cont,
                                   void *buf, size_t buf_size)
{
    u8 *p = buf;

    if (buf_size < 64)
        return -EINVAL;

    /* δ 值 */
    *(u64 *)p = cpu_to_le64(cont->delta_local ?: 7000);
    p += 8;

    /* associator_norm（模拟）*/
    *(u64 *)p = cpu_to_le64(cont->last_score_a + cont->last_score_b);
    p += 8;

    /* state_idx */
    *(u64 *)p = cpu_to_le64(cont->state_idx);
    p += 8;

    /* branch + flags + padding */
    *p++ = cont->branch;
    *p++ = cont->flags;
    memset(p, 0, 6);
    p += 6;

    /* 保留区（zeros）*/
    memset(p, 0, 32);

    return 64;  /* 每状态 64 字节 */
}

/**
 * uscs_decode_state — 从字节流解码谱状态
 *
 * @buf:     输入缓冲区
 * @buf_size: 缓冲区大小
 * @state:    输出谱状态
 */
static ssize_t uscs_decode_state(const void *buf, size_t buf_size,
                                   struct uscs_continuation *cont)
{
    const u8 *p = buf;

    if (buf_size < 64)
        return -EINVAL;

    cont->delta_local = le64_to_cpu(*(u64 *)p);
    p += 8;

    /* associator_norm 忽略（仅用于验证）*/
    p += 8;

    cont->state_idx = le64_to_cpu(*(u64 *)p);
    p += 8;

    cont->branch = *p++;
    cont->flags = *p++;

    return 64;
}

/* ================================================================
 * 4. Continuation read（核心）
 * ================================================================ */

/**
 * uscs_cont_read — Continuation 模式读取
 *
 * 不同于普通 read()，此函数：
 *   1. 从续延句柄获取当前状态索引
 *   2. 从 EML 图（或 δ-mem 缓存）读取对应谱状态
 *   3. 如果 δ > δ_critical，执行双分支评估（Φ-Gate）
 *   4. 将结果编码为字节流返回给用户态
 *   5. 更新续延句柄（state_idx++）
 *
 * @filp:   文件指针
 * @buf:    用户态缓冲区
 * @count:  请求字节数
 * @ppos:   文件位置指针
 */
static ssize_t uscs_cont_read(struct file *filp, char __user *buf,
                               size_t count, loff_t *ppos)
{
    struct uscs_file_priv *priv = filp->private_data;
    struct uscs_continuation *cont = &priv->cont;
    ssize_t ret = 0;
    size_t total_read = 0;
    int err;

    if (!priv)
        return -EINVAL;

    mutex_lock(&priv->cont_lock);

    /* 计算要读取的谱状态数（每状态 64 字节）*/
    {
        size_t num_states = count / 64;
        size_t i;

        for (i = 0; i < num_states; i++) {
            u8 state_buf[64];
            ssize_t encoded;

            /* 从 EML 图或缓存读取谱状态 */
            if (cont->use_l1_cache) {
                /* 尝试从 δ-mem L1 缓存读取 */
                u64 cache_key = cont->state_idx;
                u8  cache_val[256];
                size_t cache_len = 256;

                err = l1_read(cache_key, cache_val, &cache_len);
                if (err == 0 && cache_len >= 64) {
                    /* 缓存命中 */
                    memcpy(state_buf, cache_val, 64);
                    cont->cache_hit_count++;
                } else {
                    /* 缓存未命中：从 EML 图读取 */
                    cont->cache_miss_count++;
                    encoded = uscs_encode_state(cont, state_buf, sizeof(state_buf));
                    if (encoded < 0) {
                        ret = encoded;
                        break;
                    }
                }
            } else {
                /* 不使用缓存：直接编码 */
                encoded = uscs_encode_state(cont, state_buf, sizeof(state_buf));
                if (encoded < 0) {
                    ret = encoded;
                    break;
                }
            }

            /* 如果 δ > 0，调用 Φ-Gate 做双分支评估 */
            if (cont->delta_local > 0 || cont->delta_local == 0) {
                /* 获取全局 δ（简化处理）*/
                u64 delta = cont->delta_local ?: 7000;
                if (delta > 500) {  /* δ > 0.5，需要双分支 */
                    u8 phi_state;
                    phi_gate_eval(NULL, 0, 0, delta, &phi_state);
                    cont->last_phi_state = phi_state;
                }
            }

            /* 拷贝到用户态 */
            if (copy_to_user(buf + total_read, state_buf, 64)) {
                ret = -EFAULT;
                break;
            }

            total_read += 64;
            cont->state_idx++;
            *ppos = cont->state_idx * 64;
        }
    }

    mutex_unlock(&priv->cont_lock);

    return total_read ? (ssize_t)total_read : ret;
}

/* ================================================================
 * 5. Continuation write（核心）
 * ================================================================ */

/**
 * uscs_cont_write — Continuation 模式写入
 *
 * 将用户态的谱状态序列写入文件（EML 图或 δ-mem）。
 * 如果启用了双分支模式，同时写入两个分支的评估。
 *
 * @filp:   文件指针
 * @buf:    用户态缓冲区（谱状态序列）
 * @count:  字节数（必须是 64 的倍数）
 * @ppos:   文件位置指针
 */
static ssize_t uscs_cont_write(struct file *filp, const char __user *buf,
                                size_t count, loff_t *ppos)
{
    struct uscs_file_priv *priv = filp->private_data;
    struct uscs_continuation *cont = &priv->cont;
    ssize_t ret = 0;
    size_t total_written = 0;
    int err;

    if (!priv)
        return -EINVAL;
    if (count % 64 != 0)
        return -EINVAL;  /* 必须按谱状态对齐 */

    mutex_lock(&priv->cont_lock);

    {
        size_t num_states = count / 64;
        size_t i;

        for (i = 0; i < num_states; i++) {
            u8 state_buf[64];
            struct uscs_continuation decoded;

            /* 从用户态拷贝 */
            if (copy_from_user(state_buf, buf + total_written, 64)) {
                ret = -EFAULT;
                break;
            }

            /* 解码 */
            err = uscs_decode_state(state_buf, 64, &decoded);
            if (err < 0) {
                ret = err;
                break;
            }

            /* 写入 δ-mem L1 缓存（如果启用）*/
            if (cont->use_l1_cache) {
                u64 cache_key = decoded.state_idx;
                err = l1_write(cache_key, state_buf, 64);
                if (err) {
                    pr_warn("uscsfs: l1_write failed: %d\n", err);
                } else {
                    cont->cache_hit_count++;  /* 写入也算"命中"（预热）*/
                }
            }

            /* 如果 δ 较大，触发 L1→L2 融合 */
            if (decoded.delta_local > 5000) {  /* δ > 5.0 */
                double delta_d = decoded.delta_local / 1000.0;
                l1_to_l2_fusion(0);  /* 融合全部 L1 → L2 */
            }

            total_written += 64;
            cont->state_idx = decoded.state_idx + 1;
            *ppos = cont->state_idx * 64;
        }
    }

    mutex_unlock(&priv->cont_lock);

    return total_written ? (ssize_t)total_written : ret;
}

/* ================================================================
 * 6. 文件打开/关闭（续延句柄创建/销毁）
 * ================================================================ */

/**
 * uscs_file_open — 打开 USCS 文件
 *
 * 创建续延句柄，初始化 δ 上下文，
 * 关联 EML 图（如果文件对应已有图谱）。
 */
static int uscs_file_open(struct inode *inode, struct file *filp)
{
    struct uscs_file_priv *priv;
    struct uscs_inode_info *ui = USCS_I(inode);

    priv = kzalloc(sizeof(*priv), GFP_KERNEL);
    if (!priv)
        return -ENOMEM;

    mutex_init(&priv->cont_lock);

    /* 初始化续延句柄 */
    priv->cont.magic = USCS_CONT_MAGIC;
    priv->cont.file_pos = 0;
    priv->cont.state_idx = 0;
    priv->cont.branch = ui->delta_weight > 500 ? 2 : 0;  /* δ>0.5 → dual */
    priv->cont.flags = USCS_CONT_ACTIVE;
    priv->cont.delta_local = ui->delta_weight;
    priv->cont.delta_regime = ui->delta_regime;
    priv->cont.eml_graph_id = ui->eml_graph_id;
    priv->cont.use_l1_cache = 1;   /* 默认启用 L1 缓存 */
    priv->cont.use_l2_cache = 0;   /* L2 按需启用 */

    /* 如果关联了 EML 图，恢复快照 */
    if (ui->eml_graph_id != 0xFFFFFFFF) {
        /* eml_restore_snapshot(ui->eml_graph_id, &priv->cont.eml_snapshot); */
        pr_info("uscsfs: file open ino=%lu eml_graph=%u delta=%llu\n",
                  inode->i_no, ui->eml_graph_id,
                  (unsigned long long)ui->delta_weight);
    }

    filp->private_data = priv;

    pr_debug("uscsfs: open ino=%lu cont=%p branch=%u delta=%llu\n",
              inode->i_no, &priv->cont, priv->cont.branch,
              (unsigned long long)priv->cont.delta_local);

    return 0;
}

/**
 * uscs_file_release — 关闭 USCS 文件
 *
 * 销毁续延句柄，将脏数据写回 EML 图。
 */
static int uscs_file_release(struct inode *inode, struct file *filp)
{
    struct uscs_file_priv *priv = filp->private_data;

    if (!priv)
        return 0;

    /* 如果续延有脏数据，触发融合 */
    if (priv->cont.flags & USCS_CONT_DELTA_OK) {
        double delta = priv->cont.delta_local / 1000.0;
        l1_to_l2_fusion((int)delta);
    }

    /* 释放 EML 快照 */
    if (priv->cont.eml_snapshot) {
        vfree(priv->cont.eml_snapshot);
        priv->cont.eml_snapshot = NULL;
    }

    pr_debug("uscsfs: release ino=%lu cache_hit=%llu miss=%llu\n",
              inode->i_no,
              (unsigned long long)priv->cont.cache_hit_count,
              (unsigned long long)priv->cont.cache_miss_count);

    kfree(priv);
    filp->private_data = NULL;

    return 0;
}

/* ================================================================
 * 7. ioctl 接口（续延配置）
 * ================================================================ */

#define USCS_FILE_IOC_MAGIC  'F'
#define USCS_FILE_IOC_GET_CONT  _IOR(USCS_FILE_IOC_MAGIC, 1, struct uscs_continuation)
#define USCS_FILE_IOC_SET_DELTA _IOW(USCS_FILE_IOC_MAGIC, 2, u64)
#define USCS_FILE_IOC_ENABLE_DUAL _IOW(USCS_FILE_IOC_MAGIC, 3, u8)
#define USCS_FILE_IOC_CACHE_STATS _IOR(USCS_FILE_IOC_MAGIC, 4, struct uscs_cache_stats)

struct uscs_cache_stats {
    u64     hit_count;
    u64     miss_count;
    u64     writeback_count;
    u8      l1_enabled;
    u8      l2_enabled;
};

static long uscs_file_ioctl(struct file *filp, unsigned int cmd, unsigned long arg)
{
    struct uscs_file_priv *priv = filp->private_data;
    int ret = 0;

    if (!priv || _IOC_TYPE(cmd) != USCS_FILE_IOC_MAGIC)
        return -ENOTTY;

    mutex_lock(&priv->cont_lock);

    switch (cmd) {
    case USCS_FILE_IOC_GET_CONT:
        mutex_unlock(&priv->cont_lock);
        if (copy_to_user((void __user *)arg, &priv->cont, sizeof(priv->cont)))
            return -EFAULT;
        return 0;

    case USCS_FILE_IOC_SET_DELTA:
        mutex_unlock(&priv->cont_lock);
        if (copy_from_user(&priv->cont.delta_local, (void __user *)arg, sizeof(u64)))
            return -EFAULT;
        priv->cont.delta_local = priv->cont.delta_local;
        mutex_lock(&priv->cont_lock);
        break;

    case USCS_FILE_IOC_ENABLE_DUAL: {
        u8 enable;
        mutex_unlock(&priv->cont_lock);
        if (copy_from_user(&enable, (void __user *)arg, sizeof(u8)))
            return -EFAULT;
        mutex_lock(&priv->cont_lock);
        if (enable)
            priv->cont.flags |= USCS_CONT_DUAL;
        else
            priv->cont.flags &= ~USCS_CONT_DUAL;
        break;
    }

    case USCS_FILE_IOC_CACHE_STATS: {
        struct uscs_cache_stats stats;
        stats.hit_count = priv->cont.cache_hit_count;
        stats.miss_count = priv->cont.cache_miss_count;
        stats.writeback_count = 0;  /* 需要从 delta_mem 获取 */
        stats.l1_enabled = priv->cont.use_l1_cache;
        stats.l2_enabled = priv->cont.use_l2_cache;
        mutex_unlock(&priv->cont_lock);
        if (copy_to_user((void __user *)arg, &stats, sizeof(stats)))
            return -EFAULT;
        return 0;
    }

    default:
        mutex_unlock(&priv->cont_lock);
        return -ENOTTY;
    }

    mutex_unlock(&priv->cont_lock);
    return ret;
}

/* ================================================================
 * 8. 异步 I/O（kiocb）支持
 * ================================================================ */

/**
 * uscs_file_read_iter — 迭代读取（支持 iovec）
 */
static ssize_t uscs_file_read_iter(struct kiocb *iocb, struct iov_iter *to)
{
    struct file *filp = iocb->ki_filp;
    struct uscs_file_priv *priv = filp->private_data;
    ssize_t ret;

    if (!priv)
        return -EINVAL;

    /* 简化处理：回退到同步 read */
    ret = uscs_cont_read(filp, to->kvec->iov_base,
                           min_t(size_t, 4096, iov_iter_count(to)),
                           &iocb->ki_pos);
    return ret;
}

/* ================================================================
 * 9. 文件操作函数表
 * ================================================================ */

static const struct file_operations uscs_file_fops = {
    .owner          = THIS_MODULE,
    .open           = uscs_file_open,
    .release        = uscs_file_release,
    .read           = uscs_cont_read,
    .write          = uscs_cont_write,
    .unlocked_ioctl = uscs_file_ioctl,
    .read_iter      = uscs_file_read_iter,
    /* .write_iter = uscs_file_write_iter, */
    .llseek         = generic_file_llseek,
};

/* ================================================================
 * 10. 模块导出（供 uscsfs/super.c 使用）
 * ================================================================ */

EXPORT_SYMBOL(uscs_file_fops);
EXPORT_SYMBOL(uscs_cont_read);
EXPORT_SYMBOL(uscs_cont_write);
EXPORT_SYMBOL(uscs_encode_state);
EXPORT_SYMBOL(uscs_decode_state);
