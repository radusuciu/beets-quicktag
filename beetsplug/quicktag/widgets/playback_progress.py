import math

from just_playback import Playback
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import ProgressBar, Static

# TODO: update progress bar with timer


def format_seconds_to_time_str(seconds: float | None) -> str:
    """Format seconds into MM:SS string."""
    if seconds is None:
        return "--:--"
    if seconds < 0:
        seconds = 0
    total_seconds = int(math.floor(seconds))
    mins = total_seconds // 60
    secs = total_seconds % 60
    return f"{mins:02d}:{secs:02d}"


class PlaybackProgressWidget(Widget):
    DEFAULT_CSS = """
    #playback_progress_bar_container {
        layout: horizontal;
        width: 100%;
        height: 1;
    }
    #playback_progress {
        width: 1fr;
        height: 1;
    }
    #time_remaining_text {
        width: auto;
        min-width: 5; /* For MM:SS format */
        height: 1;
        padding: 0 0 0 1; /* Padding on the left of time */
        text-align: right;
    }
    """

    def __init__(self, player: Playback):
        super().__init__()
        self.player = player
        self._playback_timer: Timer | None = None
        self._progress_bar = ProgressBar(show_percentage=False, show_eta=False)
        self._time_remaining_display = Static("", id="time_remaining_text")
        # Note: just_playback doesn't have property observation, so we'll use polling

    async def on_mount(self) -> None:
        self._playback_timer = self.set_interval(1 / 2, self._update_progress_display)
        self._progress_bar.progress = 0
        self._progress_bar.total = 100

    def compose(self) -> ComposeResult:
        with Horizontal(id="playback_progress_bar_container"):
            yield self._progress_bar
            yield self._time_remaining_display

    def _update_progress_display(self, *args, **kwargs) -> None:
        if (
            self.player
            and hasattr(self.player, 'duration')
            and hasattr(self.player, 'curr_pos')
            and self.player.duration is not None
            and self.player.duration > 0
        ):
            duration = self.player.duration
            time_pos = self.player.curr_pos if self.player.curr_pos is not None else 0
            time_remaining_seconds = duration - time_pos if time_pos is not None else None

            self._progress_bar.total = duration
            self._progress_bar.progress = time_pos
            self._progress_bar.visible = True

            self._time_remaining_display.update(
                f"-{format_seconds_to_time_str(time_remaining_seconds)}"
            )
            self._time_remaining_display.visible = True

            # Check if playback has ended
            if (
                not self.player.active
                and time_pos is not None
                and time_pos >= (duration - 0.5)
            ):
                self._progress_bar.progress = self._progress_bar.total
                self._time_remaining_display.update("00:00")
                if self._playback_timer:
                    self._playback_timer.pause()
        else:
            if self._progress_bar.visible or self._time_remaining_display.visible:
                self._progress_bar.progress = 0
                self._progress_bar.total = 100
                self._progress_bar.visible = False
                self._time_remaining_display.update("")
                self._time_remaining_display.visible = False
