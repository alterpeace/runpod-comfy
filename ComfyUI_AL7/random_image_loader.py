import os
import torch
import numpy as np
from PIL import Image, ImageOps
import random


class LoadRandomImage_Alt:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "folder": ("STRING", {"default": ""}),
            },
            "optional": {
                "include_subfolders": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "image_path")
    FUNCTION = "load_random_image"
    CATEGORY = "Alt"

    @classmethod
    def IS_CHANGED(s, folder, include_subfolders=False):
        # Return random value so ComfyUI considers the node changed on each run
        return random.random()

    def load_random_image(self, folder, include_subfolders=False):
        if not os.path.isdir(folder):
            raise FileNotFoundError(f"Folder '{folder}' cannot be found.")
        
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        image_paths = []
        
        if include_subfolders:
            for root, _, files in os.walk(folder):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in valid_extensions):
                        image_paths.append(os.path.join(root, file))
        else:
            for file in os.listdir(folder):
                if any(file.lower().endswith(ext) for ext in valid_extensions):
                    image_paths.append(os.path.join(folder, file))

        if not image_paths:
            raise FileNotFoundError(f"No valid images found in directory '{folder}'.")

        random_image_path = random.choice(image_paths)
        
        img = Image.open(random_image_path)
        img = ImageOps.exif_transpose(img)
        
        image = img.convert("RGB")
        image = np.array(image).astype(np.float32) / 255.0
        image = torch.from_numpy(image)[None,]
        
        height, width = image.shape[1:3]
        if 'A' in img.getbands():
            mask = np.array(img.getchannel('A')).astype(np.float32) / 255.0
            mask = 1. - torch.from_numpy(mask)
        else:
            mask = torch.zeros((height, width), dtype=torch.float32, device="cpu")

        return (image, mask, random_image_path)


class LoadRandomImages_Alt:
    """Load a batch of random images from a directory"""
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "folder": ("STRING", {"default": ""}),
                "count": ("INT", {"default": 1, "min": 1, "max": 1000}),
            },
            "optional": {
                "include_subfolders": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("images", "masks", "image_paths")
    FUNCTION = "load_random_images"
    CATEGORY = "Alt"

    @classmethod
    def IS_CHANGED(s, folder, count, include_subfolders=False):
        return random.random()

    def load_random_images(self, folder, count, include_subfolders=False):
        if not os.path.isdir(folder):
            raise FileNotFoundError(f"Folder '{folder}' cannot be found.")
        
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        image_paths = []
        
        if include_subfolders:
            for root, _, files in os.walk(folder):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in valid_extensions):
                        image_paths.append(os.path.join(root, file))
        else:
            for file in os.listdir(folder):
                if any(file.lower().endswith(ext) for ext in valid_extensions):
                    image_paths.append(os.path.join(folder, file))

        if not image_paths:
            raise FileNotFoundError(f"No valid images found in directory '{folder}'.")

        # Sample with replacement if count > available images
        if count > len(image_paths):
            selected_paths = random.choices(image_paths, k=count)
        else:
            selected_paths = random.sample(image_paths, count)

        # Load first image to get target size
        first_img = Image.open(selected_paths[0])
        first_img = ImageOps.exif_transpose(first_img)
        target_width, target_height = first_img.size

        images = []
        masks = []
        
        for path in selected_paths:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            
            # Check for alpha channel before any conversion/resize
            has_alpha = 'A' in img.getbands()
            
            # Resize to match first image dimensions
            if img.size != (target_width, target_height):
                img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Extract alpha mask before converting to RGB (which drops alpha)
            if has_alpha:
                # Re-check after resize in case mode changed
                if 'A' in img.getbands():
                    mask = np.array(img.getchannel('A')).astype(np.float32) / 255.0
                    mask = 1. - mask
                else:
                    mask = np.zeros((target_height, target_width), dtype=np.float32)
            else:
                mask = np.zeros((target_height, target_width), dtype=np.float32)
            masks.append(mask)
            
            image = img.convert("RGB")
            image = np.array(image).astype(np.float32) / 255.0
            images.append(image)

        # Stack into batches
        images_batch = torch.from_numpy(np.stack(images, axis=0))
        masks_batch = torch.from_numpy(np.stack(masks, axis=0))
        paths_str = "\n".join(selected_paths)

        return (images_batch, masks_batch, paths_str)


NODE_CLASS_MAPPINGS = {
    "LoadRandomImage_Alt": LoadRandomImage_Alt,
    "LoadRandomImages_Alt": LoadRandomImages_Alt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadRandomImage_Alt": "Load Random Image (Alt)",
    "LoadRandomImages_Alt": "Load Random Images (Alt)",
}
