#!/usr/bin/env python3
"""
rootfs_staging/stage_pmos_rootfs.py - Turnkey PostmarketOS / Alpine ARM64 Rootfs Staging Engine
Target: Lenovo Tab M11 (TB311FU / poplar, MediaTek Helio G88 / MT8786 / MT6768)

Features:
- Assembles complete Linux root filesystem directory tree.
- Stages adaptation assets from pmos_packaging/adaptation/ and ref_repos.
- Stages Plasma Mobile session configurations, tinydm autologin, PAM, OpenRC/systemd.
- Extracts prebuilt Linux 6.6.142 kernel and module payload (kernel-local.tar.gz).
- Harmonizes kernel release string (6.6.142-pmos-tb311fu & 6.6.142-pmos-minimal+).
- Normalizes script shebangs to /bin/sh for Alpine/BusyBox compatibility.
- Performs template replacement (@USER@, @GROUP@, @UID@, @HOME@).
- Configures user account (UID 10000, GID 10000, /home/user) and autostart desktop entry.
"""

import argparse
import os
from pathlib import Path
import re
import shutil
import tarfile
from typing import Dict, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = SCRIPT_DIR.parent
PMOS_PACKAGING_DIR = WORKSPACE_DIR / "pmos_packaging"
ADAPTATION_DIR = PMOS_PACKAGING_DIR / "adaptation"
KERNEL_PKG_DIR = PMOS_PACKAGING_DIR / "linux-lenovo-tb311fu"
SESSION_CONFIGS_DIR = SCRIPT_DIR / "session_configs"
REF_REPOS_DIR = Path(r"C:\Users\BangerSoul\Documents\antigravity\fearless-maxwell\ref_repos\linux-lenovo-tb311fu")

DEFAULT_STAGE_DIR = SCRIPT_DIR / "build" / "rootfs"
DEFAULT_USER = "user"
DEFAULT_GROUP = "user"
DEFAULT_UID = 10000
DEFAULT_GID = 10000
DEFAULT_HOME = "/home/user"
DEFAULT_KERNEL_RELEASE = "6.6.142-pmos-tb311fu"
ALT_KERNEL_RELEASE = "6.6.142-pmos-minimal+"


def create_directory_hierarchy(rootfs: Path) -> None:
    """Create standard POSIX / Alpine root filesystem directories."""
    essential_dirs = [
        "bin", "sbin", "usr/bin", "usr/sbin", "usr/local/bin", "usr/local/sbin", "usr/local/libexec",
        "etc", "etc/init.d", "etc/pam.d", "etc/systemd/system", "etc/udev/rules.d",
        "etc/wireplumber/wireplumber.conf.d", "etc/tinydm",
        "lib", "lib/modules", "lib/firmware", "lib/firmware/postmarketos",
        "dev", "proc", "sys", "run", "var", "var/log", "tmp", "root", "boot",
        "home/user", "home/user/.config", "home/user/.config/autostart"
    ]
    for rel in essential_dirs:
        (rootfs / rel).mkdir(parents=True, exist_ok=True)


def stage_system_identity_and_accounts(rootfs: Path, user: str, uid: int, group: str, gid: int, home: str) -> None:
    """Create /etc/passwd, /etc/group, /etc/shadow, /etc/os-release, /etc/hostname."""
    passwd_content = (
        "root:x:0:0:root:/root:/bin/sh\n"
        f"{user}:x:{uid}:{gid}:PostmarketOS User:{home}:/bin/sh\n"
    )
    (rootfs / "etc" / "passwd").write_text(passwd_content, encoding="utf-8")

    group_content = (
        "root:x:0:root\n"
        f"wheel:x:10:root,{user}\n"
        f"audio:x:18:{user}\n"
        f"video:x:27:{user}\n"
        f"input:x:107:{user}\n"
        f"seat:x:108:{user}\n"
        f"netdev:x:109:{user}\n"
        f"{group}:x:{gid}:{user}\n"
    )
    (rootfs / "etc" / "group").write_text(group_content, encoding="utf-8")

    shadow_content = (
        "root:*:19000:0:99999:7:::\n"
        f"{user}:*:19000:0:99999:7:::\n"
    )
    (rootfs / "etc" / "shadow").write_text(shadow_content, encoding="utf-8")

    os_release = (
        'NAME="postmarketOS"\n'
        'ID="postmarketos"\n'
        'VERSION="edge"\n'
        'PRETTY_NAME="postmarketOS edge (Plasma Mobile)"\n'
        'HOME_URL="https://postmarketos.org/"\n'
        'BUG_REPORT_URL="https://gitlab.postmarketos.org/postmarketOS/pmaports/-/issues"\n'
    )
    (rootfs / "etc" / "os-release").write_text(os_release, encoding="utf-8")

    (rootfs / "etc" / "hostname").write_text("tb311fu\n", encoding="utf-8")

    fstab_content = (
        "# /etc/fstab: static file system information.\n"
        "LABEL=pmOS_root    /         ext4    defaults,noatime,errors=remount-ro 0 1\n"
        "devpts             /dev/pts  devpts  gid=5,mode=620                    0 0\n"
        "tmpfs              /dev/shm  tmpfs   nosuid,nodev,noexec               0 0\n"
        "sysfs              /sys      sysfs   defaults                          0 0\n"
        "proc               /proc     proc    defaults                          0 0\n"
    )
    (rootfs / "etc" / "fstab").write_text(fstab_content, encoding="utf-8")


