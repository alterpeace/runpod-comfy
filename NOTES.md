cd ~/source/runpod-comfy
set -a && source .env && set +a

uv run python scripts/invoke/alt_retake.py --video rhizome.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-52_00007.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-53_00004.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-54_00002.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-54_00004.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-54_00005.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-55_00002.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-55_00003.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-55_00004.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-58_00002.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-59_00001.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-59_00002.mp4 --random-seeds
uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-59_00003.mp4 --random-seeds

uv run python scripts/storage/sync_outputs.py ~/comfy/output/sofaking
uv run python scripts/storage/list_s3.py --prefix output/


uv run python scripts/storage/purge_outputs.py --prefix output/


uv run python scripts/storage/upload_to_volume.py <folder> --subfolder <name> --sync-timeout 600