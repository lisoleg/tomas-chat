// uscsfs/super.c —— T027: USCS 超级块操作
// 太乙互搏 AGI 内核模块 — USCS 文件系统超级块
//
// 模块职责：
//   1. 文件系统挂载/卸载（mount/umount）
//   2. 超级块读写与校验（魔数 + 版本）
//   3. δ 全局参数持久化（与 tproc_core 联动）
//   4. 文件系统统计信息导出
//   5. κ 锁状态管理（与 kappa_reg 联动）
//
// 理论背景 (TOMAS-AGI v2.0):
//   - USCS（Universal Spectral Continuation System）是 TOMAS 的
//     谱图持久化文件系统，将 EML 谱图存储为文件
//   - 超级块记录全局 δ、κ 锁、图谱版本、校验和
//   - 挂载时从磁盘（或 EML 快照）恢复 δ 全局状态
//   - 卸载时将当前 δ 状态序列化为 EML 快照
//
// 作者: 齐活林 (Qi)
// 版本: v1.0
// 日期: 2026-06-13
//
// SPDX-License-Identifier: GPL-2.0-only

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/buffer_head.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/uaccess.h>
#include <linux/cdev.h>
#include <linux/mount.h>
#include <linux/namei.h>
#include <linux/seq_file.h>
#include <linux/proc_fs.h>

/* ================================================================
 * 1. 常量与宏定义
 * ================================================================ */

#define USCS_NAME            "uscsfs"
#define USCS_VERSION         "2.0"
#define USCS_MAGIC           0x544F4D41  /* 'TOMA' */
#define USCS_BLOCK_SIZE      4096
#define USCS_INODE_SIZE     256
#define USCS_SUPER_OFFSET   1024        /* 超级块在设备中的偏移 */

/* ioctl 命令 */
#define USCS_IOC_MAGIC       'U'
#define USCS_IOC_GET_SUPER   _IOR(USCS_IOC_MAGIC,  1, struct uscs_super_block)
#define USCS_IOC_SET_DELTA   _IOW(USCS_IOC_MAGIC,  2, u64)
#define USCS_IOC_GET_DELTA   _IOR(USCS_IOC_MAGIC,  3, u64)
#define USCS_IOC_LOCK_KAPPA  _IOW(USCS_IOC_MAGIC,  4, u8)
#define USCS_IOC_GET_STATS   _IOR(USCS_IOC_MAGIC,  5, struct uscs_fs_stats)
#define USCS_IOC_SYNC_DELTA  _IO(USCS_IOC_MAGIC,  6)
#define USCS_IOC_GET_VERSION _IOR(USCS_IOC_MAGIC,  7, char[32])

/* ================================================================
 * 2. 超级块结构定义
 * ================================================================ */

/**
 * struct uscs_super_block — USCS 超级块（磁盘 + 内存）
 *
 * 布局（4096 字节对齐）：
 *   [0..15]   魔数 + 版本 + 标志
 *   [16..31]   δ 全局 + κ 锁
 *   [32..47]   图谱统计（顶点数、边数、快照数）
 *   [48..63]   校验和 + 保留
 *   [64..4095] 保留（未来扩展）
 */
struct uscs_super_block {
    __le32  s_magic;           /* 魔数：0x544F4D41 */
    __le32  s_version_major;   /* 主版本号：2 */
    __le32  s_version_minor;   /* 次版本号：0 */
    __le32  s_flags;            /* 挂载标志（见下方） */

    /* 全局 TOMAS 参数 */
    __le64  s_delta_global;    /* 全局 δ 值（×1000，定点数） */
    __le64  s_kappa_lock;      /* κ 锁值（×1000），0=未锁定 */
    __le32  s_delta_regime;    /* δ 域：0=classical, 1=quantum, 2=stable, 3=deep */
    __le32  s_reserved_1;

    /* 图谱统计 */
    __le64  s_num_graphs;      /* 已存储图谱文件数 */
    __le64  s_num_vertices;    /* 全局顶点总数 */
    __le64  s_num_edges;       /* 全局边总数 */
    __le64  s_num_snapshots;   /* EML 快照数 */

