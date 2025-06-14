# Beets QuickTag Plugin

[![CI](https://github.com/radu/beets-quicktag/workflows/CI/badge.svg)](https://github.com/radu/beets-quicktag/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/beets-quicktag.svg)](https://badge.fury.io/py/beets-quicktag)
[![Python versions](https://img.shields.io/pypi/pyversions/beets-quicktag.svg)](https://pypi.org/project/beets-quicktag/)
[![codecov](https://codecov.io/gh/radu/beets-quicktag/branch/main/graph/badge.svg)](https://codecov.io/gh/radu/beets-quicktag)

This is a plugin for [beets](https://beets.io/) that scratches my own itch to categorize my music using custom tags, for DJing, as efficiently as possible. If it's not at a 1.0 release, it's probably not stable for use by others, though I'll still try and look at issues if for some reason you've found this (hi!).

It's a work in progress with core functionality implemented. Use the `beet quicktag` command to launch an interactive TUI for quick music tagging.

TODO:
- add tests
- add rating or energy level widget
- automate releases
- test on Windows
- summarize changes after QuickTag finishes running

## Requirements

- Python 3.11+
- beets 2.3.0+

## Installation

```bash
pip install beets-quicktag
```

Then add `quicktag` to your plugins list in your beets config:

```yaml
plugins: quicktag
```


## Configuration

Add a `quicktag` section to your beets `config.yaml`. Here's an example:

```yaml
quicktag:
  autoplay_at_launch: yes
  autoplay_on_track_change: no
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
```

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

### Release Process

This project uses automated releases via GitHub Actions. To create a new release:

1. **Update version** in `pyproject.toml`:
   ```toml
   version = "0.2.0"  # Update from current version
   ```

2. **Commit the version bump**:
   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to 0.2.0"
   ```

3. **Create and push a git tag**:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. **Automated release**: GitHub Actions will automatically:
   - Generate changelog using git-cliff and conventional commits
   - Build the package
   - Publish to PyPI
   - Create a GitHub release with release notes

### Commit Convention

Use [conventional commits](https://www.conventionalcommits.org/) for automatic changelog generation:
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `chore:` - Maintenance tasks
- `test:` - Test additions/changes

## Credits

This was inspired by the Quick Tag functionality in [One Tagger](https://onetagger.github.io/), which is an excellent application. One Tagger also has [a spreadsheet](https://docs.google.com/spreadsheets/d/1wYokScjoS5Xb1IvqFMXbSbknrXJ7bySLLihTucOS4qY/edit?gid=0#gid=0) that might provide inspiration from existing systems to categorize tracks in this way. I believe the One Tagger system, or at least the default categories it has, are inspired by [a reddit post by u/nonomomomo](https://www.reddit.com/r/DJs/comments/c3o2jk/my_ultimate_track_tagging_system_the_little_data/).