"""
The test suite must not open a real audio device unless a test asks for one.

``conftest.py`` swaps ``just_playback.Playback`` for a stateful fake in every
test; ``@pytest.mark.real_audio`` opts a test back in to the real backend.
"""

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest
from conftest import fake_player_of
from just_playback import Playback

from beetsplug.quicktag.widgets.playback import PlaybackWidget


@pytest.fixture
def widget() -> Generator[PlaybackWidget, None, None]:
    """An unmounted widget whose logging and message posting are stubbed."""
    with patch.object(PlaybackWidget, "log", Mock()):
        w = PlaybackWidget()
        with patch.object(w, "post_message"):
            yield w


@pytest.fixture
def player(widget: PlaybackWidget) -> Mock:
    """The fake player behind ``widget``."""
    return fake_player_of(widget)


class TestFakePlayerByDefault:
    def test_plain_widget_gets_a_mock_player(self, widget: PlaybackWidget):
        assert isinstance(widget.player, Mock)
        assert type(widget.player) is not Playback

    def test_fake_starts_stopped(self, widget: PlaybackWidget, player: Mock):
        assert widget.is_playing() is False
        assert widget.is_player_active() is False
        assert player.paused is False
        assert player.curr_pos == 0.0
        assert player.duration > 0

    def test_fake_tracks_play_pause_stop(self, widget: PlaybackWidget, player: Mock):
        widget._current_path = "test.mp3"

        widget.play()
        assert widget.is_playing() is True
        assert widget.is_player_active() is True

        widget.pause()
        assert widget.is_playing() is False
        assert widget.is_player_active() is True
        assert player.paused is True

        widget.play()  # resumes
        assert widget.is_playing() is True

        widget.stop()
        assert widget.is_player_active() is False

    def test_fake_seek_moves_position(self, widget: PlaybackWidget, player: Mock):
        player.curr_pos = 1.0
        widget.seek_relative(2)
        assert player.curr_pos == 3.0

    def test_fake_records_calls_like_a_mock(self, widget: PlaybackWidget, player: Mock):
        widget._current_path = "test.mp3"
        widget.play()
        player.play.assert_called_once()

    def test_local_patch_still_wins(self):
        with patch("beetsplug.quicktag.widgets.playback.Playback") as playback:
            playback.side_effect = RuntimeError("no audio device")
            with patch.object(PlaybackWidget, "log", Mock()):
                widget = PlaybackWidget()
        assert widget.player is None


@pytest.mark.real_audio
def test_real_audio_marker_constructs_a_real_player():
    with patch.object(PlaybackWidget, "log", Mock()):
        widget = PlaybackWidget()
    if widget.player is None:
        pytest.skip("no audio device")
    assert isinstance(widget.player, Playback)
    assert not isinstance(widget.player, Mock)