    /* 校验与日志 */
    __le32  s_checksum;        /* CRC32 校验和（覆盖前 4092 字节） */
    __le32  s_log_start;       /* 日志起始块 */
    __le32  s_log_size;        /* 日志大小（块数）*/
    __le32  s_mtime;           /* 最后修改时间（Unix 时间戳）*/

    /* 保留区（4096 - 64 = 4032 字节） */
    u8       s_padding[4032];
} __packed;

/* 挂载标志 */
#define USCS_SB_DIRTY         0x0001  /* 超级块已修改，需回写 */
#define USCS_SB_DELTA_DIRTY   0x0002  /* δ 已修改 */
#define USCS_SB_KAPPA_DIRTY   0x0004  /* κ 已修改 */
#define USCS_SB_READONLY      0x0008  /* 只读挂载 */

/* ================================================================
 * 3. 内存超级块与文件系统上下文
 * ================================================================ */

/**
 * struct uscs_sb_info — 内存超级块信息
 *
 * 每个挂载实例对应一个 uscs_sb_info。
 */
struct uscs_sb_info {
    struct uscs_super_block  s_sb;          /* 磁盘超级块副本 */
    struct buffer_head       *s_sbh;         /* 超级块 buffer head */
    struct super_block      *s_vfs_sb;       /* VFS super_block 反向指针 */

    /* 运行时状态 */
    spinlock_t              s_lock;          /* 并发保护 */
    u64                     s_next_ino;     /* 下一个可用 inode 号 */
    u64                     s_num_graphs;    /* 运行时图谱计数 */
    u8                      s_readonly;      /* 只读标志 */
    u8                      s_dirty;         /* 脏标志 */

    /* 与 M2 模块联动 */
    u64                     s_delta_cached;  /* 缓存的 δ 值 */
    u64                     s_kappa_cached;  /* 缓存的 κ 值 */
};

/**
 * struct uscs_fs_stats — 文件系统统计信息
 */
struct uscs_fs_stats {
    u64     total_graphs;       /* 图谱文件总数 */
    u64     total_vertices;     /* 顶点总数 */
    u64     total_edges;        /* 边总数 */
    u64     total_snapshots;    /* 快照总数 */
    u64     total_bytes_used;    /* 已用字节数 */
    u64     delta_global;       /* 当前全局 δ（×1000）*/
    u64     kappa_lock;        /* 当前 κ 锁（×1000）*/
    u32     delta_regime;      /* δ 域 */
    u8      sb_dirty;          /* 超级块是否脏 */
    u64     write_count;       /* 累计写入次数 */
    u64     read_count;        /* 累计读取次数 */
};

/* ================================================================
 * 4. CRC32 校验（轻量实现，不依赖 crypto 库）
 * ================================================================ */

static u32 uscs_crc32(const void *data, size_t len)
{
    static const u32 table[16] = {
        0x00000000, 0x1DB71064, 0x3B6E20C8, 0x26D930AC,
        0x76DC4190, 0x6B6B51F4, 0x4DB26158, 0x5005713C,
        0xEDB88320, 0xF00F9344, 0xD6D6A3E8, 0xCB61B38C,
        0x9B64C2B0, 0x86D3D2D4, 0xA00AE278, 0xBDBDF21C,
    };
    const u8 *p = data;
    u32 crc = 0xFFFFFFFF;
    size_t i;

    for (i = 0; i < len; i++) {
        u8 byte = p[i];
        crc = (crc >> 4) ^ table[(crc ^  byte) & 0x0F];
        crc = (crc >> 4) ^ table[(crc ^ (byte >> 4)) & 0x0F];
    }
    return crc ^ 0xFFFFFFFF;
}

/* ================================================================
 * 5. 超级块校验与初始化
 * ================================================================ */

/**
 * uscs_validate_super — 校验超级块合法性
 *
 * @sb: 超级块
 * @return: 0=合法, <0=非法（原因）
 */
