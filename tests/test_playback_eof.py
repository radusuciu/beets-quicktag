"""
Tests for end-of-track detection and what the app does about it.

Background: just_playback reports ``active == False`` and ``curr_pos == 0`` once a
track has played to completion, so end-of-track has to be detected as a
transition ("was playing, now inactive") rather than from the position.
"""

import asyncio
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from beets.library import Item, Library
from textual.app import App, ComposeResult

from beetsplug.quicktag.app import NavigateDirection, QuickTagApp
from beetsplug.quicktag.widgets.playback import PlaybackEnded, PlaybackWidget


def _mock_player(*, active: bool, playing: bool, paused: bool = False) -> Mock:
    player = Mock()
    player.active = active
    player.playing = playing
    player.paused = paused
    player.duration = 5.0
    player.curr_pos = 0.0 if not active else 2.0
    return player


@pytest.fixture
def widget() -> Generator[PlaybackWidget, None, None]:
    with patch.object(PlaybackWidget, "log", Mock()):
        w = PlaybackWidget()
        w.player = _mock_player(active=False, playing=False)
        w._current_path = "test.mp3"
        yield w


class TestEofTransitionDetection:
    """_check_eof must fire exactly once when playback stops on its own."""

    def test_posts_once_when_playing_then_inactive(self, widget: PlaybackWidget):
        widget.player.active = True
        widget.player.playing = True
        with patch.object(widget, "post_message") as post:
            widget._check_eof()  # observes playing
            post.assert_not_called()

            widget.player.active = False
            widget.player.playing = False
            widget.player.curr_pos = 0.0  # what just_playback really reports
            widget._check_eof()
            post.assert_called_once()
            assert isinstance(post.call_args.args[0], PlaybackEnded)

            widget._check_eof()  # still inactive: must not post again
            post.assert_called_once()

    def test_no_post_when_never_played(self, widget: PlaybackWidget):
        with patch.object(widget, "post_message") as post:
            widget._check_eof()
            widget._check_eof()
            post.assert_not_called()

    def test_no_post_while_paused(self, widget: PlaybackWidget):
        widget.player.active = True
        widget.player.playing = True
        with patch.object(widget, "post_message") as post:
            widget._check_eof()
            widget.player.playing = False
            widget.player.paused = True  # paused: still active
            widget._check_eof()
            post.assert_not_called()

    def test_no_post_after_explicit_stop(self, widget: PlaybackWidget):
        widget.player.active = True
        widget.player.playing = True
        with patch.object(widget, "post_message") as post:
            widget._check_eof()
            widget.stop()
            widget.player.active = False
            widget.player.playing = False
            widget._check_eof()
            post.assert_not_called()

    def test_no_post_after_loading_new_track(self, widget: PlaybackWidget):
        widget.player.active = True
        widget.player.playing = True
        with patch.object(widget, "post_message") as post:
            widget._check_eof()
            widget.load_track("other.mp3")  # load_file kills active playback
            widget.player.active = False
            widget.player.playing = False
            widget._check_eof()
            post.assert_not_called()

    def test_play_arms_detection_before_first_poll(self, widget: PlaybackWidget):
        """A track shorter than the poll interval must still be detected."""
        with patch.object(widget, "post_message") as post:
            widget.play()  # player.play() called; track ends before next poll
            widget.player.active = False
            widget.player.playing = False
            widget._check_eof()
            post.assert_called_once()


class TestPlaybackGeneration:
    """Bug 7: an EOF message must say which playback it belongs to."""

    def test_check_eof_posts_the_current_generation(self, widget: PlaybackWidget):
        widget.player.active = True
        widget.player.playing = True
        with patch.object(widget, "post_message") as post:
            widget._check_eof()  # observes playing
            widget.player.active = False
            widget.player.playing = False
            widget._check_eof()

        message = post.call_args.args[0]
        assert message.generation == widget.playback_generation

    def test_generation_advances_on_load_and_on_play(
        self, widget: PlaybackWidget, mp3_files: dict[str, Path]
    ):
        start = widget.playback_generation

        widget.load_track(str(mp3_files["short"]))
        after_load = widget.playback_generation
        assert after_load > start

        widget.play()
        assert widget.playback_generation > after_load

    def test_generation_does_not_advance_on_a_failed_load(self, widget: PlaybackWidget):
        start = widget.playback_generation
        widget.load_track("/nonexistent/file.mp3")
        assert widget.playback_generation == start


class TestProgressDisplayIsToldAboutEof:
    """Bug 13: the widget tells the progress display; the display never polls."""

    def test_eof_marks_the_progress_display_as_ended(self, widget: PlaybackWidget):
        widget.player.active = True
        widget.player.playing = True
        with patch.object(widget._playback_progress, "mark_ended") as mark_ended:
            widget._check_eof()  # observes playing
            mark_ended.assert_not_called()

            widget.player.active = False
            widget.player.playing = False
            widget._check_eof()
            mark_ended.assert_called_once()

    def test_load_and_play_clear_the_ended_marker(
        self, widget: PlaybackWidget, mp3_files: dict[str, Path]
    ):
        with patch.object(widget._playback_progress, "clear_ended") as clear_ended:
            widget.load_track(str(mp3_files["short"]))
            assert clear_ended.call_count == 1

            widget.play()
            assert clear_ended.call_count == 2


class _WidgetApp(App):
    def __init__(self, widget: PlaybackWidget) -> None:
        super().__init__()
        self.widget = widget

    def compose(self) -> ComposeResult:
        yield self.widget


