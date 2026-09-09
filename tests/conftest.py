"""
Pytest configuration and fixtures for beets-quicktag testing.

Provides fixtures for:
- Temporary beets libraries with test data
- Generated MP3 test files using ffmpeg
- Mock configurations for different scenarios
- A fake just_playback player for every test (see ``fake_playback``)
- Plain helpers shared by the TUI tests (``make_app``, ``header_text``, ...)
"""

import shutil
import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from beets.library import Item, Library
from just_playback import Playback
from mutagen.id3 import ID3, TALB, TIT2, TPE1
from textual.pilot import Pilot
from textual.widgets import Static

from beetsplug.quicktag.app import QuickTagApp
from beetsplug.quicktag.definitions import CategoryDefinitions
from beetsplug.quicktag.widgets.custom_selection_list import CustomSelectionList

# The only fixed list-valued field that works as a category. Older beets
# versions have a plain-text ``genre`` and no ``genres``.
LIST_FIELD = "genres"
needs_list_field = pytest.mark.skipif(
    not CategoryDefinitions.is_list_field(LIST_FIELD),
    reason="installed beets has no list-valued 'genres' field",
)


def make_app(
    lib: Library,
    mapping: dict[str, list[str]],
    definitions_path: Path | None = None,
    items: list[Item] | None = None,
    **settings: bool,
) -> QuickTagApp:
    """An app over ``lib`` with every playback automation off unless
    ``settings`` says otherwise."""
    flags: dict[str, bool] = {
        "autoplay_at_launch_enabled": False,
        "autoplay_on_track_change_enabled": False,
        "autonext_at_track_end_enabled": False,
        "autosave_on_quit_enabled": False,
        "keep_playing_on_track_change_if_playing_enabled": False,
    }
    flags.update(settings)
    return QuickTagApp(
        lib=lib,
        items=list(lib.items()) if items is None else items,
        definitions=CategoryDefinitions.from_config(mapping),
        definitions_path=definitions_path,
        **flags,
    )


def header_text(app: QuickTagApp) -> str:
    """The text the header line actually renders."""
    return app.query_one("#header_text_content", Static).render().plain


def prompts(selection_list: CustomSelectionList) -> list[str]:
    """The option labels of ``selection_list`` in display order."""
    return [
        str(selection_list.get_option_at_index(i).prompt)
        for i in range(selection_list.option_count)
    ]


async def settle(app: QuickTagApp, pilot: Pilot[None]) -> None:
    """Wait for work the app runs in worker threads, and for what follows it.

    A library count, a migration and the queue reload after it each run off
    the event loop, where ``pilot.pause`` cannot see them, and each one's
    continuation may start the next.
    """
    for _ in range(3):
        await app.workers.wait_for_complete()
        await pilot.pause()


def make_fake_player(
    *,
    active: bool = False,
    playing: bool = False,
    paused: bool = False,
    curr_pos: float = 0.0,
    duration: float = 5.0,
) -> Mock:
    """A stand-in for ``just_playback.Playback`` that never opens a device.

    It is a ``Mock`` so tests can assert on calls or install ``side_effect``
    overrides, but its methods also update ``active``/``playing``/``paused``/
    ``curr_pos`` the way the real player does, so widget code that reads state
    back after acting on it behaves as it would with real audio.
    """
    player = Mock(spec=Playback)
    player.active = active
    player.playing = playing
    player.paused = paused
    player.curr_pos = curr_pos
    player.duration = duration

    def load_file(path: str) -> None:
        player.active = False
        player.playing = False
        player.paused = False
        player.curr_pos = 0.0

    def play() -> None:
        player.active = True
        player.playing = True
        player.paused = False

    def pause() -> None:
        player.playing = False
        player.paused = True

    def resume() -> None:
        player.playing = True
        player.paused = False

    def stop() -> None:
        player.active = False
        player.playing = False
        player.paused = False
        player.curr_pos = 0.0

    def seek(position: float) -> None:
        player.curr_pos = position

    player.load_file.side_effect = load_file
    player.play.side_effect = play
    player.pause.side_effect = pause
    player.resume.side_effect = resume
    player.stop.side_effect = stop
    player.seek.side_effect = seek
    return player


@pytest.fixture(autouse=True)
def fake_playback(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Give every ``PlaybackWidget`` a fake player instead of a real device.

    Tests marked ``@pytest.mark.real_audio`` are left alone and construct the
    real ``just_playback.Playback``; they must skip when it is unavailable.
    """
    if request.node.get_closest_marker("real_audio") is not None:
        yield
        return
    with patch(
        "beetsplug.quicktag.widgets.playback.Playback",
        side_effect=lambda: make_fake_player(),
    ):
        yield


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


@pytest.fixture(scope="session")
def generated_mp3_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Encode the test MP3s once per session.

    The four sine waves come out byte-identical every time and cost about a
    third of a second to encode, so they are built once here and ``mp3_files``
    hands each test its own copies.
    """
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("ffmpeg not available - cannot generate test MP3 files")

    fixtures_dir = tmp_path_factory.mktemp("mp3_fixtures")

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
def mp3_files(temp_dir: Path, generated_mp3_files: dict[str, Path]) -> dict[str, Path]:
    """Per-test copies of the session's MP3s, free to be tagged or truncated."""
    fixtures_dir = temp_dir / "fixtures"
    fixtures_dir.mkdir()
    return {
        name: Path(shutil.copy(source, fixtures_dir / source.name))
        for name, source in generated_mp3_files.items()
    }


@pytest.fixture
def temp_beets_library(
    temp_dir: Path, mp3_files: dict[str, Path]
) -> Generator[Library, None, None]:
    """Create a temporary beets library with test MP3 files.

    The library is closed on teardown so its sqlite file can be deleted along
    with ``temp_dir``; Windows refuses to remove a file that is still open.
    """
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

    yield lib
    lib._close()


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
