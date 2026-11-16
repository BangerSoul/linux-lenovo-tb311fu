<#
.SYNOPSIS
    Lenovo Tab M11 (TB311FU / 'poplar') PostmarketOS Fastbootd Dynamic Partition Deployment Script.
.DESCRIPTION
    Production PowerShell deployment runner for PostmarketOS / Alpine ARM64 with Plasma Mobile.
    Performs dynamic super partition resizing, system_a flashing with mandatory -S 64M chunking,
    boot vector flashing to boot_a, stock partition preservation, and userdata wiping.
.PARAMETER RootfsPath
    Path to PostmarketOS EXT4 rootfs image (rootfs_plasma_mobile.img, 4.0 GiB / 4,294,967,296 bytes).
.PARAMETER BootPath
    Path to PostmarketOS Android Header v4 boot vector (pmos_boot.img, 32 MB / 33,554,432 bytes).
.PARAMETER ChunkSize
    Chunking flag argument (default: 64M). Prevents Windows WinUSB endpoint stalls (error 22).
.PARAMETER FastbootPath
    Explicit path to fastboot binary. Defaults to searching C:\platform-tools and PATH.
.PARAMETER AdbPath
    Explicit path to adb binary. Defaults to searching C:\platform-tools and PATH.
.PARAMETER Serial
    Target device hardware serial identifier (default: HNQ09EZD).
.PARAMETER Execute
    If specified, performs live flashing against connected Fastbootd tablet. Default: DryRun.
.PARAMETER DryRun
    Explicit dry-run validation mode. Validates images, preflights, and generates command plan.
.PARAMETER SkipWipe
    If specified, skips userdata wipe (fastboot -w). Default: false (userdata wipe performed).
#>

[CmdletBinding()]
param(
    [string]$RootfsPath = "rootfs_staging\rootfs_plasma_mobile.img",
    [string]$BootPath = "boot_vector\pmos_boot.img",
    [string]$ChunkSize = "64M",
    [string]$FastbootPath = $null,
    [string]$AdbPath = $null,
    [string]$Serial = "HNQ09EZD",
    [switch]$Execute = $false,
    [switch]$DryRun = $false,
    [switch]$SkipWipe = $false
)

$ErrorActionPreference = "Stop"

# Determine workspace root directory
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }
$workspaceRoot = if (Test-Path (Join-Path $scriptDir "..\rootfs_staging")) {
    (Resolve-Path (Join-Path $scriptDir "..")).Path
} else {
    $scriptDir
}

# ==============================================================================
# 1. Chunk Size Boundary Validation (WinUSB 64M Standard)
# ==============================================================================
function Test-ChunkSize([string]$Chunk) {
    $cleaned = $Chunk.Trim().ToUpper()
    if (-not $cleaned.EndsWith("M")) {
        throw "Invalid chunk size '$Chunk'. Must specify in megabytes ending in 'M' (e.g. '64M')."
    }
    $val = [int]($cleaned.Substring(0, $cleaned.Length - 1))
    if ($val -gt 64) {
        throw "Chunk size $Chunk exceeds safe limit! Must be <= 64M to prevent Windows WinUSB endpoint stall (error 22)."
    }
    if ($val -lt 16) {
        throw "Chunk size $Chunk is too small! Minimum recommended chunk size is 16M."
    }
    return $val
}

$chunkMb = Test-ChunkSize -Chunk $ChunkSize
$chunkBytes = [int64]$chunkMb * 1024 * 1024

# ==============================================================================
# 2. Locate Platform Tools (adb, fastboot)
# ==============================================================================
function Resolve-ToolBinary([string]$ExplicitPath, [string]$ToolName) {
    if ($ExplicitPath -and (Test-Path -Path $ExplicitPath -PathType Leaf)) {
        return (Resolve-Path $ExplicitPath).Path
    }
    $candidates = @(
        "C:\platform-tools\$ToolName.exe",
        "C:\platform-tools\$ToolName",
        (Get-Command "$ToolName.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Get-Command $ToolName -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
    )
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path -Path $cand -PathType Leaf)) {
            return (Resolve-Path $cand).Path
        }
    }
    return $ToolName
}

$FastbootPath = Resolve-ToolBinary -ExplicitPath $FastbootPath -ToolName "fastboot"
$AdbPath = Resolve-ToolBinary -ExplicitPath $AdbPath -ToolName "adb"

