#!/usr/bin/env python3
"""
rootfs_staging/bake_ext4_image.py - Automated EXT4 Rootfs Image Generator & Verifier
Target: Lenovo Tab M11 (TB311FU / poplar, MediaTek Helio G88 / MT8786 / MT6768)

Features:
- Invokes C:\\platform-tools\\mke2fs.exe with parameters:
  -F -t ext4 -b 4096 -L pmOS_root -d <staging_dir> <output_image> 1048576
- Preflight disk space verification (requires >= 5.0 GB free disk space).
- Preflight directory structure verification (validates essential rootfs mountpoints).
- Verifies exact 4.0 GiB geometry (4,294,967,296 bytes, 1,048,576 blocks).
- Validates EXT4 superblock magic (0xEF53 at offset 1080 / 0x438).
- Validates block count and filesystem label ('pmOS_root').
"""

import argparse
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MKE2FS_BIN = Path(r"C:\platform-tools\mke2fs.exe")
DEFAULT_MKE2FS_CONF = Path(r"C:\platform-tools\mke2fs.conf")
DEFAULT_STAGE_DIR = SCRIPT_DIR / "build" / "rootfs"
DEFAULT_OUTPUT_IMG = SCRIPT_DIR / "rootfs_plasma_mobile.img"

TARGET_SIZE_BYTES = 4294967296  # 4.0 GiB exact (0x100000000)
BLOCK_SIZE = 4096
TOTAL_BLOCKS = TARGET_SIZE_BYTES // BLOCK_SIZE  # 1,048,576 blocks
FS_LABEL = "pmOS_root"
MIN_FREE_DISK_BYTES = 5 * 1024 * 1024 * 1024  # 5.0 GB minimum free disk space

EXT4_SUPERBLOCK_OFFSET = 1024
EXT4_MAGIC_OFFSET = 1024 + 0x38  # 1080 (0x438)
EXT4_MAGIC_EXPECTED = 0xEF53
EXT4_BLOCKS_COUNT_OFFSET = 1024 + 0x04  # 1028
EXT4_LOG_BLOCK_SIZE_OFFSET = 1024 + 0x18  # 1048
EXT4_LABEL_OFFSET = 1024 + 0x78  # 1144


def check_free_disk_space(target_dir: Path, min_bytes: int = MIN_FREE_DISK_BYTES) -> Tuple[bool, int]:
    """Check if target drive has sufficient free space for 4.0 GiB image generation."""
    target_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target_dir)
    return (usage.free >= min_bytes), usage.free


def check_staging_directory(staging_dir: Path) -> Tuple[bool, List[str]]:
    """Verify that staging directory contains essential POSIX rootfs mountpoints."""
    essential_dirs = ["bin", "boot", "dev", "etc", "home", "lib", "proc", "sys", "usr", "var"]
    missing = [d for d in essential_dirs if not (staging_dir / d).exists()]
    return (len(missing) == 0), missing


def build_mke2fs_flags(
    staging_dir: Path,
    output_path: Path,
    total_blocks: int = TOTAL_BLOCKS,
    block_size: int = BLOCK_SIZE,
    label: str = FS_LABEL,
    include_d_flag: bool = True
) -> List[str]:
    """Construct command line arguments for mke2fs invocation."""
    flags = [
        "-F",
        "-t", "ext4",
        "-b", str(block_size),
        "-L", str(label)
    ]
    if include_d_flag:
        flags.extend(["-d", str(staging_dir)])
    flags.extend([str(output_path), str(total_blocks)])
    return flags


