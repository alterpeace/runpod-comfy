"""
MaskFromRGB_KMeans_Alt - Fixed version with proper cache invalidation
Cloned from eden_comfy_pipelines with IS_CHANGED fix for video batch processing.
"""

import torch
import torch.nn.functional as F
import hashlib
import time
from functools import lru_cache
from contextlib import nullcontext


# ============================================================
# Color space conversion (inlined to avoid dependency)
# ============================================================
def rgb_to_lab(srgb, device=None):
    """Convert sRGB to LAB color space."""
    if device is None:
        device = srgb.device
    
    # Ensure input is contiguous before reshaping
    if not srgb.is_contiguous():
        srgb = srgb.contiguous()
    
    original_shape = srgb.shape
    srgb_pixels = srgb.reshape(-1, 3).to(device)

    linear_mask = (srgb_pixels <= 0.04045).float()
    exponential_mask = (srgb_pixels > 0.04045).float()
    rgb_pixels = (srgb_pixels / 12.92 * linear_mask) + (((srgb_pixels + 0.055) / 1.055) ** 2.4) * exponential_mask
    
    rgb_to_xyz = torch.tensor([
        [0.412453, 0.212671, 0.019334],
        [0.357580, 0.715160, 0.119193],
        [0.180423, 0.072169, 0.950227],
    ], device=device, dtype=srgb_pixels.dtype)
    
    xyz_pixels = torch.mm(rgb_pixels, rgb_to_xyz)
    xyz_norm_scale = torch.tensor([1/0.950456, 1.0, 1/1.088754], device=device, dtype=srgb_pixels.dtype)
    xyz_normalized_pixels = xyz_pixels * xyz_norm_scale

    epsilon = 6.0/29.0
    linear_mask = (xyz_normalized_pixels <= (epsilon**3)).float()
    exponential_mask = (xyz_normalized_pixels > (epsilon**3)).float()
    fxfyfz_pixels = (xyz_normalized_pixels / (3 * epsilon**2) + 4.0/29.0) * linear_mask + ((xyz_normalized_pixels+0.000001) ** (1.0/3.0)) * exponential_mask
    
    fxfyfz_to_lab = torch.tensor([
        [  0.0,  500.0,    0.0],
        [116.0, -500.0,  200.0],
        [  0.0,    0.0, -200.0],
    ], device=device, dtype=srgb_pixels.dtype)
    
    lab_offset = torch.tensor([-16.0, 0.0, 0.0], device=device, dtype=srgb_pixels.dtype)
    lab_pixels = torch.mm(fxfyfz_pixels, fxfyfz_to_lab) + lab_offset
    
    return lab_pixels.reshape(original_shape).contiguous()


