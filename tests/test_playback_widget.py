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
from textual.app import App
from textual.widget import Widget

from beetsplug.quicktag.widgets.playback import PlaybackEnded, PlaybackWidget


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
        assert widget.player is not None
        assert widget._current_path is None
        assert widget._eof_check_timer is None

    def test_widget_initialization_failure(self):
        """Test PlaybackWidget handles initialization failure gracefully."""
        with patch("beetsplug.quicktag.widgets.playback.Playback") as mock_playback:
            mock_playback.side_effect = Exception("Playback init failed")
            with patch.object(PlaybackWidget, "log", Mock()):
                widget = PlaybackWidget()
                assert widget.player is None

    def test_load_track_valid_file(self, playback_widget, mp3_files: dict[str, Path]):
        """Test loading a valid MP3 file."""
        widget = playback_widget
        if widget.player is None:
            pytest.skip("just_playback not available")

        file_path = str(mp3_files["short"])
        widget.load_track(file_path)
        assert widget._current_path == file_path

    def test_load_track_nonexistent_file(self, playback_widget, nonexistent_file: Path):
        """Test loading a non-existent file handles error gracefully."""
        widget = playback_widget
        if widget.player is None:
            pytest.skip("just_playback not available")

        # Should not raise exception
        widget.load_track(str(nonexistent_file))
        # Path should not be set if load failed
        assert widget._current_path is None

    def test_load_track_none_path(self, playback_widget):
        """Test loading with None path."""
        widget = playback_widget
        if widget.player is None:
            pytest.skip("just_playback not available")

        widget.load_track(None)
        assert widget._current_path is None

    def test_load_track_empty_path(self, playback_widget):
        """Test loading with empty path."""
        widget = playback_widget
        if widget.player is None:
            pytest.skip("just_playback not available")

        widget.load_track("")
        assert widget._current_path is None

    def test_load_track_unicode_path(self, playback_widget, unicode_filename: Path):
        """Test loading file with unicode characters in path."""
        widget = playback_widget
        if widget.player is None:
            pytest.skip("just_playback not available")

        file_path = str(unicode_filename)
        widget.load_track(file_path)
        # Should handle unicode paths correctly
        assert widget._current_path == file_path

    def test_load_same_track_twice(self, playback_widget, mp3_files: dict[str, Path]):
        """Test loading the same track twice doesn't reload."""
        widget = playback_widget
        if widget.player is None:
            pytest.skip("just_playback not available")

        file_path = str(mp3_files["short"])
        widget.load_track(file_path)

        # Mock the player to verify load_file isn't called again
        with patch.object(widget.player, "load_file") as mock_load:
            widget.load_track(file_path)
            mock_load.assert_not_called()

    def test_play_without_loaded_track(self, playback_widget):
        """Test play() when no track is loaded."""
        widget = playback_widget
        if widget.player is None:
            pytest.skip("just_playback not available")

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
        if widget.player is None:
            pytest.skip("just_playback not available")

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
        if widget.player is None:
            pytest.skip("just_playback not available")

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

        # Mock the entire player for predictable behavior
        mock_player = Mock()
        mock_player.duration = 30.0
        mock_player.curr_pos = 10.0
        widget.player = mock_player

        widget.seek_relative(5)
        mock_player.seek.assert_called_once_with(15.0)

    def test_seek_relative_backward(self, playback_widget):
        """Test seeking backward in track."""
        widget = playback_widget

        # Mock the entire player for predictable behavior
        mock_player = Mock()
        mock_player.duration = 30.0
        mock_player.curr_pos = 10.0
        widget.player = mock_player

        widget.seek_relative(-5)
        mock_player.seek.assert_called_once_with(5.0)

    def test_seek_beyond_bounds(self, playback_widget):
        """Test seeking beyond track boundaries."""
        widget = playback_widget

        # Mock the entire player for predictable behavior
        mock_player = Mock()
        mock_player.duration = 5.0
        mock_player.curr_pos = 2.0
        widget.player = mock_player

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
        mock_player = Mock()
        mock_player.duration = None
        widget.player = mock_player

        widget.seek_relative(5)
        mock_player.seek.assert_not_called()


