"""
Tests for PlaybackProgressWidget functionality.

Covers:
- Progress display and time formatting
- Timer management and updates
- Edge cases with duration and position values
- Widget lifecycle and cleanup
"""

from unittest.mock import Mock, patch
import pytest
from just_playback import Playback

from beetsplug.quicktag.widgets.playback_progress import (
    PlaybackProgressWidget, 
    format_seconds_to_time_str
)


class TestTimeFormatting:
    """Test time formatting utility function."""
    
    def test_format_seconds_basic(self):
        """Test basic time formatting."""
        assert format_seconds_to_time_str(0) == "00:00"
        assert format_seconds_to_time_str(30) == "00:30"
        assert format_seconds_to_time_str(60) == "01:00"
        assert format_seconds_to_time_str(90) == "01:30"
        assert format_seconds_to_time_str(3661) == "61:01"  # Over 1 hour
    
    def test_format_seconds_edge_cases(self):
        """Test edge cases in time formatting."""
        assert format_seconds_to_time_str(None) == "--:--"
        assert format_seconds_to_time_str(-1) == "00:00"  # Negative should become 0
        assert format_seconds_to_time_str(-100) == "00:00"
        assert format_seconds_to_time_str(0.5) == "00:00"  # Fractional rounds down
        assert format_seconds_to_time_str(59.9) == "00:59"
    
    def test_format_seconds_large_values(self):
        """Test formatting with large time values."""
        assert format_seconds_to_time_str(3600) == "60:00"  # 1 hour
        assert format_seconds_to_time_str(7200) == "120:00"  # 2 hours
        assert format_seconds_to_time_str(9999) == "166:39"  # Very large


class TestPlaybackProgressWidget:
    """Test PlaybackProgressWidget functionality."""
    
    def test_widget_initialization(self):
        """Test widget initializes correctly."""
        mock_player = Mock(spec=Playback)
        widget = PlaybackProgressWidget(mock_player)
        
        assert widget.player is mock_player
        assert widget._playback_timer is None
        assert widget._progress_bar is not None
        assert widget._time_remaining_display is not None
    
    @pytest.mark.asyncio
    async def test_on_mount_timer_setup(self):
        """Test timer setup on widget mount."""
        mock_player = Mock(spec=Playback)
        widget = PlaybackProgressWidget(mock_player)
        
        with patch.object(widget, 'set_interval') as mock_set_interval:
            await widget.on_mount()
            
            mock_set_interval.assert_called_once_with(0.5, widget._update_progress_display)
            assert widget._progress_bar.progress == 0
            assert widget._progress_bar.total == 100
    
    def test_update_progress_display_normal_playback(self):
        """Test progress display updates during normal playback."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 30.0
        mock_player.curr_pos = 10.0
        
        widget = PlaybackProgressWidget(mock_player)
        
        # Mock the progress bar and time display
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        widget._update_progress_display()
        
        # Verify progress bar updates
        assert widget._progress_bar.total == 30.0
        assert widget._progress_bar.progress == 10.0
        assert widget._progress_bar.visible is True
        
        # Verify time display updates (30 - 10 = 20 seconds remaining)
        widget._time_remaining_display.update.assert_called_once_with("-00:20")
        assert widget._time_remaining_display.visible is True
    
    def test_update_progress_display_no_duration(self):
        """Test progress display when duration is not available."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = None
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        # Set initial visibility to True to test hiding
        widget._progress_bar.visible = True
        widget._time_remaining_display.visible = True
        
        widget._update_progress_display()
        
        # Should hide progress elements
        assert widget._progress_bar.visible is False
        assert widget._time_remaining_display.visible is False
        widget._time_remaining_display.update.assert_called_once_with("")
    
    def test_update_progress_display_zero_duration(self):
        """Test progress display with zero duration."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 0.0
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        # Set initial visibility to True to test hiding
        widget._progress_bar.visible = True
        widget._time_remaining_display.visible = True
        
        widget._update_progress_display()
        
        # Should hide progress elements when duration is 0
        assert widget._progress_bar.visible is False
        assert widget._time_remaining_display.visible is False
    
    def test_update_progress_display_no_current_position(self):
        """Test progress display when current position is None."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 30.0
        mock_player.curr_pos = None
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        widget._update_progress_display()
        
        # Should use 0 as default position
        assert widget._progress_bar.progress == 0
        widget._time_remaining_display.update.assert_called_once_with("-00:30")
    
    def test_update_progress_display_end_of_track(self):
        """Test progress display at end of track."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 30.0
        mock_player.curr_pos = 29.6  # Within 0.5s of end
        mock_player.active = False
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        widget._playback_timer = Mock()
        
        widget._update_progress_display()
        
        # Should set progress bar values
        assert widget._progress_bar.total == 30.0
        # At end of track, progress should be set to total (line 90 in implementation)
        assert widget._progress_bar.progress == 30.0  # Set to total at end
        widget._time_remaining_display.update.assert_called_with("00:00")  # Shows 00:00 at end
        widget._playback_timer.pause.assert_called_once()
    
    def test_update_progress_display_player_still_active_at_end(self):
        """Test progress display when near end but player still active."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 30.0
        mock_player.curr_pos = 29.6  # Within 0.5s of end
        mock_player.active = True  # Still active
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        widget._playback_timer = Mock()
        
        widget._update_progress_display()
        
        # Should NOT pause timer or show 00:00 if still active
        widget._playback_timer.pause.assert_not_called()
        # Should show actual remaining time
        widget._time_remaining_display.update.assert_called_once_with("-00:00")
    
    def test_update_progress_display_missing_attributes(self):
        """Test progress display when player lacks required attributes."""
        mock_player = Mock()
        # Set duration to None to trigger the else clause
        mock_player.duration = None
        mock_player.curr_pos = None
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        # Set initial visibility to True to test hiding
        widget._progress_bar.visible = True
        widget._time_remaining_display.visible = True
        
        widget._update_progress_display()
        
        # Should hide progress elements
        assert widget._progress_bar.visible is False
        assert widget._time_remaining_display.visible is False
        widget._time_remaining_display.update.assert_called_once_with("")


class TestPlaybackProgressWidgetEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_update_with_negative_position(self):
        """Test handling of negative current position."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 30.0
        mock_player.curr_pos = -5.0  # Invalid negative position
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        widget._update_progress_display()
        
        # Should handle gracefully
        assert widget._progress_bar.progress == -5.0  # Passes through as-is
        # Time remaining calculation: 30 - (-5) = 35
        widget._time_remaining_display.update.assert_called_once_with("-00:35")
    
    def test_update_with_position_beyond_duration(self):
        """Test handling when position exceeds duration."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 30.0
        mock_player.curr_pos = 35.0  # Beyond duration
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        widget._update_progress_display()
        
        # Should handle gracefully
        assert widget._progress_bar.progress == 35.0
        # Time remaining: 30 - 35 = -5 (negative remaining)
        widget._time_remaining_display.update.assert_called_once_with("-00:00")  # format_seconds handles negative
    
    def test_update_with_very_large_duration(self):
        """Test handling of very large duration values."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 7200.0  # 2 hours
        mock_player.curr_pos = 3600.0   # 1 hour
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        widget._update_progress_display()
        
        # Should handle large values correctly
        assert widget._progress_bar.total == 7200.0
        assert widget._progress_bar.progress == 3600.0
        # Remaining: 7200 - 3600 = 3600 seconds = 1 hour
        widget._time_remaining_display.update.assert_called_once_with("-60:00")
    
    def test_rapid_updates(self):
        """Test handling of rapid progress updates."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 30.0
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        # Simulate rapid position changes
        positions = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
        for pos in positions:
            mock_player.curr_pos = pos
            widget._update_progress_display()
        
        # Should handle all updates without issues
        assert widget._progress_bar.progress == 30.0
        assert widget._time_remaining_display.update.call_count == len(positions)
    
    def test_timer_cleanup_scenarios(self):
        """Test timer cleanup in various scenarios."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 30.0
        mock_player.curr_pos = 29.8
        mock_player.active = False
        
        widget = PlaybackProgressWidget(mock_player)
        
        # Test with no timer
        widget._playback_timer = None
        widget._update_progress_display()  # Should not crash
        
        # Test with timer
        widget._playback_timer = Mock()
        widget._update_progress_display()
        widget._playback_timer.pause.assert_called_once()
    
    def test_visibility_state_changes(self):
        """Test progress bar visibility state changes."""
        mock_player = Mock(spec=Playback)
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        # Start with no duration (hidden state)
        mock_player.duration = None
        widget._progress_bar.visible = True
        widget._time_remaining_display.visible = True
        
        widget._update_progress_display()
        
        # Should be hidden now
        assert widget._progress_bar.visible is False
        assert widget._time_remaining_display.visible is False
        
        # Now add duration (should become visible)
        mock_player.duration = 30.0
        mock_player.curr_pos = 10.0
        widget._progress_bar.visible = False
        widget._time_remaining_display.visible = False
        
        widget._update_progress_display()
        
        # Should be visible now
        assert widget._progress_bar.visible is True
        assert widget._time_remaining_display.visible is True


class TestPlaybackProgressWidgetIntegration:
    """Test integration scenarios with realistic player behavior."""
    
    def test_full_playback_simulation(self):
        """Simulate a full playback session with progress updates."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 10.0
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        # Simulate playback progression
        time_points = [0.0, 2.5, 5.0, 7.5, 9.5, 10.0]
        
        for pos in time_points:
            mock_player.curr_pos = pos
            mock_player.active = pos < 10.0  # Not active when at end
            
            widget._update_progress_display()
            
            assert widget._progress_bar.progress == pos
            # Note: The actual call will be f"-{expected_remaining[i]}"
        
        # Verify final state
        assert widget._progress_bar.progress == 10.0
    
    def test_seek_during_playback(self):
        """Test progress updates during seek operations."""
        mock_player = Mock(spec=Playback)
        mock_player.duration = 30.0
        
        widget = PlaybackProgressWidget(mock_player)
        widget._progress_bar = Mock()
        widget._time_remaining_display = Mock()
        
        # Normal playback
        mock_player.curr_pos = 10.0
        widget._update_progress_display()
        assert widget._progress_bar.progress == 10.0
        
        # Simulate seek forward
        mock_player.curr_pos = 20.0
        widget._update_progress_display()
        assert widget._progress_bar.progress == 20.0
        
        # Simulate seek backward
        mock_player.curr_pos = 5.0
        widget._update_progress_display()
        assert widget._progress_bar.progress == 5.0