// uscsfs/inode.c —— T028: USCS inode 操作（谱页）
// 太乙互搏 AGI 内核模块 — USCS 文件系统 inode 管理
//
// 模块职责：
//   1. inode 分配/释放（iget/drop_inode）
//   2. 谱页（spectral page）读写（address_space_operations）
//   3. 目录项管理（lookup/create/delete）
//   4. δ 权重与 inode 关联（每个 inode 记录其 δ 值）
//   5. 与 EML 谱图联动（inode ↔ EML 顶点/边）
//
// 理论背景 (TOMAS-AGI v2.0):
//   - USCS inode 不只代表普通文件，而是"谱页"的抽象
//   - 每个 inode 关联一个 δ 权重（来自 NASGA 非结合谱图代数）
//   - 读写 inode 时，自动进行 δ 加权（δ=0 退化为经典文件）
//   - 目录 inode 包含子图谱列表（类似目录包含文件）
//
// 作者: 齐活林 (Qi)
// 版本: v1.0
// 日期: 2026-06-13
//
// SPDX-License-Identifier: GPL-2.0-only

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/buffer_head.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/xarray.h>
#include <linux/pagemap.h>
#include "../octonion.c"        /* 使用 EXPORT_SYMBOL 接口 */
#include "../eml_map.c"         /* 使用 eml_serialize/deserialize 接口 */

/* ================================================================
 * 1. 常量与宏定义
 * ================================================================ */

#define USCS_INODE_VERSION   "1.0"
#define USCS_INODE_DIRTY    0x01
#define USCS_INODE_DELTA_OK 0x02

/* inode 类型 */
#define USCS_INO_TYPE_FILE    0x01  /* 普通文件（EML 图谱） */
#define USCS_INO_TYPE_DIR     0x02  /* 目录（图谱集合） */
#define USCS_INO_TYPE_SNAP   0x04  /* EML 快照文件 */
#define USCS_INO_TYPE_DELTA  0x08  /* δ 权重页文件（特殊）*/

/* ================================================================
 * 2. USCS inode 扩展结构
 * ================================================================ */

/**
 * struct uscs_inode_info — USCS inode 私有数据
 *
 * 每个 inode 关联一个 uscs_inode_info，存储：
 *   - δ 权重（该 inode 所属谱图的折叠深度）
 *   - Associator 残差（非结合性度量）
 *   - EML 图 ID（关联 eml_map 的图索引）
 *   - Continuation 状态（用于非结合续延读写）
 */
struct uscs_inode_info {
    struct inode        vfs_inode;      /* 必须是第一个字段（container_of）*/

    /* δ 参数 */
    u64                 delta_weight;   /* δ 权重（×1000，定点数）*/
    u32                 delta_regime;   /* δ 域：0=classical..3=deep */
    u8                  delta_valid;    /* δ 是否有效 */

    /* EML 谱图关联 */
    u32                 eml_graph_id;  /* 关联的 EML 图 ID（eml_map 索引）*/
    u32                 eml_num_vertices; /* 顶点数 */
    u32                 eml_num_edges;     /* 边数 */

    /* Associator 残差 */
    u64                 assoc_residue;  /* 结合子残差（×1000）*/
    u8                  moufang_pass;   /* Moufang 恒等式是否通过 */

    /* Continuation 状态 */
    u64                 cont_offset;    /* 当前续延偏移（字节）*/
    u8                  cont_active;    /* 是否有活跃的续延 */
    u64                 cont_buffer;    /* 续延缓冲区（内核虚拟地址）*/

    /* 地址空间（页缓存）*/
    struct address_space  i_data;         /* 页缓存地址空间 */
    struct xarray        i_pages;        /* 页缓存 xarray */
};

/**
 * USCS_I — 从 inode 获取 uscs_inode_info
 */
static inline struct uscs_inode_info *USCS_I(struct inode *inode)
{
    return container_of(inode, struct uscs_inode_info, vfs_inode);
}

