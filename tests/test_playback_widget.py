"""
Tests for PlaybackWidget core functionality.

Covers:
- Basic playback operations (load, play, pause, stop, seek)
- File path edge cases and error handling
- EOF detection logic and edge cases
- State management and consistency
- Resource cleanup
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from conftest import fake_player_of
from textual.app import App
from textual.widget import Widget

from beetsplug.quicktag.widgets.playback import (
    PlaybackEnded,
    PlaybackStateChanged,
    PlaybackWidget,
)


class _TestApp(App):
    """Simple test app for providing Textual context to widgets."""

    def __init__(self, widget: Widget):
        super().__init__()
        self.test_widget = widget

    def compose(self):
        yield self.test_widget


@pytest.fixture
async def app_with_widget():
    """Create a test app with proper Textual context for widget testing."""
    widget = PlaybackWidget()
    app = _TestApp(widget)
    async with app.run_test() as pilot:
        yield widget, pilot


@pytest.fixture
def playback_widget():
    """Create a PlaybackWidget with mocked logging."""
    with patch.object(PlaybackWidget, "log", Mock()):
        yield PlaybackWidget()


class TestPlaybackWidgetBasicOperations:
    """Test basic playback operations."""

    def test_widget_initialization(self, playback_widget):
        """Test PlaybackWidget initializes correctly."""
        widget = playback_widget
        assert widget._current_path is None
        assert widget._eof_check_timer is None

    def test_widget_initialization_failure(self):
        """Test PlaybackWidget handles initialization failure gracefully."""
        with patch("beetsplug.quicktag.widgets.playback.Playback") as mock_playback:
            mock_playback.side_effect = Exception("Playback init failed")
            with patch.object(PlaybackWidget, "log", Mock()):
                widget = PlaybackWidget()
                assert widget.player is None

    @pytest.mark.real_audio
    def test_load_track_valid_file(self, playback_widget, mp3_files: dict[str, Path]):
        """Test loading a valid MP3 file into the real backend."""
        widget = playback_widget
        if widget.player is None:
            pytest.skip("no audio device")

        file_path = str(mp3_files["short"])
        widget.load_track(file_path)
        assert widget._current_path == file_path

    def test_load_track_nonexistent_file(self, playback_widget, nonexistent_file: Path):
        """Test loading a non-existent file handles error gracefully."""
        widget = playback_widget
        # Should not raise exception
        widget.load_track(str(nonexistent_file))
        # Path should not be set if load failed
        assert widget._current_path is None

    def test_load_track_none_path(self, playback_widget):
        """Test loading with None path."""
        widget = playback_widget
        widget.load_track(None)
        assert widget._current_path is None

    def test_load_track_empty_path(self, playback_widget):
        """Test loading with empty path."""
        widget = playback_widget
        widget.load_track("")
        assert widget._current_path is None

    @pytest.mark.real_audio
    def test_load_track_unicode_path(self, playback_widget, unicode_filename: Path):
        """The real backend must accept unicode characters in the path."""
        widget = playback_widget
        if widget.player is None:
            pytest.skip("no audio device")

        file_path = str(unicode_filename)
        widget.load_track(file_path)
        # Should handle unicode paths correctly
        assert widget._current_path == file_path

    def test_load_same_track_twice(self, playback_widget, mp3_files: dict[str, Path]):
        """Test loading the same track twice doesn't reload."""
        widget = playback_widget
        file_path = str(mp3_files["short"])
        widget.load_track(file_path)

        # Mock the player to verify load_file isn't called again
        with patch.object(widget.player, "load_file") as mock_load:
            widget.load_track(file_path)
            mock_load.assert_not_called()

    def test_play_without_loaded_track(self, playback_widget):
        """Test play() when no track is loaded."""
        widget = playback_widget
        # Should not raise exception
        widget.play()

    def test_play_without_player(self, playback_widget):
        """Test play() when player is None."""
        widget = playback_widget
        widget.player = None

        # Should not raise exception
        widget.play()

    def test_pause_without_player(self, playback_widget):
        """Test pause() when player is None."""
        widget = playback_widget
        widget.player = None

        # Should not raise exception
        widget.pause()

    def test_play_pause_toggle(self, playback_widget, mp3_files: dict[str, Path]):
        """Test play_pause() toggles between play and pause."""
        widget = playback_widget
        file_path = str(mp3_files["short"])
        widget.load_track(file_path)

        # Mock player states
        with patch.object(widget, "is_playing", side_effect=[False, True, False]):
            with patch.object(widget, "play") as mock_play:
                with patch.object(widget, "pause") as mock_pause:
                    widget.play_pause()  # Should call play
                    mock_play.assert_called_once()

                    widget.play_pause()  # Should call pause
                    mock_pause.assert_called_once()

    def test_stop_functionality(self, playback_widget, mp3_files: dict[str, Path]):
        """Test stop() functionality."""
        widget = playback_widget
        file_path = str(mp3_files["short"])
        widget.load_track(file_path)

        with patch.object(widget.player, "stop") as mock_stop:
            widget.stop()
            mock_stop.assert_called_once()
            assert widget._current_path is None


