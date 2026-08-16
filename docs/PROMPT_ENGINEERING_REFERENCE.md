# Prompt Engineering Reference for LTX-2.5 Video Generation

A comprehensive guide to writing high-quality prompts for LTX-2.5 video
generation in ComfyUI, including structured methodology, vocabulary,
and community resources.

---

## Prompt Structure — The 9-Layer Methodology

LTX-2.5 responds best to prompts built in layers. Each layer adds a
specific dimension of control. Not all layers are required, but including
more layers gives the model more information to work with.

### Layer 1: Subject / Mood (1-2 words)

What is the dominant visual feeling? This anchors the entire generation.

**Examples:** cinematic, psychedelic, sacred geometry, liquid metal,
nebula clouds, cosmic dust, arthouse, experimental film

### Layer 2: Lighting

How is the scene lit? Lighting dramatically affects mood.

**Terms:** golden hour lighting, natural sunlight, neon glow, dramatic
shadows, volumetric fog, ultraviolet, infrared, dark background, glowing
particles, volumetric light, flickering candles, lens flares

### Layer 3: Texture / Material

What surfaces are visible? Textures give the model material cues.

**Terms:** smooth metal, worn fabric, glossy surfaces, rough stone,
liquid metal, iridescent, holographic, prismatic refraction, chromatic
aberration, light leaks

### Layer 4: Color Palette

What colors dominate? Be specific.

**Terms:** vibrant, muted, monochromatic, high contrast, deep space colors,
neon glow, warm tones, cool tones, pastel, saturated

### Layer 5: Atmosphere

What particles/effects fill the air?

**Terms:** fog, rain, dust, smoke, particles, star fields, light trails,
cosmic dust, nebula clouds, volumetric fog

### Layer 6: Camera Language

How does the camera move? This is crucial for video (not image) generation.

**Terms:** follows, tracks, pans across, circles around, tilts upward,
pushes in, pulls back, overhead view, handheld movement, over-the-shoulder,
wide establishing shot, static frame, slow drift, weightless

### Layer 7: Scale

How much of the scene is visible?

**Terms:** expansive, epic, intimate, claustrophobic, vast, cosmic

### Layer 8: Pacing

How fast does motion feel?

**Terms:** slow motion, time-lapse, rapid cuts, lingering shot,
continuous shot, freeze-frame, fade-in, fade-out, seamless transition,
sudden stop, slow drift, hypnotic, trance-inducing, pulsing, rhythmic

### Layer 9: Style Markers

Film characteristics and technical qualities.

**Terms:** film grain, anamorphic lens flare, shallow depth of field,
motion blur, depth of field, 4k detail, professional cinematography,
film noir, experimental film, arthouse, stop-motion, 2D/3D animation,
claymation, hand-drawn, comic book, cyberpunk, 8-bit pixel, surreal,
minimalist, painterly, illustrated

---

## Example Prompt (All 9 Layers)

```
nebula clouds, cosmic dust, gravitational lensing,      ← Subject/Mood
deep space colors, ultraviolet, infrared,                ← Color Palette
star fields, light trails, volumetric light,             ← Atmosphere
vast scale, slow drift, weightless,                     ← Scale + Pacing
dark background, glowing particles,                     ← Lighting
fluid dynamics, swirling,                                ← Texture/Material
chromatic aberration, light leaks, prismatic refraction, ← Style Markers
liquid metal, iridescent, holographic,                   ← Texture
festival atmosphere, VJ loops, beat-synced motion,       ← Mood
abstract, non-representational, motion blur, depth of field, 4k detail  ← Style
```

---

## V2V Redetail Specifics

For video-to-video redetail workflows, the prompt guides the
re-rendering style. Key parameters:

| Parameter | Low (0.2-0.3) | High (0.4-0.5) |
|---|---|---|
| **Denoise** | Closer to source footage | More creative reinterpretation |
| **LoRA Strength** | Subtle style influence | Strong distilled model override |
| **Steps** | 6-8 (faster, less detail) | 10-20 (slower, more detail) |

### Negative Prompt Strategy

For abstract/VJing visuals, exclude:
- People, faces, hands, body parts (non-representational)
- CGI, cartoon, render (avoid digital look)
- Dots, speckles, halftone (avoid texture artifacts)
- Text, watermark, signature (avoid artifacts)
- Banding, scan lines (avoid compression artifacts)

---

## Visual Vocabulary Reference

### Animation
Stop-motion · 2D / 3D animation · Claymation · Hand-drawn

### Stylized
Comic book · Cyberpunk · 8-bit pixel · Surreal · Minimalist · Painterly · Illustrated

### Cinematic
Period drama · Film noir · Fantasy · Epic space opera · Thriller · Modern romance · Experimental film · Arthouse · Documentary

### Lighting
Flickering candles · Neon glow · Natural sunlight · Dramatic shadows · Volumetric fog · Ultraviolet · Infrared

### Textures
Rough stone · Smooth metal · Worn fabric · Glossy surfaces · Liquid metal · Iridescent · Holographic

