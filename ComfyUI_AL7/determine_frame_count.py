"""
DetermineFrameCount - Calculate optimal output frame count for time stretching.

Handles both:
- Extending short loops (e.g., 24 frames → 96 frames)
- Compressing long videos (e.g., 150 frames → 32 frames)
"""

import math
from typing import Tuple


class DetermineFrameCount:
    """
    Calculate optimal frame count for time stretching operations.
    
    Works for both extending short loops and compressing long videos.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "n_target_frames": ("INT", {
                    "default": 64,
                    "min": 1,
                    "max": 4096,
                    "step": 1,
                    "tooltip": "Desired target frame count (e.g., AnimateDiff n_frames)"
                }),
                "n_source_frames": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 99999,
                    "step": 1,
                    "tooltip": "Number of frames in source (connect to AllMediaLoader COUNT)"
                }),
                "policy": (["closest", "round_down", "round_up", "exact"], {
                    "default": "closest",
                    "tooltip": "How to calculate output frames"
                }),
                "min_frames": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 4096,
                    "step": 1,
                    "tooltip": "Minimum output frames"
                }),
                "max_frames": ("INT", {
                    "default": 1024,
                    "min": 1,
                    "max": 4096,
                    "step": 1,
                    "tooltip": "Maximum output frames"
                }),
            },
        }
    
    RETURN_TYPES = ("INT", "FLOAT", "STRING")
    RETURN_NAMES = ("frame_count", "stretch_factor", "info")
    FUNCTION = "determine"
    CATEGORY = "Alt"
    DESCRIPTION = """
Calculate optimal frame count for time stretching.

Works for BOTH cases:
- Short source (e.g., 24 frames) → extends to fill target
- Long source (e.g., 150 frames) → compresses to fit target

Policies:
- closest: Round to nearest good value
- round_down: Prefer fewer frames (faster)
- round_up: Prefer more frames (slower)
- exact: Use target frames exactly

Connect n_source_frames to AllMediaLoader's COUNT output.
"""

    def determine(
        self,
        n_target_frames: int,
        n_source_frames: int,
        policy: str,
        min_frames: int,
        max_frames: int
    ) -> Tuple[int, float, str]:
        # Validate min/max
        if min_frames > max_frames:
            min_frames, max_frames = max_frames, min_frames
        
        # Handle edge cases
        if n_target_frames <= 0:
            n_target_frames = 1
        if n_source_frames <= 0:
            n_source_frames = 1
        
        # Determine if we're extending or compressing
        is_extending = n_source_frames <= n_target_frames
        
        if policy == "exact":
            # Just use target, clamped to min/max
            result = max(min_frames, min(n_target_frames, max_frames))
            mode = "exact"
        
        elif is_extending:
            # SOURCE IS SHORTER - extend by looping
            # Find multiple of source that's closest to target
            if policy == "closest":
                loops = round(n_target_frames / n_source_frames)
                loops = max(1, loops)
            elif policy == "round_down":
                loops = n_target_frames // n_source_frames
                loops = max(1, loops)
            elif policy == "round_up":
                loops = math.ceil(n_target_frames / n_source_frames)
            else:
                loops = max(1, round(n_target_frames / n_source_frames))
            
            result = loops * n_source_frames
            mode = f"extend ({loops} loops)"
        
        else:
            # SOURCE IS LONGER - compress to fit
            # Find a divisor of source that gives us close to target
            # Or just use target directly (TimeStretchBatch handles resampling)
            
            if policy == "closest":
                # Find divisor that gets closest to target
                best_result = n_target_frames
                best_diff = abs(n_target_frames - n_target_frames)
                
                # Try divisors of source
                for divisor in range(1, min(n_source_frames + 1, 100)):
                    candidate = n_source_frames // divisor
                    if min_frames <= candidate <= max_frames:
                        diff = abs(candidate - n_target_frames)
                        if diff < best_diff:
                            best_diff = diff
                            best_result = candidate
                
                # Also consider just using target directly
                if min_frames <= n_target_frames <= max_frames:
                    if abs(n_target_frames - n_target_frames) <= best_diff:
                        best_result = n_target_frames
                
                result = best_result
                
            elif policy == "round_down":
                # Use target or find smaller divisor
                result = n_target_frames
                for divisor in range(1, n_source_frames + 1):
                    candidate = n_source_frames // divisor
                    if candidate <= n_target_frames and candidate >= min_frames:
                        result = candidate
                        break
                        
            elif policy == "round_up":
                # Use target or find larger divisor  
                result = n_target_frames
                candidates = []
                for divisor in range(1, n_source_frames + 1):
                    candidate = n_source_frames // divisor
                    if candidate >= n_target_frames and candidate <= max_frames:
                        candidates.append(candidate)
                if candidates:
                    result = min(candidates)
            else:
                result = n_target_frames
            
            mode = f"compress ({n_source_frames}→{result})"
        
        # Final clamp to min/max
        result = max(min_frames, min(result, max_frames))
        
        # Calculate stretch factor
        stretch_factor = result / n_source_frames if n_source_frames > 0 else 1.0
        
        # Info string
        info = f"{mode}: {n_source_frames} src → {result} out (x{stretch_factor:.2f})"
        
        return (int(result), stretch_factor, info)
