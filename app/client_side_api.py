"""
Lightweight Server-Side API for Client-Side Video Processing

This module provides minimal server-side support for client-side video processing:
1. Extract captions/transcripts using crawl4ai
2. AI analysis of content to find best timestamps
3. Provide video stream URLs (yt-dlp)
4. Proxy video segments to bypass CORS (ONLY downloads requested 30-60s clips)

Heavy video processing (cropping, face detection, rendering) is handled client-side.
"""

from flask import jsonify, request, Response
import yt_dlp
import re
import subprocess
import tempfile
import os
from .youtube_processor import YouTubeProcessor
from .tor_youtube_extractor import TorYouTubeExtractor

# Initialize Tor extractor for all client-side video operations
tor_extractor = TorYouTubeExtractor()

def register_client_side_api_routes(app):
    """Register API routes for client-side video processing support"""
    
    @app.route('/api/get-video-stream', methods=['POST'])
    def get_video_stream():
        """
        Get direct video stream URL and metadata without downloading
        
        Returns:
            - streamUrl: Direct video URL for browser access
            - duration: Video duration in seconds
            - title: Video title
            - thumbnail: Thumbnail URL
        """
        try:
            data = request.json
            video_url = data.get('url')
            
            if not video_url:
                return jsonify({'error': 'Video URL is required'}), 400
            
            print("\n" + "🌐" * 30)
            print("📡 CLIENT API: Getting video stream via TOR")
            print(f"🎯 URL: {video_url[:60]}...")
            print("🌐" * 30)
            
            # Extract video info using Tor for IP rotation
            info = tor_extractor.extract_video_info_with_tor(video_url, extract_info_only=False)
            
            # Get the best stream URL
            stream_url = info.get('url')
            if not stream_url:
                if 'formats' in info and info['formats']:
                    # Find best quality format
                    for fmt in reversed(info['formats']):
                        if fmt.get('url') and fmt.get('height', 0) <= 720:
                            stream_url = fmt['url']
                            break
            
            if not stream_url:
                return jsonify({'error': 'No suitable video stream found'}), 500
            
            print("✅ Video stream ready")
            
            return jsonify({
                'streamUrl': stream_url,
                'duration': info.get('duration', 0),
                'title': info.get('title', 'Unknown'),
                'thumbnail': info.get('thumbnail'),
                'videoId': info.get('id'),
                'width': info.get('width', 0),
                    'height': info.get('height', 0)
                })
            
        except Exception as e:
            return jsonify({'error': f'Failed to get video stream: {str(e)}'}), 500
    
    
    @app.route('/api/extract-captions-only', methods=['POST'])
    def extract_captions_only():
        """
        Extract only captions/transcripts without video processing
        
        Returns:
            - captions: Transcript with timestamps
        """
        try:
            data = request.json
            video_url = data.get('url')
            
            if not video_url:
                return jsonify({'error': 'Video URL is required'}), 400
            
            processor = YouTubeProcessor()
            video_id = processor.extract_video_id(video_url)
            
            if not video_id:
                return jsonify({'error': 'Invalid YouTube URL'}), 400
            
            print(f"🎬 Extracting captions for video: {video_id}")
            
            # Get transcript with timestamps
            transcript = processor.get_transcript_with_timestamps(video_id)
            
            if not transcript:
                return jsonify({'error': 'No captions available for this video'}), 404
            
            print(f"✅ Successfully extracted {len(transcript)} caption segments")
            
            return jsonify({
                'captions': transcript,
                'videoId': video_id
            })
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Caption extraction failed: {error_msg}")
            
            # Provide more specific error messages
            if "Could not extract transcript" in error_msg or "might not have captions available" in error_msg:
                return jsonify({
                    'error': 'This video does not have captions available, or the captions are not accessible. Please try a different video with subtitles/captions enabled.'
                }), 404
            elif "Invalid YouTube URL" in error_msg:
                return jsonify({
                    'error': 'Invalid YouTube URL format. Please provide a valid YouTube video URL.'
                }), 400
            elif "Task cancelled" in error_msg:
                return jsonify({
                    'error': 'Caption extraction was cancelled.'
                }), 499
            else:
                return jsonify({
                    'error': f'Failed to extract captions: {error_msg}'
                }), 500
    
    
    @app.route('/api/analyze-for-shorts', methods=['POST'])
    def analyze_for_shorts():
        """
        Analyze content using AI to find best segments for shorts
        
        This is the only AI/heavy processing done server-side.
        Returns timestamp ranges for the browser to process.
        
        Returns:
            - clips: Array of clip metadata with start/end times
        """
        try:
            data = request.json
            captions = data.get('captions')
            duration = data.get('duration', 0)
            
            if not captions:
                return jsonify({'error': 'Captions are required'}), 400
            
            # Import video processor for AI analysis
            from .video_processor import VideoProcessor
            
            with VideoProcessor() as processor:
                # Use existing AI analysis logic
                clips_analysis = processor.analyze_transcript_for_clips(
                    captions,
                    language='en',
                    progress=None
                )
                
                if not clips_analysis or 'clips' not in clips_analysis:
                    return jsonify({'error': 'Failed to analyze content'}), 500
                
                # Return only metadata - no video files
                clips_metadata = []
                for clip in clips_analysis['clips']:
                    clips_metadata.append({
                        'clip_number': clip.get('clip_number'),
                        'title': clip.get('title'),
                        'description': clip.get('description'),
                        'selection_reason': clip.get('selection_reason'),
                        'startTime': clip.get('start_time'),  # Convert to camelCase for JavaScript
                        'endTime': clip.get('end_time'),      # Convert to camelCase for JavaScript
                        'duration': clip.get('end_time', 0) - clip.get('start_time', 0)
                    })
                
                return jsonify({
                    'clips': clips_metadata,
                    'totalClips': len(clips_metadata)
                })
            
        except Exception as e:
            return jsonify({'error': f'Failed to analyze content: {str(e)}'}), 500
    
    
    @app.route('/api/proxy-video-segment', methods=['POST'])
    def proxy_video_segment():
        """
        Proxy a specific video segment to bypass CORS
        
        IMPORTANT: This ONLY downloads the requested 30-60s segment, not the full video!
        The segment is streamed directly to the browser and NOT saved to disk.
        
        Request:
            - url: YouTube URL
            - startTime: Start time in seconds
            - endTime: End time in seconds (max 60s segment)
        
        Returns:
            Streaming video data (MP4 format)
        """
        try:
            data = request.json
            video_url = data.get('url')
            start_time = float(data.get('startTime', 0))
            end_time = float(data.get('endTime', 0))
            
            if not video_url:
                return jsonify({'error': 'Video URL is required'}), 400
            
            # Validate segment duration (max 60s for safety)
            duration = end_time - start_time
            if duration <= 0 or duration > 90:
                return jsonify({'error': 'Invalid segment duration (max 90s)'}), 400
            
            print(f"📥 Loading video segment: {duration}s")
            
            print("\n" + "📥" * 30)
            print(f"🎞️  Preparing video segment")
            print(f"⏱️  Duration: {duration}s")
            print("📥" * 30)
            
            # Get video stream URL using Tor
            info = tor_extractor.extract_video_info_with_tor(video_url, extract_info_only=False)
            stream_url = info.get('url')
            
            if not stream_url:
                # Try to find from formats
                if 'formats' in info and info['formats']:
                    for fmt in reversed(info['formats']):
                        if fmt.get('url') and fmt.get('height', 0) <= 720:
                            stream_url = fmt['url']
                            break
            
            if not stream_url:
                return jsonify({'error': 'No video stream found'}), 500
            
            print("✅ Preparing video segment...")
            
            # Use FFmpeg to extract ONLY the requested segment and stream it
            # This downloads only the necessary bytes, not the full video!
            def generate_segment():
                # Try primary command with AAC bitstream filter
                primary_cmd = [
                    'ffmpeg',
                    '-ss', str(start_time),  # Seek to start
                    '-i', stream_url,         # Input stream
                    '-t', str(duration),      # Duration to extract
                    '-c:v', 'copy',           # Copy video codec (no re-encoding)
                    '-c:a', 'copy',           # Copy audio codec (avoid re-encoding sync issues)
                    '-bsf:a', 'aac_adtstoasc', # Fix malformed AAC bitstream for MP4
                    '-avoid_negative_ts', 'make_zero',  # Handle timing issues
                    '-fflags', '+genpts',     # Generate presentation timestamps
                    '-async', '1',            # Audio sync method
                    '-f', 'mp4',              # Output format
                    '-movflags', 'frag_keyframe+empty_moov+faststart',  # Enable streaming
                    'pipe:1'                  # Output to stdout (streaming)
                ]
                
                # Fallback command without bitstream filter (in case AAC filter fails)
                fallback_cmd = [
                    'ffmpeg',
                    '-ss', str(start_time),  # Seek to start
                    '-i', stream_url,         # Input stream
                    '-t', str(duration),      # Duration to extract
                    '-c:v', 'copy',           # Copy video codec (no re-encoding)
                    '-c:a', 'aac',            # Re-encode audio with proper AAC
                    '-b:a', '128k',           # Set audio bitrate
                    '-ar', '44100',           # Set sample rate
                    '-avoid_negative_ts', 'make_zero',  # Handle timing issues
                    '-fflags', '+genpts',     # Generate presentation timestamps
                    '-async', '1',            # Audio sync method
                    '-f', 'mp4',              # Output format
                    '-movflags', 'frag_keyframe+empty_moov+faststart',  # Enable streaming
                    'pipe:1'                  # Output to stdout (streaming)
                ]
                
                # Try primary command first
                for attempt, (cmd, cmd_name) in enumerate([(primary_cmd, "Primary"), (fallback_cmd, "Fallback")]):
                    try:
                        print(f"🎬 Processing video segment: {duration}s")
                        
                        # Run FFmpeg and stream output
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            bufsize=10**8  # 100MB buffer
                        )
                        
                        # Stream the output in chunks and track total size
                        total_bytes = 0
                        error_occurred = False
                        
                        while True:
                            chunk = process.stdout.read(8192)  # 8KB chunks
                            if not chunk:
                                break
                            total_bytes += len(chunk)
                            yield chunk
                        
                        process.wait()
                        
                        # Check if command succeeded
                        if process.returncode == 0:
                            # Success!
                            size_mb = total_bytes / (1024 * 1024)
                            print(f"✅ Video segment ready: {duration}s ({size_mb:.2f} MB)")
                            return  # Exit function on success
                        else:
                            # Command failed
                            error = process.stderr.read().decode()
                            print(f"⚠️ Video processing attempt failed, trying alternative method...")
                            
                            # If this was the last attempt, log the error
                            if attempt == 1:  # Last attempt
                                print(f"❌ Unable to process video segment")
                                yield b''  # Empty response 
                                return
                    
                    except Exception as e:
                        print(f"⚠️ Processing error, trying alternative method...")
                        if attempt == 1:  # Last attempt
                            yield b''  # Empty response on final failure
                            return
            
            # Return streaming response
            return Response(
                generate_segment(),
                mimetype='video/mp4',
                headers={
                    'Content-Type': 'video/mp4',
                    'Accept-Ranges': 'bytes',
                    'Cache-Control': 'no-cache'
                }
            )
            
        except Exception as e:
            print(f"❌ Proxy error: {str(e)}")
            return jsonify({'error': f'Failed to proxy segment: {str(e)}'}), 500
    
    
    return app
