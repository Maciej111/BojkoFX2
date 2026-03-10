#!/usr/bin/env pwsh
# =============================================================================
#  BojkoFx - GCP VM Setup Script
#  Creates a locked-down VM for 24/7 algorithmic trading
#  Usage: .\scripts\setup-gcp-vm.ps1
# =============================================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
$Project     = "sandbox-439719"
$Region      = "us-central1"
$Zone        = "us-central1-a"
$IpName      = "bojkofx-ip"
$VmName      = "bojkofx-vm"
$MachineType = "e2-small"
$DiskSizeGB  = "20"
$DiskType    = "pd-ssd"
$Tag         = "bojkofx"
$FwRuleName  = "bojkofx-allow-ssh"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Skip { param($msg) Write-Host "    [SKIP] $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "    [ERR] $msg" -ForegroundColor Red; exit 1 }

function Invoke-Gcloud {
    param([string[]]$GcloudArgs)
    $output = & gcloud @GcloudArgs 2>&1
    if ($LASTEXITCODE -ne 0) { return $null }
    return $output
}

# ---------------------------------------------------------------------------
# 1. Project + public IP
# ---------------------------------------------------------------------------
Write-Step "Using GCP project: $Project"

Write-Step "Detecting your current public IP"
$MyIp = $null
foreach ($url in @("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com")) {
    try {
        $MyIp = (Invoke-RestMethod -Uri $url -TimeoutSec 5).Trim()
        if ($MyIp -match '^\d{1,3}(\.\d{1,3}){3}$') { break }
        $MyIp = $null
    } catch { $MyIp = $null }
}
if (-not $MyIp) { Write-Fail "Could not detect public IP. Check internet connection." }
Write-OK "Your public IP: $MyIp"

# ---------------------------------------------------------------------------
# 2. Create static external IP (idempotent)
# ---------------------------------------------------------------------------
Write-Step "Creating static IP: $IpName"
$existingIp = Invoke-Gcloud @("compute","addresses","describe",$IpName,"--region",$Region,"--format","value(address)","--project",$Project)
if ($existingIp) {
    $StaticIp = $existingIp.Trim()
    Write-Skip "Static IP already exists: $StaticIp"
} else {
    & gcloud compute addresses create $IpName `
        --region $Region `
        --network-tier PREMIUM `
        --project $Project
    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to create static IP." }
    $StaticIp = (& gcloud compute addresses describe $IpName `
        --region $Region `
        --format "value(address)" `
        --project $Project).Trim()
    Write-OK "Static IP allocated: $StaticIp"
}

# ---------------------------------------------------------------------------
# 3. Create VM instance (idempotent)
# ---------------------------------------------------------------------------
Write-Step "Creating VM: $VmName"
$existingVm = Invoke-Gcloud @("compute","instances","describe",$VmName,"--zone",$Zone,"--project",$Project,"--format","value(name)")
if ($existingVm) {
    Write-Skip "VM already exists: $VmName"
} else {
    & gcloud compute instances create $VmName `
        --project $Project `
        --zone $Zone `
        --machine-type $MachineType `
        --image-family ubuntu-2204-lts `
        --image-project ubuntu-os-cloud `
        --boot-disk-size $DiskSizeGB `
        --boot-disk-type $DiskType `
        --boot-disk-device-name $VmName `
        --address $IpName `
        --tags $Tag `
        --no-shielded-secure-boot `
        --metadata "block-project-ssh-keys=false" `
        --format "table(name,zone,machineType,networkInterfaces[0].accessConfigs[0].natIP:label=EXTERNAL_IP,status)"
    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to create VM." }
    Write-OK "VM created: $VmName"
}

# ---------------------------------------------------------------------------
# 4. Firewall rule - SSH only from current IP (delete+recreate if IP changed)
# ---------------------------------------------------------------------------
Write-Step "Configuring firewall rule: $FwRuleName"
$existingRule = Invoke-Gcloud @("compute","firewall-rules","describe",$FwRuleName,"--project",$Project,"--format","value(sourceRanges[0])")

if ($existingRule) {
    $existingSource = $existingRule.Trim()
    if ($existingSource -eq "$MyIp/32") {
        Write-Skip "Firewall rule already correct (source: $existingSource)"
    } else {
        Write-Host "    [INFO] Source IP changed ($existingSource -> $MyIp/32). Updating rule..." -ForegroundColor Yellow
        & gcloud compute firewall-rules delete $FwRuleName --project $Project --quiet
        if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to delete old firewall rule." }
        & gcloud compute firewall-rules create $FwRuleName `
            --project $Project `
            --direction INGRESS `
            --priority 1000 `
            --network default `
            --action ALLOW `
            --rules tcp:22 `
            --source-ranges "$MyIp/32" `
            --target-tags $Tag
        if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to recreate firewall rule." }
        Write-OK "Firewall rule updated: SSH from $MyIp/32"
    }
} else {
    & gcloud compute firewall-rules create $FwRuleName `
        --project $Project `
        --direction INGRESS `
        --priority 1000 `
        --network default `
        --action ALLOW `
        --rules tcp:22 `
        --source-ranges "$MyIp/32" `
        --target-tags $Tag
    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to create firewall rule." }
    Write-OK "Firewall rule created: SSH from $MyIp/32 -> tag:$Tag"
}

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
$SshUser = $env:USERNAME.ToLower() -replace '[^a-z0-9_]', '_'

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Magenta
Write-Host "  BojkoFx VM - Setup Complete" -ForegroundColor Magenta
Write-Host "======================================================================" -ForegroundColor Magenta
Write-Host "  VM Name       : $VmName" -ForegroundColor White
Write-Host "  Zone          : $Zone" -ForegroundColor White
Write-Host "  Machine Type  : $MachineType" -ForegroundColor White
Write-Host "  Static IP     : $StaticIp" -ForegroundColor Green
Write-Host "  SSH Allowed   : $MyIp/32 only" -ForegroundColor White
Write-Host ""
Write-Host "  SSH Command:" -ForegroundColor Yellow
Write-Host "  ssh $SshUser@$StaticIp" -ForegroundColor Green
Write-Host ""
Write-Host "  First-time connect (via gcloud):" -ForegroundColor Yellow
Write-Host "  gcloud compute ssh $VmName --zone $Zone --project $Project" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Magenta
Write-Host ""

