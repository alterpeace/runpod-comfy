"""
AllMediaLoader - Robust media loader for images, videos, and GIFs.

Improved version with better .mov and video support using FFmpeg probe
and more reliable frame extraction.
"""

import os
import sys
import glob
import json
import random
import logging
import subprocess
import shutil
import tempfile
import time
import zipfile
import tarfile
from typing import Union, List, Tuple, Optional
from fractions import Fraction

import torch
import numpy as np
from PIL import Image, ImageOps, ImageSequence

import folder_paths

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Find ffmpeg and ffprobe
ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
ffprobe_path = shutil.which("ffprobe") or "ffprobe"


def pil_to_tensor(image: Image.Image) -> torch.Tensor:
    """Convert PIL image to PyTorch tensor in ComfyUI format (B,H,W,C)."""
    if image.mode != 'RGB':
        image = image.convert('RGB')
    np_image = np.array(image).astype(np.float32) / 255.0
    tensor = torch.from_numpy(np_image).unsqueeze(0)
    return tensor


def pil_to_tensor_rgba(image: Image.Image) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Convert PIL image to RGB tensor + alpha mask tensor.
    
    Returns:
        Tuple of (rgb_tensor [B,H,W,3], alpha_tensor [B,H,W])
    """
    # Check if image has alpha
    has_alpha = image.mode in ('RGBA', 'LA', 'PA') or (
        image.mode == 'P' and 'transparency' in image.info
    )
    
    if has_alpha:
        # Convert to RGBA to ensure we have alpha channel
        rgba = image.convert('RGBA')
        np_rgba = np.array(rgba).astype(np.float32) / 255.0
        
        # Split RGB and Alpha
        rgb = np_rgba[:, :, :3]
        alpha = np_rgba[:, :, 3]
        
        rgb_tensor = torch.from_numpy(rgb).unsqueeze(0)
        alpha_tensor = torch.from_numpy(alpha).unsqueeze(0)
    else:
        # No alpha - convert to RGB and create opaque mask
        rgb = image.convert('RGB')
        np_rgb = np.array(rgb).astype(np.float32) / 255.0
        
        rgb_tensor = torch.from_numpy(np_rgb).unsqueeze(0)
        # Create fully opaque alpha mask (all 1.0)
        alpha_tensor = torch.ones((1, np_rgb.shape[0], np_rgb.shape[1]), dtype=torch.float32)
    
    return rgb_tensor, alpha_tensor


def resize_image_max_size(image: Image.Image, max_res: int) -> Image.Image:
    """Resize image if its width or height exceeds max_res, preserving aspect ratio."""
    if max_res <= 0:
        return image
    w, h = image.size
    if w <= max_res and h <= max_res:
        return image
    if w > h:
        new_w = max_res
        new_h = int(h * (max_res / w))
    else:
        new_h = max_res
        new_w = int(w * (max_res / h))
    return image.resize((new_w, new_h), Image.Resampling.LANCZOS)


def get_video_info(video_path: str) -> dict:
    """
    Use ffprobe to get accurate video metadata.
    Returns dict with: fps, duration, frame_count, width, height, codec
    """
    try:
        cmd = [
            ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise ValueError(f"ffprobe failed: {result.stderr}")
        
        data = json.loads(result.stdout)
        
        # Find video stream
        video_stream = None
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break
        
        if not video_stream:
            raise ValueError("No video stream found")
        
        # Parse frame rate (can be "30/1" or "29.97" format)
        fps_str = video_stream.get('r_frame_rate', '30/1')
        if '/' in fps_str:
            num, den = fps_str.split('/')
            fps = float(num) / float(den) if float(den) != 0 else 30.0
        else:
            fps = float(fps_str)
        
        # Get frame count - try multiple methods
        frame_count = 0
        
        # Method 1: nb_frames (most reliable when available)
        if 'nb_frames' in video_stream:
            try:
                frame_count = int(video_stream['nb_frames'])
            except (ValueError, TypeError):
                pass
        
        # Method 2: Calculate from duration and fps
        if frame_count == 0:
            duration = 0.0
            if 'duration' in video_stream:
                duration = float(video_stream['duration'])
            elif 'duration' in data.get('format', {}):
                duration = float(data['format']['duration'])
            
            if duration > 0 and fps > 0:
                frame_count = int(duration * fps)
        
        # Method 3: Use ffprobe to count frames (slower but accurate)
        if frame_count == 0:
            frame_count = count_frames_ffprobe(video_path)
        
        return {
            'fps': fps,
            'frame_count': frame_count,
            'width': int(video_stream.get('width', 0)),
            'height': int(video_stream.get('height', 0)),
            'codec': video_stream.get('codec_name', 'unknown'),
            'duration': float(data.get('format', {}).get('duration', 0))
        }
        
    except Exception as e:
        logger.warning(f"ffprobe failed for {video_path}: {e}, falling back to OpenCV")
        return None


def count_frames_ffprobe(video_path: str) -> int:
    """Count frames using ffprobe -count_frames (slower but accurate)."""
    try:
        cmd = [
            ffprobe_path,
            '-v', 'error',
            '-select_streams', 'v:0',
            '-count_frames',
            '-show_entries', 'stream=nb_read_frames',
            '-print_format', 'json',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            streams = data.get('streams', [])
            if streams and 'nb_read_frames' in streams[0]:
                return int(streams[0]['nb_read_frames'])
    except Exception as e:
        logger.warning(f"Frame counting failed: {e}")
    return 0


def extract_frames_ffmpeg(
    video_path: str,
    force_rate: float = 0.0,
    image_load_cap: int = 0,
    max_res: int = 0,
    extract_alpha: bool = False
) -> Tuple[List[np.ndarray], Optional[List[np.ndarray]], float, int, int]:
    """
    Extract frames from video using FFmpeg for reliable decoding.
    
    Args:
        video_path: Path to video file
        force_rate: Target FPS (0 = original)
        image_load_cap: Max frames to extract (0 = all)
        max_res: Max resolution (0 = original)
        extract_alpha: Whether to extract alpha channel if present
    
    Returns:
        Tuple of (rgb_frames_list, alpha_frames_list or None, fps, width, height)
    """
    # Get video info
    info = get_video_info(video_path)
    if info is None:
        # Fallback to OpenCV method
        frames, fps, w, h = extract_frames_opencv(video_path, force_rate, image_load_cap, max_res)
        return frames, None, fps, w, h
    
    original_fps = info['fps']
    total_frames = info['frame_count']
    
    logger.info(f"Video info: {total_frames} frames at {original_fps:.2f} fps, codec: {info['codec']}")
    
    # Check if video has alpha (ProRes 4444, VP9, etc.)
    has_alpha = info['codec'] in ('prores', 'vp9', 'vp8', 'png', 'qtrle', 'ffv1')
    
    # Determine output fps
    output_fps = force_rate if force_rate > 0 else original_fps
    
    # Build ffmpeg command
    cmd = [ffmpeg_path, '-i', video_path]
    
    # Apply frame rate filter if needed
    vf_filters = []
    if force_rate > 0 and force_rate != original_fps:
        vf_filters.append(f'fps={force_rate}')
    
    # Apply resize filter if needed
    if max_res > 0:
        vf_filters.append(f'scale=w=min({max_res}\\,iw):h=min({max_res}\\,ih):force_original_aspect_ratio=decrease')
    
    if vf_filters:
        cmd.extend(['-vf', ','.join(vf_filters)])
    
    # Limit frames if requested
    if image_load_cap > 0:
        cmd.extend(['-frames:v', str(image_load_cap)])
    
    # Output format - RGBA if alpha requested and available, else RGB
    if extract_alpha and has_alpha:
        pix_fmt = 'rgba'
        channels = 4
    else:
        pix_fmt = 'rgb24'
        channels = 3
    
    cmd.extend([
        '-f', 'rawvideo',
        '-pix_fmt', pix_fmt,
        '-'
    ])
    
    logger.info(f"Running ffmpeg: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**8
        )
        
        stdout, stderr = process.communicate(timeout=300)
        
        if process.returncode != 0:
            logger.error(f"FFmpeg error: {stderr.decode()}")
            raise ValueError(f"FFmpeg failed: {stderr.decode()[:500]}")
        
        if len(stdout) == 0:
            raise ValueError("FFmpeg produced no output")
        
        # Calculate output dimensions
        # DON'T force even dimensions - use actual output from ffmpeg
        if max_res > 0:
            orig_w, orig_h = info['width'], info['height']
            if orig_w > orig_h:
                if orig_w > max_res:
                    out_w = max_res
                    out_h = int(orig_h * max_res / orig_w)
                else:
                    out_w, out_h = orig_w, orig_h
            else:
                if orig_h > max_res:
                    out_h = max_res
                    out_w = int(orig_w * max_res / orig_h)
                else:
                    out_w, out_h = orig_w, orig_h
        else:
            out_w, out_h = info['width'], info['height']
        
        # Calculate expected frame size
        frame_size = out_w * out_h * channels
        
        # Check if data size matches expected
        if len(stdout) % frame_size != 0:
            # Dimensions might be off - try to detect actual dimensions
            # FFmpeg might have adjusted dimensions slightly
            logger.warning(f"Data size {len(stdout)} doesn't match expected {frame_size} (w={out_w}, h={out_h})")
            
            # Try common adjustments (even dimensions)
            for adj_w, adj_h in [(out_w - (out_w % 2), out_h - (out_h % 2)),
                                  (out_w + (2 - out_w % 2) % 2, out_h + (2 - out_h % 2) % 2)]:
                test_size = adj_w * adj_h * channels
                if len(stdout) % test_size == 0:
                    out_w, out_h = adj_w, adj_h
                    frame_size = test_size
                    logger.info(f"Adjusted dimensions to {out_w}x{out_h}")
                    break
        
        num_frames = len(stdout) // frame_size
        
        if num_frames == 0:
            raise ValueError(f"Could not extract frames. Data size: {len(stdout)}, expected frame size: {frame_size}")
        
        logger.info(f"Extracted {num_frames} frames at {out_w}x{out_h} ({channels} channels)")
        
        # Reshape into frames
        rgb_frames = []
        alpha_frames = [] if (extract_alpha and has_alpha) else None
        
        for i in range(num_frames):
            frame_data = stdout[i * frame_size:(i + 1) * frame_size]
            frame = np.frombuffer(frame_data, dtype=np.uint8).reshape((out_h, out_w, channels))
            frame = frame.astype(np.float32) / 255.0
            
            if channels == 4:
                rgb_frames.append(frame[:, :, :3])
                alpha_frames.append(frame[:, :, 3])
            else:
                rgb_frames.append(frame)
        
        return rgb_frames, alpha_frames, output_fps, out_w, out_h
        
    except subprocess.TimeoutExpired:
        process.kill()
        raise ValueError("FFmpeg timed out")
    except Exception as e:
        logger.error(f"FFmpeg extraction failed: {e}")
        frames, fps, w, h = extract_frames_opencv(video_path, force_rate, image_load_cap, max_res)
        return frames, None, fps, w, h


def extract_frames_opencv(
    video_path: str,
    force_rate: float = 0.0,
    image_load_cap: int = 0,
    max_res: int = 0
) -> Tuple[List[np.ndarray], float, int, int]:
    """
    Fallback frame extraction using OpenCV.
    More compatible but less reliable for some codecs.
    """
    import cv2
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")
    
    original_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Handle invalid frame count (common with .mov files)
    if total_frames <= 0:
        logger.warning(f"Invalid frame count from OpenCV, counting manually...")
        total_frames = 0
        while True:
            ret, _ = cap.read()
            if not ret:
                break
            total_frames += 1
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        logger.info(f"Counted {total_frames} frames manually")
    
    frame_interval = 1
    if force_rate > 0 and original_fps > 0:
        frame_interval = max(1, round(original_fps / force_rate))
    
    output_fps = force_rate if force_rate > 0 else original_fps
    
    # Calculate frames to extract
    frames_to_extract = (total_frames + frame_interval - 1) // frame_interval
    if image_load_cap > 0:
        frames_to_extract = min(image_load_cap, frames_to_extract)
    
    frames = []
    frame_idx = 0
    extracted = 0
    out_w, out_h = 0, 0
    
    while extracted < frames_to_extract:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        
        if not ret:
            # Try sequential read as fallback
            if frame_idx == 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                break
        
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame)
        
        if max_res > 0:
            pil_img = resize_image_max_size(pil_img, max_res)
        
        out_w, out_h = pil_img.size
        np_frame = np.array(pil_img).astype(np.float32) / 255.0
        frames.append(np_frame)
        
        extracted += 1
        frame_idx += frame_interval
    
    cap.release()
    
    if not frames:
        raise ValueError(f"No frames extracted from video: {video_path}")
    
    return frames, output_fps, out_w, out_h


def extract_frames_sequential(
    video_path: str,
    force_rate: float = 0.0,
    image_load_cap: int = 0,
    max_res: int = 0
) -> Tuple[List[np.ndarray], float, int, int]:
    """
    Sequential frame extraction - most reliable for problematic videos.
    Reads every frame sequentially without seeking.
    """
    import cv2
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")
    
    original_fps = cap.get(cv2.CAP_PROP_FPS)
    if original_fps <= 0:
        original_fps = 30.0  # Default fallback
    
    frame_interval = 1
    if force_rate > 0 and original_fps > 0:
        frame_interval = max(1, round(original_fps / force_rate))
    
    output_fps = force_rate if force_rate > 0 else original_fps
    
    frames = []
    frame_idx = 0
    out_w, out_h = 0, 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Only keep frames at the interval
        if frame_idx % frame_interval == 0:
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Resize if needed
            if max_res > 0:
                h, w = frame_rgb.shape[:2]
                if w > max_res or h > max_res:
                    if w > h:
                        new_w = max_res
                        new_h = int(h * max_res / w)
                    else:
                        new_h = max_res
                        new_w = int(w * max_res / h)
                    frame_rgb = cv2.resize(frame_rgb, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
            
            out_h, out_w = frame_rgb.shape[:2]
            
            # Convert to float32 normalized [0, 1]
            np_frame = frame_rgb.astype(np.float32) / 255.0
            frames.append(np_frame)
            
            if image_load_cap > 0 and len(frames) >= image_load_cap:
                break
        
        frame_idx += 1
    
    cap.release()
    
    if not frames:
        raise ValueError(f"No frames extracted from video: {video_path}")
    
    logger.info(f"Sequential extraction: {len(frames)} frames at {out_w}x{out_h} from {frame_idx} total")
    return frames, output_fps, out_w, out_h


def process_gif(
    gif_path: str,
    force_rate: float = 0.0,
    image_load_cap: int = 0,
    max_res: int = 0
) -> Tuple[List[np.ndarray], float, int, int]:
    """Process an animated GIF, returning frames as numpy arrays."""
    gif = Image.open(gif_path)
    
    if not getattr(gif, "is_animated", False):
        # Not animated, treat as single image
        if max_res > 0:
            gif = resize_image_max_size(gif, max_res)
        img_rgb = gif.convert("RGB")
        w, h = img_rgb.size
        np_frame = np.array(img_rgb).astype(np.float32) / 255.0
        return [np_frame], 0.0, w, h
    
    try:
        original_fps = 1000 / (gif.info.get('duration', 100))
    except (ZeroDivisionError, TypeError):
        original_fps = 10.0
    
    frame_interval = 1
    if force_rate > 0 and original_fps > 0:
        frame_interval = max(1, round(original_fps / force_rate))
    
    output_fps = force_rate if force_rate > 0 else original_fps
    
    frames = []
    out_w, out_h = 0, 0
    
    for i, frame_pil in enumerate(ImageSequence.Iterator(gif)):
        if i % frame_interval != 0:
            continue
        
        frame_pil = frame_pil.convert("RGB")
        if max_res > 0:
            frame_pil = resize_image_max_size(frame_pil, max_res)
        
        out_w, out_h = frame_pil.size
        np_frame = np.array(frame_pil).astype(np.float32) / 255.0
        frames.append(np_frame)
        
        if image_load_cap > 0 and len(frames) >= image_load_cap:
            break
    
    if not frames:
        raise ValueError(f"No frames extracted from GIF: {gif_path}")
    
    return frames, output_fps, out_w, out_h


def process_gif_rgba(
    gif_path: str,
    force_rate: float = 0.0,
    image_load_cap: int = 0,
    max_res: int = 0
) -> Tuple[List[np.ndarray], List[np.ndarray], float, int, int]:
    """
    Process an animated GIF with alpha channel support.
    
    Returns:
        Tuple of (rgb_frames, alpha_frames, fps, width, height)
    """
    gif = Image.open(gif_path)
    
    # Check if GIF has transparency
    has_transparency = 'transparency' in gif.info or gif.mode in ('RGBA', 'LA', 'PA')
    
    if not getattr(gif, "is_animated", False):
        # Not animated, treat as single image
        if max_res > 0:
            gif = resize_image_max_size(gif, max_res)
        
        if has_transparency:
            img_rgba = gif.convert("RGBA")
            np_rgba = np.array(img_rgba).astype(np.float32) / 255.0
            rgb_frame = np_rgba[:, :, :3]
            alpha_frame = np_rgba[:, :, 3]
        else:
            img_rgb = gif.convert("RGB")
            np_rgb = np.array(img_rgb).astype(np.float32) / 255.0
            rgb_frame = np_rgb
            alpha_frame = np.ones((np_rgb.shape[0], np_rgb.shape[1]), dtype=np.float32)
        
        w, h = gif.size
        return [rgb_frame], [alpha_frame], 0.0, w, h
    
    try:
        original_fps = 1000 / (gif.info.get('duration', 100))
    except (ZeroDivisionError, TypeError):
        original_fps = 10.0
    
    frame_interval = 1
    if force_rate > 0 and original_fps > 0:
        frame_interval = max(1, round(original_fps / force_rate))
    
    output_fps = force_rate if force_rate > 0 else original_fps
    
    rgb_frames = []
    alpha_frames = []
    out_w, out_h = 0, 0
    
    for i, frame_pil in enumerate(ImageSequence.Iterator(gif)):
        if i % frame_interval != 0:
            continue
        
        if max_res > 0:
            frame_pil = resize_image_max_size(frame_pil, max_res)
        
        out_w, out_h = frame_pil.size
        
        # Handle transparency
        if has_transparency or frame_pil.mode in ('RGBA', 'LA', 'PA', 'P'):
            frame_rgba = frame_pil.convert("RGBA")
            np_rgba = np.array(frame_rgba).astype(np.float32) / 255.0
            rgb_frames.append(np_rgba[:, :, :3])
            alpha_frames.append(np_rgba[:, :, 3])
        else:
            frame_rgb = frame_pil.convert("RGB")
            np_rgb = np.array(frame_rgb).astype(np.float32) / 255.0
            rgb_frames.append(np_rgb)
            alpha_frames.append(np.ones((out_h, out_w), dtype=np.float32))
        
        if image_load_cap > 0 and len(rgb_frames) >= image_load_cap:
            break
    
    if not rgb_frames:
        raise ValueError(f"No frames extracted from GIF: {gif_path}")
    
    return rgb_frames, alpha_frames, output_fps, out_w, out_h


def load_path(path: str) -> Union[str, List[str]]:
    """Resolve a path that can be absolute, relative, annotated, or wildcard."""
    path = path.strip('"').strip("'").replace("\\", "/")
    
    # Handle annotated paths
    if "[" in path:
        name, base_dir = folder_paths.annotated_filepath(path)
        if base_dir is not None:
            full_path = os.path.join(base_dir, name)
            if '*' in name or '?' in name:
                matches = glob.glob(full_path, recursive=True)
                if matches:
                    return [os.path.abspath(p) for p in matches]
            elif os.path.exists(full_path):
                return os.path.abspath(full_path)
    
    # Try as absolute path with wildcards
    if '*' in path or '?' in path:
        matches = glob.glob(path, recursive=True)
        if matches:
            return [os.path.abspath(p) for p in matches]
    elif os.path.exists(path):
        return os.path.abspath(path)
    
    # Try in input directory
    input_path = os.path.join(folder_paths.get_input_directory(), path)
    if '*' in path or '?' in path:
        matches = glob.glob(input_path, recursive=True)
        if matches:
            return [os.path.abspath(p) for p in matches]
    elif os.path.exists(input_path):
        return os.path.abspath(input_path)
    
    raise FileNotFoundError(f"Could not find file or directory at {path} or {input_path}")


def load_single_image(image_path: str, max_res: int = 0) -> torch.Tensor:
    """Load a single image and convert to tensor (RGB only)."""
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)
    if max_res > 0:
        img = resize_image_max_size(img, max_res)
    return pil_to_tensor(img)


def load_single_image_rgba(image_path: str, max_res: int = 0) -> Tuple[torch.Tensor, torch.Tensor]:
    """Load a single image and convert to RGB tensor + alpha mask."""
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)
    if max_res > 0:
        img = resize_image_max_size(img, max_res)
    return pil_to_tensor_rgba(img)


def concat_image_tensors(tensors: List[torch.Tensor]) -> torch.Tensor:
    """Concatenate multiple image tensors along the batch dimension."""
    if not tensors:
        raise ValueError("No tensors to concatenate")
    if len(tensors) == 1:
        return tensors[0]
    return torch.cat(tensors, dim=0)


class AllMediaLoader:
    """
    Robust media loader for images, videos, GIFs, and archives.
    
    Improved version with better .mov and video support:
    - Uses FFmpeg probe for accurate frame counts
    - Sequential reading fallback for problematic codecs
    - Better handling of ProRes, HEVC, and other QuickTime codecs
    """
    
    VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.wmv', '.flv')
    IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif')
    ARCHIVE_EXTENSIONS = ('.zip', '.tar', '.tar.gz', '.tar.bz2', '.7z')
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "path": ("STRING", {
                    "image_upload": True,
                    "tooltip": "Path to media file(s). Can be an image, directory, video, GIF, or archive."
                }),
                "image_load_cap": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": sys.maxsize,
                    "step": 1,
                    "tooltip": "Maximum frames to load. 0 = load all."
                }),
                "force_rate": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "step": 0.1,
                    "tooltip": "Force extracting frames at this FPS. 0 = use original rate."
                }),
                "max_res": ("INT", {
                    "default": 2048,
                    "min": 0,
                    "max": sys.maxsize,
                    "step": 1,
                    "tooltip": "Maximum resolution (width or height). 0 = no resize."
                }),
                "sort": (["None", "alphabetical", "date_created", "date_modified", "random"], {
                    "default": "None",
                    "tooltip": "Sorting method for multiple images."
                }),
                "extraction_mode": (["auto", "ffmpeg", "opencv", "sequential"], {
                    "default": "auto",
                    "tooltip": "Video extraction method. 'auto' tries ffmpeg first, 'sequential' is most reliable for .mov files."
                }),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "MASK", "INT", "INT", "INT", "STRING", "STRING", "FLOAT")
    RETURN_NAMES = ("image", "alpha", "WIDTH", "HEIGHT", "COUNT", "FILE_NAME", "FILE_PATH", "FPS")
    FUNCTION = "load_media"
    CATEGORY = "Alt"
    
    @classmethod
    def IS_CHANGED(cls, path, image_load_cap=0, force_rate=0.0, max_res=0, sort="None", extraction_mode="auto"):
        """
        Force re-execution by checking file modification time.
        This prevents ComfyUI from returning cached results when the file changes.
        """
        import time
        try:
            resolved = load_path(path)
            if isinstance(resolved, list):
                # For multiple files, use combined mtime
                mtimes = [os.path.getmtime(p) for p in resolved if os.path.exists(p)]
                return f"{sum(mtimes)}_{len(resolved)}_{image_load_cap}_{force_rate}_{max_res}_{extraction_mode}"
            elif os.path.exists(resolved):
                mtime = os.path.getmtime(resolved)
                return f"{mtime}_{image_load_cap}_{force_rate}_{max_res}_{extraction_mode}"
        except:
            pass
        # Fallback: always re-execute
        return time.time_ns()
    
    DESCRIPTION = """
