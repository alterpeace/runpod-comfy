
The short answer is no, you cannot use the exact TextureFlow SD1.5 + AnimateDiff workflow files with LTX-2 or Wan because the underlying architectures are fundamentally different.
However, you can achieve the same result (seamlessly looping video textures) using LTX-2 or Wan by adapting the logic to the Diffusion Transformer (DiT) architecture.
Here is a breakdown of why they differ and how you can replicate the effect.
1. Why the SD1.5 Workflow won't work "As Is"
Architecture (UNet vs. DiT): SD1.5 uses a UNet with 2D convolutions. TextureFlow loops usually rely on "Circular Padding" (injecting a setting into the convolutions so the left side sees the right side). LTX-2 and Wan are Transformers; they process data as "patches" and don't use convolutions in the same way, so the standard "Tiling" nodes for SD1.5 will simply error out.
Temporal Modules: AnimateDiff is a separate module added onto SD1.5. LTX-2 and Wan have native temporal attention built-in. The nodes used to control AnimateDiff (Context Windows, Iterative Latent Shifts) do not talk to the DiT blocks of these newer models.
2. How to achieve Seamless Looping with LTX-2 or Wan
To get a "TextureFlow" result with these newer models, you need to use techniques specific to Video DiTs:
A. Temporal Looping (The "Loop" part)
Since LTX and Wan are much more powerful, you don't necessarily need "FreeNoise" (an SD1.5 trick). Instead, use:
Latent Blending/Stitching: In ComfyUI, you can use nodes from the ComfyUI-Video-Helper-Suite. You generate a video slightly longer than needed, then use a "Vae Encode (Batched)" and blend the last few frames back into the first few frames using a mask or latent interpolation.
Iterative Sampling: Some custom nodes for Wan2.1 are being developed to allow "Context Overlap" sampling, similar to how AnimateDiff works, which allows the end of the video to "know" what the beginning looks like.
B. Spatial Tiling (The "Texture" part)
This is the hardest part for DiTs. Because they use positional embeddings, "wrapping" the edges is difficult.
The VAE Trick: The most effective way currently is to use a Tiled VAE decode. While this doesn't make the generation seamless, it prevents the edges from "stretching."
Post-Process Tiling: Generate the video at a high resolution, then use a "Seamless Tile" node (like those in the ComfyUI-Essentials pack) on the resulting frames. Because LTX and Wan have such high coherence, you can often "offset" the video and use an Inpaint mask to fix the seam.
3. Which model is better for this?
Wan2.1 (T2V-1.3B or 14B): Better for complex textures (liquids, fire, magic effects). It has very high "prompt adherence," so it stays on-pattern better than SD1.5.
LTX-Video (LTX-2): Better for spatial consistency. LTX is very good at maintaining the "3D-ness" of a texture. If you want a looping brick wall or moving fabric, LTX-2 is likely faster and more stable.
4. Recommendation for your Workflow
If you want to move away from SD1.5/AnimateDiff to these newer models:
Download the latest ComfyUI-WanVideo or ComfyUI-LTXVideo nodes.
Use a "Video Linear UI" or "Forced Loop" sampling strategy: Look for nodes that allow you to feed the first frame's latents back into the final sampling step.
For the "Texture" aspect: Use a prompt like "seamless texture, top-down view, orthographic" and then use the "Image Offset" technique in post-processing to blend the seams.
Summary: You can't use the old .json files, but the Concept of TextureFlow is actually much easier to achieve with Wan/LTX because they understand motion much better than SD1.5 ever did. You just have to handle the "seams" in the VAE or via post-processing rather than inside the UNet.



