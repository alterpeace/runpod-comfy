# tunnel_webui.ps1 - Forward a RunPod ComfyUI WebUI to a Windows machine
#
# TWO MODES:
#
#   1) POD mode (direct SSH forward) - for Pods, which have public SSH:
#        .\scripts\tunnel_webui.ps1 -Mode pod -PodHost <POD_PUBLIC_IP> -PodPort <POD_SSH_PORT>
#      Get IP/port from the pod's "Connect" panel in the RunPod console.
#      Pod needs: ENABLE_SSH=true + SSH_PUBLIC_KEY set, TCP 22 exposed.
#      Uses the OpenSSH client built into Windows 10/11 (ssh.exe).
#
#   2) ZITI mode (sanctuary overlay) - for SERVERLESS workers (no inbound SSH):
#        .\scripts\tunnel_webui.ps1 -Mode ziti
#      Requires Ziti Desktop Edge installed + your client identity enrolled,
#      and the worker joined to sanctuary (see docs/WEBUI_ACCESS.md).
#      Worker side: drop ziti-identity.json + .env on the network volume:
#        /runpod-volume/ziti-identity.json
#        /runpod-volume/.env  containing:
#          OPENZITI_IDENTITY=/runpod-volume/ziti-identity.json
#          OPENZITI_SERVICE_HTTP=comfyui-http
#          OPENZITI_SERVICE_SSH=comfyui-ssh
#      entrypoint.sh sources /runpod-volume/.env at every worker boot.

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("pod", "ziti")]
    [string]$Mode,

    [string]$PodHost,
    [int]$PodPort = 22,
    [int]$LocalPort = 8188,
    [string]$ZitiService = "comfyui-http"
)

$ErrorActionPreference = "Stop"

if ($Mode -eq "pod") {
    if (-not $PodHost) {
        Write-Error "Pod mode needs -PodHost <POD_PUBLIC_IP> (and -PodPort if not 22)"
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
}
elseif ($Mode -eq "ziti") {
    $zde = Get-Process "ZitiDesktopEdge" -ErrorAction SilentlyContinue
    if ($zde) {
        Write-Host "==> Ziti Desktop Edge is running" -ForegroundColor Green
    } else {
        Write-Warning "Ziti Desktop Edge not detected. Install from https://openziti.io/docs/downloads then enroll your client identity."
    }
    Write-Host "==> WebUI: http://${ZitiService}.ziti (once the worker is enrolled and running)" -ForegroundColor Green
    Start-Process "http://${ZitiService}.ziti"
}
