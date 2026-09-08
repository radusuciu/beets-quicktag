from collections.abc import Awaitable, Callable, Sequence
from enum import Enum
from functools import partial
from pathlib import Path
from typing import TypeVar

from beets.dbcore.db import Results as BeetsResults
from beets.dbcore.query import InQuery
from beets.library import Item as BeetsItem
from beets.library import Library as BeetsLibrary
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.dom import NoMatches
from textual.widgets import Footer, Input, Static
from textual.worker import WorkerFailed

from .definitions import CategoryDefinitions, find_case_insensitive
from .definitions_file import write_definitions_file
from .item_values import read_item_values, write_item_values
from .library_ops import (
    count_tracks,
    remove_category,
    remove_option,
    rename_category,
    rename_option,
)
from .widgets.category_panel import CategoryPanel
from .widgets.custom_selection_list import CustomSelectionList, EditKind
from .widgets.inline_input import InlineInput
from .widgets.input_with_label import InputWithLabel
from .widgets.playback import PlaybackEnded, PlaybackStateChanged, PlaybackWidget

# Terminal window title whenever nothing is audibly playing.
FALLBACK_TERMINAL_TITLE = "Beets QuickTag"

CATEGORY_PLACEHOLDER = "New category name, Enter to add, Esc to cancel"


# Control characters (C0 plus DEL) in metadata could terminate or extend the
# OSC escape sequence used to set the terminal title, so they are stripped.
_CONTROL_CHARS = dict.fromkeys((*range(0x20), 0x7F))


class NavigateDirection(Enum):
    """Enum for seek direction."""

    FORWARD = 1
    BACKWARD = -1


class HeaderWidget(Vertical):
    """A custom widget for the application header, now including a playback widget."""

    DEFAULT_CSS = """
    HeaderWidget {
        dock: top;
        width: 100%;
        height: auto; /* Adjusts to content: title line + playback widget */
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    #header_text_content {
        width: 100%;
        height: 1;
    }
    """

    def __init__(self, playback_widget: PlaybackWidget, item=None, **kwargs):
        super().__init__(**kwargs)
        self.item: BeetsItem = item
        # A message replaces the title line until it is cleared; the title
        # is re-rendered underneath it, never over it.
        self._message: str | None = None
        # markup=False: titles and status messages are literal text, and
        # real-world metadata contains brackets (e.g. "Song [feat. X]").
        self._header_text_display = Static(id="header_text_content", markup=False)
        self.playback_widget = playback_widget

    def compose(self) -> ComposeResult:
        """Compose the header with text and the playback widget."""
        yield self._header_text_display
        yield self.playback_widget

    def on_mount(self) -> None:
        """Set the header text when the widget is mounted."""
        self.update_header()

    def update_header(self, item: BeetsItem | None = None) -> None:
        """Store ``item`` and show its title, unless a message is on screen."""
        if item:
            self.item = item
        self._render_line()

    def show_message(self, text: str) -> None:
        """Replace the title line with ``text`` until ``clear_message``."""
        self._message = text
        self._render_line()

    def clear_message(self) -> None:
        """Drop the message and show the title again."""
        self._message = None
        self._render_line()

    def _render_line(self) -> None:
        if self._message is not None:
            text = self._message
        elif self.item:
            text = f"Tagging: {self.item.artist} - {self.item.title}"
        else:
            text = "QuickTag"
        self._header_text_display.update(text)


# Tracks re-fetched per query after a migration; well under sqlite's limit
# on bound variables.
_RELOAD_CHUNK = 500

T = TypeVar("T")