class TestPlaybackWidgetSeekOperations:
    """Test seek functionality."""

    def test_seek_relative_forward(self, playback_widget):
        """Test seeking forward in track."""
        widget = playback_widget

        mock_player = fake_player_of(widget)
        mock_player.duration = 30.0
        mock_player.curr_pos = 10.0

        widget.seek_relative(5)
        mock_player.seek.assert_called_once_with(15.0)

    def test_seek_relative_backward(self, playback_widget):
        """Test seeking backward in track."""
        widget = playback_widget

        mock_player = fake_player_of(widget)
        mock_player.duration = 30.0
        mock_player.curr_pos = 10.0

        widget.seek_relative(-5)
        mock_player.seek.assert_called_once_with(5.0)

    def test_seek_beyond_bounds(self, playback_widget):
        """Test seeking beyond track boundaries."""
        widget = playback_widget

        mock_player = fake_player_of(widget)
        mock_player.duration = 5.0
        mock_player.curr_pos = 2.0

        # Seek beyond end
        widget.seek_relative(10)
        mock_player.seek.assert_called_once_with(5.0)  # Should clamp to duration

        mock_player.seek.reset_mock()

        # Seek before beginning
        widget.seek_relative(-10)
        mock_player.seek.assert_called_once_with(0.0)  # Should clamp to 0

    def test_seek_without_player(self, playback_widget):
        """Test seek when player is None."""
        widget = playback_widget
        widget.player = None

        # Should not raise exception
        widget.seek_relative(5)

    def test_seek_without_duration(self, playback_widget):
        """Test seek when duration is not available."""
        widget = playback_widget

        # Mock player without duration
        mock_player = fake_player_of(widget)
        mock_player.duration = None

        widget.seek_relative(5)
        mock_player.seek.assert_not_called()


