"""
Extend Sequence Alt Node

Alternative Extend_Sequence with IS_CHANGED to prevent caching issues.
This ensures fresh tensor allocation on every execution, preventing
corrupted latent outputs on subsequent runs.
"""

import sys
import time
import torch


class Extend_Sequence_Alt:
    """
    Extends an image sequence to a target number of frames.
    
    Unlike the original Extend_Sequence, this version includes IS_CHANGED
    to force re-execution and prevent corrupted latent tensor caching.
    """
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE",),
                "target_n_frames": ("INT", {"default": 24, "min": 1, "step": 1, "max": sys.maxsize}),
                "mode": (["wrap_around", "ping_pong"],),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "process_sequence"
    CATEGORY = "Alt"

    @classmethod
    def IS_CHANGED(cls, images, target_n_frames, mode):
        # Return unique value each time to prevent caching
        return time.time()

    def process_sequence(self, images, target_n_frames, mode="wrap_around"):
        n_frames = images.shape[0]
        
        if target_n_frames <= n_frames:
            return (images[:target_n_frames].clone(),)

        if mode == "wrap_around":
            extended_images = self._wrap_around(images, target_n_frames)
        elif mode == "ping_pong":
            extended_images = self._ping_pong(images, target_n_frames)
        else:
            extended_images = self._wrap_around(images, target_n_frames)

        # Clone to ensure fresh tensor, not a view
        return (extended_images.clone(),)

    def _wrap_around(self, images, target_n_frames):
        """Wrap around the input images to match the target number of frames."""
        n_frames = images.shape[0]
        indices = torch.arange(target_n_frames, device=images.device) % n_frames
        return images[indices]

    def _ping_pong(self, images, target_n_frames):
        """Create a ping-pong effect by repeating and reversing frames."""
        n_frames = images.shape[0]
        cycle_length = 2 * n_frames - 2 if n_frames > 1 else 1
        indices = torch.arange(target_n_frames, device=images.device) % max(cycle_length, 1)
        indices = torch.where(indices >= n_frames, 2 * n_frames - indices - 2, indices)
        indices = torch.clamp(indices, 0, n_frames - 1)
        return images[indices]
