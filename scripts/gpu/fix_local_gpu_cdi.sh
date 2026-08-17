#!/bin/bash
# Workaround for local GPU passthrough on Podman 4.9.x (e.g. Linux Mint 22 / Ubuntu 24.04
# "noble"), when `docker` is actually a Podman/crun install.
#
# Symptom:
#   $ docker run --rm --device nvidia.com/gpu=all nvidia/cuda:12.9.0-runtime-ubuntu24.04 nvidia-smi -L
#   Error: setting up CDI devices: unresolvable CDI devices nvidia.com/gpu=all
#
# Root cause:
#   NVIDIA Container Toolkit >= 1.17 generates CDI specs using schema v0.7.0, which added
#   an `additionalGids` field. Podman 4.9.3's bundled CDI library doesn't know this field
#   and refuses to parse the whole spec file, so it can never resolve the GPU device -
#   not even after downgrading the `cdiVersion` string alone.
#
# Fix:
#   1. Regenerate the CDI spec.
#   2. Rewrite `cdiVersion: 0.7.0` -> `0.6.0` (the schema version Podman 4.9.3 supports).
#   3. Strip the `additionalGids` blocks (device nodes already carry per-node `gid`, so
#      this doesn't remove any access - just the field newer Podman doesn't need).
#   4. Copy the same file to /var/run/cdi/nvidia.yaml, which is the runtime-refreshed
#      copy systemd's nvidia-cdi-refresh.service writes to (tmpfs, so it also resets on
#      every reboot and needs the same patch reapplied).
#
# This is a LOCAL DEVELOPMENT workaround only. RunPod does not use this container runtime
# or CDI config, so it is unaffected and does not need this script.
#
# Usage:
#   ./scripts/gpu/fix_local_gpu_cdi.sh
#
# Re-run this after: a reboot, an NVIDIA driver update, or an nvidia-container-toolkit update.

set -euo pipefail

CDI_ETC_FILE="/etc/cdi/nvidia.yaml"
CDI_RUN_FILE="/var/run/cdi/nvidia.yaml"

if ! command -v nvidia-ctk &>/dev/null; then
    echo "[ERROR] nvidia-ctk not found. Install the NVIDIA Container Toolkit first." >&2
    exit 1
fi

echo "[INFO] Regenerating CDI spec at ${CDI_ETC_FILE}..."
sudo nvidia-ctk cdi generate --output="${CDI_ETC_FILE}"

echo "[INFO] Downgrading cdiVersion to 0.6.0 (Podman 4.9.x compatibility)..."
sudo sed -i 's/cdiVersion: 0\.7\.0/cdiVersion: 0.6.0/' "${CDI_ETC_FILE}"

echo "[INFO] Stripping additionalGids fields (unsupported by Podman 4.9.x's CDI parser)..."
sudo python3 -c "
import re
path = '${CDI_ETC_FILE}'
with open(path) as f:
    content = f.read()
new_content = re.sub(r'[ \t]*additionalGids:\n(?:[ \t]+- \d+\n)+', '', content)
with open(path, 'w') as f:
    f.write(new_content)
"

echo "[INFO] Syncing patched spec to ${CDI_RUN_FILE} (tmpfs, refreshed by nvidia-cdi-refresh.service)..."
sudo mkdir -p "$(dirname "${CDI_RUN_FILE}")"
sudo cp "${CDI_ETC_FILE}" "${CDI_RUN_FILE}"

echo "[INFO] Verifying GPU passthrough..."
if docker run --rm --device nvidia.com/gpu=all nvidia/cuda:12.9.0-runtime-ubuntu24.04 nvidia-smi -L; then
    echo "[SUCCESS] GPU is visible inside the container. You can now run: docker compose up"
else
    echo "[ERROR] GPU still not visible. Check 'podman --version' (needs CDI v0.6 support) and driver install." >&2
    exit 1
fi
