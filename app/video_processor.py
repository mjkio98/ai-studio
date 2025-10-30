"""
Video processing module for YouTube Shorts generation.
Handles video download, analysis, and clip extraction with optimized resource management.
"""

import os
import tempfile
import shutil
import time
import json
import re
from urllib.parse import urlparse, parse_qs
import yt_dlp
from moviepy.editor import VideoFileClip
import threading
from concurrent.futures import ThreadPoolExecutor
import subprocess
import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
from .config import LANGUAGE_TEMPLATES
from .tor_youtube_extractor import TorYouTubeExtractor

# Global memory store for video clips
video_clips_memory_store = {}

class VideoProcessor:
    def __init__(self):
        self.temp_dir = None
        self.cleanup_files = []
        self.max_duration = 10800  # 3 hours max - suitable for long-form content like podcasts, lectures
        self.max_file_size = 500 * 1024 * 1024  # 500MB max
        self.target_resolution = (1280, 720)  # 720p for faster processing
        
        # Initialize Tor YouTube extractor for IP rotation
        self.tor_extractor = TorYouTubeExtractor()
        
        # Initialize face detection
        try:
            # Try to load OpenCV face detection cascade
            self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            
            # Verify the cascade loaded properly
            if self.face_cascade.empty():
                raise Exception("Face cascade failed to load")
                
            self.person_detection_enabled = True
            print("✅ Face detection initialized successfully")
        except Exception as e:
            print(f"⚠️ Face detection not available: {e}")
            self.face_cascade = None
            self.person_detection_enabled = False
    
    def detect_face_position(self, video_url: str, start_time: float, sample_duration: float = 3.0) -> Optional[Tuple[float, float]]:
        """
        Detect the position of faces/people in a video segment to determine optimal crop area.
        Returns (normalized_x, normalized_y) of detected faces, or None if no faces found.
        """
        if not self.person_detection_enabled:
            print(f"⚠️ Face detection disabled - using center crop")
            return None
            
        try:
            print(f"🔍 Analyzing face positions in video segment (start: {start_time}s)...")
            
            # Create temporary file for analysis
            temp_analysis_file = tempfile.mktemp(suffix='.mp4')
            
            # Extract a longer segment for analysis - get more frames for better face detection
            analysis_cmd = [
                'ffmpeg', '-y', '-loglevel', 'quiet',  # Suppress verbose output
                '-ss', str(start_time),
                '-i', video_url,
                '-t', '5.0',  # Longer duration for more frames
                '-vf', 'scale=320:180',  # Even smaller for faster processing
                '-r', '2',  # 2 fps for more frames (5s * 2fps = 10 frames)
                '-an',  # No audio
                '-f', 'mp4',  # Force MP4 format
                '-movflags', '+faststart',  # Optimize for quick access
                temp_analysis_file
            ]
            
            # Use longer timeout for reliable face analysis
            try:
                print(f"   🔧 Running FFmpeg analysis command...")
                result = subprocess.run(analysis_cmd, capture_output=True, timeout=30, text=True)
            except subprocess.TimeoutExpired:
                print(f"⚠️ Face analysis timeout (30s) - using center crop")
                return None
            
            if result.returncode != 0:
                print(f"⚠️ Face analysis FFmpeg failed (code: {result.returncode}) - using center crop")
                if result.stderr:
                    # Show specific error to help debug
                    error_msg = result.stderr.strip()
                    if "Protocol not found" in error_msg:
                        print(f"   🔍 Issue: HLS protocol not supported")
                    elif "Invalid data found" in error_msg:
                        print(f"   🔍 Issue: Stream data format problem")
                    elif "Connection refused" in error_msg or "Network" in error_msg:
                        print(f"   🔍 Issue: Network connectivity problem")
                    else:
                        print(f"   🔍 FFmpeg error: {error_msg[:150]}...")
                return None
                
            if not os.path.exists(temp_analysis_file):
                print(f"⚠️ Analysis file not created - using center crop")
                return None
            
            # Check file size
            file_size = os.path.getsize(temp_analysis_file)
            if file_size < 500:  # Less than 500 bytes
                print(f"⚠️ Analysis file too small ({file_size} bytes) - using center crop")
                if os.path.exists(temp_analysis_file):
                    os.unlink(temp_analysis_file)
                return None
            
            print(f"📊 Analysis file created: {file_size} bytes - analyzing frames...")
            
            # Quick frame analysis
            cap = cv2.VideoCapture(temp_analysis_file)
            if not cap.isOpened():
                print(f"⚠️ Could not open analysis file - using center crop")
                if os.path.exists(temp_analysis_file):
                    os.unlink(temp_analysis_file)
                return None
                
            face_positions = []
            frame_count = 0
            max_frames = 10  # Analyze more frames for better face detection reliability
            
            while cap.isOpened() and frame_count < max_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                    
                # Convert to grayscale for face detection
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Detect faces with relaxed parameters for speed
                faces = self.face_cascade.detectMultiScale(
                    gray, 
                    scaleFactor=1.3,      # Faster scaling
                    minNeighbors=2,       # Lower threshold
                    minSize=(15, 15),     # Smaller minimum size
                    maxSize=(150, 150)    # Reasonable maximum
                )
                
                # Take the largest face if multiple found
                if len(faces) > 0:
                    largest_face = max(faces, key=lambda face: face[2] * face[3])
                    x, y, w, h = largest_face
                    
                    face_center_x = x + w // 2
                    face_center_y = y + h // 2
                    face_positions.append((face_center_x, face_center_y))
                    
                    print(f"   📍 Frame {frame_count}: Face at ({face_center_x}, {face_center_y}) size {w}x{h}")
                
                frame_count += 1
            
            cap.release()
            
            # Clean up temp file
            if os.path.exists(temp_analysis_file):
                os.unlink(temp_analysis_file)
            
            if face_positions:
                # Calculate average face position
                avg_x = np.mean([pos[0] for pos in face_positions])
                avg_y = np.mean([pos[1] for pos in face_positions])
                
                # Convert from analysis resolution (320x180) to normalized coordinates
                normalized_x = avg_x / 320.0
                normalized_y = avg_y / 180.0
                
                # Clamp to valid range
                normalized_x = max(0.0, min(1.0, normalized_x))
                normalized_y = max(0.0, min(1.0, normalized_y))
                
                print(f"✅ Face detected! Position: ({avg_x:.1f}, {avg_y:.1f}) -> Normalized: ({normalized_x:.2f}, {normalized_y:.2f})")
                return (normalized_x, normalized_y)
            else:
                print(f"ℹ️ No faces found in {frame_count} frames - using center crop")
                return None
                
        except Exception as e:
            print(f"⚠️ Face detection error: {str(e)[:100]}... - using center crop")
            return None
        
    def __enter__(self):
        """Context manager entry - create temp directory"""
        self.temp_dir = tempfile.mkdtemp(prefix="youtube_shorts_")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup all temp files"""
        self.cleanup_temp_files()
        
    def cleanup_temp_files(self):
        """Clean up all temporary files and directories"""
        try:
            # Check memory store before cleanup
            global video_clips_memory_store
            clips_with_thumbnails = [clip_id for clip_id, data in video_clips_memory_store.items() 
                                   if 'thumbnail' in data and data['thumbnail']]
            print(f"🔍 [CLEANUP DEBUG] Before cleanup - Clips with thumbnails: {clips_with_thumbnails}")
            
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                print(f"🧹 Cleaned up temp directory: {self.temp_dir}")
            
            # Check memory store after cleanup
            clips_with_thumbnails_after = [clip_id for clip_id, data in video_clips_memory_store.items() 
                                         if 'thumbnail' in data and data['thumbnail']]
            print(f"🔍 [CLEANUP DEBUG] After cleanup - Clips with thumbnails: {clips_with_thumbnails_after}")
            
            if len(clips_with_thumbnails) != len(clips_with_thumbnails_after):
                print(f"❌ [CLEANUP DEBUG] WARNING: Thumbnails were lost during cleanup!")
            else:
                print(f"✅ [CLEANUP DEBUG] Thumbnails preserved after cleanup")
            
            # Clean up individual files tracked in cleanup_files
            for file_path in self.cleanup_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"🧹 Cleaned up file: {file_path}")
                except Exception as e:
                    print(f"⚠️ Could not clean up {file_path}: {e}")
                    
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")
    
    def extract_video_id(self, url):
        """Extract YouTube video ID from URL"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
            r'youtube\.com\/watch\?.*v=([^&\n?#]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def get_video_info_safe(self, video_url, progress=None):
        """Safely get video information without downloading"""
        try:
            if progress:
                progress.update('info', 10, 'Getting video information via Tor...')
            
            print("\n" + "🔍" * 30)
            print("📹 VIDEO INFO EXTRACTION - USING TOR")
            print(f"🎯 Requesting video info for: {video_url[:60]}...")
            print("🔒 Method: Tor-enabled extraction with IP rotation")
            print("🔍" * 30)
            
            # Use Tor-enabled extractor for IP rotation
            info = self.tor_extractor.extract_video_info_with_tor(video_url, extract_info_only=True)
            
            print("✅ Video info received from Tor extractor")
            print(f"📊 Video Title: {info.get('title', 'Unknown')[:50]}...")
            print(f"⏱️  Duration: {info.get('duration', 0)}s")
            
            # Check video constraints
            duration = info.get('duration', 0)
            if duration > self.max_duration:
                raise Exception(f"Video too long ({duration//60}min). Maximum allowed: {self.max_duration//60}min")
            
            video_info = {
                'id': info.get('id'),
                'title': info.get('title', 'Unknown'),
                'duration': duration,
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'thumbnail': info.get('thumbnail'),
                'description': info.get('description', '')[:500] + '...' if info.get('description', '') else ''
            }
            
            return video_info
                
        except Exception as e:
            raise Exception(f"Failed to get video info: {str(e)}")
    
    def get_video_stream_info(self, video_url, progress=None):
        """Get video stream URL without downloading the file"""
        try:
            if progress:
                progress.update('stream_info', 20, 'Getting video stream information via Tor...')
            
            print("\n" + "🎬" * 30)
            print("📺 VIDEO STREAM EXTRACTION - USING TOR")
            print(f"🎯 Getting stream URLs for: {video_url[:60]}...")
            print("🔒 Method: Tor-enabled extraction with IP rotation")
            print("🎬" * 30)
            
            # Use Tor-enabled extractor for IP rotation
            info = self.tor_extractor.extract_video_info_with_tor(video_url, extract_info_only=False)
            
            print("✅ Stream info received from Tor extractor")
            
            # Get the best format URL for streaming
            if 'url' in info:
                stream_url = info['url']
            elif 'formats' in info and info['formats']:
                # Find the best quality format
                for format_info in reversed(info['formats']):
                    if format_info.get('url') and format_info.get('height', 0) <= 720:
                        stream_url = format_info['url']
                        break
                else:
                    stream_url = info['formats'][-1]['url']
            else:
                raise Exception("No suitable video stream found")
                
                if progress:
                    progress.update('stream_ready', 35, 'Video stream ready for processing')
                
                return stream_url, info
            
        except Exception as e:
            raise Exception(f"Failed to get video stream: {str(e)}")
    
    def find_natural_ending_point(self, transcript, start_time, ideal_end_time, max_end_time, words_per_second=1.5):
        """Find the best natural ending point for a clip based on speech patterns"""
        try:
            # Convert times to word positions (approximate)
            start_word_pos = int(start_time * words_per_second)
            ideal_end_pos = int(ideal_end_time * words_per_second)
            max_end_pos = int(max_end_time * words_per_second)
            
            # Handle both timestamped and plain text transcript formats
            if isinstance(transcript, list) and len(transcript) > 0 and isinstance(transcript[0], dict):
                # Extract text from timestamped format
                transcript_text = ' '.join([seg['text'] for seg in transcript])
            else:
                # Use as plain text
                transcript_text = transcript
            
            # Split transcript into words
            words = transcript_text.split()
            total_words = len(words)
            
            # Ensure positions are within bounds
            start_word_pos = max(0, min(start_word_pos, total_words - 1))
            ideal_end_pos = max(start_word_pos + 10, min(ideal_end_pos, total_words - 1))
            max_end_pos = max(ideal_end_pos + 5, min(max_end_pos, total_words - 1))
            
            # Look for natural ending indicators in the search window
            search_text = ' '.join(words[start_word_pos:max_end_pos + 1]).lower()
            search_window = words[ideal_end_pos:max_end_pos + 1]
            
            # Natural ending patterns (in order of preference)
            ending_patterns = [
                # Complete thoughts and conclusions
                (r'\b(that\'s why|that\'s how|that\'s the|so remember|in conclusion|to summarize)\b.*?[.!]', 5),
                (r'\b(the key is|the point is|what matters|the secret)\b.*?[.!]', 4),
                (r'\b(so there you have it|that\'s it|there you go|that\'s the deal)\b', 5),
                
                # Numbered points completion
                (r'\b(number \w+|point \w+|step \w+|thing \w+)\b.*?[.!]', 4),
                (r'\b(first|second|third|fourth|fifth|finally)\b.*?[.!]', 3),
                
                # Strong punctuation endings
                (r'[.!]\s*$', 3),
                (r'[.!]\s+\w', 2),
                
                # Question completion
                (r'\?\s*$', 3),
                (r'\?\s+\w', 2),
                
                # Natural pauses
                (r'\b(okay|alright|now|so|well|right)\b[.!,]?$', 1),
            ]
            
            best_end_pos = ideal_end_pos
            best_score = 0
            
            # Search for the best ending point
            for i in range(ideal_end_pos, max_end_pos + 1):
                if i >= total_words:
                    break
                    
                # Get text segment for analysis
                segment = ' '.join(words[ideal_end_pos:i + 1]).lower()
                score = 0
                
                # Check for ending patterns
                for pattern, pattern_score in ending_patterns:
                    if re.search(pattern, segment):
                        score += pattern_score
                        break
                
                # Bonus for being closer to ideal length
                distance_penalty = abs(i - ideal_end_pos) * 0.1
                final_score = score - distance_penalty
                
                if final_score > best_score:
                    best_score = final_score
                    best_end_pos = i
            
            # Convert back to time
            natural_end_time = best_end_pos / words_per_second
            
            # Ensure minimum and maximum bounds
            natural_end_time = max(start_time + 25, min(natural_end_time, max_end_time))
            
            print(f"🎯 Natural ending found: {natural_end_time:.1f}s (was {ideal_end_time:.1f}s)")
            return natural_end_time
            
        except Exception as e:
            print(f"⚠️ Error finding natural ending: {e}")
            # Fallback to ideal time if analysis fails
            return min(ideal_end_time, max_end_time)
    
    def analyze_transcript_for_clips(self, transcript, language='en', progress=None):
        """Use AI to analyze transcript and identify best segments for shorts
        
        Args:
            transcript: Either a string (plain text) OR list of dicts with timestamps
                       [{'start': 1.36, 'duration': 1.68, 'end': 3.04, 'text': '...'}]
            language: Language code ('en' or 'ar')
            progress: Progress tracker
        """
        try:
            print(f"🔍 DEBUG: Starting transcript analysis for shorts")
            if progress:
                progress.update('analysis', 45, 'Analyzing content for best clips...')
            
            # Detect if we have timestamped data or plain text
            has_timestamps = isinstance(transcript, list) and len(transcript) > 0 and isinstance(transcript[0], dict)
            
            if has_timestamps:
                print(f"✅ Using TIMESTAMPED transcript with {len(transcript)} segments")
                # Extract plain text for AI analysis
                transcript_text = ' '.join([seg['text'] for seg in transcript])
                
                # Calculate actual video duration from timestamps
                last_segment = transcript[-1]
                actual_duration_seconds = last_segment['end']
                estimated_duration_minutes = actual_duration_seconds / 60
                
                print(f"📊 Accurate video info from timestamps:")
                print(f"   Total segments: {len(transcript)}")
                print(f"   Exact duration: {int(actual_duration_seconds // 60)}:{int(actual_duration_seconds % 60):02d}")
                print(f"   Average segment: {sum(s['duration'] for s in transcript) / len(transcript):.2f}s")
            else:
                print(f"⚠️ Using PLAIN TEXT transcript (no timestamps)")
                transcript_text = transcript
                
                # Estimate duration from word count
                words = transcript_text.split()
                total_words = len(words)
                estimated_duration_minutes = max(1.0, total_words / 150)  # 150 words per minute average
                
                print(f"📊 Estimated video info from word count:")
                print(f"   Total words: {total_words}")
                print(f"   Estimated duration: {estimated_duration_minutes:.1f} minutes")
            
            print(f"🔍 DEBUG: Importing YouTubeProcessor")
            # Import here to avoid circular imports
            from .youtube_processor import YouTubeProcessor
            
            processor = YouTubeProcessor()
            print(f"🔍 DEBUG: YouTubeProcessor initialized")
            
            # Get language-specific template for shorts analysis
            if language in LANGUAGE_TEMPLATES:
                template = LANGUAGE_TEMPLATES[language].get('shorts_template', LANGUAGE_TEMPLATES['en']['shorts_template'])
            else:
                template = LANGUAGE_TEMPLATES['en']['shorts_template']

            # Determine optimal clip count based on duration
            if estimated_duration_minutes < 2:
                suggested_clips = "1-2"
                max_clips = 2
            elif estimated_duration_minutes < 5:
                suggested_clips = "2-4" 
                max_clips = 4
            else:
                suggested_clips = "3-5"
                max_clips = 5
            
            print(f"🔍 DEBUG: Duration: {estimated_duration_minutes:.1f} minutes, suggesting {suggested_clips} clips")
            
            # Use transcript_text for AI prompt
            total_words = len(transcript_text.split())
            
            prompt = f"""{template}

📊 VIDEO INFO:
- Duration: ~{estimated_duration_minutes:.1f} minutes
- Suggested clip count: {suggested_clips} clips (prioritize quality over quantity)
- Word count: {total_words} words
- Timestamps available: {'YES - Use exact times' if has_timestamps else 'NO - Estimate times'}

Transcript:
{transcript_text}

🎯 CRITICAL INSTRUCTIONS: 
- Create {suggested_clips} clips maximum
- MANDATORY: NO clips before 60 seconds (skip intro completely)
- MANDATORY: Find CLIMAX moments, not setup/intro content  
- MANDATORY: Spread clips across video timeline (never cluster)
- Focus on VIRAL peaks: revelations, punchlines, emotional climax, conclusions
- Better to have 1 amazing clip than 3 mediocre ones from the beginning

Analysis (return valid JSON only):"""

            print(f"🔍 DEBUG: Prompt prepared, length: {len(prompt)} characters")
            if progress:
                progress.update('ai_analysis', 40, 'AI analyzing content...')
                
                # STRATEGIC BREAKPOINT: Before expensive AI call (perfect stopping point!)
                if progress.check_stop_at_breakpoint():
                    print(f"🛑 CANCELLED: Task stopped before AI analysis")
                    return None
            
            print(f"🔍 DEBUG: Calling make_ai_request_with_fallback...")
            # Make AI request
            response = processor.make_ai_request_with_fallback(prompt, progress, language, stream=False)
            print(f"🔍 DEBUG: AI request completed, processing response...")
            analysis_result = response.choices[0].message.content
            print(f"🔍 DEBUG: Analysis result length: {len(analysis_result)} characters")
            print(f"🔍 DEBUG: Full AI response:")
            print(f"{'='*50}")
            print(analysis_result)
            print(f"{'='*50}")
            
            # Parse JSON response
            try:
                # Clean the response to extract JSON
                json_start = analysis_result.find('{')
                json_end = analysis_result.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = analysis_result[json_start:json_end]
                    clips_data = json.loads(json_str)
                    clips = clips_data.get('clips', [])
                    
                    print(f"✅ AI analysis successful! Found {len(clips)} clips")
                    
                    # ENHANCED VALIDATION: Strict checks for engagement and distribution
                    if len(clips) > 0:
                        # Rule 1: ABSOLUTELY NO clips in first 60 seconds
                        early_clips = [clip for clip in clips if clip['start_time'] < 60]
                        if early_clips:
                            clip_times = [f"{clip['start_time']}s" for clip in early_clips]
                            raise ValueError(
                                f"AI selected clips from the first minute ({', '.join(clip_times)}), which is typically intro/setup content. "
                                "The AI failed to find truly engaging peak moments. "
                                "Please try a video with clearer climactic moments or dramatic peaks."
                            )
                        
                        # Rule 2: Check for sequential patterns (clips too close together)
                        sorted_clips = sorted(clips, key=lambda x: x['start_time'])
                        for i in range(len(sorted_clips) - 1):
                            time_gap = sorted_clips[i+1]['start_time'] - sorted_clips[i]['end_time']
                            if time_gap < 30:  # Less than 30 seconds between clips
                                raise ValueError(
                                    f"AI selected clips too close together (gap: {time_gap}s between clips). "
                                    "This suggests sequential cutting rather than finding scattered peak moments. "
                                    "Please try a video with more distinct engaging segments."
                                )
                        
                        # Rule 3: Ensure clips are well distributed across video
                        video_duration_estimate = estimated_duration_minutes * 60  # Convert to seconds
                        
                        # DEBUG: Show what the AI actually selected
                        print(f"🔍 AI CLIP SELECTION DEBUG:")
                        print(f"   📊 Video duration estimate: {video_duration_estimate:.1f} seconds ({estimated_duration_minutes:.1f} minutes)")
                        print(f"   📊 Total clips found: {len(clips)}")
                        
                        earliest_clip = min(clip['start_time'] for clip in clips)
                        latest_clip = max(clip['start_time'] for clip in clips)
                        print(f"   ⏰ Time range: {earliest_clip:.1f}s to {latest_clip:.1f}s")
                        
                        for i, clip in enumerate(clips):
                            percentage_through = (clip['start_time'] / video_duration_estimate * 100) if video_duration_estimate > 0 else 0
                            print(f"   🎥 Clip {i+1}: {clip['start_time']:.1f}s-{clip['end_time']:.1f}s ({percentage_through:.1f}% through video)")
                            print(f"       📝 Title: {clip.get('title', 'No title')}")
                            print(f"       📖 Reason: {clip.get('selection_reason', 'No reason provided')}")
                        
                        # Intelligent content-aware validation
                        if video_duration_estimate > 300:  # Only for videos longer than 5 minutes
                            
                            # Analyze content type from transcript and AI selections
                            content_indicators = {
                                'educational': ['lesson', 'learn', 'teach', 'example', 'practice', 'study', 'tutorial'],
                                'entertainment': ['funny', 'comedy', 'joke', 'entertainment', 'story', 'dramatic'],
                                'business': ['meeting', 'strategy', 'sales', 'business', 'work', 'office'],
                                'review': ['review', 'opinion', 'thoughts', 'rating', 'recommend'],
                                'news': ['news', 'report', 'update', 'announcement', 'breaking']
                            }
                            
                            # Check transcript and AI reasoning for content type
                            transcript_lower = transcript_text.lower()  # Use transcript_text (converted to string)
                            ai_reasoning = ' '.join([clip.get('selection_reason', '') + ' ' + clip.get('description', '') for clip in clips]).lower()
                            
                            content_scores = {}
                            for content_type, keywords in content_indicators.items():
                                score = sum(1 for keyword in keywords if keyword in transcript_lower or keyword in ai_reasoning)
                                content_scores[content_type] = score
                            
                            detected_content_type = max(content_scores.items(), key=lambda x: x[1])[0] if max(content_scores.values()) > 0 else 'general'
                            
                            print(f"   � CONTENT TYPE ANALYSIS:")
                            print(f"       Detected type: {detected_content_type}")
                            print(f"       Content scores: {content_scores}")
                            
                            # Evaluate AI reasoning quality
                            reasoning_quality_indicators = [
                                'peak', 'climax', 'twist', 'reveal', 'surprise', 'emotional', 'dramatic',
                                'engaging', 'viral', 'shareable', 'relatable', 'memorable', 'punchline',
                                'insight', 'valuable', 'important', 'key moment', 'highlight'
                            ]
                            
                            reasoning_quality_score = 0
                            for clip in clips:
                                reasoning_text = (clip.get('selection_reason', '') + ' ' + clip.get('description', '')).lower()
                                reasoning_quality_score += sum(1 for indicator in reasoning_quality_indicators if indicator in reasoning_text)
                            
                            print(f"   🧠 AI REASONING QUALITY:")
                            print(f"       Quality score: {reasoning_quality_score}/{len(clips) * 3} (good reasoning uses 2-3 quality indicators per clip)")
                            
                            # Content-type specific validation rules with special handling for very long videos
                            sixty_percent_mark = video_duration_estimate * 0.6
                            forty_percent_mark = video_duration_estimate * 0.4
                            twenty_percent_mark = video_duration_estimate * 0.2
                            
                            # For very long videos (2+ hours), use much more flexible rules
                            is_very_long_video = video_duration_estimate > 7200  # 2 hours
                            
                            print(f"   🎯 Video length category: {'Very Long (2+ hours)' if is_very_long_video else 'Standard'}")
                            if is_very_long_video:
                                print(f"   🎯 20% mark: {twenty_percent_mark:.1f}s, 40% mark: {forty_percent_mark:.1f}s")
                            else:
                                print(f"   🎯 40% mark: {forty_percent_mark:.1f}s, 60% mark: {sixty_percent_mark:.1f}s")
                            print(f"   🎯 Latest clip starts at: {latest_clip:.1f}s")
                            
                            # Apply flexible validation based on content type, video length, and reasoning quality
                            validation_passed = False
                            validation_reason = ""
                            
                            if is_very_long_video:
                                # Very long videos (2+ hours): Much more lenient rules
                                print(f"   🕐 VERY LONG VIDEO RULES: Using flexible validation for {video_duration_estimate/3600:.1f}h video")
                                
                                if reasoning_quality_score >= len(clips):  # Just need decent reasoning
                                    validation_passed = True
                                    validation_reason = f"Very long video with decent AI reasoning (quality: {reasoning_quality_score})"
                                elif latest_clip >= twenty_percent_mark:  # Or clips after first 20%
                                    validation_passed = True
                                    validation_reason = f"Very long video with clips beyond 20% mark"
                                else:
                                    # Even more lenient: check if clips are well-reasoned regardless of position
                                    if any('viral' in clip.get('selection_reason', '').lower() or 
                                          'peak' in clip.get('selection_reason', '').lower() or
                                          'emotional' in clip.get('selection_reason', '').lower() for clip in clips):
                                        validation_passed = True
                                        validation_reason = f"Very long video with high-quality viral/emotional content identification"
                                    else:
                                        validation_reason = f"Very long video but clips lack strong viral indicators"
                                        
                            elif detected_content_type in ['educational', 'business', 'tutorial']:
                                # Educational content often has examples/scenarios early on
                                if latest_clip >= forty_percent_mark or reasoning_quality_score >= len(clips) * 2:
                                    validation_passed = True
                                    validation_reason = f"Educational content with good AI reasoning (quality: {reasoning_quality_score})"
                                else:
                                    validation_reason = f"Educational content but clips too early and weak reasoning"
                                    
                            elif detected_content_type in ['entertainment', 'story']:
                                # Entertainment should have better distribution
                                if latest_clip >= sixty_percent_mark:
                                    validation_passed = True
                                    validation_reason = "Entertainment content with good distribution"
                                elif reasoning_quality_score >= len(clips) * 2:
                                    validation_passed = True
                                    validation_reason = f"Strong AI reasoning compensates for early clips (quality: {reasoning_quality_score})"
                                else:
                                    validation_reason = "Entertainment content needs better distribution or stronger reasoning"
                                    
                            else:  # General content
                                # Flexible rules for general content
                                if latest_clip >= forty_percent_mark and reasoning_quality_score >= len(clips):
                                    validation_passed = True
                                    validation_reason = f"General content with adequate distribution and reasoning"
                                elif reasoning_quality_score >= len(clips) * 2:
                                    validation_passed = True
                                    validation_reason = f"Excellent AI reasoning compensates for distribution (quality: {reasoning_quality_score})"
                                else:
                                    validation_reason = f"Insufficient distribution and reasoning quality"
                            
                            print(f"   🎯 INTELLIGENT VALIDATION RESULT:")
                            print(f"       Status: {'✅ PASSED' if validation_passed else '❌ FAILED'}")
                            print(f"       Reason: {validation_reason}")
                            
                            if not validation_passed:
                                print(f"   ⚠️ VALIDATION WARNING: {validation_reason}")
                                print(f"   � PROCEEDING ANYWAY: Relaxing validation for user experience")
                                print(f"   💡 Note: Clips may not have optimal distribution but will still be created")
                                
                                # Instead of failing, just proceed with a warning
                                validation_reason = f"PROCEEDING WITH CAUTION: {validation_reason}"
                                print(f"   ✅ CONTINUING: {validation_reason}")
                            else:
                                print(f"   ✅ VALIDATION PASSED: {validation_reason}")
                        else:
                            print(f"   ✅ SHORT VIDEO: No distribution validation required for videos under 5 minutes")
                        
                        # VALIDATION: Check if selected segments have actual speech content
                        # More realistic validation based on actual transcript length
                        words = transcript_text.split()
                        total_words = len(words)
                        
                        # Estimate video duration from transcript (more flexible)
                        # TED talks: ~120-150 words/minute, casual: ~150-180 words/minute
                        estimated_duration = max(180, total_words / 1.5)  # Assume slower speech
                        words_per_second = total_words / estimated_duration if total_words > 0 else 1
                        
                        print(f"🔍 DEBUG: Transcript has {total_words} words, estimated {estimated_duration:.0f}s duration, ~{words_per_second:.2f} words/second")
                        
                        # ENHANCED VALIDATION: Speech detection and silence filtering
                        def analyze_transcript_segment(transcript, start_seconds, end_seconds, words_per_second):
                            """Analyze a transcript segment to detect actual speech content, filtering out non-speech parts"""
                            # Estimate which words fall in this time range
                            start_word_idx = int(start_seconds * words_per_second)
                            end_word_idx = int(end_seconds * words_per_second)
                            
                            # Get the relevant transcript portion
                            transcript_words = transcript_text.split()
                            segment_words = transcript_words[start_word_idx:end_word_idx] if start_word_idx < len(transcript_words) else []
                            segment_text = ' '.join(segment_words).lower()
                            
                            # Define non-speech indicators to filter out (but not reject entire clip)
                            non_speech_patterns = [
                                '[music]', '[applause]', '[laughter]', '[silence]', 
                                '[background music]', '[intro music]', '[outro music]',
                                '[instrumental]', '[sound effects]', '[noise]', '[static]',
                                'music playing', 'background music', 'intro music'
                            ]
                            
                            # Filter out non-speech words, keeping only actual speech
                            speech_words = []
                            non_speech_count = 0
                            
                            for word in segment_words:
                                word_lower = word.lower()
                                is_non_speech = any(pattern in word_lower for pattern in non_speech_patterns)
                                
                                if is_non_speech:
                                    non_speech_count += 1
                                else:
                                    speech_words.append(word)
                            
                            # Calculate speech density after filtering out non-speech
                            actual_speech_count = len(speech_words)
                            filtered_text = ' '.join(speech_words).lower()
                            
                            return {
                                'word_count': actual_speech_count,
                                'total_words': len(segment_words),
                                'non_speech_indicators': non_speech_count,
                                'segment_text': segment_text[:100] + '...' if len(segment_text) > 100 else segment_text,
                                'filtered_speech_text': filtered_text[:100] + '...' if len(filtered_text) > 100 else filtered_text,
                                'has_speech': actual_speech_count >= 15,  # At least 15 real speech words for 30 seconds
                                'speech_percentage': (actual_speech_count / len(segment_words) * 100) if len(segment_words) > 0 else 0
                            }
                        
                        clips_to_remove = []
                        for clip in clips:
                            duration = clip['end_time'] - clip['start_time']
                            
                            # Rule 1: Reject clips shorter than 30 seconds
                            if duration < 30:
                                clips_to_remove.append(clip['clip_number'])
                                print(f"❌ REJECTED: Clip {clip['clip_number']} is too short ({duration}s < 30s minimum)")
                                continue
                            
                            # Rule 2: Analyze actual speech content in this segment
                            segment_analysis = analyze_transcript_segment(
                                transcript_text, clip['start_time'], clip['end_time'], words_per_second
                            )
                            
                            # Rule 3: Only reject if NO speech content at all
                            if not segment_analysis['has_speech']:
                                clips_to_remove.append(clip['clip_number'])
                                print(f"❌ REJECTED: Clip {clip['clip_number']} has NO speech content")
                                print(f"   📊 Analysis: {segment_analysis['word_count']} speech words out of {segment_analysis['total_words']} total")
                                print(f"   📝 Filtered speech: {segment_analysis['filtered_speech_text']}")
                                continue
                            
                            # Rule 4: Warn about non-speech content but don't reject (just inform)
                            if segment_analysis['non_speech_indicators'] > 0:
                                print(f"⚠️ NOTICE: Clip {clip['clip_number']} contains {segment_analysis['non_speech_indicators']} non-speech elements ({segment_analysis['speech_percentage']:.1f}% actual speech)")
                                print(f"   🎤 Will use speech parts: {segment_analysis['filtered_speech_text']}")
                            else:
                                print(f"✅ CLEAN: Clip {clip['clip_number']} is pure speech content")
                            
                            # Rule 5: Check speech density using filtered speech words
                            expected_words = duration * words_per_second
                            actual_word_ratio = segment_analysis['word_count'] / expected_words if expected_words > 0 else 0
                            
                            # Only reject if extremely low speech density (less than 20% after filtering)
                            if actual_word_ratio < 0.2:  # Less than 20% of expected words = truly silent
                                clips_to_remove.append(clip['clip_number'])
                                print(f"❌ REJECTED: Clip {clip['clip_number']} has extremely low speech density ({actual_word_ratio:.1%}) - likely mostly silent")
                                continue
                                
                            # Rule 6: Special check for clip beginning (first 5 seconds must have actual speech)
                            beginning_analysis = analyze_transcript_segment(
                                transcript_text, clip['start_time'], min(clip['start_time'] + 5, clip['end_time']), words_per_second
                            )
                            
                            if beginning_analysis['word_count'] < 3:  # Less than 3 actual speech words in first 5 seconds
                                clips_to_remove.append(clip['clip_number'])
                                print(f"❌ REJECTED: Clip {clip['clip_number']} starts with insufficient speech (first 5s: {beginning_analysis['word_count']} speech words)")
                                print(f"   🎵 Raw start: {beginning_analysis['segment_text']}")
                                print(f"   🎤 Filtered speech: {beginning_analysis['filtered_speech_text']}")
                                continue
                                
                            print(f"✅ APPROVED: Clip {clip['clip_number']} - {duration}s, {segment_analysis['word_count']} speech words ({actual_word_ratio:.1%} speech density)")
                            if beginning_analysis['non_speech_indicators'] > 0:
                                print(f"   � Start has non-speech but good speech: {beginning_analysis['filtered_speech_text']}")
                            else:
                                print(f"   🎤 Clean speech start: {beginning_analysis['filtered_speech_text']}")
                        
                        # Remove rejected clips
                        if clips_to_remove:
                            original_count = len(clips_data['clips'])
                            print(f"🔧 SPEECH FILTERING: Removing {len(clips_to_remove)} clips due to lack of speech content")
                            print(f"   📋 Clips being removed: {clips_to_remove}")
                            
                            # Filter out rejected clips
                            clips_data['clips'] = [clip for clip in clips if clip['clip_number'] not in clips_to_remove]
                            
                            # Update clip numbers to be sequential
                            for i, clip in enumerate(clips_data['clips']):
                                clip['clip_number'] = i + 1
                            
                            clips = clips_data['clips']  # Update local variable
                            print(f"✅ After speech filtering: {len(clips)} clips remain (was {original_count})")
                            
                            # Debug: Show remaining clips
                            for clip in clips:
                                print(f"   ✅ APPROVED CLIP {clip['clip_number']}: {clip['start_time']}s-{clip['end_time']}s - {clip['title']}")
                        
                        # Check if we have any clips left after all filtering
                        if len(clips_data['clips']) == 0:
                            raise ValueError(
                                "No suitable clips found after filtering. "
                                "All segments were either too short (< 30s), had excessive silence (5+ sec gaps), "
                                "or lacked sufficient speech content. "
                                "Please try a video with more continuous, engaging dialogue."
                            )
                        
                        # Final validation: Ensure clip count is reasonable for video length
                        final_clip_count = len(clips_data['clips'])
                        if estimated_duration_minutes < 2 and final_clip_count > 2:
                            # Keep only best 2 clips for short videos
                            clips_data['clips'] = clips_data['clips'][:2]
                            print(f"🎯 Short video optimization: Reduced to {len(clips_data['clips'])} clips for {estimated_duration_minutes:.1f}-minute video")
                        elif estimated_duration_minutes < 5 and final_clip_count > 4:
                            # Keep only best 4 clips for medium videos
                            clips_data['clips'] = clips_data['clips'][:4]
                            print(f"🎯 Medium video optimization: Reduced to {len(clips_data['clips'])} clips for {estimated_duration_minutes:.1f}-minute video")
                        
                        # Final check after all optimizations
                        if len(clips_data['clips']) == 0:
                            raise ValueError(
                                "No clips remain after quality filtering and optimization. "
                                "This video may not have sufficient engaging content for shorts creation."
                            )
                    
                    # Debug: show the final selected segments
                    final_clips = clips_data.get('clips', [])
                    for clip in final_clips:
                        print(f"   Clip {clip['clip_number']}: {clip['start_time']}s-{clip['end_time']}s - {clip['title']}")
                    
                    print(f"🎬 Final result: {len(final_clips)} clips selected for {estimated_duration_minutes:.1f}-minute video")
                else:
                    raise ValueError("No JSON found in response")
                    
            except (json.JSONDecodeError, ValueError) as e:
                print(f"❌ Failed to parse AI response as JSON: {e}")
                print(f"Raw response: {analysis_result[:500]}...")
                print(f"❌ AI FAILED TO DETECT ENGAGING PARTS - No fallback, returning error")
                # Raise error instead of using fallback
                raise ValueError(f"AI failed to properly analyze the video content. Please try again or use a different video. Error: {e}")
            
            if progress:
                progress.update('analysis_complete', 55, 'Content analysis complete')
            
            return clips_data
            
        except Exception as e:
            print(f"❌ Transcript analysis failed: {e}")
            # Raise error instead of using fallback
            raise ValueError(f"Failed to analyze video content for engaging moments: {str(e)}")
    
    def fallback_clip_analysis(self, transcript):
        """
        DEPRECATED: This fallback method is no longer used.
        Instead, we raise an error when AI fails to detect engaging moments.
        This ensures only high-quality, AI-detected clips are created.
        """
        print(f"⚠️  DEPRECATED: fallback_clip_analysis called but should not be used")
        raise ValueError("AI failed to detect engaging moments. Please try again with a different video or check if the content has clear engaging points.")
    
    def download_segment_optimized(self, video_url, start_time, end_time, clip_number, progress=None):
        """Download only a specific segment of the video with timeout protection"""
        try:
            if progress:
                progress.update('segment_download', 50, f'Attempting segment {clip_number} download...')
            
            # Quick timeout - if segment download takes too long, fallback immediately
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("Segment download timeout")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(15)  # 15 second timeout for segment download
            
            try:
                # Calculate download range (add small buffer for accuracy)
                buffer_seconds = 2
                download_start = max(0, start_time - buffer_seconds)
                download_end = end_time + buffer_seconds
                
                clip_filename = f'segment_{clip_number}.%(ext)s'
                clip_path = os.path.join(self.temp_dir, clip_filename)
                
                print("\n" + "⬇️" * 30)
                print(f"📥 SEGMENT DOWNLOAD - USING TOR (Clip {clip_number})")
                print(f"⏱️  Time range: {start_time}s - {end_time}s ({end_time - start_time}s)")
                print(f"🔒 Method: Tor-enabled yt-dlp with IP rotation")
                print("⬇️" * 30)
                
                # Use Tor-enabled extractor for segment download with IP rotation
                ydl_opts = self.tor_extractor.get_robust_ydl_options_with_tor()
                ydl_opts.update({
                    'outtmpl': clip_path,
                    'format': 'best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best',
                    'download_ranges': yt_dlp.utils.download_range_func(None, [(download_start, download_end)]),
                    'force_keyframes_at_cuts': True,
                })
                
                print(f"🔐 Downloading segment via Tor proxy...")
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])
                
                print(f"✅ Segment {clip_number} downloaded via Tor!")
                
                signal.alarm(0)  # Cancel timeout
                
                # Find the downloaded segment
                downloaded_file = None
                for file in os.listdir(self.temp_dir):
                    if file.startswith(f'segment_{clip_number}.'):
                        downloaded_file = os.path.join(self.temp_dir, file)
                        break
                
                if not downloaded_file or not os.path.exists(downloaded_file):
                    raise Exception(f"Segment {clip_number} download failed")
                
                self.cleanup_files.append(downloaded_file)
                print(f"✅ Successfully downloaded segment {clip_number}")
                return downloaded_file
                
            except (TimeoutError, Exception) as e:
                signal.alarm(0)  # Cancel timeout
                raise e
            
        except Exception as e:
            print(f"⚠️ Segment download failed ({e}), using timestamp fallback")
            return None

    def extract_video_clips_streaming(self, video_url, clips_data, transcript=None, progress=None):
        """Extract video clips in memory - creates actual downloadable video files
        
        Args:
            transcript: Either a string (plain text) OR list of dicts with timestamps
                       [{'start': 1.36, 'duration': 1.68, 'text': '...'}]
        """
        global video_clips_memory_store
        import time  # Import at function level to avoid scope issues
        import io
        import subprocess
        import tempfile
        import os
        
        try:
            if progress:
                progress.update('extraction', 60, 'Preparing in-memory video processing...')
            
            # Handle transcript format conversion for natural ending detection
            transcript_text = None
            if transcript:
                if isinstance(transcript, list) and len(transcript) > 0 and isinstance(transcript[0], dict):
                    # Convert timestamped transcript to plain text for natural ending detection
                    transcript_text = ' '.join([seg.get('text', '') for seg in transcript])
                    print(f"🔄 Converted timestamped transcript to text for natural ending detection")
                else:
                    # Already plain text
                    transcript_text = transcript
            
            extracted_clips = []
            clips = clips_data.get('clips', [])
            
            print(f"🎬 DEBUG: Starting clip extraction for {len(clips)} approved clips")
            for i, clip in enumerate(clips):
                print(f"   🎥 Clip {i+1}: {clip['start_time']}s-{clip['end_time']}s - {clip['title']}")
            
            if progress:
                progress.update('stream_ready', 65, 'Creating video clips in memory...')
            
            for i, clip_info in enumerate(clips):
                try:
                    # STRATEGIC BREAKPOINT: Check before each clip (efficient signal check)
                    if progress and progress.check_stop_at_breakpoint():
                        print(f"🛑 CANCELLED: Task stopped during clip {i+1} processing")
                        return None
                    
                    clip_num = i + 1
                    start_time = max(0, clip_info.get('start_time', 0))
                    end_time = clip_info.get('end_time', start_time + 30)
                    
                    # TikTok/YouTube Shorts vertical format: 9:16 aspect ratio
                    # High-quality resolutions: 1080x1920 (Full HD), 720x1280 (HD)
                    target_width = 720    # HD width for excellent quality and compatibility
                    target_height = 1280  # HD height for 9:16 aspect ratio
                    
                    # Smart clip duration: 30-60 seconds with natural ending points
                    initial_duration = end_time - start_time
                    
                    if initial_duration < 25:
                        # Too short, extend to at least 30 seconds
                        end_time = start_time + 30
                    elif initial_duration > 60:
                        # Too long, cap at 60 seconds initially
                        end_time = start_time + 60
                    
                    # Use intelligent ending detection if transcript is available
                    if transcript_text and initial_duration >= 25:
                        ideal_end_time = start_time + 30  # Target 30 seconds
                        max_end_time = start_time + 60    # Maximum 60 seconds
                        
                        # Find natural ending point
                        end_time = self.find_natural_ending_point(
                            transcript_text, 
                            start_time, 
                            ideal_end_time, 
                            max_end_time
                        )
                        
                        print(f"🎯 Smart ending: Clip {clip_num} duration adjusted to {end_time - start_time:.1f}s for natural conclusion")
                    else:
                        # Fallback to fixed 30-second clips
                        if end_time - start_time < 30:
                            end_time = start_time + 30
                        elif end_time - start_time > 60:
                            end_time = start_time + 45  # Reasonable middle ground
                    
                    if progress:
                        # Calculate base progress for this clip (each clip gets 7% in a 5-clip scenario, 60-95% range)
                        clip_progress_chunk = 35 / len(clips)  # 7% per clip for 5 clips (35% total range)
                        base_progress = 60 + ((clip_num - 1) * clip_progress_chunk)
                        progress.update('processing_clip', base_progress, f'Creating video clip {clip_num}/{len(clips)}...')
                    
                    print(f"🎬 Creating vertical video clip {clip_num} ({start_time}s - {end_time}s) - {target_width}x{target_height} (9:16)")
                    
                    # STRATEGIC BREAKPOINT: Before expensive FFmpeg operation
                    if progress and progress.check_stop_at_breakpoint():
                        print(f"🛑 CANCELLED: Task stopped before FFmpeg processing of clip {clip_num}")
                        return None
                    
                    # Create actual video clip in memory using yt-dlp + ffmpeg
                    try:
                        # Generate safe filename (ASCII only for HTTP headers)
                        title_text = clip_info.get('title', f'clip_{clip_num}')
                        # Remove all non-ASCII characters and replace with underscore
                        safe_title = re.sub(r'[^\x00-\x7F]', '_', title_text)
                        # Then remove any remaining problematic characters
                        safe_title = re.sub(r'[^\w\-_\.]', '_', safe_title)[:30]
                        output_filename = f'clip_{clip_num}_{safe_title}.mp4'
                        
                        # Create clip using yt-dlp with specific time range (in memory buffer)
                        duration = end_time - start_time
                        
                        print("\n" + "🎥" * 30)
                        print(f"🎬 CLIP STREAM EXTRACTION - USING TOR (Clip {clip_num})")
                        print(f"🎯 Quality target: 1080p/720p")
                        print(f"🔒 Method: Tor-enabled extraction with IP rotation")
                        print("🎥" * 30)
                        
                        # Extract video info using Tor to get direct stream URL - prioritize highest quality
                        info = self.tor_extractor.extract_video_info_with_tor(video_url, extract_info_only=False)
                        
                        print("✅ Stream URLs received from Tor extractor")
                        
                        # Find best quality format URL - prioritize 1080p then 720p
                        if 'url' in info:
                            stream_url = info['url']
                        elif 'formats' in info and info['formats']:
                            # Sort formats by quality (height) in descending order
                            quality_formats = [f for f in info['formats'] if f.get('url') and f.get('height')]
                            quality_formats.sort(key=lambda x: x.get('height', 0), reverse=True)
                            
                            # Prefer up to 1080p for best quality
                            for format_info in quality_formats:
                                if format_info.get('height', 0) <= 1080:
                                    stream_url = format_info['url']
                                    print(f"🎥 Selected {format_info.get('height', 'unknown')}p quality for clip {clip_num}")
                                    break
                            else:
                                # Fallback to any available format
                                stream_url = info['formats'][-1]['url']
                        else:
                                raise Exception("No suitable video stream found")
                        
                        # Use ffmpeg to extract the specific clip to a temporary file, then read to memory
                        # Create temporary file for the clip
                        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                            temp_clip_path = temp_file.name
                        
                        # Update progress for face detection
                        if progress:
                            clip_progress_chunk = 35 / len(clips)  # 7% per clip for 5 clips (60-95% range)
                            base_progress = 60 + ((clip_num - 1) * clip_progress_chunk)
                            stage_progress = base_progress + (0.05 * clip_progress_chunk)  # 5% of clip for face detection
                            progress.update('face_detection', stage_progress, f'🔍 Analyzing faces in clip {clip_num}...')
                        
                        # Detect face position for intelligent cropping
                        face_position = self.detect_face_position(stream_url, start_time, duration)
                        
                        # Create video filter with intelligent cropping based on face detection
                        if face_position:
                            normalized_x, normalized_y = face_position
                            print(f"🎯 Face detected at ({normalized_x:.2f}, {normalized_y:.2f}) - calculating intelligent crop")
                            
                            # Smart cropping algorithm for vertical video (9:16)
                            # Map face position to crop center position - MORE AGGRESSIVE
                            
                            # For horizontal positioning: directly follow the face position
                            # Face at 0.0 (left) -> crop at 0.15 (significantly left)
                            # Face at 0.5 (center) -> crop at 0.5 (center)  
                            # Face at 1.0 (right) -> crop at 0.85 (significantly right)
                            crop_center_x = 0.15 + (normalized_x * 0.7)  # Maps 0-1 to 0.15-0.85
                            
                            # For vertical positioning: follow face more directly for better framing
                            # Face at 0.0 (top) -> crop at 0.1 (very top for headroom)
                            # Face at 0.5 (middle) -> crop at 0.4 (upper-middle for good framing)
                            # Face at 1.0 (bottom) -> crop at 0.7 (lower but still visible)
                            crop_center_y = 0.1 + (normalized_y * 0.6)  # Maps 0-1 to 0.1-0.7
                            
                            # Ensure bounds are respected
                            crop_center_x = max(0.0, min(1.0, crop_center_x))
                            crop_center_y = max(0.0, min(1.0, crop_center_y))
                            
                            # Create intelligent crop filter - use safer two-step approach
                            # Step 1: Scale to give room for cropping
                            # Step 2: Crop with calculated position
                            video_filter = (
                                f'scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,'
                                f'crop={target_width}:{target_height}:'
                                f'(iw-{target_width})*{crop_center_x}:'
                                f'(ih-{target_height})*{crop_center_y}'
                            )
                            print(f"🎯 Using intelligent face-based crop: face at ({normalized_x:.2f}, {normalized_y:.2f}) -> crop at ({crop_center_x:.2f}, {crop_center_y:.2f})")
                        else:
                            print(f"📐 No face detected - using center crop")
                            # Use center crop as fallback
                            video_filter = f'scale={target_width}:{target_height}:force_original_aspect_ratio=increase:flags=lanczos,crop={target_width}:{target_height}'
                        
                        ffmpeg_cmd = [
                            'ffmpeg',
                            '-ss', str(start_time),     # Start time
                            '-i', stream_url,           # Input URL
                            '-t', str(duration),        # Duration
                            '-vf', video_filter,        # Intelligent crop filter
                            '-c:v', 'libx264',          # Video codec
                            '-c:a', 'aac',              # Audio codec
                            '-preset', 'medium',        # Good balance of quality and speed
                            '-crf', '20',               # Excellent quality level
                            '-pix_fmt', 'yuv420p',      # Ensure compatibility
                            '-profile:v', 'baseline',   # Use baseline profile for maximum compatibility
                            '-level', '3.0',            # H.264 level for web compatibility
                            '-b:a', '128k',             # Good audio bitrate
                            '-ar', '44100',             # Standard audio sample rate
                            '-movflags', '+faststart',  # Web-optimized
                            '-f', 'mp4',                # MP4 format
                            '-avoid_negative_ts', 'make_zero',  # Handle timestamp issues
                            '-y',                       # Overwrite output
                            temp_clip_path              # Output to temp file
                        ]
                        
                        # Execute ffmpeg with retry mechanism
                        max_retries = 1
                        retry_count = 0
                        success = False
                        last_error = None
                        
                        # Update progress for each stage of clip creation
                        if progress:
                            clip_progress_chunk = 35 / len(clips)  # 7% per clip for 5 clips (60-95% range)
                            base_progress = 60 + ((clip_num - 1) * clip_progress_chunk)
                            stage_progress = base_progress + (0.15 * clip_progress_chunk)  # 15% of clip for video processing
                            progress.update('ffmpeg_processing', stage_progress, f'🎬 Processing video for clip {clip_num}...')
                        
                        print(f"🎬 Creating clip {clip_num}: {duration:.1f}s from {start_time:.1f}s")
                        print(f"   🎯 Target size: {target_width}x{target_height}")
                        print(f"   🔧 FFmpeg command: {' '.join(ffmpeg_cmd[:8])}... (truncated)")
                        
                        while retry_count <= max_retries and not success:
                            if retry_count > 0:
                                print(f"🔄 Retry {retry_count}/{max_retries} for clip {clip_num}")
                                time.sleep(1)  # Brief delay between retries
                            
                            process = subprocess.Popen(
                                ffmpeg_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )
                            
                            try:
                                # Add timeout to prevent hanging - 90 seconds should be enough for any clip
                                stdout, stderr = process.communicate(timeout=90)
                            except subprocess.TimeoutExpired:
                                print(f"⚠️ FFmpeg timeout (90 seconds) for clip {clip_num} - terminating process")
                                process.kill()
                                stdout, stderr = process.communicate()
                                last_error = f"FFmpeg timeout after 90 seconds"
                                retry_count += 1
                                continue
                            
                            if process.returncode == 0 and os.path.exists(temp_clip_path):
                                file_size_check = os.path.getsize(temp_clip_path)
                                # More reasonable minimum: 200KB for 30-second clips (was 1MB)
                                min_size = 200 * 1024  # 200KB minimum
                                if file_size_check >= min_size:
                                    success = True
                                    print(f"✅ Video clip created successfully: {self.format_file_size(file_size_check)}")
                                else:
                                    last_error = f"File too small: {self.format_file_size(file_size_check)} (minimum: {self.format_file_size(min_size)})"
                                    print(f"❌ File size validation failed: {last_error}")
                                    if os.path.exists(temp_clip_path):
                                        os.unlink(temp_clip_path)
                            else:
                                last_error = stderr.decode('utf-8', errors='ignore') if stderr else f"FFmpeg failed with return code {process.returncode}"
                                if os.path.exists(temp_clip_path):
                                    os.unlink(temp_clip_path)
                            
                            retry_count += 1
                        
                        if success:
                            # Get final file size
                            file_size = os.path.getsize(temp_clip_path)
                            
                            # Read the file into memory
                            try:
                                with open(temp_clip_path, 'rb') as f:
                                    video_data = f.read()
                                
                                # Double-check data consistency
                                if len(video_data) != file_size:
                                    os.unlink(temp_clip_path)
                                    print(f"❌ ERROR: File size mismatch for clip {clip_num}")
                                    continue
                                
                                # ADD CAPTIONS TO VIDEO if transcript is available
                                if transcript:
                                    try:
                                        # Update progress for caption generation
                                        if progress:
                                            clip_progress_chunk = 35 / len(clips)  # 7% per clip for 5 clips (60-95% range)
                                            base_progress = 60 + ((clip_num - 1) * clip_progress_chunk)
                                            stage_progress = base_progress + (0.85 * clip_progress_chunk)  # 85% of clip for captions
                                            progress.update('adding_captions', stage_progress, f'📋 Adding captions to clip {clip_num}...')
                                        
                                        print(f"📋 Adding captions to clip {clip_num}...")
                                        from .caption_generator import CaptionGenerator
                                        
                                        # Save video data to temp file for caption processing
                                        caption_video_path = tempfile.mktemp(suffix='.mp4')
                                        with open(caption_video_path, 'wb') as f:
                                            f.write(video_data)
                                        
                                        # Generate and burn captions using timestamped data
                                        with CaptionGenerator() as caption_gen:
                                            video_with_captions = caption_gen.add_captions_to_video(
                                                caption_video_path,
                                                transcript,  # Pass original transcript (timestamped or text)
                                                start_time,  # Clip start time in original video
                                                end_time     # Clip end time in original video
                                            )
                                        
                                            # Replace video data with captioned version
                                            video_data = video_with_captions
                                            file_size = len(video_data)
                                        
                                        # Clean up temp caption file
                                        if os.path.exists(caption_video_path):
                                            os.unlink(caption_video_path)
                                        
                                        print(f"✅ Captions added to clip {clip_num} (new size: {self.format_file_size(file_size)})")
                                        
                                    except Exception as caption_error:
                                        print(f"⚠️ Caption generation failed for clip {clip_num}: {caption_error}")
                                        # Continue with original video without captions
                                
                                # Clean up temp file
                                os.unlink(temp_clip_path)
                                
                                # Create a unique identifier for this clip
                                clip_id = f"{self.temp_dir.split('/')[-1]}_{clip_num}"
                                
                                # Store the video data for later download
                                video_clips_memory_store[clip_id] = {
                                    'data': video_data,
                                    'filename': output_filename,
                                    'content_type': 'video/mp4',
                                    'size': file_size,
                                    'created_at': time.time()
                                }
                                
                                # Generate thumbnail immediately when clip is created
                                try:
                                    print(f"🔧 [CLIP DEBUG] Starting thumbnail generation for clip {clip_num} (ID: {clip_id})")
                                    print(f"📦 [CLIP DEBUG] Video data size: {len(video_data)} bytes")
                                    
                                    thumbnail_data = self.generate_thumbnail_from_video_data(video_data, clip_id)
                                    if thumbnail_data:
                                        video_clips_memory_store[clip_id]['thumbnail'] = thumbnail_data
                                        print(f"✅ [CLIP DEBUG] Thumbnail generated and stored for clip {clip_num} (size: {len(thumbnail_data)} bytes)")
                                        
                                        # Verify thumbnail was stored
                                        stored_thumb = video_clips_memory_store[clip_id].get('thumbnail')
                                        if stored_thumb:
                                            print(f"✅ [CLIP DEBUG] Thumbnail verification successful - stored size: {len(stored_thumb)} bytes")
                                        else:
                                            print(f"❌ [CLIP DEBUG] Thumbnail verification failed - not found in store!")
                                    else:
                                        print(f"❌ [CLIP DEBUG] Failed to generate thumbnail for clip {clip_num}")
                                except Exception as thumb_error:
                                    print(f"❌ [CLIP DEBUG] Error generating thumbnail for clip {clip_num}: {thumb_error}")
                                    import traceback
                                    print(f"📋 [CLIP DEBUG] Thumbnail error traceback: {traceback.format_exc()}")
                                
                                extracted_clips.append({
                                    'clip_number': clip_num,
                                    'title': clip_info.get('title', f'Clip {clip_num}'),
                                    'description': clip_info.get('description', ''),
                                    'selection_reason': clip_info.get('selection_reason', ''),
                                    'start_time': start_time,
                                    'end_time': end_time,
                                    'duration': round(duration, 1),
                                    'file_path': None,  # No local file
                                    'file_size': file_size,
                                    'filename': output_filename,
                                    'clip_id': clip_id,  # For in-memory access
                                    'processing_method': 'In-Memory Video Processing',
                                    'download_url': f'/api/download-clip/{clip_id}',
                                    'stream_url': f'/api/stream-clip/{clip_id}',
                                    'has_video_file': True,
                                    'video_ready': True
                                })
                                
                                print(f"✅ Created video clip {clip_num}: {self.format_file_size(file_size)}")
                                
                                # Update progress - clip completed
                                if progress:
                                    clip_progress_chunk = 35 / len(clips)  # 7% per clip for 5 clips (60-95% range)
                                    completed_progress = 60 + (clip_num * clip_progress_chunk)  # Full progress for this clip
                                    progress.update('clip_completed', completed_progress, f'✅ Completed clip {clip_num}/{len(clips)}')
                                
                                # Send partial result with the newly created clip
                                if progress:
                                    print(f"🔍 DEBUG: Sending partial result for clip {clip_num}")
                                    
                                    # Create a serializable version of the clip
                                    clip_data = {
                                        'clip_number': extracted_clips[-1]['clip_number'],
                                        'title': extracted_clips[-1]['title'],
                                        'description': extracted_clips[-1]['description'],
                                        'selection_reason': extracted_clips[-1]['selection_reason'],
                                        'start_time': extracted_clips[-1]['start_time'],
                                        'end_time': extracted_clips[-1]['end_time'],
                                        'duration': extracted_clips[-1]['duration'],
                                        'file_size': extracted_clips[-1]['file_size'],
                                        'filename': extracted_clips[-1]['filename'],
                                        'clip_id': extracted_clips[-1]['clip_id'],
                                        'processing_method': extracted_clips[-1]['processing_method'],
                                        'download_url': extracted_clips[-1]['download_url'],
                                        'stream_url': extracted_clips[-1]['stream_url'],
                                        'has_video_file': extracted_clips[-1]['has_video_file'],
                                        'video_ready': extracted_clips[-1]['video_ready']
                                    }
                                    
                                    # Calculate current progress for clip completion
                                    clip_progress_chunk = 35 / len(clips)  # 7% per clip for 5 clips (60-95% range)
                                    current_progress = 60 + (clip_num * clip_progress_chunk)  # Full progress for this clip
                                    
                                    progress.update(
                                        'clip_ready', 
                                        current_progress, 
                                        f'Video clip {clip_num}/{len(clips)} ready!',
                                        partial_result={
                                            'new_clip': clip_data,
                                            'total_ready': len(extracted_clips),
                                            'total_clips': len(clips)
                                        }
                                    )
                                    print(f"🔍 DEBUG: Partial result sent for clip {clip_num}")
                                else:
                                    print(f"🔍 DEBUG: No progress tracker available for partial result")
                                
                            except Exception as file_error:
                                # Clean up temp file on error
                                if os.path.exists(temp_clip_path):
                                    os.unlink(temp_clip_path)
                                raise file_error
                        
                        else:
                            # All retries failed - clean up and raise error
                            if os.path.exists(temp_clip_path):
                                os.unlink(temp_clip_path)
                            
                            print(f"❌ FFMPEG FAILED for clip {clip_num} after {max_retries + 1} attempts")
                            print(f"   Final error: {last_error}")
                            print(f"   Command: {' '.join(ffmpeg_cmd[:5])}...{' '.join(ffmpeg_cmd[-2:])}")
                            
                            # Raise error - no fallback downloads
                            raise Exception(f"FFmpeg failed to create clip after {max_retries + 1} attempts: {last_error}")
                        
                    except Exception as clip_error:
                        print(f"❌ Failed to create video clip {clip_num}: {clip_error}")
                        # No fallback - clip creation failed completely
                        
                except Exception as e:
                    print(f"❌ Failed to process clip {clip_num}: {e}")
                    continue
            
            # Final validation: Remove clips that failed to create proper video files
            valid_clips = []
            min_final_size = 200 * 1024  # 200KB minimum (was 500KB)
            for clip in extracted_clips:
                if clip.get('has_video_file', False) and clip.get('file_size', 0) > min_final_size:
                    valid_clips.append(clip)
                    print(f"✅ VALID CLIP: {clip['clip_number']} - {self.format_file_size(clip['file_size'])}")
                else:
                    print(f"❌ INVALID CLIP REMOVED: {clip['clip_number']} - {self.format_file_size(clip.get('file_size', 0))} (minimum: {self.format_file_size(min_final_size)})")
            
            if len(valid_clips) == 0:
                raise Exception("No valid video clips were created. All clips failed validation.")
            
            # Check if any valid clips were created
            if len(valid_clips) == 0:
                error_msg = f"No valid video clips were created. All clips failed validation."
                if progress:
                    progress.error(error_msg)
                raise Exception(error_msg)
            
            if progress:
                progress.update('clips_ready', 95, f'Successfully created {len(valid_clips)} valid video clips')
            
            print(f"🔍 DEBUG: Video clips validated, {len(valid_clips)} valid clips out of {len(extracted_clips)} total")
            return valid_clips
            
        except Exception as e:
            raise Exception(f"Failed to extract video clips: {str(e)}")
    
    def format_file_size(self, bytes_size):
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024
        return f"{bytes_size:.1f} TB"
    
    def generate_thumbnail_from_video_data(self, video_data, clip_id):
        """Generate thumbnail from video data in memory"""
        try:
            # Create a temporary file for FFmpeg processing
            temp_video_path = None
            temp_thumbnail_path = None
            
            try:
                # Write video data to temporary file
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_video:
                    temp_video.write(video_data)
                    temp_video_path = temp_video.name
                
                # Create temporary thumbnail file
                temp_thumbnail_fd, temp_thumbnail_path = tempfile.mkstemp(suffix='.jpg')
                os.close(temp_thumbnail_fd)
                
                # Generate thumbnail using FFmpeg with multiple time positions
                positions = ['00:00:01', '00:00:02', '00:00:03', '00:00:00.5']
                
                for position in positions:
                    
                    cmd = [
                        'ffmpeg', '-y', '-loglevel', 'error',  # Suppress verbose output
                        '-i', temp_video_path,
                        '-ss', position,
                        '-vframes', '1',
                        '-vf', 'scale=320:240:force_original_aspect_ratio=increase,crop=320:240',
                        '-q:v', '2',
                        temp_thumbnail_path
                    ]
                    
                    try:
                        import subprocess
                        result = subprocess.run(cmd, capture_output=True, timeout=30, check=True)
                        
                        # Check if thumbnail was created successfully
                        if os.path.exists(temp_thumbnail_path) and os.path.getsize(temp_thumbnail_path) > 0:
                            with open(temp_thumbnail_path, 'rb') as f:
                                thumbnail_data = f.read()
                            return thumbnail_data
                    except subprocess.CalledProcessError as e:
                        continue
                    except Exception as e:
                        continue
                return None
                
            finally:
                # Clean up temporary files
                for temp_path in [temp_video_path, temp_thumbnail_path]:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.unlink(temp_path)
                        except Exception as e:
                            pass
                            
        except Exception as e:
            return None
    
    def process_video_for_shorts(self, video_url, transcript, language='en', progress=None):
        """Main method to process video and generate shorts clips using in-memory processing"""
        try:
            # BREAKPOINT 1: Before video info (fast check)
            if progress and progress.check_stop_at_breakpoint():
                return {'success': False, 'error': 'Task cancelled before video info'}
            
            # Step 1: Get video info (lightweight)
            video_info = self.get_video_info_safe(video_url, progress)
            
            # BREAKPOINT 2: Before AI analysis (natural stopping point)
            if progress and progress.check_stop_at_breakpoint():
                return {'success': False, 'error': 'Task cancelled before AI analysis'}
            
            # Step 2: Analyze transcript for best clips (AI-powered)
            clips_analysis = self.analyze_transcript_for_clips(transcript, language, progress)
            
            # BREAKPOINT 3: Before video processing (natural stopping point)
            if progress and progress.check_stop_at_breakpoint():
                return {'success': False, 'error': 'Task cancelled before video processing'}
            
            # Step 3: Extract clips using in-memory streaming (NO file downloads)
            extracted_clips = self.extract_video_clips_streaming(video_url, clips_analysis, transcript, progress)
            
            if progress:
                progress.update('complete', 100, 'Shorts generation complete!')
            
            return {
                'success': True,
                'video_info': video_info,
                'clips': extracted_clips,
                'total_clips': len(extracted_clips) if extracted_clips else 0,
                'processing_method': 'In-Memory Stream Processing (Zero Download)',
                'storage_used': 'Minimal - Only final clips stored temporarily',
                'memory_efficient': True
            }
            
        except Exception as e:
            if progress:
                progress.error(f"Shorts generation failed: {str(e)}")
            raise e