class TestPlaybackWidgetEOFDetection:
    """Test end-of-file detection logic."""

    def test_eof_check_conditions(self, playback_widget):
        """EOF is the transition from playing to inactive (curr_pos is 0 then)."""
        widget = playback_widget

        mock_player = fake_player_of(widget)
        mock_player.duration = 5.0
        mock_player.curr_pos = 2.0
        mock_player.active = True
        mock_player.playing = True
        widget._current_path = "test.mp3"

        with patch.object(widget, "post_message") as mock_post:
            widget._check_eof()  # observes playing
            mock_post.assert_not_called()

            mock_player.active = False
            mock_player.playing = False
            mock_player.curr_pos = 0.0
            widget._check_eof()
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert isinstance(args[0], PlaybackEnded)

    def test_eof_check_not_at_end(self, playback_widget):
        """An inactive player that was never observed playing is not EOF."""
        widget = playback_widget

        mock_player = fake_player_of(widget)
        mock_player.duration = 5.0
        mock_player.curr_pos = 0.0
        mock_player.active = False
        mock_player.playing = False
        widget._current_path = "test.mp3"

        with patch.object(widget, "post_message") as mock_post:
            widget._check_eof()
            mock_post.assert_not_called()

    def test_eof_check_still_active(self, playback_widget):
        """Test EOF detection when player is still active."""
        widget = playback_widget

        # Mock player state - still active
        mock_player = fake_player_of(widget)
        mock_player.duration = 5.0
        mock_player.curr_pos = 4.6  # Near end
        mock_player.active = True  # Still active
        widget._current_path = "test.mp3"

        with patch.object(widget, "post_message") as mock_post:
            widget._check_eof()
            mock_post.assert_not_called()

    def test_eof_check_no_current_path(self, playback_widget):
        """Test EOF detection when no track is loaded."""
        widget = playback_widget

        # Mock player state - no current path
        mock_player = fake_player_of(widget)
        mock_player.duration = 5.0
        mock_player.curr_pos = 4.6
        mock_player.active = False
        widget._current_path = None

        with patch.object(widget, "post_message") as mock_post:
            widget._check_eof()
            mock_post.assert_not_called()

    def test_eof_check_posts_only_once(self, playback_widget):
        """Repeated polls after the end must not post again."""
        widget = playback_widget

        mock_player = fake_player_of(widget)
        mock_player.active = True
        mock_player.playing = True
        widget._current_path = "test.mp3"

        with patch.object(widget, "post_message") as mock_post:
            widget._check_eof()
            mock_player.active = False
            mock_player.playing = False
            widget._check_eof()
            widget._check_eof()
            widget._check_eof()
            mock_post.assert_called_once()


class TestPlaybackWidgetStateManagement:
    """Test state management and consistency."""

    def test_is_playing_with_player(self, playback_widget):
        """Test is_playing() with active player."""
        widget = playback_widget

        # Mock playing state
        mock_player = fake_player_of(widget)
        mock_player.playing = True
        assert widget.is_playing() is True

        mock_player.playing = False
        assert widget.is_playing() is False

    def test_is_playing_without_player(self, playback_widget):
        """Test is_playing() when player is None."""
        widget = playback_widget
        widget.player = None
        assert widget.is_playing() is False

    def test_is_player_active_with_player(self, playback_widget):
        """Test is_player_active() with active player."""
        widget = playback_widget

        # Mock active state
        mock_player = fake_player_of(widget)
        mock_player.active = True
        assert widget.is_player_active() is True

        mock_player.active = False
        assert widget.is_player_active() is False

    def test_is_player_active_without_player(self, playback_widget):
        """Test is_player_active() when player is None."""
        widget = playback_widget
        widget.player = None
        assert widget.is_player_active() is False


class TestPlaybackWidgetResourceCleanup:
    """Test resource cleanup and lifecycle management."""

    @pytest.mark.asyncio
    async def test_terminate_player(self, playback_widget):
        """Test player termination and cleanup."""
        widget = playback_widget
        # Set up state
        widget._current_path = "test.mp3"
        widget._eof_check_timer = Mock()

        with patch.object(widget.player, "stop") as mock_stop:
            await widget._terminate_player()

            # Verify cleanup
            mock_stop.assert_called_once()
            assert widget.player is None
            assert widget._current_path is None
            assert widget._eof_check_timer is None

    @pytest.mark.asyncio
    async def test_terminate_player_with_exception(self, playback_widget):
        """Test player termination when stop() raises exception."""
        widget = playback_widget
        # Set up state
        widget._current_path = "test.mp3"

        with patch.object(widget.player, "stop", side_effect=Exception("Stop failed")):
            # Should not raise exception
            await widget._terminate_player()

            # Should still clean up
            assert widget.player is None
            assert widget._current_path is None

    @pytest.mark.asyncio
    async def test_on_unmount_cleanup(self, playback_widget):
        """Test cleanup on widget unmount."""
        widget = playback_widget

        with patch.object(widget, "_terminate_player") as mock_terminate:
            await widget.on_unmount()
            mock_terminate.assert_called_once()


