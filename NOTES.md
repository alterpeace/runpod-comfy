cd /home/chiral/source/runpod-comfy
set -a && source .env && set +a

uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-52_00007.mp4
uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-53_00004.mp4
uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-54_00002.mp4
uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-54_00004.mp4
uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-54_00005.mp4
uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-55_00002.mp4
uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-55_00003.mp4
uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-55_00004.mp4
uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-58_00002.mp4
uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-59_00001.mp4
uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-59_00002.mp4
uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-59_00003.mp4

uv run python scripts/sync_outputs.py /media/chiral/data/comfy/output/sofaking
uv run python scripts/list_s3.py --prefix output/
