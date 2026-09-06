"""
Integration tests for QuickTagApp with playback functionality.

Covers:
- Configuration scenarios (autoplay combinations)
- Track navigation with state preservation
- Error recovery and resource cleanup
- Full end-to-end playback workflows
- Message handling between components
"""

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from beets.library import Library
from textual.widgets import Input, Static

from beetsplug.quicktag.app import NavigateDirection, QuickTagApp
from beetsplug.quicktag.widgets.custom_selection_list import CustomSelectionList
from beetsplug.quicktag.widgets.input_with_label import InputWithLabel
from beetsplug.quicktag.widgets.playback import PlaybackEnded


def header_text(app: QuickTagApp) -> str:
    """Return the text the header Static actually renders."""
    return app.query_one("#header_text_content", Static).render().plain


class TestQuickTagAppPlaybackConfiguration:
    """Test various autoplay configuration scenarios."""

    @pytest.mark.asyncio
    async def test_autoplay_at_launch_enabled(
        self, temp_beets_library: Library, mock_config: dict[str, Any]
    ):
        """Test autoplay starts when app launches with autoplay_at_launch=True."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        config = mock_config.copy()
        config["autoplay_at_launch"] = True

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=list(config["categories"].items()),
            autoplay_at_launch_enabled=config["autoplay_at_launch"],
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        with patch.object(app.playback_widget, "play") as mock_play:
            async with app.run_test() as pilot:
                await pilot.pause()

            # Mounting the app must start playback when autoplay is enabled
            mock_play.assert_called_once()

    @pytest.mark.asyncio
    async def test_autoplay_at_launch_disabled(
        self, temp_beets_library: Library, mock_config: dict[str, Any]
    ):
        """Test autoplay pauses when app launches with autoplay_at_launch=False."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        config = mock_config.copy()
        config["autoplay_at_launch"] = False

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=list(config["categories"].items()),
            autoplay_at_launch_enabled=config["autoplay_at_launch"],
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        with patch.object(app.playback_widget, "play") as mock_play:
            async with app.run_test() as pilot:
                await pilot.pause()

            # Mounting the app must not start playback when autoplay is disabled
            mock_play.assert_not_called()

    @pytest.mark.asyncio
    async def test_autoplay_on_track_change_combinations(
        self, temp_beets_library: Library, autoplay_configs: dict[str, dict[str, bool]]
    ):
        """Test different autoplay_on_track_change combinations."""
        items = list(temp_beets_library.items())
        if len(items) < 2:
            pytest.skip("Need at least 2 items for track change test")

        for _config_name, config in autoplay_configs.items():
            app = QuickTagApp(
                lib=temp_beets_library,
                items=items,
                categories=[("genre", ["Rock", "Pop"])],
                autoplay_at_launch_enabled=config["autoplay_at_launch"],
                autoplay_on_track_change_enabled=config["autoplay_on_track_change"],
                autonext_at_track_end_enabled=config["autonext_at_track_end"],
                autosave_on_quit_enabled=False,
                keep_playing_on_track_change_if_playing_enabled=config[
                    "keep_playing_on_track_change_if_playing"
                ],
            )

            with patch.object(app, "_save_current_item_tags", new_callable=AsyncMock):
                with patch.object(
                    app, "_load_tags_for_current_item", new_callable=AsyncMock
                ):
                    with patch.object(
                        app, "_load_current_item_for_playback", new_callable=AsyncMock
                    ):
                        with patch.object(app.playback_widget, "play") as mock_play:
                            with patch.object(
                                app.playback_widget, "pause"
                            ) as mock_pause:
                                with patch.object(
                                    app.playback_widget,
                                    "is_playing",
                                    return_value=False,
                                ):
                                    async with app.run_test():
                                        # on_mount already called _set_item once
                                        mock_play.reset_mock()
                                        mock_pause.reset_mock()
                                        # Navigate to next item
                                        await app._set_item(items[1])

                                    if config["autoplay_on_track_change"]:
                                        mock_play.assert_called()
                                    else:
                                        # If not autoplaying, should ensure paused
                                        if mock_play.called:
                                            mock_pause.assert_called()

    @pytest.mark.asyncio
    async def test_keep_playing_on_track_change_when_playing(
        self, temp_beets_library: Library
    ):
        """Test keep_playing_on_track_change_if_playing when currently playing."""
        items = list(temp_beets_library.items())
        if len(items) < 2:
            pytest.skip("Need at least 2 items for track change test")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=True,
        )

        with patch.object(app, "_save_current_item_tags", new_callable=AsyncMock):
            with patch.object(
                app, "_load_tags_for_current_item", new_callable=AsyncMock
            ):
                with patch.object(
                    app, "_load_current_item_for_playback", new_callable=AsyncMock
                ):
                    with patch.object(app.playback_widget, "play") as mock_play:
                        with patch.object(
                            app.playback_widget, "is_playing", return_value=True
                        ):
                            async with app.run_test():
                                # on_mount already called _set_item once
                                mock_play.reset_mock()
                                # Navigate to next item while playing
                                await app._set_item(items[1])

                            # Should continue playing the new track
                            mock_play.assert_called_once()

    @pytest.mark.asyncio
    async def test_keep_playing_on_track_change_when_paused(
        self, temp_beets_library: Library
    ):
        """Test keep_playing_on_track_change_if_playing when currently paused."""
        items = list(temp_beets_library.items())
        if len(items) < 2:
            pytest.skip("Need at least 2 items for track change test")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=True,
        )

        with patch.object(app, "_save_current_item_tags", new_callable=AsyncMock):
            with patch.object(
                app, "_load_tags_for_current_item", new_callable=AsyncMock
            ):
                with patch.object(
                    app, "_load_current_item_for_playback", new_callable=AsyncMock
                ):
                    with patch.object(app.playback_widget, "play") as mock_play:
                        with patch.object(
                            app.playback_widget,
                            "is_playing",
                            return_value=False,
                        ):
                            async with app.run_test():
                                # Navigate to next item while paused
                                await app._set_item(items[1])

                            # Should not start playing (was paused)
                            mock_play.assert_not_called()