class TestPlaybackWidgetMockScenarios:
    """Test scenarios using mocked components for edge cases."""

    def test_player_exceptions_during_operations(self, playback_widget):
        """Test handling of player exceptions during various operations."""
        widget = playback_widget
        player = fake_player_of(widget)
        widget._current_path = "test.mp3"

        # Test play with exception
        player.play.side_effect = Exception("Play failed")
        player.playing = False
        player.paused = False
        widget.play()  # Should not raise

        # Test pause with exception
        player.pause.side_effect = Exception("Pause failed")
        player.paused = False
        widget.pause()  # Should not raise

        # Test seek with exception
        player.seek.side_effect = Exception("Seek failed")
        player.duration = 10.0
        player.curr_pos = 5.0
        widget.seek_relative(2)  # Should not raise

    def test_rapid_state_changes(self, playback_widget):
        """Test rapid play/pause/stop operations."""
        widget = playback_widget
        player = fake_player_of(widget)
        widget._current_path = "test.mp3"

        # Simulate rapid state changes
        player.playing = False
        player.paused = False

        for _ in range(10):
            widget.play_pause()
            # Toggle playing state
            player.playing = not player.playing

        # Should handle rapid changes without issues
        assert player.play.call_count + player.pause.call_count > 0


class TestPlaybackWidgetWithoutAudioBackend:
    """Bug 8: a failed ``Playback()`` must not break compose()."""

    def test_progress_widget_is_built_even_when_player_init_fails(self) -> None:
        """The progress child is needed by compose() whether or not audio works."""
        with patch("beetsplug.quicktag.widgets.playback.Playback") as mock_playback:
            mock_playback.side_effect = Exception("no audio device")
            with patch.object(PlaybackWidget, "log", Mock()):
                widget = PlaybackWidget()

        assert widget.player is None
        assert widget._playback_progress is not None
        assert widget._playback_progress.player is None

    @pytest.mark.asyncio
    async def test_mounts_without_audio_backend(self) -> None:
        """Mounting the widget must not raise when there is no player."""
        with patch("beetsplug.quicktag.widgets.playback.Playback") as mock_playback:
            mock_playback.side_effect = Exception("no audio device")
            widget = PlaybackWidget()

        app = _TestApp(widget)
        async with app.run_test():
            assert widget.is_mounted


@pytest.fixture
def fake_player_widget(playback_widget: PlaybackWidget) -> PlaybackWidget:
    """A PlaybackWidget driving the conftest fake player.

    The fake tracks its own stream state, so ``load_file`` raising before the
    previous stream is stopped (bug 6) is observable through ``is_playing()``.
    """
    return playback_widget


