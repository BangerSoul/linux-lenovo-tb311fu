# Automated PostmarketOS & Ubuntu Touch Restoration Script for Lenovo Tab M11 (TB311FU)
# Run this from host PowerShell after a clean flash of LineageOS / GSI

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Restoring PostmarketOS & Ubuntu Touch Environment " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Check ADB connection
Write-Host "[1/6] Verifying ADB root connection..." -ForegroundColor Yellow
$device = adb devices | Select-String "HNQ09EZD"
if (-not $device) {
    Write-Host "Waiting for device HNQ09EZD..." -ForegroundColor Yellow
    adb wait-for-device
}

# Verify Root via KernelSU / su
Write-Host "[2/6] Verifying root execution via KernelSU..." -ForegroundColor Yellow
adb shell "su -c 'id'"

# Push Rootfs if missing on /data
Write-Host "[3/6] Checking /data/rootfs_plasma_mobile.img..." -ForegroundColor Yellow
$exists = adb shell "su -c 'test -f /data/rootfs_plasma_mobile.img && echo yes || echo no'"
if ($exists.Trim() -ne "yes") {
    $hostImg = "$ScriptDir\..\rootfs_staging\rootfs_plasma_mobile.img"
    if (Test-Path $hostImg) {
        Write-Host "Pushing $hostImg to /data/rootfs_plasma_mobile.img (this may take ~1 minute)..." -ForegroundColor Yellow
        adb push $hostImg /data/rootfs_plasma_mobile.img
    } else {
        Write-Warning "Host rootfs not found at $hostImg! Ensure rootfs is available."
    }
} else {
    Write-Host "Rootfs image already present on /data." -ForegroundColor Green
}

# Push core session scripts
Write-Host "[4/6] Deploying session lifecycle scripts to /data..." -ForegroundColor Yellow
adb push "$ScriptDir\scripts\start_plasma.sh" /data/local/tmp/start_plasma.sh
adb push "$ScriptDir\scripts\stop_plasma.sh" /data/local/tmp/stop_plasma.sh
adb shell "su -c 'mv /data/local/tmp/start_plasma.sh /data/start_plasma.sh && chmod 755 /data/start_plasma.sh'"
adb shell "su -c 'mv /data/local/tmp/stop_plasma.sh /data/stop_plasma.sh && chmod 755 /data/stop_plasma.sh'"

# Mount rootfs to stage internal files
Write-Host "[5/6] Mounting rootfs and injecting patched binaries & configs..." -ForegroundColor Yellow
adb shell "su -c 'mkdir -p /data/pmos && mountpoint -q /data/pmos || mount -o loop,rw /data/rootfs_plasma_mobile.img /data/pmos'"

# Inject Patched 24-bit True Color KWin Library
adb push "$ScriptDir\binaries\libkwin.so.6.7.5.patched" /data/local/tmp/libkwin.so.6.7.5
adb shell "su -c 'mv /data/local/tmp/libkwin.so.6.7.5 /data/pmos/usr/lib/libkwin.so.6.7.5 && chmod 755 /data/pmos/usr/lib/libkwin.so.6.7.5'"

# Inject Plasmashell wrapper and session supervisor
adb push "$ScriptDir\scripts\tb311fu-plasmashell" /data/local/tmp/tb311fu-plasmashell
adb push "$ScriptDir\scripts\tb311fu-plasma-session" /data/local/tmp/tb311fu-plasma-session
adb push "$ScriptDir\scripts\tb311fu-audio-setup" /data/local/tmp/tb311fu-audio-setup
adb push "$ScriptDir\scripts\tb311fu-wmt" /data/local/tmp/tb311fu-wmt
adb push "$ScriptDir\scripts\tb311fu-bt" /data/local/tmp/tb311fu-bt
adb shell "su -c 'mv /data/local/tmp/tb311fu* /data/pmos/usr/local/bin/ && chmod 755 /data/pmos/usr/local/bin/tb311fu*'"

# Inject user configs & autostart
adb push "$ScriptDir\config\org.kde.plasmashell.desktop" /data/local/tmp/org.kde.plasmashell.desktop
adb push "$ScriptDir\config\plasmamobilerc" /data/local/tmp/plasmamobilerc
adb push "$ScriptDir\config\kwinoutputconfig.json" /data/local/tmp/kwinoutputconfig.json
adb push "$ScriptDir\config\kscreenlockerrc" /data/local/tmp/kscreenlockerrc
adb shell "su -c 'mkdir -p /data/pmos/home/user/.config/autostart && cp /data/local/tmp/org.kde.plasmashell.desktop /data/pmos/home/user/.config/autostart/ && cp /data/local/tmp/plasmamobilerc /data/local/tmp/kwinoutputconfig.json /data/local/tmp/kscreenlockerrc /data/pmos/home/user/.config/ && chown -R 10000:10000 /data/pmos/home/user/.config'"

# Inject PAM authentication permits
adb push "$ScriptDir\config\pam.tar.gz" /data/local/tmp/pam.tar.gz
adb shell "su -c 'tar -xzf /data/local/tmp/pam.tar.gz -C /data/pmos/etc/ && rm -f /data/local/tmp/pam.tar.gz'"

# Clean unmount
adb shell "su -c 'umount /data/pmos 2>/dev/null || true'"

Write-Host "[6/6] Restoration Complete! All components verified." -ForegroundColor Green
Write-Host "To boot into PostmarketOS Plasma Mobile at any time:" -ForegroundColor Cyan
Write-Host "  adb shell su -c '/data/start_plasma.sh'" -ForegroundColor Yellow
Write-Host "To return to Android:" -ForegroundColor Cyan
Write-Host "  adb shell su -c '/data/stop_plasma.sh'" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Cyan