class TestQuickTagAppNavigation:
    """Test track navigation functionality."""

    @pytest.mark.asyncio
    async def test_navigate_forward(self, temp_beets_library: Library):
        """Test navigating to next item."""
        items = list(temp_beets_library.items())
        if len(items) < 2:
            pytest.skip("Need at least 2 items for navigation test")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        initial_index = app.current_item_index

        with patch.object(app, "_set_item", new_callable=AsyncMock) as mock_set_item:
            await app._navigate(NavigateDirection.FORWARD)

            assert app.current_item_index == initial_index + 1
            mock_set_item.assert_called_once_with(items[initial_index + 1])

    @pytest.mark.asyncio
    async def test_navigate_backward(self, temp_beets_library: Library):
        """Test navigating to previous item."""
        items = list(temp_beets_library.items())
        if len(items) < 2:
            pytest.skip("Need at least 2 items for navigation test")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        # Start at second item
        app.current_item_index = 1

        with patch.object(app, "_set_item", new_callable=AsyncMock) as mock_set_item:
            await app._navigate(NavigateDirection.BACKWARD)

            assert app.current_item_index == 0
            mock_set_item.assert_called_once_with(items[0])

    @pytest.mark.asyncio
    async def test_navigate_forward_at_end(self, temp_beets_library: Library):
        """Test navigating forward when at last item."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        # Set to last item
        app.current_item_index = len(items) - 1

        with (
            patch.object(app, "_set_item", new_callable=AsyncMock) as mock_set_item,
            patch.object(
                app, "_save_current_item_tags", new_callable=AsyncMock
            ) as mock_save,
        ):
            moved = await app._navigate(NavigateDirection.FORWARD)

            # Should not change index, but must still save the last item
            assert moved is False
            assert app.current_item_index == len(items) - 1
            mock_set_item.assert_not_called()
            mock_save.assert_called_once()

            # Should show completion message
            # Note: This updates the header display directly

    @pytest.mark.asyncio
    async def test_navigate_backward_at_beginning(self, temp_beets_library: Library):
        """Test navigating backward when at first item."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        # Start at first item (index 0)
        app.current_item_index = 0

        with patch.object(app, "_set_item", new_callable=AsyncMock) as mock_set_item:
            await app._navigate(NavigateDirection.BACKWARD)

            # Should not change index
            assert app.current_item_index == 0
            mock_set_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_navigating_past_last_item_saves_tags(
        self, temp_beets_library: Library
    ):
        """Pressing Right on the last item must persist that item's tags."""
        items = list(temp_beets_library.items())
        if len(items) < 2:
            pytest.skip("Need at least 2 items for navigation test")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,  # No safety net on quit
            keep_playing_on_track_change_if_playing_enabled=False,
        )
        last_item_id = items[-1].id

        async with app.run_test() as pilot:
            for _ in range(len(items) - 1):
                await pilot.press("right")
            assert app.current_item_index == len(items) - 1

            app.query_one("#selection-genre", CustomSelectionList).select(0)

            await pilot.press("right")

            assert app.current_item_index == len(items) - 1
            assert "All items processed" in header_text(app)
            assert temp_beets_library.get_item(last_item_id).get("genre") == "Rock"