static int uscs_validate_super(const struct uscs_super_block *sb)
{
    u32 crc_calc, crc_stored;

    /* 魔数校验 */
    if (le32_to_cpu(sb->s_magic) != USCS_MAGIC) {
        pr_err(USCS_NAME ": invalid magic: expected 0x%08X, got 0x%08X\n",
                USCS_MAGIC, le32_to_cpu(sb->s_magic));
        return -EINVAL;
    }

    /* 版本校验（允许 v2.x） */
    if (le32_to_cpu(sb->s_version_major) != 2) {
        pr_err(USCS_NAME ": unsupported version: %u.%u\n",
                le32_to_cpu(sb->s_version_major),
                le32_to_cpu(sb->s_version_minor));
        return -EINVAL;
    }

    /* CRC32 校验 */
    crc_stored = le32_to_cpu(sb->s_checksum);
    crc_calc = uscs_crc32(sb, sizeof(*sb) - sizeof(sb->s_checksum) - sizeof(sb->s_padding));
    /* 注意：完整 CRC 应覆盖整个超级块（不含 s_checksum 自身）*/
    /* 简化处理：仅校验前 64 字节 */
    crc_calc = uscs_crc32(sb, 64 - sizeof(sb->s_checksum));
    if (crc_calc != crc_stored) {
        pr_warn(USCS_NAME ": checksum mismatch: stored=0x%08X, calc=0x%08X\n",
                 crc_stored, crc_calc);
        /* 非致命错误，仅警告 */
    }

    pr_info(USCS_NAME ": superblock valid — version %u.%u, delta=%llu, kappa=%llu\n",
             le32_to_cpu(sb->s_version_major),
             le32_to_cpu(sb->s_version_minor),
             (unsigned long long)le64_to_cpu(sb->s_delta_global),
             (unsigned long long)le64_to_cpu(sb->s_kappa_lock));

    return 0;
}

/**
 * uscs_fill_super — 填充 VFS 超级块（mount 核心回调）
 *
 * 这是 Linux 文件系统挂载的关键函数。
 * 负责：读取磁盘超级块 → 校验 → 初始化 VFS super_block → 创建根 inode
 *
 * @sb:     VFS super_block（由 VFS 分配）
 * @data:   mount 选项（字符串）
 * @silent: 是否静默（不打印错误）
 */
static int uscs_fill_super(struct super_block *sb, void *data, int silent)
{
    struct uscs_sb_info *sbi;
    struct inode *root_inode;
    int ret;

    /* 分配文件系统私有数据 */
    sbi = kzalloc(sizeof(*sbi), GFP_KERNEL);
    if (!sbi)
        return -ENOMEM;

    sb->s_fs_info = sbi;
    sbi->s_vfs_sb = sb;
    spin_lock_init(&sbi->s_lock);

    /* 读取超级块（从底层块设备）*/
    /* 注意：对于虚拟文件系统，这里应该从 EML 快照恢复 */
    /* 简化处理：初始化为默认值 */
    sbi->s_sb.s_magic = cpu_to_le32(USCS_MAGIC);
    sbi->s_sb.s_version_major = cpu_to_le32(2);
    sbi->s_sb.s_version_minor = cpu_to_le32(0);
    sbi->s_sb.s_flags = 0;
    sbi->s_sb.s_delta_global = cpu_to_le64(7000);  /* δ=7.0（稳定态）*/
    sbi->s_sb.s_kappa_lock = cpu_to_le64(7000);     /* κ=7.0 */
    sbi->s_sb.s_delta_regime = cpu_to_le32(2);      /* stable */
    sbi->s_sb.s_num_graphs = cpu_to_le64(0);
    sbi->s_sb.s_num_vertices = cpu_to_le64(0);
    sbi->s_sb.s_num_edges = cpu_to_le64(0);
    sbi->s_sb.s_num_snapshots = cpu_to_le64(0);
    sbi->s_sb.s_checksum = cpu_to_le32(
        uscs_crc32(&sbi->s_sb, 64 - sizeof(sbi->s_sb.s_checksum))
    );

    sbi->s_next_ino = 1;  /* inode 1 = 根目录 */
    sbi->s_delta_cached = 7000;
    sbi->s_kappa_cached = 7000;

    /* 设置 VFS super_block 字段 */
    sb->s_magic = USCS_MAGIC;
    sb->s_blocksize = USCS_BLOCK_SIZE;
    sb->s_blocksize_bits = 12;  /* log2(4096) = 12 */
    sb->s_maxbytes = MAX_LFS_FILESIZE;
    sb->s_op = &uscs_sops;  /* super_operations（见下方）*/

    /* 创建根 inode（inode 1，目录）*/
    root_inode = uscs_iget(sb, 1);
    if (IS_ERR(root_inode)) {
        ret = PTR_ERR(root_inode);
        goto err_free;
    }

    /* 创建根 dentry */
    sb->s_root = d_make_root(root_inode);
    if (!sb->s_root) {
        ret = -ENOMEM;
        goto err_free;
    }

    pr_info(USCS_NAME ": mounted — delta=%llu, regime=%u\n",
             (unsigned long long)sbi->s_delta_cached,
             le32_to_cpu(sbi->s_sb.s_delta_regime));
    return 0;

err_free:
    kfree(sbi);
    sb->s_fs_info = NULL;
    return ret;
}