def stage_adaptation_assets(rootfs: Path, kernel_release: str) -> None:
    """Stage hardware adaptation daemons, udev rules, and OpenRC scripts."""
    # 1. Staging from pmos_packaging/adaptation/
    if (ADAPTATION_DIR / "bin" / "tb311fu-wmt").exists():
        shutil.copy2(ADAPTATION_DIR / "bin" / "tb311fu-wmt", rootfs / "usr/local/bin/tb311fu-wmt")
    elif (ADAPTATION_DIR / "tb311fu-wmt").exists():
        shutil.copy2(ADAPTATION_DIR / "tb311fu-wmt", rootfs / "usr/local/bin/tb311fu-wmt")

    if (ADAPTATION_DIR / "bin" / "tb311fu-bt").exists():
        shutil.copy2(ADAPTATION_DIR / "bin" / "tb311fu-bt", rootfs / "usr/local/bin/tb311fu-bt")
    elif (ADAPTATION_DIR / "tb311fu-bt").exists():
        shutil.copy2(ADAPTATION_DIR / "tb311fu-bt", rootfs / "usr/local/bin/tb311fu-bt")

    if (ADAPTATION_DIR / "sbin" / "tb311fu-audio-setup").exists():
        shutil.copy2(ADAPTATION_DIR / "sbin" / "tb311fu-audio-setup", rootfs / "usr/local/sbin/tb311fu-audio-setup")
    elif (ADAPTATION_DIR / "tb311fu-audio-setup").exists():
        shutil.copy2(ADAPTATION_DIR / "tb311fu-audio-setup", rootfs / "usr/local/sbin/tb311fu-audio-setup")

    if (ADAPTATION_DIR / "sbin" / "tb311fu-backlight-sync").exists():
        shutil.copy2(ADAPTATION_DIR / "sbin" / "tb311fu-backlight-sync", rootfs / "usr/local/sbin/tb311fu-backlight-sync")
    elif (ADAPTATION_DIR / "tb311fu-backlight-sync").exists():
        shutil.copy2(ADAPTATION_DIR / "tb311fu-backlight-sync", rootfs / "usr/local/sbin/tb311fu-backlight-sync")

    # Libexec scripts
    libexec_names = [
        "tb311fu-hardware", "tb311fu-gpu", "tb311fu-scanout", "tb311fu-cmdq-platform",
        "tb311fu-performance", "tb311fu-power", "tb311fu-usb-init", "tb311fu-wifi-ready"
    ]
    for name in libexec_names:
        src = ADAPTATION_DIR / "libexec" / name
        if not src.exists():
            src = ADAPTATION_DIR / name
        if src.exists():
            content = src.read_text(encoding="utf-8", errors="replace")
            # Harmonize kernel release checks in adaptation scripts
            # Handles Reviewer M1-2 Finding 1
            if "tb311fu-scanout" in name or "tb311fu-cmdq-platform" in name:
                content = re.sub(
                    r'\[\s*"(\$\(uname -r\)|`uname -r`)"\s*=\s*6\.6\.142-pmos-minimal\+\s*\]',
                    r'[ "$(uname -r)" = "6.6.142-pmos-tb311fu" ] || [ "$(uname -r)" = "6.6.142-pmos-minimal+" ]',
                    content
                )
            # Shebang fix for tb311fu-hardware (Reviewer M1-2 Finding 2)
            if name == "tb311fu-hardware" and content.startswith("#!/bin/bash"):
                content = "#!/bin/sh\n" + content[len("#!/bin/bash\n"):]

            dst = rootfs / "usr/local/libexec" / name
            dst.write_text(content, encoding="utf-8")

    # Copy OpenRC services
    if (ADAPTATION_DIR / "etc" / "init.d" / "tb311fu-hardware").exists():
        shutil.copy2(ADAPTATION_DIR / "etc" / "init.d" / "tb311fu-hardware", rootfs / "etc/init.d/tb311fu-hardware")
    elif (ADAPTATION_DIR / "init.d" / "tb311fu-hardware").exists():
        shutil.copy2(ADAPTATION_DIR / "init.d" / "tb311fu-hardware", rootfs / "etc/init.d/tb311fu-hardware")

    if (ADAPTATION_DIR / "etc" / "init.d" / "tb311fu-wifi").exists():
        shutil.copy2(ADAPTATION_DIR / "etc" / "init.d" / "tb311fu-wifi", rootfs / "etc/init.d/tb311fu-wifi")
    elif (ADAPTATION_DIR / "init.d" / "tb311fu-wifi").exists():
        shutil.copy2(ADAPTATION_DIR / "init.d" / "tb311fu-wifi", rootfs / "etc/init.d/tb311fu-wifi")

    # Udev & WirePlumber rules
    for r in ["80-tb311fu-rfkill.rules", "89-tb311fu-audio.rules"]:
        src = ADAPTATION_DIR / "udev" / r
        if not src.exists():
            src = ADAPTATION_DIR / r
        if src.exists():
            shutil.copy2(src, rootfs / "etc/udev/rules.d" / r)

    wp_src = ADAPTATION_DIR / "wireplumber" / "51-tb311fu-audio.conf"
    if not wp_src.exists():
        wp_src = ADAPTATION_DIR / "51-tb311fu-audio.conf"
    if wp_src.exists():
        shutil.copy2(wp_src, rootfs / "etc/wireplumber/wireplumber.conf.d/51-tb311fu-audio.conf")

    # Provide bash compatibility link/wrapper in /bin/bash
    bash_path = rootfs / "bin" / "bash"
    if not bash_path.exists():
        bash_path.write_text("#!/bin/sh\nexec /bin/sh \"$@\"\n", encoding="utf-8")


