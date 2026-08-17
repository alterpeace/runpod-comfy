# tunnel_webui.ps1 - Forward a RunPod ComfyUI WebUI to a Windows machine
#
# POD mode (direct SSH forward) - for Pods, which have public SSH:
#   .\scripts\tunnel_webui.ps1 -PodHost <POD_PUBLIC_IP> -PodPort <POD_SSH_PORT>
# Get IP/port from the pod's "Connect" panel in the RunPod console.
# Pod needs: ENABLE_SSH=true + SSH_PUBLIC_KEY set, TCP 22 exposed.
# Uses the OpenSSH client built into Windows 10/11 (ssh.exe).

param(
    [Parameter(Mandatory = $true)]
    [string]$PodHost,

    [int]$PodPort = 22,
    [int]$LocalPort = 8188
)

$ErrorActionPreference = "Stop"

if (-not $PodHost) {
    Write-Error "Needs -PodHost <POD_PUBLIC_IP> (and -PodPort if not 22)"
    exit 1
}
if (-not (Get-Command ssh.exe -ErrorAction SilentlyContinue)) {
    Write-Error "ssh.exe not found. Install Windows OpenSSH Client: Settings > Apps > Optional Features > Add a feature > OpenSSH Client"
    exit 1
}

Write-Host "==> Forwarding pod ${PodHost}:${PodPort} -> http://localhost:$LocalPort" -ForegroundColor Cyan
Write-Host "==> Ctrl+C to close the tunnel" -ForegroundColor Cyan

# -N: no remote command; ServerAliveInterval keeps the conn alive through NAT
$sshArgs = @(
    "-N",
    "-L", "${LocalPort}:127.0.0.1:8188",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "-o", "ExitOnForwardFailure=yes",
    "root@${PodHost}", "-p", "$PodPort"
)

$proc = Start-Process ssh.exe -ArgumentList $sshArgs -NoNewWindow -PassThru
Start-Sleep -Seconds 2

if ($proc.HasExited) {
    Write-Error "ssh exited immediately - check the pod IP/port and that your SSH_PUBLIC_KEY is on the pod"
    exit 1
}

Start-Process "http://localhost:$LocalPort"
Write-Host "==> WebUI: http://localhost:$LocalPort" -ForegroundColor Green
Wait-Process -Id $proc.Id