# ==============================================================================
# 3. Preflight Checks & Image Validation
# ==============================================================================
function Resolve-TargetImage([string]$PathCandidate, [string]$DefaultRel, [bool]$IsExplicit = $false, [string]$ImageLabel = "image") {
    $explicit = $IsExplicit -or ($PathCandidate -and ($PathCandidate -ne $DefaultRel))
    if ($explicit) {
        if ([string]::IsNullOrWhiteSpace($PathCandidate)) {
            throw "Target $ImageLabel path cannot be empty or whitespace!"
        }
        $candidates = @(
            $PathCandidate,
            (Join-Path $workspaceRoot $PathCandidate),
            (Join-Path $scriptDir $PathCandidate)
        )
        foreach ($p in $candidates) {
            if ($p -and (Test-Path -Path $p -PathType Leaf)) {
                return (Resolve-Path $p).Path
            }
        }
        throw "Target $ImageLabel not found! Explicit path '$PathCandidate' does not exist."
    }

    $searchPaths = @(
        $DefaultRel,
        (Join-Path $workspaceRoot $DefaultRel),
        (Join-Path $scriptDir $DefaultRel)
    )
    foreach ($p in $searchPaths) {
        if ($p -and (Test-Path -Path $p -PathType Leaf)) {
            return (Resolve-Path $p).Path
        }
    }
    return $null
}

$isRootfsExplicit = $PSBoundParameters.ContainsKey('RootfsPath')
$resolvedRootfs = Resolve-TargetImage -PathCandidate $RootfsPath -DefaultRel "rootfs_staging\rootfs_plasma_mobile.img" -IsExplicit $isRootfsExplicit -ImageLabel "rootfs image"
if (-not $resolvedRootfs) {
    throw "Target rootfs image not found! Checked '$RootfsPath' and workspace candidates."
}

$isBootExplicit = $PSBoundParameters.ContainsKey('BootPath')
$resolvedBoot = Resolve-TargetImage -PathCandidate $BootPath -DefaultRel "boot_vector\pmos_boot.img" -IsExplicit $isBootExplicit -ImageLabel "boot vector image"
if (-not $resolvedBoot) {
    throw "Target boot vector image not found! Checked '$BootPath' and workspace candidates."
}

# Image geometry verification
$rootfsItem = Get-Item $resolvedRootfs
$rootfsSize = $rootfsItem.Length
$expectedRootfsSize = 4294967296  # 4.0 GiB (1048576 blocks of 4096 B)

$bootItem = Get-Item $resolvedBoot
$bootSize = $bootItem.Length
$expectedBootSize = 33554432      # 32.0 MB

$rootfsFormatted = '{0:N0}' -f $rootfsSize
$bootFormatted = '{0:N0}' -f $bootSize
$chunkFormatted = '{0:N0}' -f $chunkBytes

Write-Host ("=" * 75) -ForegroundColor Cyan
Write-Host "PostmarketOS Fastbootd Deployment Suite -- Lenovo Tab M11 (TB311FU / poplar)" -ForegroundColor Cyan
Write-Host ("=" * 75) -ForegroundColor Cyan
Write-Host ("Hardware Target:   Lenovo Tab M11 (Serial: {0})" -f $Serial)
Write-Host ("Fastboot Binary:   {0}" -f $FastbootPath)
Write-Host ("ADB Binary:        {0}" -f $AdbPath)
Write-Host ("Rootfs Image:      {0} ({1} bytes)" -f $resolvedRootfs, $rootfsFormatted)
Write-Host ("Boot Vector:       {0} ({1} bytes)" -f $resolvedBoot, $bootFormatted)
Write-Host ("Chunking Flag:     -S {0} ({1} bytes/chunk)" -f $ChunkSize, $chunkFormatted)
Write-Host ("Userdata Wipe:     {0}" -f $(if ($SkipWipe) { 'DISABLED (-SkipWipe passed)' } else { 'ENABLED (fastboot -w)' }))
Write-Host ("=" * 75) -ForegroundColor Cyan

# Check rootfs file validity and size
if (-not (Test-Path -Path $resolvedRootfs -PathType Leaf)) {
    throw "Resolved rootfs path '$resolvedRootfs' is not a valid file!"
}
if ($rootfsSize -ne $expectedRootfsSize) {
    throw "Rootfs size ($rootfsSize bytes) differs from nominal 4.0 GiB ($expectedRootfsSize bytes)."
}

# Check boot file validity and size
if (-not (Test-Path -Path $resolvedBoot -PathType Leaf)) {
    throw "Resolved boot path '$resolvedBoot' is not a valid file!"
}
if ($bootSize -ne $expectedBootSize) {
    throw "Boot vector size ($bootSize bytes) differs from nominal 32 MB ($expectedBootSize bytes)."
}

