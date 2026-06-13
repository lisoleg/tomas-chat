// uscsfs/mmap.c —— T030: USCS 内存映射（δ 页框）
// 太乙互搏 AGI 内核模块 — USCS 文件系统 δ 加权页框 mmap
//
// 模块职责：
//   1. 谱页 mmap（将 δ 加权页直接映射到用户空间）
//   2. 页故障处理（vm_operations->fault）
//   3. 与 δ-mem L1/L2 缓存联动（透明缓存加速）
//   4. 直接 I/O 旁路（zero-copy：用户空间 ↔ EML 图数据）
//   5. δ 页框分配器（类似 buddy 但 δ 加权）
//
// 理论背景 (TOMAS-AGI v2.0):
//   - 经典 mmap：页框内容对用户空间直接可读写
//   - δ-mmap：页框内容按 δ 权重进行非结合修正
//   - 如果 δ=0（经典极限），退化为普通 mmap
//   - 如果 δ>0，每次页故障触发 associator 修正
//   - 与 Φ-Gate 联动：映射区域保留双分支视图
//
// 作者: 齐活林 (Qi)
// 版本: v1.0
// 日期: 2026-06-13
//
// SPDX-License-Identifier: GPL-2.0-only

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/mm.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/pagemap.h>
#include <linux/dma-mapping.h>
#include "../delta_mem.c"       /* 使用 l1/l2 接口 */
#include "../eml_map.c"         /* 使用 eml_serialize/deserialize */

/* ================================================================
 * 1. 常量与宏定义
 * ================================================================ */

#define USCS_MMAP_VERSION   "1.0"
#define USCS_MMAP_NAME      "uscs_mmap"
#define USCS_DELTA_PAGE_SHIFT 12  /* δ 页框大小 = 4KB（与经典相同）*/
#define USCS_DELTA_PAGE_SIZE  (1UL << USCS_DELTA_PAGE_SHIFT)

/* vm_flags 扩展（自定义）*/
#define VM_USCS_DELTA       VM_MIXEDMAP  /* 占位：表示 δ 加权页 */
#define VM_USCS_DUAL        (1 << 20)    /* 双分支映射 */
#define VM_USCS_CONT        (1 << 21)    /* Continuation 映射 */

/* ================================================================
 * 2. δ 页框结构
 * ================================================================ */

/**
 * struct uscs_delta_pfn — δ 加权页框描述符
 *
 * 每个 mmap() 的页关联一个 δ 权重。
 * 当 δ=0 时，退化为普通页框（无修正）。
 * 当 δ>0 时，每次访问触发非结合修正。
 */
struct uscs_delta_pfn {
    struct list_head    list;           /* 链表指针 */
    unsigned long       pfn;            /* 页框号（PFN）*/
    u64                delta_weight;   /* δ 权重（×1000）*/
    u32                eml_vertex_id;  /* 关联的 EML 顶点 ID（可选）*/
    u8                  flags;          /* 标志位 */
    u8                  accessed;       /* 访问计数（用于 LRU）*/
    u64                associator_corr;/* associator 修正项（缓存）*/
    void               *kaddr;         /* 内核虚拟地址 */
};

/* 标志位 */
#define USCS_PFN_DIRTY    0x01  /* 页框已修改 */
#define USCS_PFN_DELTA_OK 0x02  /* δ 有效，需要修正 */
#define USCS_PFN_DUAL     0x04  /* 双分支页（映射两份）*/
#define USCS_PFN_FIXED    0x08  /* 页框已固定（get_user_pages）*/

/* ================================================================
 * 3. USCS mmap 上下文（每个 vma 一个）
 * ================================================================ */

/**
 * struct uscs_vma_ctx — 每个 VMA 的私有数据
 *
 * 通过 vma->vm_private_data 关联。
 * 记录该映射区域的 δ 参数和 EML 图关联。
 */
struct uscs_vma_ctx {
    u64                delta_start;   /* 映射起始 δ（×1000）*/
    u64                delta_end;     /* 映射结束 δ（×1000）*/
    u32                eml_graph_id;  /* 关联的 EML 图 */
    u8                  dual_mode;     /* 是否双分支模式 */
    u8                  cont_mode;     /* 是否 Continuation 模式 */
    spinlock_t          pfn_lock;      /* PFN 链表锁 */
    struct list_head    pfn_list;      /* 已映射 PFN 链表 */
    atomic_t            num_mapped;   /* 已映射页数 */
};

/* ================================================================
 * 4. vm_operations — 页故障处理（核心）
 * ================================================================ */