@pytest.mark.asyncio
async def test_real_file_end_posts_playback_ended(mp3_files: dict[str, Path]):
    """Real just_playback + real timer: a 0.5s file ends and posts once."""
    widget = PlaybackWidget()
    if widget.player is None:
        pytest.skip("no audio device")

    app = _WidgetApp(widget)
    async with app.run_test():
        with patch.object(widget, "post_message", wraps=widget.post_message) as post:
            widget.load_track(str(mp3_files["very_short"]))
            widget.play()
            await asyncio.sleep(2.0)
            ended = [
                c for c in post.call_args_list if isinstance(c.args[0], PlaybackEnded)
            ]
            assert len(ended) == 1


def _make_app(lib: Library, items: list[Item], **flags: bool) -> QuickTagApp:
    defaults: dict[str, bool] = {
        "autoplay_at_launch_enabled": False,
        "autoplay_on_track_change_enabled": False,
        "autonext_at_track_end_enabled": False,
        "autosave_on_quit_enabled": False,
        "keep_playing_on_track_change_if_playing_enabled": False,
    }
    defaults.update(flags)
    return QuickTagApp(
        lib=lib, items=items, categories=[("mood", ["a", "b"])], **defaults
    )


class TestAppHandlesPlaybackEnded:
    def test_handler_name_matches_textual_dispatch(self):
        assert hasattr(QuickTagApp, PlaybackEnded.handler_name)

    @pytest.mark.asyncio
    async def test_autonext_advances_and_plays(self, temp_beets_library: Library):
        items = list(temp_beets_library.items())
        app = _make_app(temp_beets_library, items, autonext_at_track_end_enabled=True)
        handler = getattr(app, PlaybackEnded.handler_name)

        with (
            patch.object(app, "_navigate", new_callable=AsyncMock) as navigate,
            patch.object(app.playback_widget, "play") as play,
        ):
            await handler(PlaybackEnded(app.playback_widget.playback_generation))
            navigate.assert_called_once()
            play.assert_called_once()

    @pytest.mark.asyncio
    async def test_autonext_off_does_nothing_and_does_not_raise(
        self, temp_beets_library: Library
    ):
        items = list(temp_beets_library.items())
        app = _make_app(temp_beets_library, items, autonext_at_track_end_enabled=False)
        handler = getattr(app, PlaybackEnded.handler_name)

        with patch.object(app, "_navigate", new_callable=AsyncMock) as navigate:
            await handler(PlaybackEnded(app.playback_widget.playback_generation))
            navigate.assert_not_called()

    @pytest.mark.asyncio
    async def test_autonext_at_last_item_stays(self, temp_beets_library: Library):
        items = list(temp_beets_library.items())
        app = _make_app(temp_beets_library, items, autonext_at_track_end_enabled=True)
        app.current_item_index = len(items) - 1
        handler = getattr(app, PlaybackEnded.handler_name)

        with (
            patch.object(
                app, "_navigate", new_callable=AsyncMock, return_value=False
            ) as navigate,
            patch.object(app.playback_widget, "play") as play,
        ):
            await handler(PlaybackEnded(app.playback_widget.playback_generation))
            # _navigate reports the end of the list; playback must not restart
            navigate.assert_called_once_with(NavigateDirection.FORWARD)
            play.assert_not_called()

    @pytest.mark.asyncio
    async def test_stale_generation_is_ignored(self, temp_beets_library: Library):
        """Right or `/` pressed inside the 0.5 s poll window must win."""
        items = list(temp_beets_library.items())
        app = _make_app(temp_beets_library, items, autonext_at_track_end_enabled=True)
        handler = getattr(app, PlaybackEnded.handler_name)
        generation = app.playback_widget.playback_generation

        with (
            patch.object(app, "_navigate", new_callable=AsyncMock) as navigate,
            patch.object(app.playback_widget, "play") as play,
        ):
            await handler(PlaybackEnded(generation - 1))
            navigate.assert_not_called()
            play.assert_not_called()

            await handler(PlaybackEnded(generation))
            navigate.assert_called_once_with(NavigateDirection.FORWARD)


class TestEndToEnd:
    """Headless runs of the real app with real audio files."""

    @staticmethod
    def _items_by_title(lib: Library) -> dict[str, Item]:
        return {i.title: i for i in lib.items()}

    @pytest.mark.asyncio
    async def test_track_end_autoadvances_and_keeps_playing(
        self, temp_beets_library: Library
    ):
        by_title = self._items_by_title(temp_beets_library)
        items = [by_title["Test Very Short"], by_title["Test Short"]]
        app = _make_app(temp_beets_library, items, autonext_at_track_end_enabled=True)
        if app.playback_widget.player is None:
            pytest.skip("no audio device")

        async with app.run_test():
            await app.action_play_pause_current_item()
            await asyncio.sleep(2.5)
            assert app.current_item_index == 1
            assert app.playback_widget.is_playing()

    @pytest.mark.asyncio
    async def test_autoplay_at_launch_starts_playback(
        self, temp_beets_library: Library
    ):
        by_title = self._items_by_title(temp_beets_library)
        items = [by_title["Test Short"]]
        app = _make_app(temp_beets_library, items, autoplay_at_launch_enabled=True)
        if app.playback_widget.player is None:
            pytest.skip("no audio device")

        async with app.run_test():
            await asyncio.sleep(0.5)
            assert app.playback_widget.is_playing()


class TestSeekRelativeIsSafe:
    def test_seek_relative_swallows_player_errors(self, widget: PlaybackWidget):
        widget.player.active = True
        widget.player.curr_pos = 2.0
        widget.player.seek.side_effect = RuntimeError("boom")
        widget.seek_relative(2)  # must not raise
