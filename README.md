# Beets QuickTag Plugin

[![CI](https://github.com/radusuciu/beets-quicktag/workflows/CI/badge.svg)](https://github.com/radusuciu/beets-quicktag/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/beets-quicktag.svg)](https://badge.fury.io/py/beets-quicktag)
[![Python versions](https://img.shields.io/pypi/pyversions/beets-quicktag.svg)](https://pypi.org/project/beets-quicktag/)

A [beets](https://beets.io/) plugin for tagging tracks with your own categories, as fast as possible. I wrote it to sort my library for DJing. Until 1.0 it may not be stable for others, but I'll still look at issues if you find it (hi!).

![beet quicktag playing a track and tagging it from the keyboard](https://raw.githubusercontent.com/radusuciu/beets-quicktag/main/assets/demo.gif)

## Requirements

- Python 3.11+
- beets 2.3.0+

## Installation

```bash
pip install beets-quicktag
```

Then enable the plugin in your beets config:

```yaml
plugins: quicktag
```

## Usage

```bash
beet quicktag [query]
```

`beet qt` also works. The query is a normal beets query and defaults to the whole library.

This opens a TUI that plays each track and shows a checklist per category, plus a comments field. While a track plays, the terminal title shows its artist and title.

| Key | Action |
|---|---|
| `Left` / `Right` | Previous / next track |
| `/` | Play or pause |
| `<` / `>` | Seek 5 seconds back / forward |
| `Tab` / `Shift+Tab` | Move focus to the next / previous category list or the comments field |
| `Up` / `Down` | Move the highlight within a category list |
| `Space` / `Enter` | Toggle the highlighted value |
| Letter or digit | Jump to the next value in the list that starts with that character |
| `+` | Add a value to the focused category (type it, `Enter` to add, `Escape` to cancel) |
| `Ctrl+N` | Add a category (type its name, `Enter` to add, `Escape` to cancel) |
| `Escape` | Cancel an open add-value / add-category input, otherwise quit |
| Media keys | Play/pause, stop, next and previous track (see below) |

The footer shows the keys that apply to the focused widget. While the comments field has focus, `Left` and `Right` move the text cursor, and `/`, `<` and `>` are typed into the comment, so the footer drops those entries. Press `Tab` to leave the field first.

Hardware media keys (play/pause, stop, next track, previous track) work when the terminal passes them through with the kitty keyboard protocol. That includes Windows Terminal Preview 1.25 and later (the stable channel does not have it yet as of 1.24), kitty, WezTerm, Alacritty, and Ghostty. On desktops where the window manager grabs the media keys (for example GNOME or KDE) they do not reach the terminal, and the VS Code terminal keeps them for itself. Media keys work even while the comments field has focus, and are not listed in the footer. Stop pauses rather than unloading the track, so play resumes where it left off.

Tags are saved when you move to another track, and on quit if `autosave_on_quit` is on. Selected values are joined with `, ` and stored in the beets database only; audio files are not written to. A category is stored as a flexible attribute unless its name is a built-in beets field: a list-valued field such as `genres` (beets 2.7+) is stored as a list, and a text field is stored as text. If a track already carries a value that is not in the category's list, the value is added to the list rather than dropped.

A new value typed with `+` is selected for the current track right away. A new category made with `Ctrl+N` starts empty; press `+` to give it values.

## Configuration

Add a `quicktag` section to your beets `config.yaml`:

```yaml
quicktag:
  autoplay_at_launch: yes
  autoplay_on_track_change: no
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
```

Categories live in a YAML file, `quicktag_categories.yaml` next to your beets `config.yaml` by default. On the first run the file is created from the `categories` section above and a message says so; from then on the file is what counts and the `categories` section is ignored. The file has the same shape as the config section (name → list of values) and can be edited by hand, or from the TUI with `+` and `Ctrl+N`. Key order is display order. If the file cannot be parsed, `beet quicktag` stops and prints the path and the error rather than overwriting it.

Category names may only contain letters, digits, underscores and hyphens, cannot start with a digit, and cannot be `comments`. From the TUI a built-in beets field name is refused, except list-valued ones such as `genres`; a file or config that already names a built-in text field (for example `album`) is accepted with a warning at startup. Values cannot contain commas.

| Option | Default | Effect |
|---|---|---|
| `categories_file` | `quicktag_categories.yaml` | Where the category definitions are stored. A bare filename is placed next to `config.yaml`; an absolute path is used as is. |
| `autoplay_at_launch` | `no` | Start playing the first track when the app opens. |
| `autoplay_on_track_change` | `no` | Start playing whenever you move to another track. |
| `keep_playing_on_track_change_if_playing` | `yes` | If a track is playing when you move on, play the next one too. |
| `autonext_at_track_end` | `no` | Move to the next track when the current one finishes. |
| `autosave_on_quit` | `no` | Save the current track's tags on quit. |
| `keep_audio_device_awake` | `no` | Loop silence at zero volume so the audio device never suspends. Fixes choppy resume on some setups, such as WSLg. |

## Development

### Running Tests

```bash
uv run pytest
```

### Code Quality

```bash
uv run ruff check .  # Linting
uv run ruff format . # Formatting
```

### Re-recording the Demo

```bash
scripts/record-demo.sh
```

This builds a throwaway beets library of generated tone files in a scratch directory, drives `beet quicktag` against it inside [asciinema](https://asciinema.org/) in a tmux pane, and renders the recording to `assets/demo.gif` with [agg](https://github.com/asciinema/agg). It needs `uv`, `tmux`, `ffmpeg` and `curl`, and fetches agg into your cache directory on first use. Your own beets config and library are never touched. Pass `--gif-only` to re-render the existing `assets/demo.cast` without recording again.

### Release Process

Releases are automated with GitHub Actions:

1. Bump `version` in `pyproject.toml` and commit it.
2. Tag and push:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
3. The workflow builds the package, publishes to PyPI, creates a GitHub release with notes from git-cliff, and commits the updated `CHANGELOG.md` to `main`. Pull before your next change.

### Commit Convention

Use [conventional commits](https://www.conventionalcommits.org/) so the changelog can be generated:
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `chore:` - Maintenance tasks
- `test:` - Test additions/changes

## Credits

This was inspired by the Quick Tag functionality in [One Tagger](https://onetagger.github.io/), which is an excellent application. One Tagger also has [a spreadsheet](https://docs.google.com/spreadsheets/d/1wYokScjoS5Xb1IvqFMXbSbknrXJ7bySLLihTucOS4qY/edit?gid=0#gid=0) that might provide inspiration from existing systems to categorize tracks in this way. I believe the One Tagger system, or at least the default categories it has, are inspired by [a reddit post by u/nonomomomo](https://www.reddit.com/r/DJs/comments/c3o2jk/my_ultimate_track_tagging_system_the_little_data/).