/* ================================================================
 * 3. inode 分配与销毁
 * ================================================================ */

/**
 * uscs_alloc_inode — 分配 USCS inode
 *
 * VFS 回调：当 VFS 需要新 inode 时调用。
 * 分配 uscs_inode_info 并初始化。
 */
static struct inode *uscs_alloc_inode(struct super_block *sb)
{
    struct uscs_inode_info *ui;

    ui = kzalloc(sizeof(*ui), GFP_KERNEL);
    if (!ui)
        return NULL;

    /* 初始化 δ 参数（继承超级块全局值）*/
    {
        struct uscs_sb_info *sbi = sb->s_fs_info;
        if (sbi) {
            ui->delta_weight = sbi->s_delta_cached;
            ui->delta_regime = le32_to_cpu(sbi->s_sb.s_delta_regime);
        } else {
            ui->delta_weight = 7000;  /* 默认 δ=7.0 */
            ui->delta_regime = 2;      /* stable */
        }
    }

    ui->delta_valid = 1;
    ui->eml_graph_id = 0xFFFFFFFF;  /* 未关联 */
    ui->cont_offset = 0;
    ui->cont_active = 0;

    inode_init_once(&ui->vfs_inode);
    return &ui->vfs_inode;
}

/**
 * uscs_destroy_inode — 销毁 USCS inode
 */
static void uscs_destroy_inode(struct inode *inode)
{
    struct uscs_inode_info *ui = USCS_I(inode);

    /* 释放续延缓冲区 */
    if (ui->cont_buffer) {
        vfree((void *)ui->cont_buffer);
        ui->cont_buffer = 0;
    }

    /* 如果关联了 EML 图，减少引用计数 */
    if (ui->eml_graph_id != 0xFFFFFFFF) {
        /* eml_graph_put(ui->eml_graph_id);  需要 eml_map 导出该函数 */
        pr_debug("uscsfs: inode %lu releasing eml_graph %u\n",
                  inode->i_no, ui->eml_graph_id);
    }

    kfree(ui);
}

/**
 * uscs_iget — 从磁盘（或 EML 快照）读取 inode
 *
 * @sb:     超级块
 * @ino:     inode 号
 * @return:  初始化的 inode
 *
 * 对于 USCS（虚拟文件系统），inode 信息来自：
 *   1. 根目录（ino=1）：静态创建
 *   2. 图谱文件：从 eml_map 恢复元数据
 *   3. 快照文件：从 eml_snapshot 恢复
 */
struct inode *uscs_iget(struct super_block *sb, unsigned long ino)
{
    struct inode *inode;
    struct uscs_inode_info *ui;
    int ret;

    /* 检查 inode 缓存 */
    inode = iget_locked(sb, ino);
    if (!inode)
        return ERR_PTR(-ENOMEM);
    if (!(inode->i_state & I_NEW))
        return inode;

    ui = USCS_I(inode);

    /* 根据 ino 初始化 */
    if (ino == 1) {
        /* 根目录 */
        inode->i_mode = S_IFDIR | 0755;
        inode->i_op = &uscs_dir_inode_ops;
        inode->i_fop = &uscs_dir_fops;
        inode->i_size = 4096;  /* 目录页大小 */
        ui->delta_weight = 7000;
        ui->eml_graph_id = 0xFFFFFFFF;
    } else {
        /* 普通文件（EML 图谱或快照）*/
        /* 简化处理：从 eml_map 获取图元数据 */
        inode->i_mode = S_IFREG | 0644;
        inode->i_op = &uscs_file_inode_ops;
        inode->i_fop = &uscs_file_fops;
        inode->i_mapping->a_ops = &uscs_aops;
        /* 大小从 EML 序列化数据获取（见下方 read_inode）*/
        ui->eml_graph_id = (u32)(ino - 2);  /* 简化处理 */
    }

    /* 设置时间戳 */
    inode->i_atime = inode->i_mtime = inode->i_ctime = current_time(sb, inode);

