#!/usr/bin/env python3
"""Download LTX-2.3 models/LoRAs listed in config/ltx-2.3-models.json.

Usage:
    python scripts/models/download_ltx23_models.py --profile low_vram_8gb
    python scripts/models/download_ltx23_models.py --ids checkpoint_fp8 distilled_lora
    python scripts/models/download_ltx23_models.py --profile full --dry-run
    python scripts/models/download_ltx23_models.py --list

Gated repos (see manifest "gated": true) require:
  1. Visiting the repo page on huggingface.co and clicking "Agree and Access" once.
  2. Setting HF_TOKEN (or HUGGING_FACE_HUB_TOKEN) in your environment / .env.

Models download into <output-dir>/<dest>/<filename>, matching ComfyUI's
models/ layout (checkpoints/, loras/, unet/, vae/, text_encoders/,
latent_upscale_models/) so this can point straight at models/.
"""
import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / "config" / "ltx-2.3-models.json"


def load_manifest(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_ids(manifest: dict, profile: str | None, ids: list[str] | None) -> list[dict]:
    models_by_id = {m["id"]: m for m in manifest["models"]}

    if ids:
        wanted = ids
    elif profile:
        profiles = manifest.get("profiles", {})
        if profile not in profiles:
            available = ", ".join(sorted(profiles))
            raise SystemExit(f"Unknown profile '{profile}'. Available: {available}")
        wanted = profiles[profile]
        if wanted == ["all"]:
            wanted = list(models_by_id.keys())
    else:
        raise SystemExit("Specify either --profile or --ids")

    resolved = []
    missing = []
    for model_id in wanted:
        if model_id not in models_by_id:
            missing.append(model_id)
        else:
            resolved.append(models_by_id[model_id])
    if missing:
        raise SystemExit(f"Unknown model id(s): {', '.join(missing)}")
    return resolved


def download_one(model: dict, output_dir: Path, token: str | None, dry_run: bool, force: bool) -> bool:
    dest_dir = output_dir / model["dest"]
    filename_only = os.path.basename(model["file"])
    dest_path = dest_dir / filename_only

    if dest_path.exists() and not force:
        print(f"  [skip] {model['id']}: already exists at {dest_path}")
        return True

    if model.get("gated") and not token:
        print(
            f"  [FAIL] {model['id']}: repo '{model['repo']}' is gated and no HF_TOKEN "
            f"is set. Visit https://huggingface.co/{model['repo']} , click 'Agree and "
            f"Access', then set HF_TOKEN and retry."
        )
        return False

    if dry_run:
        print(f"  [dry-run] {model['id']}: {model['repo']}/{model['file']} -> {dest_path}")
        return True

    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError
    except ImportError:
        print("  [FAIL] huggingface_hub not installed. Run: uv pip install 'huggingface_hub[cli,hf_transfer]'")
        return False

    print(f"  [get] {model['id']}: {model['repo']}/{model['file']}")
    try:
        cached_path = hf_hub_download(
            repo_id=model["repo"],
            filename=model["file"],
            token=token,
        )
    except GatedRepoError:
        print(
            f"  [FAIL] {model['id']}: access denied for gated repo '{model['repo']}'. "
            f"Click 'Agree and Access' on the repo page with the account matching HF_TOKEN."
        )
        return False
    except RepositoryNotFoundError:
        print(f"  [FAIL] {model['id']}: repo '{model['repo']}' not found (check the manifest).")
        return False
    except Exception as exc:  # noqa: BLE001 - surface any other download error clearly
        print(f"  [FAIL] {model['id']}: {exc}")
        return False

    # Symlink into the ComfyUI models tree so files stay dedup'd in the HF cache.
    try:
        if dest_path.exists() or dest_path.is_symlink():
            dest_path.unlink()
        dest_path.symlink_to(os.path.abspath(cached_path))
        print(f"  [ok] {model['id']}: symlinked -> {dest_path}")
    except OSError:
        import shutil

        shutil.copy(cached_path, dest_path)
        print(f"  [ok] {model['id']}: copied -> {dest_path}")

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to model manifest JSON")
    parser.add_argument("--profile", help="Named profile from the manifest (e.g. low_vram_8gb, full)")
    parser.add_argument("--ids", nargs="+", help="Explicit model ids to download instead of a profile")
    parser.add_argument("--output-dir", type=Path, default=Path("models"), help="ComfyUI models/ directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without downloading")
    parser.add_argument("--force", action="store_true", help="Re-download even if the destination file exists")
    parser.add_argument("--list", action="store_true", help="List all model ids and profiles, then exit")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)

    if args.list:
        print("Profiles:")
        for name, ids in manifest.get("profiles", {}).items():
            print(f"  {name}: {', '.join(ids)}")
        print("\nModels:")
        for m in manifest["models"]:
            gated = " [gated]" if m.get("gated") else ""
            print(f"  {m['id']}{gated}: {m['desc']}")
        return 0

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    models = resolve_ids(manifest, args.profile, args.ids)

    print(f"Resolved {len(models)} model(s) -> {args.output_dir}")
    ok = True
    for model in models:
        if not download_one(model, args.output_dir, token, args.dry_run, args.force):
            ok = False

    if not ok:
        print("\nOne or more downloads failed. See [FAIL] lines above.")
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