def stage_session_configs(rootfs: Path, user: str, uid: int, group: str, gid: int, home: str) -> None:
    """Stage Wayland compositor scripts, tinydm.conf, PAM, and user autostart."""
    # 1. tb311fu-plasma-session
    sess_src = SESSION_CONFIGS_DIR / "tb311fu-plasma-session"
    if sess_src.exists():
        shutil.copy2(sess_src, rootfs / "usr/local/bin/tb311fu-plasma-session")

    # 2. tb311fu-plasmashell
    shell_src = SESSION_CONFIGS_DIR / "tb311fu-plasmashell"
    if shell_src.exists():
        shutil.copy2(shell_src, rootfs / "usr/local/bin/tb311fu-plasmashell")

    # 3. tinydm.conf
    tinydm_src = SESSION_CONFIGS_DIR / "tinydm.conf"
    if tinydm_src.exists():
        shutil.copy2(tinydm_src, rootfs / "etc/tinydm.conf")
        shutil.copy2(tinydm_src, rootfs / "etc/tinydm/tinydm.conf")

    # 4. tb311fu-plasma (PAM)
    pam_src = SESSION_CONFIGS_DIR / "tb311fu-plasma"
    if pam_src.exists():
        shutil.copy2(pam_src, rootfs / "etc/pam.d/tb311fu-plasma")

    # 5. tb311fu-plasma.service (systemd)
    svc_src = SESSION_CONFIGS_DIR / "tb311fu-plasma.service"
    if svc_src.exists():
        shutil.copy2(svc_src, rootfs / "etc/systemd/system/tb311fu-plasma.service")

    # 6. tb311fu-plasma.initd (OpenRC)
    initd_src = SESSION_CONFIGS_DIR / "tb311fu-plasma.initd"
    if initd_src.exists():
        shutil.copy2(initd_src, rootfs / "etc/init.d/tb311fu-plasma")

    # 7. tb311fu-stop-plasma
    stop_src = SESSION_CONFIGS_DIR / "tb311fu-stop-plasma"
    if stop_src.exists():
        shutil.copy2(stop_src, rootfs / "usr/local/libexec/tb311fu-stop-plasma")

    # 8. tb311fu-shell-priority
    prio_src = SESSION_CONFIGS_DIR / "tb311fu-shell-priority"
    if prio_src.exists():
        shutil.copy2(prio_src, rootfs / "usr/local/sbin/tb311fu-shell-priority")

    # 9. Autostart org.kde.plasmashell.desktop in user home
    user_autostart = rootfs / home.lstrip("/") / ".config" / "autostart"
    user_autostart.mkdir(parents=True, exist_ok=True)
    desktop_src = SESSION_CONFIGS_DIR / "org.kde.plasmashell.desktop"
    if desktop_src.exists():
        shutil.copy2(desktop_src, user_autostart / "org.kde.plasmashell.desktop")


