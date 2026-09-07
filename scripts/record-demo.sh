#!/usr/bin/env bash
# Record the README showcase: assets/demo.cast (asciinema) and assets/demo.gif.
#
# Builds a throwaway beets library of generated tone MP3s in a scratch directory,
# runs `beet quicktag` against it inside asciinema in a tmux pane, drives the keys
# on a timer, then renders the cast to a GIF with agg. It never reads or writes
# your own beets config or library: BEETSDIR points at the scratch directory.
#
# Usage: scripts/record-demo.sh [--gif-only]
#   --gif-only  skip recording and only re-render assets/demo.gif from the cast
#
# Needs: uv, tmux, ffmpeg, curl (to fetch agg once into $XDG_CACHE_HOME).
# asciinema runs through uvx. The GIF is silent; the tones exist only so the
# app has something to load, and they stay in the scratch directory.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH="${QT_DEMO_SCRATCH:-${TMPDIR:-/tmp}/quicktag-demo}"
CAST="$REPO/assets/demo.cast"
GIF="$REPO/assets/demo.gif"
SESSION="${QT_DEMO_SESSION:-quicktag-demo}"
COLS=100
ROWS=28
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/beets-quicktag"
AGG="$CACHE/agg"
AGG_VERSION="1.9.0"

need() { command -v "$1" >/dev/null || { echo "$1 is required" >&2; exit 1; }; }

fetch_agg() {
  [[ -x "$AGG" ]] && return
  local target
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) target="x86_64-unknown-linux-musl" ;;
    Linux-aarch64) target="aarch64-unknown-linux-gnu" ;;
    Darwin-arm64) target="aarch64-apple-darwin" ;;
    Darwin-x86_64) target="x86_64-apple-darwin" ;;
    *) echo "no prebuilt agg for $(uname -s)-$(uname -m); put one at $AGG" >&2; exit 1 ;;
  esac
  mkdir -p "$CACHE"
  echo "fetching agg $AGG_VERSION ($target) into $CACHE"
  curl -sSL -o "$AGG" \
    "https://github.com/asciinema/agg/releases/download/v$AGG_VERSION/agg-$target"
  chmod +x "$AGG"
}

# A tone MP3 per track, tagged so the header looks like a real library. Only
# the first two tracks appear in the demo. Lengths matter: the progress bar
# shows them.
make_library() {
  need ffmpeg
  rm -rf "$SCRATCH"
  mkdir -p "$SCRATCH/tracks" "$SCRATCH/lib"
  local i=0 spec artist title album seconds
  for spec in \
    "Darude|Sandstorm|Before the Storm|225" \
    "Disclosure|Apollo|Apollo|278" \
    "Daft Punk|Veridis Quo|Discovery|344"; do
    i=$((i + 1))
    IFS='|' read -r artist title album seconds <<<"$spec"
    ffmpeg -loglevel error -y -f lavfi -i "sine=frequency=$((220 + i * 110)):duration=$seconds" \
      -metadata artist="$artist" -metadata title="$title" -metadata album="$album" \
      -metadata track="$i" -c:a mp3 -b:a 48k "$SCRATCH/tracks/$(printf '%02d' "$i").mp3"
  done
  cat >"$SCRATCH/config.yaml" <<YAML
directory: $SCRATCH/lib
library: $SCRATCH/library.db
pluginpath: $REPO/beetsplug
plugins: [quicktag]
# Keep the tracks in the order above rather than beets' default artist sort.
sort_item: path+
import:
  copy: no
  autotag: no
  write: no
quicktag:
  autosave_on_quit: yes
  categories:
    collection:
      - DJ
      - Sample
    mood:
      - happy
      - sad
      - bright
      - dark
      - angry
    energy:
      - low
      - medium
      - high
YAML
  (cd "$REPO" && BEETSDIR="$SCRATCH" uv run beet import -s -q "$SCRATCH/tracks" >/dev/null)
  echo "scratch library: $(cd "$REPO" && BEETSDIR="$SCRATCH" uv run beet ls 2>/dev/null | wc -l) tracks in $SCRATCH"
}

# Keystrokes go through tmux into the pty asciinema is recording.
key() { tmux send-keys -t "$SESSION" "$@"; }
type_text() {
  local text="$1" i
  for ((i = 0; i < ${#text}; i++)); do
    key -l "${text:i:1}"
    sleep 0.07
  done
}
pause() { sleep "$1"; }

record() {
  need tmux
  need uv
  (cd "$REPO" && uv sync -q)
  mkdir -p "$(dirname "$CAST")"
  rm -f "$CAST"
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  # The recorded shell sees only the scratch config (BEETSDIR) and the project
  # venv on PATH, so a literal `beet quicktag` is what runs. No stderr
  # redirection: Textual draws on stderr.
  tmux new-session -d -s "$SESSION" -x "$COLS" -y "$ROWS" \
    "cd '$SCRATCH' && \
     BEETSDIR='$SCRATCH' PATH='$REPO/.venv/bin:$PATH' PS1='$ ' \
     uvx asciinema rec --overwrite --cols $COLS --rows $ROWS -t 'beet quicktag' \
       -c 'bash --norc --noprofile -i' '$CAST'"
  pause 2

  type_text "beet quicktag"; pause 0.6; key Enter
  pause 2.5                       # app up, first track loaded, collection list focused
  key /;               pause 2                   # play
  # Sandstorm. A letter jumps to the next value starting with it, wrapping, so
  # the letters below land on the same values no matter where the highlight is.
  key Space;           pause 1.2                 # collection: DJ is highlighted at launch
  key Tab;             pause 0.8                 # mood
  key h;    pause 0.4; key Space; pause 0.9      # happy
  key b;    pause 0.4; key Space; pause 1.2      # bright
  key Tab;             pause 0.8                 # energy
  key h;    pause 0.4; key Space; pause 1.2      # high
  key Tab;             pause 0.8                 # comments
  type_text "peak time, everyone knows the riff"; pause 1.5
  key Tab;             pause 0.6                 # leave the field so Right changes track
  # Apollo. Tags are saved on the way out; the lists come up empty, but each
  # keeps the row it had highlighted.
  key Right;           pause 2.5
  key Space;           pause 1.0                 # collection: DJ
  key Tab;  pause 0.6; key b; pause 0.4; key Space; pause 1.0   # mood: bright
  key Tab;  pause 0.6; key m; pause 0.4; key Space; pause 1.8   # energy: medium
  key Escape                                     # quit, autosave_on_quit
  pause 1.5
  type_text "exit"; key Enter
  # asciinema finalises the cast once the shell exits.
  local n=0
  while tmux has-session -t "$SESSION" 2>/dev/null && ((n < 100)); do sleep 0.1; n=$((n + 1)); done
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  [[ -s "$CAST" ]] || { echo "recording failed: $CAST is missing or empty" >&2; exit 1; }
  echo "recorded $CAST ($(wc -l <"$CAST") events)"
}

render() {
  fetch_agg
  "$AGG" --quiet --font-size 14 --idle-time-limit 3 --last-frame-duration 2 \
    --theme github-dark "$CAST" "$GIF"
  echo "rendered $GIF ($(du -h "$GIF" | cut -f1))"
}

if [[ "${1:-}" != "--gif-only" ]]; then
  make_library
  record
fi
render