/**
 * uscs_vmfault — 处理页故障（缺页中断）
 *
 * 当用戶空间访问 mmap() 区域中未映射的页时，
 * 内核调用此函数。
 *
 * 处理流程：
 *   1. 分配（或查找）δ 加权页框
 *   2. 如果 δ>0，计算 associator 修正项
 *   3. 将页框插入页缓存（add_to_page_cache）
 *   4. 如果双分支模式，同时映射"镜像页"
 *   5. 返回 VM_FAULT_LOCKED
 *
 * @vma:   触发故障的 VMA
 * @vmf:   页故障上下文（含地址、标志等）
 */
static int uscs_vmfault(struct vm_area_struct *vma, struct vm_fault *vmf)
{
    struct uscs_vma_ctx *ctx = vma->vm_private_data;
    unsigned long address = vmf->address;
    u64 page_no = (address - vma->vm_start) >> PAGE_SHIFT;
    struct page *page = NULL;
    struct uscs_delta_pfn *dpfn = NULL;
    u64 delta;
    int ret;

    pr_debug(USCS_MMAP_NAME ": vmfault addr=%lx page_no=%llu\n",
               address, (unsigned long long)page_no);

    /* 获取该 VMA 的 δ 权重 */
    delta = ctx ? ctx->delta_start : 7000;  /* 默认 δ=7.0 */

    /* 查找页缓存中是否已有该页 */
    page = find_get_page(vma->vm_file->f_mapping, page_no);
    if (page) {
        /* 页已在缓存中：直接映射 */
        ret = vm_insert_page(vma, address, page);
        if (ret == 0)
            ret = VM_FAULT_LOCKED;
        else
            ret = VM_FAULT_SIGBUS;
        put_page(page);
        return ret;
    }

    /* 页不在缓存中：分配新页 */
    page = alloc_page(GFP_KERNEL | __GFP_ZERO);
    if (!page) {
        pr_warn(USCS_MMAP_NAME ": alloc_page failed (OOM)\n");
        return VM_FAULT_OOM;
    }

    /* 如果 δ>0，进行非结合修正 */
    if (delta > 0) {
        void *kaddr = kmap(page);
        u64 i;

        /* 模拟 associator 修正：
         *   对每个 64 字节块，加上 associator 残差
         *   实际实现中，这里应调用 octonion.associator_norm()
         */
        for (i = 0; i < PAGE_SIZE; i += 64) {
            u64 *q = (u64 *)(kaddr + i);
            /* 模拟修正：δ·associator */
            *q = *q + (delta / 1000) * 10;  /* 简化 */
        }

        /* 如果关联了 EML 图，填入序列化数据 */
        if (ctx && ctx->eml_graph_id != 0xFFFFFFFF) {
            /* 调用 eml_get_vertex_data(ctx->eml_graph_id, page_no, kaddr, PAGE_SIZE); */
            memset(kaddr, 0xAB, 64);  /* 模拟：填入 EML 顶点数据标记 */
        }

        kunmap(page);
    }

    /* 将页插入页缓存 */
    ret = add_to_page_cache_lru(page, vma->vm_file->f_mapping,
                                  page_no, GFP_KERNEL);
    if (ret) {
        put_page(page);
        pr_warn(USCS_MMAP_NAME ": add_to_page_cache failed: %d\n", ret);
        return VM_FAULT_SIGBUS;
    }

    /* 映射到用户空间 */
    ret = vm_insert_page(vma, address, page);
    if (ret) {
        put_page(page);
        return VM_FAULT_SIGBUS;
    }

    /* 如果双分支模式，在"镜像偏移"也映射一页（模拟）*/
    if (ctx && ctx->dual_mode) {
        unsigned long mirror_addr = address + (vma->vm_end - vma->vm_start) / 2;
        /* 注意：这需要用户空间预先保留双份映射区域 */
        pr_debug(USCS_MMAP_NAME ": dual-branch page mapped at %lx (mirror %lx)\n",
                   address, mirror_addr);
    }

    /* 更新统计 */
    if (ctx)
        atomic_inc(&ctx->num_mapped);

    return VM_FAULT_LOCKED;
}

/**
 * uscs_vma_open — VMA 分裂/复制时调用
 */
static void uscs_vma_open(struct vm_area_struct *vma)
{
    struct uscs_vma_ctx *ctx = vma->vm_private_data;
    if (ctx)
        atomic_inc(&ctx->num_mapped);
}

/**
 * uscs_vma_close — VMA 销毁时调用
 */