### Color Palette
Vibrant · Muted · Monochromatic · High contrast · Deep space colors · Pastel · Saturated

### Atmosphere
Fog · Rain · Dust · Smoke · Particles · Star fields · Light trails · Cosmic dust · Nebula clouds

### Camera Language
Follows · Tracks · Pans across · Circles around · Tilts upward · Pushes in / pulls back · Overhead view · Handheld movement · Over-the-shoulder · Wide establishing shot · Static frame · Slow drift · Weightless

### Film Characteristics
Film grain · Lens flares · Pixelated edges · Jittery stop-motion · Anamorphic lens flare · Shallow depth of field · Motion blur · Depth of field

### Scale Indicators
Expansive · Epic · Intimate · Claustrophobic · Vast · Cosmic

### Pacing & Temporal Effects
Slow motion · Time-lapse · Rapid cuts · Lingering shot · Continuous shot · Freeze-frame · Fade-in / fade-out · Seamless transition · Sudden stop · Slow drift · Hypnotic · Trance-inducing · Pulsing · Rhythmic

### Visual Effects
Particle systems · Motion blur · Depth of field · Fluid dynamics · Gravitational lensing · Chromatic aberration · Light leaks · Prismatic refraction

---

## Usage in Workflows

Use these terms in the `CLIPTextEncode` positive prompt node:

```json
{
  "class_type": "CLIPTextEncode",
  "inputs": {
    "text": "cinematic drone shot, golden hour lighting, film grain, shallow depth of field, slow motion, expansive landscape, dramatic shadows, 4k detail"
  }
}
```

For V2V redetail workflows, the prompt guides the re-rendering style.
Lower IC-LoRA `strength` values give the model more creative freedom to
reinterpret the footage; higher values keep it closer to the original.

---

## Communities & Resources for LTX Prompt Engineering

### Discord Communities
- **ComfyUI Discord** — `#ltx-video` channel. Most active LTX workflow
  sharing. Users post workflow JSON, prompt examples, and LoRA configs.
  Join at: https://discord.com/invite/comfyui
- **Lightricks Discord** — Official LTX model creator. Early access to
  new models, direct Q&A with the team.

### Reddit
- **r/comfyui** — Workflow JSON sharing, prompt discussions, node
  troubleshooting. Search "LTX" for relevant posts.
- **r/StableDiffusion** — General diffusion prompt techniques that
  transfer to LTX. Strong community for prompt engineering fundamentals.

### Model Hubs
- **Hugging Face** — `Lightricks/LTX-2.5` model page. Includes example
  prompts, model cards, and usage instructions.
- **Civitai.com** — User-generated LTX models, LoRAs, and prompt
  examples. Search "LTX" for community-created content. Users post
  full prompt strings with their outputs.

### GitHub
- **Lightricks/ComfyUI-LTXVideo** — Official custom node repo.
  Contains example workflows in `example_workflows/` directory with
  prompt examples for T2V, I2V, V2V, ICLoRA, and more.
- **comfyanonymous/ComfyUI** — Main ComfyUI repo. Check issues and
  discussions for LTX-related threads.

### Social Media
- **X/Twitter** — Follow `@Lightricks`. Search `#LTX` `#ComfyUI`
  `#LTXVideo` for creator content, prompt sharing, and result showcases.
- **YouTube** — Search "ComfyUI LTX" for tutorials. Notable creators:
  - **Scott Detweiler** — Professional prompt engineering for video models
  - **Olivio Sarikas** — Workflow breakdowns and prompt analysis
  - **Sebastian Kamph** — Beginner-friendly diffusion tutorials

### Workflow Marketplaces
- **OpenArt.ai** — LTX workflow templates with prompt examples.
  Pre-built workflows you can import directly into ComfyUI.
- **ComfyWorkflows.com** — Community-shared ComfyUI workflows,
  including LTX video generation pipelines.

### How Creators Achieve High-Quality Results

1. **Layered prompts** — Top creators use the 9-layer methodology above,
   not just keyword dumps. Each layer adds specific control.

2. **Negative prompt tuning** — High-quality results come from carefully
   curated negative prompts that exclude artifacts without over-constraining.

3. **LoRA stacking** — Creators combine multiple LoRAs (distilled + style
   + motion) with carefully tuned strengths. The distilled LoRA provides
   the base look; style LoRAs add aesthetic direction.

4. **Step count vs. denoise balance** — For V2V, creators balance steps
   and denoise. More steps with lower denoise gives cleaner detail; fewer
   steps with higher denoise gives more creative reinterpretation.

5. **Resolution scaling** — Generate at 640×352 (entry tier) or
   768×432 (comfortable tier), then upscale with latent spatial upscaler.
   Direct high-res generation produces worse results than generate-then-upscale.

6. **Frame rate matching** — Match `force_rate` to the source video's
   frame rate for smooth V2V. Mismatched rates cause stutter.

7. **Seed exploration** — Creators test multiple seeds with the same
   prompt to find the "sweet spot" before iterating on prompt text.
   Seeds matter as much as prompts for video quality.
