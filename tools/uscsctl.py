#!/usr/bin/env python3
"""
uscsctl — TOMAS-AGI USCS 文件系统管理 CLI

M6 用户态工具 (T037)

功能：
  mount      模拟挂载 USCS 文件系统
  unmount    卸载
  status     显示文件系统状态
  snapshot   创建/列出快照
  delta      查看 δ 参数统计
  check      完整性校验

用法：
  python uscsctl.py mount [--delta 7.0] [--kappa-lock]
  python uscsctl.py status
  python uscsctl.py snapshot --create my_snap
  python uscsctl.py delta
  python uscsctl.py check
"""

import argparse
import json
import os
import struct
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, List

# USCS 常量（与 uscsfs/super.c 一致）
USCS_MAGIC = 0x544F4D53  # 'TOMS'
USCS_VERSION_MAJOR = 2
USCS_VERSION_MINOR = 0
USCS_BLOCK_SIZE = 4096
USCS_SUPER_BLOCK = 0


# ============================================================
# 数据结构
# ============================================================
@dataclass
class USCSSuperBlock:
    """USCS 超级块"""
    magic: int = USCS_MAGIC
    version_major: int = USCS_VERSION_MAJOR
    version_minor: int = USCS_VERSION_MINOR
    flags: int = 0
    delta_global: int = 0       # Q8.8 定点
    kappa_lock: int = 0
    delta_regime: int = 0       # 0=classical,1=quantum,2=stable,3=deep
    num_graphs: int = 0
    num_vertices: int = 0
    num_edges: int = 0
    num_snapshots: int = 0
    checksum: int = 0
    log_start: int = 0
    log_size: int = 0
    mtime: int = 0

    def pack(self) -> bytes:
        buf = bytearray(USCS_BLOCK_SIZE)
        struct.pack_into('<IIII', buf, 0, self.magic, self.version_major,
                         self.version_minor, self.flags)
        struct.pack_into('<q', buf, 16, self.delta_global)
        struct.pack_into('<q', buf, 24, self.kappa_lock)
        struct.pack_into('<I', buf, 32, self.delta_regime)
        struct.pack_into('<qqqq', buf, 40, self.num_graphs, self.num_vertices,
                         self.num_edges, self.num_snapshots)
        struct.pack_into('<III', buf, 64, self.checksum, self.log_start, self.log_size)
        buf[76] = self.mtime & 0xFF
        return bytes(buf)

    @classmethod
    def unpack(cls, data: bytes) -> 'USCSSuperBlock':
        sb = cls()
        sb.magic, sb.version_major, sb.version_minor, sb.flags = \
            struct.unpack_from('<IIII', data, 0)
        sb.delta_global = struct.unpack_from('<q', data, 16)[0]
        sb.kappa_lock = struct.unpack_from('<q', data, 24)[0]
        sb.delta_regime = struct.unpack_from('<I', data, 32)[0]
        sb.num_graphs, sb.num_vertices, sb.num_edges, sb.num_snapshots = \
            struct.unpack_from('<qqqq', data, 40)
        sb.checksum, sb.log_start, sb.log_size = \
            struct.unpack_from('<III', data, 64)
        sb.mtime = data[76]
        return sb


@dataclass
class USCSInode:
    """USCS 谱页 inode"""
    ino: int = 0
    mode: int = 0
    delta_weight: int = 0      # Q8.8
    nlinks: int = 0
    size: int = 0
    nblocks: int = 0
    atime: int = 0
    mtime: int = 0


@dataclass
class USCSMount:
    """挂载状态"""
    mounted: bool = False
    mount_point: str = ""
    sb: Optional[USCSSuperBlock] = None
    inodes: List[USCSInode] = field(default_factory=list)
    snapshots: List[dict] = field(default_factory=list)
    delta_log: List[float] = field(default_factory=list)


# 全局挂载状态
_mount_state = USCSMount()