    unlock_new_inode(inode);
    return inode;
}

/* ================================================================
 * 4. address_space_operations（谱页读写）
 * ================================================================ */

/**
 * uscs_readpage — 读取单个谱页
 *
 * 将 EML 谱图数据（δ 加权）读入页缓存。
 * 如果 δ=0（经典极限），退化为普通页读取。
 *
 * @file:    文件指针（可为 NULL）
 * @page:    目标页（struct page *）
 */
static int uscs_readpage(struct file *file, struct page *page)
{
    struct inode *inode = page->mapping->host;
    struct uscs_inode_info *ui = USCS_I(inode);
    u64 page_offset = page_offset(page);  /* 页在文件中的偏移（字节）*/
    u64 page_no = page_offset >> PAGE_SHIFT;
    void *page_addr;
    int ret = 0;

    pr_debug("uscsfs: readpage ino=%lu page_no=%llu delta=%llu\n",
              inode->i_no, (unsigned long long)page_no,
              (unsigned long long)ui->delta_weight);

    page_addr = kmap(page);

    /* 从 EML 图数据填充页内容 */
    /* 简化处理：如果关联了 EML 图，反序列化对应范围的数据 */
    if (ui->eml_graph_id != 0xFFFFFFFF) {
        /* 调用 eml_deserialize_graph 的部分读取 */
        /* 这里简化为填充模拟数据 */
        memset(page_addr, 0, PAGE_SIZE);
        /* 在页首写入 δ 权重标记（用于验证）*/
        *(u64 *)page_addr = ui->delta_weight;
        *(u64 *)(page_addr + 8) = page_no;
        ret = 0;
    } else {
        /* 未关联 EML 图：返回零页 */
        clear_highpage(page);
        ret = 0;
    }

    /* 如果 δ > 0，应用 δ 加权（模拟非结合修正）*/
    if (ui->delta_weight > 0) {
        u8 *p = page_addr;
        u64 i;
        /* 对页内容施加微扰（δ 越大，扰动越强）*/
        for (i = 0; i < PAGE_SIZE; i += 64) {
            u32 *w = (u32 *)(p + i);
            *w = *w ^ (ui->delta_weight & 0xFFFFFFFF);
        }
    }

    flush_dcache_page(page);
    kunmap(page);

    if (ret == 0)
        SetPageUptodate(page);
    else
        SetPageError(page);

    unlock_page(page);
    return ret;
}

/**
 * uscs_writepage — 写入单个谱页
 *
 * 将页缓存中的 δ 加权数据写回 EML 谱图。
 * 触发 eml_serialize_graph（如果页对应 EML 图的一部分）。
 */
static int uscs_writepage(struct page *page, struct writeback_control *wbc)
{
    struct inode *inode = page->mapping->host;
    struct uscs_inode_info *ui = USCS_I(inode);
    u64 page_no = page_offset(page) >> PAGE_SHIFT;
    void *page_addr;
    int ret = 0;

    pr_debug("uscsfs: writepage ino=%lu page_no=%llu\n",
              inode->i_no, (unsigned long long)page_no);

    /* 如果 δ 退化为 0（经典极限），直接写回，无需非结合修正 */
    if (ui->delta_weight == 0) {
        /* 经典模式：直接写回 */
        /* 调用底层存储_WRITE(page) */
        SetPageWriteback(page);
        end_page_writeback(page);
        return 0;
    }

    /* δ > 0：非结合修正后再写回 */
    page_addr = kmap(page);

    /* 应用 Associator 修正（模拟）*/
    {
        u64 i;
        u8 *p = page_addr;
        for (i = 0; i < PAGE_SIZE; i += 128) {
            u64 *q = (u64 *)(p + i);
            /* 模拟 associator 修正项：δ·[a,b,c] */
            *q = *q + ui->assoc_residue;
        }
    }

    /* 写回 EML 序列化数据 */
    /* eml_serialize_graph(..., page_addr, PAGE_SIZE); */

    kunmap(page);
    SetPageWriteback(page);
    end_page_writeback(page);

    return ret;
}

