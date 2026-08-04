"""
TimeStretchBatch - Resample image batches to a target frame count.

This node takes an image batch of any length and resamples it to exactly
the target number of frames, preserving the full loop/sequence.
"""

import torch
import hashlib
import time
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class TimeStretchBatch:
    """
    Resample an image batch to a specific target frame count.
    
    Useful for matching varying-length looping videos/GIFs to a fixed
    AnimateDiff frame count while preserving the complete loop.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "target_frames": ("INT", {
                    "default": 64,
                    "min": 1,
                    "max": 4096,
                    "step": 1,
                    "tooltip": "Target number of output frames"
                }),
                "interpolation": (["nearest", "linear", "blend"], {
                    "default": "linear",
                    "tooltip": "nearest: snap to closest frame, linear: interpolate between frames, blend: smooth blend"
                }),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "INT", "FLOAT")
    RETURN_NAMES = ("images", "frame_count", "stretch_factor")
    FUNCTION = "stretch"
    CATEGORY = "Alt"
    DESCRIPTION = """
Resample an image batch to exactly target_frames.

- If input has fewer frames → frames are interpolated (slow down)
- If input has more frames → frames are skipped/blended (speed up)

Perfect for matching varying-length looping videos to AnimateDiff's n_frames.

Interpolation modes:
- nearest: Snap to closest source frame (fast, can look choppy)
- linear: Blend between adjacent frames (smooth, recommended)
- blend: Weighted 3-frame blend for smoother transitions
"""

    @classmethod
    def IS_CHANGED(cls, images, target_frames, interpolation="linear"):
        """
        Force re-execution every time by returning current timestamp.
        """
        # Always return unique value to force re-execution
        return float("nan")

    def stretch(self, images: torch.Tensor, target_frames: int, interpolation: str = "linear") -> Tuple[torch.Tensor, int, float]:
        """
        Resample image batch to target frame count.
        
        Args:
            images: Input tensor [B, H, W, C] where B is frame count
            target_frames: Desired output frame count
            interpolation: Resampling method
            
        Returns:
            Tuple of (resampled images, frame count, stretch factor)
        """
        # Debug logging - what did we actually receive?
        logger.info(f"TimeStretchBatch received: type={type(images)}, shape={images.shape if hasattr(images, 'shape') else 'N/A'}")
        logger.info(f"TimeStretchBatch target_frames={target_frames}, interpolation={interpolation}")
        
        # Safety check for empty or invalid input
        if images is None or images.numel() == 0:
            raise ValueError("TimeStretchBatch received empty or None images tensor")
        
        source_frames = images.shape[0]
        logger.info(f"TimeStretchBatch source_frames={source_frames} (from shape[0])")
        
        if source_frames == 0:
            raise ValueError("TimeStretchBatch received 0 frames")
        
        # If already the right size, return a clone to avoid reference issues
        if source_frames == target_frames:
            return (images.clone(), target_frames, 1.0)
        
        stretch_factor = target_frames / source_frames
        
        if interpolation == "nearest":
            output = self._resample_nearest(images, target_frames)
        elif interpolation == "linear":
            output = self._resample_linear(images, target_frames)
        elif interpolation == "blend":
            output = self._resample_blend(images, target_frames)
        else:
            output = self._resample_linear(images, target_frames)
        
        # Ensure output is contiguous for downstream nodes
        return (output.contiguous(), target_frames, stretch_factor)
    
    def _resample_nearest(self, images: torch.Tensor, target_frames: int) -> torch.Tensor:
        """Nearest-neighbor resampling - snap to closest source frame."""
        source_frames = images.shape[0]
        device = images.device
        
        # Ensure input is contiguous
        if not images.is_contiguous():
            images = images.contiguous()
        
        # Calculate which source frame each target frame maps to
        indices = torch.linspace(0, source_frames - 1, target_frames, device=device)
        indices = torch.round(indices).long().clamp(0, source_frames - 1)
        
        return images[indices].clone().contiguous()
    
    def _resample_linear(self, images: torch.Tensor, target_frames: int) -> torch.Tensor:
        """Linear interpolation between adjacent frames."""
        source_frames = images.shape[0]
        device = images.device
        dtype = images.dtype
        
        # Ensure input is contiguous to avoid CUDA memory registration issues
        if not images.is_contiguous():
            images = images.contiguous()
        
        # Calculate fractional positions in source
        positions = torch.linspace(0, source_frames - 1, target_frames, device=device)
        
        output_frames = []
        for pos in positions:
            # Get the two adjacent frames
            idx_low = int(pos.floor().item())
            idx_high = min(idx_low + 1, source_frames - 1)
            
            # Calculate blend weight (keep on same device/dtype)
            weight = (pos - idx_low).to(dtype)
            
            # Linear interpolation - clone to ensure contiguous memory
            if idx_low == idx_high:
                frame = images[idx_low].clone()
            else:
                frame = (images[idx_low] * (1.0 - weight) + images[idx_high] * weight).clone()
            
            output_frames.append(frame)
        
        return torch.stack(output_frames, dim=0).contiguous()
    
    def _resample_blend(self, images: torch.Tensor, target_frames: int) -> torch.Tensor:
        """
        Smooth blending with wider kernel for smoother transitions.
        Uses a 3-frame window for blending.
        """
        source_frames = images.shape[0]
        device = images.device
        dtype = images.dtype
        
        # Ensure input is contiguous
        if not images.is_contiguous():
            images = images.contiguous()
        
        # Calculate fractional positions in source
        positions = torch.linspace(0, source_frames - 1, target_frames, device=device)
        
        output_frames = []
        for pos in positions:
            pos_val = pos.item()
            idx_center = int(round(pos_val))
            
            # Get neighboring frames with weights based on distance
            weights = []
            frames = []
            
            for offset in [-1, 0, 1]:
                idx = idx_center + offset
                if 0 <= idx < source_frames:
                    distance = abs(pos_val - idx)
                    # Gaussian-like weight
                    weight = max(0.0, 1.0 - distance)
                    if weight > 0:
                        weights.append(weight)
                        frames.append(images[idx].clone())
            
            # Normalize weights and blend
            if frames:
                total_weight = sum(weights)
                # Convert weights to tensor for proper dtype handling
                weights_tensor = torch.tensor(weights, device=device, dtype=dtype) / total_weight
                blended = sum(f * w for f, w in zip(frames, weights_tensor))
                output_frames.append(blended.clone())
            else:
                # Fallback to nearest
                output_frames.append(images[min(idx_center, source_frames - 1)].clone())
        
        return torch.stack(output_frames, dim=0).contiguous()
