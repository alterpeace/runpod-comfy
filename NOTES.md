cd ~/source/runpod-comfy
set -a && source .env && set +a

uv run python scripts/invoke/alt_retake.py --video rhizome.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-52_00007.mp4 --random-seeds


uv run python scripts/storage/sync_outputs.py ~/comfy/output/sofaking

uv run python scripts/storage/list_s3.py --prefix output/


uv run python scripts/storage/purge_outputs.py --prefix output/


uv run python scripts/storage/upload_to_volume.py <folder> --subfolder <name> --sync-timeout 600


# Fire-and-forget
uv run python scripts/invoke/alt_retake.py \
    --batch-dir <folder> \
    --variation obsidian \
    --fire-and-forget \
    --jobs-file swa_aliens_obsidian.json

# Check status later (next day, from any machine)
uv run python scripts/invoke/alt_retake.py \
    --check-jobs \
    --jobs-file swa_aliens_obsidian.json

# Synchronous mode (default — submit and wait, for testing)
uv run python scripts/invoke/alt_retake.py \
    --video rhizome.mp4 \
    --variation obsidian

# FnF
uv run python scripts/invoke/alt_retake.py \
    --batch-dir <folder> \
    --variation obsidian \
    --fire-and-forget \
    --jobs-file al7_obsidian.json

# Close laptop, go to sleep

# Next morning:
uv run python scripts/invoke/alt_retake.py --check-jobs --jobs-file al7_obsidian.json