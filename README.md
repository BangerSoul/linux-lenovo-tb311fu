# linux-lenovo-tb311fu

[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Target: Lenovo Tab M11](https://img.shields.io/badge/Device-Lenovo%20Tab%20M11%20(TB311FU)-orange.svg)](https://www.lenovo.com)
[![SoC: MediaTek Helio G88](https://img.shields.io/badge/SoC-MediaTek%20Helio%20G88%20(MT8786%2FMT6768)-red.svg)](https://www.mediatek.com)
[![OS: PostmarketOS](https://img.shields.io/badge/OS-PostmarketOS%20%2F%20Alpine%20ARM64-teal.svg)](https://postmarketos.org)
[![Compositor: Plasma Mobile 6](https://img.shields.io/badge/Compositor-KWin%20Wayland%20%2F%20Plasma%20Mobile%206-blueviolet.svg)](https://plasma-mobile.org)

Native Linux (PostmarketOS / Alpine Linux ARM64 with KDE Plasma Mobile 6) device package, downstream Linux 6.6.142 GKI kernel integration, udev hardware rules, compositor patches, and Fastbootd dynamic partition deployment scripts for the **Lenovo Tab M11** (`TB311FU`, codename `poplar`).

---

## Hardware Specification

| Attribute | Specification |
| :--- | :--- |
| **Model** | Lenovo Tab M11 (`TB311FU`) |
| **Codename** | `poplar` |
| **SoC** | MediaTek Helio G88 (`MT8786` / `MT6768`) |
| **CPU** | 8-core (2x Cortex-A75 @ 2.0 GHz, 6x Cortex-A55 @ 1.8 GHz) |
| **GPU** | ARM Mali-G52 MP2 (Bifrost v8) |
| **Display** | 11.0" IPS LCD, 1200 x 1920 (WUXGA), 90Hz VDO |
| **Digitizer** | Himax HX83102E / Novatek NVT Active Stylus (Lenovo Tab Pen AP500U, 4096 levels) |
| **Audio** | Quad stereo speakers with dual smart power amplifiers (Awinic AW883xx) |
| **Storage / RAM** | 64GB / 128GB eMMC 5.1, 4GB / 8GB LPDDR4x |
| **Boot Header** | Android Boot Image Header Version 4 (`boot_a`, `boot_b`, `vendor_boot`) |

---

## Hardware Status Matrix

Forensic audit and live subsystem verification status on the live hardware:

| # | Subsystem | Status | Hardware Component | Operational Details |
| :--- | :--- | :---: | :--- | :--- |
| 1 | **Display / DRM** | **PASS** | 1200x1920 IPS Panel | Direct Rendering Manager (DRM/KMS) output via dispsys card, 90Hz refresh rate |
| 2 | **GPU Acceleration** | **PASS** | Mali-G52 MP2 | Panfrost / Mesa Gallium & OpenGL ES accelerated compositing |
| 3 | **Touchscreen** | **PASS** | Himax HX83102E / NVT | 1:1 coordinate mapping, multi-touch capacitive digitizer |
| 4 | **Active Stylus** | **PASS** | Lenovo AP500U Pen | 4096 pressure levels, 12mm hover telemetry, palm rejection |
| 5 | **Backlight Control** | **PASS** | 12-bit MTK LED PWM | Hardware minimum brightness clamped at PWM 48 (eliminates 0-nit blackouts) |
| 6 | **Audio Output** | **PASS** | Quad Speakers | ALSA scenario 1 routed to all 4 discrete speakers via Awinic smart PAs |
| 7 | **Wi-Fi Subsystem** | **PASS** | MT6631 Dual-Band PHY | 802.11a/b/g/n/ac operational; `wlan0` netdev managed via NetworkManager |
| 8 | **Bluetooth HCI** | **PASS** | MT6631 Bluetooth 5.0 | `/dev/stpbt` bridged to `/dev/vhci`; factory NVData MAC address persisted |
| 9 | **Battery / Power** | **PASS** | 7040 mAh Li-Po Battery | MT6358 PMIC / MT6370 fuel gauge monitoring and charging management |
| 10 | **Cellular Modem** | **N/A** | Wi-Fi Only Tablet | Baseband daemons cleanly suppressed (`ro.radio.noril=yes`) to eliminate wakelocks |

---

## Repository Structure

```
linux-lenovo-tb311fu/
├── ports/
│   └── postmarketos/
│       ├── device-lenovo-tb311fu/     # PostmarketOS device package (deviceinfo, APKBUILD)
│       └── linux-lenovo-tb311fu/      # Linux 6.6.142 kernel package (APKBUILD, configs)
├── udev/
│   ├── 70-tb311fu.rules              # Unified hardware permissions udev rule
│   └── rules.d/
│       ├── 80-tb311fu-rfkill.rules   # Network rfkill auto-unblock rules
│       ├── 89-tb311fu-audio.rules    # ALSA smart PA permissions
│       └── 90-tb311fu-touch.rules    # Touchscreen & AP500U pen digitizer tagging
├── patches/
│   ├── kwin/                         # KWin DRM 24-bit True Color fallback & rotation fix
│   │   ├── 0001-fix-drm-rotation-and-24bit-fallback.patch
│   │   └── apply_kwin_patch.py       # Binary patch tool for libkwin.so.6.x
│   └── kernel/
│       └── 0001-host-openssl.patch   # Kernel build environment compatibility patch
├── scripts/
│   ├── deployment/
│   │   ├── flash_pmos_fastbootd.ps1  # Production Fastbootd super deployment script (-S 64M)
│   │   ├── deploy_dual_linux.ps1     # Dual-boot staging and flashing manager
│   │   └── restore_pmos.ps1          # Live environment restore script
│   ├── rootfs_staging/
│   │   ├── stage_pmos_rootfs.py      # PostmarketOS root filesystem builder
│   │   ├── bake_ext4_image.py        # EXT4 raw/sparse image packaging engine
│   │   └── verify_super_budget.py    # Dynamic super partition headroom auditor
│   ├── session/                      # Plasma Mobile Wayland session configs
│   │   ├── tb311fu-plasma-session    # KWin Wayland session supervisor
│   │   ├── tb311fu-plasmashell       # Panfrost / OpenGL plasmashell wrapper
│   │   ├── tinydm.conf               # Autologin display manager configuration
│   │   └── org.kde.plasmashell.desktop
│   └── adaptation/                   # Subsystem helper daemons and utilities
│       ├── tb311fu-audio-setup       # ALSA scenario initialization
│       ├── tb311fu-backlight-sync    # Sysfs backlight synchronization
│       ├── tb311fu-bt                # WMT STP Bluetooth HCI bridge
│       └── tb311fu-wmt               # MediaTek WMT connectivity loader
└── drivers/
    ├── bluetooth/                    # MediaTek STP to Linux VHCI bridge
    ├── panel-tuning/                 # DSI panel timing, SSC, and reinitialization
    ├── panfrost/                     # ARM Mali Bifrost GKI integration helpers
    └── scanout/                      # Custom DRM scanout and overlay helpers
```

---

## Little Kernel (LK) & AVB Invariants

MediaTek Helio G88 Little Kernel (LK) bootloader mandates strict cryptographic and alignment checks when booting Android Header Version 4 boot images:

1. **Header Version 4 Invariant:**
   - Page size strictly set to `4096` bytes.
   - `os_version` and `os_patch_level` headers aligned to Android 15/16 security levels.
2. **AVB 2.0 Descriptor Alignment:**
   - $\text{VBMeta Offset} == \text{Raw Image Size}$.
   - The Hash Descriptor size must perfectly match the payload boundary to prevent Little Kernel 2-second Orange State reboot loops.
3. **Partition Preservation:**
   - Factory OEM `vbmeta.img`, `vbmeta_vendor.img`, and `vendor_boot.img` remain **100% untouched** on flash to preserve RSA4096 trust chaining.

---

## Deployment via Fastbootd (`-S 64M`)

Flashing dynamic logical partitions on Windows requires the strict `-S 64M` chunking standard to prevent WinUSB buffer exhaustion (Error 22: *Endpoint stall / IO error*).

### Fastbootd Flashing Procedure:

1. Reboot the tablet into fastbootd mode:
   ```bash
   adb reboot fastboot
   ```
2. Verify userspace fastbootd mode:
   ```bash
   fastboot getvar is-userspace
   # Must return: is-userspace: yes
   ```
3. Run the automated deployment script:
   ```powershell
   .\scripts\deployment\flash_pmos_fastbootd.ps1 -Execute
   ```
   *The script resizes `system_a` within the `super` partition budget, streams the 4.0 GiB rootfs using `-S 64M` chunking, flashes the Android v4 boot vector to `boot_a`, and wipes userdata for clean initialization.*

---

## Compositor & Display Rotation Fix

On MediaTek MT6768 dispsys DRM, KWin Wayland queries plane format capabilities and erroneously selects 10-bit color formats (`DRM_FORMAT_XRGB2101010` / `XR30`). When hardware rotation is requested in 10-bit mode, the MTK display subsystem fails atomic commit (`EINVAL`), resulting in a black screen or green tint.

To solve this:
1. Apply `patches/kwin/0001-fix-drm-rotation-and-24bit-fallback.patch` to KWin DRM backend source, OR:
2. Run the included binary patcher against `libkwin.so.6.x`:
   ```bash
   python patches/kwin/apply_kwin_patch.py /usr/lib/libkwin.so.6.7.5
   ```
This disables the 10-bit FourCC formats, forcing fallback to 24-bit True Color (`XRGB8888`), enabling seamless 90°/180°/270° orientation changes and hardware-accelerated rendering.

---

## Bi-Directional OS Switching

When running in a dual-boot or containerized coexistence environment, the system provides clean zero-reboot switching between Android and PostmarketOS:

- **Launch PostmarketOS Plasma Mobile:**
  ```bash
  adb shell su -c '/data/start_plasma.sh'
  ```
- **Return to Android SurfaceFlinger:**
  ```bash
  adb shell su -c '/data/stop_plasma.sh'
  ```

---

## Author & Maintainer

- **Maintainer:** Azmathulla Shaik (`BangerSoul`)
- **Contact:** `iamshaikhazmathulla@outlook.com`
- **GitHub:** [@BangerSoul](https://github.com/BangerSoul)

## License

This project is licensed under the **GNU General Public License v3.0** (GPL-3.0). See [LICENSE](LICENSE) for details.
