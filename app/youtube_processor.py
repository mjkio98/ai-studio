"""
YouTube video processing module.
Handles video ID extraction, transcript retrieval, and AI-powered summarization.
"""

import re
import json
import requests
import time
import random
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import g4f
from g4f.client import Client

from .config import MODEL_CONFIGS, USER_AGENTS, PROXY_LIST, LANGUAGE_TEMPLATES

class YouTubeProcessor:
    def __init__(self):
        # G4F Direct client configuration
        self.g4f_client = Client()
        
        # Primary and fallback configurations
        self.model_configs = MODEL_CONFIGS
        
        # Set initial configuration
        self.current_config_index = 0
        self.model = self.model_configs[0]["model"]
        self.provider = self.model_configs[0]["provider"]

    def _get_random_progress_message(self, language='en', model_name=''):
        """Generate random engaging progress messages instead of boring model names"""
        if language == 'ar':
            messages = [
                'جاري تحليل المحتوى بذكاء اصطناعي متقدم...',
                'نستخدم خوارزميات متطورة لفهم الفيديو...',
                'جاري استخراج أفضل اللحظات من المحتوى...',
                'نحلل كل ثانية لإنشاء محتوى رائع...',
                'الذكاء الاصطناعي يعمل على تحسين النتائج...',
                'جاري فهم سياق المحتوى وتحليله...',
                'نستخدم تقنيات متقدمة لتحليل الصوت والنص...',
                'جاري إنشاء ملخصات ذكية ومفيدة...',
            ]
        else:
            messages = [
                'Analyzing content with advanced AI...',
                'Using sophisticated algorithms to understand the video...',
                'Extracting the best moments from your content...',
                'Analyzing every second to create amazing content...',
                'AI is working to optimize results...',
                'Understanding context and analyzing content...',
                'Using advanced techniques to analyze audio and text...',
                'Creating smart and useful summaries...',
            ]
        return random.choice(messages)

    def try_next_model(self):
        """Switch to the next model configuration in the fallback chain"""
        self.current_config_index += 1
        if self.current_config_index < len(self.model_configs):
            config = self.model_configs[self.current_config_index]
            self.model = config["model"]
            self.provider = config["provider"]
            print(f"🔄 Switching to fallback model: {config['name']}")
            return True
        else:
            print("❌ All fallback models exhausted")
            return False
    
    def reset_to_primary_model(self):
        """Reset to the primary model configuration"""
        self.current_config_index = 0
        config = self.model_configs[0]
        self.model = config["model"]
        self.provider = config["provider"]
        print(f"✅ Reset to primary model: {config['name']}")
    
    def get_current_model_name(self):
        """Get the name of the currently active model"""
        return self.model_configs[self.current_config_index]["name"]
    
    def make_ai_request_with_fallback(self, prompt, progress=None, language='en', stream=False):
        """Make AI request with automatic fallback through all configured models"""
        print(f"🔍 DEBUG: Starting AI request with fallback, stream={stream}")
        last_error = None
        original_config_index = self.current_config_index
        
        # Try each model in the fallback chain
        while self.current_config_index < len(self.model_configs):
            try:
                config = self.model_configs[self.current_config_index]
                print(f"🤖 Trying model: {config['name']}")
                print(f"🔍 DEBUG: Model config - provider: {config.get('provider')}, model: {config.get('model')}")
                
                # Update progress with random engaging message
                if progress:
                    model_attempt = self.current_config_index + 1
                    total_models = len(self.model_configs)
                    random_message = self._get_random_progress_message(language, config["name"])
                    
                    # Detect context based on current progress to avoid conflicts
                    # Safely check if progress has a progress attribute (for ProgressTracker objects)
                    if hasattr(progress, 'progress') and progress.progress:
                        current_progress = progress.progress.get('percentage', 0)
                        if current_progress < 50:
                            # Shorts generation context (40-60% range)
                            ai_progress = 40 + (model_attempt * 3)  # 40%, 43%, 46%, etc.
                        else:
                            # Summary generation context (65%+ range)
                            ai_progress = 65 + (model_attempt * 5)
                    else:
                        # Default progress for simple progress objects
                        ai_progress = 65 + (model_attempt * 5)
                    
                    # Only call update if the progress object has an update method
                    if hasattr(progress, 'update'):
                        progress.update('ai_request', ai_progress, random_message)
                
                print(f"🔍 DEBUG: About to create chat completion...")
                
                # Make the request (removed signal timeout as it doesn't work in threads)
                if stream:
                    print(f"🔍 DEBUG: Creating streaming chat completion...")
                    response = self.g4f_client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        provider=self.provider,
                        stream=True
                    )
                else:
                    print(f"🔍 DEBUG: Creating non-streaming chat completion...")
                    response = self.g4f_client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        provider=self.provider
                    )
                
                print(f"🔍 DEBUG: Chat completion created successfully")
                print(f"✅ Success with model: {config['name']}")
                return response
                
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                config = self.model_configs[self.current_config_index]
                
                print(f"❌ Model {config['name']} failed: {str(e)}")
                
                # Check if this is a retryable error
                if any(keyword in error_msg for keyword in ['rate limit', 'quota', 'timeout', 'connection', 'unavailable']):
                    print(f"🔄 Retryable error detected, trying next model...")
                    if not self.try_next_model():
                        break
                else:
                    # Non-retryable error, but still try next model
                    print(f"⚠️ Non-retryable error, but trying next model anyway...")
                    if not self.try_next_model():
                        break
        
        # If we get here, all models failed
        print(f"💥 All {len(self.model_configs)} models failed")
        
        # Reset to original configuration for next attempt
        self.current_config_index = original_config_index
        config = self.model_configs[self.current_config_index]
        self.model = config["model"]
        self.provider = config["provider"]
        
        # Raise the last error encountered
        if last_error:
            raise last_error
        else:
            raise Exception("All AI models are currently unavailable. Please try again later.")

    def extract_video_id(self, url):
        """Extract video ID from YouTube URL"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
            r'youtube\.com\/watch\?.*v=([^&\n?#]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def get_transcript(self, video_id, progress=None):
        """Get transcript using youtubevideotranscripts.com service"""
        
        # Check for cancellation at start
        if progress and progress.is_cancelled():
            raise Exception("Task cancelled by user")
        
        # Cloud Run optimized approaches: prioritize direct connection, minimal proxy fallbacks
        approaches = [
            {'name': 'Direct YouTubeToTranscript (lxml)', 'parser': 'lxml', 'proxy': None, 'timeout': 15},
            {'name': 'Direct YouTubeToTranscript (html.parser)', 'parser': 'html.parser', 'proxy': None, 'timeout': 15},
            {'name': 'Malaysia Proxy (lxml)', 'parser': 'lxml', 'proxy': PROXY_LIST[0], 'timeout': 12},
            {'name': 'US Elite Proxy (html.parser)', 'parser': 'html.parser', 'proxy': PROXY_LIST[5], 'timeout': 12},
        ]
        
        for approach_idx, approach in enumerate(approaches):
            # Check for cancellation before each attempt
            if progress and progress.is_cancelled():
                raise Exception("Task cancelled by user")
                
            try:
                print(f"Processing attempt {approach_idx + 1}...")
                
                # Update progress based on approach attempt (0-30% range for transcript extraction)
                progress_percentage = 10 + (approach_idx * 5)  # Start from 10%, increment by 5% per attempt
                if progress:
                    progress.update('getting_transcript', progress_percentage, "Processing video...")
                
                # Setup session with random user agent and basic headers
                session = requests.Session()
                
                # Select random user agent
                ua = random.choice(USER_AGENTS)
                
                # Headers to appear like a regular browser
                session.headers.update({
                    'User-Agent': ua,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Referer': 'https://www.google.com/',
                })
                
                # Set proxy if specified
                if approach.get('proxy'):
                    session.proxies.update(approach['proxy'])
                    print(f"Using proxy: {list(approach['proxy'].values())[0]}")
                
                session.timeout = approach.get('timeout', 15)
                
                # Step 1: Build the transcript service URL (much simpler!)
                transcript_service_url = f"https://youtubetotranscript.com/transcript?v={video_id}"
                
                print(f"Analyzing video content...")
                
                # Update progress for analyzing
                if progress:
                    progress.update('getting_transcript', progress_percentage + 2, "Processing video...")
                
                # Check for cancellation before HTTP request
                if progress and progress.is_cancelled():
                    raise Exception("Task cancelled by user")
                
                # Reduced delays for Cloud Run timeout optimization
                if approach.get('proxy'):
                    time.sleep(random.uniform(0.5, 1.5))  # Shorter delay for proxy requests
                else:
                    time.sleep(random.uniform(0.2, 0.8))  # Very short delay for direct requests
                
                # Check for cancellation before HTTP request
                if progress and progress.is_cancelled():
                    raise Exception("Task cancelled by user")
                
                response = session.get(transcript_service_url)
                
                if response.status_code == 429:
                    print(f"Rate limited (429) - will try proxy approaches")
                    continue
                elif response.status_code == 403:
                    print(f"Forbidden (403) - may need different proxy")
                    continue  
                elif response.status_code != 200:
                    print(f"Failed to get transcript service page: {response.status_code}")
                    continue
                
                page_content = response.text
                parser_name = approach.get('parser', 'lxml')
                
                # Check for cancellation after HTTP request
                if progress and progress.is_cancelled():
                    raise Exception("Task cancelled by user")
                
                # Step 2: Parse the page using BeautifulSoup
                print(f"Parsing page with {parser_name}...")
                
                # Update progress for parsing
                if progress:
                    progress.update('getting_transcript', progress_percentage + 3, "Processing video...")
                
                soup = BeautifulSoup(page_content, parser_name)
                
                # Check for cancellation after parsing
                if progress and progress.is_cancelled():
                    raise Exception("Task cancelled by user")
                
                # Step 3: Find elements with the transcript class
                # Class: "inline NA text-primary-content"
                transcript_elements = soup.find_all(class_="inline NA text-primary-content")
                
                if not transcript_elements:
                    # Try alternative selectors in case the classes change slightly
                    print("Exact class not found, trying alternative selectors...")
                    
                    # Try partial class matching
                    transcript_elements = soup.find_all(class_=lambda x: x and 'inline' in x and 'text-primary-content' in x)
                    
                    # Try by class parts
                    if not transcript_elements:
                        transcript_elements = soup.find_all(class_=lambda x: x and 'text-primary-content' in x)
                    
                    # Try by looking for elements with transcript-like content
                    if not transcript_elements:
                        all_elements = soup.find_all(['span', 'div', 'p'], class_=True)
                        for element in all_elements:
                            text_content = element.get_text(strip=True)
                            if len(text_content) > 10 and len(text_content) < 500:  # Individual transcript segments
                                transcript_elements.append(element)
                        
                        # If we found some elements, keep only the ones that look like transcript text
                        if transcript_elements:
                            transcript_elements = [elem for elem in transcript_elements[:50]]  # Limit to first 50
                
                if not transcript_elements:
                    print("Could not find transcript elements")
                    continue
                
                print(f"Found {len(transcript_elements)} content sections")
                
                # Update progress for extraction
                if progress:
                    progress.update('getting_transcript', progress_percentage + 4, "Processing video...")
                
                # Check for cancellation before text extraction
                if progress and progress.is_cancelled():
                    raise Exception("Task cancelled by user")
                
                # Step 4: Extract and combine all transcript text
                transcript_parts = []
                for element in transcript_elements:
                    # Check for cancellation during text extraction loop
                    if progress and progress.is_cancelled():
                        raise Exception("Task cancelled by user")
                        
                    text = element.get_text(strip=True)
                    if text and len(text) > 1:  # Skip empty or single-character elements
                        transcript_parts.append(text)
                
                if not transcript_parts:
                    print("No valid transcript text found in elements")
                    continue
                
                # Check for cancellation before combining text
                if progress and progress.is_cancelled():
                    raise Exception("Task cancelled by user")
                
                # Combine all parts into full transcript
                transcript_text = ' '.join(transcript_parts)
                
                if not transcript_text or len(transcript_text) < 50:
                    print(f"Transcript too short or empty: {len(transcript_text)} characters")
                    continue
                
                # Clean up the transcript
                # Remove extra whitespace and normalize
                transcript_text = re.sub(r'\s+', ' ', transcript_text).strip()
                
                # Remove common unwanted text that might be in the div
                critical_unwanted_phrases = [
                    'transcript not available',
                    'no transcript found',
                    'transcript coming soon'
                ]
                
                # Check for critical phrases that indicate no transcript
                transcript_invalid = False
                for phrase in critical_unwanted_phrases:
                    if phrase.lower() in transcript_text.lower():
                        print(f"Found critical unwanted phrase: {phrase}")
                        transcript_invalid = True
                        break
                
                if transcript_invalid:
                    continue
                
                # Remove UI elements but don't reject the transcript
                ui_phrases = ['click to expand', 'show more', 'show less']
                for phrase in ui_phrases:
                    transcript_text = re.sub(re.escape(phrase), '', transcript_text, flags=re.IGNORECASE)
                
                # Clean up again after removing UI elements
                transcript_text = re.sub(r'\s+', ' ', transcript_text).strip()
                
                # Check if we still have substantial content after cleanup
                if len(transcript_text) < 100:
                    print(f"Transcript too short after cleanup: {len(transcript_text)} characters")
                    continue
                
                # Final check for cancellation before return
                if progress and progress.is_cancelled():
                    raise Exception("Task cancelled by user")
                
                print(f"✅ Video content processed successfully")
                print(f"Content length: {len(transcript_text)} characters")
                print(f"Preview: {transcript_text[:200]}...")
                
                return transcript_text
                
            except Exception as e:
                print(f"Approach '{approach['name']}' failed: {e}")
                continue
        
        # If all approaches fail
        raise Exception("Could not extract transcript from youtubetotranscript.com service. The video might not have captions available.")
    
    def get_transcript_with_timestamps(self, video_id, progress=None):
        """
        Get transcript WITH precise timestamps for video shorts generation.
        Returns list of dicts with 'start', 'duration', 'end', 'text'.
        Raises exception if timestamps are not available.
        """
        
        # Check for cancellation at start
        if progress and progress.is_cancelled():
            raise Exception("Task cancelled by user")
        
        print("🕐 Extracting transcript WITH timestamps for shorts generation...")
        
        # Cloud Run optimized approaches: prioritize direct connection
        approaches = [
            {'name': 'Direct YouTubeToTranscript (lxml)', 'parser': 'lxml', 'proxy': None, 'timeout': 15},
            {'name': 'Direct YouTubeToTranscript (html.parser)', 'parser': 'html.parser', 'proxy': None, 'timeout': 15},
            {'name': 'Malaysia Proxy (lxml)', 'parser': 'lxml', 'proxy': PROXY_LIST[0], 'timeout': 12},
        ]
        
        for approach_idx, approach in enumerate(approaches):
            # Check for cancellation before each attempt
            if progress and progress.is_cancelled():
                raise Exception("Task cancelled by user")
                
            try:
                print(f"Timestamp extraction attempt {approach_idx + 1}...")
                
                # Update progress (30-40% range for timestamp extraction)
                progress_percentage = 30 + (approach_idx * 2)  # 30%, 32%, 34%, etc.
                if progress:
                    progress.update('getting_timestamps', progress_percentage, "Extracting precise timestamps...")
                
                # Setup session
                session = requests.Session()
                ua = random.choice(USER_AGENTS)
                
                session.headers.update({
                    'User-Agent': ua,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Referer': 'https://www.google.com/',
                })
                
                if approach.get('proxy'):
                    session.proxies.update(approach['proxy'])
                    print(f"Using proxy: {list(approach['proxy'].values())[0]}")
                
                session.timeout = approach.get('timeout', 15)
                
                # Build URL
                transcript_service_url = f"https://youtubetotranscript.com/transcript?v={video_id}"
                
                # Check for cancellation before HTTP request
                if progress and progress.is_cancelled():
                    raise Exception("Task cancelled by user")
                
                # Small delay
                if approach.get('proxy'):
                    time.sleep(random.uniform(0.5, 1.5))
                else:
                    time.sleep(random.uniform(0.2, 0.8))
                
                # Fetch page
                response = session.get(transcript_service_url)
                
                if response.status_code == 429:
                    print(f"Rate limited (429) - will try proxy")
                    continue
                elif response.status_code == 403:
                    print(f"Forbidden (403) - may need different proxy")
                    continue  
                elif response.status_code != 200:
                    print(f"Failed to get page: {response.status_code}")
                    continue
                
                # Parse HTML
                parser_name = approach.get('parser', 'lxml')
                print(f"Parsing page with {parser_name}...")
                
                if progress:
                    progress.update('parsing_timestamps', progress_percentage + 2, "Parsing timestamps...")
                
                soup = BeautifulSoup(response.text, parser_name)
                
                # Check for cancellation after parsing
                if progress and progress.is_cancelled():
                    raise Exception("Task cancelled by user")
                
                # Extract transcript segments WITH timestamps
                print("🔍 Looking for timestamped transcript segments...")
                transcript_segments = soup.find_all('span', class_='transcript-segment')
                
                if not transcript_segments:
                    print("❌ No timestamped segments found with class 'transcript-segment'")
                    continue
                
                print(f"✅ Found {len(transcript_segments)} timestamped segments")
                
                # Extract data from each segment
                timestamped_transcript = []
                
                for segment in transcript_segments:
                    try:
                        # Check for cancellation during extraction
                        if progress and progress.is_cancelled():
                            raise Exception("Task cancelled by user")
                        
                        # Get timestamp attributes
                        start_time = segment.get('data-start')
                        duration = segment.get('data-duration')
                        text = segment.get_text(strip=True)
                        
                        # Validate and convert
                        if start_time and text:
                            start = float(start_time)
                            dur = float(duration) if duration else 0.0
                            
                            timestamped_transcript.append({
                                'start': start,
                                'duration': dur,
                                'end': start + dur,
                                'text': text
                            })
                    except (ValueError, TypeError) as e:
                        # Skip invalid segments
                        print(f"⚠️ Skipping invalid segment: {e}")
                        continue
                
                # Validate we got meaningful data
                if not timestamped_transcript:
                    print("❌ No valid timestamped segments extracted")
                    continue
                
                if len(timestamped_transcript) < 5:
                    print(f"❌ Too few segments ({len(timestamped_transcript)}), likely invalid")
                    continue
                
                # Success!
                print(f"✅ Successfully extracted {len(timestamped_transcript)} timestamped segments")
                
                if progress:
                    progress.update('timestamps_ready', progress_percentage + 4, "Timestamps extracted successfully!")
                
                # Display info
                last_segment = timestamped_transcript[-1]
                duration_mins = int(last_segment['end'] // 60)
                duration_secs = int(last_segment['end'] % 60)
                avg_duration = sum(s['duration'] for s in timestamped_transcript) / len(timestamped_transcript)
                
                print(f"📊 Timestamp Extraction Summary:")
                print(f"   Total segments: {len(timestamped_transcript)}")
                print(f"   Video duration: ~{duration_mins}:{duration_secs:02d}")
                print(f"   Average segment: {avg_duration:.2f}s")
                print(f"   First segment: [{timestamped_transcript[0]['start']:.2f}s] {timestamped_transcript[0]['text'][:50]}...")
                
                # Final cancellation check
                if progress and progress.is_cancelled():
                    raise Exception("Task cancelled by user")
                
                return timestamped_transcript
                
            except Exception as e:
                print(f"Approach '{approach['name']}' failed: {e}")
                continue
        
        # If all approaches fail
        raise Exception(
            "Could not extract transcript with timestamps. "
            "This video may not have captions available, or the caption format is not supported. "
            "Timestamps are required for accurate shorts generation."
        )

    def _try_caption_url(self, session, caption_url):
        """Try to fetch and parse captions from a URL"""
        try:
            # Add format parameter if not present
            if '?' in caption_url:
                caption_url += '&fmt=srv3'
            else:
                caption_url += '?fmt=srv3'
            
            print(f"Fetching captions from: {caption_url[:100]}...")
            response = session.get(caption_url, timeout=8)
            print(f"Caption response status: {response.status_code}")
            
            if response.status_code != 200:
                if response.status_code == 429:
                    print("Rate limited on caption URL")
                return None
            
            # Parse XML content
            try:
                root = ET.fromstring(response.text)
                transcript_parts = []
                
                for text_elem in root.findall('.//text'):
                    text_content = text_elem.text or ''
                    if text_content:
                        # Clean up text
                        text_content = re.sub(r'<[^>]+>', '', text_content)
                        text_content = text_content.replace('&amp;', '&')
                        text_content = text_content.replace('&lt;', '<')
                        text_content = text_content.replace('&gt;', '>')
                        text_content = text_content.replace('&quot;', '"')
                        text_content = text_content.replace('&#39;', "'")
                        
                        if text_content.strip():
                            transcript_parts.append(text_content.strip())
                
                if transcript_parts:
                    full_transcript = ' '.join(transcript_parts)
                    full_transcript = re.sub(r'\s+', ' ', full_transcript.strip())
                    
                    if len(full_transcript) >= 50:
                        return full_transcript
            
            except ET.ParseError:
                pass
                
        except Exception:
            pass
        
        return None

    def detect_language(self, text):
        """Detect if the text is Arabic or English based on character analysis
        
        Args:
            text: Either a string (plain text) OR list of dicts with timestamps
                  [{'start': 1.36, 'duration': 1.68, 'text': '...'}]
        """
        if not text:
            return 'en'
        
        # Handle timestamped transcript (list of dicts)
        if isinstance(text, list) and len(text) > 0 and isinstance(text[0], dict):
            # Extract plain text from timestamped segments
            text_content = ' '.join([seg.get('text', '') for seg in text])
            print(f"🔍 Language detection: Converting timestamped transcript to text ({len(text)} segments)")
        else:
            # Handle plain text
            text_content = text
            print(f"🔍 Language detection: Using plain text ({len(text)} chars)")
        
        if not text_content:
            return 'en'
        
        # Count Arabic characters (Unicode range for Arabic script)
        arabic_chars = 0
        english_chars = 0
        total_chars = 0
        
        for char in text_content:
            if char.isalpha():
                total_chars += 1
                # Arabic Unicode ranges: 0x0600-0x06FF (Arabic), 0x0750-0x077F (Arabic Supplement)
                if '\u0600' <= char <= '\u06FF' or '\u0750' <= char <= '\u077F':
                    arabic_chars += 1
                elif 'A' <= char <= 'Z' or 'a' <= char <= 'z':
                    english_chars += 1
        
        if total_chars == 0:
            return 'en'
        
        arabic_ratio = arabic_chars / total_chars
        english_ratio = english_chars / total_chars
        
        print(f"Language detection - Arabic: {arabic_ratio:.2%}, English: {english_ratio:.2%}")
        
        # Enhanced logic for mixed content detection
        print(f"Total characters analyzed: {total_chars}")
        
        # If more than 25% Arabic characters, consider it Arabic (lowered threshold for mixed content)
        if arabic_ratio > 0.25:
            return 'ar'
        elif english_ratio > 0.6:  # Need higher threshold for English to be confident
            return 'en'
        else:
            # Enhanced fallback: check for Arabic words and patterns
            arabic_indicators = ['في', 'من', 'إلى', 'على', 'هذا', 'التي', 'الذي', 'وهو', 'ولا', 'أن', 'كان', 'هي', 'له', 'أو', 'قال', 'بين', 'عند', 'غير', 'بعد', 'حول', 'أول', 'كل', 'لم', 'قد', 'لا', 'ما', 'ان']
            
            # Count Arabic word occurrences (case-insensitive)
            arabic_word_count = 0
            for word in arabic_indicators:
                arabic_word_count += text_content.count(word)
            
            # Also check for Arabic sentence patterns
            arabic_patterns = ['===', 'فيديو', 'VIDEO']  # Common in mixed transcripts
            pattern_count = sum(1 for pattern in arabic_patterns if pattern in text_content)
            
            print(f"Arabic words found: {arabic_word_count}, patterns: {pattern_count}")
            
            # If we found Arabic words or patterns, and Arabic ratio is not negligible
            if (arabic_word_count > 2 or pattern_count > 0) and arabic_ratio > 0.1:
                return 'ar'
            else:
                return 'en'

    def get_video_info(self, video_id):
        """Get basic video information from YouTube oEmbed"""
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            response = requests.get(oembed_url)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'id': video_id,
                    'title': data.get('title', 'Unknown Title'),
                    'author': data.get('author_name', 'Unknown Channel'),
                    'thumbnail': data.get('thumbnail_url')
                }
            else:
                raise Exception("Failed to fetch video information")
                
        except Exception as e:
            raise Exception(f"Unable to fetch video information: {str(e)}")

    def summarize_with_g4f(self, transcript):
        """Generate summary using advanced AI with automatic language detection"""
        try:
            # Detect the language of the transcript
            detected_language = self.detect_language(transcript)
            print(f"Content language: {'Arabic' if detected_language == 'ar' else 'English'}")
            
            # Use the appropriate language-specific method
            return self.summarize_with_g4f_language(transcript, detected_language)
                
        except Exception as e:
            error_msg = str(e)
            if "rate limit" in error_msg.lower():
                raise Exception("Rate limit exceeded. Please try again in a moment.")
            elif "provider" in error_msg.lower():
                raise Exception("AI provider is currently unavailable. Please try again later.")
            elif "model" in error_msg.lower():
                raise Exception("AI model is currently unavailable.")
            else:
                raise Exception(f"Failed to generate summary: {error_msg}")
    
    def summarize_with_g4f_language(self, transcript, language='en', progress=None):
        """Generate summary using advanced AI with language-specific optimization"""
        try:
            # Check for cancellation at start
            if progress and progress.is_cancelled():
                return "Task cancelled by user"
            
            # Get template for the detected/specified language
            template = LANGUAGE_TEMPLATES[language]['youtube_template']
            
            prompt = f"""{template}