Practical Comparison: How to do this today
Method	Effort	Result Quality	Recommended Tool
Noise Interpolation	Low	Good for abstract textures	ComfyUI-Noise (Batch Noise)
Latent Blending	Medium	Very smooth, but can "ghost"	Video-Helper-Suite (Latent Blend)
I2V Targeting	High	Best for complex motion	Wan2.1 I2V + Load Image
Step-by-Step for a Texture Loop (Wan2.1 / LTX-Video):
Generate your base texture: Use a standard T2I (like SDXL or Flux) to get a high-quality seamless tile.
Prepare Latents: Create a latent batch of 24–48 frames.
Set the Loop Pins:
Put your base texture into Frame 0.
Put that same texture into Frame 24 (the end).
Use a "Latent Keyframe" node to set the strength of these frames to 100% (so the sampler doesn't change them too much).
Denoise: Run the Wan2.1 I2V sampler. The model will animate the "empty" frames between 0 and 24.
Post-Process: Because the first and last frames are the same, the video will loop perfectly.
Summary: While you can't use the old "TextureFlow" node (which was a specific code hack for SD1.5's UNet), you can achieve a higher quality result by using I2V Targeting. You essentially "pin" the start and end to the same image and let the powerful DiT model fill in the motion.




The term "LTX-Video AnimateDiff LoRA" usually refers to the Motion LoRAs released for the LTX-Video architecture (often used in ComfyUI to give more control over how things move).
Using these LoRAs makes the TextureFlow concept much easier to achieve than using the base LTX model alone. Here is how that changes the workflow and how to implement it:
1. What the LoRA actually does for Looping
Standard LTX-Video can be "chaotic"—objects move in and out of frame quickly. The Motion LoRAs (like the Slow Motion or Camera Control LoRAs) stabilize the "latent flow."
For a looping texture (like flowing water, moving clouds, or shifting sand), the LoRA acts as an anchor. It prevents the model from introducing "new" objects halfway through the video, which is the biggest killer of a seamless loop.
2. The Updated Workflow (LTX-Video + Motion LoRA)
To replicate a TextureFlow looping setup with these tools, you should use the "Image-to-Video-to-Image" loopback.
The Setup:
Model: LTX-Video.
LoRA: Apply the ltx_video_motion_lora at a strength of 0.6–1.0.
Sampler: Use the LTXVideoSampler node.
The Looping Logic (The "Ping-Pong" or "Closed Loop" method):
Instead of the SD1.5 "Circular Padding" hack, you use Latent Noise Injection.
In ComfyUI, use the "Batch Creative Interpolation" or "Video Linear UI" node logic.
The trick: You take the Final Frame of your generated latent and "add" it back to the Initial Noise of the first frame.
3. How to get "Seamless Tiling" (Edges)
The "TextureFlow" workflow in SD1.5 often used a "Tiling" button. LTX-Video does not have a native "Tiling" mode in the transformer blocks yet.
To get seamless edges with LTX-Video LoRAs:
The VAE Tiling Hack: In ComfyUI, use the "VAE Decode (Tiled)" node. While this is meant for saving VRAM, if you set the tile size correctly, it can sometimes help force edge consistency.
The Post-Crop Method (Most Reliable):
Generate your texture video at 768x768 (or higher).
Use a "Tile Image" node to offset the video by 50% (so the "seams" move to the center).
Use an Inpaint Mask on that center seam.
Run a second LTX-Video pass (at a low denoising strength, around 0.3) with the Motion LoRA active. This will "heal" the seam while keeping the movement consistent.
4. Why this is better than the SD1.5 version
While the SD1.5 TextureFlow was easier to set up (one click for "Tiling"), the LTX-Video version is physically more accurate.
SD1.5: Often looks like a "sliding image" or a "kaleidoscope."
LTX-Video + LoRA: Looks like actual moving geometry. The shadows, lighting, and perspective shift correctly as the texture moves.
Summary: Can you use the LoRA for TextureFlow?
Yes, but you have to change your mindset:
Don't look for a "Tiling" toggle.
Do use the Motion LoRA to keep the movement slow and steady.
Do use I2V (Image-to-Video) where the first and last frames are the same image to "force" the temporal loop.
Do use a Post-Process Offset to fix the spatial seams (the edges of the texture).
Recommended Node Suite: Look for "ComfyUI-LTXVideo" by Lightricks or Kosinkadink. They have the "Context Options" nodes that allow you to set a "Loop" boolean to True, which attempts to wrap the temporal attention around from the end back to the start.