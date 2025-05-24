from just_playback import Playback
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.timer import Timer

from .playback_progress import PlaybackProgressWidget


class PlaybackEnded(Message):
    """Posted when playback finishes (EOF)."""

    pass


class PlaybackWidget(Widget):
    DEFAULT_CSS = """
    PlaybackWidget {
        width: 100%;
        height: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_path: str | None = None
        self._eof_check_timer: Timer | None = None

        try:
            self.player = Playback()
            self._playback_progress = PlaybackProgressWidget(player=self.player)
            # self.log.info("just_playback Player initialized in PlaybackWidget")
        except Exception:
            # self.log.error(f"Failed to initialize just_playback player in PlaybackWidget: {e}")
            self.player = None

    async def on_mount(self) -> None:
        # Start a timer to check for end-of-file conditions since just_playback doesn't have property observation
        self._eof_check_timer = self.set_interval(0.5, self._check_eof)

    async def on_unmount(self) -> None:
        await self._terminate_player()

    def compose(self) -> ComposeResult:
        yield self._playback_progress

    def render(self):
        return "hi"

    def _check_eof(self) -> None:
        """Check if playback has reached end of file and post PlaybackEnded message if so."""
        if (
            self.player
            and self._current_path
            and hasattr(self.player, 'duration')
            and hasattr(self.player, 'curr_pos')
            and self.player.duration
            and self.player.curr_pos is not None
        ):
            # Check if we've reached the end (within 0.5 seconds tolerance)
            if (
                not self.player.active
                and self.player.curr_pos >= (self.player.duration - 0.5)
            ):
                self.log.info(
                    f"just_playback: End of file - {self._current_path or 'Unknown file'}"
                )
                self.post_message(PlaybackEnded())

    async def _terminate_player(self) -> None:
        if self._eof_check_timer:
            self._eof_check_timer.stop()
            self._eof_check_timer = None
        
        if self.player:
            try:
                self.player.stop()
                self.log.info("just_playback player stopped from PlaybackWidget.")
            except Exception as e:
                self.log.error(f"Error stopping just_playback player in PlaybackWidget: {e}")
            self.player = None
        self._current_path = None

    def load_track(self, new_path: str) -> None:
        """Loads a track for playback. Does not start playing immediately."""
        if not self.player:
            self.log.warning("just_playback player not available. Cannot load track.")
            return
        if not new_path:
            self.log.warning("No path provided to load_track.")
            self.stop()  # Clear current state if path is None
            return

        if self._current_path != new_path:
            try:
                self.player.load_file(new_path)
                self._current_path = new_path
                self.log.info(f"just_playback: Loaded track {new_path}")
            except Exception as e:
                self.log.error(f"just_playback: Error loading track {new_path}: {e}")
                self._current_path = None
        else:
            self.log.info(f"just_playback: Track {new_path} already loaded.")

    def play(self) -> None:
        """Starts or resumes playback of the currently loaded track."""
        if not self.player:
            self.log.warning("just_playback player not available for play.")
            return
        if not self._current_path:
            self.log.warning("No track loaded to play.")
            return

        try:
            if self.player.paused:
                self.player.resume()
                self.log.info(
                    f"just_playback: Resumed play for {self._current_path} via play() method."
                )
            elif not self.player.playing:
                self.player.play()
                self.log.info(
                    f"just_playback: Started play for {self._current_path} via play() method."
                )
            else:
                self.log.info(
                    f"just_playback: Already playing {self._current_path}. play() called."
                )
        except Exception as e:
            self.log.error(f"just_playback: Error during play for {self._current_path}: {e}")

    def pause(self) -> None:
        """Pauses playback of the currently playing track."""
        if not self.player:
            self.log.warning("just_playback player not available for pause.")
            return
        if not self.is_player_active() or self.player.paused:
            self.log.warning("No track playing or already paused. Cannot pause.")
            return

        try:
            self.player.pause()
            self.log.info(
                f"just_playback: Paused playback for {self._current_path}. Player pause state: {self.player.paused}"
            )
        except Exception as e:
            self.log.error(f"just_playback: Error during pause for {self._current_path}: {e}")

    def play_pause(self) -> None:
        """Toggles play/pause for the currently loaded track."""
        if not self.player:
            self.log.warning("just_playback player not available for play/pause.")
            return
        if not self._current_path:
            self.log.warning("No track loaded to play/pause.")
            return

        if self.is_playing():
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        if self.player and self._current_path:
            self.log.info(
                f"just_playback: Stopping playback for {self._current_path or 'unknown file'}"
            )
            self.player.stop()

        self._current_path = None

    def seek_relative(self, seconds: int) -> None:
        if self.player and hasattr(self.player, 'curr_pos') and hasattr(self.player, 'duration'):
            if self.player.duration and self.player.curr_pos is not None:
                new_position = max(0, min(self.player.curr_pos + seconds, self.player.duration))
                self.player.seek(new_position)

    def is_playing(self) -> bool:
        return bool(self.player and self.player.playing)

    def is_player_active(self) -> bool:
        return bool(self.player and self.player.active)
