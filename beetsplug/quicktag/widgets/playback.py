import mpv
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget

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

        mpv_options = {
            "ytdl": False,
            "ao": "pulse",
            "cache": "yes",
            "demuxer-max-bytes": "50M",
            "demuxer-readahead-secs": "15",
            "audio-buffer": "0.5",
        }

        try:
            self.player = mpv.MPV(**mpv_options)
            self._playback_progress = PlaybackProgressWidget(player=self.player)
            self.player.observe_property("eof-reached", self._on_mpv_eof)

            # TODO: can't log from here because app is not mounted yet?
            # self.log.info(
            #     f"MPV Player initialized in PlaybackWidget with options: {mpv_options}"
            # )
        except Exception:
            # self.log.error(f"Failed to initialize MPV player in PlaybackWidget: {e}")
            self.player = None

    async def on_unmount(self) -> None:
        await self._terminate_player()

    def compose(self) -> ComposeResult:
        yield self._playback_progress

    def render(self):
        return "hi"

    def _on_mpv_eof(self, name: str, eof_reached: bool) -> None:
        if self.player and eof_reached:
            self.log.info(
                f"MPV: End of file - {self.player.filename or self._current_path or 'Unknown file'}"
            )
            self.post_message(PlaybackEnded())

    async def _terminate_player(self) -> None:
        if self.player:
            try:
                self.player.terminate()
                self.log.info("MPV player terminated from PlaybackWidget.")
            except Exception as e:
                self.log.error(f"Error terminating MPV player in PlaybackWidget: {e}")
            self.player = None
        self._current_path = None

    def load_track(self, new_path: str) -> None:
        """Loads a track for playback. Does not start playing immediately."""
        if not self.player:
            self.log.warning("MPV player not available. Cannot load track.")
            return
        if not new_path:
            self.log.warning("No path provided to load_track.")
            self.stop()  # Clear current state if path is None
            return

        if self._current_path != new_path or self.player.path != new_path:
            try:
                self.player.loadfile(new_path)  # Use loadfile to prepare the track
                self._current_path = new_path
                self.log.info(f"MPV: Loaded track {new_path}")
            except Exception as e:
                self.log.error(f"MPV: Error loading track {new_path}: {e}")
                self._current_path = None
        else:
            self.log.info(f"MPV: Track {new_path} already loaded.")

    def play(self) -> None:
        """Starts or resumes playback of the currently loaded track."""
        if not self.player:
            self.log.warning("MPV player not available for play.")
            return
        if not self._current_path:
            self.log.warning("No track loaded to play.")
            return

        try:
            if not self.player.path or self.player.path != self._current_path:
                self.player.wait_for_property("seekable")
                self.player.play(self._current_path)
                self.log.info(
                    f"MPV: Initiated play for {self._current_path} via play() method."
                )
            elif self.player.pause:
                self.player.pause = False
                self.log.info(
                    f"MPV: Resumed play for {self._current_path} via play() method."
                )
            else:
                self.log.info(
                    f"MPV: Already playing {self._current_path}. play() called."
                )
                pass
        except Exception as e:
            self.log.error(f"MPV: Error during play for {self._current_path}: {e}")

    def pause(self) -> None:
        """Pauses playback of the currently playing track."""
        if not self.player:
            self.log.warning("MPV player not available for pause.")
            return
        if not self.is_player_active() or self.player.pause:
            self.log.warning("No track playing or already paused. Cannot pause.")
            return

        try:
            self.player.pause = True
            self.log.info(
                f"MPV: Paused playback for {self._current_path}. Player pause state: {self.player.pause}"
            )
        except Exception as e:
            self.log.error(f"MPV: Error during pause for {self._current_path}: {e}")

    def play_pause(self) -> None:
        """Toggles play/pause for the currently loaded track."""
        if not self.player:
            self.log.warning("MPV player not available for play/pause.")
            return
        if not self._current_path:
            self.log.warning("No track loaded to play/pause.")
            return

        if self.is_playing():
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        if self.player and (self.player.path or self._current_path):
            self.log.info(
                f"MPV: Stopping playback for {self._current_path or self.player.filename or 'unknown file'}"
            )
            self.player.command("stop")

        self._current_path = None

    def seek_relative(self, seconds: int) -> None:
        if self.player and self.player.duration:
            self.player.seek(seconds, reference="relative")

    def is_playing(self) -> bool:
        return bool(self.player and self.player.path and not self.player.pause)

    def is_player_active(self) -> bool:
        return bool(self.player and self.player.path)