class TestQuickTagAppPlaybackActions:
    """Test playback action methods."""

    @pytest.mark.asyncio
    async def test_action_play_pause_current_item(self, temp_beets_library: Library):
        """Test play/pause action."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        with patch.object(app.playback_widget, "play_pause") as mock_play_pause:
            await app.action_play_pause_current_item()
            mock_play_pause.assert_called_once()

    @pytest.mark.asyncio
    async def test_action_play_pause_no_item(self, temp_beets_library: Library):
        """Test play/pause action when no item is loaded."""
        app = QuickTagApp(
            lib=temp_beets_library,
            items=[],  # Empty items list
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )
        app.item = None

        with patch.object(app.playback_widget, "play_pause") as mock_play_pause:
            await app.action_play_pause_current_item()
            mock_play_pause.assert_not_called()

    @pytest.mark.asyncio
    async def test_action_seek_forward(self, temp_beets_library: Library):
        """Test seek forward action."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        with patch.object(app.playback_widget, "seek_relative") as mock_seek:
            await app.action_seek_forward(10)
            mock_seek.assert_called_once_with(10)

    @pytest.mark.asyncio
    async def test_action_seek_backward(self, temp_beets_library: Library):
        """Test seek backward action."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        with patch.object(app.playback_widget, "seek_relative") as mock_seek:
            await app.action_seek_backward(5)
            mock_seek.assert_called_once_with(-5)


class TestQuickTagAppPlaybackEndedHandling:
    """Test handling of PlaybackEnded messages."""

    @pytest.mark.asyncio
    async def test_playback_ended_with_autonext_enabled(
        self, temp_beets_library: Library
    ):
        """Test auto-advance when track ends and autonext is enabled."""
        items = list(temp_beets_library.items())
        if len(items) < 2:
            pytest.skip("Need at least 2 items for autonext test")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=True,  # Enable autonext
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        # Start at first item
        app.current_item_index = 0

        with (
            patch.object(
                app, "_navigate", new_callable=AsyncMock, return_value=True
            ) as mock_navigate,
            patch.object(app.playback_widget, "play") as mock_play,
        ):
            await app.on_playback_ended(PlaybackEnded())

            mock_navigate.assert_called_once_with(NavigateDirection.FORWARD)
            # Auto-advance keeps listening, regardless of autoplay_on_track_change
            mock_play.assert_called_once()

    @pytest.mark.asyncio
    async def test_playback_ended_with_autonext_disabled(
        self, temp_beets_library: Library
    ):
        """Test behavior when track ends and autonext is disabled."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,  # Disable autonext
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        with (
            patch.object(app, "_navigate", new_callable=AsyncMock) as mock_navigate,
            patch.object(app.playback_widget, "play") as mock_play,
        ):
            await app.on_playback_ended(PlaybackEnded())

            # The player is already stopped at the start of the track; nothing to do
            mock_navigate.assert_not_called()
            mock_play.assert_not_called()

    @pytest.mark.asyncio
    async def test_playback_ended_at_last_item(self, temp_beets_library: Library):
        """Test behavior when track ends at the last item."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=True,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        # Set to last item
        app.current_item_index = len(items) - 1

        with (
            patch.object(
                app, "_navigate", new_callable=AsyncMock, return_value=False
            ) as mock_navigate,
            patch.object(app.playback_widget, "play") as mock_play,
        ):
            await app.on_playback_ended(PlaybackEnded())

            # _navigate handles the end of the list (saving and reporting);
            # nothing to advance to, so playback must not restart
            mock_navigate.assert_called_once_with(NavigateDirection.FORWARD)
            mock_play.assert_not_called()

    @pytest.mark.asyncio
    async def test_playback_ended_at_last_item_shows_completion(
        self, temp_beets_library: Library
    ):
        """Auto-advancing past the last item must report that we are done."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=True,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        async with app.run_test():
            app.current_item_index = len(items) - 1
            app.item = items[-1]

            with patch.object(app.playback_widget, "play") as mock_play:
                await app.on_playback_ended(PlaybackEnded())

            assert app.current_item_index == len(items) - 1
            assert "All items processed" in header_text(app)
            # The last track must not restart in a loop
            mock_play.assert_not_called()