# ============================================================
# CRC32 校验
# ============================================================
def crc32(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


# ============================================================
# 命令实现
# ============================================================
def cmd_mount(args):
    """挂载 USCS 文件系统"""
    global _mount_state

    if _mount_state.mounted:
        print(f"错误：USCS 已挂载于 {_mount_state.mount_point}")
        return 1

    delta = args.delta if args.delta else 0.0
    delta_q88 = int(delta * 256)

    sb = USCSSuperBlock(
        magic=USCS_MAGIC,
        version_major=USCS_VERSION_MAJOR,
        version_minor=USCS_VERSION_MINOR,
        delta_global=delta_q88,
        kappa_lock=1 if args.kappa_lock else 0,
        delta_regime=_classify_regime(delta),
        mtime=int(time.time()) & 0xFF,
    )

    # 计算校验和（两次 pack：第一次用 checksum=0 计算，第二次填入）
    sb.checksum = 0
    sb_raw = sb.pack()
    sb.checksum = crc32(sb_raw[4:76])  # 排除 magic + checksum 自身

    _mount_state.mounted = True
    _mount_state.mount_point = args.mount_point or "/mnt/uscs"
    _mount_state.sb = sb

    print(f"USCS 文件系统已挂载于 {_mount_state.mount_point}")
    print(f"  版本: {sb.version_major}.{sb.version_minor}")
    print(f"  δ_global = {delta:.4f} (0x{delta_q88:04X})")
    print(f"  域: {_regime_name(sb.delta_regime)}")
    print(f"  κ-lock = {'启用' if sb.kappa_lock else '禁用'}")
    print(f"  CRC32 = 0x{sb.checksum:08X}")
    return 0


def cmd_unmount(args):
    """卸载 USCS 文件系统"""
    global _mount_state

    if not _mount_state.mounted:
        print("错误：USCS 未挂载")
        return 1

    sb = _mount_state.sb
    print(f"卸载 {_mount_state.mount_point}")
    print(f"  最终 δ = {sb.delta_global / 256:.4f}")
    print(f"  图谱数 = {sb.num_graphs}")
    print(f"  快照数 = {sb.num_snapshots}")
    print(f"  总顶点 = {sb.num_vertices}")
    print(f"  总边 = {sb.num_edges}")

    _mount_state = USCSMount()
    print("USCS 已卸载")
    return 0


def cmd_status(args):
    """显示文件系统状态"""
    if not _mount_state.mounted:
        print("USCS 未挂载")
        return 0

    sb = _mount_state.sb
    print("=" * 50)
    print(f"  挂载点:     {_mount_state.mount_point}")
    print(f"  魔数:       0x{sb.magic:08X}")
    print(f"  版本:       {sb.version_major}.{sb.version_minor}")
    print(f"  δ_global:   {sb.delta_global / 256:.4f}")
    print(f"  δ 域:       {_regime_name(sb.delta_regime)}")
    print(f"  κ-lock:     {'启用' if sb.kappa_lock else '禁用'}")
    print(f"  图谱数:     {sb.num_graphs}")
    print(f"  顶点数:     {sb.num_vertices}")
    print(f"  边数:       {sb.num_edges}")
    print(f"  快照数:     {sb.num_snapshots}")
    print(f"  CRC32:      0x{sb.checksum:08X}")
    print(f"  inode 数:   {len(_mount_state.inodes)}")
    print("=" * 50)
    return 0


def cmd_snapshot(args):
    """快照管理"""
    if not _mount_state.mounted:
        print("错误：USCS 未挂载")
        return 1

    if args.create:
        snap = {
            "name": args.create,
            "timestamp": time.time(),
            "delta_global": _mount_state.sb.delta_global / 256,
            "num_graphs": _mount_state.sb.num_graphs,
            "num_vertices": _mount_state.sb.num_vertices,
            "num_edges": _mount_state.sb.num_edges,
        }
        _mount_state.snapshots.append(snap)
        _mount_state.sb.num_snapshots += 1
        print(f"快照 '{args.create}' 已创建")
        print(f"  δ = {snap['delta_global']:.4f}")
        print(f"  图谱 = {snap['num_graphs']}, 顶点 = {snap['num_vertices']}")
        return 0

    # 列出快照
    if not _mount_state.snapshots:
        print("无快照")
        return 0

    print(f"{'名称':<20} {'时间':<20} {'δ':<10} {'图谱':<8}")
    print("-" * 60)
    for snap in _mount_state.snapshots:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(snap["timestamp"]))
        print(f"{snap['name']:<20} {ts:<20} {snap['delta_global']:<10.4f} {snap['num_graphs']:<8}")
    return 0