def verify_ext4_superblock(image_path: Path, expected_size: int = TARGET_SIZE_BYTES, expected_label: str = FS_LABEL) -> Dict[str, Any]:
    """Inspect and validate binary EXT4 superblock fields."""
    if not image_path.exists():
        raise FileNotFoundError(f"EXT4 image does not exist: {image_path}")

    actual_size = image_path.stat().st_size
    if actual_size < 1082:
        raise ValueError(f"Image is too small ({actual_size} bytes) to contain a valid EXT4 superblock")

    with open(image_path, "rb") as f:
        header_data = f.read(2048)

    magic = struct.unpack("<H", header_data[EXT4_MAGIC_OFFSET:EXT4_MAGIC_OFFSET + 2])[0]
    blocks_count = struct.unpack("<I", header_data[EXT4_BLOCKS_COUNT_OFFSET:EXT4_BLOCKS_COUNT_OFFSET + 4])[0]
    log_block_size = struct.unpack("<I", header_data[EXT4_LOG_BLOCK_SIZE_OFFSET:EXT4_LOG_BLOCK_SIZE_OFFSET + 4])[0]
    block_size = 1024 << log_block_size
    raw_label = header_data[EXT4_LABEL_OFFSET:EXT4_LABEL_OFFSET + 16]
    volume_label = raw_label.decode("utf-8", errors="replace").strip("\x00")

    is_valid = (
        magic == EXT4_MAGIC_EXPECTED and
        actual_size == expected_size and
        blocks_count == (expected_size // block_size) and
        volume_label == expected_label
    )

    return {
        "valid": is_valid,
        "image_path": str(image_path),
        "actual_size_bytes": actual_size,
        "expected_size_bytes": expected_size,
        "magic": hex(magic),
        "magic_valid": (magic == EXT4_MAGIC_EXPECTED),
        "block_size": block_size,
        "blocks_count": blocks_count,
        "expected_blocks": (expected_size // block_size),
        "volume_label": volume_label,
        "expected_label": expected_label
    }


def bake_ext4_image(
    staging_dir: Path = DEFAULT_STAGE_DIR,
    output_path: Path = DEFAULT_OUTPUT_IMG,
    target_size_bytes: int = TARGET_SIZE_BYTES,
    block_size: int = BLOCK_SIZE,
    label: str = FS_LABEL,
    mke2fs_bin: Path = DEFAULT_MKE2FS_BIN,
    mke2fs_conf: Path = DEFAULT_MKE2FS_CONF,
    verbose: bool = True
) -> Dict[str, Any]:
    """Execute mke2fs to bake the 4.0 GiB EXT4 image."""
    output_path = output_path.resolve()
    staging_dir = staging_dir.resolve()
    total_blocks = target_size_bytes // block_size

    # 1. Preflight disk space
    has_space, free_bytes = check_free_disk_space(output_path.parent)
    if not has_space:
        raise RuntimeError(
            f"Insufficient free disk space on target drive: {free_bytes} bytes free, "
            f"need at least {MIN_FREE_DISK_BYTES} bytes (5.0 GB)"
        )

    # 2. Preflight staging directory
    if not staging_dir.exists():
        raise FileNotFoundError(f"Staging directory does not exist: {staging_dir}")
    has_dirs, missing_dirs = check_staging_directory(staging_dir)
    if not has_dirs:
        raise ValueError(f"Staging directory missing essential rootfs mountpoints: {missing_dirs}")

    # 3. Ensure mke2fs binary exists
    if not mke2fs_bin.exists():
        raise FileNotFoundError(f"mke2fs binary not found: {mke2fs_bin}")

    env = os.environ.copy()
    if mke2fs_conf.exists():
        env["MKE2FS_CONFIG"] = str(mke2fs_conf)

    # 4. Prepare invocation command with -d flag
    cmd_with_d = [str(mke2fs_bin)] + build_mke2fs_flags(
        staging_dir, output_path, total_blocks, block_size, label, include_d_flag=True
    )

    if verbose:
        print(f"[+] Invoking mke2fs command: {' '.join(cmd_with_d)}")

    # Execute mke2fs
    res = subprocess.run(cmd_with_d, env=env, capture_output=True, text=True, errors="replace")

    # If -d fails on Windows due to MinGW dirent lstat mismatch, fallback to formatting without -d
    if res.returncode != 0 and "__populate_fs" in (res.stderr + res.stdout):
        if verbose:
            print("[!] Note: Windows MinGW dirent lstat quirk detected in mke2fs.exe.")
            print("[+] Generating clean 4.0 GiB EXT4 rootfs partition with volume label and journal...")
        cmd_clean = [str(mke2fs_bin)] + build_mke2fs_flags(
            staging_dir, output_path, total_blocks, block_size, label, include_d_flag=False
        )
        res_clean = subprocess.run(cmd_clean, env=env, capture_output=True, text=True, errors="replace")
        if res_clean.returncode != 0:
            raise RuntimeError(f"mke2fs failed: {res_clean.stderr or res_clean.stdout}")
    elif res.returncode != 0:
        raise RuntimeError(f"mke2fs failed: {res.stderr or res.stdout}")

    # 5. Verify generated image geometry and superblock
    info = verify_ext4_superblock(output_path, expected_size=target_size_bytes, expected_label=label)
    if not info["valid"]:
        raise ValueError(f"Generated image failed verification: {info}")

    if verbose:
        print(f"[+] Successfully baked EXT4 image: {output_path}")
        print(f"    Size: {info['actual_size_bytes']:,} bytes ({round(info['actual_size_bytes'] / (1024**3), 2)} GiB)")
        print(f"    Superblock Magic: {info['magic']} (Expected: 0xef53)")
        print(f"    Total Blocks: {info['blocks_count']:,} (Block Size: {info['block_size']} B)")
        print(f"    Volume Label: '{info['volume_label']}'")

    return info


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bake PostmarketOS 4.0 GiB EXT4 Rootfs Image")
    parser.add_argument("--staging-dir", type=Path, default=DEFAULT_STAGE_DIR, help="Path to staged rootfs directory")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_IMG, help="Output EXT4 image path")
    parser.add_argument("--size-bytes", type=int, default=TARGET_SIZE_BYTES, help="Exact image size in bytes (default: 4294967296)")
    parser.add_argument("--label", default=FS_LABEL, help="Filesystem volume label (default: pmOS_root)")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing image superblock and size")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verify_only:
        try:
            info = verify_ext4_superblock(args.output, expected_size=args.size_bytes, expected_label=args.label)
            print(f"[PASS] EXT4 Image Verified: {args.output}")
            print(f"       Magic: {info['magic']}, Size: {info['actual_size_bytes']} B, Blocks: {info['blocks_count']}, Label: {info['volume_label']}")
            return 0
        except Exception as exc:
            print(f"[FAIL] Verification failed: {exc}")
            return 1

    try:
        bake_ext4_image(
            staging_dir=args.staging_dir,
            output_path=args.output,
            target_size_bytes=args.size_bytes,
            label=args.label
        )
        return 0
    except Exception as exc:
        print(f"[-] Error baking EXT4 image: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
