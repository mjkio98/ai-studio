from flask import Flask, render_template, send_from_directory, request, jsonify, Response
import os
import re
import json
import requests
import argparse
import time
import random
import xml.etree.ElementTree as ET
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import uuid
import queue
from threading import Thread
import g4f
from g4f.client import Client
from bs4 import BeautifulSoup
from requests_html import HTMLSession
from urllib.parse import urlparse, urljoin
import PyPDF2
import asyncio
from datetime import datetime

# Import our application modules
from .config import RATE_LIMITS
from .progress import ProgressTracker, generate_progress_stream, cancel_task_by_id
from .youtube_processor import YouTubeProcessor
from .webpage_analyzer import WebPageAnalyzer
from .client_side_api import register_client_side_api_routes

# Initialize Flask app
app = Flask(__name__, static_folder='../static', template_folder='../templates')

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["500 per hour"],  # Increased global default limit
    storage_uri="memory://",  # Use in-memory storage (simple setup)
)
limiter.init_app(app)

# Register client-side API routes
register_client_side_api_routes(app)

# Add CORS and SharedArrayBuffer headers for FFmpeg.wasm
@app.before_request
def detect_bots():
    """Simple bot detection to prevent automated abuse"""
    user_agent = request.headers.get('User-Agent', '').lower()
    
    # Common bot/scraper user agents
    bot_patterns = [
        'bot', 'crawler', 'spider', 'scraper', 'curl', 'wget', 
        'python-requests', 'scrapy', 'selenium', 'headless',
        'phantom', 'automation', 'test'
    ]
    
    # Skip bot detection for legitimate browsers and local development
    if any(browser in user_agent for browser in ['chrome', 'firefox', 'safari', 'edge', 'opera']):
        return None
    
    # Block obvious bots on API endpoints
    if request.path.startswith('/api/') and any(pattern in user_agent for pattern in bot_patterns):
        return jsonify({
            'error': 'Access denied',
            'message': 'Automated requests are not allowed'
        }), 403
    
    return None

@app.after_request
def add_security_headers(response):
    """Add headers required for SharedArrayBuffer (FFmpeg.wasm)"""
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
    return response

# Route handlers
@app.route('/')
@limiter.exempt  # No rate limit on UI
def index():
    return render_template('dashboard.html')

@app.route('/dashboard')
@limiter.exempt  # No rate limit on UI
def dashboard():
    return render_template('dashboard.html')

@app.route('/classic')
@limiter.exempt  # No rate limit on UI  
def classic_index():
    return render_template('index.html')

@app.route('/old')
@limiter.exempt  # No rate limit on UI
def legacy_index():
    return render_template('index.html')

# NEW SEPARATE PAGES - Added for functionality separation
@app.route('/single-video')
@limiter.exempt  # No rate limit on UI
def single_video_page():
    """Single video analysis page"""
    return render_template('pages/single_video.html')

@app.route('/multi-video')
@limiter.exempt  # No rate limit on UI
def multi_video_page():
    """Multiple videos analysis page"""
    return render_template('pages/multi_video.html')

@app.route('/webpage-analysis')
@limiter.exempt  # No rate limit on UI
def webpage_analysis_page():
    """Webpage analysis page"""
    return render_template('pages/webpage_analysis.html')

@app.route('/chat-agent')
@limiter.exempt  # No rate limit on UI
def chat_agent_page():
    """Chat agent page"""
    return render_template('pages/chat_agent.html')

@app.route('/shorts-generator')
@limiter.exempt  # No rate limit on UI
def shorts_generator_page():
    """Shorts generator page"""
    return render_template('shorts_generator.html')

@app.errorhandler(429)
def rate_limit_handler(e):
    """Handle rate limit exceeded errors"""
    return jsonify({
        'success': False,
        'error': 'Rate limit exceeded. Please try again later.',
        'retry_after': str(e.retry_after) + ' seconds' if hasattr(e, 'retry_after') else 'unknown'
    }), 429

@app.route('/api/health', methods=['GET'])
@limiter.limit(RATE_LIMITS['health_check'])
def health_check():
    """Health check endpoint for the API server"""
    return jsonify({
        'status': 'healthy',
        'service': 'YouTube Transcript & Summary API',
        'version': '1.0.0',
        'rate_limits': RATE_LIMITS,
        'endpoints': {
            'extract_transcript': '/api/extract-transcript',
            'summarize': '/api/summarize', 
            'process_video': '/api/process-video'
        }
    })