class TestPlaybackWidgetMissingFile:
    """Bug 6: a missing file must not leave the previous track playing."""

    @staticmethod
    def _start_playing(widget: PlaybackWidget, path: str) -> None:
        widget.load_track(path)
        widget.play()
        assert widget.is_playing()

    def test_missing_file_stops_playback_and_notifies(
        self,
        fake_player_widget: PlaybackWidget,
        mp3_files: dict[str, Path],
        nonexistent_file: Path,
    ):
        widget = fake_player_widget
        player = fake_player_of(widget)
        self._start_playing(widget, str(mp3_files["short"]))

        with patch.object(PlaybackWidget, "notify") as mock_notify:
            widget.load_track(str(nonexistent_file))

        player.stop.assert_called_once()
        assert widget._current_path is None
        assert widget.is_playing() is False
        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs["severity"] == "error"

    def test_load_failure_stops_playback_and_notifies(
        self, fake_player_widget: PlaybackWidget, mp3_files: dict[str, Path]
    ):
        """A file that exists but cannot be decoded gets the same treatment."""
        widget = fake_player_widget
        player = fake_player_of(widget)
        self._start_playing(widget, str(mp3_files["short"]))
        other = str(mp3_files["long"])
        player.load_file.side_effect = RuntimeError("bad audio")

        with patch.object(PlaybackWidget, "notify") as mock_notify:
            widget.load_track(other)

        player.stop.assert_called_once()
        assert widget._current_path is None
        assert widget.is_playing() is False
        mock_notify.assert_called_once()

    def test_unmounted_widget_does_not_raise_when_notifying(
        self, fake_player_widget: PlaybackWidget, nonexistent_file: Path
    ):
        """Unit tests (and startup) use unmounted widgets; notify must be safe."""
        fake_player_widget.load_track(str(nonexistent_file))  # must not raise

        assert fake_player_widget._current_path is None


def _state_changes(mock_post: Mock) -> list[bool]:
    """Return the `playing` flags of every PlaybackStateChanged posted."""
    return [
        call.args[0].playing
        for call in mock_post.call_args_list
        if isinstance(call.args[0], PlaybackStateChanged)
    ]


class TestPlaybackStateChangedMessages:
    """PlaybackStateChanged is posted exactly when the playing state flips."""

    @pytest.fixture
    def widget(self, playback_widget: PlaybackWidget) -> PlaybackWidget:
        """A widget with the (stopped) fake player and a loaded track."""
        playback_widget._current_path = "test.mp3"
        return playback_widget

    def test_play_from_stopped_posts_playing(self, widget: PlaybackWidget) -> None:
        with patch.object(widget, "post_message") as mock_post:
            widget.play()
        assert _state_changes(mock_post) == [True]

    def test_play_while_playing_posts_nothing(self, widget: PlaybackWidget) -> None:
        player = fake_player_of(widget)
        with patch.object(widget, "post_message") as mock_post:
            widget.play()
            player.playing = True
            widget.play()
        assert _state_changes(mock_post) == [True]

    def test_pause_posts_not_playing(self, widget: PlaybackWidget) -> None:
        player = fake_player_of(widget)
        with patch.object(widget, "post_message") as mock_post:
            widget.play()
            player.playing = True
            player.active = True
            widget.pause()
        assert _state_changes(mock_post) == [True, False]

    def test_stop_posts_not_playing(self, widget: PlaybackWidget) -> None:
        with patch.object(widget, "post_message") as mock_post:
            widget.play()
            widget.stop()
        assert _state_changes(mock_post) == [True, False]

    def test_stop_while_stopped_posts_nothing(self, widget: PlaybackWidget) -> None:
        with patch.object(widget, "post_message") as mock_post:
            widget.stop()
        assert _state_changes(mock_post) == []

    def test_eof_posts_not_playing(self, widget: PlaybackWidget) -> None:
        player = fake_player_of(widget)
        with patch.object(widget, "post_message") as mock_post:
            widget.play()
            player.playing = True
            player.active = True
            widget._check_eof()
            player.playing = False
            player.active = False
            widget._check_eof()
        assert _state_changes(mock_post) == [True, False]

    def test_loading_another_track_posts_not_playing(
        self, widget: PlaybackWidget, mp3_files: dict[str, Path]
    ) -> None:
        """load_file() silently stops the current stream, so report the stop."""
        with patch.object(widget, "post_message") as mock_post:
            widget.play()
            widget.load_track(str(mp3_files["short"]))
        assert _state_changes(mock_post) == [True, False]

    def test_failed_load_posts_not_playing(
        self, widget: PlaybackWidget, nonexistent_file: Path
    ) -> None:
        with patch.object(widget, "post_message") as mock_post:
            widget.play()
            widget.load_track(str(nonexistent_file))
        assert _state_changes(mock_post) == [True, False]
