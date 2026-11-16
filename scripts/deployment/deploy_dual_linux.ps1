# Master Deployment Script: Deploy Ubuntu Touch & PostmarketOS to Lenovo Tab M11 (TB311FU)
# Architecture: Marcelino's Hybrid Pivot/Chroot via KernelSU Root on LineageOS 23.2 GSI baseline

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  TB311FU Dual Linux Bringup: Ubuntu Touch + PostmarketOS" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Preflight Check
Write-Host "`n[1/5] Verifying ADB Connection & Root Authority..." -ForegroundColor Yellow
$devices = adb devices
if ($devices -notmatch "HNQ09EZD\s+device") {
    Write-Host "Waiting for device to be online..." -ForegroundColor Yellow
    adb wait-for-device
}

$id = (adb shell su -c id) 2>&1
Write-Host "Current Root Authority: $id" -ForegroundColor Green
if ($id -notmatch "uid=0\(root\)") {
    Write-Error "Root authority not obtained. Please ensure KernelSU has granted root access."
}

# Ensure destination directories exist
adb shell "su -c 'mkdir -p /data/ubuntu /data/pmos /data/local/tmp'"

# 2. Deploy Ubuntu Touch (Focal 20.04 Lomiri)
Write-Host "`n[2/5] Deploying Ubuntu Touch (Lomiri)..." -ForegroundColor Yellow
$utTar = "c:\Users\BangerSoul\Documents\antigravity\fearless-maxwell\ubuntu_touch_backup\ubuntu_touch_rootfs_backup.tar.gz"
$utDeploy = "c:\Users\BangerSoul\Documents\antigravity\vibrant-hertz\deployment\ubuntu_touch"

Write-Host "Pushing Ubuntu Touch rootfs archive (1.45 GB)..." -ForegroundColor Gray
adb push $utTar /data/local/tmp/ubuntu_touch_rootfs.tar.gz

Write-Host "Extracting Ubuntu Touch rootfs into /data/ubuntu/..." -ForegroundColor Gray
adb shell "su -c 'tar -xzf /data/local/tmp/ubuntu_touch_rootfs.tar.gz -C /data/ubuntu/ && rm -f /data/local/tmp/ubuntu_touch_rootfs.tar.gz'"

Write-Host "Pushing Ubuntu Touch controller and bridge scripts..." -ForegroundColor Gray
adb push "$utDeploy\start_lomiri.sh" /data/local/tmp/start_lomiri.sh
adb push "$utDeploy\stop_lomiri.sh" /data/local/tmp/stop_lomiri.sh
adb push "$utDeploy\launch_lomiri.sh" /data/local/tmp/launch_lomiri.sh
adb push "$utDeploy\brightness-bridge.py" /data/local/tmp/brightness-bridge.py
adb push "$utDeploy\rotation-toggle.py" /data/local/tmp/rotation-toggle.py

adb shell "su -c 'mv /data/local/tmp/start_lomiri.sh /data/start_lomiri.sh && mv /data/local/tmp/stop_lomiri.sh /data/stop_lomiri.sh && mv /data/local/tmp/launch_lomiri.sh /data/ubuntu/launch_lomiri.sh && mkdir -p /data/ubuntu/usr/local/bin && mv /data/local/tmp/brightness-bridge.py /data/ubuntu/usr/local/bin/brightness-bridge.py && mv /data/local/tmp/rotation-toggle.py /data/ubuntu/usr/local/bin/rotation-toggle.py && chmod 755 /data/start_lomiri.sh /data/stop_lomiri.sh /data/ubuntu/launch_lomiri.sh /data/ubuntu/usr/local/bin/brightness-bridge.py /data/ubuntu/usr/local/bin/rotation-toggle.py'"
Write-Host "Ubuntu Touch deployed successfully!" -ForegroundColor Green

# 3. Deploy PostmarketOS (Plasma Mobile)
Write-Host "`n[3/5] Deploying PostmarketOS (Plasma Mobile)..." -ForegroundColor Yellow
$pmImg = "c:\Users\BangerSoul\Documents\antigravity\vibrant-hertz\rootfs_staging\rootfs_plasma_mobile.img"
$pmDeploy = "c:\Users\BangerSoul\Documents\antigravity\vibrant-hertz\deployment\postmarketos"

Write-Host "Pushing PostmarketOS rootfs image (4.0 GB)..." -ForegroundColor Gray
adb push $pmImg /data/local/tmp/rootfs_plasma_mobile.img
adb shell "su -c 'mv /data/local/tmp/rootfs_plasma_mobile.img /data/rootfs_plasma_mobile.img'"

Write-Host "Pushing PostmarketOS controller scripts & hardware shims..." -ForegroundColor Gray
adb push "$pmDeploy\start_plasma.sh" /data/local/tmp/start_plasma.sh
adb push "$pmDeploy\stop_plasma.sh" /data/local/tmp/stop_plasma.sh
adb shell "su -c 'mv /data/local/tmp/start_plasma.sh /data/start_plasma.sh && mv /data/local/tmp/stop_plasma.sh /data/stop_plasma.sh && chmod 755 /data/start_plasma.sh /data/stop_plasma.sh'"

Write-Host "PostmarketOS deployed successfully!" -ForegroundColor Green

# 4. Final Verification
Write-Host "`n[4/5] Verification of Installed Environments on /data:" -ForegroundColor Yellow
adb shell "su -c 'ls -ld /data/ubuntu /data/pmos /data/start_lomiri.sh /data/stop_lomiri.sh /data/start_plasma.sh /data/stop_plasma.sh /data/rootfs_plasma_mobile.img'"

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "  - To start Ubuntu Touch:   adb shell su -c /data/start_lomiri.sh" -ForegroundColor Cyan
Write-Host "  - To start PostmarketOS:   adb shell su -c /data/start_plasma.sh" -ForegroundColor Cyan
Write-Host "  - To return to Android:    adb shell su -c /data/stop_lomiri.sh" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Green