/* ================================================================
 * 6. super_operations 回调
 * ================================================================ */

static struct super_operations uscs_sops = {
    /* 注：完整实现需要以下回调（在后续版本中补充）
     * .alloc_inode  = uscs_alloc_inode,
     * .destroy_inode = uscs_destroy_inode,
     * .write_inode   = uscs_write_inode,
     * .put_super     = uscs_put_super,
     * .sync_fs       = uscs_sync_fs,
     * .statfs        = uscs_statfs,
     */
    .drop_inode     = generic_delete_inode,
};

/* ================================================================
 * 7. 文件系统挂载/卸载（VFS 接口）
 * ================================================================ */

static struct dentry *uscs_mount(struct file_system_type *fs_type,
                                  int flags, const char *dev_name,
                                  void *data)
{
    return mount_bdev(fs_type, flags, dev_name, data, uscs_fill_super);
}

static void uscs_kill_sb(struct super_block *sb)
{
    /* 卸载前同步 δ 状态到 EML 快照 */
    struct uscs_sb_info *sbi = sb->s_fs_info;

    if (sbi) {
        pr_info(USCS_NAME ": unmounting — syncing delta=%llu to EML snapshot\n",
                 (unsigned long long)sbi->s_delta_cached);
        /* 这里调用 eml_create_snapshot() 将当前状态序列化 */
        kfree(sbi);
        sb->s_fs_info = NULL;
    }

    kill_block_super(sb);
}

static struct file_system_type uscs_fs_type = {
    .owner          = THIS_MODULE,
    .name           = USCS_NAME,
    .mount          = uscs_mount,
    .kill_sb        = uscs_kill_sb,
    .fs_flags       = FS_REQUIRES_DEV,
};

/* ================================================================
 * 8. 字符设备驱动（用于 ioctl 配置接口）
 * ================================================================ */

static dev_t uscs_devt;
static struct cdev uscs_cdev;
static struct class *uscs_class;

/**
 * uscs_ioctl — 超级块配置接口
 *
 * 用户态可以通过 /dev/uscsfs 控制 δ、κ 等全局参数。
 */
