"""
Caption Generator for YouTube Shorts
Creates stylized captions burned into video using FFmpeg
"""

import os
import tempfile
import subprocess
import json
import re
from typing import List, Dict, Union

class CaptionGenerator:
    def __init__(self):
        self.temp_files = []
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up temporary files"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass
    
    def add_captions_to_video(self, video_path: str, transcript_data: Union[str, List[Dict]], 
                            clip_start_time: float, clip_end_time: float) -> bytes:
        """
        Add captions to video clip using timestamped transcript data
        
        Args:
            video_path: Path to input video file
            transcript_data: Either timestamped list or plain text
            clip_start_time: Start time of the clip in the original video
            clip_end_time: End time of the clip in the original video
            
        Returns:
            bytes: Video data with burned-in captions
        """
        
        print(f"🎬 Generating captions for clip {clip_start_time}s-{clip_end_time}s")
        
        # Handle transcript format
        if isinstance(transcript_data, list) and len(transcript_data) > 0 and isinstance(transcript_data[0], dict):
            # Use timestamped data for precise captions
            return self._add_timestamped_captions(video_path, transcript_data, clip_start_time, clip_end_time)
        else:
            # Fallback to simple text overlay for plain text
            return self._add_simple_text_overlay(video_path, str(transcript_data), clip_start_time, clip_end_time)
    
    def _add_timestamped_captions(self, video_path: str, transcript_segments: List[Dict], 
                                clip_start: float, clip_end: float) -> bytes:
        """Add precise word-by-word timestamped captions using the transcript segments"""
        
        # Filter segments that overlap with our clip
        relevant_segments = []
        for segment in transcript_segments:
            seg_start = segment['start']
            seg_end = segment.get('end', seg_start + segment.get('duration', 0))
            
            # Check if segment overlaps with clip timeframe
            if seg_end > clip_start and seg_start < clip_end:
                # Adjust timing relative to clip start
                relative_start = max(0, seg_start - clip_start)
                relative_end = min(clip_end - clip_start, seg_end - clip_start)
                
                if relative_end > relative_start:
                    relevant_segments.append({
                        'start': relative_start,
                        'end': relative_end,
                        'text': segment['text'].strip()
                    })
        
        if not relevant_segments:
            print("⚠️ No relevant segments found for captions")
            # Return original video without captions
            with open(video_path, 'rb') as f:
                return f.read()
        
        print(f"📋 Found {len(relevant_segments)} caption segments - creating word-by-word effect")
        
        # Try ASS format first for advanced word-by-word highlighting
        try:
            return self._create_word_by_word_ass_captions(video_path, relevant_segments)
        except Exception as ass_error:
            print(f"⚠️ ASS captions failed: {ass_error}")
            # Fallback to simpler word-by-word method
            return self._create_simple_word_by_word_captions(video_path, relevant_segments)
    
    def _create_word_by_word_ass_captions(self, video_path: str, segments: List[Dict]) -> bytes:
        """Create word-by-word captions using ASS format"""
        
        # Create subtitle file in ASS format with word-by-word timing
        ass_content = self._create_ass_subtitles(segments)
        
        # Write ASS file
        ass_file = tempfile.mktemp(suffix='.ass')
        self.temp_files.append(ass_file)
        
        with open(ass_file, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        # Create output file
        output_file = tempfile.mktemp(suffix='.mp4')
        self.temp_files.append(output_file)
        
        # FFmpeg command to burn ASS subtitles with word-by-word effect
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-vf', f"ass={ass_file}",
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-preset', 'medium',
            '-crf', '20',
            '-pix_fmt', 'yuv420p',
            '-profile:v', 'baseline',   # Use baseline for maximum compatibility
            '-level', '3.0',            # H.264 level for web compatibility
            '-movflags', '+faststart',  # Ensure web compatibility
            '-avoid_negative_ts', 'make_zero',  # Handle timestamp issues
            output_file
        ]
        
        print(f"🎬 Creating word-by-word caption effect...")
        print(f"🔧 FFmpeg command: {' '.join(ffmpeg_cmd[:6])}... (with {len(ffmpeg_cmd)} total args)")
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and os.path.exists(output_file):
            # Check output file size and video info
            file_size = os.path.getsize(output_file)
            print(f"✅ Word-by-word captions added successfully (output: {file_size} bytes)")
            
            with open(output_file, 'rb') as f:
                video_data = f.read()
            return video_data
        else:
            print(f"❌ FFmpeg ASS failed (return code: {result.returncode})")
            print(f"❌ STDERR: {result.stderr}")
            print(f"❌ STDOUT: {result.stdout}")
            raise Exception(f"FFmpeg ASS error: {result.stderr}")
    
    def _create_simple_word_by_word_captions(self, video_path: str, segments: List[Dict]) -> bytes:
        """Fallback method: Create simpler word-by-word effect using multiple text overlays"""
        
        print(f"🔧 Using fallback word-by-word method...")
        
        # Create output file
        output_file = tempfile.mktemp(suffix='.mp4')
        self.temp_files.append(output_file)
        
        # Build complex filter for word-by-word display
        filter_parts = []
        overlay_inputs = "[0:v]"
        
        word_events = []
        for segment in segments:
            text = self._format_caption_text(segment['text']).replace('\\N', ' ')
            words = text.split()
            
            if not words:
                continue
                
            segment_duration = segment['end'] - segment['start']
            word_timings = self._calculate_smart_word_timings(words, segment_duration)
            
            current_time = segment['start']
            for word_index, (word, duration) in enumerate(zip(words, word_timings)):
                word_start = current_time
                word_end = min(current_time + duration, segment['end'])
                
                # Clean the word and determine styling
                clean_word = self._clean_word_for_display(word.strip())
                if not clean_word:
                    current_time = word_end
                    continue
                
                # Escape for FFmpeg
                safe_word = clean_word.replace("'", "\\'").replace('"', '\\"').replace(':', '\\:')
                
                # Determine if hook word
                is_hook_word = self._is_hook_word(clean_word, word_index, len(words), segment['start'])
                
                word_events.append({
                    'word': safe_word,
                    'start': word_start,
                    'end': word_end,
                    'is_hook': is_hook_word
                })
                
                current_time = word_end
        
        # Limit to first 20 words to avoid FFmpeg complexity issues
        word_events = word_events[:20]
        
        # Create single drawtext filter that shows only current word
        if word_events:
            # Build enable condition for each word
            enable_conditions = []
            for event in word_events:
                enable_conditions.append(f"between(t,{event['start']},{event['end']})*eq(mod(floor(t*100),{len(word_events)}),{word_events.index(event)})")
            
            # Create a single filter with all words, but only one visible at a time
            word_texts = [f"if(between(t,{event['start']},{event['end']}),'{event['word']}','')" for event in word_events]
            
            # Use a simpler approach: create one filter per word with precise timing
            filters = []
            for i, event in enumerate(word_events):
                # Determine color and size based on hook status
                if event['is_hook']:
                    fontcolor = "cyan"
                    fontsize = 36
                    box_effect = ":box=1:boxcolor=black@0.8:boxborderw=10"
                else:
                    fontcolor = "white"
                    fontsize = 32
                    box_effect = ":box=1:boxcolor=black@0.9:boxborderw=8"
                
                filter_text = (
                    f"drawtext=text='{event['word']}'"
                    f":fontcolor={fontcolor}:fontsize={fontsize}{box_effect}"
                    f":x=(w-text_w)/2:y=h-120"
                    f":enable='between(t,{event['start']},{event['end']})'"
                )
                
                if i == 0:
                    filters.append(f"[0:v]{filter_text}[v1]")
                    current_output = "[v1]"
                else:
                    filters.append(f"{current_output}{filter_text}[v{i+1}]")
                    current_output = f"[v{i+1}]"
            
            filter_complex = ';'.join(filters)
            overlay_inputs = current_output
        
        # Combine all filters
        if filters:
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-filter_complex', filter_complex,
                '-map', overlay_inputs.strip('[]'),
                '-c:a', 'aac',  # Ensure audio codec
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '22',
                '-pix_fmt', 'yuv420p',  # Ensure compatible pixel format
                '-profile:v', 'baseline',   # Use baseline for maximum compatibility
                '-level', '3.0',            # H.264 level for web compatibility
                '-movflags', '+faststart',  # Web optimization
                '-avoid_negative_ts', 'make_zero',  # Handle timestamp issues
                output_file
            ]
        else:
            # Fallback: no captions
            ffmpeg_cmd = ['ffmpeg', '-y', '-i', video_path, '-c', 'copy', output_file]
        
        try:
            print(f"🔧 Fallback FFmpeg command: {' '.join(ffmpeg_cmd[:6])}... (with {len(ffmpeg_cmd)} total args)")
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=90)
            
            if result.returncode == 0 and os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print(f"✅ Fallback captions added successfully (output: {file_size} bytes)")
                with open(output_file, 'rb') as f:
                    return f.read()
            else:
                print(f"❌ Fallback caption error (code: {result.returncode}): {result.stderr}")
                print(f"❌ Returning original video without captions")
                # Return original video
                with open(video_path, 'rb') as f:
                    return f.read()
                    
        except Exception as e:
            print(f"❌ Fallback caption exception: {e}")
            print(f"❌ Returning original video without captions")
            with open(video_path, 'rb') as f:
                return f.read()
    
    def _create_ass_subtitles(self, segments: List[Dict]) -> str:
        """Create ASS subtitle format with word-by-word highlighting effect"""
        
        # ASS header optimized for single-word display
        ass_header = """[Script Info]
Title: YouTube Shorts Single Word Captions
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,32,&H00FFFFFF,&H000000FF,&H00000000,&HAA000000,-1,0,0,0,100,100,0,0,1,3,2,2,20,20,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # Create word-by-word events
        events = []
        
        for segment in segments:
            # Clean and prepare text
            text = self._format_caption_text(segment['text'])
            if not text.strip():
                continue
                
            # Split into words
            words = text.replace('\\N', ' ').split()
            if not words:
                continue
            
            # Calculate intelligent timing per word based on word characteristics
            segment_duration = segment['end'] - segment['start']
            word_timings = self._calculate_smart_word_timings(words, segment_duration)
            
            # Create events for word-by-word display (only current word visible)
            current_time = segment['start']
            
            for word_index, (word, duration) in enumerate(zip(words, word_timings)):
                word_start_time = current_time
                word_end_time = min(current_time + duration, segment['end'])
                
                # Show ONLY the current word being spoken
                # Clean the word and apply smart styling
                clean_word = self._clean_word_for_display(word.strip())
                if clean_word:
                    # Determine if this is a hook/engaging word
                    is_hook_word = self._is_hook_word(clean_word, word_index, len(words), segment['start'])
                    
                    if is_hook_word:
                        # Hook words: larger, bold, colored for engagement
                        complete_text = f"{{\\c&H00FFFF&\\b1\\fs36}}{clean_word}{{\\b0\\fs32\\c&HFFFFFF&}}"
                    else:
                        # Normal words: clean white text
                        complete_text = f"{{\\c&HFFFFFF&\\fs32}}{clean_word}"
                
                # Add line breaks if needed (preserve original formatting)
                if '\\N' in text:
                    # Try to maintain original line breaks
                    words_per_line = len(words) // 2 if len(words) > 6 else len(words)
                    if word_index == words_per_line - 1 and len(words) > words_per_line:
                        complete_text += '\\N'
                
                # Convert to ASS time format
                start_ass = self._seconds_to_ass_time(word_start_time)
                end_ass = self._seconds_to_ass_time(word_end_time)
                
                # Add the event
                events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{complete_text}")
                
                current_time = word_end_time
        
        return ass_header + '\n'.join(events)
    
    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Convert seconds to ASS time format H:MM:SS.CC"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"
    
    def _format_caption_text(self, text: str) -> str:
        """Format caption text for better readability"""
        
        # Remove music notation and sound effects
        text = re.sub(r'[♪♫🎵🎶]', '', text)
        text = re.sub(r'\[.*?\]', '', text)  # Remove [music], [applause], etc.
        text = re.sub(r'\(.*?\)', '', text)  # Remove (background noise), etc.
        
        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Limit length for readability (split long sentences) - optimized for smaller font
        if len(text) > 45:  # Shorter limit for better readability with smaller font
            # Try to split at natural breaks
            words = text.split()
            if len(words) > 6:  # Split earlier for better mobile viewing
                # Split roughly in half at a good breaking point
                mid_point = len(words) // 2
                # Look for good break points near the middle
                for i in range(max(1, mid_point - 2), min(len(words), mid_point + 3)):
                    word = words[i-1].lower()
                    if word.endswith((',', '.', '!', '?', ';')) or word in ['and', 'but', 'or', 'so', 'because']:
                        first_half = ' '.join(words[:i])
                        second_half = ' '.join(words[i:])
                        text = f"{first_half}\\N{second_half}"
                        break
                else:
                    # No good break found, split at midpoint
                    first_half = ' '.join(words[:mid_point])
                    second_half = ' '.join(words[mid_point:])
                    text = f"{first_half}\\N{second_half}"
        
        # Escape special characters for ASS format
        text = text.replace('\\', '\\\\')
        text = text.replace('{', '\\{')
        text = text.replace('}', '\\}')
        
        return text
    
    def _calculate_smart_word_timings(self, words: List[str], total_duration: float) -> List[float]:
        """Calculate intelligent word timing based on word characteristics"""
        
        if not words:
            return []
        
        # Calculate base timing weights for each word
        word_weights = []
        for word in words:
            weight = 1.0  # Base weight
            
            # Adjust for word length (longer words take more time)
            length_factor = len(word) / 5.0  # Normalize to 5-character words
            weight *= (0.7 + length_factor * 0.6)  # Range: 0.7x to 1.3x+ based on length
            
            # Adjust for syllables (approximate by vowel count)
            vowels = sum(1 for char in word.lower() if char in 'aeiouAEIOU')
            syllables = max(1, vowels)  # At least 1 syllable
            weight *= (0.8 + syllables * 0.15)  # More syllables = longer duration
            
            # Adjust for punctuation (creates natural pauses)
            if word.endswith(('.', '!', '?', ';')):
                weight *= 1.4  # Pause after sentence endings
            elif word.endswith((',', ':')):
                weight *= 1.2  # Shorter pause for commas/colons
            
            # Adjust for common words (spoken faster)
            common_words = {
                'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have',
                'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
                'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'
            }
            
            if word.lower().strip('.,!?;:') in common_words:
                weight *= 0.7  # Common words spoken faster
            
            # Adjust for emphasis words (spoken slower for impact)
            emphasis_words = {
                'amazing', 'incredible', 'shocking', 'unbelievable', 'fantastic',
                'wow', 'never', 'always', 'everything', 'nothing', 'everyone',
                'important', 'crucial', 'essential', 'perfect', 'terrible'
            }
            
            if word.lower().strip('.,!?;:') in emphasis_words:
                weight *= 1.3  # Emphasis words spoken slower
            
            # Adjust for numbers (usually spoken more deliberately)
            if any(char.isdigit() for char in word):
                weight *= 1.2
                
            word_weights.append(max(0.3, min(2.5, weight)))  # Clamp between 0.3x and 2.5x
        
        # Normalize weights to fit total duration
        total_weight = sum(word_weights)
        if total_weight <= 0:
            # Fallback to equal timing
            return [total_duration / len(words)] * len(words)
        
        # Calculate actual durations
        durations = []
        for weight in word_weights:
            duration = (weight / total_weight) * total_duration
            # Ensure minimum duration (100ms) and maximum duration (3s)
            duration = max(0.1, min(3.0, duration))
            durations.append(duration)
        
        # Final adjustment to ensure total matches exactly
        actual_total = sum(durations)
        if actual_total > 0:
            adjustment_factor = total_duration / actual_total
            durations = [d * adjustment_factor for d in durations]
        
        return durations
    
    def _clean_word_for_display(self, word: str) -> str:
        """Clean word for caption display - remove unwanted symbols"""
        if not word:
            return ""
        
        # Remove music notation and unwanted symbols
        word = re.sub(r'[♪♫🎵🎶]', '', word)
        word = re.sub(r'[^\w\s.,!?;:\'-]', '', word)  # Keep only letters, numbers, basic punctuation
        
        # Remove any remaining weird characters or encoding artifacts
        word = re.sub(r'\\[a-fA-F0-9]+', '', word)  # Remove hex codes like \H00FFFF
        word = re.sub(r'[\\{}]', '', word)  # Remove backslashes and curly braces
        
        # Clean up multiple spaces and trim
        word = re.sub(r'\s+', ' ', word).strip()
        
        return word
    
    def _is_hook_word(self, word: str, word_index: int, total_words: int, segment_start: float) -> bool:
        """Determine if a word should have special hook/engaging styling"""
        
        # Early video (first 10 seconds) - more hook words for visual engagement
        is_early_video = segment_start < 10.0
        
        # First few words are always hooks for engagement
        if word_index < 3 and is_early_video:
            return True
        
        # Check word characteristics
        word_lower = word.lower().strip('.,!?;:\'"')
        
        # Hook word categories
        hook_words = {
            # Attention grabbers
            'shocking', 'amazing', 'incredible', 'unbelievable', 'mind-blowing',
            'wow', 'omg', 'whoa', 'insane', 'crazy', 'wild', 'stunning',
            
            # Numbers and statistics (always engaging)
            'million', 'billion', 'thousand', 'percent', 'times', 'years',
            
            # Emotional words
            'love', 'hate', 'fear', 'angry', 'excited', 'surprised', 'shocked',
            'happy', 'sad', 'terrified', 'devastated', 'thrilled',
            
            # Superlatives
            'best', 'worst', 'biggest', 'smallest', 'fastest', 'slowest',
            'first', 'last', 'only', 'never', 'always', 'most', 'least',
            
            # Action words
            'revealed', 'exposed', 'discovered', 'found', 'caught', 'busted',
            'failed', 'succeeded', 'won', 'lost', 'died', 'born', 'created',
            
            # Mystery/intrigue
            'secret', 'hidden', 'mystery', 'unknown', 'conspiracy', 'truth',
            'lie', 'fake', 'real', 'hoax', 'scam', 'exposed',
            
            # Money/success
            'money', 'rich', 'poor', 'millionaire', 'billionaire', 'broke',
            'success', 'failure', 'profit', 'loss', 'expensive', 'cheap'
        }
        
        # Check if word contains digits (numbers are engaging)
        if any(char.isdigit() for char in word):
            return True
        
        # Check if it's in hook words list
        if word_lower in hook_words:
            return True
        
        # Check if word has emphasis punctuation
        if word.endswith(('!', '?')):
            return True
        
        # Check if it's a long impactful word (6+ characters, not common)
        if len(word_lower) >= 6:
            common_long_words = {'because', 'through', 'without', 'between', 'something', 'anything'}
            if word_lower not in common_long_words:
                return True
        
        # Early video boost - more words are hooks in first 10 seconds
        if is_early_video and word_index < 8:
            # Every other word in early video for visual rhythm
            return word_index % 2 == 0
        
        return False
    
    def _add_simple_text_overlay(self, video_path: str, text: str, 
                               clip_start: float, clip_end: float) -> bytes:
        """Fallback method for plain text overlay"""
        
        # Clean and truncate text
        clean_text = re.sub(r'[♪♫🎵🎶\[\]()]', '', text)
        clean_text = ' '.join(clean_text.split())
        
        # Truncate to reasonable length
        if len(clean_text) > 100:
            clean_text = clean_text[:97] + '...'
        
        # Create output file
        output_file = tempfile.mktemp(suffix='.mp4')
        self.temp_files.append(output_file)
        
        # Simple text overlay with FFmpeg (optimized for shorts)
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-vf', 
            f"drawtext=text='{clean_text}':fontcolor=white:fontsize=24:box=1:boxcolor=black@0.7:boxborderw=3:x=(w-text_w)/2:y=h-100:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-preset', 'medium',
            '-crf', '20',
            output_file
        ]
        
        try:
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0 and os.path.exists(output_file):
                with open(output_file, 'rb') as f:
                    return f.read()
            else:
                print(f"❌ Simple caption error: {result.stderr}")
                with open(video_path, 'rb') as f:
                    return f.read()
                    
        except Exception as e:
            print(f"❌ Simple caption error: {e}")
            with open(video_path, 'rb') as f:
                return f.read()