class QuickTagApp(App):
    BINDINGS = [
        # Escape has its own action so that Textual's built-in ctrl+q, which
        # maps to ``quit``, keeps quitting even while an inline edit is open.
        Binding("escape", "cancel_or_quit", "Quit", show=True, priority=True),
        # No priority: the focused widget wins first, so Left/Right move the
        # cursor inside the comments input instead of changing track.
        Binding("left", "previous_item", "Previous", show=True),
        Binding("right", "next_item", "Next", show=True),
        ("/", "play_pause_current_item", "Play/Pause"),
        ("<", "seek_backward(5)", "Seek -5s"),
        (">", "seek_forward(5)", "Seek +5s"),
        Binding("ctrl+n", "add_category", "New category"),
        # Hardware media keys, as named by the kitty keyboard protocol. Hidden
        # because the footer would print the raw key names.
        Binding("media_play_pause", "media_play_pause", show=False),
        Binding("media_stop", "pause_current_item", show=False),
        Binding("media_track_next", "next_item", show=False),
        Binding("media_track_previous", "previous_item", show=False),
    ]

    DEFAULT_CSS = """
    Screen {
        align: center middle;
    }
    #new-category-input {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        lib: BeetsLibrary,
        items: BeetsResults | Sequence[BeetsItem],
        definitions: CategoryDefinitions,
        autoplay_on_track_change_enabled: bool,
        autoplay_at_launch_enabled: bool,
        autonext_at_track_end_enabled: bool,
        autosave_on_quit_enabled: bool,
        keep_playing_on_track_change_if_playing_enabled: bool,
        keep_audio_device_awake_enabled: bool = False,
        definitions_path: Path | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.lib = lib
        self.items = items
        self.definitions = definitions
        self.definitions_path = definitions_path
        self.autoplay_on_track_change_enabled = autoplay_on_track_change_enabled
        self.autoplay_at_launch_enabled = autoplay_at_launch_enabled
        self.autonext_at_track_end_enabled = autonext_at_track_end_enabled
        self.autosave_on_quit_enabled = autosave_on_quit_enabled
        self.keep_playing_on_track_change_if_playing_enabled = (
            keep_playing_on_track_change_if_playing_enabled
        )

        self.current_item_index = 0
        self.item = items[0] if items else None
        # Stored values the model refuses as options (e.g. they contain a
        # comma). Kept per category so a save writes them back untouched
        # instead of deleting them from the track.
        self._unadoptable_values: dict[str, list[str]] = {}
        self.playback_widget = PlaybackWidget(
            keep_audio_device_awake=keep_audio_device_awake_enabled
        )
        self.header_widget = HeaderWidget(
            item=self.item, playback_widget=self.playback_widget
        )

        self.log.info("QuickTagApp initialized.")

    async def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.theme = "gruvbox"
        self._set_terminal_title(FALLBACK_TERMINAL_TITLE)
        await self._set_item(
            self.item, save_current_item_tags=False, is_initial_load=True
        )
        if self.autoplay_at_launch_enabled:
            self.playback_widget.play()

    async def on_unmount(self) -> None:
        """Called when the app is unmounted."""
        self.log.info("QuickTagApp unmounted.")
        # The original title cannot be restored portably; leave the fallback
        # rather than the last song. Most shells reset it at the next prompt.
        self._set_terminal_title(FALLBACK_TERMINAL_TITLE)

    def on_playback_state_changed(self, message: PlaybackStateChanged) -> None:
        """Show the playing track in the terminal title, else the fallback."""
        if message.playing and self.item:
            song = f"{self.item.artist} - {self.item.title}"
            self._set_terminal_title(song.translate(_CONTROL_CHARS))
        else:
            self._set_terminal_title(FALLBACK_TERMINAL_TITLE)

    def _set_terminal_title(self, text: str) -> None:
        """Set the terminal window title with an OSC 0 escape sequence.

        Textual 3.x has no terminal-title API (App.title only feeds the Header
        widget), so the sequence is written through the driver, where it is
        queued with frame output instead of interleaving with a partial render.
        The driver attribute is private to Textual; this is the only place
        that touches it.
        """
        driver = self._driver
        if driver is None:
            return
        driver.write(f"\x1b]0;{text}\x07")

    def _selection_list(self, category: str) -> CustomSelectionList:
        """The list widget for ``category``; raises ``NoMatches``."""
        return self.query_one(f"#selection-{category}", CustomSelectionList)

    def _panel(self, category: str) -> CategoryPanel:
        """The panel for ``category``; raises ``NoMatches``."""
        return self.query_one(f"#panel-{category}", CategoryPanel)

    def _persist_definitions(self) -> None:
        """Write the definitions file if one is configured.

        A failure is logged and the in-memory change is kept, so the next
        successful write carries it.
        """
        if self.definitions_path is None:
            return
        try:
            write_definitions_file(self.definitions_path, self.definitions)
        except OSError as error:
            self.log.error(
                f"Could not write categories file {self.definitions_path}: {error}"
            )
            # The log goes nowhere in a real session, and the user would
            # otherwise believe the category was saved for next time.
            self.header_widget.show_message(
                f"Could not write categories file: {self.definitions_path}"
            )

    def compose(self) -> ComposeResult:
        yield self.header_widget

        if self.item:
            for category_name in self.definitions.categories:
                yield CategoryPanel(
                    category_name, self.definitions.options(category_name)
                )
            yield InlineInput(id="new-category-input", placeholder=CATEGORY_PLACEHOLDER)
            yield InputWithLabel(input_label="Comments:", id="comments-input")
        else:
            yield Static("No items to tag.")

        yield Footer()

    # Actions bound to printable keys. While an Input has focus those keys are
    # typed into it and never reach the App.
    _TYPED_KEY_ACTIONS = frozenset(
        {"play_pause_current_item", "seek_backward", "seek_forward"}
    )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Hide the playback bindings from the footer while an Input has focus.

        Textual drops ancestor bindings that the focused widget will consume, but
        it decides by mapping the key name to a character and has no entry for
        "slash". The Input still swallows the actual "/" key press, so without
        this the footer advertises Play/Pause that cannot be triggered.
        """
        if action in self._TYPED_KEY_ACTIONS and isinstance(self.focused, Input):
            return False
        return True

    async def on_category_panel_edit_requested(
        self, message: CategoryPanel.EditRequested
    ) -> None:
        """An editing key on a panel's list (everything except add)."""
        panel, kind, value = message.panel, message.kind, message.value
        category = panel.category
        if kind is EditKind.RENAME_OPTION and value is not None:
            panel.open_input(kind, target=value, initial=value)
        elif kind is EditKind.REMOVE_OPTION and value is not None:
            planned = self.definitions.copy()
            planned.remove_option(category, value)
            count = await self._count_tracks(category, value)
            panel.open_confirm(
                f"Delete '{value}' from {count} tracks? y/n",
                partial(
                    self._edit_options,
                    panel,
                    planned,
                    partial(remove_option, self.lib, category, value),
                ),
            )
        elif kind is EditKind.RENAME_CATEGORY:
            if not CategoryDefinitions.owns_field(category):
                self.header_widget.show_message(
                    f"'{category}' is a built-in beets field; its category "
                    "cannot be renamed."
                )
                return
            panel.open_input(kind, initial=category)
        elif kind is EditKind.REMOVE_CATEGORY:
            planned = self.definitions.copy()
            planned.remove_category(category)
            if not CategoryDefinitions.owns_field(category):
                # The field holds data quicktag did not put there, so the
                # category is only unlisted.
                panel.open_confirm(
                    f"Remove category '{category}'? It is a built-in beets "
                    "field, so every track keeps its value. y/n",
                    partial(self._remove_category, panel, planned, None),
                )
                return
            count = await self._count_tracks(category)
            panel.open_confirm(
                f"Delete category '{category}' and its values from {count} tracks? y/n",
                partial(
                    self._remove_category,
                    panel,
                    planned,
                    partial(remove_category, self.lib, category),
                ),
            )

    async def on_category_panel_inline_submitted(
        self, message: CategoryPanel.InlineSubmitted
    ) -> None:
        """Enter in a panel's inline input, dispatched on what it was opened for."""
        if message.kind is EditKind.ADD_OPTION:
            self._add_option(message.panel, message.value)
        elif message.kind is EditKind.RENAME_OPTION and message.target is not None:
            await self._submit_option_rename(
                message.panel, message.target, message.value
            )
        elif message.kind is EditKind.RENAME_CATEGORY:
            await self._submit_category_rename(message.panel, message.value)

    def _add_option(self, panel: CategoryPanel, typed: str) -> None:
        """Validate, persist, show and select a new option.

        Typing a new option almost always means the current track should get
        it, so the new option is selected as well as highlighted.
        """
        try:
            value = self.definitions.add_option(panel.category, typed)
        except ValueError as error:
            panel.show_error(str(error))
            return
        self._persist_definitions()
        panel.add_option(value, select=True)
        panel.close_input()

    async def _submit_option_rename(
        self, panel: CategoryPanel, old: str, typed: str
    ) -> None:
        """Plan the rename, then apply it directly or ask first."""
        category = panel.category
        planned = self.definitions.copy()
        try:
            new = planned.rename_option(category, old, typed)
        except ValueError as error:
            panel.show_error(str(error))
            return
        if new == old:
            panel.close_input()
            return
        # A merge drops the old entry instead of renaming it in place.
        merged = len(planned.options(category)) < len(
            self.definitions.options(category)
        )
        count = await self._count_tracks(category, old)
        run = partial(
            self._edit_options,
            panel,
            planned,
            partial(rename_option, self.lib, category, old, new),
        )
        if merged:
            question = f"Merge '{old}' into '{new}' on {count} tracks? y/n"
        elif count:
            question = f"Rename '{old}' to '{new}' on {count} tracks? y/n"
        else:
            question = None
        await self._confirm_or_run(panel, question, run)

    async def _submit_category_rename(self, panel: CategoryPanel, typed: str) -> None:
        """Plan the rename, then apply it directly or ask first."""
        old = panel.category
        planned = self.definitions.copy()
        try:
            new = planned.rename_category(old, typed)
        except ValueError as error:
            panel.show_error(str(error))
            return
        if new == old:
            panel.close_input()
            return
        count = await self._count_tracks(old)
        run = partial(
            self._rename_category,
            panel,
            planned,
            new,
            partial(rename_category, self.lib, old, new),
        )
        question = (
            f"Rename category '{old}' to '{new}' on {count} tracks? y/n"
            if count
            else None
        )
        await self._confirm_or_run(panel, question, run)

    async def _confirm_or_run(
        self,
        panel: CategoryPanel,
        question: str | None,
        run: Callable[[], Awaitable[None]],
    ) -> None:
        """Ask ``question`` on the panel's inline line, or just run when None."""
        if question is not None:
            panel.open_confirm(question, run)
            return
        panel.close_input()
        await run()

    async def _count_tracks(self, category: str, value: str | None = None) -> int:
        """Count off the event loop: it scans the whole library.

        The current track is counted as the panel shows it, pending
        selection included, and not stored first: cancelling the prompt
        must leave it exactly as it was.
        """
        shown = self._shown_values(category)
        if shown is None:
            return await self._off_loop(
                partial(count_tracks, self.lib, category, value)
            )
        count = await self._off_loop(
            partial(count_tracks, self.lib, category, value, exclude_id=self.item.id)
        )
        if value is None:
            has_value = bool(shown)
        else:
            has_value = find_case_insensitive(shown, value) is not None
        return count + int(has_value)

    def _shown_values(self, category: str) -> list[str] | None:
        """The current track's ``category`` values as the screen has them.

        Selected options plus the values the track carries that could not
        become options: exactly what a save would write. ``None`` when
        there is no track or no list for ``category``.
        """
        if not self.item:
            return None
        try:
            selected = list(self._selection_list(category).selected)
        except NoMatches:
            return None
        return selected + self._unadoptable_values.get(category, [])

    async def _off_loop(self, work: Callable[[], T]) -> T:
        """Run ``work`` in a thread so the UI keeps painting; re-raise its error.

        beets opens one connection per thread and the library functions
        fetch and store within one call, so they are safe off the loop.
        """
        worker = self.run_worker(work, thread=True, exit_on_error=False)
        try:
            return await worker.wait()
        except WorkerFailed as failed:
            raise failed.error from None

    async def _edit_options(
        self,
        panel: CategoryPanel,
        planned: CategoryDefinitions,
        migrate: Callable[[], int],
    ) -> None:
        """Migrate, swap the definitions in, rebuild the list, reload the track."""
        highlighted = panel.selection_list.highlighted
        changed = await self._apply_edit(planned, migrate)
        if changed is None:
            return
        panel.set_options(
            self.definitions.options(panel.category), highlighted=highlighted
        )
        await self._refresh_tracks(changed)

    async def _rename_category(
        self,
        panel: CategoryPanel,
        planned: CategoryDefinitions,
        new: str,
        migrate: Callable[[], int],
    ) -> None:
        """A widget id cannot change, so the panel is replaced in place."""
        changed = await self._apply_edit(planned, migrate)
        if changed is None:
            return
        replacement = CategoryPanel(new, self.definitions.options(new))
        await self.mount(replacement, before=panel)
        await panel.remove()
        await self._refresh_tracks(changed)
        replacement.selection_list.focus()

    async def _remove_category(
        self,
        panel: CategoryPanel,
        planned: CategoryDefinitions,
        migrate: Callable[[], int] | None,
    ) -> None:
        panels = list(self.query(CategoryPanel))
        index = panels.index(panel)
        changed = await self._apply_edit(planned, migrate)
        if changed is None:
            return
        await panel.remove()
        await self._refresh_tracks(changed)
        remaining = list(self.query(CategoryPanel))
        if remaining:
            # The panel that took the removed one's place, or the last one.
            remaining[min(index, len(remaining) - 1)].selection_list.focus()
        else:
            self._focus_after_closing_category_input()

    async def _apply_edit(
        self, planned: CategoryDefinitions, migrate: Callable[[], int] | None
    ) -> int | None:
        """Library first, then the definitions.

        ``planned`` is the definitions as they will be once the library
        agrees; computing it before migrating means nothing can fail after
        the migration has committed. Returns how many tracks changed, or
        ``None`` when the migration failed, in which case it changed nothing
        and the header says so.
        """
        changed = 0
        if migrate is not None:
            # The prompt counted the track's pending selection without
            # storing it; the migration reloads the track, so store now or
            # the selection is lost. A failed store already says why.
            if not await self._save_current_item_tags():
                return None
            self.header_widget.show_message("Updating library…")
            try:
                changed = await self._off_loop(migrate)
            except Exception as error:
                # The transaction was rolled back; any error class is a
                # "nothing happened" for the user, so it is caught broadly
                # on purpose.
                self.log.error(f"Library migration failed: {error}")
                self.header_widget.show_message(
                    f"Library update failed, nothing changed: {error}"
                )
                return None
            self.log.info(f"Library migration changed {changed} tracks.")
            self.header_widget.clear_message()
        self.definitions = planned
        self._persist_definitions()
        return changed

    async def _refresh_tracks(self, changed: int) -> None:
        """Reload the track's selections; re-fetch the queue if the library changed."""
        if changed:
            await self._reload_after_migration()
        else:
            await self._load_tags_for_current_item()

    async def on_category_panel_confirmed(
        self, message: CategoryPanel.Confirmed
    ) -> None:
        await message.run()

    def on_category_panel_input_opened(
        self, message: CategoryPanel.InputOpened
    ) -> None:
        """Keep at most one inline edit open, so Escape is unambiguous."""
        self._close_inline_edits(except_panel=message.panel)

    def _close_inline_edits(self, *, except_panel: CategoryPanel | None = None) -> None:
        """Close every open inline edit except ``except_panel``'s.

        Focus is left alone: the edit that is taking over already has it.
        """
        for panel in self.query(CategoryPanel):
            if panel is not except_panel and panel.inline_active:
                panel.close_inline(refocus=False)
        try:
            new_category_input = self._new_category_input()
        except NoMatches:
            return
        if new_category_input.active:
            new_category_input.close()

    def _new_category_input(self) -> InlineInput:
        return self.query_one("#new-category-input", InlineInput)

    def action_add_category(self) -> None:
        """ctrl+n: reveal the new-category input above the comments field."""
        try:
            new_category_input = self._new_category_input()
        except NoMatches:
            return
        if new_category_input.active:
            # Already open: re-opening would discard what has been typed.
            new_category_input.focus()
            return
        self._close_inline_edits()
        new_category_input.open()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in the new-category input. Panel inputs never reach here
        (the panel stops their Submitted), and the comments Input has no id."""
        if event.input.id != "new-category-input":
            return
        event.stop()
        new_category_input = self._new_category_input()
        try:
            name = self.definitions.add_category(event.value)
        except ValueError as error:
            new_category_input.show_error(str(error))
            return
        panel = CategoryPanel(name, [])
        await self.mount(panel, before=new_category_input)
        # The track may already carry values for this field; show them (and
        # adopt unknown ones) so the first save keeps them instead of
        # writing an empty selection over them.
        self._load_category_values(name)
        self._persist_definitions()
        new_category_input.close()
        panel.selection_list.focus()

    async def action_cancel_or_quit(self) -> None:
        """Escape: cancel an open inline edit if there is one, else quit."""
        if self._cancel_inline_edit():
            return
        await self.action_quit()

    async def action_quit(self) -> None:
        """Quit (also Textual's ctrl+q), saving first if autosave is on."""
        self.log.info(
            "action_quit called. "
            f"autosave_on_quit_enabled: {self.autosave_on_quit_enabled}"
        )
        if self.autosave_on_quit_enabled and self.item:
            self.log.info("Autosaving tags before quitting.")
            await self._save_current_item_tags()
        self.exit()

    def _cancel_inline_edit(self) -> bool:
        """Close any open inline input. Returns True if one was open."""
        if not self.is_running:
            # No screen is mounted (e.g. action_quit called directly in a
            # test, outside run_test()); querying would raise
            # ScreenStackError, and there is nothing open to close anyway.
            return False
        for panel in self.query(CategoryPanel):
            if panel.inline_active:
                panel.close_inline()
                return True
        try:
            new_category_input = self._new_category_input()
        except NoMatches:
            return False
        if not new_category_input.active:
            return False
        new_category_input.close()
        self._focus_after_closing_category_input()
        return True

    def _focus_after_closing_category_input(self) -> None:
        """Hiding the input drops focus, so hand it to the first list.

        With no categories yet there is no list, and the comments field is
        the only other place focus can sensibly go.
        """
        if self.definitions.categories:
            try:
                self._selection_list(self.definitions.categories[0]).focus()
                return
            except NoMatches:
                pass
        try:
            comments = self.query_one("#comments-input", InputWithLabel)
        except NoMatches:
            return
        comments.query_one(Input).focus()

    async def _load_current_item_for_playback(self) -> None:
        """Load the current item for playback."""

        item_path_bytes = self.item.path

        try:
            item_path_str = item_path_bytes.decode("utf-8", "surrogateescape")
        except AttributeError:
            item_path_str = item_path_bytes
        except Exception as e:
            self.log.error(f"Error decoding item path: {e}")
            return

        self.playback_widget.load_track(item_path_str)

    async def _set_item(
        self,
        item: BeetsItem,
        save_current_item_tags: bool = True,
        *,
        is_initial_load: bool = False,
    ) -> None:
        """Handle changes to the current item.

        `is_initial_load` marks the call made from `on_mount`: the launch
        decision belongs solely to `autoplay_at_launch_enabled` there, so the
        autoplay-on-track-change branch below is skipped for that call.
        """
        # Capture the current playback state before changing items
        was_playing_before = self.playback_widget.is_playing()

        # A y/n prompt was armed on the track that is leaving; nothing binds
        # its keys once focus moves on, so it is withdrawn. An open input
        # keeps its text and its focus.
        for panel in self.query(CategoryPanel):
            if panel.confirm_active:
                panel.close_confirm(refocus=False)

        # The title changes before the save so that a save failure reported
        # by ``_save_current_item_tags`` is the last thing written to the
        # header rather than being overwritten by the new title.
        self.header_widget.clear_message()
        self.header_widget.update_header(item)
        if save_current_item_tags:
            await self._save_current_item_tags()
        self.item = item
        await self._load_tags_for_current_item()
        self.log.info(f"Item set to: {item.artist} - {item.title}")

        if self.definitions.categories and not self._inline_edit_active():
            try:
                self._selection_list(self.definitions.categories[0]).focus()
            except NoMatches:
                pass

        # Load the new track (this doesn't start playback automatically)
        await self._load_current_item_for_playback()

        # Determine whether to start playing the new track
        should_play = False

        if was_playing_before and self.keep_playing_on_track_change_if_playing_enabled:
            # If we were playing before and the setting allows it, continue
            # playing the new track
            should_play = True
            self.log.info(
                "Continuing playback with new track (was playing before and "
                "keep_playing_on_track_change_if_playing enabled)"
            )
        elif not is_initial_load and self.autoplay_on_track_change_enabled:
            # If autoplay is enabled, start playing regardless of previous state
            should_play = True
            self.log.info("Starting playback due to autoplay_on_track_change setting")
        else:
            # We were paused or keep_playing_on_track_change_if_playing is
            # disabled, stay paused
            self.log.info(
                "Keeping playback paused (was paused, autoplay disabled, or "
                "keep_playing_on_track_change_if_playing disabled)"
            )

        if should_play:
            self.playback_widget.play()
        else:
            # Ensure we're paused if we shouldn't be playing
            if self.playback_widget.is_playing():
                self.playback_widget.pause()

    def _inline_edit_active(self) -> bool:
        """True while a panel input or the new-category input is open."""
        if any(panel.input_active for panel in self.query(CategoryPanel)):
            return True
        try:
            return self._new_category_input().active
        except NoMatches:
            return False

    async def _navigate(self, direction: NavigateDirection) -> bool:
        """Navigates through the items list in the specified direction.

        Returns True if the current item changed, False if we were already at
        the end the caller asked to move past.
        """
        # TODO: Do we need this?
        # TODO: should be exception?
        if not self.item:
            return False

        # TODO: do we stop here or elsewhere?
        # self.playback_widget.stop()
        # self.log.info("Playback stopped for next item.")

        if direction == NavigateDirection.FORWARD:
            if self.current_item_index < len(self.items) - 1:
                self.current_item_index += 1
            else:
                # There is nowhere to move to, but the last item's tags would
                # otherwise never be saved (only moving off an item saves it).
                if await self._save_current_item_tags():
                    self.header_widget.show_message(
                        "All items processed. Press Esc to quit."
                    )
                return False
        elif direction == NavigateDirection.BACKWARD:
            if self.current_item_index > 0:
                self.current_item_index -= 1
            else:
                # We don't want to loop back to the last item
                return False
        else:
            # this should never happen...
            error_message = (
                f"Invalid direction: {direction}. Use "
                f"{NavigateDirection.FORWARD} (NavigateDirection.FORWARD) or "
                f"{NavigateDirection.BACKWARD} (NavigateDirection.BACKWARD)."
            )
            self.log.error(error_message)
            raise ValueError(error_message)

        await self._set_item(self.items[self.current_item_index])
        return True

    async def action_next_item(self) -> None:
        """Saves tags for the current item and moves to the next item."""
        await self._navigate(NavigateDirection.FORWARD)
        self.log.info("action_next_item called.")

    async def action_previous_item(self) -> None:
        """Saves tags for the current item and moves to the previous item."""
        await self._navigate(NavigateDirection.BACKWARD)
        self.log.info("action_previous_item called.")

    async def action_play_pause_current_item(self) -> None:
        """Toggles play/pause for the current item."""
        # might not need to check if item exists if we validate earlier
        # but the path does need to exist
        # TODO: check if path exists, probably not here though
        if not self.item or not hasattr(self.item, "path"):
            self.log.warning("No item selected or item has no path.")
            return

        self.playback_widget.play_pause()
        self.log.info("Requested play/pause for current item.")

    async def action_media_play_pause(self) -> None:
        """Play/pause from a hardware media key.

        Separate from ``play_pause_current_item`` because ``check_action``
        disables that one while an Input has focus, and media keys must keep
        working there.
        """
        await self.action_play_pause_current_item()

    async def action_pause_current_item(self) -> None:
        """Pauses the current item, keeping it loaded so play resumes it."""
        if not self.item:
            return
        self.playback_widget.pause()
        self.log.info("Requested pause for current item.")

    async def action_seek_forward(self, seconds: int = 5) -> None:
        """Seeks forward in the current track."""
        if self.item:
            self.playback_widget.seek_relative(seconds)

    async def action_seek_backward(self, seconds: int = 5) -> None:
        """Seeks backward in the current track."""
        if self.item:
            self.playback_widget.seek_relative(-seconds)

    async def on_playback_ended(self, message: PlaybackEnded) -> None:
        """Handles the PlaybackEnded message from PlaybackWidget."""
        current_generation = self.playback_widget.playback_generation
        if message.generation != current_generation:
            # EOF is only noticed on the next poll, so the user may have changed
            # track or restarted this one in the meantime; acting now would skip
            # an item or cut the new track short.
            self.log.info(
                f"Ignoring stale PlaybackEnded (generation {message.generation}, "
                f"current {current_generation})."
            )
            return

        self.log.info(
            "PlaybackEnded received. autonext_at_track_end: "
            f"{self.autonext_at_track_end_enabled}"
        )
        if not self.autonext_at_track_end_enabled:
            # The player is already stopped at the start of the track; pressing
            # play again restarts it.
            return

        self.log.info("Advancing to next item because the track ended.")
        moved = await self._navigate(NavigateDirection.FORWARD)

        if not moved:
            # _navigate saved the last item and showed the completion message;
            # replaying here would loop the track that just ended.
            self.log.info("Track ended, but already at the last item.")
            return

        # The track that just ended no longer counts as "playing", so _set_item
        # would leave the new one paused; auto-advance means keep listening.
        self.playback_widget.play()

    async def _save_current_item_tags(self) -> bool:
        """Save the current item's selections. Returns False on any failure.

        A failure is logged and shown in the header; it never propagates,
        because the save runs from track changes and quitting, where an
        exception would tear the app down.
        """
        if not self.item:
            self.log.warning("_save_current_item_tags: No item to save.")
            return True

        self.log.info(
            "_save_current_item_tags: Attempting to save tags for "
            f"{self.item.artist} - {self.item.title}"
        )
        changed = False
        ok = True
        for category_name in self.definitions.categories:
            try:
                selection_list = self._selection_list(category_name)
            except NoMatches:
                self.log.error(
                    "Could not find SelectionList for category: "
                    f"{category_name} during save."
                )
                continue

            selected = set(selection_list.selected)
            # Definition order, not click order, so the stored string is stable.
            selected_values = [
                option
                for option in self.definitions.options(category_name)
                if option in selected
            ]
            # Values the track carries that could never become options are
            # not selectable, so they must be re-added here or the write
            # below would drop them.
            selected_values.extend(self._unadoptable_values.get(category_name, []))
            try:
                written = write_item_values(self.item, category_name, selected_values)
            except Exception as error:
                # One field beets refuses must not lose the others' changes.
                self.log.error(f"Could not update {category_name}: {error}")
                self.header_widget.show_message(
                    f"Could not update '{category_name}': {error}"
                )
                ok = False
                continue
            if written:
                self.log.info(
                    f"Updating {category_name} to {selected_values!r} "
                    f"for {self.item.title}"
                )
                changed = True

        # Save comments using InputWithLabel
        try:
            comments_widget = self.query_one("#comments-input", InputWithLabel)
            new_comments = comments_widget.value
            old_comments = self.item.get(
                "comments", ""
            )  # Use get with default for comments
            if isinstance(old_comments, bytes):  # Ensure old_comments is a string
                old_comments = old_comments.decode("utf-8", "ignore")

            if old_comments != new_comments:
                self.log.info(
                    f"Updating comments from '{old_comments}' to "
                    f"'{new_comments}' for {self.item.title}"
                )
                if new_comments:
                    self.item["comments"] = new_comments
                elif "comments" in self.item:  # Only delete if it exists
                    del self.item["comments"]
                changed = True
        except NoMatches:
            self.log.error("Could not find comments input for saving.")

        if changed:
            self.log.info(
                f"Changes detected for '{self.item.artist} - "
                f"{self.item.title}'. Storing item."
            )
            try:
                self.item.store()
                self.log.info(
                    f"Successfully stored item: {self.item.artist} - {self.item.title}"
                )
            except Exception as error:
                self.log.error(
                    f"Error storing item {self.item.artist} - {self.item.title}: "
                    f"{error}"
                )
                self.header_widget.show_message(
                    f"Could not save {self.item.artist} - {self.item.title}: {error}"
                )
                return False
        else:
            self.log.info(
                f"No changes detected for '{self.item.artist} - "
                f"{self.item.title}'. Nothing to store."
            )
        return ok

    async def _load_tags_for_current_item(self) -> None:
        """Loads the tags for the current item into the selection lists."""
        # TODO: I think we should validate earlier that we have a valid items
        if not self.item:
            return

        self._unadoptable_values = {}
        adopted_any = False
        for category_name in self.definitions.categories:
            adopted_any = self._load_category_values(category_name) or adopted_any
        if adopted_any:
            # Once per track, not once per adopted value.
            self._persist_definitions()

        # Load comments using InputWithLabel
        try:
            comments_widget = self.query_one("#comments-input", InputWithLabel)
            current_comments = self.item.get(
                "comments", ""
            )  # Use get with default for comments
            if isinstance(current_comments, bytes):  # Ensure comments is a string
                current_comments = current_comments.decode("utf-8", "ignore")
            comments_widget.value = current_comments
        except NoMatches:
            self.log.error("Could not find comments input for loading.")

    def _load_category_values(self, category_name: str) -> bool:
        """Select the current track's values for ``category_name`` in its list.

        A value that is not an option yet is adopted as one, except on a
        built-in text field such as ``album``, where that would append every
        distinct value in the library to the file. Values that cannot become
        options are remembered so a save writes them back untouched.

        Returns ``True`` when the definitions changed; persisting them is
        the caller's job.
        """
        try:
            selection_list = self._selection_list(category_name)
        except NoMatches:
            self.log.error(
                "Could not find SelectionList for category: "
                f"{category_name} during load."
            )
            return False

        selection_list.deselect_all()
        self._unadoptable_values.pop(category_name, None)
        known_options = set(self.definitions.options(category_name))
        adopt = not CategoryDefinitions.is_text_field(category_name)
        adopted_any = False
        for value in read_item_values(self.item, category_name):
            if value not in known_options:
                # A value differing only by case is the known option, so
                # select that one rather than adopting a near-duplicate.
                existing = self.definitions.find_option(category_name, value)
                if existing is not None:
                    selection_list.select(existing)
                    continue
                if not adopt or not self._adopt_option(category_name, value):
                    self._unadoptable_values.setdefault(category_name, []).append(value)
                    continue
                known_options.add(value)
                adopted_any = True
            selection_list.select(value)
        selection_list.scroll_to_highlight()
        return adopted_any

    async def _reload_after_migration(self) -> None:
        """Swap the stale ``Item`` objects for fresh ones and reload the track.

        The items were loaded before the migration; saving one of them would
        write the old values straight back. Each held track is re-read by id,
        so the session keeps working through exactly the queue it was launched
        with, in the same order, whether or not a track still matches the
        query that found it (it may have been found by the value just
        deleted). A track deleted from the library meanwhile simply drops out.
        """
        if self.item is None:
            return
        ids = [item.id for item in self.items]
        by_id = {
            item.id: item for item in await self._off_loop(partial(self._fetch, ids))
        }
        fresh = [by_id[item_id] for item_id in ids if item_id in by_id]
        if not fresh:
            # Every queued track is gone from the library. The stale queue
            # is kept: saving into it is harmless (the rows no longer exist)
            # and there is nothing to show instead.
            self.header_widget.show_message(
                "None of the queued tracks are in the library any more."
            )
            return
        current_id = self.item.id
        for index, item in enumerate(fresh):
            if item.id == current_id:
                self.current_item_index = index
                break
        else:
            self.current_item_index = min(self.current_item_index, len(fresh) - 1)
        self.items = fresh
        self.item = fresh[self.current_item_index]
        self.header_widget.update_header(self.item)
        await self._load_tags_for_current_item()

    def _fetch(self, ids: list[int]) -> list[BeetsItem]:
        """Fetch tracks by id, a few hundred per query, in no particular order."""
        items: list[BeetsItem] = []
        for start in range(0, len(ids), _RELOAD_CHUNK):
            chunk = ids[start : start + _RELOAD_CHUNK]
            items.extend(self.lib.items(InQuery("id", chunk)))
        return items

    def _adopt_option(self, category_name: str, value: str) -> bool:
        """Add a value found on a track but missing from the definitions.

        Keeps the definitions a faithful mirror of the library so the value is
        not silently dropped on the next save. Returns ``False`` when the model
        refuses it (e.g. it differs from an existing option only by case).
        The definitions file is not written here; see
        :meth:`_load_tags_for_current_item`.
        """
        try:
            self.definitions.add_option(category_name, value)
        except ValueError as error:
            self.log.warning(
                f"Not adopting {value!r} into category {category_name}: {error}"
            )
            return False
        try:
            self._panel(category_name).add_option(value, select=False)
        except NoMatches:
            pass
        return True