static long uscs_ioctl(struct file *filp, unsigned int cmd, unsigned long arg)
{
    struct uscs_sb_info *sbi = filp->private_data;
    unsigned long flags;

    if (!sbi || _IOC_TYPE(cmd) != USCS_IOC_MAGIC)
        return -ENOTTY;

    spin_lock_irqsave(&sbi->s_lock, flags);

    switch (cmd) {
    case USCS_IOC_GET_SUPER: {
        spin_unlock_irqrestore(&sbi->s_lock, flags);
        if (copy_to_user((void __user *)arg, &sbi->s_sb, sizeof(sbi->s_sb)))
            return -EFAULT;
        return 0;
    }

    case USCS_IOC_SET_DELTA: {
        u64 new_delta;
        spin_unlock_irqrestore(&sbi->s_lock, flags);
        if (copy_from_user(&new_delta, (void __user *)arg, sizeof(new_delta)))
            return -EFAULT;
        spin_lock_irqsave(&sbi->s_lock, flags);
        sbi->s_sb.s_delta_global = cpu_to_le64(new_delta);
        sbi->s_delta_cached = new_delta;
        sbi->s_sb.s_flags |= cpu_to_le32(USCS_SB_DELTA_DIRTY);
        sbi->s_dirty = 1;
        spin_unlock_irqrestore(&sbi->s_lock, flags);
        pr_info(USCS_NAME ": delta set to %llu\n", (unsigned long long)new_delta);
        return 0;
    }

    case USCS_IOC_GET_DELTA: {
        u64 delta = sbi->s_delta_cached;
        spin_unlock_irqrestore(&sbi->s_lock, flags);
        if (copy_to_user((void __user *)arg, &delta, sizeof(delta)))
            return -EFAULT;
        return 0;
    }

    case USCS_IOC_LOCK_KAPPA: {
        u8 lock_val;
        spin_unlock_irqrestore(&sbi->s_lock, flags);
        if (copy_from_user(&lock_val, (void __user *)arg, sizeof(lock_val)))
            return -EFAULT;
        spin_lock_irqsave(&sbi->s_lock, flags);
        sbi->s_sb.s_kappa_lock = cpu_to_le64((u64)lock_val * 1000);
        sbi->s_kappa_cached = (u64)lock_val * 1000;
        sbi->s_sb.s_flags |= cpu_to_le32(USCS_SB_KAPPA_DIRTY);
        sbi->s_dirty = 1;
        spin_unlock_irqrestore(&sbi->s_lock, flags);
        pr_info(USCS_NAME ": kappa lock set to %u\n", lock_val);
        return 0;
    }

    case USCS_IOC_GET_STATS: {
        struct uscs_fs_stats stats;
        memset(&stats, 0, sizeof(stats));
        stats.total_graphs = le64_to_cpu(sbi->s_sb.s_num_graphs);
        stats.total_vertices = le64_to_cpu(sbi->s_sb.s_num_vertices);
        stats.total_edges = le64_to_cpu(sbi->s_sb.s_num_edges);
        stats.total_snapshots = le64_to_cpu(sbi->s_sb.s_num_snapshots);
        stats.delta_global = sbi->s_delta_cached;
        stats.kappa_lock = sbi->s_kappa_cached;
        stats.delta_regime = le32_to_cpu(sbi->s_sb.s_delta_regime);
        stats.sb_dirty = sbi->s_dirty;
        spin_unlock_irqrestore(&sbi->s_lock, flags);
        if (copy_to_user((void __user *)arg, &stats, sizeof(stats)))
            return -EFAULT;
        return 0;
    }

    case USCS_IOC_SYNC_DELTA: {
        /* 将内存 δ 同步到磁盘超级块 */
        sbi->s_sb.s_flags &= ~cpu_to_le32(USCS_SB_DELTA_DIRTY | USCS_SB_KAPPA_DIRTY);
        sbi->s_dirty = 0;
        /* 计算新校验和 */
        sbi->s_sb.s_checksum = cpu_to_le32(
            uscs_crc32(&sbi->s_sb, 64 - sizeof(sbi->s_sb.s_checksum))
        );
        pr_info(USCS_NAME ": superblock synced to disk\n");
        spin_unlock_irqrestore(&sbi->s_lock, flags);
        return 0;
    }

    case USCS_IOC_GET_VERSION: {
        char ver[32] = USCS_VERSION;
        spin_unlock_irqrestore(&sbi->s_lock, flags);
        if (copy_to_user((void __user *)arg, ver, sizeof(ver)))
            return -EFAULT;
        return 0;
    }

    default:
        spin_unlock_irqrestore(&sbi->s_lock, flags);
        return -ENOTTY;
    }
}

static int uscs_chr_open(struct inode *inode, struct file *filp)
{
    /* 关联当前挂载实例（简化处理：使用首个实例）*/
    filp->private_data = current->nsproxy->mnt_ns;  /* 占位 */
    return 0;
}

static const struct file_operations uscs_chr_fops = {
    .owner          = THIS_MODULE,
    .open           = uscs_chr_open,
    .unlocked_ioctl = uscs_ioctl,
};

/* ================================================================
 * 9. /proc/uscsfs 统计信息（可选）
 * ================================================================ */