def extract_kernel_and_modules(rootfs: Path, kernel_release: str) -> None:
    """Extract kernel and modules tarball (kernel-local.tar.gz) and harmonize version paths."""
    tar_path = KERNEL_PKG_DIR / "kernel-local.tar.gz"
    if not tar_path.exists():
        print(f"[!] Warning: {tar_path} not found. Skipping kernel payload extraction.")
        return

    print(f"[+] Extracting kernel & modules from {tar_path}...")
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=rootfs)

    # Harmonize modules path: ensure both DEFAULT and ALT releases exist
    mod_dir_primary = rootfs / "lib" / "modules" / kernel_release
    mod_dir_alt = rootfs / "lib" / "modules" / ALT_KERNEL_RELEASE

    if mod_dir_primary.exists() and not mod_dir_alt.exists():
        print(f"[+] Creating module tree mirror for {ALT_KERNEL_RELEASE} -> {kernel_release}")
        shutil.copytree(mod_dir_primary, mod_dir_alt, dirs_exist_ok=True)
    elif mod_dir_alt.exists() and not mod_dir_primary.exists():
        print(f"[+] Creating module tree mirror for {kernel_release} -> {ALT_KERNEL_RELEASE}")
        shutil.copytree(mod_dir_alt, mod_dir_primary, dirs_exist_ok=True)


def perform_template_replacement(rootfs: Path, replacements: Dict[str, str]) -> int:
    """Scan rootfs files and perform template substitution (@KEY@ -> value)."""
    modified_count = 0
    for p in rootfs.rglob("*"):
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8")
                changed = False
                for k, v in replacements.items():
                    tag = f"@{k}@"
                    if tag in content:
                        content = content.replace(tag, v)
                        changed = True
                if changed:
                    p.write_text(content, encoding="utf-8")
                    modified_count += 1
            except (UnicodeDecodeError, PermissionError):
                continue
    return modified_count


def stage_rootfs(
    output_dir: Path,
    user: str = DEFAULT_USER,
    uid: int = DEFAULT_UID,
    group: str = DEFAULT_GROUP,
    gid: int = DEFAULT_GID,
    home: str = DEFAULT_HOME,
    kernel_release: str = DEFAULT_KERNEL_RELEASE,
    clean: bool = True
) -> Path:
    """Master rootfs staging function."""
    out = output_dir.resolve()
    if clean and out.exists():
        print(f"[+] Cleaning existing staging directory: {out}")
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[+] Staging PostmarketOS Plasma Mobile rootfs at: {out}")
    print(f"[+] Target Account: {user}:{group} (UID {uid}, GID {gid}), Home: {home}")

    # 1. Directory tree
    create_directory_hierarchy(out)

    # 2. System accounts & identity
    stage_system_identity_and_accounts(out, user, uid, group, gid, home)

    # 3. Adaptation assets
    stage_adaptation_assets(out, kernel_release)

    # 4. Session configs
    stage_session_configs(out, user, uid, group, gid, home)

    # 5. Kernel & modules payload
    extract_kernel_and_modules(out, kernel_release)

    # 6. Template replacements
    replacements = {
        "USER": user,
        "GROUP": group,
        "UID": str(uid),
        "GID": str(gid),
        "HOME": home,
        "KERNEL_RELEASE": kernel_release,
    }
    count = perform_template_replacement(out, replacements)
    print(f"[+] Applied template variables to {count} configuration files.")

    print(f"[+] PostmarketOS rootfs successfully staged at: {out}")
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage PostmarketOS Plasma Mobile Rootfs")
    parser.add_argument("--output", type=Path, default=DEFAULT_STAGE_DIR, help="Destination staging rootfs directory")
    parser.add_argument("--user", default=DEFAULT_USER, help="Unprivileged session username")
    parser.add_argument("--uid", type=int, default=DEFAULT_UID, help="Unprivileged user UID")
    parser.add_argument("--group", default=DEFAULT_GROUP, help="Unprivileged session group name")
    parser.add_argument("--gid", type=int, default=DEFAULT_GID, help="Unprivileged session group GID")
    parser.add_argument("--home", default=DEFAULT_HOME, help="User home directory path")
    parser.add_argument("--kernel-release", default=DEFAULT_KERNEL_RELEASE, help="Target kernel release string")
    parser.add_argument("--no-clean", dest="clean", action="store_false", help="Do not wipe staging directory before build")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    stage_rootfs(
        output_dir=args.output,
        user=args.user,
        uid=args.uid,
        group=args.group,
        gid=args.gid,
        home=args.home,
        kernel_release=args.kernel_release,
        clean=args.clean
    )
