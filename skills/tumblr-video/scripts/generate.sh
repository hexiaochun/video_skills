#!/usr/bin/env bash
set -euo pipefail

# ── Paths ────────────────────────────────────────────────────
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
SCRIPT="$SCRIPTS_DIR/tumblr_video.py"
DEFAULT_BG="$SKILL_DIR/assets/minecraft-bg.mp4"
PYTHON="${PYTHON:-/opt/homebrew/bin/python3.11}"

# ── Dependency checks ────────────────────────────────────────
if [[ ! -f "$SCRIPT" ]]; then
  echo "ERROR: tumblr_video.py not found at $SCRIPTS_DIR" >&2; exit 1
fi
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
  [[ -z "$PYTHON" ]] && { echo "ERROR: Python not found" >&2; exit 1; }
fi
if ! command -v ffmpeg &>/dev/null; then
  echo "ERROR: ffmpeg not found. Install: brew install ffmpeg" >&2; exit 1
fi

# ── Parse args ───────────────────────────────────────────────
TEXT=""
INPUT_FILE=""
OUTPUT=""
HAS_OUTPUT=false
HAS_BG=false
GREEN_SCREEN=false
PASS_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--input)      INPUT_FILE="$2"; PASS_ARGS+=("$1" "$2"); shift 2 ;;
    -o|--output)     OUTPUT="$2"; HAS_OUTPUT=true; PASS_ARGS+=("$1" "$2"); shift 2 ;;
    --bg-video)      HAS_BG=true; PASS_ARGS+=("$1" "$2"); shift 2 ;;
    --green-screen)  GREEN_SCREEN=true; PASS_ARGS+=("$1"); shift ;;
    --voice|--work-dir) PASS_ARGS+=("$1" "$2"); shift 2 ;;
    --list-voices)   PASS_ARGS+=("$1"); shift ;;
    -*)              PASS_ARGS+=("$1"); shift ;;
    *)               [[ -z "$TEXT" ]] && TEXT="$1"; shift ;;
  esac
done

# ── Defaults ─────────────────────────────────────────────────
if [[ "$HAS_OUTPUT" == false ]]; then
  OUTPUT="/tmp/tumblr-$(date +%Y%m%d-%H%M%S).mp4"
  PASS_ARGS+=("-o" "$OUTPUT")
fi

if [[ "$GREEN_SCREEN" == false && "$HAS_BG" == false && -f "$DEFAULT_BG" ]]; then
  PASS_ARGS+=("--bg-video" "$DEFAULT_BG")
fi

# ── Input handling ───────────────────────────────────────────
if [[ -n "$INPUT_FILE" ]]; then
  :
elif [[ -n "$TEXT" ]]; then
  if [[ ${#TEXT} -gt 200 ]] || printf '%s' "$TEXT" | grep -q $'\n'; then
    TMPFILE="$(mktemp /tmp/tumblr-text-XXXXXX)"
    mv "$TMPFILE" "${TMPFILE}.txt"; TMPFILE="${TMPFILE}.txt"
    printf '%s' "$TEXT" > "$TMPFILE"
    PASS_ARGS=("-i" "$TMPFILE" "${PASS_ARGS[@]}")
  else
    PASS_ARGS=("$TEXT" "${PASS_ARGS[@]}")
  fi
else
  echo "ERROR: No text provided." >&2
  echo "Usage: generate.sh \"text\" [--voice NAME] [--green-screen] [-o PATH]" >&2
  exit 1
fi

# ── Run ──────────────────────────────────────────────────────
"$PYTHON" "$SCRIPT" "${PASS_ARGS[@]}"

# ── Summary ──────────────────────────────────────────────────
if [[ -f "$OUTPUT" ]]; then
  SIZE=$(du -h "$OUTPUT" | cut -f1 | xargs)
  DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$OUTPUT" 2>/dev/null | xargs printf "%.1f")
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  OUTPUT: $OUTPUT"
  echo "  DURATION: ${DURATION}s  |  SIZE: $SIZE"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  command -v open &>/dev/null && open "$OUTPUT"
fi