Robust Media Loader with improved video support.

Features:
- Loads images, directories, videos, GIFs, and archives
- Better .mov file support with multiple extraction methods
- FFmpeg-based extraction for accurate frame counts
- Sequential fallback for problematic codecs (ProRes, HEVC)
- Automatic resize with aspect ratio preservation
- Alpha channel extraction for PNG, WebP, GIF, ProRes 4444, VP9

Outputs:
- image: RGB frames [B, H, W, 3]
- alpha: Alpha mask [B, H, W] (1.0=opaque, 0.0=transparent)
  For files without alpha, mask is all 1.0

Extraction modes:
- auto: Try FFmpeg first, fall back to OpenCV
- ffmpeg: Use FFmpeg directly (best for most formats)
- opencv: Use OpenCV (faster but less reliable for .mov)
- sequential: Read frames sequentially (most reliable for .mov)
"""

    def load_media(
        self,
        path: str,
        image_load_cap: int = 0,
        force_rate: float = 0.0,
        max_res: int = 0,
        sort: str = "None",
        extraction_mode: str = "auto"
    ) -> Tuple:
        """Main function to load media from various sources."""
        try:
            resolved_path = load_path(path)
            
            # Handle list of paths from wildcard matching
            if isinstance(resolved_path, list):
                return self._process_image_list(resolved_path, image_load_cap, max_res, sort)
            
            path = resolved_path
            
            # Handle directories
            if os.path.isdir(path):
                return self._load_from_directory(path, image_load_cap, max_res, sort)
            
            # Handle videos
            if path.lower().endswith(self.VIDEO_EXTENSIONS):
                return self._load_video(path, force_rate, image_load_cap, max_res, extraction_mode)
            
            # Handle GIFs
            if path.lower().endswith('.gif'):
                return self._load_gif(path, force_rate, image_load_cap, max_res)
            
            # Handle archives
            if path.lower().endswith(self.ARCHIVE_EXTENSIONS):
                return self._load_from_archive(path, image_load_cap, max_res, sort)
            
            # Handle single image (with alpha support)
            return self._load_single_image(path, max_res)
            
        except Exception as e:
            logger.error(f"Error loading media: {e}")
            raise

    def _load_video(
        self,
        path: str,
        force_rate: float,
        image_load_cap: int,
        max_res: int,
        extraction_mode: str
    ) -> Tuple:
        """Load video file with robust frame extraction."""
        logger.info(f"Loading video: {path} (mode: {extraction_mode})")
        
        alpha_frames = None
        
        # Choose extraction method
        if extraction_mode == "ffmpeg":
            frames, alpha_frames, fps, w, h = extract_frames_ffmpeg(
                path, force_rate, image_load_cap, max_res, extract_alpha=True
            )
        elif extraction_mode == "opencv":
            frames, fps, w, h = extract_frames_opencv(path, force_rate, image_load_cap, max_res)
        elif extraction_mode == "sequential":
            frames, fps, w, h = extract_frames_sequential(path, force_rate, image_load_cap, max_res)
        else:  # auto
            # For .mov files, use FFmpeg as OpenCV often has codec issues
            if path.lower().endswith('.mov'):
                logger.info("Using FFmpeg extraction for .mov file (better codec support)")
                try:
                    frames, alpha_frames, fps, w, h = extract_frames_ffmpeg(
                        path, force_rate, image_load_cap, max_res, extract_alpha=True
                    )
                except Exception as e:
                    logger.warning(f"FFmpeg extraction failed: {e}, trying sequential")
                    frames, fps, w, h = extract_frames_sequential(path, force_rate, image_load_cap, max_res)
            else:
                try:
                    frames, fps, w, h = extract_frames_sequential(path, force_rate, image_load_cap, max_res)
                except Exception as e:
                    logger.warning(f"Sequential extraction failed: {e}, trying FFmpeg")
                    frames, alpha_frames, fps, w, h = extract_frames_ffmpeg(
                        path, force_rate, image_load_cap, max_res, extract_alpha=True
                    )
        
        if not frames:
            raise ValueError(f"No frames extracted from video: {path}")
        
        # Stack frames into tensor
        images_np = np.stack(frames, axis=0)
        images = torch.from_numpy(images_np)
        
        # Debug: log tensor shape
        logger.info(f"Tensor shape: {images.shape}, dtype: {images.dtype}")
        
        # Verify shape is [B, H, W, C]
        if len(images.shape) != 4:
            logger.error(f"Invalid tensor shape: {images.shape}, expected 4 dimensions [B, H, W, C]")
        elif images.shape[0] != len(frames):
            logger.error(f"Batch dimension mismatch: tensor has {images.shape[0]}, expected {len(frames)}")
        
        # Handle alpha
        if alpha_frames is not None:
            alpha_np = np.stack(alpha_frames, axis=0)
            alpha = torch.from_numpy(alpha_np)
        else:
            # Create opaque mask
            alpha = torch.ones((len(frames), h, w), dtype=torch.float32)
        
        frame_count = len(frames)
        file_name = os.path.basename(path).rsplit('.', 1)[0]
        
        logger.info(f"Loaded {frame_count} frames at {w}x{h}, {fps:.2f} fps")
        
        return (images, alpha, w, h, frame_count, file_name, path, fps)

    def _load_gif(
        self,
        path: str,
        force_rate: float,
        image_load_cap: int,
        max_res: int
    ) -> Tuple:
        """Load GIF file with alpha support."""
        frames, alpha_frames, fps, w, h = process_gif_rgba(path, force_rate, image_load_cap, max_res)
        
        images_np = np.stack(frames, axis=0)
        images = torch.from_numpy(images_np)
        
        alpha_np = np.stack(alpha_frames, axis=0)
        alpha = torch.from_numpy(alpha_np)
        
        frame_count = len(frames)
        file_name = os.path.basename(path).rsplit('.', 1)[0]
        
        return (images, alpha, w, h, frame_count, file_name, path, fps)

    def _load_single_image(self, path: str, max_res: int) -> Tuple:
        """Load a single image file with alpha support."""
        rgb, alpha = load_single_image_rgba(path, max_res)
        _, h, w, c = rgb.shape
        file_name = os.path.basename(path).rsplit('.', 1)[0]
        return (rgb, alpha, w, h, 1, file_name, path, 0.0)

    def _process_image_list(
        self,
        image_paths: List[str],
        image_load_cap: int,
        max_res: int,
        sort: str
    ) -> Tuple:
        """Process a list of image paths with alpha support."""
        if not image_paths:
            raise ValueError("No image paths provided")
        
        # Apply sorting
        if sort == "alphabetical":
            image_paths.sort(key=lambda x: x.lower())
        elif sort == "date_created":
            image_paths.sort(key=lambda x: os.path.getctime(x))
        elif sort == "date_modified":
            image_paths.sort(key=lambda x: os.path.getmtime(x))
        elif sort == "random":
            random.seed(0)
            random.shuffle(image_paths)
        
        # Apply cap
        if image_load_cap > 0:
            image_paths = image_paths[:image_load_cap]
        
        # Load images with alpha
        rgb_frames = []
        alpha_frames = []
        for img_path in image_paths:
            try:
                rgb, alpha = load_single_image_rgba(img_path, max_res)
                rgb_frames.append(rgb)
                alpha_frames.append(alpha)
            except Exception as e:
                logger.warning(f"Failed to load image {img_path}: {e}")
        
        if not rgb_frames:
            raise ValueError("No valid images found")
        
        images = torch.cat(rgb_frames, dim=0)
        alphas = torch.cat(alpha_frames, dim=0)
        _, h, w, c = images.shape
        
        parent_dir = os.path.dirname(image_paths[0])
        file_names = [os.path.basename(p).rsplit('.', 1)[0] for p in image_paths[:3]]
        file_name = "|".join(file_names) + ("..." if len(image_paths) > 3 else "")
        
        return (images, alphas, w, h, len(rgb_frames), file_name, parent_dir, 0.0)

    def _load_from_directory(
        self,
        directory: str,
        image_load_cap: int,
        max_res: int,
        sort: str
    ) -> Tuple:
        """Load images from a directory."""
        image_files = []
        for ext in self.IMAGE_EXTENSIONS:
            image_files.extend(glob.glob(os.path.join(directory, f"*{ext}")))
            image_files.extend(glob.glob(os.path.join(directory, f"*{ext.upper()}")))
        
        # Also check for GIFs
        image_files.extend(glob.glob(os.path.join(directory, "*.gif")))
        image_files.extend(glob.glob(os.path.join(directory, "*.GIF")))
        
        if not image_files:
            raise ValueError(f"No image files found in directory {directory}")
        
        return self._process_image_list(image_files, image_load_cap, max_res, sort)

    def _load_from_archive(
        self,
        archive_path: str,
        image_load_cap: int,
        max_res: int,
        sort: str
    ) -> Tuple:
        """Extract and load images from an archive."""
        import py7zr
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract archive
            if archive_path.lower().endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as z:
                    z.extractall(temp_dir)
            elif archive_path.lower().endswith('.7z'):
                with py7zr.SevenZipFile(archive_path, mode='r') as z:
                    z.extractall(path=temp_dir)
            else:  # tar variants
                with tarfile.open(archive_path, 'r') as t:
                    t.extractall(temp_dir)
            
            # Check for single directory
            contents = os.listdir(temp_dir)
            if len(contents) == 1 and os.path.isdir(os.path.join(temp_dir, contents[0])):
                temp_dir = os.path.join(temp_dir, contents[0])
            
            result = self._load_from_directory(temp_dir, image_load_cap, max_res, sort)
            
            # Update path to original archive
            images, alpha, w, h, count, _, _, fps = result
            file_name = os.path.basename(archive_path).rsplit('.', 1)[0]
            return (images, alpha, w, h, count, file_name, archive_path, fps)