static void uscs_vma_close(struct vm_area_struct *vma)
{
    struct uscs_vma_ctx *ctx = vma->vm_private_data;
    if (ctx) {
        /* 清理 PFN 链表 */
        struct uscs_delta_pfn *dpfn, *tmp;
        spin_lock(&ctx->pfn_lock);
        list_for_each_entry_safe(dpfn, tmp, &ctx->pfn_list, list) {
            list_del(&dpfn->list);
            kfree(dpfn);
        }
        spin_unlock(&ctx->pfn_lock);
        kfree(ctx);
        vma->vm_private_data = NULL;
    }
}

/* vm_operations_struct */
static const struct vm_operations_struct uscs_vm_ops = {
    .fault      = uscs_vmfault,
    .map_pages  = NULL,  /* 可选：批量预映射（提速）*/
    .open       = uscs_vma_open,
    .close      = uscs_vma_close,
};

/* ================================================================
 * 5. mmap() 入口（file_operations->mmap）
 * ================================================================ */

/**
 * uscs_mmap — USCS 文件 mmap() 回调
 *
 * 用戶空间调用 mmap() 时，内核调用此函数。
 * 负责：
 *   1. 设置 VMA 标志（VM_READ, VM_WRITE, VM_SHARED 等）
 *   2. 分配 uscs_vma_ctx（δ 参数、EML 关联）
 *   3. 绑定 vm_operations（页故障处理）
 *   4. 如果 delta=0，使用 generic_file_mmap（经典模式，快速）
 *
 * @filp:   文件指针
 * @vma:    待建立的 VMA
 */
int uscs_mmap(struct file *filp, struct vm_area_struct *vma)
{
    struct inode *inode = filp->f_inode;
    struct uscs_inode_info *ui = USCS_I(inode);
    struct uscs_vma_ctx *ctx;
    u64 delta;

    if (!ui)
        return -EINVAL;

    delta = ui->delta_weight;

    /* 如果 δ=0（经典极限），退化为普通 mmap（无修正，最快）*/
    if (delta == 0) {
        pr_info(USCS_MMAP_NAME ": delta=0, using generic_file_mmap (classical)\n");
        return generic_file_mmap(filp, vma);
    }

    /* δ>0：需要非结合修正，使用自定义 vm_ops */
    ctx = kzalloc(sizeof(*ctx), GFP_KERNEL);
    if (!ctx)
        return -ENOMEM;

    /* 初始化 VMA 上下文 */
    ctx->delta_start = delta;
    ctx->delta_end = delta;  /* 简化处理：整个映射区 δ 相同 */
    ctx->eml_graph_id = ui->eml_graph_id;
    ctx->dual_mode = (delta > 500) ? 1 : 0;  /* δ>0.5 → 双分支 */
    ctx->cont_mode = ui->cont_active;
    spin_lock_init(&ctx->pfn_lock);
    INIT_LIST_HEAD(&ctx->pfn_list);
    atomic_set(&ctx->num_mapped, 0);

    /* 设置 VMA 标志 */
    vma->vm_flags |= VM_READ | VM_WRITE | VM_MAYREAD | VM_MAYWRITE;
    if (ctx->dual_mode)
        vma->vm_flags |= VM_USCS_DUAL;  /* 自定义标志 */
    vma->vm_private_data = ctx;
    vma->vm_ops = &uscs_vm_ops;

    pr_info(USCS_MMAP_NAME ": mmap ino=%lu size=%lu delta=%llu dual=%u\n",
              inode->i_ino,
              (unsigned long)(vma->vm_end - vma->vm_start),
              (unsigned long long)delta,
              ctx->dual_mode);

    return 0;
}
EXPORT_SYMBOL(uscs_mmap);

/* ================================================================
 * 6. 直接 I/O 旁路（zero-copy）
 * ================================================================ */

/**
 * uscs_direct_io_read — 直接 I/O 读取（旁路页缓存）
 *
 * 用戶态调用 pread2() 带 RWF_DSYNC 标志时触发。
 * 数据直接从 EML 图（或 δ-mem L2）拷贝到用户空间，
 * 不经过页缓存（zero-copy if possible）。
 *
 * @filp:   文件指针
 * @buf:    用户态缓冲区
 * @count:  请求字节数
 * @pos:     文件偏移
 */
