# Prompt Engineering Reference for LTX-2.5 Video Generation

Useful terms for shaping video generation results. Not exhaustive — mix and
match to achieve desired effects.

---

## Categories

**Animation** — Stop-motion · 2D / 3D animation · Claymation · Hand-drawn

**Stylized** — Comic book · Cyberpunk · 8-bit pixel · Surreal · Minimalist · Painterly · Illustrated

**Cinematic** — Period drama · Film noir · Fantasy · Epic space opera · Thriller · Modern romance · Experimental film · Arthouse · Documentary

---

## Visual Details

**Lighting** — Flickering candles · Neon glow · Natural sunlight · Dramatic shadows

**Textures** — Rough stone · Smooth metal · Worn fabric · Glossy surfaces

**Color Palette** — Vibrant · Muted · Monochromatic · High contrast

**Atmosphere** — Fog · Rain · Dust · Smoke · Particles

---

## Sound and Voice

**Ambient Settings** — Coffeeshop noise · Wind and rain · Forest ambience with birds

**Dialogue Style** — Energetic announcer · Resonant voice with gravitas · Distorted radio-style · Robotic monotone · Childlike curiosity

**Volume** — Whisper · Mutter · Shout · Scream

---

## Technical Style Markers

**Camera Language** — Follows · Tracks · Pans across · Circles around · Tilts upward · Pushes in / pulls back · Overhead view · Handheld movement · Over-the-shoulder · Wide establishing shot · Static frame

**Film Characteristics** — Film grain · Lens flares · Pixelated edges · Jittery stop-motion

**Scale Indicators** — Expansive · Epic · Intimate · Claustrophobic

**Pacing & Temporal Effects** — Slow motion · Time-lapse · Rapid cuts · Lingering shot · Continuous shot · Freeze-frame · Fade-in / fade-out · Seamless transition · Sudden stop

**Visual Effects** — Particle systems · Motion blur · Depth of field

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

For V2V redetail workflows, the prompt guides the re-rendering style. Lower
IC-LoRA `strength` values give the model more creative freedom to reinterpret
the footage; higher values keep it closer to the original.
