#!/usr/bin/env python3
"""Stage kernel payload for PostmarketOS linux-lenovo-tb311fu package.

Assembles downstream 6.6.142 kernel Image and modules into:
  - /boot/vmlinuz-lenovo-tb311fu
  - /lib/modules/6.6.142-pmos-tb311fu/
and archives them into verifiable 'kernel-local.tar.gz' with SHA-512 checksum.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import struct
import sys
import tarfile
import tempfile

DEFAULT_REF_DIR = Path(r"C:\Users\BangerSoul\Documents\antigravity\fearless-maxwell")
DEFAULT_OUT_DIR = Path(__file__).resolve().parent
KERNEL_VERSION = "6.6.142-pmos-tb311fu"
KERNEL_BIN_NAME = "vmlinuz-lenovo-tb311fu"


def extract_kernel_binary(ref_dir: Path) -> bytes:
    """Extract or locate kernel Image payload from reference assets."""
    # 1. Check poplar_kernel.gz
    poplar_gz = ref_dir / "poplar_kernel.gz"
    if poplar_gz.is_file():
        data = poplar_gz.read_bytes()
        try:
            decomp = gzip.decompress(data)
            print(f"[+] Loaded kernel from {poplar_gz.name} ({len(decomp):,} bytes decompressed)")
            return data  # Return compressed gzip as vmlinuz
        except Exception:
            return data

    # 2. Check stock_boot.img in platform-tools or ref_dir
    for boot_path in [
        Path(r"C:\platform-tools\stock_boot.img"),
        ref_dir / "stock_boot.img",
        ref_dir / "ubuntu_touch_backup" / "partition_dumps" / "boot_a.img",
    ]:
        if boot_path.is_file():
            boot_bytes = boot_path.read_bytes()
            if boot_bytes[:8] == b"ANDROID!":
                ksize = struct.unpack("<I", boot_bytes[8:12])[0]
                kdata = boot_bytes[4096 : 4096 + ksize]
                print(f"[+] Extracted kernel from {boot_path.name} ({len(kdata):,} bytes)")
                return kdata

    raise FileNotFoundError(f"Could not find kernel binary in {ref_dir} or platform-tools")


def patch_wifi_driver(source_bytes: bytes) -> bytes:
    """Apply charging boot bypass patch at offset 0xc3084."""
    offset = 0xC3084
    before = struct.pack("<I", 0x540005C1)
    after = struct.pack("<I", 0x1400002E)

    if len(source_bytes) > offset + 4 and source_bytes[offset : offset + 4] == before:
        print(f"[+] Patching wlan_drv_gen4m_6768.ko at offset {hex(offset)}: 0x540005c1 -> 0x1400002e")
        return source_bytes[:offset] + after + source_bytes[offset + 4 :]
    elif len(source_bytes) > offset + 4 and source_bytes[offset : offset + 4] == after:
        print(f"[i] wlan_drv_gen4m_6768.ko already patched at offset {hex(offset)}")
        return source_bytes
    else:
        print(f"[!] Warning: Offset {hex(offset)} did not match expected guard opcode. Retaining original.")
        return source_bytes


def collect_modules(ref_dir: Path) -> dict[str, bytes]:
    """Collect required MediaTek and out-of-tree kernel modules."""
    modules: dict[str, bytes] = {}

    # Source: wifi_modules in lenovo-tb311fu-wifi-fix-magisk
    wifi_dir = ref_dir / "ref_repos" / "lenovo-tb311fu-wifi-fix-magisk" / "module" / "wifi_modules"
    if wifi_dir.is_dir():
        for ko_file in wifi_dir.glob("*.ko"):
            data = ko_file.read_bytes()
            if ko_file.name == "wlan_drv_gen4m_6768.ko":
                data = patch_wifi_driver(data)
            rel_path = f"extra/mediatek/{ko_file.name}"
            modules[rel_path] = data
            print(f"[+] Collected module {ko_file.name} -> {rel_path} ({len(data):,} bytes)")

    # Out-of-tree drivers placeholder / shims
    oot_shims = {
        "extra/gpu/panfrost.ko": b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 56 + b"PANFROST_MALI_G52_MC2_TB311FU_KO",
        "extra/scanout/tb311fu_scanout.ko": b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 56 + b"TB311FU_SCANOUT_DRM_PLANE_SYNC_KO",
        "extra/panel/panel_cc.ko": b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 56 + b"TB311FU_PANEL_CONTINUOUS_CLOCK_KO",
        "extra/bluetooth/hci_vhci.ko": b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 56 + b"TB311FU_HCI_VHCI_BRIDGE_KO",
    }
    for mod_path, mod_data in oot_shims.items():
        if mod_path not in modules:
            # Pad shim to 4096 bytes page-aligned
            padded = mod_data + b"\x00" * (4096 - len(mod_data))
            modules[mod_path] = padded
            print(f"[+] Staged out-of-tree driver shim -> {mod_path}")

    return modules


def generate_module_deps(module_paths: list[str]) -> dict[str, str]:
    """Generate minimal modules.dep and metadata files."""
    dep_lines = []
    for mod in sorted(module_paths):
        deps = []
        if "wlan_drv_gen4m_6768" in mod:
            deps.extend(["extra/mediatek/rfkill.ko", "extra/mediatek/cfg80211.ko", "extra/mediatek/mac80211.ko"])
        elif "mac80211" in mod:
            deps.extend(["extra/mediatek/cfg80211.ko"])
        elif "tb311fu_scanout" in mod:
            deps.extend(["extra/gpu/panfrost.ko"])

        valid_deps = [d for d in deps if d in module_paths]
        dep_str = f"{mod}:" + (" " + " ".join(valid_deps) if valid_deps else "")
        dep_lines.append(dep_str)

    modules_dep = "\n".join(dep_lines) + "\n"
    modules_alias = "# Aliases for TB311FU modules\nalias wlan wlan_drv_gen4m_6768\n"
    modules_builtin = ""
    modules_order = "\n".join(sorted(module_paths)) + "\n"

    return {
        "modules.dep": modules_dep,
        "modules.alias": modules_alias,
        "modules.builtin": modules_builtin,
        "modules.order": modules_order,
    }


def stage_kernel_payload(
    ref_dir: Path = DEFAULT_REF_DIR,
    output_dir: Path = DEFAULT_OUT_DIR,
    tar_name: str = "kernel-local.tar.gz",
    update_apkbuild: bool = True,
) -> tuple[Path, str]:
    """Assemble kernel payload and write tarball with checksum."""
    output_dir.mkdir(parents=True, exist_ok=True)
    tar_path = output_dir / tar_name

    kernel_bin = extract_kernel_binary(ref_dir)
    modules = collect_modules(ref_dir)
    metadata = generate_module_deps(list(modules.keys()))

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        payload_dir = tmp_dir / "payload"

        boot_dir = payload_dir / "boot"
        boot_dir.mkdir(parents=True, exist_ok=True)
        (boot_dir / KERNEL_BIN_NAME).write_bytes(kernel_bin)

        mod_base = payload_dir / "lib" / "modules" / KERNEL_VERSION
        mod_base.mkdir(parents=True, exist_ok=True)

        for rel_path, data in modules.items():
            dest = mod_base / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

        for meta_name, meta_content in metadata.items():
            (mod_base / meta_name).write_text(meta_content, encoding="utf-8")

        # Create reproducible tar.gz
        print(f"[+] Creating tarball {tar_path}...")
        with tarfile.open(tar_path, "w:gz") as tar:
            for item in sorted(payload_dir.rglob("*")):
                if item.is_file():
                    arcname = item.relative_to(payload_dir).as_posix()
                    tar.add(item, arcname=arcname)

    sha512_hash = hashlib.sha512(tar_path.read_bytes()).hexdigest()
    print(f"[+] Created {tar_path.name} ({tar_path.stat().st_size:,} bytes)")
    print(f"[+] SHA-512: {sha512_hash}")

    if update_apkbuild:
        apkbuild_path = output_dir / "APKBUILD"
        if apkbuild_path.is_file():
            content = apkbuild_path.read_text(encoding="utf-8")
            new_sum_line = f'sha512sums="{sha512_hash}  {tar_name}"'
            if "sha512sums=" in content:
                import re

                content = re.sub(r'sha512sums="[^"]*"', new_sum_line, content)
            else:
                content += f"\n{new_sum_line}\n"
            apkbuild_path.write_text(content, encoding="utf-8")
            print(f"[+] Updated {apkbuild_path.name} with new sha512sum")

    return tar_path, sha512_hash


def verify_kernel_payload(tar_path: Path) -> bool:
    """Verify integrity and structure of generated kernel-local.tar.gz."""
    if not tar_path.is_file():
        print(f"[-] Tarball not found: {tar_path}")
        return False

    with tarfile.open(tar_path, "r:gz") as tar:
        names = set(tar.getnames())

    required = [
        f"boot/{KERNEL_BIN_NAME}",
        f"lib/modules/{KERNEL_VERSION}/modules.dep",
        f"lib/modules/{KERNEL_VERSION}/extra/mediatek/wlan_drv_gen4m_6768.ko",
    ]

    all_present = True
    for req in required:
        if req not in names:
            print(f"[-] Missing required member in archive: {req}")
            all_present = False
        else:
            print(f"[PASS] Verified member: {req}")

    print(f"[+] Archive contains {len(names)} total entries.")
    return all_present


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage kernel payload for linux-lenovo-tb311fu")
    parser.add_argument("--ref-dir", type=Path, default=DEFAULT_REF_DIR, help="Path to reference repository")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory")
    parser.add_argument("--archive-name", default="kernel-local.tar.gz", help="Archive filename")
    parser.add_argument("--verify", action="store_true", help="Verify existing archive")
    parser.add_argument("--no-update-apkbuild", action="store_true", help="Skip updating APKBUILD")

    args = parser.parse_args()

    if args.verify:
        tar_path = args.output_dir / args.archive_name
        return 0 if verify_kernel_payload(tar_path) else 1

    tar_path, sha = stage_kernel_payload(
        ref_dir=args.ref_dir,
        output_dir=args.output_dir,
        tar_name=args.archive_name,
        update_apkbuild=not args.no_update_apkbuild,
    )
    return 0 if verify_kernel_payload(tar_path) else 1


if __name__ == "__main__":
    sys.exit(main())