static ssize_t uscs_direct_io_read(struct file *filp,
                                         char __user *buf,
                                         size_t count, loff_t *pos)
{
    struct uscs_inode_info *ui = USCS_I(filp->f_inode);
    u64 page_no = *pos / PAGE_SIZE;
    u64 page_offset = *pos % PAGE_SIZE;
    size_t remaining = count;
    u8 *kbuf;
    ssize_t total = 0;

    kbuf = kmalloc(PAGE_SIZE, GFP_KERNEL);
    if (!kbuf)
        return -ENOMEM;

    while (remaining > 0) {
        size_t copy_len = min_t(size_t, remaining, PAGE_SIZE - page_offset);

        /* 尝试从 δ-mem L2 缓存读取（最快）*/
        if (ui->delta_weight > 0) {
            u8 l2_buf[256];
            size_t l2_len = 256;
            int err = l2_read(page_no, l2_buf, &l2_len);
            if (err == 0 && l2_len >= copy_len) {
                /* L2 缓存命中 */
                if (copy_to_user(buf + total, l2_buf, copy_len)) {
                    total = -EFAULT;
                    break;
                }
                total += copy_len;
                remaining -= copy_len;
                page_no++;
                page_offset = 0;
                continue;
            }
        }

        /* L2 未命中：从 EML 序列化数据读取 */
        {
            /* eml_get_vertex_data(ui->eml_graph_id, page_no, kbuf, PAGE_SIZE); */
            memset(kbuf, 0xCD, PAGE_SIZE);  /* 模拟：填入 EML 数据 */
        }

        /* 如果 δ>0，应用修正 */
        if (ui->delta_weight > 500) {
            u64 i;
            for (i = 0; i < copy_len; i += 8) {
                *(u64 *)(kbuf + i) += ui->assoc_residue;
            }
        }

        if (copy_to_user(buf + total, kbuf, copy_len)) {
            total = -EFAULT;
            break;
        }

        total += copy_len;
        remaining -= copy_len;
        page_no++;
        page_offset = 0;
    }

    kfree(kbuf);
    *pos += total;
    return total;
}

/* ================================================================
 * 7. δ 页框分配器（简化 buddy，带 δ 权重）
 * ================================================================ */

/**
 * uscs_alloc_delta_page — 分配 δ 加权页
 *
 * 与普通 alloc_page() 的区别：
 *   - 记录 δ 权重到页描述符
 *   - 如果 δ 较大，优先分配远离 CPU 的页（NUMA 感知，模拟）
 *
 * @delta:   δ 权重（×1000）
 * @gfp:    GFP 标志
 * @return:  page 指针，失败返回 NULL
 */
struct page *uscs_alloc_delta_page(u64 delta, gfp_t gfp)
{
    struct page *page;
    struct uscs_delta_pfn *dpfn;

    page = alloc_page(gfp);
    if (!page)
        return NULL;

    /* 分配 PFN 描述符 */
    dpfn = kzalloc(sizeof(*dpfn), GFP_KERNEL);
    if (!dpfn) {
        put_page(page);
        return NULL;
    }

    dpfn->pfn = page_to_pfn(page);
    dpfn->delta_weight = delta;
    dpfn->kaddr = page_address(page);
    dpfn->flags = (delta > 0) ? USCS_PFN_DELTA_OK : 0;

    /* 将 dpfn 附加到页（通过 page->private）*/
    set_page_private(page, (unsigned long)dpfn);
    SetPagePrivate(page);

    pr_debug(USCS_MMAP_NAME ": alloc_delta_page pfn=%lu delta=%llu\n",
               dpfn->pfn, (unsigned long long)delta);

    return page;
}
EXPORT_SYMBOL(uscs_alloc_delta_page);

/**
 * uscs_free_delta_page — 释放 δ 加权页
 */
void uscs_free_delta_page(struct page *page)
{
    struct uscs_delta_pfn *dpfn;

    if (!PagePrivate(page))
        goto free;

    dpfn = (struct uscs_delta_pfn *)page_private(page);
    if (dpfn) {
        pr_debug(USCS_MMAP_NAME ": free_delta_page pfn=%lu\n", dpfn->pfn);
        kfree(dpfn);
    }
    ClearPagePrivate(page);
    set_page_private(page, 0);

free:
    put_page(page);
}
EXPORT_SYMBOL(uscs_free_delta_page);

/* ================================================================
 * 8. 与 δ-mem 联动：L1/L2 透明加速
 * ================================================================ */

/**
 * uscs_mmap_sync_to_l2 — 将 mmap 脏页同步到 δ-mem L2
 *
 * 当用户调用 msync() 时触发。
 * 遍历 VMA 的所有页，将脏页写入 δ-mem L2 缓存。
 *
 * @vma:    待同步的 VMA
 * @return:  0=成功，<0=错误
 */
