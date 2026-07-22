# Testing the LTX-2.3 Build: Local → RunPod

Notes on validating this repo's LTX-2.3 changes (Dockerfile bump, custom
nodes, model manifest, install scripts) locally before pushing anywhere,
then testing on RunPod.

## Before You Build: Check Your GPU Architecture

`docker-compose.yml` defaults `TORCH_CUDA_ARCH_LIST=8.9` (Ada / RTX 40-series).
SageAttention and FlashAttention are compiled from source against this
target — if your local GPU has a **different** compute capability, the
compiled kernels won't run on it.

Check your GPU's compute capability before building:

```bash
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
```

Common values:

| GPU generation | Example cards | Compute capability |
|---|---|---|
| Turing | RTX 20xx, GTX 16xx | 7.5 |
| Ampere | RTX 30xx, A4000/A5000 | 8.6 |
| Ada | RTX 40xx | 8.9 |
| Hopper | H100 | 9.0 |
| Blackwell | RTX 50xx | 12.0 |

Override `TORCH_CUDA_ARCH_LIST` to match your card before building locally.
RunPod's default GPU pool skews Ampere/Ada, so the `8.9` default in
`docker-compose.yml` is tuned for *that* target, not necessarily your local
dev machine.

## 1. Local Build and Smoke Test

### Create a local `.env`

Not committed (`.gitignore` excludes `.env`). Set VRAM-appropriate
ComfyUI args for your card — e.g. for an 8GB card:

```env
MODE=local
COMFYUI_PORT=8188
COMFYUI_ARGS=--lowvram --disable-smart-memory
```

### Build with the correct arch

```bash
export TORCH_CUDA_ARCH_LIST=7.5   # match YOUR GPU, not the repo default
export MAX_JOBS=4
docker compose build
```

This compiles SageAttention/FlashAttention from source — expect this step
alone to take 20-40+ minutes depending on CPU, on top of base image and
dependency install time. Reduce `MAX_JOBS` if the build OOMs or crashes.

### Start and verify

```bash
docker compose up -d
docker compose logs -f comfy   # watch for "ComfyUI WebUI is ready"
```

```bash
curl -f http://localhost:8188/
```

Then open `http://localhost:8188` in a browser and manually queue a simple
workflow — this is the real smoke test, not just the health check.

### Install LTX-2.3 nodes and models inside the running container

```bash
docker exec -it comfy bash
cd /workspace
export HF_TOKEN=hf_...   # only needed for gated Lightricks IC-LoRA repos
./scripts/install_ltx23.sh --profile low_vram_8gb   # pick the profile matching your VRAM
```

See `docs/LTX_2.3_V2V_ICLORA_SETUP.md` for the full profile list.

### Run the automated handler test

Separate from the manual `docker compose` container above — this uses its
own container (`comfyui-test`, default port `8188`). Don't run both
simultaneously without changing `TEST_PORT`.

```bash
IMAGE_NAME=comfyui-serverless:local ./scripts/test_local.sh examples/text_to_image_simple.json
```

## 2. Pushing to a Git Remote

Check which remote you're actually configured against before pushing —
this repo's `origin` may point at a self-hosted Gitea instance rather than
GitHub:

```bash
git remote -v
```

If you want a GitHub remote in addition to (or instead of) the existing
one:

```bash
git remote add github git@github.com:<you>/<repo>.git
git push -u github <branch>
```

Push to a new branch, not directly to `master`/`main`, unless explicitly
intended otherwise.

## 3. Testing on RunPod

RunPod pulls container images from a registry — pushing your *source code*
to a git remote is separate from pushing the *built image* to a registry
RunPod can reach. `scripts/build.sh` and `config/runpod-config-*.json`
already assume GitHub Container Registry (ghcr.io) — this works
independent of where your source git repo lives.

### Push the image to ghcr.io

```bash
export GITHUB_TOKEN=ghp_...   # needs write:packages scope
./scripts/build.sh --username <your-gh-username> --push
```

### Point your RunPod config at your image

`config/runpod-config-pods.json` and `config/runpod-config-serverless.json`
currently hardcode `ghcr.io/aaronghent/comfyui-serverless:latest` — update
the `image` field to your own pushed image before deploying.

### Deploy a Pod for interactive testing

Pods give persistent WebUI access so you can click around and verify
directly (Serverless is API-only, harder to debug interactively):

```bash
export RUNPOD_API_KEY=...
./scripts/deploy.sh --mode pods --name ltx23-test \
    --image ghcr.io/<you>/comfyui-serverless:latest \
    --gpu "NVIDIA RTX A4000"
```

`deploy.sh` uses `runpodctl` if installed, otherwise falls back to a Python
script requiring `pip install runpod`. Check which path applies before
running.

### Terminate when done

**Pods bill continuously while they exist.** Stopping a pod does **not**
stop billing — you must terminate it via the RunPod console or
`runpodctl stop pod <POD_ID> --terminate`. `deploy.sh` prints this warning
too; it's worth repeating because it's real money, not just a script nag.

## Summary Checklist

- [ ] Confirm local GPU compute capability, override `TORCH_CUDA_ARCH_LIST`
- [ ] Build locally (`docker compose build`), expect a long first build
- [ ] Start and manually verify via the web UI, not just a health check
- [ ] Run `install_ltx23.sh` with the profile matching your VRAM tier
- [ ] Run `test_local.sh` for the automated handler check
- [ ] Confirm actual git remote before pushing source (`git remote -v`)
- [ ] Push image to ghcr.io separately from pushing source code
- [ ] Update `config/runpod-config-*.json` image field before deploying
- [ ] Deploy a Pod (not Serverless) for interactive RunPod verification
- [ ] Terminate the pod when finished — stopping is not enough
