# LUTs (Look-Up Tables)

428 .cube LUT files for professional color grading.

## Categories

- Action Movie, Adventure, Advertisement, Aerial Drone
- Analog Film, Autumn, Beach, Beauty Blogger
- Black & White, Blockbuster Movie, Bohemian, Box Office
- Brilliance, Broadcast, Cinematic, Cinematography
- Cinema Tones, City Vibes, Color Clash, Commercial
- Contemporary, Corporate, Documentary, Dramatic
- Dreamy, Duotone, Editorial, Explorer
- Extreme Sports, Fashion Glam, Filmmaker, Film Emulation
- Film Noir, Film Stock, Fitness, Food
- Golden Hour, High Contrast, Hipster, Horror
- Indie, Industrial, Influencer, Interview
- Investigation, Lifestyle, Luxury, Military
- Moody, Motion Picture, Music Video, Neon Cyberpunk
- Nightlife, Pastel, Podcast, Pop Culture
- Post-Apocalypse, Real Estate, Red Carpet, Retro
- Romance, Safari, Sci-Fi, Smartphone
- Social Media, Sports, Spring, Street Vibes
- Summer, Telecast, Thriller, Timeless
- Tone Tension, Travel, Tropical, Underwater
- Urban, Vibrant, Videography, Vintage
- Washed Pastel, Wedding, Wildlife, Winter

## Usage with ffmpeg

```bash
ffmpeg -i input.mp4 -vf "lut3d=luts/Music_Video_LUTS (1).cube" -c:v libx264 -crf 16 -g 1 -bf 0 -an output.mp4
```

## Recommended LUTs for Music Visuals

| Variation | LUT Category | Effect |
|---|---|---|
| golden_cinematic | Analog Film / Golden Hour | Warm, filmic, nostalgic |
| neon_psychedelic | Neon Cyberpunk | Bright neon, futuristic |
| sacred_geometry | Sci-Fi | Cool, otherworldly |
| festival_energy | Music Video / Blockbuster | Bold, vibrant, high-energy |
| liquid_dreams | Dreamy | Soft, ethereal, pastel |
