"""
Random Filepath Sampler - Standalone ComfyUI custom node
Extracted from eden_comfy_pipelines for independent use
"""

import os
import random
import re
from typing import Tuple


class Alt_RandomFilepathSampler:
    """Node that samples a random filepath from a directory with filtering options"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "directory_path": ("STRING", {"default": "./"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
            "optional": {
                "file_extension": ("STRING", {"default": ""}),
                "include_subdirectories": ("BOOLEAN", {"default": False}),
                "filter_string": ("STRING", {"default": ""}),
                "filter_mode": (["contains", "starts_with", "ends_with", "regex"], {"default": "contains"}),
                "case_sensitive": ("BOOLEAN", {"default": False}),
            }
        }

    FUNCTION = "sample_filepath"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("filepath",)
    CATEGORY = "alt"

    def sample_filepath(
        self,
        directory_path: str,
        seed: int,
        file_extension: str = "",
        include_subdirectories: bool = False,
        filter_string: str = "",
        filter_mode: str = "contains",
        case_sensitive: bool = False
    ) -> Tuple[str]:
        """Sample a random filepath from the given directory matching the specified criteria.

        Args:
            directory_path: The directory path to sample files from
            seed: Random seed for reproducible sampling
            file_extension: File extension to filter by (e.g., ".jpg", ".png")
            include_subdirectories: Whether to include files from subdirectories
            filter_string: String to filter filenames by
            filter_mode: How to apply the filter_string (contains, starts_with, ends_with, regex)
            case_sensitive: Whether string filtering should be case-sensitive

        Returns:
            A tuple containing the randomly selected filepath as a string
        """
        # Set random seed for reproducibility
        random.seed(seed)

        # Clean up input parameters
        directory_path = os.path.expanduser(directory_path)  # Expand ~ if present

        if file_extension and not file_extension.startswith('.'):
            file_extension = '.' + file_extension

        # Validate directory exists
        if not os.path.isdir(directory_path):
            raise ValueError(f"Directory not found: {directory_path}")

        # Gather all files based on the include_subdirectories flag
        all_files = []
        if include_subdirectories:
            for root, _, files in os.walk(directory_path):
                for file in files:
                    all_files.append(os.path.join(root, file))
        else:
            all_files = [
                os.path.join(directory_path, f)
                for f in os.listdir(directory_path)
                if os.path.isfile(os.path.join(directory_path, f))
            ]

        # Filter by extension if specified
        if file_extension:
            all_files = [f for f in all_files if f.lower().endswith(file_extension.lower())]

        # Apply additional filename filtering if specified
        if filter_string:
            filtered_files = []
            for filepath in all_files:
                filename = os.path.basename(filepath)

                # Apply case sensitivity
                compare_filename = filename if case_sensitive else filename.lower()
                compare_filter = filter_string if case_sensitive else filter_string.lower()

                # Apply filtering based on selected mode
                if filter_mode == "contains":
                    if compare_filter in compare_filename:
                        filtered_files.append(filepath)
                elif filter_mode == "starts_with":
                    if compare_filename.startswith(compare_filter):
                        filtered_files.append(filepath)
                elif filter_mode == "ends_with":
                    if compare_filename.endswith(compare_filter):
                        filtered_files.append(filepath)
                elif filter_mode == "regex":
                    flags = 0 if case_sensitive else re.IGNORECASE
                    if re.search(filter_string, filename, flags):
                        filtered_files.append(filepath)

            all_files = filtered_files

        # Remove hidden files (starting with .)
        all_files = [f for f in all_files if not os.path.basename(f).startswith('.')]

        # Check if any files match the criteria
        if not all_files:
            raise ValueError(f"No files found matching the specified criteria in {directory_path}")

        selected_file = random.choice(all_files)
        return (selected_file,)


NODE_CLASS_MAPPINGS = {
    "Alt_RandomFilepathSampler": Alt_RandomFilepathSampler,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Alt_RandomFilepathSampler": "Random Filepath Sampler 🎲 (Alt)",
}