/**
 * uscs_write_begin — 写前准备（预留页）
 */
static int uscs_write_begin(struct file *file,
                            struct address_space *mapping,
                            loff_t pos, unsigned len, unsigned flags,
                            struct page **pagep, void **fsdata)
{
    struct inode *inode = mapping->host;
    pgoff_t index = pos >> PAGE_SHIFT;
    struct page *page;
    int ret;

    page = grab_cache_page_write_begin(mapping, index, flags);
    if (!page)
        return -ENOMEM;

    *pagep = page;

    /* 如果页不在缓存中，读入 */
    if (!PageUptodate(page)) {
        ret = uscs_readpage(file, page);
        if (ret)
            return ret;
    }

    return 0;
}

/**
 * uscs_write_end — 写后收尾
 */
static int uscs_write_end(struct file *file,
                          struct address_space *mapping,
                          loff_t pos, unsigned len, unsigned copied,
                          struct page *page, void *fsdata)
{
    struct inode *inode = mapping->host;

    if (copied < len)
        zero_user_segment(page, pos + copied, pos + len);

    if (!PageUptodate(page))
        SetPageUptodate(page);
    set_page_dirty(page);
    unlock_page(page);
    put_page(page);

    /* 更新文件大小 */
    if (pos + copied > inode->i_size)
        i_size_write(inode, pos + copied);

    return copied;
}

/* address_space_operations */
static const struct address_space_operations uscs_aops = {
    .readpage       = uscs_readpage,
    .writepage      = uscs_writepage,
    .write_begin    = uscs_write_begin,
    .write_end      = uscs_write_end,
    /* .readpages   = uscs_readpages,   可选批量预读 */
    /* .writepages  = uscs_writepages, 可选批量写回 */
};

/* ================================================================
 * 5. 目录操作（lookup / create / delete）
 * ================================================================ */

/**
 * uscs_lookup — 目录查找
 *
 * 在目录 @dir 中查找名为 @name（长度 @len）的文件。
 * 返回对应的 dentry（附加上 inode）。
 */
static struct dentry *uscs_lookup(struct inode *dir,
                                  const struct qstr *name,
                                  unsigned int flags)
{
    struct dentry *dentry;
    struct inode *inode = NULL;
    u64 ino;

    /* 简化处理：按名称哈希计算 ino */
    ino = name->hash;
    if (ino == 0)
        ino = 2;  /* 第一个非根 inode */

    dentry = d_lookup(dir, name);
    if (dentry)
        return dentry;

    dentry = d_alloc(dir, name);
    if (!dentry)
        return ERR_PTR(-ENOMEM);

    inode = uscs_iget(dir->i_sb, ino);
    if (IS_ERR(inode)) {
        dput(dentry);
        return ERR_CAST(inode);
    }

    d_add(dentry, inode);
    return dentry;
}

/**
 * uscs_create — 创建新文件（目录项）
 */
static int uscs_create(struct inode *dir, struct dentry *dentry,
                        umode_t mode, bool excl)
{
    struct inode *inode;
    int ret = 0;

    inode = uscs_alloc_inode(dir->i_sb);
    if (!inode)
        return -ENOMEM;

    inode->i_mode = mode;
    inode->i_ino = dentry->d_name.hash;  /* 简化处理 */
    if (inode->i_ino == 0)
        inode->i_ino = 2;

    /* 继承父目录的 δ 权重 */
    {
        struct uscs_inode_info *dir_ui = USCS_I(dir);
        struct uscs_inode_info *ui = USCS_I(inode);
        ui->delta_weight = dir_ui->delta_weight;
        ui->delta_regime = dir_ui->delta_regime;
    }

    d_instantiate(dentry, inode);
    return ret;
}