class TestPlaybackWidgetEOFDetection:
    """Test end-of-file detection logic."""

    def test_eof_check_conditions(self, playback_widget):
        """Test EOF detection conditions."""
        widget = playback_widget

        # Mock player state for EOF detection
        mock_player = Mock()
        mock_player.duration = 5.0
        mock_player.curr_pos = 4.6  # Near end
        mock_player.active = False
        widget.player = mock_player
        widget._current_path = "test.mp3"

        with patch.object(widget, "post_message") as mock_post:
            widget._check_eof()
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert isinstance(args[0], PlaybackEnded)

    def test_eof_check_not_at_end(self, playback_widget):
        """Test EOF detection when not at end of track."""
        widget = playback_widget

        # Mock player state - not at end
        mock_player = Mock()
        mock_player.duration = 5.0
        mock_player.curr_pos = 2.0  # Middle of track
        mock_player.active = False
        widget.player = mock_player
        widget._current_path = "test.mp3"

        with patch.object(widget, "post_message") as mock_post:
            widget._check_eof()
            mock_post.assert_not_called()

    def test_eof_check_still_active(self, playback_widget):
        """Test EOF detection when player is still active."""
        widget = playback_widget

        # Mock player state - still active
        mock_player = Mock()
        mock_player.duration = 5.0
        mock_player.curr_pos = 4.6  # Near end
        mock_player.active = True  # Still active
        widget.player = mock_player
        widget._current_path = "test.mp3"

        with patch.object(widget, "post_message") as mock_post:
            widget._check_eof()
            mock_post.assert_not_called()

    def test_eof_check_no_current_path(self, playback_widget):
        """Test EOF detection when no track is loaded."""
        widget = playback_widget

        # Mock player state - no current path
        mock_player = Mock()
        mock_player.duration = 5.0
        mock_player.curr_pos = 4.6
        mock_player.active = False
        widget.player = mock_player
        widget._current_path = None

        with patch.object(widget, "post_message") as mock_post:
            widget._check_eof()
            mock_post.assert_not_called()

    def test_eof_check_tolerance(self, playback_widget):
        """Test EOF detection tolerance (0.5 seconds)."""
        widget = playback_widget

        # Mock player state - exactly at tolerance boundary
        mock_player = Mock()
        mock_player.duration = 5.0
        mock_player.curr_pos = 4.5  # Exactly 0.5s before end
        mock_player.active = False
        widget.player = mock_player
        widget._current_path = "test.mp3"

        with patch.object(widget, "post_message") as mock_post:
            widget._check_eof()
            mock_post.assert_called_once()  # Should trigger EOF

    def test_eof_check_very_short_file(self, playback_widget):
        """Test EOF detection with very short file."""
        widget = playback_widget

        # Mock player state - very short file
        mock_player = Mock()
        mock_player.duration = 0.3  # Shorter than tolerance
        mock_player.curr_pos = 0.3
        mock_player.active = False
        widget.player = mock_player
        widget._current_path = "test.mp3"

        with patch.object(widget, "post_message") as mock_post:
            widget._check_eof()
            mock_post.assert_called_once()


class TestPlaybackWidgetStateManagement:
    """Test state management and consistency."""

    def test_is_playing_with_player(self, playback_widget):
        """Test is_playing() with active player."""
        widget = playback_widget

        # Mock playing state
        mock_player = Mock()
        mock_player.playing = True
        widget.player = mock_player
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
        mock_player = Mock()
        mock_player.active = True
        widget.player = mock_player
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
        if widget.player is None:
            pytest.skip("just_playback not available")

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
        if widget.player is None:
            pytest.skip("just_playback not available")

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
        widget.player = Mock()
        widget._current_path = "test.mp3"

        # Test play with exception
        widget.player.play.side_effect = Exception("Play failed")
        widget.player.playing = False
        widget.player.paused = False
        widget.play()  # Should not raise

        # Test pause with exception
        widget.player.pause.side_effect = Exception("Pause failed")
        widget.player.paused = False
        widget.pause()  # Should not raise

        # Test seek with exception
        widget.player.seek.side_effect = Exception("Seek failed")
        widget.player.duration = 10.0
        widget.player.curr_pos = 5.0
        widget.seek_relative(2)  # Should not raise

    def test_rapid_state_changes(self, playback_widget):
        """Test rapid play/pause/stop operations."""
        widget = playback_widget
        widget.player = Mock()
        widget._current_path = "test.mp3"

        # Simulate rapid state changes
        widget.player.playing = False
        widget.player.paused = False

        for _ in range(10):
            widget.play_pause()
            # Toggle playing state
            widget.player.playing = not widget.player.playing

        # Should handle rapid changes without issues
        assert widget.player.play.call_count + widget.player.pause.call_count > 0
