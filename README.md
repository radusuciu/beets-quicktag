# Beets QuickTag Plugin

[![CI](https://github.com/radusuciu/beets-quicktag/workflows/CI/badge.svg)](https://github.com/radusuciu/beets-quicktag/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/beets-quicktag.svg)](https://badge.fury.io/py/beets-quicktag)
[![Python versions](https://img.shields.io/pypi/pyversions/beets-quicktag.svg)](https://pypi.org/project/beets-quicktag/)

A [beets](https://beets.io/) plugin for tagging tracks with your own categories, as fast as possible. I wrote it to sort my library for DJing. Until 1.0 it may not be stable for others, but I'll still look at issues if you find it (hi!).

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
| `Escape` | Quit |
| Media keys | Play/pause, stop, next and previous track (see below) |

The footer shows the keys that apply to the focused widget. While the comments field has focus, `Left` and `Right` move the text cursor, and `/`, `<` and `>` are typed into the comment, so the footer drops those entries. Press `Tab` to leave the field first.

Hardware media keys (play/pause, stop, next track, previous track) work when the terminal passes them through with the kitty keyboard protocol. That includes Windows Terminal Preview 1.25 and later (the stable channel does not have it yet as of 1.24), kitty, WezTerm, Alacritty, and Ghostty. On desktops where the window manager grabs the media keys (for example GNOME or KDE) they do not reach the terminal, and the VS Code terminal keeps them for itself. Media keys work even while the comments field has focus, and are not listed in the footer. Stop pauses rather than unloading the track, so play resumes where it left off.

Tags are saved when you move to another track, and on quit if `autosave_on_quit` is on. Each category is stored in the beets database as a flexible attribute, with selected values joined by `, `. Audio files are not written to.

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

`categories` is required. Names may only contain letters, digits, underscores and hyphens, and cannot start with a digit or clash with a built-in beets field.

| Option | Default | Effect |
|---|---|---|
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
uv run ty check      # Type checking
```

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
