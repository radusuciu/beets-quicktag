import os

from just_playback import Playback
from textual.app import ComposeResult
from textual.message import Message
from textual.timer import Timer
from textual.widget import Widget

from .playback_progress import PlaybackProgressWidget


class PlaybackEnded(Message):
    """Posted when playback finishes (EOF).

    `generation` identifies the playback that ended. EOF is only noticed on the
    next poll, so by the time the app handles this message the user may already
    have changed track or restarted the current one; comparing generations lets
    the handler drop such stale messages.
    """

    def __init__(self, generation: int) -> None:
        super().__init__()
        self.generation = generation


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
        # just_playback reports active=False and curr_pos=0 once a track has
        # played to completion, so end-of-track has to be detected as a
        # transition: we were playing, and now the player is inactive without
        # us having stopped, paused, or reloaded it.
        self._was_playing: bool = False
        # Bumped on every successful load and every start/resume, so a
        # PlaybackEnded posted for an earlier playback can be recognised as
        # stale. See PlaybackEnded.
        self._playback_generation: int = 0

        self.player: Playback | None
        try:
            self.player = Playback()
        except Exception:
            # No audio device (or a broken backend): keep the widget usable so
            # the rest of the UI still works, just without sound.
            self.player = None

        # Built unconditionally: compose() yields it even when there is no
        # player, and the progress widget tolerates player=None.
        self._playback_progress = PlaybackProgressWidget(player=self.player)

    @property
    def playback_generation(self) -> int:
        """Identifier of the current playback, for stale-message detection."""
        return self._playback_generation

    async def on_mount(self) -> None:
        # Start a timer to check for end-of-file conditions since
        # just_playback doesn't have property observation
        self._eof_check_timer = self.set_interval(0.5, self._check_eof)

    async def on_unmount(self) -> None:
        await self._terminate_player()

    def compose(self) -> ComposeResult:
        yield self._playback_progress

    def _check_eof(self) -> None:
        """Post PlaybackEnded once when playback stops on its own."""
        if not self.player or not self._current_path:
            return

        if self._was_playing and not self.player.active:
            self._was_playing = False
            self.log.info(f"just_playback: End of file - {self._current_path}")
            self._playback_progress.mark_ended()
            self.post_message(PlaybackEnded(self._playback_generation))
        else:
            self._was_playing = bool(self.player.playing)

    async def _terminate_player(self) -> None:
        if self._eof_check_timer:
            self._eof_check_timer.stop()
            self._eof_check_timer = None

        if self.player:
            try:
                self.player.stop()
                self.log.info("just_playback player stopped from PlaybackWidget.")
            except Exception as e:
                self.log.error(
                    f"Error stopping just_playback player in PlaybackWidget: {e}"
                )
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
            self._was_playing = False
            try:
                # load_file() raises before it tears down the current stream, so
                # check first: otherwise a missing file leaves the previous
                # track playing with no loaded path to stop it.
                if not os.path.exists(new_path):
                    raise FileNotFoundError(f"Audio file not found: {new_path}")
                self.player.load_file(new_path)
            except Exception as e:
                self._handle_load_failure(new_path, e)
                return
            self._current_path = new_path
            self._playback_generation += 1
            self._playback_progress.clear_ended()
            self.log.info(f"just_playback: Loaded track {new_path}")
        else:
            self.log.info(f"just_playback: Track {new_path} already loaded.")

    def _handle_load_failure(self, new_path: str, error: Exception) -> None:
        """Silence whatever is still playing and tell the user why."""
        self.log.error(f"just_playback: Error loading track {new_path}: {error}")

        if self.player:
            try:
                self.player.stop()
            except Exception as stop_error:
                self.log.error(
                    f"just_playback: Error stopping playback after a failed "
                    f"load of {new_path}: {stop_error}"
                )

        self._current_path = None
        self._was_playing = False
        # A failed load is still a track change: bump the generation so an EOF
        # posted for the track that was playing until now is dropped as stale
        # instead of advancing a second time.
        self._playback_generation += 1

        try:
            self.notify(
                f"Cannot load audio: {new_path}",
                title="Playback",
                severity="error",
            )
        except Exception:
            # notify() needs an active app; unmounted widgets have nowhere to
            # show the message, and the error is already logged.
            pass

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
                self._playback_generation += 1
                self.log.info(
                    f"just_playback: Resumed play for {self._current_path} "
                    "via play() method."
                )
            elif not self.player.playing:
                self.player.play()
                self._playback_generation += 1
                self.log.info(
                    f"just_playback: Started play for {self._current_path} "
                    "via play() method."
                )
            else:
                self.log.info(
                    f"just_playback: Already playing {self._current_path}. "
                    "play() called."
                )
            # Arm end-of-track detection now, so a track shorter than the poll
            # interval is still noticed by _check_eof.
            self._was_playing = True
            self._playback_progress.clear_ended()
        except Exception as e:
            self.log.error(
                f"just_playback: Error during play for {self._current_path}: {e}"
            )

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
                f"just_playback: Paused playback for {self._current_path}. "
                f"Player pause state: {self.player.paused}"
            )
        except Exception as e:
            self.log.error(
                f"just_playback: Error during pause for {self._current_path}: {e}"
            )

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
                "just_playback: Stopping playback for "
                f"{self._current_path or 'unknown file'}"
            )
            self.player.stop()

        self._was_playing = False
        self._current_path = None

    def seek_relative(self, seconds: int) -> None:
        if (
            self.player
            and hasattr(self.player, "curr_pos")
            and hasattr(self.player, "duration")
        ):
            if self.player.duration and self.player.curr_pos is not None:
                new_position = max(
                    0, min(self.player.curr_pos + seconds, self.player.duration)
                )
                try:
                    self.player.seek(new_position)
                except Exception as e:
                    self.log.error(
                        f"just_playback: Error seeking to {new_position} in "
                        f"{self._current_path}: {e}"
                    )

    def is_playing(self) -> bool:
        return bool(self.player and self.player.playing)

    def is_player_active(self) -> bool:
        return bool(self.player and self.player.active)