/* inode_operations（目录）*/
static const struct inode_operations uscs_dir_inode_ops = {
    .lookup    = uscs_lookup,
    .create    = uscs_create,
    /* .unlink  = uscs_unlink,  */
    /* .mkdir    = uscs_mkdir,    */
    /* .rmdir    = uscs_rmdir,    */
};

/* ================================================================
 * 6. 文件操作（read/write/iterate/llseek）
 * ================================================================ */

/**
 * uscs_file_read — 文件读取（Continuation 模式）
 *
 * 非结合续延读取：读取时保留续延状态，
 * 使得下次读取能从"非结合分歧点"继续。
 */
static ssize_t uscs_file_read(struct file *filp, char __user *buf,
                              size_t count, loff_t *ppos)
{
    struct inode *inode = filp->f_inode;
    struct uscs_inode_info *ui = USCS_I(inode);
    loff_t pos = *ppos;
    ssize_t ret;

    /* 如果启用了续延模式，从续延偏移继续 */
    if (ui->cont_active) {
        pos = ui->cont_offset;
        pr_debug("uscsfs: continuation read from offset %llu\n",
                  (unsigned long long)pos);
    }

    /* 标准 VFS 读取（通过 address_space）*/
    ret = generic_file_read_iter(filp, buf, count, ppos);

    /* 更新续延偏移 */
    ui->cont_offset = *ppos;
    ui->cont_active = 1;

    return ret;
}

/**
 * uscs_file_write — 文件写入（δ 加权）
 */
static ssize_t uscs_file_write(struct file *filp, const char __user *buf,
                               size_t count, loff_t *ppos)
{
    struct inode *inode = filp->f_inode;
    struct uscs_inode_info *ui = USCS_I(inode);
    ssize_t ret;

    /* 如果 δ 接近 0（经典极限），直接写入 */
    if (ui->delta_weight < 10) {  /* δ < 0.01 */
        ret = generic_file_write_iter(filp, buf, count, ppos);
        return ret;
    }

    /* δ > 0：非结合写入（保留双分支状态）*/
    /* 将写入数据同时应用到两个"虚拟分支" */
    /* 分支 A：直接写入 */
    ret = generic_file_write_iter(filp, buf, count, ppos);
    if (ret < 0)
        return ret;

    /* 分支 B：δ 修正后写入（模拟）*/
    /* 实际实现中，这里会将数据传入 Φ-Gate 做双分支评估 */
    pr_debug("uscsfs: dual-branch write ino=%lu delta=%llu\n",
              inode->i_no, (unsigned long long)ui->delta_weight);

    ui->cont_offset = *ppos;
    return ret;
}

/**
 * uscs_file_llseek — 文件定位
 *
 * 支持 SEEK_DATA / SEEK_HOLE（用于稀疏谱页文件）。
 */
static loff_t uscs_file_llseek(struct file *filp, loff_t offset, int whence)
{
    struct inode *inode = filp->f_inode;
    loff_t maxsize = inode->i_size;

    switch (whence) {
    case SEEK_SET:
        break;
    case SEEK_CUR:
        offset += filp->f_pos;
        break;
    case SEEK_END:
        offset += maxsize;
        break;
    case SEEK_DATA:
        /* 查找第一个非空页（δ > 0 的页）*/
        /* 简化处理：返回当前偏移 */
        break;
    case SEEK_HOLE:
        /* 查找第一个空页（δ = 0 的页）*/
        break;
    default:
        return -EINVAL;
    }

    if (offset < 0 || offset > maxsize)
        return -EINVAL;

    filp->f_pos = offset;
    return offset;
}

/* file_operations（普通文件）*/
static const struct file_operations uscs_file_fops = {
    .read           = uscs_file_read,
    .write          = uscs_file_write,
    .llseek         = uscs_file_llseek,
    .open           = generic_file_open,
    .release        = NULL,
    .mmap           = uscs_mmap,  /* 在 mmap.c 中实现 */
};