@app.route('/api/process-video', methods=['POST'])
@limiter.limit(RATE_LIMITS['process_video'])
def process_video():
    """Complete video processing: extract transcript + generate summary in one call"""
    try:
        data = request.json
        video_url = data.get('url')
        
        if not video_url:
            return jsonify({
                'success': False,
                'error': 'Video URL is required'
            }), 400
        
        processor = YouTubeProcessor()
        video_id = processor.extract_video_id(video_url)
        
        if not video_id:
            return jsonify({
                'success': False,
                'error': 'Invalid YouTube URL'
            }), 400
        
        # Extract transcript
        try:
            video_info = processor.get_video_info(video_id)
            transcript = processor.get_transcript(video_id)
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Failed to extract transcript: {str(e)}'
            }), 500
        
        # Generate summary
        try:
            summary = processor.summarize_with_g4f(transcript)
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Failed to generate summary: {str(e)}'
            }), 500
        
        return jsonify({
            'success': True,
            'video_id': video_id,
            'video_info': video_info,
            'transcript': transcript,
            'summary': summary,
            'model_used': 'GPT-OSS-120B',
            'provider_used': 'DeepInfra'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/api/extract-transcript', methods=['POST'])
@limiter.limit(RATE_LIMITS['extract_transcript'])
def extract_transcript():
    try:
        data = request.json
        video_url = data.get('url')
        
        if not video_url:
            return jsonify({'error': 'Video URL is required'}), 400
        
        # Check for active tasks to prevent concurrent operations
        from .progress import progress_store, cleanup_stale_tasks
        
        # Clean up any stale tasks first
        cleaned_count = cleanup_stale_tasks()
        if cleaned_count > 0:
            print(f"🧹 Cleaned up {cleaned_count} stale tasks")
        
        active_tasks = [task_id for task_id, progress in progress_store.items() 
                       if not progress.get('completed', False)]
        
        if len(active_tasks) > 0:
            print(f"🚫 TASK CONFLICT: {len(active_tasks)} active tasks found: {active_tasks}")
            return jsonify({
                'error': 'Another task is currently running. Please wait for it to complete before starting a new one.',
                'active_tasks': len(active_tasks)
            }), 429  # Too Many Requests
        
        # Create task ID for tracking and cancellation
        task_id = str(uuid.uuid4())
        progress = ProgressTracker(task_id)
        
        def process_transcript():
            try:
                # Check for cancellation at start
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                progress.update('extracting', 10, 'Analyzing YouTube video...')
                
                processor = YouTubeProcessor()
                video_id = processor.extract_video_id(video_url)
                
                if not video_id:
                    progress.error('Invalid YouTube URL')
                    return
                
                # Check for cancellation before getting video info
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                progress.update('getting_info', 30, 'Getting video information...')
                video_info = processor.get_video_info(video_id)
                
                # Check for cancellation before getting transcript
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                progress.update('getting_transcript', 60, 'Processing video...')
                transcript = processor.get_transcript(video_id, progress)
                
                # Check for cancellation before completing
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                progress.complete({
                    'video_id': video_id,
                    'video_info': video_info,
                    'transcript': transcript
                })
                
            except Exception as e:
                progress.error(str(e))
        
        # Start processing in background thread
        thread = Thread(target=process_transcript, daemon=True)
        thread.start()
        
        return jsonify({'task_id': task_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/summarize', methods=['POST'])
@limiter.limit(RATE_LIMITS['summarize'])
def summarize():
    try:
        data = request.json
        transcript = data.get('transcript')
        language = data.get('language', 'auto')  # Use auto-detection for all languages
        
        if not transcript:
            return jsonify({'error': 'Transcript is required'}), 400
        
        if len(transcript) > 200000:  # Increased limit for long-form content (200k characters)
            return jsonify({'error': 'Transcript too long for summarization (max 200,000 characters)'}), 400
        
        # Create task ID for tracking and cancellation
        task_id = str(uuid.uuid4())
        progress = ProgressTracker(task_id)
        
        def process_summary():
            try:
                print(f"🔍 DEBUG: Starting process_summary for transcript length: {len(transcript)}")
                
                # Check for cancellation at start
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                progress.update('summarizing', 20, 'Generating AI summary...')
                print(f"🔍 DEBUG: Updated progress to summarizing")
                
                processor = YouTubeProcessor()
                print(f"🔍 DEBUG: Created YouTubeProcessor")
                
                # Auto-detect language if requested
                if language == 'auto':
                    detected_language = processor.detect_language(transcript)
                    language = detected_language
                    print(f"🌐 Auto-detected language: {'Arabic' if language == 'ar' else 'English'}")
                
                # Check for cancellation before processing
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                print(f"🔍 DEBUG: About to call summarize_with_g4f_language with language: {language}")
                summary = processor.summarize_with_g4f_language(transcript, language, progress)
                print(f"🔍 DEBUG: Completed summarize_with_g4f_language, summary length: {len(summary) if summary else 0}")
                
                # Check for cancellation before completing
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                progress.complete({
                    'summary': summary,
                    'model_used': 'GPT-OSS-120B',
                    'provider_used': 'DeepInfra'
                })
                
            except Exception as e:
                progress.error(f'Failed to generate summary: {str(e)}')
        
        # Start processing in background thread
        thread = Thread(target=process_summary, daemon=True)
        thread.start()
        
        return jsonify({'task_id': task_id})
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to generate summary: {str(e)}'
        }), 500

@app.route('/api/summarize-video-stream', methods=['POST'])
@limiter.limit(RATE_LIMITS['summarize_video_stream'])
def summarize_video_stream():
    """Start streaming YouTube video analysis - combines transcript extraction and summarization"""
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'YouTube URL is required'}), 400
        
        url = data['url'].strip()
        language = data.get('language', 'auto')  # Auto-detect language
        
        if not url:
            return jsonify({'error': 'Please enter a YouTube URL'}), 400
        
        # Basic YouTube URL validation
        if not any(pattern in url.lower() for pattern in ['youtube.com', 'youtu.be']):
            return jsonify({'error': 'Please enter a valid YouTube URL'}), 400
        
        # Check for active tasks to prevent concurrent operations
        from .progress import progress_store, cleanup_stale_tasks
        
        # Clean up any stale tasks first
        cleaned_count = cleanup_stale_tasks()
        if cleaned_count > 0:
            print(f"🧹 Cleaned up {cleaned_count} stale tasks")
        
        active_tasks = [task_id for task_id, progress in progress_store.items() 
                       if not progress.get('completed', False)]
        
        if len(active_tasks) > 0:
            print(f"🚫 VIDEO SUMMARIZE TASK CONFLICT: {len(active_tasks)} active tasks found: {active_tasks}")
            return jsonify({
                'error': 'Another task is currently running. Please wait for it to complete before summarizing.',
                'active_tasks': len(active_tasks)
            }), 429  # Too Many Requests
            return jsonify({'error': 'Please enter a valid YouTube URL'}), 400
        
        # Generate unique task ID
        task_id = str(uuid.uuid4())
        progress = ProgressTracker(task_id)
        
        def get_localized_message(key, lang=language, **kwargs):
            """Get localized progress messages based on user's language preference"""
            messages = {
                'en': {
                    'extracting': 'Preparing content...',
                    'processing': 'Processing...',
                    'analyzing': 'Analyzing...',
                    'generating': 'Generating summary...',
                    'streaming': 'Creating summary...'
                },
                'ar': {
                    'extracting': 'إعداد المحتوى...',
                    'processing': 'معالجة...',
                    'analyzing': 'تحليل...',
                    'generating': 'إنتاج الملخص...',
                    'streaming': 'إنشاء الملخص...'
                }
            }
            
            lang_messages = messages.get(lang, messages['en'])
            message = lang_messages.get(key, messages['en'].get(key, key))
            return message.format(**kwargs)
        
        def process_video_in_background():
            nonlocal language  # Allow modification of outer scope variable
            try:
                print(f"🔍 DEBUG: process_video_in_background started")
                print(f"🔍 DEBUG: URL: {url}")
                print(f"🔍 DEBUG: Language parameter: {language}")
                
                progress.update('extracting', 10, get_localized_message('extracting'))
                
                # Initialize processor
                processor = YouTubeProcessor()
                
                # Extract video ID
                print(f"🔍 DEBUG: Extracting video ID from URL")
                video_id = processor.extract_video_id(url)
                
                if not video_id:
                    progress.error('Invalid YouTube URL')
                    return
                
                # Check for cancellation before getting video info
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                progress.update('getting_info', 30, get_localized_message('processing'))
                print(f"🔍 DEBUG: Getting video info for: {video_id}")
                video_info = processor.get_video_info(video_id)
                
                # Check for cancellation before getting transcript
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                progress.update('getting_transcript', 50, get_localized_message('extracting'))
                print(f"🔍 DEBUG: Getting transcript for: {video_id}")
                transcript = processor.get_transcript(video_id, progress)
                
                if not transcript or len(transcript.strip()) < 50:
                    progress.error("No valid transcript found for this video")
                    return
                
                print(f"🔍 DEBUG: Transcript extracted, length: {len(transcript)}")
                progress.update('analyzing', 50, get_localized_message('analyzing'))
                
                # Auto-detect language if requested
                if language == 'auto':
                    detected_language = processor.detect_language(transcript)
                    language = detected_language
                    print(f"🌐 Auto-detected language: {'Arabic' if language == 'ar' else 'English'}")
                
                # Generate summary with streaming
                print(f"🔍 DEBUG: About to generate summary with streaming, language: {language}")
                summary = processor.summarize_with_g4f_language(transcript, language, progress)
                
                if not summary or summary.startswith('Error') or summary == 'Task cancelled by user':
                    progress.error(f"Failed to generate summary: {summary}")
                    return
                
                print(f"🔍 DEBUG: Summary generated, length: {len(summary)}")
                
                # Complete with final result
                progress.complete({
                    'success': True,
                    'summary': summary,
                    'video_info': video_info,
                    'video_id': video_id,
                    'transcript_length': len(transcript),
                    'ai_engine': 'Qwen/Qwen3-235B-A22B-Instruct-2507',
                    'provider': 'DeepInfra'
                })
                    
            except Exception as e:
                print(f"🔍 DEBUG: Error in process_video_in_background: {str(e)}")
                progress.error(f'Video analysis failed: {str(e)}')
        
        # Start background processing
        Thread(target=process_video_in_background, daemon=True).start()
        
        return jsonify({'task_id': task_id, 'stream_url': f'/progress/{task_id}'})
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/process-multiple-videos', methods=['POST'])
@limiter.limit(RATE_LIMITS['process_multiple_videos'])
def process_multiple_videos():
    """Process multiple YouTube videos and create a combined summary"""
    try:
        data = request.get_json()
        
        if not data or 'urls' not in data:
            return jsonify({'error': 'URLs are required'}), 400
        
        urls = data['urls']
        language = data.get('language', 'auto')  # Auto-detect language
        if not isinstance(urls, list) or len(urls) == 0:
            return jsonify({'error': 'At least one URL is required'}), 400
        
        if len(urls) > 4:  # Limit to 4 videos max
            return jsonify({'error': 'Maximum 4 videos allowed'}), 400
        
        # Check for duplicate URLs
        unique_urls = set(urls)
        if len(unique_urls) != len(urls):
            return jsonify({'error': 'Duplicate URLs are not allowed'}), 400
        
        # Create task ID for tracking and cancellation
        task_id = str(uuid.uuid4())
        progress = ProgressTracker(task_id)
        
        def process_multiple():
            nonlocal language  # Allow modification of the outer scope language variable
            try:
                # Check for cancellation at start
                if progress.is_cancelled():
                    progress.cancel()
                    return
        
                processor = YouTubeProcessor()
                video_data = []
                all_transcripts = []
                
                # Process each video with detailed progress updates
                for i, url in enumerate(urls):
                    # Check for cancellation before each video
                    if progress.is_cancelled():
                        progress.cancel()
                        return
                    
                    video_progress_start = (i / len(urls)) * 75  # Reserve last 25% for synthesis
                    video_progress_end = ((i + 1) / len(urls)) * 75
                    
                    # Show video processing with simple messages
                    if language == 'ar':
                        progress.update('extracting_video', 
                                      video_progress_start + 2,
                                      f'معالجة فيديو {i+1}/{len(urls)}...')
                    else:
                        progress.update('extracting_video', 
                                      video_progress_start + 2,
                                      f'Processing video {i+1}/{len(urls)}...')
                    
                    try:
                        # Extract video ID with progress update
                        video_id = processor.extract_video_id(url)
                        if not video_id:
                            progress.error(f'Invalid YouTube URL: {url}')
                            return
                        
                        # Get video info first (faster operation)
                        if language == 'ar':
                            progress.update('getting_info', 
                                          video_progress_start + 5,
                                          f'فيديو {i+1}/{len(urls)}...')
                        else:
                            progress.update('getting_info', 
                                          video_progress_start + 5,
                                          f'Video {i+1}/{len(urls)}...')
                        
                        video_info = processor.get_video_info(video_id)
                        
                        # Processing video content
                        if language == 'ar':
                            progress.update('processing_transcript', 
                                          video_progress_start + 8,
                                          f'فيديو {i+1}: {video_info["title"][:30]}...')
                        else:
                            progress.update('processing_transcript', 
                                          video_progress_start + 8,
                                          f'Video {i+1}: {video_info["title"][:30]}...')
                        
                        # Get transcript (this takes the most time)
                        transcript_text = processor.get_transcript(video_id, progress)
                        
                        # Video processing complete
                        if language == 'ar':
                            progress.update('transcript_complete', 
                                          video_progress_end - 2,
                                          f'تم الانتهاء من فيديو {i+1}/{len(urls)}')
                        else:
                            progress.update('transcript_complete', 
                                          video_progress_end - 2,
                                          f'Completed video {i+1}/{len(urls)}')
                        
                        video_data.append({
                            'video_id': video_id,
                            'url': url,
                            'transcript': transcript_text,
                            'info': video_info
                        })
                        
                        # Add labeled transcript for combined processing
                        labeled_transcript = f"\n\n=== VIDEO {i+1}: {video_info['title']} ===\n{transcript_text}\n"
                        all_transcripts.append(labeled_transcript)
                        
                    except Exception as e:
                        progress.error(f'Failed to process video {i+1}: {str(e)}')
                        return
        
                
                # Check for cancellation before synthesis
                if progress.is_cancelled():
                    progress.cancel()
                    return
                    
                # Show combining progress
                if language == 'ar':
                    progress.update('combining', 77, 'دمج المحتوى...')
                else:
                    progress.update('combining', 77, 'Processing content...')
                
                # Combine all transcripts
                combined_transcript = "\n".join(all_transcripts)
                
                # Show combination complete
                if language == 'ar':
                    progress.update('combined', 79, 'إعداد المحتوى...')
                else:
                    progress.update('combined', 79, 'Preparing content...')
                
                # Create enhanced prompt for multiple video synthesis
                video_titles = [video['info']['title'] for video in video_data]
                
                # Set language-specific headers and instructions
                if language == 'ar':
                    headers = {
                        'title': f'# التوليف الموحد لـ {len(video_data)} فيديوهات',
                        'core': '## 🌟 الرسالة الأساسية الموحدة',
                        'core_desc': '[قم بإنشاء فهم شامل واحد يجمع جميع رؤى الفيديوهات]',
                        'framework': '## 🧩 إطار المعرفة المتكامل',
                        'framework_desc': '[اجمع كل المعلومات في هيكل معرفي شامل]',
                        'understanding': '## 💎 الفهم المحسّن',
                        'understanding_desc': '[أظهر كيف يخلق دمج هذه الفيديوهات فهماً أعمق من أي فيديو منفرد]',
                        'action': '## 🎯 خطة العمل المجمعة',
                        'action_desc': '[قدم إرشاداً موحداً يجمع الحكمة من جميع الفيديوهات]',
                        'summary': '## 🔮 ملخص الصورة الكاملة',
                        'summary_desc': '[اعرض الفهم الكامل الموحد المحقق من خلال التوليف]',
                        'instruction': f'قم بتوليف الفيديوهات التالية البالغ عددها {len(video_data)} فيديو يوتيوب في فهم شامل موحد. لا تلخص كل فيديو منفرداً، بل اجمع كل المعلومات والأفكار من جميع الفيديوهات لتكوين صورة كاملة موحدة وتوليف فكرة متماسكة واحدة تتضمن كل الرؤى القيمة من كلا الفيديوهين معاً.',
                        'videos_label': 'الفيديوهات المجمعة:'
                    }
                else:
                    headers = {
                        'title': f'# Unified Synthesis of {len(video_data)} Videos',
                        'core': '## 🌟 Core Unified Message',
                        'core_desc': '[Create a single overarching understanding that combines all video insights]',
                        'framework': '## 🧩 Integrated Knowledge Framework',
                        'framework_desc': '[Weave together all information into a comprehensive knowledge structure]',
                        'understanding': '## 💎 Enhanced Understanding',
                        'understanding_desc': '[Show how combining these videos creates deeper insight than any single video alone]',
                        'action': '## 🎯 Synthesized Action Plan',
                        'action_desc': '[Provide unified guidance that incorporates wisdom from all videos]',
                        'summary': '## 🔮 Complete Picture Summary',
                        'summary_desc': '[Present the full, unified understanding achieved through synthesis]',
                        'instruction': f'Synthesize the following {len(video_data)} YouTube videos into a unified comprehensive understanding. Do NOT summarize each video separately. Instead, combine all information from ALL videos to create a complete picture and synthesize into a single cohesive idea that incorporates all valuable insights from both videos together.',
                        'videos_label': 'Videos being synthesized:'
                    }
                
                # Create enhanced prompt with language specification
                language_instruction = ""
                if language == 'ar':
                    language_instruction = "\n\nمهم جداً: يجب أن يكون الملخص بالكامل باللغة العربية، حتى لو كانت بعض الفيديوهات باللغة الإنجليزية."
                else:
                    language_instruction = "\n\nIMPORTANT: Provide the summary entirely in English, even if some videos contain Arabic content."
                
                prompt = f"""{headers['instruction']}{language_instruction}

IMPORTANT: This is NOT about summarizing individual videos. You must COMBINE and SYNTHESIZE the content from ALL {len(video_data)} videos into ONE unified understanding.

{headers['videos_label']}
{chr(10).join([f"{i+1}. {title}" for i, title in enumerate(video_titles)])}

SYNTHESIS REQUIREMENT: Look for connections, patterns, and complementary ideas between these videos. Create ONE integrated understanding that shows how the videos work together to form a complete picture.

Please structure your response as follows:
{headers['title']}

{headers['core']}
{headers['core_desc']}

{headers['framework']}
{headers['framework_desc']}

{headers['understanding']}
{headers['understanding_desc']}

{headers['action']}
{headers['action_desc']}

{headers['summary']}
{headers['summary_desc']}

Here are the complete transcripts from ALL videos (analyze them together):
{combined_transcript}

REMINDER: Synthesize - don't just summarize one video. Show how ALL videos connect and complement each other."""
        
                # Check for cancellation before AI processing
                if progress.is_cancelled():
                    progress.cancel()
                    return
                    
                # Show language detection
                if language == 'ar':
                    progress.update('detecting_language', 81, 'جاري المعالجة...')
                else:
                    progress.update('detecting_language', 81, 'Processing...')
                
                # Auto-detect language from combined transcript for better handling of mixed content
                detected_language = processor.detect_language(combined_transcript)
                print(f"Combined transcript detected language: {'Arabic' if detected_language == 'ar' else 'English'}")
                
                # Store original language for comparison
                original_language = language
                
                # Language processing complete
                if detected_language != original_language:
                    print(f"Language override: User specified '{original_language}' but detected '{detected_language}' - using detected language")
                    language = detected_language
                
                if language == 'ar':
                    progress.update('language_ready', 83, 'جاهز للتلخيص...')
                else:
                    progress.update('language_ready', 83, 'Ready for summarization...')
                
                # Check for cancellation before AI summary
                if progress.is_cancelled():
                    progress.cancel()
                    return
                    
                # Generate combined summary using streaming approach
                summary = ""
                streaming_worked = False
                
                print(f"🔍 DEBUG: About to attempt streaming for multi-video synthesis...")
                print(f"🔍 DEBUG: Model: {processor.model}")
                print(f"🔍 DEBUG: Provider: {processor.provider}")
                print(f"🔍 DEBUG: Language: {language}")
                print(f"🔍 DEBUG: Prompt length: {len(prompt)} chars")
                
                try:
                    # Start streaming with simple message
                    if language == 'ar':
                        progress.update('streaming_start', 85, 'إنشاء الملخص...')
                    else:
                        progress.update('streaming_start', 85, 'Creating summary...')
                    
                    # Attempt streaming for multi-video
                    response = processor.g4f_client.chat.completions.create(
                        model=processor.model,
                        messages=[
                            {"role": "user", "content": prompt}
                        ],
                        provider=processor.provider,
                        stream=True
                    )
                    print(f"🔍 DEBUG: Multi-video streaming call successful, processing chunks...")
                    
                    # Process stream with real-time updates (more frequent updates for smoothness)
                    for chunk in response:
                        # Check for cancellation during streaming
                        if progress.is_cancelled():
                            print("❌ Multi-video task cancelled during streaming")
                            progress.cancel()
                            return
                            
                        if hasattr(chunk, 'choices') and chunk.choices:
                            delta = getattr(chunk.choices[0], 'delta', None)
                            if delta and hasattr(delta, 'content') and delta.content:
                                summary += delta.content
                                
                                # Update progress with simple percentage
                                if len(summary) % 3 < len(delta.content):  # More frequent updates
                                    percentage = min(85 + (len(summary) / 20), 97)  # Start from 85%
                                    if language == 'ar':
                                        progress.update('streaming', percentage, 
                                                      f'إنشاء الملخص... {percentage:.0f}%', 
                                                      summary)
                                    else:
                                        progress.update('streaming', percentage, 
                                                      f'Creating summary... {percentage:.0f}%', 
                                                      summary)
                    
                    streaming_worked = True
                    print("✅ Multi-video streaming successful!")
                    
                except Exception as stream_error:
                    print(f"❌ Multi-video streaming failed: {stream_error}")
                    
                    # Fallback to regular generation
                    if language == 'ar':
                        progress.update('fallback', 87, 'إنشاء الملخص...')
                    else:
                        progress.update('fallback', 87, 'Creating summary...')
                    
                    try:
                        response = processor.g4f_client.chat.completions.create(
                            model=processor.model,
                            messages=[
                                {"role": "user", "content": prompt}
                            ],
                            provider=processor.provider
                        )
                        summary = response.choices[0].message.content
                        
                        # Real-time word-by-word streaming simulation for fallback (faster updates)
                        if summary:
                            import time
                            words = summary.split()
                            accumulated = ""
                            
                            for i, word in enumerate(words):
                                if progress.is_cancelled():
                                    progress.cancel()
                                    return
                                    
                                accumulated += word + " "
                                percentage = 87 + (i / len(words) * 10)  # 87% to 97%
                                
                                if language == 'ar':
                                    progress.update('word_synthesis', percentage, 
                                                  f'إنشاء الملخص... {percentage:.0f}%', 
                                                  accumulated.strip())
                                else:
                                    progress.update('word_synthesis', percentage, 
                                                  f'Creating summary... {percentage:.0f}%', 
                                                  accumulated.strip())
                                
                                time.sleep(0.04)  # 40ms per word
                                
                    except Exception as fallback_error:
                        error_msg = str(fallback_error)
                        if "rate limit" in error_msg.lower():
                            progress.error("Rate limit exceeded. Please try again in a moment.")
                        elif "provider" in error_msg.lower():
                            progress.error("AI provider is currently unavailable. Please try again later.")
                        elif "model" in error_msg.lower():
                            progress.error("AI model is currently unavailable.")
                        else:
                            progress.error(f"Failed to generate summary: {error_msg}")
                        return
                
                # Check for cancellation before completion
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                # Prepare video info for frontend
                video_infos = [video['info'] for video in video_data]
                
                progress.complete({
                    'combined_summary': summary,
                    'video_infos': video_infos,
                    'video_count': len(video_data),
                    'model_used': 'GPT-OSS-120B',
                    'provider_used': 'DeepInfra'
                })
                
            except Exception as e:
                progress.error(str(e))
        
        # Start processing in background thread
        thread = Thread(target=process_multiple, daemon=True)
        thread.start()
        
        return jsonify({'task_id': task_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analyze-webpage-stream', methods=['POST'])
@limiter.limit(RATE_LIMITS['analyze_webpage_stream'])
def analyze_webpage_stream():
    """Start streaming webpage analysis"""
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'Webpage URL is required'}), 400
        
        url = data['url'].strip()
        language = data.get('language', 'auto')  # Auto-detect language
        
        if not url:
            return jsonify({'error': 'Please enter a webpage URL'}), 400
        
        # Basic URL validation
        if not any(url.startswith(prefix) for prefix in ['http://', 'https://', 'www.']):
            return jsonify({'error': 'Please enter a valid URL (e.g., https://example.com)'}), 400
        
        # Check for active tasks to prevent concurrent operations
        from .progress import progress_store, cleanup_stale_tasks
        
        # Clean up any stale tasks first
        cleaned_count = cleanup_stale_tasks()
        if cleaned_count > 0:
            print(f"🧹 Cleaned up {cleaned_count} stale tasks")
        
        active_tasks = [task_id for task_id, progress in progress_store.items() 
                       if not progress.get('completed', False)]
        
        if len(active_tasks) > 0:
            print(f"🚫 WEBPAGE ANALYSIS TASK CONFLICT: {len(active_tasks)} active tasks found: {active_tasks}")
            return jsonify({
                'error': 'Another task is currently running. Please wait for it to complete before analyzing a webpage.',
                'active_tasks': len(active_tasks)
            }), 429  # Too Many Requests
        
        # Generate unique task ID
        task_id = str(uuid.uuid4())
        progress = ProgressTracker(task_id)
        
        def get_localized_message(key, lang=language, **kwargs):
            """Get localized progress messages based on user's language preference"""
            messages = {
                'en': {
                    'extracting': 'Loading content...',
                    'crawling': 'Processing...',
                    'analyzing': 'Analyzing...',
                    'generating': 'Creating summary...'
                },
                'ar': {
                    'extracting': 'تحميل المحتوى...',
                    'crawling': 'معالجة...',
                    'analyzing': 'تحليل...',
                    'generating': 'إنشاء الملخص...'
                }
            }
            
            lang_messages = messages.get(lang, messages['en'])
            message = lang_messages.get(key, messages['en'].get(key, key))
            return message.format(**kwargs)
        
        def analyze_in_background():
            try:
                print(f"🔍 DEBUG: analyze_in_background started")
                print(f"🔍 DEBUG: URL: {url}")
                print(f"🔍 DEBUG: Language parameter: {language}")
                
                progress.update('extracting', 10, get_localized_message('extracting', url=url))
                
                # Initialize analyzer
                analyzer = WebPageAnalyzer()
                
                # Extract content with progress tracking
                progress.update('crawling', 30, get_localized_message('crawling'))
                print(f"🔍 DEBUG: About to call extract_content with target_language={language}")
                content_data = analyzer.extract_content(url, return_summary=True, target_language=language, progress=progress)
                
                if not content_data.get('success', True):
                    progress.error(f"Failed to process webpage: {content_data.get('error', 'Unknown error')}")
                    return
                
                # Final result
                if 'summary' in content_data:
                    progress.complete({
                        'success': True,
                        'url': url,
                        'title': content_data['title'],
                        'content_length': content_data.get('original_length', 0),
                        'extraction_method': content_data['method'],
                        'summary': content_data['summary'],
                        'language_detected': 'auto',
                        'ai_engine': 'G4F Qwen3-235B',
                        'processing_method': 'Crawl4AI + G4F Direct Summarization',
                        'warning': content_data.get('warning')
                    })
                else:
                    progress.error("Content extraction failed")
                    
            except Exception as e:
                progress.error(f'Analysis failed: {str(e)}')
        
        # Start background analysis
        Thread(target=analyze_in_background, daemon=True).start()
        
        return jsonify({'task_id': task_id, 'stream_url': f'/progress/{task_id}'})
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/analyze-webpage', methods=['POST'])
@limiter.limit(RATE_LIMITS['analyze_webpage'])
def analyze_webpage():
    """Analyze and summarize content from any webpage"""
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'Webpage URL is required'}), 400
        
        url = data['url'].strip()
        language = data.get('language', 'auto')  # Auto-detect language
        
        if not url:
            return jsonify({'error': 'Please enter a webpage URL'}), 400
        
        # Basic URL validation
        if not any(url.startswith(prefix) for prefix in ['http://', 'https://', 'www.']):
            return jsonify({'error': 'Please enter a valid URL (e.g., https://example.com)'}), 400
        
        # Initialize webpage analyzer
        analyzer = WebPageAnalyzer()
        
        # Extract and summarize content from webpage using new method
        try:
            # Use the new extract_content method with summarization and language preference
            content_data = analyzer.extract_content(url, return_summary=True, target_language=language)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

        # Check if summarization was successful
        if not content_data.get('success', True):
            return jsonify({'error': f"Failed to process webpage: {content_data.get('error', 'Unknown error')}"}), 500
        
        # If there is a warning (e.g., PDF truncated), include it in the response
        warning = content_data.get('warning')
        
        # Check if we got a summary (new method) or raw content (fallback)
        if 'summary' in content_data:
            # New method returned summary directly
            summary_text = content_data['summary']
            if len(summary_text.strip()) < 20:  # More reasonable threshold
                print(f"Summary too short ({len(summary_text)} chars): {summary_text[:100]}")
                return jsonify({'error': f'Generated summary is too short ({len(summary_text)} characters). Please try again.'}), 400
        else:
            # Fallback - we got raw content, need to summarize with old method
            content_text = content_data.get('content', '')
            if len(content_text) < 100:
                return jsonify({'error': 'Webpage does not contain enough content to analyze'}), 400

        # Handle both new summary format and fallback
        if 'summary' in content_data:
            # New method - summary already generated
            summary_text = content_data['summary']
            title = content_data['title']
            method = content_data['method']
            original_length = content_data.get('original_length', 0)
            
            return jsonify({
                'success': True,
                'url': url,
                'title': title,
                'content_length': original_length,
                'extraction_method': method,
                'summary': summary_text,
                'language_detected': 'auto',  # G4F handles language detection
                'ai_engine': 'G4F GPT-4o-mini',
                'processing_method': 'Crawl4AI + G4F Direct Summarization',
                'warning': warning
            })
        else:
            # Fallback method - process with old pipeline
            content_text = content_data['content']
            
            processor = YouTubeProcessor()
            detected_language = processor.detect_language(content_text)
            print(f"Webpage content language: {'Arabic' if detected_language == 'ar' else 'English'}")
            if not language or language not in ['en', 'ar']:
                language = detected_language

            # If content is too long, split into chunks
            max_len = 200000
            if len(content_text) > max_len:
                print(f"Content is too long ({len(content_text)} chars), splitting into chunks...")
                summaries = []
                for i in range(0, len(content_text), max_len):
                    chunk = content_text[i:i+max_len]
                    try:
                        chunk_summary = processor.summarize_with_g4f_language(chunk, language)
                    except Exception as e:
                        chunk_summary = f"[Error summarizing chunk {i//max_len+1}: {str(e)}]"
                    summaries.append(f"Summary of part {i//max_len+1} (chars {i+1}-{min(i+max_len, len(content_text))}):\n" + chunk_summary)
                summary = '\n\n'.join(summaries)
            else:
                try:
                    summary = processor.summarize_with_g4f_language(content_text, language)
                except Exception as e:
                    return jsonify({'error': f'Failed to generate summary: {str(e)}'}), 500

            return jsonify({
                'success': True,
                'url': url,
                'title': content_data['title'],
                'content_length': len(content_text),
                'extraction_method': content_data['method'],
                'content': content_text[:max_len*3],  # Only return first 600k chars for safety
                'summary': summary,
                'language_detected': detected_language,
                'ai_engine': 'G4F Fallback',
                'processing_method': 'Fallback Processing',
                'warning': warning
            })
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/generate-shorts-stream', methods=['POST'])
@limiter.limit(RATE_LIMITS['summarize_video_stream'])  # Use same rate limit as video processing
def generate_shorts_stream():
    """Generate YouTube Shorts clips with video processing"""
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'YouTube URL is required'}), 400
        
        url = data['url'].strip()
        language = data.get('language', 'auto')  # Auto-detect language
        
        if not url:
            return jsonify({'error': 'Please enter a YouTube URL'}), 400
        
        # Basic YouTube URL validation
        if not any(pattern in url.lower() for pattern in ['youtube.com', 'youtu.be']):
            return jsonify({'error': 'Please enter a valid YouTube URL'}), 400
        
        # Check for active tasks to prevent overwhelming the system
        from .progress import progress_store, cleanup_stale_tasks, add_to_queue, get_processing_status
        
        # Clean up any stale tasks first
        cleaned_count = cleanup_stale_tasks()
        if cleaned_count > 0:
            print(f"🧹 Cleaned up {cleaned_count} stale tasks")
        
        # Check current processing status
        status = get_processing_status()
        print(f"🔍 PROCESSING STATUS: {status['active_tasks_count']}/{status['max_concurrent_tasks']} active, {status['queued_tasks_count']} queued")
        
        # Generate unique task ID and add to queue
        task_id = str(uuid.uuid4())
        progress = ProgressTracker(task_id)
        
        # Add to queue system
        queue_position = add_to_queue(task_id)
        
        if queue_position == -1:
            # Queue is full
            return jsonify({
                'error': 'Server is currently at full capacity. Please try again later.',
                'queue_full': True,
                'max_queue_size': status['max_queue_size'],
                'active_tasks': status['active_tasks_count'],
                'queued_tasks': status['queued_tasks_count']
            }), 429
        elif queue_position == 0:
            print(f"🎯 CONCURRENT: Starting shorts generation immediately for task {task_id}")
            progress.update_queue_status()
        else:
            estimated_wait = get_estimated_wait_time(task_id)
            print(f"🎯 CONCURRENT: Task {task_id} added to queue at position {queue_position} (estimated wait: {estimated_wait} minutes)")
            progress.update_queue_status()
            
            # Return immediately with queue status - don't wait for older sequential behavior
            return jsonify({
                'task_id': task_id, 
                'stream_url': f'/progress/{task_id}',
                'queue_position': queue_position,
                'estimated_wait_minutes': estimated_wait,
                'message': f'Added to queue at position #{queue_position}',
                'concurrent_processing': True
            })
        
        def get_localized_message(key, lang=language, **kwargs):
            """Get localized progress messages based on user's language preference"""
            messages = {
                'extracting': {
                    'en': 'Extracting video transcript...',
                    'ar': 'استخراج النص من الفيديو...'
                },
                'processing': {
                    'en': 'Processing video information...',
                    'ar': 'معالجة معلومات الفيديو...'
                },
                'analyzing': {
                    'en': 'Analyzing content for clips...',
                    'ar': 'تحليل المحتوى لإنشاء المقاطع...'
                },
                'downloading': {
                    'en': 'Downloading video...',
                    'ar': 'تحميل الفيديو...'
                },
                'generating': {
                    'en': 'Generating shorts clips...',
                    'ar': 'إنشاء مقاطع الشورتس...'
                },
                'complete': {
                    'en': 'Shorts generation complete!',
                    'ar': 'تم إنشاء الشورتس بنجاح!'
                }
            }
            return messages.get(key, {}).get(lang, messages.get(key, {}).get('en', key))
        
        def process_shorts_in_background():
            nonlocal language  # Allow access to the language variable from outer scope
            try:
                # Use the new concurrent processing wait system
                from .progress import wait_for_processing_slot, get_queue_position
                
                # Wait for processing slot (with timeout)
                if not wait_for_processing_slot(task_id, timeout=600):  # 10 minute timeout
                    if progress.is_cancelled():
                        progress.cancel()
                        return
                    else:
                        progress.error('Request timed out waiting for processing slot')
                        return
                
                # Now we can start processing
                print(f"🔍 DEBUG: Starting concurrent shorts processing for task {task_id}")
                progress.update('extracting', 10, get_localized_message('extracting'))
                
                # Initialize processor
                processor = YouTubeProcessor()
                
                # Extract video ID
                print(f"🔍 DEBUG: Extracting video ID from URL")
                video_id = processor.extract_video_id(url)
                
                if not video_id:
                    progress.error('Invalid YouTube URL')
                    return
                
                # Check for cancellation before getting video info
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                progress.update('getting_info', 20, get_localized_message('processing'))
                print(f"🔍 DEBUG: Getting video info for: {video_id}")
                video_info = processor.get_video_info(video_id)
                
                # Check for cancellation before getting transcript
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                progress.update('getting_transcript', 30, get_localized_message('extracting'))
                print(f"🔍 DEBUG: Getting transcript WITH TIMESTAMPS for shorts: {video_id}")
                
                # Use the new timestamped method for shorts generation
                try:
                    transcript = processor.get_transcript_with_timestamps(video_id, progress)
                    print(f"✅ Timestamped transcript extracted: {len(transcript)} segments")
                except Exception as timestamp_error:
                    progress.error(f"Failed to extract timestamps: {str(timestamp_error)}")
                    return
                
                if not transcript or len(transcript) < 5:
                    progress.error("No valid timestamped transcript found. This video may not have captions or timestamps available.")
                    return
                
                print(f"🔍 DEBUG: Timestamped transcript extracted, segments: {len(transcript)}")
                
                # Auto-detect language if requested from transcript
                if language == 'auto':
                    # Extract text from timestamped transcript for language detection
                    if isinstance(transcript, list) and len(transcript) > 0:
                        transcript_text = ' '.join([seg.get('text', '') for seg in transcript[:10]])  # Sample first 10 segments
                    else:
                        transcript_text = str(transcript)
                    
                    detected_language = processor.detect_language(transcript_text)
                    language = detected_language
                    print(f"🌐 Auto-detected language for shorts: {'Arabic' if language == 'ar' else 'English'}")
                
                # Check for cancellation before video processing
                if progress.check_stop_at_breakpoint():
                    progress.cancel()
                    return
                
                # Import VideoProcessor here to avoid circular imports
                from .video_processor import VideoProcessor
                
                # Process video and generate clips
                with VideoProcessor() as video_processor:
                    if progress.check_stop_at_breakpoint():
                        progress.cancel()
                        return
                    
                    print(f"🔍 DEBUG: Starting video processing for shorts with language: {language}")
                    result = video_processor.process_video_for_shorts(url, transcript, language, progress)
                    
                    if not result.get('success'):
                        progress.error(f"Failed to generate shorts: {result.get('error', 'Unknown error')}")
                        return
                    
                    print(f"🔍 DEBUG: Shorts generated successfully, clips: {result.get('total_clips', 0)}")
                
                # Check memory store after VideoProcessor context ends
                from .video_processor import video_clips_memory_store
                clips_with_thumbnails = [clip_id for clip_id, data in video_clips_memory_store.items() 
                                       if 'thumbnail' in data and data['thumbnail']]
                print(f"🔍 [POST-PROCESSING DEBUG] After VideoProcessor context - Clips with thumbnails: {clips_with_thumbnails}")
                for clip_id in clips_with_thumbnails:
                    thumbnail_size = len(video_clips_memory_store[clip_id]['thumbnail'])
                    print(f"✅ [POST-PROCESSING DEBUG] Clip {clip_id} has thumbnail: {thumbnail_size} bytes")
                
                if not clips_with_thumbnails:
                    print(f"❌ [POST-PROCESSING DEBUG] WARNING: No clips with thumbnails found after processing!")
                    print(f"🔍 [POST-PROCESSING DEBUG] Available clips: {list(video_clips_memory_store.keys())}")
                    for clip_id, data in video_clips_memory_store.items():
                        print(f"🔍 [POST-PROCESSING DEBUG] Clip {clip_id} keys: {list(data.keys())}")
                
                # Complete with final result
                progress.complete({
                    'success': True,
                    'video_info': result['video_info'],
                    'clips': result['clips'],
                    'total_clips': result['total_clips'],
                    'video_id': video_id,
                    'transcript_length': len(transcript),
                    'processing_engine': 'MoviePy + yt-dlp',
                    'ai_engine': processor.get_current_model_name()
                })
                    
            except Exception as e:
                print(f"🔍 DEBUG: Error in process_shorts_in_background: {str(e)}")
                progress.error(f'Shorts generation failed: {str(e)}')
            finally:
                # Ensure task is always marked as completed
                if not progress.progress.get('completed', False):
                    print(f"🧹 SAFETY CLEANUP: Marking task as completed in finally block")
                    progress.error('Task completed with unknown status')
        
        # Start background processing
        Thread(target=process_shorts_in_background, daemon=True).start()
        
        return jsonify({'task_id': task_id, 'stream_url': f'/progress/{task_id}'})
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/download-clip/<task_id>/<int:clip_number>')
@limiter.limit("10 per minute")  # Rate limit clip downloads
def download_clip(task_id, clip_number):
    """Download a specific clip file"""
    try:
        # Here you would implement clip download logic
        # For now, return info about the clip
        return jsonify({
            'success': False,
            'error': 'Clip download not implemented yet. Please use the file paths provided in the results.'
        })
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