Transcript:
{transcript}

Summary:"""

            # Check for cancellation before AI call
            if progress and progress.is_cancelled():
                return "Task cancelled by user"
                
            # Show content preview logic - avoid showing Arabic content to English users
            if progress and len(transcript) > 500:
                # Detect if transcript contains Arabic characters for preview decision
                arabic_char_count = sum(1 for char in transcript[:500] if '\u0600' <= char <= '\u06FF' or '\u0750' <= char <= '\u077F')
                has_arabic_content = arabic_char_count > 10  # If more than 10 Arabic characters in first 500
                
                if language == 'ar':
                    # Arabic UI
                    if progress and hasattr(progress, 'update'):
                        progress.update('analyzing', 62, 'تحليل المحتوى...')
                elif language == 'en' and not has_arabic_content:
                    # English UI with English content - show preview (keep this for user engagement)
                    content_preview = transcript[:300] + "..." if len(transcript) > 300 else transcript
                    if progress and hasattr(progress, 'update'):
                        progress.update('analyzing', 62, 'Analyzing content...', content_preview)
                else:
                    # English UI with other content
                    if progress and hasattr(progress, 'update'):
                        progress.update('analyzing', 62, 'Analyzing content...')
            elif progress:
                # Fallback for short content
                if language == 'ar':
                    if hasattr(progress, 'update'):
                        progress.update('analyzing', 62, 'تحليل المحتوى...')
                else:
                    if hasattr(progress, 'update'):
                        progress.update('analyzing', 62, 'Analyzing content...')
            
            # Try streaming first, fallback to regular if it fails
            summary = ""
            streaming_worked = False
            
            print(f"🔍 DEBUG: About to attempt streaming for YouTube...")
            print(f"🔍 DEBUG: Model: {self.model}")
            print(f"🔍 DEBUG: Provider: {self.provider}")
            print(f"🔍 DEBUG: Language: {language}")
            print(f"🔍 DEBUG: Prompt length: {len(prompt)} chars")
            
            try:
                if progress and hasattr(progress, 'update'):
                    if language == 'ar':
                        progress.update('streaming_start', 65, 'إنشاء الملخص...', '')
                    else:
                        progress.update('streaming_start', 65, 'Creating summary...', '')
                
                print(f"🔍 DEBUG: Calling G4F with stream=True for YouTube...")
                # Attempt streaming with smart fallback
                response = self.make_ai_request_with_fallback(prompt, progress, language, stream=True)
                print(f"🔍 DEBUG: G4F streaming call successful, processing chunks...")
                
                # Process stream with consistent word-by-word streaming for both languages
                for chunk in response:
                    # Check for cancellation during streaming
                    if progress and progress.is_cancelled():
                        print("❌ Task cancelled during streaming")
                        return "Task cancelled by user"
                        
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = getattr(chunk.choices[0], 'delta', None)
                        if delta and hasattr(delta, 'content') and delta.content:
                            summary += delta.content
                            
                            # Update progress frequently for smooth streaming (every few characters)
                            if len(summary) % 5 < len(delta.content):  # More frequent updates
                                percentage = min(65 + (len(summary) / 20), 95)
                                if progress and hasattr(progress, 'update'):
                                    if language == 'ar':
                                        progress.update('streaming', percentage, 
                                                      f'إنشاء الملخص... {percentage:.0f}%', 
                                                      summary)
                                    else:
                                        progress.update('streaming', percentage, 
                                                      f'Creating summary... {percentage:.0f}%', 
                                                      summary)
                
                streaming_worked = True
                print("✅ YouTube streaming successful!")
                
            except Exception as stream_error:
                print(f"❌ YouTube streaming failed: {stream_error}")
                print(f"🔍 DEBUG: Stream error type: {type(stream_error)}")
                print(f"🔍 DEBUG: Stream error details: {str(stream_error)}")
                
                # Fallback to regular generation
                if progress and hasattr(progress, 'update'):
                    # Detect context based on current progress
                    # Safely check if progress has a progress attribute (for ProgressTracker objects)
                    if hasattr(progress, 'progress') and progress.progress:
                        current_progress = progress.progress.get('percentage', 0)
                        if current_progress < 50:
                            # Shorts generation context
                            fallback_progress = 45
                            if language == 'ar':
                                progress.update('fallback', fallback_progress, 'تحليل المحتوى...')
                            else:
                                progress.update('fallback', fallback_progress, 'Analyzing content...')
                        else:
                            # Summary generation context
                            if language == 'ar':
                                progress.update('fallback', 70, 'إنشاء الملخص...')
                            else:
                                progress.update('fallback', 70, 'Creating summary...')
                    else:
                        # Default fallback for simple progress objects
                        if language == 'ar':
                            progress.update('fallback', 70, 'إنشاء الملخص...')
                        else:
                            progress.update('fallback', 70, 'Creating summary...')
                
                print(f"🔍 DEBUG: Attempting fallback non-streaming call for YouTube...")
                response = self.make_ai_request_with_fallback(prompt, progress, language, stream=False)
                summary = response.choices[0].message.content
                
                # Real-time word-by-word streaming simulation
                if progress and hasattr(progress, 'update') and summary:
                    import time
                    
                    # Split into words for realistic typing effect
                    words = summary.split()
                    accumulated = ""
                    
                    # Stream word by word for true real-time effect
                    for i, word in enumerate(words):
                        # Check for cancellation during word streaming
                        if progress and hasattr(progress, 'is_cancelled') and progress.is_cancelled():
                            print("❌ Task cancelled during word-by-word streaming")
                            return "Task cancelled by user"
                            
                        accumulated += word + " "
                        
                        # Detect context based on current progress
                        # Safely check if progress has a progress attribute (for ProgressTracker objects)
                        if hasattr(progress, 'progress') and progress.progress:
                            current_progress = progress.progress.get('percentage', 0)
                            if current_progress < 50:
                                # Shorts generation context (45-55% range for word display)
                                percentage = 45 + (i / len(words) * 10)
                                context_msg = 'تحليل المحتوى...' if language == 'ar' else 'Analyzing content...'
                            else:
                                # Summary generation context (70-95% range)
                                percentage = 70 + (i / len(words) * 25)
                                context_msg = 'إنشاء الملخص...' if language == 'ar' else 'Creating summary...'
                        else:
                            # Default context for simple progress objects
                            percentage = 70 + (i / len(words) * 25)
                            context_msg = 'إنشاء الملخص...' if language == 'ar' else 'Creating summary...'
                        
                        # Send every single word for smooth word-by-word display
                        if language == 'ar':
                            progress.update('word_by_word', percentage, 
                                          f'{context_msg} {percentage:.0f}%', 
                                          accumulated.strip())
                        else:
                            progress.update('word_by_word', percentage, 
                                          f'{context_msg} {percentage:.0f}%', 
                                          accumulated.strip())
                        
                        # Very fast word-by-word streaming for smooth experience
                        time.sleep(0.04)  # 40ms per word = ~900 WPM (very fast streaming)
            
            if progress and hasattr(progress, 'update'):
                if language == 'ar':
                    progress.update('finalizing', 98, 'تم الانتهاء', summary)
                else:
                    progress.update('finalizing', 98, 'Complete', summary)

            return summary
        
        except Exception as e:
            error_msg = str(e)
            if "rate limit" in error_msg.lower():
                raise Exception("Rate limit exceeded. Please try again in a moment.")
            elif "provider" in error_msg.lower():
                raise Exception("AI provider is currently unavailable. Please try again later.")
            elif "model" in error_msg.lower():
                raise Exception("AI model is currently unavailable.")
            else:
                raise Exception(f"Failed to generate summary: {error_msg}")