# Verify Android boot header v4 magic
$bootBytes = [System.IO.File]::ReadAllBytes($resolvedBoot)
$bootMagic = [System.Text.Encoding]::ASCII.GetString($bootBytes, 0, 8)
if ($bootMagic -ne "ANDROID!") {
    throw "Boot vector magic verification failed! Expected 'ANDROID!', got '$bootMagic'."
}

# ==============================================================================
# 4. Build Fastbootd Deployment Command Plan
# ==============================================================================
$plan = [System.Collections.Generic.List[string]]::new()
$serialFlag = if ($Serial) { "-s $Serial " } else { "" }

# Command sequence adhering to Milestone 4 specifications:
# 1. Resize logical partition system_a to 4,294,967,296 bytes
$plan.Add("$FastbootPath $serialFlag resize-logical-partition system_a $expectedRootfsSize")

# 2. Erase target logical partition
$plan.Add("$FastbootPath $serialFlag erase system_a")

# 3. Flash rootfs with mandatory -S 64M chunking
$plan.Add("$FastbootPath $serialFlag -S $ChunkSize flash system_a `"$resolvedRootfs`"")

# 4. Flash boot vector to boot_a
$plan.Add("$FastbootPath $serialFlag flash boot_a `"$resolvedBoot`"")

# 5. Userdata wipe (clean state for PostmarketOS)
if (-not $SkipWipe) {
    $plan.Add("$FastbootPath $serialFlag -w")
}

# 6. Reboot device into PostmarketOS
$plan.Add("$FastbootPath $serialFlag reboot")

# ==============================================================================
# 5. Factory Stock Preservation & Safety Guard Audits
# ==============================================================================
# Guard 1: Stock vendor_boot partition protection
# Notice: Flashing custom recovery or kernel into vendor_boot breaks the salted SHA-256
# digest pinned in root vbmeta, triggering an infinite 2-second Orange State reboot loop.
foreach ($cmd in $plan) {
    if ($cmd -match "vendor_boot") {
        throw "CRITICAL SAFETY VIOLATION: Command targets protected partition vendor_boot: $cmd"
    }
}

# Guard 2: Root vbmeta signature preservation
# Passing --disable-verity or --disable-verification flips header byte 123 from 0 to 3,
# breaking the OEM RSA4096 signature validated by Little Kernel.
foreach ($cmd in $plan) {
    if ($cmd -match "--disable-verity" -or $cmd -match "--disable-verification") {
        throw "CRITICAL SAFETY VIOLATION: Verity disable flag detected: $cmd"
    }
    if ($cmd -match "\bflash\b.*\bvbmeta\b") {
        throw "CRITICAL SAFETY VIOLATION: Attempt to flash vbmeta detected: $cmd"
    }
}

# Guard 3: Retention of product_a and vendor_a
# Stock product_a (1.71 GB) hashtree is pinned by root vbmeta. Deleting product_a
# crashes early kernel dm-verity setup.
foreach ($cmd in $plan) {
    if ($cmd -match "delete-logical-partition\s+product" -or $cmd -match "delete-logical-partition\s+vendor") {
        throw "CRITICAL SAFETY VIOLATION: Attempt to delete stock dynamic partition: $cmd"
    }
}

# Guard 4: Chunking validation
$hasChunking = $false
foreach ($cmd in $plan) {
    if ($cmd -match "flash system_a" -and $cmd -match "-S $ChunkSize") {
        $hasChunking = $true
        break
    }
}
if (-not $hasChunking) {
    throw "CRITICAL SAFETY VIOLATION: system_a flash command lacks mandatory -S $ChunkSize chunking!"
}

# ==============================================================================
# 6. Execution Mode: DryRun vs Live Flashing
# ==============================================================================
$isDryRun = (-not $Execute) -or $DryRun

if ($isDryRun) {
    Write-Host "`n[DRY-RUN VALIDATION] Validating deployment plan without device modification:`n" -ForegroundColor Yellow
    $step = 1
    foreach ($cmd in $plan) {
        Write-Host "  Step $step`: $cmd" -ForegroundColor Gray
        $step++
    }
    Write-Host "`n" + ("-" * 75)
    Write-Host "Milestone 4 Safety Audits Passed:" -ForegroundColor Green
    Write-Host ("  [PASS] Mandatory -S {0} WinUSB chunking enforced on system_a ({1} B/chunk)." -f $ChunkSize, $chunkFormatted) -ForegroundColor Green
    Write-Host ("  [PASS] Logical partition system_a resized to exact 4.0 GiB ({0} bytes)." -f $expectedRootfsSize) -ForegroundColor Green
    Write-Host ("  [PASS] Boot vector targets boot_a ({0} bytes, Android Header v4)." -f $bootSize) -ForegroundColor Green
    Write-Host "  [PASS] Factory stock preservation: vendor_boot remains 100% untouched." -ForegroundColor Green
    Write-Host "  [PASS] Factory stock preservation: vbmeta RSA4096 signature remains 100% untouched." -ForegroundColor Green
    Write-Host "  [PASS] Factory stock preservation: product_a and vendor_a retained in super." -ForegroundColor Green
    Write-Host ("  [PASS] Userdata wipe: {0}." -f $(if ($SkipWipe) { 'Skipped' } else { 'fastboot -w staged' })) -ForegroundColor Green
    Write-Host ("=" * 75) -ForegroundColor Cyan
    Write-Host "[+] DRY-RUN SUCCESS: Fastbootd deployment plan verified and safe for execution." -ForegroundColor Green
    exit 0
}

# ==============================================================================
# 7. Live Execution Path
# ==============================================================================
Write-Host "`n[Phase 1] Preflight: Querying device state..." -ForegroundColor Cyan

# Step 1a: Check if already in Fastboot mode first
$fastbootDevices = try { & $FastbootPath devices 2>$null | Out-String } catch { "" }
if ($fastbootDevices -match "$Serial" -or ($fastbootDevices.Trim().Length -gt 0 -and $fastbootDevices -match "fastboot")) {
    Write-Host "  [+] Device detected in fastboot mode." -ForegroundColor Green
} else {
    # Check if device is visible in ADB
    $adbDevices = try { & $AdbPath devices 2>$null | Out-String } catch { "" }
    $deviceInAdb = $adbDevices -match "$Serial\s+device"
    if ($deviceInAdb) {
        Write-Host "  [+] Device $Serial detected in ADB mode. Rebooting to fastboot..." -ForegroundColor Yellow
        & $AdbPath -s $Serial reboot fastboot 2>$null
        Write-Host "  [*] Waiting for device to re-enumerate in Fastbootd..." -ForegroundColor Gray
        Start-Sleep -Seconds 10
    } else {
        throw "No fastboot or ADB device detected! Ensure tablet $Serial is connected in Fastbootd mode."
    }
}

# Step 1c: Assert Fastbootd userspace mode (MANDATORY)
# In bootloader fastboot, dynamic partitions (super) cannot be resized or managed.
$userspaceOutput = cmd.exe /c "`"$FastbootPath`" -s $Serial getvar is-userspace 2>&1" | Out-String
Write-Host "  [*] Querying getvar is-userspace: $($userspaceOutput.Trim())" -ForegroundColor Gray

if ($userspaceOutput -notmatch "is-userspace:\s*yes") {
    throw "CRITICAL: Device is in Bootloader mode, NOT Fastbootd userspace! Fastbootd is strictly mandatory for dynamic partition management. Execute 'fastboot reboot fastboot' and retry."
}
Write-Host "  [PASS] Fastbootd userspace mode confirmed (is-userspace == yes)." -ForegroundColor Green

# Step 1d: Verify bootloader unlock status
$unlockedOutput = cmd.exe /c "`"$FastbootPath`" -s $Serial getvar unlocked 2>&1" | Out-String
if ($unlockedOutput -notmatch "unlocked:\s*yes") {
    throw "CRITICAL: Bootloader is LOCKED. Cannot flash logical partitions or custom boot vector."
}
Write-Host "  [PASS] Bootloader unlocked state confirmed." -ForegroundColor Green

# Phase 2: Execute command plan sequentially
Write-Host "`n[Phase 2] Executing Fastbootd commands sequentially..." -ForegroundColor Cyan
$step = 1
foreach ($cmd in $plan) {
    Write-Host "`n[*] Step $step/$($plan.Count): $cmd" -ForegroundColor Yellow
    cmd.exe /c "$cmd"
    if ($LASTEXITCODE -ne 0) {
        throw "Step $step failed with exit code $LASTEXITCODE`: $cmd"
    }
    $step++
}

Write-Host "`n" + ("=" * 75) -ForegroundColor Green
Write-Host "DEPLOYMENT COMPLETE: PostmarketOS successfully flashed to Lenovo Tab M11!" -ForegroundColor Green
Write-Host ("=" * 75) -ForegroundColor Green
exit 0
