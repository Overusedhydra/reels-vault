#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCREENSHOTS="$SCRIPT_DIR/screenshots"
GIFS="$SCRIPT_DIR/gifs"
mkdir -p "$GIFS"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${GREEN}🎬 Reels Vault GIF Generator${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

command -v ffmpeg &>/dev/null || { echo -e "${RED}❌ ffmpeg not found${NC}"; exit 1; }

# Helper: create a zoom-pan GIF from a screenshot
# $1=input $2=output $3=duration $4=zoompan_filter
make_gif() {
    local input="$1" output="$2" dur="$3" zp="$4" name="$5"
    echo -e "${GREEN}📸 $name${NC}"

    # Render at high res, 30fps, then downscale to GIF with palette
    ffmpeg -y -loop 1 -i "$input" \
        -vf "scale=6000:-1,$zp:s=1200x800:fps=30" \
        -t "$dur" -pix_fmt yuv420p "$GIFS/_tmp.mp4" 2>/dev/null

    ffmpeg -y -i "$GIFS/_tmp.mp4" \
        -vf "fps=20,split[s0][s1];[s0]palettegen=max_colors=192:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5" \
        -loop 0 "$output" 2>/dev/null

    rm -f "$GIFS/_tmp.mp4"
    local size=$(du -h "$output" | cut -f1)
    echo -e "${GREEN}   ✅ $output ($size)${NC}"
}

# 01 — Claude Install: zoom into the success/clone area
f="$SCREENSHOTS/01-claude-install.png"
[ -f "$f" ] && make_gif "$f" "$GIFS/01-claude-install.gif" 2.5 \
    "zoompan=z='min(zoom+0.004,1.35)':x='iw/2-(iw/zoom/2)':y='ih*0.6-(ih/zoom/2)':d=75" \
    "01-claude-install"

# 02 — Claude Extract: zoom into "Saved ✓" + file path
f="$SCREENSHOTS/02-claude-extract.png"
[ -f "$f" ] && make_gif "$f" "$GIFS/02-claude-extract.gif" 3 \
    "zoompan=z='if(lte(zoom,1.0),1.3,max(1.001,zoom-0.003))':x='iw*0.35-(iw/zoom/2)':y='ih*0.5-(ih/zoom/2)':d=90" \
    "02-claude-extract"

# 03 — Obsidian Metadata: gentle zoom into properties panel
f="$SCREENSHOTS/03-obsidian-metadata.png"
[ -f "$f" ] && make_gif "$f" "$GIFS/03-obsidian-metadata.gif" 3 \
    "zoompan=z='min(zoom+0.003,1.25)':x='iw/2-(iw/zoom/2)':y='ih*0.25-(ih/zoom/2)':d=90" \
    "03-obsidian-metadata"

# 04 — Obsidian Transcript: scroll down through lines
f="$SCREENSHOTS/04-obsidian-transcript.png"
[ -f "$f" ] && make_gif "$f" "$GIFS/04-obsidian-transcript.gif" 3.5 \
    "zoompan=z='1.15':x='iw/2-(iw/zoom/2)':y='min(y+4,ih-ih/zoom)':d=105" \
    "04-obsidian-transcript"

# Hero: stitch all available GIFs
available=()
for g in "$GIFS"/0*.gif; do [ -f "$g" ] && available+=("$g"); done

if [ ${#available[@]} -ge 2 ]; then
    echo -e "${GREEN}🎬 hero-combined${NC}"
    # Build concat list
    : > "$GIFS/_concat.txt"
    for g in "${available[@]}"; do echo "file '$(basename "$g")'" >> "$GIFS/_concat.txt"; done

    (cd "$GIFS" && ffmpeg -y -f concat -safe 0 -i _concat.txt \
        -vf "fps=20,split[s0][s1];[s0]palettegen=max_colors=192:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5" \
        -loop 0 hero-combined.gif 2>/dev/null)
    rm -f "$GIFS/_concat.txt"
    size=$(du -h "$GIFS/hero-combined.gif" | cut -f1)
    echo -e "${GREEN}   ✅ hero-combined.gif ($size)${NC}"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}🎉 Done:${NC}"
ls -lh "$GIFS"/*.gif 2>/dev/null
