"""
Pytest configuration and fixtures for beets-quicktag testing.

Provides fixtures for:
- Temporary beets libraries with test data
- Generated MP3 test files using ffmpeg
- Mock configurations for different scenarios
"""

import shutil
import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from beets.library import Library
from mutagen.id3 import ID3, TALB, TIT2, TPE1


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory that's cleaned up after the test."""
    with tempfile.TemporaryDirectory() as temp_path:
        yield Path(temp_path)


@pytest.fixture
def ffmpeg_available() -> bool:
    """Check if ffmpeg is available for MP3 generation."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


@pytest.fixture
def mp3_files(temp_dir: Path) -> dict[str, Path]:
    """Generate test MP3 files using ffmpeg."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("ffmpeg not available - cannot generate test MP3 files")

    fixtures_dir = temp_dir / "fixtures"
    fixtures_dir.mkdir()

    files = {}

    # Short valid MP3 (5 seconds, 440Hz sine wave)
    short_mp3 = fixtures_dir / "valid_short.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=5",
            "-c:a",
            "mp3",
            "-b:a",
            "128k",
            "-y",
            str(short_mp3),
        ],
        capture_output=True,
        check=True,
    )
    files["short"] = short_mp3

    # Long valid MP3 (30 seconds, 220Hz sine wave)
    long_mp3 = fixtures_dir / "valid_long.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=30",
            "-c:a",
            "mp3",
            "-b:a",
            "128k",
            "-y",
            str(long_mp3),
        ],
        capture_output=True,
        check=True,
    )
    files["long"] = long_mp3

    # Very short MP3 (0.5 seconds) for EOF edge cases
    very_short_mp3 = fixtures_dir / "very_short.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=0.5",
            "-c:a",
            "mp3",
            "-b:a",
            "128k",
            "-y",
            str(very_short_mp3),
        ],
        capture_output=True,
        check=True,
    )
    files["very_short"] = very_short_mp3

    # Different sample rate (48kHz)
    high_samplerate_mp3 = fixtures_dir / "high_samplerate.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=10",
            "-ar",
            "48000",
            "-c:a",
            "mp3",
            "-b:a",
            "128k",
            "-y",
            str(high_samplerate_mp3),
        ],
        capture_output=True,
        check=True,
    )
    files["high_samplerate"] = high_samplerate_mp3

    # Create corrupted MP3 by truncating a valid file
    corrupted_mp3 = fixtures_dir / "corrupted.mp3"
    shutil.copy(short_mp3, corrupted_mp3)
    with open(corrupted_mp3, "r+b") as f:
        f.seek(0, 2)  # Seek to end
        size = f.tell()
        f.truncate(size // 2)  # Truncate to half size
    files["corrupted"] = corrupted_mp3

    # Add ID3 metadata to files for beets compatibility
    metadata_configs = {
        "short": {
            "title": "Test Short Track",
            "artist": "Test Artist",
            "album": "Test Album",
        },
        "long": {
            "title": "Test Long Track",
            "artist": "Test Artist",
            "album": "Test Album",
        },
        "very_short": {
            "title": "Very Short Track",
            "artist": "Test Artist",
            "album": "Test Album",
        },
        "high_samplerate": {
            "title": "High Sample Rate Track",
            "artist": "Test Artist",
            "album": "Test Album",
        },
    }

    for file_key, metadata in metadata_configs.items():
        if file_key in files:
            try:
                audio_file = ID3(str(files[file_key]))
                audio_file.add(TIT2(encoding=3, text=metadata["title"]))
                audio_file.add(TPE1(encoding=3, text=metadata["artist"]))
                audio_file.add(TALB(encoding=3, text=metadata["album"]))
                audio_file.save()
            except Exception as e:
                # If metadata addition fails, continue - the file is still usable
                print(f"Warning: Could not add metadata to {file_key}: {e}")

    return files


@pytest.fixture
def temp_beets_library(temp_dir: Path, mp3_files: dict[str, Path]) -> Library:
    """Create a temporary beets library with test MP3 files."""
    library_db = temp_dir / "test_library.db"
    music_dir = temp_dir / "music"
    music_dir.mkdir()

    # Copy MP3 files to music directory
    copied_files = {}
    for name, path in mp3_files.items():
        if name != "corrupted":  # Don't add corrupted file to library
            dest = music_dir / f"{name}.mp3"
            shutil.copy(path, dest)
            copied_files[name] = dest

    # Create beets library
    lib = Library(str(library_db))

    # Import files into library
    for name, path in copied_files.items():
        try:
            # Create item manually with basic metadata
            from beets.library import Item

            item = Item(
                path=str(path),
                title=f"Test {name.replace('_', ' ').title()}",
                artist="Test Artist",
                album="Test Album",
            )
            lib.add(item)
            item.store()
        except Exception as e:
            print(f"Warning: Could not add {name} to beets library: {e}")

    return lib


@pytest.fixture
def mock_config() -> dict[str, Any]:
    """Provide mock configuration for quicktag plugin."""
    return {
        "autoplay_at_launch": False,
        "autoplay_on_track_change": False,
        "keep_playing_on_track_change_if_playing": True,
        "autonext_at_track_end": True,
        "autosave_on_quit": True,
        "categories": {
            "genre": ["Rock", "Pop", "Electronic"],
            "mood": ["Happy", "Sad", "Energetic"],
        },
    }


@pytest.fixture
def autoplay_configs() -> dict[str, dict[str, bool]]:
    """Provide various autoplay configuration combinations for testing."""
    return {
        "all_disabled": {
            "autoplay_at_launch": False,
            "autoplay_on_track_change": False,
            "keep_playing_on_track_change_if_playing": False,
            "autonext_at_track_end": False,
        },
        "all_enabled": {
            "autoplay_at_launch": True,
            "autoplay_on_track_change": True,
            "keep_playing_on_track_change_if_playing": True,
            "autonext_at_track_end": True,
        },
        "launch_only": {
            "autoplay_at_launch": True,
            "autoplay_on_track_change": False,
            "keep_playing_on_track_change_if_playing": False,
            "autonext_at_track_end": False,
        },
        "keep_playing": {
            "autoplay_at_launch": False,
            "autoplay_on_track_change": False,
            "keep_playing_on_track_change_if_playing": True,
            "autonext_at_track_end": False,
        },
        "auto_advance": {
            "autoplay_at_launch": False,
            "autoplay_on_track_change": False,
            "keep_playing_on_track_change_if_playing": False,
            "autonext_at_track_end": True,
        },
        "track_change_only": {
            "autoplay_at_launch": False,
            "autoplay_on_track_change": True,
            "keep_playing_on_track_change_if_playing": False,
            "autonext_at_track_end": False,
        },
    }


@pytest.fixture
def unicode_filename(temp_dir: Path, mp3_files: dict[str, Path]) -> Path:
    """Create a test file with unicode characters in the filename."""
    unicode_name = "test_unicode_🎵_файл.mp3"
    unicode_path = temp_dir / unicode_name
    shutil.copy(mp3_files["short"], unicode_path)
    return unicode_path


@pytest.fixture
def nonexistent_file(temp_dir: Path) -> Path:
    """Return path to a non-existent file for testing error handling."""
    return temp_dir / "does_not_exist.mp3"