# ============================================================
# Gaussian kernels (separable, cached)
# ============================================================
@lru_cache(maxsize=16)
def gaussian_kernel_1d(kernel_size, sigma=None, device="cpu", dtype=torch.float32):
    if kernel_size % 2 == 0:
        kernel_size += 1
    if sigma is None:
        sigma = 0.3 * ((kernel_size - 1) * 0.5 - 1) + 0.8
    r = torch.arange(-(kernel_size//2), kernel_size//2 + 1, device=device, dtype=dtype)
    k = torch.exp(-(r**2) / (2 * sigma**2))
    k = k / k.sum()
    return k


def separable_gaussian_blur(x, kernel_size, device):
    dtype = x.dtype
    k1 = gaussian_kernel_1d(kernel_size, device=device, dtype=dtype)
    kx = k1.view(1,1,1,-1)
    ky = k1.view(1,1,-1,1)
    pad = kernel_size // 2
    x = F.pad(x, (pad,pad,pad,pad), mode='reflect')
    x = F.conv2d(x, kx)
    x = F.conv2d(x, ky)
    return x


# ============================================================
# KMeans (CUDA-friendly)
# ============================================================
def _seed_from_tensor(t: torch.Tensor) -> int:
    """Content-dependent deterministic seed based on small stats of t."""
    with torch.no_grad():
        m = t.mean(dim=0).float().cpu().numpy().tobytes()
    return int.from_bytes(hashlib.blake2b(m, digest_size=8).digest(), 'little') & 0x7FFFFFFF


def kmeans_torch(x, k, iters=20, tol=1e-4, seeding='kmeans++', device=None, use_amp=True, seed=None):
    """
    x: (N, D) float on CUDA
    returns centers (k, D), labels (N,)
    """
    assert x.dim() == 2
    N, D = x.shape
    device = device or x.device
    
    # Ensure input is contiguous
    if not x.is_contiguous():
        x = x.contiguous()
    
    amp_ctx = torch.cuda.amp.autocast(enabled=use_amp and x.is_cuda, dtype=torch.float16) if x.is_cuda else nullcontext()

    if seed is None:
        seed = 12345
    g = torch.Generator(device=device)
    g.manual_seed(seed)

    if seeding == 'kmeans++':
        idx0 = torch.randint(0, N, (1,), device=device, generator=g)
        centers = x[idx0].clone().contiguous()
        for _ in range(1, k):
            with amp_ctx:
                dist2 = torch.cdist(x.float(), centers.float(), p=2).pow(2)
                dmin = dist2.min(dim=1).values
            prob_sum = dmin.sum()
            if prob_sum <= 1e-12:
                # All points are at existing centers; pick randomly from remaining
                idx = torch.randint(0, N, (1,), device=device, generator=g)
            else:
                probs = dmin / prob_sum
                idx = torch.multinomial(probs, 1, generator=g)
            centers = torch.cat([centers, x[idx].clone()], dim=0).contiguous()
    else:
        perm = torch.randperm(N, generator=g, device=device)[:k]
        centers = x[perm].clone().contiguous()

    prev_inertia = None
    for _ in range(iters):
        with amp_ctx:
            dist2 = torch.cdist(x.float(), centers.float(), p=2).pow(2)
            labels = torch.argmin(dist2, dim=1)
            inertia = dist2.gather(1, labels.view(-1,1)).sum()

        new_centers = torch.zeros_like(centers)
        counts = torch.bincount(labels, minlength=k).clamp_min(1).view(-1,1).to(new_centers.dtype)
        new_centers.scatter_add_(0, labels.view(-1,1).expand(-1, D), x)
        new_centers = (new_centers / counts).contiguous()

        if prev_inertia is not None and torch.abs(prev_inertia - inertia) < tol * (prev_inertia + 1e-12):
            centers = new_centers
            break
        centers = new_centers
        prev_inertia = inertia

    return centers.contiguous(), labels.contiguous()


def _deterministic_stride_indices(N, max_points, device):
    if N <= max_points:
        return torch.arange(N, device=device)
    step = float(N) / float(max_points)
    idx = torch.clamp(torch.round(torch.arange(0, max_points, device=device) * step).long(), max=N-1)
    return idx.unique()


def fit_kmeans_gpu(lab_flat, n_color_clusters, max_fit_points=200_000, iters=25, device=None):
    N = lab_flat.shape[0]
    device = device or lab_flat.device
    
    # Ensure input is contiguous
    if not lab_flat.is_contiguous():
        lab_flat = lab_flat.contiguous()
    
    idx = _deterministic_stride_indices(N, max_fit_points, device=device)
    x_fit = lab_flat[idx].clone().contiguous()
    seed = _seed_from_tensor(x_fit.detach())
    centers, _ = kmeans_torch(x_fit, n_color_clusters, iters=iters, device=device, use_amp=True, seed=seed)
    dist2_full = torch.cdist(lab_flat.float(), centers.float(), p=2).pow(2)
    labels_full = torch.argmin(dist2_full, dim=1)
    return centers.contiguous(), labels_full.contiguous()


def equalize_cluster_areas(lab_flat, labels, centers, strength, max_iters=5):
    """Reassign pixels to equalize cluster areas while preserving color similarity."""
    if strength <= 0:
        return labels

    K = centers.shape[0]
    N = lab_flat.shape[0]
    target_size = N / K
    device = lab_flat.device

    labels = labels.clone()
    base_distances = torch.cdist(lab_flat.float(), centers.float(), p=2)
    distance_scale = base_distances.std().item()
    scaled_strength = strength * distance_scale

    for iteration in range(max_iters):
        counts = torch.bincount(labels, minlength=K).float()
        size_ratio = (counts + 1.0) / (target_size + 1.0)
        size_penalty = scaled_strength * torch.log(size_ratio)
        adjusted_distances = base_distances + size_penalty.unsqueeze(0)
        new_labels = torch.argmin(adjusted_distances, dim=1)

        if (new_labels == labels).all():
            break
        labels = new_labels

    return labels


# ============================================================
# ComfyUI Node - Fixed version with IS_CHANGED
# ============================================================
class MaskFromRGB_KMeans_Alt:
    """
    Fixed MaskFromRGB_KMeans with proper cache invalidation for video batches.
    Prevents stale/cached results when processing different video sequences.
    """
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE", ),
                "n_color_clusters": ("INT", {"default": 6, "min": 2, "max": 10}),
                "clustering_resolution": ("INT", {"default": 256, "min": 32, "max": 1024}),
                "feathering_fraction": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 0.5, "step": 0.01}),
                "equalize_areas": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("MASK","MASK","MASK","MASK","MASK","MASK","MASK","MASK","MASK",)
    RETURN_NAMES = ("1","2","3","4","5","6","7","8","combined",)
    FUNCTION = "execute"
    CATEGORY = "Alt"
    
    @classmethod
    def IS_CHANGED(cls, image, **kwargs):
        """
        Force re-execution by returning a unique hash based on actual image content.
        This prevents ComfyUI from returning cached results for different video batches.
        """
        with torch.no_grad():
            shape_str = str(image.shape)
            if image.numel() > 0:
                flat = image.flatten()
                n = flat.numel()
                indices = torch.linspace(0, n - 1, min(100, n)).long()
                samples = flat[indices].cpu().numpy().tobytes()
                content_hash = hashlib.md5(samples).hexdigest()
            else:
                content_hash = "empty"
        return f"{shape_str}_{content_hash}_{time.time_ns()}"

    @torch.no_grad()
    def execute(self, image, n_color_clusters, clustering_resolution, feathering_fraction, equalize_areas):
        if torch.cuda.is_available():
            device = torch.device('cuda')
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            device = torch.device('mps')
        else:
            device = torch.device('cpu')

        original_device = image.device
        
        # Ensure input is contiguous before device transfer
        if not image.is_contiguous():
            image = image.contiguous()
        image = image.to(device)

        # Convert to LAB - pass device explicitly
        lab_images = torch.stack([rgb_to_lab(img, device=device) for img in image])
        # permute creates non-contiguous tensor, make it contiguous
        lab_images = lab_images.permute(0, 3, 1, 2).contiguous()

        n, c, h, w = lab_images.shape
        h_target = int(clustering_resolution)
        w_target = int(round(clustering_resolution * w / h))
        lab_images = F.interpolate(lab_images, size=[h_target, w_target], mode='bicubic', align_corners=False)

        n, c, h, w = lab_images.shape
        # permute + reshape needs contiguous
        lab_flat = lab_images.permute(0, 2, 3, 1).contiguous().reshape(-1, 3).contiguous()

        centers, cluster_labels_flat = fit_kmeans_gpu(lab_flat, n_color_clusters, device=device)

        cluster_luminance = centers[:, 0].contiguous()
        sorted_indices = torch.argsort(cluster_luminance)
        index_map = torch.empty_like(sorted_indices)
        index_map[sorted_indices] = torch.arange(n_color_clusters, device=device)
        cluster_labels_flat = index_map[cluster_labels_flat].contiguous()

        if equalize_areas > 0:
            cluster_labels_flat = equalize_cluster_areas(
                lab_flat, cluster_labels_flat, centers[sorted_indices].contiguous(), strength=float(equalize_areas)
            )

        cluster_labels = cluster_labels_flat.view(n, h, w).contiguous()

        masks_list = []
        for k in range(n_color_clusters):
            mask_k = (cluster_labels == k).float().contiguous()
            masks_list.append(mask_k)

        masks = torch.stack(masks_list, dim=1).contiguous()
        K = min(n_color_clusters, 8)
        masks = masks[:, :K, :, :].contiguous()

        if n_color_clusters > 1:
            combined_mask = (cluster_labels.float() / (n_color_clusters - 1)).clamp(0, 1).contiguous()
        else:
            combined_mask = torch.zeros_like(cluster_labels, dtype=torch.float).contiguous()

        if feathering_fraction > 0:
            feather = int(feathering_fraction * (w + h) / 2.0)
            if feather < 3:
                feather = 3
            if feather % 2 == 0:
                feather += 1

            masks_b = masks.reshape(-1, 1, h, w).contiguous()
            masks_b = separable_gaussian_blur(masks_b, feather, device)
            masks = masks_b.view(n, K, h, w).contiguous()

            cmb_b = combined_mask.unsqueeze(1).contiguous()
            cmb_b = separable_gaussian_blur(cmb_b, feather, device)
            combined_mask = cmb_b.squeeze(1).contiguous()

        H0, W0 = image.shape[1], image.shape[2]
        masks = F.interpolate(masks.contiguous(), size=(H0, W0), mode='bicubic', align_corners=False).clamp(0, 1)
        combined_mask = F.interpolate(combined_mask.unsqueeze(1).contiguous(), size=(H0, W0), mode='bicubic', align_corners=False).squeeze(1).clamp(0, 1)

        # Ensure contiguous before device transfer
        masks = masks.contiguous().to(original_device)
        combined_mask = combined_mask.contiguous().to(original_device)

        N, Kcur, H, W = masks.shape
        if Kcur < 8:
            pad = torch.zeros((N, 8-Kcur, H, W), device=masks.device, dtype=masks.dtype)
            masks = torch.cat([masks, pad], dim=1).contiguous()

        # Return contiguous slices
        return (masks[:, 0].contiguous(), masks[:, 1].contiguous(), masks[:, 2].contiguous(), 
                masks[:, 3].contiguous(), masks[:, 4].contiguous(), masks[:, 5].contiguous(), 
                masks[:, 6].contiguous(), masks[:, 7].contiguous(), combined_mask.contiguous())
