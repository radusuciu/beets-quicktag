"""
Simplified tests for PlaybackWidget core functionality with proper mocking.

Focuses on the most critical functionality while avoiding Textual context issues.
"""

from pathlib import Path
from typing import Dict
from unittest.mock import Mock, patch

import pytest

from beetsplug.quicktag.widgets.playback import PlaybackWidget, PlaybackEnded


class TestPlaybackWidgetCore:
    """Test core PlaybackWidget functionality with minimal setup."""
    
    def test_widget_initialization_success(self):
        """Test successful widget initialization."""
        with patch('beetsplug.quicktag.widgets.playback.Playback') as mock_playback_class:
            mock_player = Mock()
            mock_playback_class.return_value = mock_player
            
            with patch.object(PlaybackWidget, 'log', Mock()):
                widget = PlaybackWidget()
                
                assert widget.player is mock_player
                assert widget._current_path is None
                assert widget._eof_check_timer is None
    
    def test_widget_initialization_failure(self):
        """Test widget initialization when Playback fails."""
        with patch('beetsplug.quicktag.widgets.playback.Playback') as mock_playback_class:
            mock_playback_class.side_effect = Exception("Playback init failed")
            
            with patch.object(PlaybackWidget, 'log', Mock()):
                widget = PlaybackWidget()
                
                assert widget.player is None
    
    def test_load_track_success(self, mp3_files: Dict[str, Path]):
        """Test loading a valid track."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            if widget.player is None:
                pytest.skip("just_playback not available")
            
            mock_player = Mock()
            widget.player = mock_player
            
            file_path = str(mp3_files['short'])
            widget.load_track(file_path)
            
            mock_player.load_file.assert_called_once_with(file_path)
            assert widget._current_path == file_path
    
    def test_load_track_with_error(self, mp3_files: Dict[str, Path]):
        """Test loading track when player raises exception."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.load_file.side_effect = Exception("Load failed")
            widget.player = mock_player
            
            file_path = str(mp3_files['short'])
            widget.load_track(file_path)
            
            mock_player.load_file.assert_called_once_with(file_path)
            assert widget._current_path is None  # Should not be set on error
    
    def test_load_track_empty_path(self):
        """Test loading track with empty path."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            widget.player = mock_player
            
            with patch.object(widget, 'stop') as mock_stop:
                widget.load_track("")
                mock_stop.assert_called_once()
                assert widget._current_path is None
    
    def test_load_track_none_path(self):
        """Test loading track with None path."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            widget.player = mock_player
            
            with patch.object(widget, 'stop') as mock_stop:
                widget.load_track(None)
                mock_stop.assert_called_once()
                assert widget._current_path is None
    
    def test_load_same_track_twice(self, mp3_files: Dict[str, Path]):
        """Test loading the same track twice doesn't reload."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            widget.player = mock_player
            
            file_path = str(mp3_files['short'])
            
            # First load
            widget.load_track(file_path)
            mock_player.load_file.assert_called_once()
            
            # Second load - should not call load_file again
            mock_player.load_file.reset_mock()
            widget.load_track(file_path)
            mock_player.load_file.assert_not_called()
    
    def test_play_with_loaded_track(self):
        """Test play when track is loaded."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.paused = False
            mock_player.playing = False
            widget.player = mock_player
            widget._current_path = "test.mp3"
            
            widget.play()
            
            mock_player.play.assert_called_once()
    
    def test_play_when_paused(self):
        """Test play when player is paused."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.paused = True
            widget.player = mock_player
            widget._current_path = "test.mp3"
            
            widget.play()
            
            mock_player.resume.assert_called_once()
            mock_player.play.assert_not_called()
    
    def test_play_already_playing(self):
        """Test play when already playing."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.paused = False
            mock_player.playing = True
            widget.player = mock_player
            widget._current_path = "test.mp3"
            
            widget.play()
            
            # Should not call play or resume
            mock_player.play.assert_not_called()
            mock_player.resume.assert_not_called()
    
    def test_pause_when_playing(self):
        """Test pause when playing."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.paused = False
            widget.player = mock_player
            
            with patch.object(widget, 'is_player_active', return_value=True):
                widget.pause()
                mock_player.pause.assert_called_once()
    
    def test_pause_when_already_paused(self):
        """Test pause when already paused."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.paused = True
            widget.player = mock_player
            
            widget.pause()
            
            # Should not call pause again
            mock_player.pause.assert_not_called()
    
    def test_play_pause_toggle(self):
        """Test play_pause toggles correctly."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            widget.player = mock_player
            widget._current_path = "test.mp3"
            
            # Test play when not playing
            with patch.object(widget, 'is_playing', return_value=False):
                with patch.object(widget, 'play') as mock_play:
                    widget.play_pause()
                    mock_play.assert_called_once()
            
            # Test pause when playing
            with patch.object(widget, 'is_playing', return_value=True):
                with patch.object(widget, 'pause') as mock_pause:
                    widget.play_pause()
                    mock_pause.assert_called_once()
    
    def test_stop_functionality(self):
        """Test stop functionality."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            widget.player = mock_player
            widget._current_path = "test.mp3"
            
            widget.stop()
            
            mock_player.stop.assert_called_once()
            assert widget._current_path is None
    
    def test_seek_relative_forward(self):
        """Test seeking forward."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.duration = 30.0
            mock_player.curr_pos = 10.0
            widget.player = mock_player
            
            widget.seek_relative(5)
            
            mock_player.seek.assert_called_once_with(15.0)
    
    def test_seek_relative_backward(self):
        """Test seeking backward."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.duration = 30.0
            mock_player.curr_pos = 10.0
            widget.player = mock_player
            
            widget.seek_relative(-5)
            
            mock_player.seek.assert_called_once_with(5.0)
    
    def test_seek_beyond_bounds(self):
        """Test seeking beyond track boundaries."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.duration = 30.0
            mock_player.curr_pos = 25.0
            widget.player = mock_player
            
            # Seek beyond end
            widget.seek_relative(10)
            mock_player.seek.assert_called_with(30.0)  # Clamped to duration
            
            mock_player.reset_mock()
            mock_player.curr_pos = 5.0
            
            # Seek before beginning
            widget.seek_relative(-10)
            mock_player.seek.assert_called_with(0.0)  # Clamped to 0
    
    def test_eof_detection_at_end(self):
        """Test EOF detection when at end of track."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.duration = 30.0
            mock_player.curr_pos = 29.6  # Within 0.5s of end
            mock_player.active = False
            widget.player = mock_player
            widget._current_path = "test.mp3"
            
            with patch.object(widget, 'post_message') as mock_post:
                widget._check_eof()
                
                mock_post.assert_called_once()
                args, kwargs = mock_post.call_args
                assert isinstance(args[0], PlaybackEnded)
    
    def test_eof_detection_not_at_end(self):
        """Test EOF detection when not at end."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.duration = 30.0
            mock_player.curr_pos = 15.0  # Middle of track
            mock_player.active = False
            widget.player = mock_player
            widget._current_path = "test.mp3"
            
            with patch.object(widget, 'post_message') as mock_post:
                widget._check_eof()
                mock_post.assert_not_called()
    
    def test_eof_detection_still_active(self):
        """Test EOF detection when player still active."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_player.duration = 30.0
            mock_player.curr_pos = 29.6  # Near end
            mock_player.active = True  # Still active
            widget.player = mock_player
            widget._current_path = "test.mp3"
            
            with patch.object(widget, 'post_message') as mock_post:
                widget._check_eof()
                mock_post.assert_not_called()
    
    def test_is_playing_state(self):
        """Test is_playing method."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            # No player
            widget.player = None
            assert widget.is_playing() is False
            
            # Player not playing
            mock_player = Mock()
            mock_player.playing = False
            widget.player = mock_player
            assert widget.is_playing() is False
            
            # Player playing
            mock_player.playing = True
            assert widget.is_playing() is True
    
    def test_is_player_active_state(self):
        """Test is_player_active method."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            # No player
            widget.player = None
            assert widget.is_player_active() is False
            
            # Player not active
            mock_player = Mock()
            mock_player.active = False
            widget.player = mock_player
            assert widget.is_player_active() is False
            
            # Player active
            mock_player.active = True
            assert widget.is_player_active() is True
    
    @pytest.mark.asyncio
    async def test_terminate_player(self):
        """Test player termination."""
        with patch.object(PlaybackWidget, 'log', Mock()):
            widget = PlaybackWidget()
            
            mock_player = Mock()
            mock_timer = Mock()
            widget.player = mock_player
            widget._current_path = "test.mp3"
            widget._eof_check_timer = mock_timer
            
            await widget._terminate_player()
            
            mock_timer.stop.assert_called_once()
            mock_player.stop.assert_called_once()
            assert widget.player is None
            assert widget._current_path is None
            assert widget._eof_check_timer is None