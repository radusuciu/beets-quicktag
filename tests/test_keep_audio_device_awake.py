"""
Keeping the audio device awake with a silent, looping second stream.

On WSLg the PulseAudio RDP sink suspends about five seconds after the only
stream is paused, and resuming it then stalls audibly. When
``keep_audio_device_awake`` is on, ``PlaybackWidget`` keeps a muted looping
stream of silence running for its whole lifetime so the sink never idles.
"""

import wave
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from beets.library import Library
from textual.app import App, ComposeResult

from beetsplug.quicktag import QuickTagPlugin
from beetsplug.quicktag.app import QuickTagApp
from beetsplug.quicktag.widgets.playback import SILENCE_WAV, PlaybackWidget
from tests.conftest import make_fake_player

PLAYBACK = "beetsplug.quicktag.widgets.playback.Playback"


class _HostApp(App[None]):
    def __init__(self, widget: PlaybackWidget) -> None:
        super().__init__()
        self.widget = widget

    def compose(self) -> ComposeResult:
        yield self.widget


@pytest.fixture
def playback_class() -> Generator[Mock, None, None]:
    """Count ``Playback`` constructions; each one yields a fresh fake."""
    with patch(PLAYBACK, side_effect=lambda: make_fake_player()) as cls:
        yield cls


async def _mount(widget: PlaybackWidget) -> None:
    async with _HostApp(widget).run_test() as pilot:
        await pilot.pause()


class TestBundledSilence:
    def test_silence_file_is_a_short_wav_of_zero_samples(self) -> None:
        assert Path(SILENCE_WAV).is_file()
        with wave.open(str(SILENCE_WAV), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            duration = wav.getnframes() / wav.getframerate()
        assert 0.1 <= duration <= 2.0
        assert frames == b"\x00" * len(frames)


class TestKeepAliveDisabled:
    @pytest.mark.asyncio
    async def test_off_by_default_opens_only_the_main_player(
        self, playback_class: Mock
    ) -> None:
        widget = PlaybackWidget()
        await _mount(widget)
        assert playback_class.call_count == 1
        assert widget.keep_alive is None


class TestKeepAliveEnabled:
    @pytest.mark.asyncio
    async def test_mount_starts_a_muted_looping_silent_stream(
        self, playback_class: Mock
    ) -> None:
        widget = PlaybackWidget(keep_audio_device_awake=True)
        async with _HostApp(widget).run_test() as pilot:
            await pilot.pause()
            assert playback_class.call_count == 2
            keep_alive = widget.keep_alive
            assert keep_alive is not None
            assert keep_alive is not widget.player
            keep_alive.load_file.assert_called_once_with(str(SILENCE_WAV))
            keep_alive.set_volume.assert_called_once_with(0)
            keep_alive.loop_at_end.assert_called_once_with(True)
            assert keep_alive.playing is True

    @pytest.mark.asyncio
    async def test_unmount_stops_the_keep_alive(self, playback_class: Mock) -> None:
        widget = PlaybackWidget(keep_audio_device_awake=True)
        async with _HostApp(widget).run_test() as pilot:
            await pilot.pause()
            keep_alive = widget.keep_alive
            assert keep_alive is not None
        keep_alive.stop.assert_called_once_with()
        assert widget.keep_alive is None

    @pytest.mark.asyncio
    async def test_pausing_the_track_leaves_the_keep_alive_running(
        self, playback_class: Mock, mp3_files: dict[str, Path]
    ) -> None:
        widget = PlaybackWidget(keep_audio_device_awake=True)
        async with _HostApp(widget).run_test() as pilot:
            await pilot.pause()
            widget.load_track(str(mp3_files["short"]))
            widget.play()
            widget.pause()
            keep_alive = widget.keep_alive
            assert keep_alive is not None
            assert keep_alive.playing is True
            keep_alive.pause.assert_not_called()
            keep_alive.stop.assert_not_called()


class TestKeepAliveFailures:
    @pytest.mark.asyncio
    async def test_no_keep_alive_without_a_main_player(
        self, playback_class: Mock
    ) -> None:
        playback_class.side_effect = RuntimeError("no audio device")
        with patch.object(PlaybackWidget, "log", Mock()):
            widget = PlaybackWidget(keep_audio_device_awake=True)
        assert widget.player is None
        await _mount(widget)
        assert playback_class.call_count == 1
        assert widget.keep_alive is None

    @pytest.mark.asyncio
    async def test_keep_alive_construction_failure_keeps_main_player(
        self, playback_class: Mock
    ) -> None:
        main = make_fake_player()
        playback_class.side_effect = [main, RuntimeError("second device failed")]
        widget = PlaybackWidget(keep_audio_device_awake=True)
        async with _HostApp(widget).run_test() as pilot:
            await pilot.pause()
            assert widget.player is main
            assert widget.keep_alive is None

    @pytest.mark.asyncio
    async def test_keep_alive_load_failure_is_dropped_and_stopped(
        self, playback_class: Mock
    ) -> None:
        main = make_fake_player()
        broken = make_fake_player()
        broken.load_file.side_effect = OSError("cannot decode")
        playback_class.side_effect = [main, broken]
        widget = PlaybackWidget(keep_audio_device_awake=True)
        async with _HostApp(widget).run_test() as pilot:
            await pilot.pause()
            assert widget.player is main
            assert widget.keep_alive is None
            broken.play.assert_not_called()
            broken.stop.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_keep_alive_stop_failure_on_unmount_is_swallowed(
        self, playback_class: Mock
    ) -> None:
        widget = PlaybackWidget(keep_audio_device_awake=True)
        async with _HostApp(widget).run_test() as pilot:
            await pilot.pause()
            keep_alive = widget.keep_alive
            assert keep_alive is not None
            keep_alive.stop.side_effect = RuntimeError("device gone")
        assert widget.keep_alive is None


class TestAppPlumbing:
    def _make_app(
        self, lib: Library, mock_config: dict[str, Any], **flags: bool
    ) -> QuickTagApp:
        return QuickTagApp(
            lib=lib,
            items=list(lib.items()),
            categories=list(mock_config["categories"].items()),
            autoplay_on_track_change_enabled=False,
            autoplay_at_launch_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
            **flags,
        )

    def test_flag_defaults_to_off(
        self, temp_beets_library: Library, mock_config: dict[str, Any]
    ) -> None:
        app = self._make_app(temp_beets_library, mock_config)
        assert app.playback_widget.keep_audio_device_awake is False

    def test_flag_reaches_the_playback_widget(
        self, temp_beets_library: Library, mock_config: dict[str, Any]
    ) -> None:
        app = self._make_app(
            temp_beets_library, mock_config, keep_audio_device_awake_enabled=True
        )
        assert app.playback_widget.keep_audio_device_awake is True


class TestPluginConfig:
    def test_default_is_off(self) -> None:
        plugin = QuickTagPlugin()
        assert plugin.config["keep_audio_device_awake"].get(bool) is False
