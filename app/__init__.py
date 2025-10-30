"""
YouTube Transcript & Summary Application Package
"""

# Import main classes for easy access
from .config import *
from .progress import ProgressTracker, generate_progress_stream, cancel_task_by_id
from .youtube_processor import YouTubeProcessor
from .webpage_analyzer import WebPageAnalyzer
from .video_processor import VideoProcessor

# Import the Flask app
from .app import app

__version__ = "1.0.0"
__author__ = "YouTube Transcript & Summary App"