class TestQuickTagAppErrorHandling:
    """Test error handling and recovery."""

    @pytest.mark.asyncio
    async def test_load_current_item_for_playback_path_decoding_error(
        self, temp_beets_library: Library
    ):
        """Test handling of path decoding errors."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        # Mock item with problematic path
        mock_item = Mock()
        mock_item.path = Mock()
        mock_item.path.decode.side_effect = UnicodeDecodeError(
            "utf-8", b"", 0, 1, "test error"
        )

        with patch.object(app.playback_widget, "load_track") as mock_load_track:
            async with app.run_test():
                mock_load_track.reset_mock()  # on_mount loaded the real item
                app.item = mock_item
                await app._load_current_item_for_playback()

            # Should not call load_track if path decoding fails
            mock_load_track.assert_not_called()

    @pytest.mark.asyncio
    async def test_autosave_on_quit(self, temp_beets_library: Library):
        """Test autosave functionality on quit."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=True,  # Enable autosave
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        with patch.object(
            app, "_save_current_item_tags", new_callable=AsyncMock
        ) as mock_save:
            with patch.object(app, "exit") as mock_exit:
                await app.action_quit()

                mock_save.assert_called_once()
                mock_exit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_autosave_on_quit(self, temp_beets_library: Library):
        """Test quit without autosave."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,  # Disable autosave
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        with patch.object(
            app, "_save_current_item_tags", new_callable=AsyncMock
        ) as mock_save:
            with patch.object(app, "exit") as mock_exit:
                await app.action_quit()

                mock_save.assert_not_called()
                mock_exit.assert_called_once()


class TestQuickTagAppRealPlaybackIntegration:
    """Integration tests with real playback using generated MP3 files."""

    @pytest.mark.asyncio
    async def test_full_playback_lifecycle(
        self, temp_beets_library: Library, mp3_files: dict[str, Path]
    ):
        """Test complete playback lifecycle with real files."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=True,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        # Use real MP3 file path
        if app.playback_widget.player is None:
            pytest.skip("just_playback not available")

        async with app.run_test():
            # Mock the item path to point to our test file
            app.item.path = str(mp3_files["short"])

            # Load and play
            await app._load_current_item_for_playback()
            await app.action_play_pause_current_item()

            # Give some time for playback to start
            await asyncio.sleep(0.1)
            assert app.playback_widget.is_playing()

            # Test seek operations
            await app.action_seek_forward(2)
            await app.action_seek_backward(1)

            # Stop playback
            app.playback_widget.stop()
            assert not app.playback_widget.is_playing()

    @pytest.mark.asyncio
    async def test_rapid_track_changes(self, temp_beets_library: Library):
        """Test rapid track changes don't cause issues."""
        items = list(temp_beets_library.items())
        if len(items) < 3:
            pytest.skip("Need at least 3 items for rapid change test")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        # Mock methods to avoid actual file operations
        with patch.object(app, "_save_current_item_tags", new_callable=AsyncMock):
            with patch.object(
                app, "_load_tags_for_current_item", new_callable=AsyncMock
            ):
                with patch.object(
                    app, "_load_current_item_for_playback", new_callable=AsyncMock
                ):
                    async with app.run_test():
                        # Rapid navigation
                        for _ in range(min(5, len(items))):
                            await app.action_next_item()
                            # Small delay to simulate real usage
                            await asyncio.sleep(0.01)

                    # Should handle rapid changes without errors
                    assert app.current_item_index > 0