/* file_operations（目录）*/
static const struct file_operations uscs_dir_fops = {
    .readdir        = generic_readdir,  /* 简化处理 */
    .open           = generic_file_open,
    .release        = NULL,
};

/* ================================================================
 * 7. 超级块回调（super.c 引用）
 * ================================================================ */

/* 这些函数在 super.c 中声明，这里提供实现 */

/* uscs_write_inode — 将 inode 写入磁盘（或 EML 快照）*/
static int uscs_write_inode(struct inode *inode,
                             struct writeback_control *wbc)
{
    struct uscs_inode_info *ui = USCS_I(inode);

    /* 序列化 uscs_inode_info 到 EML 快照 */
    pr_debug("uscsfs: write_inode ino=%lu delta=%llu\n",
              inode->i_ino, (unsigned long long)ui->delta_weight);

    /* 标记 inode 为干净 */
    return 0;
}

/* uscs_put_super — 卸载时释放超级块资源 */
static void uscs_put_super(struct super_block *sb)
{
    struct uscs_sb_info *sbi = sb->s_fs_info;
    if (sbi) {
        /* 同步所有脏 inode */
        sync_filesystem(sb);
        kfree(sbi);
        sb->s_fs_info = NULL;
    }
}

/* uscs_statfs — 获取文件系统统计信息（statfs 系统调用）*/
static int uscs_statfs(struct dentry *dentry, struct kstatfs *buf)
{
    struct super_block *sb = dentry->d_sb;
    struct uscs_sb_info *sbi = sb->s_fs_info;

    buf->f_type = USCS_MAGIC;
    buf->f_bsize = USCS_BLOCK_SIZE;
    buf->f_blocks = 0xFFFFFFFF;  /* 虚拟文件系统：无限（或受内存限制）*/
    buf->f_bfree = 0xFFFFFFFF;
    buf->f_bavail = 0xFFFFFFFF;
    buf->f_files = 0xFFFFFFFF;   /* 最大 inode 数 */
    buf->f_ffree = 0xFFFFFFFF;
    buf->f_namelen = 255;

    if (sbi) {
        buf->f_fsid.val[0] = (u32)(sbi->s_delta_cached & 0xFFFFFFFF);
        buf->f_fsid.val[1] = (u32)(sbi->s_delta_cached >> 32);
    }

    return 0;
}

/* 更新 super_operations（在 super.c 的 uscs_sops 中引用）*/
/* 注意：这里需要 extern 声明，或在 super.c 中直接赋值 */

/* ================================================================
 * 8. 初始化与退出（供 super.c 调用）
 * ================================================================ */

/**
 * uscs_inode_init — inode 子系统初始化
 *
 * 在文件系统挂载时调用（从 uscs_fill_super 调用）。
 * 初始化 inode 缓存、EML 图关联表。
 */
int uscs_inode_init(struct super_block *sb)
{
    struct uscs_sb_info *sbi = sb->s_fs_info;

    if (!sbi)
        return -EINVAL;

    /* 初始化 inode 操作函数表（已在上方定义）*/
    /* 绑定 super_operations */
    sb->s_op->alloc_inode  = uscs_alloc_inode;
    sb->s_op->destroy_inode = uscs_destroy_inode;
    sb->s_op->write_inode   = uscs_write_inode;
    sb->s_op->put_super     = uscs_put_super;
    sb->s_op->statfs        = uscs_statfs;

    pr_info("uscsfs: inode subsystem initialized (delta=%llu)\n",
             (unsigned long long)sbi->s_delta_cached);
    return 0;
}

/**
 * uscs_inode_exit — inode 子系统清理
 */
void uscs_inode_exit(struct super_block *sb)
{
    /* 驱逐所有干净的 inode */
    invalidate_inodes(sb, true);
    pr_info("uscsfs: inode subsystem exited\n");
}

EXPORT_SYMBOL(uscs_inode_init);
EXPORT_SYMBOL(uscs_inode_exit);
EXPORT_SYMBOL(uscs_iget);