static int uscs_mmap_sync_to_l2(struct vm_area_struct *vma)
{
    struct uscs_vma_ctx *ctx = vma->vm_private_data;
    unsigned long addr;
    int ret = 0;

    if (!ctx)
        return 0;

    for (addr = vma->vm_start; addr < vma->vm_end; addr += PAGE_SIZE) {
        struct page *page = follow_page(vma, addr, FOLL_GET);
        if (IS_ERR_OR_NULL(page))
            continue;

        if (PageDirty(page)) {
            u64 key = (addr - vma->vm_start) / PAGE_SIZE;
            void *kaddr = kmap(page);
            int err;

            /* 写入 δ-mem L2 */
            err = l2_write(key, kaddr, PAGE_SIZE);
            if (err) {
                pr_warn(USCS_MMAP_NAME ": l2_write failed: %d\n", err);
                ret = err;
            }

            kunmap(page);
            ClearPageDirty(page);
        }

        put_page(page);
    }

    /* 触发 L2→L1 融合（如果 δ 较大）*/
    if (ctx->delta_start > 5000) {
        double delta_d = ctx->delta_start / 1000.0;
        l1_to_l2_fusion((int)delta_d);
    }

    pr_info(USCS_MMAP_NAME ": msync done (delta=%llu)\n",
             (unsigned long long)ctx->delta_start);

    return ret;
}

/* ================================================================
 * 9. ioctl 接口（mmap 配置）
 * ================================================================ */

#define USCS_MMAP_IOC_MAGIC  'M'
#define USCS_MMAP_IOC_GET_CTX   _IOR(USCS_MMAP_IOC_MAGIC, 1, struct uscs_vma_ctx)
#define USCS_MMAP_IOC_SET_DELTA _IOW(USCS_MMAP_IOC_MAGIC, 2, u64)
#define USCS_MMAP_IOC_SYNC_L2   _IO(USCS_MMAP_IOC_MAGIC,  3)
#define USCS_MMAP_IOC_ENABLE_DUAL _IOW(USCS_MMAP_IOC_MAGIC, 4, u8)

static long uscs_mmap_ioctl(struct file *filp, unsigned int cmd, unsigned long arg)
{
    struct vm_area_struct *vma = filp->f_vma;  /* 简化处理：取当前 VMA */
    struct uscs_vma_ctx *ctx = vma ? vma->vm_private_data : NULL;

    if (!ctx || _IOC_TYPE(cmd) != USCS_MMAP_IOC_MAGIC)
        return -ENOTTY;

    switch (cmd) {
    case USCS_MMAP_IOC_GET_CTX:
        if (copy_to_user((void __user *)arg, ctx, sizeof(*ctx)))
            return -EFAULT;
        return 0;

    case USCS_MMAP_IOC_SET_DELTA: {
        u64 new_delta;
        if (copy_from_user(&new_delta, (void __user *)arg, sizeof(new_delta)))
            return -EFAULT;
        ctx->delta_start = new_delta;
        ctx->delta_end = new_delta;
        return 0;
    }

    case USCS_MMAP_IOC_SYNC_L2:
        return uscs_mmap_sync_to_l2(vma);

    case USCS_MMAP_IOC_ENABLE_DUAL: {
        u8 enable;
        if (copy_from_user(&enable, (void __user *)arg, sizeof(enable)))
            return -EFAULT;
        ctx->dual_mode = enable ? 1 : 0;
        return 0;
    }

    default:
        return -ENOTTY;
    }
}

/* ================================================================
 * 10. 模块初始化与退出
 * ================================================================ */

static int __init uscs_mmap_init(void)
{
    pr_info(USCS_MMAP_NAME " v%s loading...\n", USCS_MMAP_VERSION);
    pr_info(USCS_MMAP_NAME ": delta-weighted mmap ready\n");
    return 0;
}

static void __exit uscs_mmap_exit(void)
{
    pr_info(USCS_MMAP_NAME ": unloading...\n");
}

module_init(uscs_mmap_init);
module_exit(uscs_mmap_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("齐活林 (Qi)");
MODULE_DESCRIPTION("TOMAS-AGI USCS mmap — δ-weighted page frame mapping");
MODULE_VERSION(USCS_MMAP_VERSION);

/* 导出接口（供 file.c / super.c 使用）*/
EXPORT_SYMBOL(uscs_mmap);
EXPORT_SYMBOL(uscs_alloc_delta_page);
EXPORT_SYMBOL(uscs_free_delta_page);
EXPORT_SYMBOL(uscs_mmap_sync_to_l2);