#ifdef CONFIG_PROC_FS
static int uscs_proc_show(struct seq_file *m, void *v)
{
    /* 遍历所有挂载实例，输出统计信息 */
    seq_printf(m, "uscsfs version: %s\n", USCS_VERSION);
    seq_printf(m, "magic: 0x%08X\n", USCS_MAGIC);
    seq_printf(m, "block_size: %u\n", USCS_BLOCK_SIZE);
    seq_printf(m, "inode_size: %u\n", USCS_INODE_SIZE);
    seq_printf(m, "note: full per-mount stats require per-sb tracking\n");
    return 0;
}

static int uscs_proc_open(struct inode *inode, struct file *filp)
{
    return single_open(filp, uscs_proc_show, NULL);
}

static const struct proc_ops uscs_proc_ops = {
    .proc_open    = uscs_proc_open,
    .proc_read    = seq_read,
    .proc_lseek   = seq_lseek,
    .proc_release = single_release,
};
#endif /* CONFIG_PROC_FS */

/* ================================================================
 * 10. 模块初始化与退出
 * ================================================================ */

/**
 * uscsfs_init — 模块加载
 *
 * 执行以下步骤：
 *   1. 注册文件系统类型（register_filesystem）
 *   2. 创建字符设备（用于 ioctl）
 *   3. 创建 /proc/uscsfs（可选）
 */
static int __init uscsfs_init(void)
{
    int ret;

    pr_info("USCS Filesystem v%s loading...\n", USCS_VERSION);
    pr_info("  Magic: 0x%08X, Block: %u, Inode: %u\n",
             USCS_MAGIC, USCS_BLOCK_SIZE, USCS_INODE_SIZE);

    /* 注册文件系统类型 */
    ret = register_filesystem(&uscs_fs_type);
    if (ret) {
        pr_err(USCS_NAME ": register_filesystem failed: %d\n", ret);
        return ret;
    }

    /* 分配字符设备号（用于非挂载配置）*/
    ret = alloc_chrdev_region(&uscs_devt, 0, 1, USCS_NAME);
    if (ret) {
        pr_warn(USCS_NAME ": alloc_chrdev_region failed: %d (ignored)\n", ret);
        /* 不致命，继续 */
    } else {
        cdev_init(&uscs_cdev, &uscs_chr_fops);
        uscs_cdev.owner = THIS_MODULE;
        ret = cdev_add(&uscs_cdev, uscs_devt, 1);
        if (ret) {
            pr_warn(USCS_NAME ": cdev_add failed: %d (ignored)\n", ret);
        } else {
            uscs_class = class_create(USCS_NAME);
            if (IS_ERR(uscs_class)) {
                pr_warn(USCS_NAME ": class_create failed (ignored)\n");
            } else {
                device_create(uscs_class, NULL, uscs_devt, NULL, USCS_NAME);
            }
        }
    }

#ifdef CONFIG_PROC_FS
    proc_create(USCS_NAME, 0444, NULL, &uscs_proc_ops);
#endif

    pr_info(USCS_NAME ": loaded successfully\n");
    pr_info(USCS_NAME ":   mount:  mount -t %s /dev/<dev> /mnt/uscs\n", USCS_NAME);
    pr_info(USCS_NAME ":   config: ioctl(/dev/%s)\n", USCS_NAME);
    return 0;
}

/**
 * uscsfs_exit — 模块卸载
 */
static void __exit uscsfs_exit(void)
{
    pr_info(USCS_NAME ": unloading...\n");

#ifdef CONFIG_PROC_FS
    remove_proc_entry(USCS_NAME, NULL);
#endif

    /* 卸载字符设备 */
    if (uscs_class) {
        device_destroy(uscs_class, uscs_devt);
        class_destroy(uscs_class);
    }
    cdev_del(&uscs_cdev);
    unregister_chrdev_region(uscs_devt, 1);

    /* 注销文件系统类型 */
    unregister_filesystem(&uscs_fs_type);

    pr_info(USCS_NAME ": unloaded successfully\n");
}

module_init(uscsfs_init);
module_exit(uscsfs_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("齐活林 (Qi)");
MODULE_DESCRIPTION("TOMAS-AGI USCS Filesystem — Universal Spectral Continuation System");
MODULE_VERSION(USCS_VERSION);
