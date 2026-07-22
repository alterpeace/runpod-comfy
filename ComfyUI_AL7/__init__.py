"""
Alt Custom Nodes - Alternative implementations with improved caching behavior
"""

from .extend_sequence import Extend_Sequence_Alt
from .mask_from_rgb_kmeans import MaskFromRGB_KMeans_Alt
from .random_image_loader import LoadRandomImage_Alt, LoadRandomImages_Alt
from .random_filepath_sampler import Alt_RandomFilepathSampler
from .time_stretch_batch import TimeStretchBatch
from .all_media_loader import AllMediaLoader
from .determine_frame_count import DetermineFrameCount

NODE_CLASS_MAPPINGS = {
    "Extend_Sequence_Alt": Extend_Sequence_Alt,
    "MaskFromRGB_KMeans_Alt": MaskFromRGB_KMeans_Alt,
    "LoadRandomImage_Alt": LoadRandomImage_Alt,
    "LoadRandomImages_Alt": LoadRandomImages_Alt,
    "Alt_RandomFilepathSampler": Alt_RandomFilepathSampler,
    "TimeStretchBatch": TimeStretchBatch,
    "AllMediaLoader": AllMediaLoader,
    "DetermineFrameCount": DetermineFrameCount,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Extend_Sequence_Alt": "Extend Sequence (Alt)",
    "MaskFromRGB_KMeans_Alt": "Mask From RGB KMeans (Alt)",
    "LoadRandomImage_Alt": "Load Random Image (Alt)",
    "LoadRandomImages_Alt": "Load Random Images (Alt)",
    "Alt_RandomFilepathSampler": "Random Filepath Sampler (Alt)",
    "TimeStretchBatch": "Time Stretch Batch",
    "AllMediaLoader": "All Media Loader (Alt)",
    "DetermineFrameCount": "Determine Frame Count (Alt)",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