def cmd_delta(args):
    """查看 δ 参数统计"""
    if not _mount_state.mounted:
        print("错误：USCS 未挂载")
        return 1

    sb = _mount_state.sb
    delta = sb.delta_global / 256

    print("δ（谱折叠深度）参数统计")
    print("=" * 40)
    print(f"  δ_global:     {delta:.4f}")
    print(f"  域:          {_regime_name(sb.delta_regime)}")
    print(f"  κ-lock:      {'启用' if sb.kappa_lock else '禁用'}")
    print(f"  δ_critical:  0.5 (阈值)")
    print(f"  悖论耐受:    {'✅ 通过' if delta >= 0.5 else '❌ 不足'}")

    if _mount_state.delta_log:
        import numpy as np
        arr = np.array(_mount_state.delta_log)
        print(f"\n  δ 日志统计:")
        print(f"    记录数: {len(arr)}")
        print(f"    均值:   {np.mean(arr):.4f}")
        print(f"    标准差: {np.std(arr):.4f}")
        print(f"    最大:   {np.max(arr):.4f}")
        print(f"    最小:   {np.min(arr):.4f}")
    return 0


def cmd_check(args):
    """完整性校验"""
    if not _mount_state.mounted:
        print("错误：USCS 未挂载")
        return 1

    sb = _mount_state.sb
    errors = []

    # 1. 魔数校验
    if sb.magic != USCS_MAGIC:
        errors.append(f"魔数错误: 0x{sb.magic:08X} (预期 0x{USCS_MAGIC:08X})")

    # 2. 版本校验
    if sb.version_major != USCS_VERSION_MAJOR:
        errors.append(f"主版本号不匹配: {sb.version_major} (预期 {USCS_VERSION_MAJOR})")

    # 3. CRC32 校验（重新计算，checksum 字段置零）
    sb_copy = USCSSuperBlock(
        magic=sb.magic, version_major=sb.version_major,
        version_minor=sb.version_minor, flags=sb.flags,
        delta_global=sb.delta_global, kappa_lock=sb.kappa_lock,
        delta_regime=sb.delta_regime,
        num_graphs=sb.num_graphs, num_vertices=sb.num_vertices,
        num_edges=sb.num_edges, num_snapshots=sb.num_snapshots,
        checksum=0,  # 计算时置零
        log_start=sb.log_start, log_size=sb.log_size, mtime=sb.mtime,
    )
    sb_raw = sb_copy.pack()
    expected_crc = crc32(sb_raw[4:76])
    if sb.checksum != expected_crc:
        errors.append(f"CRC32 不匹配: 0x{sb.checksum:08X} (预期 0x{expected_crc:08X})")

    # 4. δ 域一致性
    expected_regime = _classify_regime(sb.delta_global / 256)
    if sb.delta_regime != expected_regime:
        errors.append(f"δ 域不一致: {sb.delta_regime} (预期 {expected_regime})")

    # 5. 统计一致性
    if sb.num_snapshots != len(_mount_state.snapshots):
        errors.append(f"快照数不一致: sb={sb.num_snapshots} vs 实际={len(_mount_state.snapshots)}")

    if errors:
        print("❌ 完整性校验失败:")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("✅ 完整性校验通过:")
        print(f"  魔数:     OK")
        print(f"  版本:     OK")
        print(f"  CRC32:    OK")
        print(f"  δ 域:     OK")
        print(f"  快照数:   OK")
        return 0


# ============================================================
# 辅助函数
# ============================================================
def _classify_regime(delta: float) -> int:
    if delta < 0.375:
        return 0  # classical
    elif delta < 3.5:
        return 1  # quantum
    elif delta < 7.0:
        return 2  # stable
    else:
        return 3  # deep_quantum


def _regime_name(regime: int) -> str:
    return {0: "classical", 1: "quantum", 2: "stable", 3: "deep_quantum"}.get(regime, "unknown")


# ============================================================
# 主入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        prog="uscsctl",
        description="TOMAS-AGI USCS 文件系统管理工具"
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # mount
    p_mount = sub.add_parser("mount", help="挂载 USCS 文件系统")
    p_mount.add_argument("--mount-point", default="/mnt/uscs", help="挂载点")
    p_mount.add_argument("--delta", type=float, default=7.0, help="初始 δ 值")
    p_mount.add_argument("--kappa-lock", action="store_true", help="启用 κ=7 锁定")

    # unmount
    sub.add_parser("unmount", help="卸载 USCS 文件系统")

    # status
    sub.add_parser("status", help="显示文件系统状态")

    # snapshot
    p_snap = sub.add_parser("snapshot", help="快照管理")
    p_snap.add_argument("--create", metavar="NAME", help="创建快照")

    # delta
    sub.add_parser("delta", help="查看 δ 参数统计")

    # check
    sub.add_parser("check", help="完整性校验")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "mount": cmd_mount,
        "unmount": cmd_unmount,
        "status": cmd_status,
        "snapshot": cmd_snapshot,
        "delta": cmd_delta,
        "check": cmd_check,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