class TestQuickTagAppMarkupSafety:
    """Bracketed text from metadata and config must render literally."""

    @pytest.mark.asyncio
    async def test_header_renders_bracketed_title_literally(
        self, temp_beets_library: Library
    ):
        """A title like 'Foo [feat. Bar]' must not crash or lose the brackets."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        items[0].title = "Foo [feat. Bar]"
        items[0].store()

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        async with app.run_test():
            assert "Foo [feat. Bar]" in header_text(app)

    @pytest.mark.asyncio
    async def test_option_text_with_brackets_renders_literally(
        self, temp_beets_library: Library
    ):
        """Category options come from user config and may contain brackets."""
        items = list(temp_beets_library.items())
        if not items:
            pytest.skip("No items in test library")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["lo-fi [chill]", "Rock"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        async with app.run_test():
            selection_list = app.query_one("#selection-genre", CustomSelectionList)
            prompt = selection_list.get_option_at_index(0).prompt
            assert prompt.plain == "lo-fi [chill]"


class TestQuickTagAppNavigationBindings:
    """Left/Right must navigate tracks without stealing keys from the input."""

    @pytest.mark.asyncio
    async def test_left_moves_cursor_in_comments_input(
        self, temp_beets_library: Library
    ):
        """With the comments input focused, Left moves the cursor, not the track."""
        items = list(temp_beets_library.items())
        if len(items) < 2:
            pytest.skip("Need at least 2 items for navigation test")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        async with app.run_test() as pilot:
            # Move off the first item so that Left would visibly change track.
            await pilot.press("right")
            assert app.current_item_index == 1

            comments_input = app.query_one("#comments-input", InputWithLabel).query_one(
                Input
            )
            comments_input.value = "hello"
            comments_input.focus()
            await pilot.pause()
            comments_input.cursor_position = 3

            await pilot.press("left")

            assert comments_input.cursor_position == 2
            assert app.current_item_index == 1

    @pytest.mark.asyncio
    async def test_right_advances_track_from_selection_list(
        self, temp_beets_library: Library
    ):
        """With a selection list focused, Right still moves to the next track."""
        items = list(temp_beets_library.items())
        if len(items) < 2:
            pytest.skip("Need at least 2 items for navigation test")

        app = QuickTagApp(
            lib=temp_beets_library,
            items=items,
            categories=[("genre", ["Rock", "Pop"])],
            autoplay_at_launch_enabled=False,
            autoplay_on_track_change_enabled=False,
            autonext_at_track_end_enabled=False,
            autosave_on_quit_enabled=False,
            keep_playing_on_track_change_if_playing_enabled=False,
        )

        async with app.run_test() as pilot:
            app.query_one("#selection-genre", CustomSelectionList).focus()
            await pilot.pause()

            await pilot.press("right")

            assert app.current_item_index == 1