# Debug and cleanup endpoints
@app.route('/api/debug/tasks')
@limiter.exempt  # No rate limit on debug endpoint
def debug_tasks():
    """Debug endpoint to see active tasks with concurrent processing info"""
    try:
        from .progress import progress_store, cleanup_stale_tasks, get_processing_status
        import time
        
        # Clean up stale tasks first
        cleaned_count = cleanup_stale_tasks()
        
        # Get processing status
        status = get_processing_status()
        
        active_tasks = []
        for task_id, progress in progress_store.items():
            active_tasks.append({
                'task_id': task_id,
                'status': progress.get('status'),
                'completed': progress.get('completed', False),
                'start_time': progress.get('start_time'),
                'age_minutes': (time.time() - progress.get('start_time', time.time())) / 60,
                'message': progress.get('message', ''),
                'error': progress.get('error'),
                'queue_position': progress.get('queue_position', -1),
                'estimated_wait_minutes': progress.get('estimated_wait_minutes', 0)
            })
        
        return jsonify({
            'cleaned_stale_tasks': cleaned_count,
            'total_tasks_in_store': len(progress_store),
            'active_tasks': active_tasks,
            'concurrent_processing_status': status
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/force-cleanup', methods=['POST'])
@limiter.exempt  # No rate limit on cleanup
def force_cleanup():
    """Force cleanup of all tasks"""
    try:
        from .progress import progress_store, cancelled_tasks
        import time
        
        # Force mark all tasks as completed
        cleaned_count = 0
        for task_id, progress in list(progress_store.items()):
            if not progress.get('completed', False):
                progress.update({
                    'status': 'error',
                    'error': 'Force cleaned by admin',
                    'completed': True
                })
                cleaned_count += 1
        
        # Clear everything after a short delay
        def delayed_cleanup():
            time.sleep(2)
            progress_store.clear()
            cancelled_tasks.clear()
        
        from threading import Thread
        Thread(target=delayed_cleanup, daemon=True).start()
        
        return jsonify({
            'success': True,
            'message': f'Force cleaned {cleaned_count} tasks',
            'remaining_tasks': len(progress_store)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Progress streaming endpoints
@app.route('/progress/<task_id>')
@limiter.exempt  # No rate limit on progress streaming
def stream_progress(task_id):
    """Stream progress updates using Server-Sent Events"""
    return Response(generate_progress_stream(task_id), mimetype='text/event-stream')

@app.route('/api/clips/<task_id>')
@limiter.exempt  # No rate limit on clips polling
def get_clips(task_id):
    """Get current clips for a task (for polling)"""
    try:
        if task_id in progress_store:
            progress = progress_store[task_id]
            partial_result = progress.get('partial_result')
            if partial_result and isinstance(partial_result, dict):
                return jsonify({
                    'success': True,
                    'clips': partial_result.get('clips', []),
                    'total_ready': partial_result.get('total_ready', 0),
                    'total_clips': partial_result.get('total_clips', 0)
                })
        return jsonify({'success': False, 'clips': [], 'total_ready': 0, 'total_clips': 0})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cancel/<task_id>', methods=['POST'])
@limiter.limit("10 per minute")  # Rate limit cancellations
def cancel_task(task_id):
    """Cancel a queued or processing task"""
    try:
        from .progress import progress_store, remove_from_queue, cancel_task_by_id
        
        if task_id not in progress_store:
            return jsonify({'error': 'Task not found'}), 404
        
        task_progress = progress_store[task_id]
        
        if task_progress.get('completed', False):
            return jsonify({'error': 'Task already completed'}), 400
        
        # Cancel the task using the existing cancel function
        cancel_task_by_id(task_id)
        
        # Also remove from queue
        remove_from_queue(task_id)
        
        print(f"🚫 CANCELLED: User cancelled task {task_id}")
        
        return jsonify({
            'success': True,
            'message': 'Task cancelled successfully',
            'task_id': task_id
        })
        
    except Exception as e:
        print(f"❌ ERROR: Failed to cancel task {task_id}: {str(e)}")
        return jsonify({'error': f'Failed to cancel task: {str(e)}'}), 500

@app.route('/api/queue-status', methods=['GET'])
@limiter.limit("30 per minute")  # Rate limit queue status checks
def get_queue_status():
    """Get current queue status with concurrent processing info"""
    try:
        from .progress import get_processing_status, processing_queue, active_processing_tasks
        status = get_processing_status()
        
        return jsonify({
            'concurrent_processing_enabled': status['concurrent_processing_enabled'],
            'max_concurrent_tasks': status['max_concurrent_tasks'],
            'max_queue_size': status['max_queue_size'],
            'active_tasks_count': status['active_tasks_count'],
            'queued_tasks_count': status['queued_tasks_count'],
            'estimated_wait_per_task_minutes': 2 if status['concurrent_processing_enabled'] else 3,
            'system_load': 'normal' if status['active_tasks_count'] < status['max_concurrent_tasks'] else 'high'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get queue status: {str(e)}'}), 500

@app.route('/api/configure-concurrent-processing', methods=['POST'])
@limiter.limit("5 per minute")  # Rate limit configuration changes
def configure_concurrent_processing():
    """Configure concurrent processing settings"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Configuration data required'}), 400
        
        from .progress import set_max_concurrent_tasks, enable_concurrent_processing, get_processing_status
        
        # Update max concurrent tasks if provided
        if 'max_concurrent_tasks' in data:
            max_tasks = int(data['max_concurrent_tasks'])
            if max_tasks < 1 or max_tasks > 50:
                return jsonify({'error': 'max_concurrent_tasks must be between 1 and 50'}), 400
            set_max_concurrent_tasks(max_tasks)
        
        # Enable/disable concurrent processing if provided
        if 'enable_concurrent_processing' in data:
            enabled = bool(data['enable_concurrent_processing'])
            enable_concurrent_processing(enabled)
        
        # Return updated status
        status = get_processing_status()
        return jsonify({
            'success': True,
            'message': 'Configuration updated successfully',
            'current_config': status
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to update configuration: {str(e)}'}), 500

# Static file routes
@app.route('/robots.txt')
@limiter.exempt  # No rate limit on robots.txt
def robots_txt():
    return send_from_directory('../static', 'robots.txt', mimetype='text/plain')

@app.route('/favicon.ico')
@limiter.exempt  # No rate limit on favicon
def favicon():
    return send_from_directory('../static', 'favicon.ico')

@app.route('/apple-touch-icon.png')
@limiter.exempt  # No rate limit on apple touch icon
def apple_touch_icon():
    return send_from_directory('../static', 'apple-touch-icon.png')

@app.route('/favicon-32x32.png')
@limiter.exempt  # No rate limit on favicon
def favicon_32():
    return send_from_directory('../static', 'favicon-32x32.png')

@app.route('/favicon-16x16.png')
@limiter.exempt  # No rate limit on favicon
def favicon_16():
    return send_from_directory('../static', 'favicon-16x16.png')

@app.route('/site.webmanifest')
@limiter.exempt  # No rate limit on manifest
def site_webmanifest():
    return send_from_directory('../static', 'site.webmanifest', mimetype='application/json')

@app.route('/static/<path:filename>')
@limiter.exempt  # No rate limit on static files
def static_files(filename):
    return send_from_directory('../static', filename)

# Video clip streaming and download endpoints
@app.route('/api/stream-clip/<clip_id>')
@limiter.limit("10 per minute")  # Rate limit video streaming
def stream_video_clip(clip_id):
    """Stream video clip directly from memory"""
    try:
        from .video_processor import video_clips_memory_store
        
        if clip_id not in video_clips_memory_store:
            return jsonify({'error': 'Video clip not found'}), 404
        
        clip_data = video_clips_memory_store[clip_id]
        
        def generate():
            yield clip_data['data']
        
        return Response(
            generate(),
            mimetype=clip_data['content_type'],
            headers={
                'Content-Disposition': f'inline; filename="{clip_id}.mp4"',
                'Content-Length': str(clip_data['size']),
                'Accept-Ranges': 'bytes',
                'Cache-Control': 'public, max-age=3600'
            }
        )
        
    except Exception as e:
        return jsonify({'error': f'Failed to stream video: {str(e)}'}), 500

@app.route('/api/download-clip/<clip_id>')
@limiter.limit("5 per minute")  # Rate limit downloads
def download_video_clip(clip_id):
    """Download video clip from memory"""
    try:
        from .video_processor import video_clips_memory_store
        
        if clip_id not in video_clips_memory_store:
            return jsonify({'error': 'Video clip not found'}), 404
        
        clip_data = video_clips_memory_store[clip_id]
        
        def generate():
            yield clip_data['data']
        
        return Response(
            generate(),
            mimetype=clip_data['content_type'],
            headers={
                'Content-Disposition': f'attachment; filename="{clip_id}.mp4"',
                'Content-Length': str(clip_data['size'])
            }
        )
        
    except Exception as e:
        return jsonify({'error': f'Failed to download video: {str(e)}'}), 500

@app.route('/api/clip-info/<clip_id>')
@limiter.limit("20 per minute")  # Rate limit info requests
def get_clip_info(clip_id):
    """Get information about a video clip"""
    try:
        from .video_processor import video_clips_memory_store
        
        if clip_id not in video_clips_memory_store:
            return jsonify({'error': 'Video clip not found'}), 404
        
        clip_data = video_clips_memory_store[clip_id]
        
        return jsonify({
            'clip_id': clip_id,
            'filename': clip_data['filename'],
            'size': clip_data['size'],
            'content_type': clip_data['content_type'],
            'created_at': clip_data.get('created_at', 0),
            'download_url': f'/api/download-clip/{clip_id}',
            'stream_url': f'/api/stream-clip/{clip_id}'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get clip info: {str(e)}'}), 500

@app.route('/api/thumbnail/<clip_id>')
@limiter.limit("30 per minute")  # Rate limit thumbnail requests
def get_video_thumbnail(clip_id):
    """Generate and serve a thumbnail for a video clip"""
    try:
        from .video_processor import video_clips_memory_store
        import subprocess
        import tempfile
        import os
        
        print(f"🔍 [THUMBNAIL DEBUG] Thumbnail request received for clip_id: {clip_id}")
        print(f"🔍 [THUMBNAIL DEBUG] Available clips in memory store: {list(video_clips_memory_store.keys())}")
        
        if clip_id not in video_clips_memory_store:
            print(f"❌ [THUMBNAIL DEBUG] Clip {clip_id} not found in memory store")
            if video_clips_memory_store:
                print(f"🔍 [THUMBNAIL DEBUG] Available clip IDs: {list(video_clips_memory_store.keys())}")
            else:
                print(f"🔍 [THUMBNAIL DEBUG] Memory store is completely empty!")
            return jsonify({'error': 'Video clip not found'}), 404
        
        clip_data = video_clips_memory_store[clip_id]
        print(f"🔍 [THUMBNAIL DEBUG] Clip data keys: {list(clip_data.keys())}")
        print(f"🔍 [THUMBNAIL DEBUG] Clip data sizes: {[(k, len(v) if isinstance(v, bytes) else type(v)) for k, v in clip_data.items()]}")
        
        # First, check if we already have a pre-generated thumbnail
        if 'thumbnail' in clip_data and clip_data['thumbnail']:
            print(f"✅ [THUMBNAIL DEBUG] Serving pre-generated thumbnail for clip {clip_id} (size: {len(clip_data['thumbnail'])} bytes)")
            from flask import Response
            return Response(
                clip_data['thumbnail'],
                mimetype='image/jpeg',
                headers={
                    'Cache-Control': 'public, max-age=3600',  # Cache for 1 hour
                    'Content-Length': str(len(clip_data['thumbnail']))
                }
            )
        else:
            # Log why thumbnail is missing
            if 'thumbnail' not in clip_data:
                print(f"❌ [THUMBNAIL DEBUG] No 'thumbnail' key found in clip_data for {clip_id}")
            elif clip_data['thumbnail'] is None:
                print(f"❌ [THUMBNAIL DEBUG] Thumbnail key exists but value is None for {clip_id}")
            elif not clip_data['thumbnail']:
                print(f"❌ [THUMBNAIL DEBUG] Thumbnail key exists but value is empty/falsy for {clip_id}")
            
            print(f"⚠️ [THUMBNAIL DEBUG] Thumbnail missing - will attempt on-demand generation for {clip_id}")
        
        print(f"🔄 No pre-generated thumbnail found for clip {clip_id}, generating on-demand...")
        
        # Create temporary files for video and thumbnail
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_video:
            temp_video.write(clip_data['data'])
            temp_video_path = temp_video.name
        
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_thumb:
            temp_thumb_path = temp_thumb.name
        
        try:
            # Use FFmpeg to generate thumbnail from middle of video
            # Try multiple time positions to get a good frame
            positions = ['00:00:01', '00:00:02', '00:00:03', '00:00:00.5']
            
            for pos in positions:
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-i', temp_video_path,
                    '-ss', pos,  # Time position
                    '-vframes', '1',    # Extract single frame
                    '-vf', 'scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2',  # Resize with padding
                    '-q:v', '2',        # High quality
                    '-y',               # Overwrite output file
                    temp_thumb_path
                ]
                
                # Execute FFmpeg
                process = subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    timeout=15  # 15 second timeout
                )
                
                if process.returncode == 0 and os.path.exists(temp_thumb_path) and os.path.getsize(temp_thumb_path) > 0:
                    # Success! Read the generated thumbnail
                    with open(temp_thumb_path, 'rb') as f:
                        thumbnail_data = f.read()
                    
                    # Return the thumbnail as image
                    from flask import Response
                    return Response(
                        thumbnail_data,
                        mimetype='image/jpeg',
                        headers={
                            'Cache-Control': 'public, max-age=3600',  # Cache for 1 hour
                            'Content-Length': str(len(thumbnail_data))
                        }
                    )
                else:
                    # This position failed, try next one
                    if os.path.exists(temp_thumb_path):
                        os.unlink(temp_thumb_path)
                    continue
            
            # All positions failed
            return jsonify({'error': 'Failed to generate thumbnail from video'}), 500
                
        finally:
            # Clean up temporary files
            try:
                os.unlink(temp_video_path)
                if os.path.exists(temp_thumb_path):
                    os.unlink(temp_thumb_path)
            except:
                pass
        
    except Exception as e:
        return jsonify({'error': f'Failed to generate thumbnail: {str(e)}'}), 500

# ============================================
# Chat Agent API Routes - URL Q&A with Webscout
# ============================================

# Import chat agent module (lazy import to avoid startup issues)
# Global ChatAgent singleton
_global_chat_agent = None

def get_chat_agent():
    """Lazy import and initialize chat agent"""
    global _global_chat_agent
    try:
        from .chat_agent import ChatAgent
        if _global_chat_agent is None:
            print(f"DEBUG: Creating new global ChatAgent singleton")
            _global_chat_agent = ChatAgent()
        else:
            print(f"DEBUG: Reusing existing global ChatAgent: {getattr(_global_chat_agent, 'instance_id', 'unknown')}")
        return _global_chat_agent
    except ImportError as e:
        print(f"⚠️ Chat Agent not available: {e}")
        return None

@app.route('/api/chat-agent/analyze', methods=['GET'])
@limiter.limit("10 per minute")
def chat_agent_analyze():
    """Analyze a webpage URL for chat interaction"""
    try:
        chat_agent = get_chat_agent()
        if not chat_agent:
            return jsonify({'error': 'Chat Agent not available'}), 503
        
        url = request.args.get('url')
        session_id = request.args.get('session_id')
        analysis_mode = request.args.get('analysis_mode', 'fast')  # Default to fast analysis
        
        if not url or not session_id:
            return jsonify({'error': 'URL and session_id are required'}), 400
        
        def progress_callback(sid, status, percentage, message, details):
            """Send progress updates via Server-Sent Events"""
            data = {
                'type': 'progress',
                'status': status,
                'percentage': percentage,
                'message': message,
                'details': details
            }
            return f"data: {json.dumps(data)}\n\n"
        
        def generate():
            """Generate Server-Sent Events for analysis progress"""
            yield "data: {\"type\": \"start\"}\n\n"
            
            # Set up progress callback
            progress_messages = []
            
            def collect_progress(sid, status, percentage, message, details):
                progress_messages.append({
                    'type': 'progress',
                    'status': status,
                    'percentage': percentage,
                    'message': message,
                    'details': details
                })
                yield f"data: {json.dumps(progress_messages[-1])}\n\n"
            
            # Analyze the webpage
            try:
                result = chat_agent.fetch_webpage_content(url, session_id, analysis_mode, collect_progress)
                
                if result['success']:
                    # Send analysis completion
                    yield f"data: {json.dumps({'type': 'analysis_complete', 'data': result})}\n\n"
                    
                    # Now automatically generate a summary
                    yield f"data: {json.dumps({'type': 'summary_start', 'message': 'Generating automatic summary...'})}\n\n"
                    
                    try:
                        # Generate automatic summary question with explicit markdown formatting request
                        summary_question = """Please provide a comprehensive summary of this webpage, including the main topics, key points, and important information. 

Use proper markdown formatting:
- Use # for main headers
- Use ## for subheaders  
- Use - for bullet points
- Use **bold** for important terms
- Use proper line breaks between sections

Structure your response with clear headers and organized bullet points."""
                        
                        # Clear any previous cancel flags
                        chat_agent.clear_cancel_flag(session_id)
                        
                        # Stream the summary response
                        for update in chat_agent.ask_question_word_stream(session_id, summary_question, analysis_mode):
                            # Modify the update type to indicate it's an automatic summary
                            if update.get('type') == 'thinking':
                                update['type'] = 'summary_thinking'
                            elif update.get('type') == 'streaming':
                                update['type'] = 'summary_streaming' 
                            elif update.get('type') == 'complete':
                                update['type'] = 'summary_complete'
                            elif update.get('type') == 'error':
                                update['type'] = 'summary_error'
                            
                            yield f"data: {json.dumps(update, ensure_ascii=False)}\n\n"
                            
                    except Exception as e:
                        yield f"data: {json.dumps({'type': 'summary_error', 'message': f'Failed to generate summary: {str(e)}'})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'error', 'message': result['error']})}\n\n"
            
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        return Response(generate(), mimetype='text/event-stream')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat-agent/ask', methods=['GET'])
@limiter.limit("20 per minute")
def chat_agent_ask():
    """Ask a question about the analyzed webpage"""
    try:
        chat_agent = get_chat_agent()
        if not chat_agent:
            return jsonify({'error': 'Chat Agent not available'}), 503
        
        question = request.args.get('question')
        session_id = request.args.get('session_id')
        analysis_mode = request.args.get('analysis_mode', 'fast')  # Default to fast mode
        
        if not question or not session_id:
            return jsonify({'error': 'Question and session_id are required'}), 400
        
        # Validate question length (2000 character limit)
        if len(question) > 2000:
            return jsonify({'error': f'Question too long. Maximum 2000 characters allowed. Current length: {len(question)}'}), 400
        
        def generate():
            """Generate Server-Sent Events for streaming response"""
            try:
                yield "data: {\"type\": \"start\"}\n\n"
                
                # Clear any previous cancel flags
                chat_agent.clear_cancel_flag(session_id)
                
                # Use the new word-streaming generator with analysis mode
                for update in chat_agent.ask_question_word_stream(session_id, question, analysis_mode):
                    yield f"data: {json.dumps(update, ensure_ascii=False)}\n\n"
            
            except Exception as e:
                print(f"Chat agent error: {e}")  # Log the error
                yield f"data: {json.dumps({'type': 'error', 'message': f'Backend error: {str(e)}'}, ensure_ascii=False)}\n\n"
        
        return Response(generate(), mimetype='text/event-stream', headers={'Content-Type': 'text/event-stream; charset=utf-8'})
    
    except Exception as e:
        print(f"Chat agent endpoint error: {e}")  # Log the error
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat-agent/cancel', methods=['POST'])
@limiter.limit("30 per minute")  # Allow more cancel requests
def chat_agent_cancel():
    """Cancel ongoing chat agent operation"""
    try:
        chat_agent = get_chat_agent()
        if not chat_agent:
            return jsonify({'error': 'Chat Agent not available'}), 503
        
        session_id = request.args.get('session_id')
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400
        
        result = chat_agent.cancel_operation(session_id)
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat-agent/clear', methods=['POST'])
@limiter.limit("20 per minute")  # Reasonable limit for clearing sessions
def chat_agent_clear():
    """Clear chat agent session"""
    try:
        chat_agent = get_chat_agent()
        if not chat_agent:
            return jsonify({'error': 'Chat Agent not available'}), 503
        
        session_id = request.args.get('session_id')
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400
        
        result = chat_agent.clear_session(session_id)
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat-agent/session', methods=['GET'])
@limiter.limit("60 per minute")  # Allow frequent session info checks
def chat_agent_session_info():
    """Get chat agent session information"""
    try:
        chat_agent = get_chat_agent()
        if not chat_agent:
            return jsonify({'error': 'Chat Agent not available'}), 503
        
        session_id = request.args.get('session_id')
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400
        
        info = chat_agent.get_session_info(session_id)
        if info:
            return jsonify({'success': True, 'data': info})
        else:
            return jsonify({'success': False, 'error': 'Session not found'}), 404
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat-agent/validate-session', methods=['GET'])
@limiter.limit("60 per minute")  # Allow frequent session validation checks
def chat_agent_validate_session():
    """Validate if a chat agent session is still active"""
    try:
        chat_agent = get_chat_agent()
        if not chat_agent:
            return jsonify({'error': 'Chat Agent not available'}), 503
        
        session_id = request.args.get('session_id')
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400
        
        # Check if session exists and has valid data
        info = chat_agent.get_session_info(session_id)
        if info and info.get('url'):
            return jsonify({'valid': True, 'session_id': session_id}), 200
        else:
            return jsonify({'valid': False, 'session_id': session_id}), 404
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# Video Chat API Routes - YouTube Video Analysis with Q&A
# ============================================

# Global storage for video chat sessions
video_chat_sessions = {}

@app.route('/api/video-chat/process', methods=['POST'])
@limiter.limit("10 per minute")
def video_chat_process():
    """Process YouTube video URL and start chat session - supports both initial analysis and Q&A"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        message = data.get('message', '').strip()
        session_id = data.get('session_id')
        
        if not message or not session_id:
            return jsonify({'error': 'Message and session_id are required'}), 400
        
        # Check if message is a YouTube URL
        is_youtube_url = any(pattern in message.lower() for pattern in ['youtube.com', 'youtu.be'])
        
        if is_youtube_url:
            # Process YouTube video URL
            return process_youtube_video_for_chat(message, session_id)
        else:
            # Handle Q&A about existing video
            return handle_video_qa(message, session_id)
            
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def process_youtube_video_for_chat(url, session_id):
    """Process YouTube video and return initial summary"""
    try:
        # Initialize processor
        processor = YouTubeProcessor()
        
        # Extract video ID
        video_id = processor.extract_video_id(url)
        if not video_id:
            return jsonify({
                'type': 'error',
                'message': '❌ Invalid YouTube URL. Please check the URL and try again.'
            })
        
        # Get video info
        try:
            video_info = processor.get_video_info(video_id)
        except Exception as e:
            return jsonify({
                'type': 'error', 
                'message': f'❌ Could not fetch video information: {str(e)}'
            })
        
        # Get transcript
        try:
            transcript = processor.get_transcript(video_id)
            if not transcript or len(transcript.strip()) < 50:
                return jsonify({
                    'type': 'error',
                    'message': '❌ No transcript available for this video. The video may not have captions or transcripts enabled.'
                })
        except Exception as e:
            return jsonify({
                'type': 'error',
                'message': f'❌ Could not extract transcript: {str(e)}'
            })
        
        # Auto-detect language
        detected_language = processor.detect_language(transcript)
        
        # Generate summary
        try:
            summary = processor.summarize_with_g4f_language(transcript, detected_language)
            if not summary or summary.startswith('Error') or summary == 'Task cancelled by user':
                return jsonify({
                    'type': 'error',
                    'message': '❌ Failed to generate video summary. Please try again later.'
                })
        except Exception as e:
            return jsonify({
                'type': 'error',
                'message': f'❌ Failed to generate summary: {str(e)}'
            })
        
        # Store video session data
        video_chat_sessions[session_id] = {
            'video_id': video_id,
            'video_info': video_info,
            'transcript': transcript,
            'summary': summary,
            'language': detected_language,
            'chat_history': []
        }
        
        # Create video info display
        video_display = f"""
**🎥 {video_info['title']}**
📺 *{video_info['author']}*

## 📝 Video Summary

{summary}

---
*You can now ask questions about this video! Try asking about specific topics, key points, or request explanations of concepts mentioned in the video.*
"""
        
        return jsonify({
            'type': 'video_summary',
            'video_info': video_info,
            'summary': summary,
            'content': video_display,
            'language': detected_language,
            'session_id': session_id
        })
        
    except Exception as e:
        return jsonify({
            'type': 'error',
            'message': f'❌ Failed to process video: {str(e)}'
        })

def handle_video_qa(question, session_id):
    """Handle Q&A about previously processed video"""
    try:
        # Check if session exists
        if session_id not in video_chat_sessions:
            return jsonify({
                'type': 'error',
                'message': '❌ No video has been analyzed yet. Please share a YouTube URL first to start the conversation.'
            })
        
        session_data = video_chat_sessions[session_id]
        transcript = session_data['transcript']
        video_info = session_data['video_info']
        language = session_data.get('language', 'en')
        
        # Create Q&A prompt
        language_instruction = ""
        if language == 'ar':
            language_instruction = "\nIMPORTANT: The user is asking in Arabic context, so please respond in Arabic language."
        
        prompt = f"""You are analyzing a YouTube video and answering questions about its content. Here's the video information and transcript:

VIDEO TITLE: {video_info['title']}
CHANNEL: {video_info['author']}

FULL VIDEO TRANSCRIPT:
{transcript}

USER QUESTION: {question}

Please answer the user's question based on the video content above. Be specific and reference relevant parts of the video when possible.{language_instruction}

FORMATTING GUIDELINES:
- Use **bold** for important terms
- Use numbered lists for step-by-step information  
- Use bullet points for features or key points
- Quote relevant parts from the video when appropriate
- Be clear and helpful

ANSWER:"""

        # Use G4F to generate answer
        try:
            processor = YouTubeProcessor()
            answer = processor.make_ai_request_with_fallback(prompt, None, language)
            
            if hasattr(answer, 'choices') and answer.choices:
                response_text = answer.choices[0].message.content
            else:
                response_text = str(answer)
            
            # Clean the response
            response_text = response_text.replace("ANSWER:", "").strip()
            
            # Add to chat history
            session_data['chat_history'].append({
                'question': question,
                'answer': response_text,
                'timestamp': time.time()
            })
            
            return jsonify({
                'type': 'qa_response',
                'question': question,
                'answer': response_text,
                'video_title': video_info['title']
            })
            
        except Exception as e:
            return jsonify({
                'type': 'error',
                'message': f'❌ Failed to generate answer: {str(e)}'
            })
            
    except Exception as e:
        return jsonify({
            'type': 'error',
            'message': f'❌ Failed to process question: {str(e)}'
        })

@app.route('/api/video-chat/stream', methods=['GET'])
@limiter.limit("10 per minute")
def video_chat_stream():
    """Stream processing for video chat with real-time updates"""
    try:
        message = request.args.get('message', '').strip()
        session_id = request.args.get('session_id')
        
        if not message or not session_id:
            return jsonify({'error': 'Message and session_id are required'}), 400
        
        # Validate message length (2000 character limit)
        if len(message) > 2000:
            return jsonify({'error': f'Message too long. Maximum 2000 characters allowed. Current length: {len(message)}'}), 400
        
        # Validate message length (2000 character limit)
        if len(message) > 2000:
            return jsonify({'error': f'Message too long. Maximum 2000 characters allowed. Current length: {len(message)}'}), 400
        
        def generate_stream():
            try:
                # Check if message is a YouTube URL
                is_youtube_url = any(pattern in message.lower() for pattern in ['youtube.com', 'youtu.be'])
                
                if is_youtube_url:
                    # Process YouTube video with streaming updates
                    yield f"data: {json.dumps({'type': 'progress', 'message': '🔍 Analyzing video...', 'progress': 10})}\n\n"
                    
                    # Initialize processor
                    processor = YouTubeProcessor()
                    
                    # Extract video ID
                    video_id = processor.extract_video_id(message)
                    if not video_id:
                        yield f"data: {json.dumps({'type': 'error', 'message': '❌ Invalid YouTube URL'})}\n\n"
                        return
                    
                    yield f"data: {json.dumps({'type': 'progress', 'message': '📹 Getting video information...', 'progress': 30})}\n\n"
                    
                    # Get video info and transcript
                    try:
                        video_info = processor.get_video_info(video_id)
                        yield f"data: {json.dumps({'type': 'progress', 'message': '📝 Extracting transcript...', 'progress': 50})}\n\n"
                        
                        transcript = processor.get_transcript(video_id)
                        if not transcript or len(transcript.strip()) < 50:
                            yield f"data: {json.dumps({'type': 'error', 'message': '❌ No transcript available'})}\n\n"
                            return
                        
                        yield f"data: {json.dumps({'type': 'progress', 'message': '🤖 Generating summary...', 'progress': 70})}\n\n"
                        
                        # Auto-detect language
                        detected_language = processor.detect_language(transcript)
                        
                        # Generate summary with word-by-word streaming
                        language_instruction = ""
                        if detected_language == 'ar':
                            language_instruction = "\nIMPORTANT: Please respond in Arabic language."
                        
                        prompt = f"""You are a helpful assistant analyzing a YouTube video. Based on the video content below, provide insights about the main topics and key points.{language_instruction}

VIDEO TITLE: {video_info['title']}
CHANNEL: {video_info['author']}

FULL VIDEO TRANSCRIPT:
{transcript}

Share the key insights from this video including main topics, important conclusions, and actionable takeaways. Use **bold** for important terms and organize with bullet points where appropriate. Start directly with the content without any introductory headers."""

                        try:
                            # Use G4F for streaming response
                            response = processor.make_ai_request_with_fallback(prompt, None, detected_language, stream=True)
                            
                            accumulated_text = ""
                            last_content_length = 0
                            no_new_content_count = 0
                            
                            for chunk in response:
                                if hasattr(chunk, 'choices') and chunk.choices:
                                    delta_content = getattr(chunk.choices[0].delta, 'content', None)
                                    if delta_content:
                                        accumulated_text += delta_content
                                        
                                        # Send the accumulated text as-is to preserve formatting
                                        yield f"data: {json.dumps({'type': 'streaming', 'text': accumulated_text, 'progress': min(80 + len(accumulated_text.split()) // 10, 95)})}\n\n"
                                        
                                        # Small delay for natural typing effect
                                        time.sleep(0.05)
                                        
                                        # Update tracking variables
                                        current_length = len(accumulated_text)
                                        if current_length == last_content_length:
                                            no_new_content_count += 1
                                        else:
                                            no_new_content_count = 0
                                        last_content_length = current_length
                                        
                                        # Stop only if no new content for several iterations
                                        if no_new_content_count > 15:
                                            break                            # Use the accumulated text as the final summary
                            summary = accumulated_text.strip()
                            
                            # Store session data
                            video_chat_sessions[session_id] = {
                                'video_id': video_id,
                                'video_info': video_info,
                                'transcript': transcript,
                                'summary': summary,
                                'language': detected_language,
                                'chat_history': []
                            }
                            
                            # Create final video display content without headers
                            video_display = summary
                            
                            # Send final result
                            yield f"data: {json.dumps({'type': 'complete', 'content': video_display, 'video_info': video_info})}\n\n"
                            
                        except Exception as e:
                            # Fallback to non-streaming if streaming fails
                            summary = processor.summarize_with_g4f_language(transcript, detected_language)
                            
                            if summary and not summary.startswith('Error'):
                                # Simulate word-by-word for non-streaming
                                words = summary.split()
                                for i, word in enumerate(words):
                                    current_text = " ".join(words[:i+1])
                                    yield f"data: {json.dumps({'type': 'streaming', 'text': current_text, 'progress': min(80 + (i * 2), 95)})}\n\n"
                                    time.sleep(0.05)  # Faster for simulated streaming
                                
                                # Store and complete without headers
                                video_chat_sessions[session_id] = {
                                    'video_id': video_id,
                                    'video_info': video_info,
                                    'transcript': transcript,
                                    'summary': summary,
                                    'language': detected_language,
                                    'chat_history': []
                                }
                                
                                video_display = summary
                                yield f"data: {json.dumps({'type': 'complete', 'content': video_display, 'video_info': video_info})}\n\n"
                            else:
                                yield f"data: {json.dumps({'type': 'error', 'message': '❌ Failed to generate summary'})}\n\n"
                        
                    except Exception as e:
                        yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Error: {str(e)}'})}\n\n"
                else:
                    # Handle Q&A with word-by-word streaming
                    yield f"data: {json.dumps({'type': 'progress', 'message': '🤔 Thinking about your question...', 'progress': 30})}\n\n"
                    
                    # Check if session exists
                    if session_id not in video_chat_sessions:
                        yield f"data: {json.dumps({'type': 'error', 'message': '❌ No video has been analyzed yet. Please share a YouTube URL first.'})}\n\n"
                        return
                    
                    session_data = video_chat_sessions[session_id]
                    transcript = session_data['transcript']
                    video_info = session_data['video_info']
                    language = session_data.get('language', 'en')
                    
                    # Create Q&A prompt
                    language_instruction = ""
                    if language == 'ar':
                        language_instruction = "\nIMPORTANT: Please respond in Arabic language."
                    
                    prompt = f"""You are analyzing a YouTube video and answering questions about its content.{language_instruction}

VIDEO TITLE: {video_info['title']}
CHANNEL: {video_info['author']}

FULL VIDEO TRANSCRIPT:
{transcript}

USER QUESTION: {message}

Please answer the user's question based on the video content above. Be specific and reference relevant parts of the video when possible.

Use **bold** for important terms, numbered lists for steps, and bullet points for key information.

ANSWER:"""

                    try:
                        # Use G4F to generate answer with streaming
                        processor = YouTubeProcessor()
                        response = processor.make_ai_request_with_fallback(prompt, None, language, stream=True)
                        
                        accumulated_text = ""
                        
                        for chunk in response:
                            if hasattr(chunk, 'choices') and chunk.choices:
                                delta_content = getattr(chunk.choices[0].delta, 'content', None)
                                if delta_content:
                                    accumulated_text += delta_content
                                    
                                    # Send the accumulated text as-is to preserve formatting
                                    yield f"data: {json.dumps({'type': 'streaming', 'text': accumulated_text, 'progress': min(70 + len(accumulated_text.split()), 95)})}\n\n"
                                    
                                    # Small delay for natural typing effect
                                    time.sleep(0.05)
                        
                        # Use the accumulated text as the final answer
                        answer = accumulated_text.replace("ANSWER:", "").strip()
                        
                        # Add to chat history
                        session_data['chat_history'].append({
                            'question': message,
                            'answer': answer,
                            'timestamp': time.time()
                        })
                        
                        yield f"data: {json.dumps({'type': 'qa_response', 'question': message, 'answer': answer})}\n\n"
                        
                    except Exception as e:
                        yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Failed to generate answer: {str(e)}'})}\n\n"
                        
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Server error: {str(e)}'})}\n\n"
        
        return Response(generate_stream(), mimetype='text/event-stream',
                       headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'})
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/video-chat/clear', methods=['POST'])
@limiter.limit("30 per minute")
def video_chat_clear():
    """Clear video chat session"""
    try:
        data = request.get_json()
        session_id = data.get('session_id') if data else None
        
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400
        
        # Clear session data
        if session_id in video_chat_sessions:
            del video_chat_sessions[session_id]
        
        return jsonify({'success': True, 'message': 'Chat cleared successfully'})
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='YouTube Transcript & Summary Server')
    parser.add_argument('--mode', choices=['full', 'api'], default='full',
                       help='Run mode: full (UI + API) or api (API only)')
    parser.add_argument('--port', type=int, default=5001,
                       help='Port to run the server on (default: 5001)')
    parser.add_argument('--host', default='0.0.0.0',
                       help='Host to bind the server to (default: 0.0.0)')
    args = parser.parse_args()
    
    # Set host and port from arguments
    host = args.host
    port = args.port
    
    # Run the app
    if args.mode == 'full':
        # Full mode: run with UI (disable reloader to prevent Crawl4AI conflicts)
        app.run(host=host, port=port, debug=True, use_reloader=False)
    else:
        # API mode: run as API server only
        app.run(host=host, port=port, debug=True, use_reloader=False)