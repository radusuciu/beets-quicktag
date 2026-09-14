# Beets QuickTag Plugin

[![CI](https://github.com/radusuciu/beets-quicktag/workflows/CI/badge.svg)](https://github.com/radusuciu/beets-quicktag/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/beets-quicktag.svg)](https://badge.fury.io/py/beets-quicktag)
[![Python versions](https://img.shields.io/pypi/pyversions/beets-quicktag.svg)](https://pypi.org/project/beets-quicktag/)

A [beets](https://beets.io/) plugin for tagging tracks with your own categories, as fast as possible. I wrote it to sort my library for DJing. Until 1.0 it may not be stable for others, but I'll still look at issues if you find it (hi!).

![beet quicktag playing a track, tagging it from the keyboard, and adding a new value and an energy scale](https://raw.githubusercontent.com/radusuciu/beets-quicktag/main/assets/demo.gif)

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

This opens a TUI that plays each track and shows a checklist per category, plus a comments field. While a track plays, the terminal title shows its artist and title. A category can also be a scale (a rating or an energy level): one row of numbers, one of which is picked per track.

| Key | Action |
|---|---|
| `Left` / `Right` | Previous / next track |
| `/` | Play or pause |
| `<` / `>` | Seek 5 seconds back / forward |
| `Tab` / `Shift+Tab` | Move focus to the next / previous category list or the comments field |
| `Up` / `Down` | Move the highlight within a category list; raise / lower a scale value |
| `Space` / `Enter` | Toggle the highlighted value (lists) |
| Letter or digit | Jump to the next value in the list that starts with that character; on a scale, a digit picks that value |
| `+` | Add a value to the focused category (type it, `Enter` to add, `Escape` to cancel) |
| `F2` | Rename the highlighted value (edit it, `Enter` to apply, `Escape` to cancel) |
| `Delete` | Delete the highlighted value (lists); clear the value (scales, `Backspace` too) |
| `Ctrl+N` | Add a category (type its name, or `name: 1..5` for a scale; `Enter` to add, `Escape` to cancel) |
| `Ctrl+R` | Rename the focused category |
| `Ctrl+D` | Delete the focused category |
| `Escape` | Cancel an open input or `y/n` prompt, otherwise quit |
| Media keys | Play/pause, stop, next and previous track (see below) |

The footer shows the keys that apply to the focused widget. While the comments field has focus, `Left` and `Right` move the text cursor, and `/`, `<` and `>` are typed into the comment, so the footer drops those entries. Press `Tab` to leave the field first.

Hardware media keys (play/pause, stop, next track, previous track) work when the terminal passes them through with the kitty keyboard protocol. That includes Windows Terminal Preview 1.25 and later (the stable channel does not have it yet as of 1.24), kitty, WezTerm, Alacritty, and Ghostty. On desktops where the window manager grabs the media keys (for example GNOME or KDE) they do not reach the terminal, and the VS Code terminal keeps them for itself. Media keys work even while the comments field has focus, and are not listed in the footer. Stop pauses rather than unloading the track, so play resumes where it left off.

Tags are saved when you move to another track, and on quit if `autosave_on_quit` is on. Selected values are joined with `, ` and stored in the beets database only; audio files are not written to. A scale stores its number as text, for example `energy` = `4`, and clearing it removes the field. A category is stored as a flexible attribute unless its name is a built-in beets field: a list-valued field such as `genres` (beets 2.7+) is stored as a list, and a text field is stored as text. If a track already carries a value that is not in the category's list, the value is added to the list rather than dropped, except for a category that is a built-in text field, where the value is kept on the track but not added to the list. A value that differs from an existing option only by case selects that option instead, and its stored spelling is left alone until the track's selection changes. A scale whose track carries something that is not one of its numbers (say `high` from an older setup) shows it next to the row and leaves it alone until you pick a number or press `Delete`.

A new value typed with `+` is selected for the current track right away. A new category made with `Ctrl+N` starts empty; press `+` to give it values.

Renaming or deleting a value or a category also updates every track in the library that carries it, in the beets database only. A delete always asks first; a rename asks when at least one track is affected, and the prompt says how many. The count includes the current track's unsaved selection; pressing `y` saves the track before the library is updated. Answer `y` to go ahead or `n` (or `Escape`) to cancel. Renaming a value onto one that already exists merges the two (`Hiphop` into `Hip-Hop`, say), and the prompt says so. Renaming a category moves its values into the new field in that field's shape: renaming `genre` to `genres` on beets 2.7+ turns the comma-separated text into the list-valued built-in field. A category that is a built-in text field (for example `album`) cannot be renamed, and deleting it only removes it from the list: the field keeps its values on every track. If the database update fails nothing changes and the header says so.

## Configuration

Add a `quicktag` section to your beets `config.yaml`:

```yaml
quicktag:
  autoplay_at_launch: yes
  autoplay_on_track_change: no
  categories:
    energy: 1..5
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

Categories live in a YAML file, `quicktag_categories.yaml` next to your beets `config.yaml` by default. On the first run the file is created from the `categories` section above and a message says so; from then on the file is what counts and the `categories` section is ignored. The file has the same shape as the config section (name → list of values, or name → `low..high` for a scale) and can be edited by hand, or from the TUI with `+`, `F2`, `Delete`, `Ctrl+N`, `Ctrl+R` and `Ctrl+D`. Key order is display order, and so is value order unless `sort_options` is on. If the file cannot be parsed, `beet quicktag` stops and prints the path and the error rather than overwriting it.

Category names may only contain letters, digits, underscores and hyphens, cannot start with a digit, and cannot be `comments`. From the TUI a built-in beets field name is refused, except `genres`; a file or config that already names a built-in text field (for example `album`) is accepted with a warning at startup. Other list-valued fields such as `artists` and `albumtypes` are refused everywhere, because beets keeps them in step with companion fields. Names and values must be unique within their list ignoring case. Values cannot contain commas, and `genres` values cannot contain `; `, which beets uses to separate them. A scale is written `low..high` with `0 <= low < high <= 10`; its name must not be a built-in beets field, `genres` included. `Ctrl+N` adds a scale when the name is followed by its range, `energy: 1..5`; a scale can also be added by editing the file. Scales are typed as integers for beets, so `beet ls energy:4..5` and `beet ls -s energy-` work as numbers.

| Option | Default | Effect |
|---|---|---|
| `categories_file` | `quicktag_categories.yaml` | Where the category definitions are stored. A bare filename is placed next to `config.yaml`; an absolute path is used as is. |
| `autoplay_at_launch` | `no` | Start playing the first track when the app opens. |
| `autoplay_on_track_change` | `no` | Start playing whenever you move to another track. |
| `keep_playing_on_track_change_if_playing` | `yes` | If a track is playing when you move on, play the next one too. |
| `autonext_at_track_end` | `no` | Move to the next track when the current one finishes. |
| `autosave_on_quit` | `no` | Save the current track's tags on quit. |
| `keep_audio_device_awake` | `no` | Loop silence at zero volume so the audio device never suspends. Fixes choppy resume on some setups, such as WSLg. |
| `sort_options` | `no` | Show each category's values sorted, ignoring case, whatever order the file has them in. A value added or renamed from the TUI lands in its sorted place, and the file is written sorted the next time it is saved. Category order is left alone. |

## Development

### Common Tasks

Day-to-day commands are collected in a `justfile` and run with [just](https://github.com/casey/just). It is installed into the project's virtual environment as a dev dependency by `uv sync`, so activate the environment first (`source .venv/bin/activate`) or install `just` on your system with your package manager.

```bash
just            # list available recipes
just lint       # lint and check formatting (same as CI)
just fix        # fix lint errors and reformat
just typecheck  # type check with ty
just test       # run the test suite
just check      # lint, type check and test in one go
```

Anything after `just test` is passed straight to pytest, so `just test -k playback` runs only the playback tests. The tests run with `BEETSDIR` pointing at an empty temporary directory so your own beets config and library are never read or written.

If you prefer to skip `just`, the underlying commands are:

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
uv run ty check
```

### Re-recording the Demo

```bash
scripts/record-demo.sh
```

This builds a throwaway beets library of generated tone files in a scratch directory, drives `beet quicktag` against it inside [asciinema](https://asciinema.org/) in a tmux pane, and renders the recording to `assets/demo.gif` with [agg](https://github.com/asciinema/agg). It needs `uv`, `tmux`, `ffmpeg` and `curl`, and fetches agg into your cache directory on first use. Your own beets config and library are never touched. Pass `--gif-only` to re-render the existing `assets/demo.cast` without recording again.

### Release Process

Releases are automated with GitHub Actions and never need a local checkout:

1. Run the **Release PR** workflow from the Actions tab, or `just release` (`just release minor` to force a bump level). It picks the next version from the commits since the last tag (`feat` bumps minor, `fix` bumps patch; choose `patch`, `minor` or `major` in the dropdown to override), bumps `pyproject.toml` and `uv.lock` with `uv version`, regenerates `CHANGELOG.md` with git-cliff, and pushes a `release-vX.Y.Z` branch.
2. Open the pull request from the link in the run summary (with a `RELEASE_PR_TOKEN` repository secret holding a personal access token, the workflow opens it for you). Review the changelog and merge like any other PR.
3. On merge, the **Release** workflow sees that `pyproject.toml` names a version with no tag yet, builds the package, publishes it to PyPI via trusted publishing, and creates the `vX.Y.Z` tag and GitHub release with the changelog section as notes.

Every other push to `main` leaves the Release workflow as a no-op.

### Commit Convention

Use [conventional commits](https://www.conventionalcommits.org/) so the changelog can be generated:
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `chore:` - Maintenance tasks
- `test:` - Test additions/changes

## Credits

This was inspired by the Quick Tag functionality in [One Tagger](https://onetagger.github.io/), which is an excellent application. One Tagger also has [a spreadsheet](https://docs.google.com/spreadsheets/d/1wYokScjoS5Xb1IvqFMXbSbknrXJ7bySLLihTucOS4qY/edit?gid=0#gid=0) that might provide inspiration from existing systems to categorize tracks in this way. I believe the One Tagger system, or at least the default categories it has, are inspired by [a reddit post by u/nonomomomo](https://www.reddit.com/r/DJs/comments/c3o2jk/my_ultimate_track_tagging_system_the_little_data/).
