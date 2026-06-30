# Reels Vault — Visual Assets

## Quick Start

1. Save screenshots to `assets/screenshots/`:
   ```
   01-claude-install.png
   02-claude-extract.png
   03-obsidian-metadata.png
   04-obsidian-transcript.png
   ```

2. Run:
   ```bash
   cd assets && ./create-gifs.sh
   ```

3. Get GIFs in `assets/gifs/`

## Effects

| GIF | Duration | Effect |
|-----|----------|--------|
| 01-claude-install | 2.5s | Zoom into success message |
| 02-claude-extract | 3s | Zoom into "Saved ✓" result |
| 03-obsidian-metadata | 3s | Zoom into properties panel |
| 04-obsidian-transcript | 3.5s | Scroll through transcript |
| hero-combined | ~12s | All 4 stitched |

## Tuning

Edit `create-gifs.sh` — key variables:

- `d=75` — frames (75/30fps = 2.5s). Multiply seconds × 30.
- `z='min(zoom+0.004,1.35)'` — zoom speed (0.004) and max depth (1.35x)
- `x/y` — zoom anchor point (fractions of width/height)
- `max_colors=192` — GIF color quality (128=small, 256=best)
- `fps=20` — GIF frame rate (15=choppy, 30=smooth, large)
