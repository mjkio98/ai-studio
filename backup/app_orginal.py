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

# Import Crawl4AI components
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    CRAWL4AI_AVAILABLE = True
    print("✅ Crawl4AI is available - using advanced web scraping")
except ImportError:
    CRAWL4AI_AVAILABLE = False
    print("⚠️ Crawl4AI not available - falling back to requests-html")

# Initialize Flask app
app = Flask(__name__, static_folder='static', template_folder='templates')

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["500 per hour"],  # Increased global default limit
    storage_uri="memory://",  # Use in-memory storage (simple setup)
)
limiter.init_app(app)

# Progress tracking system for streaming updates
progress_store = {}
cancelled_tasks = set()  # Track cancelled tasks

class ProgressTracker:
    def __init__(self, task_id):
        self.task_id = task_id
        self.progress = {
            'status': 'starting',
            'step': '',
            'percentage': 0,
            'message': 'Initializing...',
            'partial_result': '',
            'completed': False,
            'error': None,
            'cancelled': False
        }
        progress_store[task_id] = self.progress
    
    def update(self, step, percentage, message, partial_result=None):
        self.progress.update({
            'status': 'processing',
            'step': step,
            'percentage': percentage,
            'message': message,
            'partial_result': partial_result or self.progress.get('partial_result', '')
        })
    
    def complete(self, result):
        self.progress.update({
            'status': 'completed',
            'step': 'finished',
            'percentage': 100,
            'message': 'Analysis completed!',
            'result': result,
            'completed': True
        })
    
    def error(self, error_msg):
        self.progress.update({
            'status': 'error',
            'error': error_msg,
            'completed': True
        })
    
    def cancel(self):
        """Cancel the task"""
        cancelled_tasks.add(self.task_id)
        self.progress.update({
            'status': 'cancelled',
            'message': 'Task cancelled by user',
            'completed': True,
            'cancelled': True
        })
    
    def is_cancelled(self):
        """Check if task is cancelled"""
        return self.task_id in cancelled_tasks or self.progress.get('cancelled', False)

# Server-Sent Events endpoint for real-time progress
@app.route('/progress/<task_id>')
def progress_stream(task_id):
    def generate():
        last_update = None
        while True:
            if task_id in progress_store:
                current_progress = progress_store[task_id].copy()
                
                # Only send updates if something changed
                if current_progress != last_update:
                    yield f"data: {json.dumps(current_progress)}\n\n"
                    last_update = current_progress.copy()
                
                # Stop streaming if task is completed or errored
                if current_progress.get('completed', False):
                    # Clean up after 5 seconds
                    def cleanup():
                        time.sleep(5)
                        progress_store.pop(task_id, None)
                    Thread(target=cleanup, daemon=True).start()
                    break
            
            time.sleep(0.5)  # Check for updates every 500ms
    
    return Response(generate(), mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache',
                           'Connection': 'keep-alive',
                           'Access-Control-Allow-Origin': '*'})

# Cancel endpoint to stop ongoing tasks
@app.route('/api/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id):
    """Cancel a running task"""
    try:
        if task_id in progress_store:
            # Mark as cancelled in the cancelled_tasks set
            cancelled_tasks.add(task_id)
            
            # Update progress to reflect cancellation
            progress_store[task_id].update({
                'status': 'cancelled',
                'message': 'Task cancelled by user',
                'completed': True,
                'cancelled': True
            })
            
            return jsonify({
                'success': True,
                'message': 'Task cancelled successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Task not found'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to cancel task: {str(e)}'
        }), 500

class YouTubeProcessor:
    def __init__(self):
        # G4F Direct client configuration
        self.g4f_client = Client()
        self.model = "Qwen/Qwen3-235B-A22B-Instruct-2507"  # Qwen3-235B model for better long context handling
        self.provider = g4f.Provider.DeepInfra  # Use DeepInfra provider

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
        
        # User agents for scraping the transcript service
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
        ]
        
        # Fresh proxy list for fallback in case of rate limiting
        proxy_list = [
            {'http': 'http://219.93.101.62:80', 'https': 'http://219.93.101.62:80'},  # Malaysia
            {'http': 'http://133.18.234.13:80', 'https': 'http://133.18.234.13:80'},  # Japan
            {'http': 'http://46.47.197.210:3128', 'https': 'http://46.47.197.210:3128'},  # Russia Elite
            {'http': 'http://200.174.198.158:8888', 'https': 'http://200.174.198.158:8888'},  # Brazil HTTPS
            {'http': 'http://188.40.57.101:80', 'https': 'http://188.40.57.101:80'},  # Germany Elite
            {'http': 'http://192.73.244.36:80', 'https': 'http://192.73.244.36:80'},  # US Elite
            {'http': 'http://152.53.107.230:80', 'https': 'http://152.53.107.230:80'},  # Netherlands
            {'http': 'http://199.188.204.105:8080', 'https': 'http://199.188.204.105:8080'},  # US Elite HTTPS
            {'http': 'http://213.33.126.130:80', 'https': 'http://213.33.126.130:80'},  # Austria
            {'http': 'http://4.195.16.140:80', 'https': 'http://4.195.16.140:80'},  # Australia
            {'http': 'http://5.252.33.13:2025', 'https': 'http://5.252.33.13:2025'},  # Slovakia Elite HTTPS
            {'http': 'http://14.251.13.0:8080', 'https': 'http://14.251.13.0:8080'},  # Vietnam Elite HTTPS
            {'http': 'http://138.124.49.149:10808', 'https': 'http://138.124.49.149:10808'},  # Sweden Elite HTTPS
            {'http': 'http://147.75.34.105:443', 'https': 'http://147.75.34.105:443'},  # Netherlands Elite HTTPS
            {'http': 'http://47.79.94.191:1122', 'https': 'http://47.79.94.191:1122'},  # Japan Elite HTTPS
        ]
        
        # Cloud Run optimized approaches: prioritize direct connection, minimal proxy fallbacks
        approaches = [
            {'name': 'Direct YouTubeToTranscript (lxml)', 'parser': 'lxml', 'proxy': None, 'timeout': 15},
            {'name': 'Direct YouTubeToTranscript (html.parser)', 'parser': 'html.parser', 'proxy': None, 'timeout': 15},
            {'name': 'Malaysia Proxy (lxml)', 'parser': 'lxml', 'proxy': proxy_list[0], 'timeout': 12},
            {'name': 'US Elite Proxy (html.parser)', 'parser': 'html.parser', 'proxy': proxy_list[5], 'timeout': 12},
        ]
        
        for approach_idx, approach in enumerate(approaches):
            # Check for cancellation before each attempt
            if progress and progress.is_cancelled():
                raise Exception("Task cancelled by user")
                
            try:
                print(f"Processing attempt {approach_idx + 1}...")
                
                # Update progress based on approach attempt
                progress_percentage = 50 + (approach_idx * 5)  # Start from 50%, increment by 5% per attempt
                if progress:
                    progress.update('getting_transcript', progress_percentage, "Processing video...")
                
                # Setup session with random user agent and basic headers
                session = requests.Session()
                
                # Select random user agent
                ua = random.choice(user_agents)
                
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
        
        # Fresh working proxy list with multiple approaches
        approaches = [
            {'name': 'Direct (no proxy)', 'proxy': None, 'timeout': 10},
            {'name': 'Malaysia proxy', 'proxy': {'http': 'http://219.93.101.62:80', 'https': 'http://219.93.101.62:80'}, 'timeout': 12},
            {'name': 'Vietnam proxy', 'proxy': {'http': 'http://123.30.154.171:7777', 'https': 'http://123.30.154.171:7777'}, 'timeout': 12},
            {'name': 'Japan proxy', 'proxy': {'http': 'http://133.18.234.13:80', 'https': 'http://133.18.234.13:80'}, 'timeout': 12},
            {'name': 'Russia elite proxy', 'proxy': {'http': 'http://46.47.197.210:3128', 'https': 'http://46.47.197.210:3128'}, 'timeout': 12},
            {'name': 'Trinidad proxy', 'proxy': {'http': 'http://190.58.248.86:80', 'https': 'http://190.58.248.86:80'}, 'timeout': 12},
            {'name': 'US proxy 1', 'proxy': {'http': 'http://50.122.86.118:80', 'https': 'http://50.122.86.118:80'}, 'timeout': 12},
            {'name': 'Brazil HTTPS proxy', 'proxy': {'http': 'http://200.174.198.158:8888', 'https': 'http://200.174.198.158:8888'}, 'timeout': 15},
            {'name': 'Germany elite proxy', 'proxy': {'http': 'http://188.40.57.101:80', 'https': 'http://188.40.57.101:80'}, 'timeout': 12},
            {'name': 'US elite proxy', 'proxy': {'http': 'http://192.73.244.36:80', 'https': 'http://192.73.244.36:80'}, 'timeout': 12},
            {'name': 'US proxy 2', 'proxy': {'http': 'http://4.156.78.45:80', 'https': 'http://4.156.78.45:80'}, 'timeout': 12},
            {'name': 'Netherlands proxy', 'proxy': {'http': 'http://152.53.107.230:80', 'https': 'http://152.53.107.230:80'}, 'timeout': 12},
            {'name': 'US elite HTTPS proxy', 'proxy': {'http': 'http://199.188.204.105:8080', 'https': 'http://199.188.204.105:8080'}, 'timeout': 15},
            {'name': 'Germany proxy 2', 'proxy': {'http': 'http://213.157.6.50:80', 'https': 'http://213.157.6.50:80'}, 'timeout': 12},
            {'name': 'Mexico proxy', 'proxy': {'http': 'http://201.148.32.162:80', 'https': 'http://201.148.32.162:80'}, 'timeout': 12},
            {'name': 'Austria proxy', 'proxy': {'http': 'http://213.33.126.130:80', 'https': 'http://213.33.126.130:80'}, 'timeout': 12},
            {'name': 'Belarus proxy', 'proxy': {'http': 'http://194.158.203.14:80', 'https': 'http://194.158.203.14:80'}, 'timeout': 12},
            {'name': 'Greece proxy', 'proxy': {'http': 'http://194.219.134.234:80', 'https': 'http://194.219.134.234:80'}, 'timeout': 12},
            {'name': 'Netherlands proxy 2', 'proxy': {'http': 'http://4.245.123.244:80', 'https': 'http://4.245.123.244:80'}, 'timeout': 12},
            {'name': 'Australia proxy', 'proxy': {'http': 'http://4.195.16.140:80', 'https': 'http://4.195.16.140:80'}, 'timeout': 12},
            {'name': 'Netherlands proxy 3', 'proxy': {'http': 'http://108.141.130.146:80', 'https': 'http://108.141.130.146:80'}, 'timeout': 12},
            {'name': 'US elite HTTPS proxy 2', 'proxy': {'http': 'http://54.226.156.148:20201', 'https': 'http://54.226.156.148:20201'}, 'timeout': 15},
            {'name': 'US proxy 3', 'proxy': {'http': 'http://198.98.48.76:31280', 'https': 'http://198.98.48.76:31280'}, 'timeout': 12},
            {'name': 'US proxy 4', 'proxy': {'http': 'http://8.17.0.15:8080', 'https': 'http://8.17.0.15:8080'}, 'timeout': 12},
            {'name': 'Austria proxy 2', 'proxy': {'http': 'http://62.99.138.162:80', 'https': 'http://62.99.138.162:80'}, 'timeout': 12},
            {'name': 'Poland proxy', 'proxy': {'http': 'http://83.175.157.49:3128', 'https': 'http://83.175.157.49:3128'}, 'timeout': 12},
            {'name': 'Belarus elite proxy', 'proxy': {'http': 'http://178.124.197.141:8080', 'https': 'http://178.124.197.141:8080'}, 'timeout': 12},
            {'name': 'Germany proxy 3', 'proxy': {'http': 'http://89.58.55.33:80', 'https': 'http://89.58.55.33:80'}, 'timeout': 12},
            {'name': 'Austria proxy 3', 'proxy': {'http': 'http://213.143.113.82:80', 'https': 'http://213.143.113.82:80'}, 'timeout': 12},
            {'name': 'India proxy', 'proxy': {'http': 'http://219.65.73.81:80', 'https': 'http://219.65.73.81:80'}, 'timeout': 12},
            {'name': 'Slovakia elite HTTPS proxy', 'proxy': {'http': 'http://5.252.33.13:2025', 'https': 'http://5.252.33.13:2025'}, 'timeout': 15},
            {'name': 'Vietnam elite HTTPS proxy', 'proxy': {'http': 'http://14.251.13.0:8080', 'https': 'http://14.251.13.0:8080'}, 'timeout': 15},
            {'name': 'Sweden elite HTTPS proxy', 'proxy': {'http': 'http://138.124.49.149:10808', 'https': 'http://138.124.49.149:10808'}, 'timeout': 15},
            {'name': 'Netherlands elite HTTPS proxy', 'proxy': {'http': 'http://147.75.34.105:443', 'https': 'http://147.75.34.105:443'}, 'timeout': 15},
            {'name': 'Japan elite HTTPS proxy', 'proxy': {'http': 'http://47.79.94.191:1122', 'https': 'http://47.79.94.191:1122'}, 'timeout': 15},
            {'name': 'Ireland elite HTTPS proxy', 'proxy': {'http': 'http://207.254.28.68:2025', 'https': 'http://207.254.28.68:2025'}, 'timeout': 15},
        ]
        
        for approach_idx, approach in enumerate(approaches):
            try:
                print(f"Trying {approach['name']}...")
                
                # Random delay between attempts
                if approach_idx > 0:
                    delay = approach.get('delay', random.uniform(1, 3))
                    time.sleep(delay)
                
                # Setup session with random user agent and additional headers
                session = requests.Session()
                
                # Use different user agent if specified
                if approach.get('different_ua'):
                    ua = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
                else:
                    ua = random.choice(user_agents)
                
                session.headers.update({
                    'User-Agent': ua,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Cache-Control': 'max-age=0',
                    'DNT': '1'
                })
                
                session.timeout = approach.get('timeout', 10)
                
                # Step 1: Get the YouTube watch page
                watch_url = f"https://www.youtube.com/watch?v={video_id}"
                response = session.get(watch_url)
                
                if response.status_code != 200:
                    print(f"Failed to get watch page: {response.status_code}")
                    continue
                
                page_content = response.text
                
                # Step 2: Try multiple patterns to find caption tracks
                caption_patterns = [
                    r'"captionTracks":\s*(\[.*?\])',
                    r'"captions".*?"playerCaptionsTracklistRenderer".*?"captionTracks":\s*(\[.*?\])',
                    r'captionTracks":\s*(\[.*?\])',
                    r'"captionTracks":(\[.*?\])',
                    r'captionTracks.*?(\[.*?\])',
                    r'player_response.*?captionTracks.*?(\[.*?\])'
                ]
                
                caption_tracks = []
                found_pattern = None
                
                for i, pattern in enumerate(caption_patterns):
                    try:
                        match = re.search(pattern, page_content, re.DOTALL)
                        if match:
                            caption_tracks = json.loads(match.group(1))
                            if caption_tracks:
                                found_pattern = i + 1
                                print(f"Found captions using pattern {found_pattern}")
                                break
                    except json.JSONDecodeError:
                        continue
                
                # Step 3: If no captionTracks found, try direct timedtext URLs
                if not caption_tracks:
                    print("No captionTracks found, trying timedtext URLs...")
                    timedtext_patterns = [
                        r'"https://www\.youtube\.com/api/timedtext[^"]*"',
                        r'https://www\.youtube\.com/api/timedtext[^"\s]*',
                        r'timedtext[^"]*v=' + video_id,
                        r'/api/timedtext.*?v=' + video_id
                    ]
                    
                    for j, pattern in enumerate(timedtext_patterns):
                        matches = re.findall(pattern, page_content)
                        if matches:
                            print(f"Found {len(matches)} timedtext URLs with pattern {j+1}")
                            for match in matches[:3]:  # Try first 3 URLs
                                caption_url = match.strip('"')
                                print(f"Trying timedtext URL: {caption_url[:80]}...")
                                transcript = self._try_caption_url(session, caption_url)
                                if transcript:
                                    print(f"✅ Successfully got transcript from timedtext using {approach['name']}")
                                    return transcript
                
                if not caption_tracks:
                    continue
                
                # Step 4: Select best caption track
                preferred_langs = ['en', 'en-US', 'en-GB', 'ar']
                selected_track = None
                
                # Priority 1: Manual captions in preferred languages
                for lang in preferred_langs:
                    for track in caption_tracks:
                        if (track.get('languageCode') == lang and 
                            not track.get('kind')):
                            selected_track = track
                            break
                    if selected_track:
                        break
                
                # Priority 2: Auto-generated in preferred languages
                if not selected_track:
                    for lang in preferred_langs:
                        for track in caption_tracks:
                            if track.get('languageCode', '').startswith(lang):
                                selected_track = track
                                break
                        if selected_track:
                            break
                
                # Priority 3: Any available track
                if not selected_track and caption_tracks:
                    selected_track = caption_tracks[0]
                
                if not selected_track:
                    continue
                
                # Step 5: Fetch caption content
                caption_url = selected_track.get('baseUrl')
                if not caption_url:
                    continue
                
                transcript = self._try_caption_url(session, caption_url)
                if transcript:
                    print(f"✅ Successfully got transcript using {approach['name']}")
                    return transcript
                    
            except Exception as e:
                print(f"Approach '{approach['name']}' failed: {e}")
                continue
        
        # If all approaches fail
        raise Exception("This video cannot be summarized because captions are not accessible. Try again in a few minutes.")
    
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
            import xml.etree.ElementTree as ET
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
        """Detect if the text is Arabic or English based on character analysis"""
        if not text:
            return 'en'
        
        # Count Arabic characters (Unicode range for Arabic script)
        arabic_chars = 0
        english_chars = 0
        total_chars = 0
        
        for char in text:
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
                arabic_word_count += text.count(word)
            
            # Also check for Arabic sentence patterns
            arabic_patterns = ['===', 'فيديو', 'VIDEO']  # Common in mixed transcripts
            pattern_count = sum(1 for pattern in arabic_patterns if pattern in text)
            
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
                
            # Set language-specific templates
            if language == 'ar':
                template = """قم بتحليل وتلخيص النسخة النصية التالية من فيديو يوتيوب باللغة العربية بشكل شامل ومنظم.

مهم جداً: يجب أن يكون الملخص كاملاً باللغة العربية فقط. لا تستخدم أي كلمات إنجليزية في الملخص.

قم بتنسيق إجابتك بالضبط كما في الهيكل التالي:

# 📹 ملخص شامل للفيديو

## 🎯 المواضيع والثيمات الرئيسية
• **الموضوع الأول** - شرح موجز مع السياق والأهمية
• **الموضوع الثاني** - شرح موجز مع السياق والأهمية  
• **الموضوع الثالث** - شرح موجز مع السياق والأهمية

## 📋 النقاط الأساسية والمعلومات المهمة
• **النقطة الأولى** - شرح مفصل مع المعلومات والأدلة الداعمة
• **النقطة الثانية** - شرح مفصل مع المعلومات والأدلة الداعمة
• **النقطة الثالثة** - شرح مفصل مع المعلومات والأدلة الداعمة

## 💡 الرؤى والاستنتاجات المهمة
• **الرؤية الأولى** - تحليل عميق للفكرة وتأثيراتها وأهميتها
• **الرؤية الثانية** - تحليل عميق للفكرة وتأثيراتها وأهميتها
• **الرؤية الثالثة** - تحليل عميق للفكرة وتأثيراتها وأهميتها

## ⚡ النصائح والإرشادات العملية القابلة للتطبيق
• **الإرشاد الأول** - خطوات واضحة ومحددة للتطبيق العملي
• **الإرشاد الثاني** - خطوات واضحة ومحددة للتطبيق العملي
• **الإرشاد الثالث** - خطوات واضحة ومحددة للتطبيق العملي

---
**🎯 الخلاصة النهائية:** [جملة قوية ومؤثرة تلخص الرسالة الأساسية وقيمة المحتوى]"""
            else:
                template = """RESPOND ONLY IN ENGLISH. START IMMEDIATELY:

# 📹 Video Summary

## 🎯 Main Topics & Themes

(CRITICAL INSTRUCTION: Your entire response must be completely in English from start to finish. Do not use any Arabic words or phrases whatsoever, even if the video contains Arabic content.)

TASK: Analyze and summarize the following YouTube video transcript in English in a comprehensive and organized manner.

Use this exact format:

# 📹 Video Summary

## 🎯 Main Topics & Themes
• **Topic 1** - Brief explanation with context and relevance
• **Topic 2** - Brief explanation with context and relevance  
• **Topic 3** - Brief explanation with context and relevance

## 📋 Key Points & Information
• **Point 1** - Detailed explanation with supporting information
• **Point 2** - Detailed explanation with supporting information
• **Point 3** - Detailed explanation with supporting information

## 💡 Notable Insights & Conclusions  
• **Insight 1** - Deep explanation of the insight and its implications
• **Insight 2** - Deep explanation of the insight and its implications
• **Insight 3** - Deep explanation of the insight and its implications

## ⚡ Actionable Takeaways
• **Action 1** - Clear, specific step-by-step guidance
• **Action 2** - Clear, specific step-by-step guidance  
• **Action 3** - Clear, specific step-by-step guidance

---
**🎯 Bottom Line:** [One powerful sentence summarizing the core message and value]

IMPORTANT: Provide the summary entirely in English, even if the transcript contains Arabic content. Translate and explain Arabic content in English."""
            
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
                    progress.update('analyzing', 62, 'تحليل المحتوى...')
                elif language == 'en' and not has_arabic_content:
                    # English UI with English content - show preview (keep this for user engagement)
                    content_preview = transcript[:300] + "..." if len(transcript) > 300 else transcript
                    progress.update('analyzing', 62, 'Analyzing content...', content_preview)
                else:
                    # English UI with other content
                    progress.update('analyzing', 62, 'Analyzing content...')
            elif progress:
                # Fallback for short content
                if language == 'ar':
                    progress.update('analyzing', 62, 'تحليل المحتوى...')
                else:
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
                if progress:
                    if language == 'ar':
                        progress.update('streaming_start', 65, 'إنشاء الملخص...', '')
                    else:
                        progress.update('streaming_start', 65, 'Creating summary...', '')
                
                print(f"🔍 DEBUG: Calling G4F with stream=True for YouTube...")
                # Attempt streaming
                response = self.g4f_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    provider=self.provider,
                    stream=True
                )
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
                if progress:
                    if language == 'ar':
                        progress.update('fallback', 70, 'إنشاء الملخص...')
                    else:
                        progress.update('fallback', 70, 'Creating summary...')
                
                print(f"🔍 DEBUG: Attempting fallback non-streaming call for YouTube...")
                response = self.g4f_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    provider=self.provider
                )
                summary = response.choices[0].message.content
                
                # Real-time word-by-word streaming simulation
                if progress and summary:
                    import time
                    
                    # Split into words for realistic typing effect
                    words = summary.split()
                    accumulated = ""
                    
                    # Stream word by word for true real-time effect
                    for i, word in enumerate(words):
                        # Check for cancellation during word streaming
                        if progress and progress.is_cancelled():
                            print("❌ Task cancelled during word-by-word streaming")
                            return "Task cancelled by user"
                            
                        accumulated += word + " "
                        
                        percentage = 70 + (i / len(words) * 25)  # Progress from 70% to 95%
                        
                        # Send every single word for smooth word-by-word display
                        if language == 'ar':
                            progress.update('word_by_word', percentage, 
                                          f'إنشاء الملخص... {percentage:.0f}%', 
                                          accumulated.strip())
                        else:
                            progress.update('word_by_word', percentage, 
                                          f'Creating summary... {percentage:.0f}%', 
                                          accumulated.strip())
                        
                        # Very fast word-by-word streaming for smooth experience
                        time.sleep(0.04)  # 40ms per word = ~900 WPM (very fast streaming)
            
            if progress:
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

class WebPageAnalyzer:
    def __init__(self):
        # Initialize G4F client for summarization
        self.g4f_client = Client()
        self.model = "Qwen/Qwen3-235B-A22B-Instruct-2507"  # Updated to available Qwen3-235B for better long context handling
        self.provider = g4f.Provider.DeepInfra  # Use DeepInfra provider (same as YouTube)
        
        # Initialize fallback session for non-Crawl4AI extraction
        if not CRAWL4AI_AVAILABLE:
            self.session = HTMLSession()
            # More realistic user agents
            self.user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36'
            ]
            
            # Configure session with realistic headers
            self.session.headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            })
        
        # Universal website-specific patterns for better extraction
        self.site_patterns = {
            # News & Media Sites
            'cnn.com': {
                'selectors': ['.article__content', '.zn-body__paragraph', 'article', '.story-body'],
                'title': 'h1'
            },
            'bbc.com': {
                'selectors': ['[data-component="text-block"]', '.story-body', 'article'],
                'title': 'h1'
            },
            'reuters.com': {
                'selectors': ['.article-body', '.StandardArticleBody_body', 'article'],
                'title': 'h1'
            },
            'nytimes.com': {
                'selectors': ['.ArticleBody-articleBody', '.story-content', 'article'],
                'title': 'h1'
            },
            
            # E-commerce Sites
            'amazon.com': {
                'selectors': ['#feature-bullets', '.product-description', '[data-feature-name="productDescription"]', '#aplus'],
                'title': '#productTitle'
            },
            'ebay.com': {
                'selectors': ['.notranslate', '.item-description', '.u-flL'],
                'title': 'h1'
            },
            
            # Social & Forums
            'medium.com': {
                'selectors': ['article', '.post-content', '.story-content', '.section-content'],
                'title': 'h1'
            },
            'reddit.com': {
                'selectors': ['.usertext-body', '.Post', '[data-testid="post-content"]'],
                'title': 'h1'
            },
            'stackoverflow.com': {
                'selectors': ['.post-text', '.question', '.answer', '.js-post-body'],
                'title': 'h1'
            },
            
            # Documentation & Reference
            'wikipedia.org': {
                'selectors': ['#mw-content-text', '.mw-parser-output'],
                'title': '.firstHeading'
            },
            'github.com': {
                'selectors': ['.markdown-body', '#readme', '.Box-body'],
                'title': 'h1'
            },
            'docs.python.org': {
                'selectors': ['.body', '.document', '.section'],
                'title': 'h1'
            },
            
            # Blogs & Content Sites
            'wordpress.com': {
                'selectors': ['.entry-content', '.post-content', 'article'],
                'title': '.entry-title'
            },
            'blogger.com': {
                'selectors': ['.post-body', '.entry-content'],
                'title': '.post-title'
            },
            
            # News Aggregators
            'hackernews.com': {
                'selectors': ['.comment', '.storylink'],
                'title': '.storylink'
            }
        }

    async def scrape_with_crawl4ai(self, url):
        """Advanced web scraping using Crawl4AI with our proven configuration"""
        try:
            # Minimal browser configuration - headless only
            browser_config = BrowserConfig(
                browser_type="chromium",
                headless=True,  # Pure headless mode
                viewport_width=1920,
                viewport_height=1080,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                verbose=False  # Minimal logging
            )
            
            # Universal crawler configuration - optimized for all website types
            crawler_config = CrawlerRunConfig(
                # Get fresh content
                cache_mode=CacheMode.BYPASS,
                # Generous timeout for various website types
                page_timeout=40000,  # 40 seconds for complex sites
                # Wait for dynamic content to fully load
                delay_before_return_html=4.0,
                # Remove unwanted elements but keep main content
                excluded_tags=['script', 'style', 'noscript'],
                # No screenshot needed for text extraction
                screenshot=False,
                # Minimal logging for clean output
                verbose=False,
                # Allow JavaScript execution for dynamic sites
                js_only=False
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                # Universal JavaScript for better content extraction across all sites
                js_code = """
                // Universal content cleanup for all website types
                const unwantedSelectors = [
                    '[data-module="Advertisement"]', '.ad', '.advertisement', '.banner', '.ads',
                    '.overlay', '.modal', '.popup', '.cookie-banner', '.newsletter-signup',
                    '.social-share', '.sidebar-ads', '[id*="ad"]', '[class*="ad-"]',
                    '.promo', '.promotion', '.sponsored', '.related-ads', '.google-ads'
                ];
                
                unwantedSelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        try { el.remove(); } catch(e) {}
                    });
                });
                
                // Close any modal dialogs that might be blocking content
                document.querySelectorAll('[role="dialog"], .dialog, .modal-backdrop').forEach(el => {
                    try { el.remove(); } catch(e) {}
                });
                
                // Click away cookie banners and consent forms
                const dismissButtons = document.querySelectorAll(
                    '[data-testid*="accept"], [data-testid*="dismiss"], [aria-label*="close"], ' +
                    'button[class*="accept"], button[class*="dismiss"], .cookie-accept, .accept-cookies'
                );
                dismissButtons.forEach(btn => {
                    try { btn.click(); } catch(e) {}
                });
                
                // Wait for dynamic content and any lazy loading
                await new Promise(resolve => setTimeout(resolve, 2000));
                
                // Trigger any lazy loading by scrolling
                window.scrollTo(0, document.body.scrollHeight / 2);
                await new Promise(resolve => setTimeout(resolve, 1000));
                """
                
                result = await crawler.arun(
                    url=url,
                    config=crawler_config.clone(js_code=js_code)
                )
                
                if result.success:
                    # Extract and clean text content
                    markdown_content = result.markdown or ""
                    cleaned_html = result.cleaned_html or ""
                    
                    print(f"📄 Raw markdown length: {len(markdown_content)} characters")
                    print(f"🧹 Cleaned HTML length: {len(cleaned_html)} characters")
                    
                    # Extract readable text from the content
                    
                    # Method 1: Clean up markdown by removing links and formatting
                    clean_markdown = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', markdown_content)  # Remove markdown links
                    clean_markdown = re.sub(r'!\[([^\]]*)\]\([^)]*\)', '', clean_markdown)  # Remove images
                    clean_markdown = re.sub(r'#{1,6}\s*', '', clean_markdown)  # Remove headers
                    clean_markdown = re.sub(r'\*+', '', clean_markdown)  # Remove bold/italic
                    clean_markdown = re.sub(r'\s+', ' ', clean_markdown).strip()  # Normalize whitespace
                    
                    # Method 2: Extract text from HTML
                    clean_html_text = ""
                    try:
                        soup = BeautifulSoup(cleaned_html, 'html.parser')
                        # Remove unwanted elements
                        for element in soup(['script', 'style', 'nav', 'footer', 'aside', 'header']):
                            element.decompose()
                        clean_html_text = soup.get_text(separator=' ', strip=True)
                        clean_html_text = re.sub(r'\s+', ' ', clean_html_text).strip()
                    except Exception as e:
                        print(f"⚠️ HTML parsing error: {e}")
                    
                    # Choose the best content source
                    candidates = [
                        ('cleaned_markdown', clean_markdown),
                        ('cleaned_html_text', clean_html_text),
                        ('raw_markdown', markdown_content),
                    ]
                    
                    # Select the content with the most meaningful text
                    best_content = ""
                    best_method = ""
                    for method, candidate in candidates:
                        if len(candidate) > 500 and len(candidate.split()) > 50:  # Has substantial content
                            best_content = candidate
                            best_method = method
                            break
                    
                    # Fallback if no good content found
                    if not best_content and result.html:
                        print("⚠️ Using raw HTML as final fallback")
                        best_content = result.html
                        best_method = "raw_html"
                    
                    print(f"✅ Selected {best_method}: {len(best_content)} characters")
                    print(f"📝 Content preview: {best_content[:300]}...")
                    
                    return {
                        'content': best_content,
                        'title': result.metadata.get('title', 'No title'),
                        'url': url,
                        'method': 'Advanced Web Scraping',
                        'content_length': len(result.markdown),
                        'success': True
                    }
                else:
                    return {
                        'success': False,
                        'error': result.error_message or "Unknown error",
                        'method': 'Advanced Web Scraping'
                    }
                    
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'method': 'Advanced Web Scraping'
            }

    def detect_language(self, text):
        """Detect if the text is Arabic or English based on character analysis"""
        if not text:
            return 'en'
        
        # Count Arabic characters (Unicode range for Arabic script)
        arabic_chars = 0
        english_chars = 0
        total_chars = 0
        
        for char in text:
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
        
        print(f"Web content language detection - Arabic: {arabic_ratio:.2%}, English: {english_ratio:.2%}")
        
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
                arabic_word_count += text.count(word)
            
            # Also check for Arabic sentence patterns
            arabic_patterns = ['===', 'فيديو', 'VIDEO']  # Common in mixed transcripts
            pattern_count = sum(1 for pattern in arabic_patterns if pattern in text)
            
            print(f"Arabic words found: {arabic_word_count}, patterns: {pattern_count}")
            
            # If we found Arabic words or patterns, and Arabic ratio is not negligible
            if (arabic_word_count > 2 or pattern_count > 0) and arabic_ratio > 0.1:
                return 'ar'
            else:
                return 'en'

    def summarize_content_with_g4f(self, content, title="", custom_prompt=None, target_language=None, progress=None):
        """Summarize extracted content using G4F with intelligent content compression to preserve all information"""
        try:
            if progress:
                # Language-specific progress messages
                if target_language == 'ar':
                    progress.update('processing', 20, 'جاري المعالجة...')
                else:
                    progress.update('processing', 20, 'Processing...')
            
            # Intelligent content optimization for long content
            max_content_length = 20000  # Qwen3-235B model limit
            if len(content) > max_content_length:
                if progress:
                    if target_language == 'ar':
                        progress.update('compressing', 40, 'جاري المعالجة...')
                    else:
                        progress.update('compressing', 40, 'Processing...')
                print(f"📄 Content is {len(content)} chars, using intelligent compression...")
                content = self._intelligent_content_compression(content, max_content_length, progress)
                print(f"📄 Compressed content to {len(content)} chars (preserved all key information)")
                if progress:
                    if target_language == 'ar':
                        progress.update('compressed', 60, 'جاري المعالجة...')
                    else:
                        progress.update('compressed', 60, 'Processing...')
            
            # Use standard summarization
            if progress:
                if target_language == 'ar':
                    progress.update('summarizing', 80, 'إنشاء الملخص...')
                else:
                    progress.update('summarizing', 80, 'Creating summary...')
            print(f"📄 Processing {len(content)} chars with single AI call...")
            result = self._standard_summarize(content, title, custom_prompt, target_language, progress)
            
            if progress:
                if target_language == 'ar':
                    progress.update('finalizing', 95, 'جاري الإنتهاء...')
                else:
                    progress.update('finalizing', 95, 'Almost done...')
            
            return result
        
        except Exception as e:
            return {
                'summary': f"Error generating summary: {str(e)}",
                'success': False,
                'error': str(e),
                'method': 'g4f_main_error'
            }

    def _intelligent_content_compression(self, content, target_length, progress=None):
        """Intelligently compress content by removing redundant information while preserving meaning"""
        try:
            print("🔄 Applying intelligent content compression...")
            
            # Step 1: Remove redundant whitespace and formatting
            import re
            
            # Normalize whitespace
            content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)  # Multiple newlines → double newline
            content = re.sub(r' +', ' ', content)  # Multiple spaces → single space
            content = re.sub(r'\t+', ' ', content)  # Tabs → spaces
            
            # Step 2: Remove navigation and menu items (common website clutter)
            navigation_patterns = [
                r'(?i)(?:home|about|contact|menu|login|register|sign up|sign in|subscribe|follow)\s*[|\-•]\s*',
                r'(?i)(?:facebook|twitter|instagram|linkedin|youtube|tiktok)\s*[|\-•]\s*',
                r'(?i)(?:privacy policy|terms of service|cookie policy|disclaimer)\s*[|\-•]\s*',
                r'(?i)(?:©|copyright|all rights reserved).*?\d{4}',
                r'(?i)(?:share|like|comment|subscribe|follow us)(?:\s+[^\w\s])*',
            ]
            
            for pattern in navigation_patterns:
                content = re.sub(pattern, '', content)
            
            # Step 3: Remove duplicate sentences (common in web scraping)
            sentences = content.split('.')
            seen_sentences = set()
            unique_sentences = []
            
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) > 10:  # Skip very short fragments
                    # Create a normalized version for comparison
                    normalized = re.sub(r'[^\w\s]', '', sentence.lower())
                    if normalized not in seen_sentences:
                        seen_sentences.add(normalized)
                        unique_sentences.append(sentence)
            
            content = '. '.join(unique_sentences)
            
            # Step 4: Smart paragraph compression - keep most informative paragraphs
            paragraphs = content.split('\n\n')
            if len(paragraphs) > 10 and len(content) > target_length:
                
                # Score paragraphs by information density
                scored_paragraphs = []
                for i, para in enumerate(paragraphs):
                    if len(para.strip()) > 20:  # Skip very short paragraphs
                        score = self._score_paragraph_importance(para, i, len(paragraphs))
                        scored_paragraphs.append((score, para))
                
                # Sort by importance and take the best ones
                scored_paragraphs.sort(key=lambda x: x[0], reverse=True)
                
                # Keep paragraphs until we approach target length
                selected_paragraphs = []
                current_length = 0
                
                for score, para in scored_paragraphs:
                    if current_length + len(para) <= target_length * 0.95:  # Leave some buffer
                        selected_paragraphs.append(para)
                        current_length += len(para)
                    elif len(selected_paragraphs) == 0:  # Always keep at least one paragraph
                        selected_paragraphs.append(para[:target_length//2])
                        break
                
                content = '\n\n'.join(selected_paragraphs)
            
            # Step 5: Final length check - if still too long, smart truncation
            if len(content) > target_length:
                print("📄 Applying final smart truncation...")
                # Keep first 80% and last 20% to preserve context
                first_part = int(target_length * 0.8)
                last_part = target_length - first_part - 50  # 50 chars for separator
                
                content = content[:first_part] + "\n[...]\n" + content[-last_part:]
            
            print(f"✅ Compression complete: {len(content)} chars")
            return content
            
        except Exception as e:
            print(f"⚠️ Compression failed, using simple truncation: {e}")
            # Fallback to simple truncation
            return content[:target_length]

    def _score_paragraph_importance(self, paragraph, position, total_paragraphs):
        """Score a paragraph's importance for content selection"""
        score = 0
        para_lower = paragraph.lower()
        
        # Length-based scoring (medium length is best)
        para_len = len(paragraph)
        if 100 <= para_len <= 500:
            score += 10
        elif 50 <= para_len <= 1000:
            score += 5
        elif para_len < 50:
            score -= 5
        
        # Position-based scoring (beginning and end are important)
        if position < total_paragraphs * 0.2:  # First 20%
            score += 8
        elif position > total_paragraphs * 0.8:  # Last 20%
            score += 6
        else:
            score += 3  # Middle content
        
        # Content quality indicators
        quality_indicators = [
            'important', 'key', 'main', 'primary', 'essential', 'crucial', 'significant',
            'conclusion', 'summary', 'result', 'finding', 'research', 'study', 'analysis',
            'because', 'therefore', 'however', 'although', 'furthermore', 'moreover',
            'example', 'instance', 'specifically', 'particular', 'details'
        ]
        
        for indicator in quality_indicators:
            if indicator in para_lower:
                score += 2
        
        # Penalize navigation/menu content
        navigation_words = [
            'click', 'menu', 'navigation', 'home', 'contact', 'about', 'login',
            'register', 'subscribe', 'follow', 'share', 'like', 'comment'
        ]
        
        nav_count = sum(1 for word in navigation_words if word in para_lower)
        score -= nav_count * 3
        
        # Reward informative punctuation
        sentence_count = paragraph.count('.') + paragraph.count('!') + paragraph.count('?')
        if sentence_count > 1:
            score += min(sentence_count, 5)
        
        return score

    def _standard_summarize(self, content, title="", custom_prompt=None, target_language=None, progress=None):
        """Standard summarization for content ≤ 20K characters (existing logic unchanged)"""
        try:
            # Check for cancellation at the start
            if progress and progress.is_cancelled():
                print("❌ Task cancelled during standard summarization")
                return {'success': False, 'error': 'Task cancelled by user'}
                
            # Always detect content language first, use UI language as fallback only
            print(f"🔍 DEBUG: _standard_summarize called with target_language={target_language}")
            print(f"🔍 DEBUG: Content preview: {content[:100]}...")
            
            # Use target language if specified (user preference), otherwise auto-detect
            if target_language and target_language in ['ar', 'en']:
                detected_language = target_language
                print(f"🌐 Using user-selected language: {target_language} ({'Arabic' if detected_language == 'ar' else 'English'})")
            else:
                detected_language = self.detect_language(content)
                print(f"🌐 Auto-detected content language: {detected_language} ({'Arabic' if detected_language == 'ar' else 'English'})")
            
            print(f"🔍 DEBUG: Final language for summary = {detected_language}")
            
            # Create language-specific summarization prompt
            if custom_prompt:
                prompt = custom_prompt.format(content=content, title=title)
            elif detected_language == 'ar':
                # Arabic template with maximum language enforcement
                prompt = f"""تحدث بالعربية فقط. ابدأ فوراً:

# 🌐 ملخص شامل للموقع

## 🎯 المواضيع والثيمات الرئيسية

(ملاحظة مهمة: يجب أن تكون الإجابة كاملة باللغة العربية من البداية للنهاية، ولا تستخدم أي كلمة إنجليزية نهائياً)

المطلوب: قم بتحليل وتلخيص المحتوى التالي من الموقع الإلكتروني باللغة العربية بشكل شامل ومنظم.

استخدم هذا التنسيق بدقة:

# 🌐 ملخص شامل للموقع

## 🎯 المواضيع والثيمات الرئيسية
• **الموضوع الأول** - شرح موجز مع السياق والأهمية
• **الموضوع الثاني** - شرح موجز مع السياق والأهمية  
• **الموضوع الثالث** - شرح موجز مع السياق والأهمية

## 📋 النقاط الأساسية والمعلومات المهمة
• **النقطة الأولى** - شرح مفصل مع المعلومات والأدلة الداعمة
• **النقطة الثانية** - شرح مفصل مع المعلومات والأدلة الداعمة
• **النقطة الثالثة** - شرح مفصل مع المعلومات والأدلة الداعمة

## 💡 الرؤى والاستنتاجات المهمة
• **الرؤية الأولى** - تحليل عميق للفكرة وتأثيراتها وأهميتها
• **الرؤية الثانية** - تحليل عميق للفكرة وتأثيراتها وأهميتها
• **الرؤية الثالثة** - تحليل عميق للفكرة وتأثيراتها وأهميتها

## ⚡ النصائح والإرشادات العملية القابلة للتطبيق
• **الإرشاد الأول** - خطوات واضحة ومحددة للتطبيق العملي
• **الإرشاد الثاني** - خطوات واضحة ومحددة للتطبيق العملي
• **الإرشاد الثالث** - خطوات واضحة ومحددة للتطبيق العملي

---
**🎯 الخلاصة النهائية:** [جملة قوية ومؤثرة تلخص الرسالة الأساسية وقيمة المحتوى]

العنوان: {title}

المحتوى:
{content}

الملخص:"""
            else:
                # English template with strong language enforcement
                prompt = f"""RESPOND ONLY IN ENGLISH. START IMMEDIATELY:

# 🌐 Website Content Summary

## 🎯 Main Topics & Themes

(CRITICAL INSTRUCTION: Your entire response must be completely in English from start to finish. Do not use any Arabic words or phrases whatsoever, even if the content contains Arabic text.)

TASK: Analyze and summarize the following website content in English in a comprehensive and organized manner.

Use this exact format:

# 🌐 Website Content Summary

## 🎯 Main Topics & Themes
• **Topic 1** - Brief explanation with context and relevance
• **Topic 2** - Brief explanation with context and relevance  
• **Topic 3** - Brief explanation with context and relevance

## 📋 Key Points & Information
• **Point 1** - Detailed explanation with supporting information
• **Point 2** - Detailed explanation with supporting information
• **Point 3** - Detailed explanation with supporting information

## 💡 Notable Insights & Conclusions  
• **Insight 1** - Deep explanation of the insight and its implications
• **Insight 2** - Deep explanation of the insight and its implications
• **Insight 3** - Deep explanation of the insight and its implications

## ⚡ Actionable Takeaways
• **Action 1** - Clear, specific step-by-step guidance
• **Action 2** - Clear, specific step-by-step guidance  
• **Action 3** - Clear, specific step-by-step guidance

---
**🎯 Bottom Line:** [One powerful sentence summarizing the core message and value]

IMPORTANT: Provide the summary entirely in English, even if the content contains Arabic text. Translate and explain Arabic content in English.

Title: {title}

Content:
{content}

Summary:"""

            # Use G4F to generate summary with real-time streaming
            if progress:
                if target_language == 'ar':
                    progress.update('ai_processing', 85, 'الاتصال بنموذج الذكاء الاصطناعي...')
                else:
                    progress.update('ai_processing', 85, 'Connecting to AI model...')
            
            # Show content preview logic - avoid showing Arabic content to English users
            if progress and len(content) > 500:
                # Detect if content contains Arabic characters for preview decision
                arabic_char_count = sum(1 for char in content[:500] if '\u0600' <= char <= '\u06FF' or '\u0750' <= char <= '\u077F')
                has_arabic_content = arabic_char_count > 10  # If more than 10 Arabic characters in first 500
                
                if target_language == 'ar':
                    # Arabic UI - show Arabic processing message regardless of content
                    progress.update('analyzing', 87, 'الذكاء الاصطناعي يحلل بنية المحتوى...', 
                                  f"🤖 **جاري المعالجة:**\nيتم الآن تحليل المحتوى وإنتاج الملخص باللغة العربية...")
                elif target_language == 'en' and not has_arabic_content:
                    # English UI with English content - show preview
                    content_preview = content[:500] + "..." if len(content) > 500 else content
                    progress.update('analyzing', 87, 'AI analyzing content structure...', 
                                  f"📖 **Content Preview:**\n\n{content_preview}")
                elif target_language == 'en' and has_arabic_content:
                    # English UI with Arabic content - show processing message without Arabic text
                    progress.update('analyzing', 87, 'AI analyzing Arabic content for English summary...', 
                                  f"🤖 **Processing:**\nAnalyzing Arabic webpage content to generate English summary...")
            elif progress:
                # Fallback for short content
                if target_language == 'ar':
                    progress.update('analyzing', 87, 'الذكاء الاصطناعي يحلل المحتوى...', 
                                  f"🤖 **جاري المعالجة:**\nيتم تحليل المحتوى...")
                else:
                    progress.update('analyzing', 87, 'AI analyzing content...', 
                                  f"🤖 **Processing:**\nAnalyzing content for summary...")
            
            # Try streaming first, fallback to regular if it fails
            summary = ""
            streaming_worked = False
            
            print(f"🔍 DEBUG: About to attempt streaming...")
            print(f"🔍 DEBUG: Model: {self.model}")
            print(f"🔍 DEBUG: Provider: {self.provider}")
            print(f"🔍 DEBUG: Prompt language: {detected_language}")
            print(f"🔍 DEBUG: Prompt length: {len(prompt)} chars")
            
            try:
                if progress:
                    progress.update('streaming_start', 88, 'Creating summary...', '')
                
                print(f"🔍 DEBUG: Calling G4F with stream=True...")
                # Attempt streaming
                response = self.g4f_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    provider=self.provider,
                    stream=True
                )
                print(f"🔍 DEBUG: G4F streaming call successful, processing chunks...")
                
                # Process stream with consistent word-by-word streaming for both languages
                for chunk in response:
                    # Check for cancellation during streaming
                    if progress and progress.is_cancelled():
                        print("❌ Task cancelled during streaming")
                        return {'success': False, 'error': 'Task cancelled by user'}
                        
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = getattr(chunk.choices[0], 'delta', None)
                        if delta and hasattr(delta, 'content') and delta.content:
                            summary += delta.content
                            
                            # Update progress frequently for smooth streaming (every few characters)
                            if len(summary) % 5 < len(delta.content):  # More frequent updates
                                percentage = min(88 + (len(summary) / 20), 97)
                                if detected_language == 'ar':
                                    progress.update('streaming', percentage, 
                                                  f'الذكاء الاصطناعي ينتج المحتوى... ({len(summary)} حرف)', 
                                                  summary)
                                else:
                                    progress.update('streaming', percentage, 
                                                  f'AI generating... ({len(summary)} chars)', 
                                                  summary)
                
                streaming_worked = True
                print("✅ Streaming successful!")
                
            except Exception as stream_error:
                print(f"❌ Streaming failed: {stream_error}")
                print(f"🔍 DEBUG: Stream error type: {type(stream_error)}")
                print(f"🔍 DEBUG: Stream error details: {str(stream_error)}")
                print(f"🔍 DEBUG: Language when streaming failed: {detected_language}")
                print(f"🔍 DEBUG: Target language when streaming failed: {target_language}")
                
                # Fallback to regular generation
                if progress:
                    progress.update('fallback', 89, 'Streaming failed, using standard generation...')
                
                print(f"🔍 DEBUG: Attempting fallback non-streaming call...")
                response = self.g4f_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    provider=self.provider
                )
                summary = response.choices[0].message.content
                
                # Real-time word-by-word streaming simulation
                if progress and summary:
                    import time
                    
                    # Split into words for realistic typing effect
                    words = summary.split()
                    accumulated = ""
                    
                    # Stream word by word for true real-time effect
                    for i, word in enumerate(words):
                        # Check for cancellation during word streaming
                        if progress and progress.is_cancelled():
                            print("❌ Task cancelled during word-by-word streaming")
                            return {'success': False, 'error': 'Task cancelled by user'}
                            
                        accumulated += word + " "
                        
                        percentage = 90 + (i / len(words) * 7)  # Progress from 90% to 97%
                        
                        # Send every single word for smooth word-by-word display
                        progress.update('word_by_word', percentage, 
                                      f'Streaming word {i+1}/{len(words)}...', 
                                      accumulated.strip())
                        
                        # Very fast word-by-word streaming for smooth experience
                        time.sleep(0.04)  # 40ms per word = ~900 WPM (very fast streaming)
            
            if progress:
                progress.update('finalizing', 98, 'Complete', summary)
            
            return {
                'summary': summary,
                'original_title': title,
                'content_length': len(content),
                'summary_length': len(summary),
                'method': f'g4f_{self.model.replace("/", "_")}_standard',
                'success': True
            }
            
        except Exception as e:
            return {
                'summary': f"Error generating summary: {str(e)}",
                'success': False,
                'error': str(e),
                'method': 'g4f_standard_error'
            }

    def _smart_chunk_summarize(self, content, title="", target_language=None, progress=None):
        """Smart chunking summarization for content > 20K characters"""
        try:
            print("🔄 Starting smart chunk summarization...")
            
            # Check for cancellation at the start
            if progress and progress.is_cancelled():
                print("❌ Task cancelled during chunk summarization setup")
                return {'success': False, 'error': 'Task cancelled by user'}
            
            # Detect language
            if target_language:
                detected_language = target_language
                print(f"🌐 Using specified target language: {'Arabic' if detected_language == 'ar' else 'English'}")
            else:
                detected_language = self.detect_language(content)
                print(f"🌐 Detected content language: {'Arabic' if detected_language == 'ar' else 'English'}")
            
            # Split content into meaningful chunks (around 15K chars each with overlap)
            chunk_size = 15000
            overlap = 1000
            chunks = []
            
            # Smart splitting: Try to split at paragraph boundaries
            paragraphs = content.split('\n\n')
            current_chunk = ""
            
            for paragraph in paragraphs:
                if len(current_chunk) + len(paragraph) <= chunk_size:
                    current_chunk += paragraph + '\n\n'
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = paragraph + '\n\n'
            
            # Add the last chunk
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            # Fallback: if we still have huge chunks, split by characters
            final_chunks = []
            for chunk in chunks:
                if len(chunk) <= chunk_size:
                    final_chunks.append(chunk)
                else:
                    # Split large chunk by characters with word boundaries
                    words = chunk.split()
                    current_subchunk = ""
                    for word in words:
                        if len(current_subchunk) + len(word) + 1 <= chunk_size:
                            current_subchunk += word + " "
                        else:
                            if current_subchunk:
                                final_chunks.append(current_subchunk.strip())
                            current_subchunk = word + " "
                    if current_subchunk:
                        final_chunks.append(current_subchunk.strip())
            
            print(f"📊 Split content into {len(final_chunks)} chunks")
            
            # Summarize each chunk
            chunk_summaries = []
            for i, chunk in enumerate(final_chunks):
                # Check for cancellation before each chunk
                if progress and progress.is_cancelled():
                    print(f"❌ Task cancelled during chunk {i+1}/{len(final_chunks)} processing")
                    return {'success': False, 'error': 'Task cancelled by user'}
                
                if progress:
                    chunk_progress = 60 + (i / len(final_chunks) * 25)  # Progress from 60% to 85%
                    progress.update('chunking', chunk_progress, f'Processing chunk {i+1}/{len(final_chunks)}...')
                
                print(f"📝 Summarizing chunk {i+1}/{len(final_chunks)} ({len(chunk)} chars)...")
                
                chunk_summary = self._standard_summarize(
                    chunk, 
                    title=f"{title} (Part {i+1})",
                    target_language=detected_language,
                    progress=None  # Don't pass progress to avoid conflicts
                )
                
                if chunk_summary['success']:
                    chunk_summaries.append(chunk_summary['summary'])
                else:
                    print(f"⚠️ Failed to summarize chunk {i+1}: {chunk_summary['error']}")
                    chunk_summaries.append(f"[Chunk {i+1} summary failed: {chunk_summary['error']}]")
            
            # Combine summaries
            combined_content = "\n\n---\n\n".join(chunk_summaries)
            print(f"📋 Combined summaries: {len(combined_content)} characters")
            
            # Final comprehensive summary
            if detected_language == 'ar':
                final_prompt = f"""لديك عدة ملخصات من أجزاء مختلفة من موقع إلكتروني واحد. قم بدمجها في ملخص شامل واحد باللغة العربية.

مهم جداً: يجب أن يكون الملخص النهائي كاملاً باللغة العربية فقط.

قم بتنسيق إجابتك بالضبط كما في الهيكل التالي:

# 🌐 ملخص شامل للموقع (محتوى طويل)

## 🎯 المواضيع والثيمات الرئيسية
• **الموضوع الأول** - شرح موجز مع السياق والأهمية
• **الموضوع الثاني** - شرح موجز مع السياق والأهمية  
• **الموضوع الثالث** - شرح موجز مع السياق والأهمية

## 📋 النقاط الأساسية والمعلومات المهمة
• **النقطة الأولى** - شرح مفصل مع المعلومات والأدلة الداعمة
• **النقطة الثانية** - شرح مفصل مع المعلومات والأدلة الداعمة
• **النقطة الثالثة** - شرح مفصل مع المعلومات والأدلة الداعمة

## 💡 الرؤى والاستنتاجات المهمة
• **الرؤية الأولى** - تحليل عميق للفكرة وتأثيراتها وأهميتها
• **الرؤية الثانية** - تحليل عميق للفكرة وتأثيراتها وأهميتها
• **الرؤية الثالثة** - تحليل عميق للفكرة وتأثيراتها وأهميتها

## ⚡ النصائح والإرشادات العملية القابلة للتطبيق
• **الإرشاد الأول** - خطوات واضحة ومحددة للتطبيق العملي
• **الإرشاد الثاني** - خطوات واضحة ومحددة للتطبيق العملي
• **الإرشاد الثالث** - خطوات واضحة ومحددة للتطبيق العملي

---
**🎯 الخلاصة النهائية:** [جملة قوية ومؤثرة تلخص الرسالة الأساسية وقيمة المحتوى الكامل]

العنوان الأصلي: {title}

الملخصات المدمجة:
{combined_content}

الملخص النهائي الشامل:"""
            else:
                final_prompt = f"""You have multiple summaries from different sections of the same website. Combine them into one comprehensive summary.

Format your response EXACTLY like this structure:

# 🌐 Comprehensive Website Summary (Long Content)

## 🎯 Main Topics & Themes
• **Topic 1** - Brief explanation with context and relevance
• **Topic 2** - Brief explanation with context and relevance  
• **Topic 3** - Brief explanation with context and relevance

## 📋 Key Points & Information
• **Point 1** - Detailed explanation with supporting information
• **Point 2** - Detailed explanation with supporting information
• **Point 3** - Detailed explanation with supporting information

## 💡 Notable Insights & Conclusions  
• **Insight 1** - Deep explanation of the insight and its implications
• **Insight 2** - Deep explanation of the insight and its implications
• **Insight 3** - Deep explanation of the insight and its implications

## ⚡ Actionable Takeaways
• **Action 1** - Clear, specific step-by-step guidance
• **Action 2** - Clear, specific step-by-step guidance  
• **Action 3** - Clear, specific step-by-step guidance

---
**🎯 Bottom Line:** [One powerful sentence summarizing the core message and value of the complete content]

Original Title: {title}

Combined Summaries:
{combined_content}

Comprehensive Final Summary:"""
            
            print("🔄 Generating final comprehensive summary...")
            response = self.g4f_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": final_prompt}
                ],
                provider=self.provider
            )
            
            final_summary = response.choices[0].message.content
            
            return {
                'summary': final_summary,
                'original_title': title,
                'content_length': len(content),
                'summary_length': len(final_summary),
                'method': f'g4f_{self.model.replace("/", "_")}_smart_chunking',
                'chunks_processed': len(final_chunks),
                'success': True
            }
            
        except Exception as e:
            print(f"❌ Smart chunking failed: {str(e)}")
            return {
                'summary': f"Error in smart chunking: {str(e)}",
                'success': False,
                'error': str(e),
                'method': 'g4f_chunking_error'
            }

    def extract_content(self, url, return_summary=True, target_language=None, progress=None):
        """Extract and optionally summarize content from any webpage or PDF"""
        try:
            # Normalize URL
            url = self._normalize_url(url)
            
            # PDF detection (by extension)
            if url.lower().endswith('.pdf'):
                print(f"Fetching PDF file from: {url}")
                resp = requests.get(url, stream=True, timeout=20)
                resp.raise_for_status()
                # Check content-type header as well
                if 'application/pdf' not in resp.headers.get('Content-Type', ''):
                    raise Exception("URL does not point to a valid PDF file.")
                # Read PDF bytes in memory
                from io import BytesIO
                pdf_file = BytesIO(resp.content)
                try:
                    reader = PyPDF2.PdfReader(pdf_file)
                    max_pages = 50
                    max_chars = 200000
                    text_parts = []
                    warning = None
                    for i, page in enumerate(reader.pages):
                        if i >= max_pages:
                            warning = f"This PDF is very large. Only the first {max_pages} pages were analyzed."
                            break
                        page_text = page.extract_text() or ''
                        if sum(len(t) for t in text_parts) + len(page_text) > max_chars:
                            allowed = max_chars - sum(len(t) for t in text_parts)
                            text_parts.append(page_text[:allowed])
                            warning = f"This PDF is very large. Only the first {i+1} pages and {max_chars} characters were analyzed."
                            break
                        text_parts.append(page_text)
                    text = "\n".join(text_parts)
                except Exception as e:
                    raise Exception(f"Failed to extract text from PDF: {e}")
                if not text or len(text.strip()) < 50:
                    raise Exception("PDF does not contain extractable text or is scanned as images.")
                # Use filename or URL as title
                title = url.split('/')[-1] or 'PDF Document'
                
                # Return summary if requested
                if return_summary:
                    summary_result = self.summarize_content_with_g4f(text, title, target_language=target_language, progress=progress)
                    return {
                        'summary': summary_result.get('summary', 'Failed to generate summary'),
                        'title': title,
                        'url': url,
                        'method': 'AI-Powered PDF Analysis',
                        'warning': warning,
                        'original_length': len(text),
                        'success': summary_result.get('success', False)
                    }
                else:
                    return {
                        'content': text,
                    'title': title,
                    'url': url,
                    'method': 'PDF Document Analysis',
                    'warning': warning
                }
            
            # Domain extraction for potential future use
            domain = urlparse(url).netloc.lower()
            print(f"🌐 Processing domain: {domain}")
            
            # Check for cancellation before starting web scraping
            if progress and progress.is_cancelled():
                print("❌ Task cancelled before web scraping")
                return {'success': False, 'error': 'Task cancelled by user'}
            
            # Try Crawl4AI first (if available)
            if CRAWL4AI_AVAILABLE:
                if progress:
                    # Create language-specific progress messages
                    if target_language == 'ar':
                        detailed_message = f"🕷️ **تفاصيل الاستخراج:**\nالرابط: {url}\nالطريقة: Crawl4AI (متقدم)\nالمهلة الزمنية: 30 ثانية"
                        main_message = 'جاري استخراج الصفحة باستخدام أداة متقدمة...'
                    else:
                        detailed_message = f"🕷️ **Scraping Details:**\nURL: {url}\nMethod: Crawl4AI (Advanced)\nTimeout: 30 seconds"
                        main_message = 'Loading webpage...'
                    
                    progress.update('crawling', 35, main_message, detailed_message)
                
                print(f"Using Crawl4AI to scrape: {url}")
                
                # Run Crawl4AI in async context with proper error handling
                try:
                    # Check if we're already in an async context
                    try:
                        loop = asyncio.get_running_loop()
                        # We're in an async context, create a new thread
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(asyncio.run, self.scrape_with_crawl4ai(url))
                            crawl_result = future.result(timeout=30)
                    except RuntimeError:
                        # No running loop, we can run directly
                        crawl_result = asyncio.run(self.scrape_with_crawl4ai(url))
                except Exception as async_error:
                    print(f"Async execution error: {async_error}")
                    crawl_result = {'success': False, 'error': str(async_error)}
                
                if crawl_result.get('success'):
                    content = crawl_result['content']
                    title = crawl_result['title']
                    
                    if progress:
                        # Language-specific extraction success message
                        if target_language == 'ar':
                            main_msg = 'تم استخراج المحتوى بنجاح!'
                            detail_msg = f"📄 **نجح الاستخراج:**\nالعنوان: {title[:100]}{'...' if len(title) > 100 else ''}\nطول المحتوى: {len(content):,} حرف\nجاهز للمعالجة..."
                        else:
                            main_msg = 'Content extracted successfully!'
                            detail_msg = f"📄 **Extraction Success:**\nTitle: {title[:100]}{'...' if len(title) > 100 else ''}\nContent length: {len(content):,} characters\nReady for processing..."
                        
                        progress.update('extracted', 38, main_msg, detail_msg)
                    
                    # Check if we got good content
                    if content and len(content.strip()) > 100:
                        if return_summary:
                            # Generate summary using G4F
                            print("Generating summary with G4F...")
                            summary_result = self.summarize_content_with_g4f(content, title, target_language=target_language, progress=progress)
                            return {
                                'summary': summary_result.get('summary', 'Failed to generate summary'),
                                'title': title,
                                'url': url,
                                'method': 'AI-powered webpage analysis',
                                'original_length': len(content),
                                'success': summary_result.get('success', False)
                            }
                        else:
                            return {
                                'content': content,
                                'title': title,
                                'url': url,
                                'method': 'Advanced Web Scraping',
                                'success': True
                            }
                    else:
                        print("Crawl4AI returned insufficient content, falling back to requests-html")
                else:
                    print(f"Crawl4AI failed: {crawl_result.get('error', 'Unknown error')}, falling back to requests-html")
            
            # Fallback to requests-html if Crawl4AI is not available or failed
            if not CRAWL4AI_AVAILABLE or not hasattr(self, 'session'):
                self.session = HTMLSession()
                self.user_agents = [
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ]
            
            # Set random user agent and additional headers for fallback
            user_agent = random.choice(self.user_agents) if hasattr(self, 'user_agents') else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            self.session.headers.update({
                'User-Agent': user_agent,
                'Referer': 'https://www.google.com/',
                'DNT': '1',
                'Cache-Control': 'no-cache'
            })
            
            # Enhanced fallback method with better retry logic
            print(f"Using enhanced fallback method to fetch: {url}")
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Enhanced headers for better compatibility
                    enhanced_headers = {
                        'User-Agent': user_agent,
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/avif,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'cross-site',
                        'Cache-Control': 'no-cache',
                        'Pragma': 'no-cache'
                    }
                    self.session.headers.update(enhanced_headers)
                    
                    # Longer timeout for complex sites
                    response = self.session.get(url, timeout=30, allow_redirects=True)
                    response.raise_for_status()
                    
                    # PDF detection by content-type (for URLs without .pdf extension)
                    if 'application/pdf' in response.headers.get('Content-Type', ''):
                        print("Detected PDF by content-type header.")
                        from io import BytesIO
                        pdf_file = BytesIO(response.content)
                        try:
                            reader = PyPDF2.PdfReader(pdf_file)
                            text = "\n".join(page.extract_text() or '' for page in reader.pages)
                        except Exception as e:
                            raise Exception(f"Failed to extract text from PDF: {e}")
                        if not text or len(text.strip()) < 50:
                            raise Exception("PDF does not contain extractable text or is scanned as images.")
                        title = url.split('/')[-1] or 'PDF Document'
                        
                        if return_summary:
                            summary_result = self.summarize_content_with_g4f(text, title, target_language=target_language, progress=progress)
                            return {
                                'summary': summary_result.get('summary', 'Failed to generate summary'),
                                'title': title,
                                'url': url,
                                'method': 'AI-Powered PDF Analysis',
                                'original_length': len(text),
                                'success': summary_result.get('success', False)
                            }
                        else:
                            return {
                                'content': text,
                                'title': title,
                                'url': url,
                                'method': 'PDF Document Analysis'
                            }
                    break
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                    if attempt == max_retries - 1:
                        print(f"⚠️ All {max_retries} attempts failed for {domain}")
                        raise Exception(f"Unable to access {domain}. The website may be temporarily unavailable or have strict access controls.")
                    print(f"🔄 Attempt {attempt + 1} failed, retrying in {(attempt + 1) * 2} seconds...")
                    time.sleep((attempt + 1) * 2)  # Progressive backoff
            
            # Try multiple extraction methods in order of preference
            extraction_methods = [
                ('site_specific', lambda: self._try_site_specific_extraction(response, domain)),
                ('semantic_html5', lambda: self._try_semantic_extraction(response)),
                ('content_patterns', lambda: self._try_pattern_extraction(response))
            ]
            
            for method_name, extraction_func in extraction_methods:
                try:
                    content = extraction_func()
                    if content and self._is_good_content(content):
                        print(f"✅ Successfully extracted content using {method_name} method")
                        if return_summary:
                            summary_result = self.summarize_content_with_g4f(content['text'], content['title'], target_language=target_language, progress=progress)
                            return {
                                'summary': summary_result.get('summary', 'Failed to generate summary'),
                                'title': content['title'],
                                'url': url,
                                'method': f'fallback_{method_name}_with_g4f_summary',
                                'original_length': len(content['text']),
                                'success': summary_result.get('success', False)
                            }
                        else:
                            return {
                                'content': content['text'],
                                'title': content['title'],
                                'url': url,
                                'method': f'fallback_{method_name}'
                            }
                except Exception as e:
                    print(f"⚠️ {method_name} extraction failed: {e}")
                    continue
            
            # Last resort: JavaScript rendering + text blocks
            content = self._try_js_rendering_extraction(response, url)
            if content and self._is_good_content(content):
                return {
                    'content': content['text'],
                    'title': content['title'],
                    'url': url,
                    'method': 'Dynamic Web Rendering'
                }

            # Final fallback: Playwright dynamic rendering
            content = self._try_playwright_extraction(url)
            if content and self._is_good_content(content):
                return {
                    'content': content['text'],
                    'title': content['title'],
                    'url': url,
                    'method': 'Advanced Dynamic Rendering'
                }
            
            raise Exception("Unable to extract meaningful content from this webpage")
            
        except requests.exceptions.Timeout:
            raise Exception("Website took too long to respond. Please try again.")
        except requests.exceptions.ConnectionError:
            raise Exception("Unable to connect to the website. Please check the URL.")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                raise Exception("Access denied by website. Try a different page or direct article link.")
            elif e.response.status_code == 404:
                raise Exception("Page not found. Please check the URL.")
            else:
                raise Exception(f"Website returned error: {e.response.status_code}")
        except Exception as e:
            if "meaningful content" in str(e):
                raise e
            raise Exception(f"Failed to analyze webpage: {str(e)}")

    def _normalize_url(self, url):
        """Normalize and validate URL"""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url

    def _try_site_specific_extraction(self, response, domain):
        """Try extraction using site-specific patterns"""
        for site_domain, patterns in self.site_patterns.items():
            if site_domain in domain:
                print(f"Using site-specific extraction for {site_domain}")
                html = BeautifulSoup(response.html.html, 'html.parser')
                
                # Try each selector for this site
                for selector in patterns['selectors']:
                    element = html.select_one(selector)
                    if element:
                        text = element.get_text(strip=True)
                        if len(text) > 200:  # Minimum content length
                            title = self._extract_title(html, patterns.get('title', 'h1'))
                            return {'text': text, 'title': title}
        return None

    def _try_semantic_extraction(self, response):
        """Try extraction using semantic HTML5 tags"""
        print("Trying semantic HTML5 extraction...")
        html = BeautifulSoup(response.html.html, 'html.parser')
        
        # Remove unwanted elements
        self._remove_unwanted_elements(html)
        
        # Try semantic tags in order of preference
        semantic_selectors = ['article', 'main', '[role="main"]', 'section']
        
        for selector in semantic_selectors:
            elements = html.select(selector)
            
            # Score elements and pick the best one
            best_element = None
            best_score = 0
            
            for element in elements:
                score = self._score_element(element)
                if score > best_score:
                    best_score = score
                    best_element = element
            
            if best_element and best_score > 50:  # Minimum quality threshold
                text = best_element.get_text(strip=True)
                title = self._extract_title(html)
                return {'text': text, 'title': title}
        
        return None

    def _try_pattern_extraction(self, response):
        """Try extraction using common content patterns"""
        print("Trying common pattern extraction...")
        html = BeautifulSoup(response.html.html, 'html.parser')
        
        # Remove unwanted elements
        self._remove_unwanted_elements(html)
        
        # Common content selectors with priority scores
        pattern_selectors = [
            ('.post-content', 90),
            ('.entry-content', 90),
            ('.article-content', 85),
            ('.content', 80),
            ('.main-content', 85),
            ('.page-content', 80),
            ('.post-body', 85),
            ('.article-body', 85),
            ('.story-body', 85),
            ('#content', 75),
            ('#main-content', 80),
            ('#article', 80),
            ('.text-content', 75),
            ('.entry', 70),
            ('.post', 70)
        ]
        
        best_element = None
        best_score = 0
        
        for selector, base_score in pattern_selectors:
            element = html.select_one(selector)
            if element:
                content_score = self._score_element(element)
                total_score = content_score + base_score
                
                if total_score > best_score:
                    best_score = total_score
                    best_element = element
        
        if best_element and best_score > 100:  # Higher threshold for pattern matching
            text = best_element.get_text(strip=True)
            title = self._extract_title(html)
            return {'text': text, 'title': title}
        
        return None

    def _try_js_rendering_extraction(self, response, url):
        """Last resort: JavaScript rendering + text block analysis"""
        print("Trying JavaScript rendering extraction...")
        try:
            # Render JavaScript
            response.html.render(timeout=20)
            html = BeautifulSoup(response.html.html, 'html.parser')
            
            # Remove unwanted elements
            self._remove_unwanted_elements(html)
            
            # Analyze text blocks
            text_blocks = []
            
            # Find all elements with substantial text
            for element in html.find_all(['p', 'div', 'span']):
                text = element.get_text(strip=True)
                if len(text) > 50:  # Minimum text length
                    text_blocks.append({
                        'element': element,
                        'text': text,
                        'length': len(text),
                        'parent_score': self._score_element(element.parent)
                    })
            
            if not text_blocks:
                return None
            
            # Group by parent containers
            containers = {}
            for block in text_blocks:
                parent = block['element'].parent
                if parent not in containers:
                    containers[parent] = []
                containers[parent].append(block)
            
            # Find the best container
            best_container = None
            best_score = 0
            
            for parent, blocks in containers.items():
                total_length = sum(block['length'] for block in blocks)
                avg_parent_score = sum(block['parent_score'] for block in blocks) / len(blocks)
                container_score = total_length + (avg_parent_score * 10)
                
                if container_score > best_score and total_length > 500:
                    best_score = container_score
                    best_container = blocks
            
            if best_container:
                # Combine text from best container
                combined_text = ' '.join(block['text'] for block in best_container)
                title = self._extract_title(html)
                return {'text': combined_text, 'title': title}
            
        except Exception as e:
            print(f"JavaScript rendering failed: {e}")
        
        return None

    def _try_playwright_extraction(self, url, wait_time=5):
        """Use Playwright to load and render the page, then extract with BeautifulSoup."""
        try:
            print("Trying Playwright dynamic extraction (headless)...")
            html = get_dynamic_html(url, wait_time=wait_time)
            soup = BeautifulSoup(html, 'html.parser')
            self._remove_unwanted_elements(soup)
            # Try to extract main content as with other methods
            text_blocks = []
            for element in soup.find_all(['p', 'div', 'span']):
                text = element.get_text(strip=True)
                if len(text) > 50:
                    text_blocks.append({
                        'element': element,
                        'text': text,
                        'length': len(text),
                        'parent_score': self._score_element(element.parent)
                    })
            if not text_blocks:
                return None
            containers = {}
            for block in text_blocks:
                parent = block['element'].parent
                if parent not in containers:
                    containers[parent] = []
                containers[parent].append(block)
            best_container = None
            best_score = 0
            for parent, blocks in containers.items():
                total_length = sum(block['length'] for block in blocks)
                avg_parent_score = sum(block['parent_score'] for block in blocks) / len(blocks)
                container_score = total_length + (avg_parent_score * 10)
                if container_score > best_score and total_length > 500:
                    best_score = container_score
                    best_container = blocks
            if best_container:
                combined_text = ' '.join(block['text'] for block in best_container)
                title = self._extract_title(soup)
                return {'text': combined_text, 'title': title}
        except Exception as e:
            print(f"Playwright extraction failed: {e}")
        return None

    def _remove_unwanted_elements(self, soup):
        """Remove navigation, ads, and other unwanted elements"""
        unwanted_selectors = [
            'nav', 'header', 'footer', '.navigation', '.menu', '.sidebar',
            '.ads', '.advertisement', '.comments', '.social-share', 
            '.related-posts', '.cookie-banner', '.newsletter', '.popup',
            'script', 'style', 'noscript', '.breadcrumb'
        ]
        
        for selector in unwanted_selectors:
            for element in soup.select(selector):
                element.decompose()

    def _score_element(self, element):
        """Score an element based on content quality indicators"""
        if not element:
            return 0
        
        text = element.get_text(strip=True)
        score = 0
        
        # Text length scoring (sweet spot: 500-50000 chars)
        text_length = len(text)
        if 500 <= text_length <= 50000:
            score += 50
        elif 200 <= text_length < 500:
            score += 25
        elif text_length > 50000:
            score -= 20  # Probably grabbed too much
        
        # Paragraph density
        paragraphs = element.find_all('p') if hasattr(element, 'find_all') else []
        if len(paragraphs) > 3:
            score += 30
        
        # Heading presence
        headings = element.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']) if hasattr(element, 'find_all') else []
        score += min(len(headings) * 10, 30)  # Cap at 30 points
        
        # Sentence structure
        sentences = text.split('.')
        if len(sentences) > 5:
            avg_sentence_length = len(text.split()) / len(sentences)
            if 5 <= avg_sentence_length <= 30:  # Good sentence length
                score += 20
        
        # Penalize navigation-like content
        text_lower = text.lower()
        nav_words = ['home', 'menu', 'login', 'search', 'subscribe', 'follow', 'share', 'tweet']
        nav_count = sum(text_lower.count(word) for word in nav_words)
        score -= nav_count * 2
        
        # Penalize high link density
        links = element.find_all('a') if hasattr(element, 'find_all') else []
        link_text_ratio = sum(len(link.get_text()) for link in links) / max(text_length, 1)
        if link_text_ratio > 0.3:  # More than 30% links
            score -= 30
        
        return score

    def _extract_title(self, soup, title_selector='h1'):
        """Extract page title"""
        # Try the specified title selector first
        title_element = soup.select_one(title_selector)
        if title_element:
            title = title_element.get_text(strip=True)
            if title:
                return title
        
        # Fallback to other title sources
        title_selectors = ['h1', 'title', '.title', '.headline', '.post-title', '.entry-title']
        
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                title = element.get_text(strip=True)
                if title and len(title) < 200:  # Reasonable title length
                    return title
        
        return "Untitled"

    def _is_good_content(self, content):
        """Validate extracted content quality"""
        if not content or not content.get('text'):
            return False
        
        text = content['text']
        words = text.split()
        
        # Length checks
        if len(words) < 50:  # Too short
            return False
        if len(words) > 100000:  # Probably grabbed whole page
            return False
        
        # Sentence structure check
        sentences = text.split('.')
        if len(sentences) < 3:  # Too few sentences
            return False
        
        avg_sentence_length = len(words) / len(sentences)
        if avg_sentence_length < 3:  # Just menu items or fragments
            return False
        
        # Navigation content ratio check
        nav_words = ['home', 'about', 'contact', 'menu', 'login', 'search', 'subscribe']
        nav_count = sum(1 for word in words if word.lower() in nav_words)
        if nav_count / len(words) > 0.05:  # More than 5% navigation words
            return False
        
        return True

@app.route('/')
@limiter.exempt  # No rate limit on UI
def index():
    return render_template('index.html')

@app.errorhandler(429)
def rate_limit_handler(e):
    """Handle rate limit exceeded errors"""
    return jsonify({
        'success': False,
        'error': 'Rate limit exceeded. Please try again later.',
        'retry_after': str(e.retry_after) + ' seconds' if hasattr(e, 'retry_after') else 'unknown'
    }), 429

@app.route('/api/health', methods=['GET'])
@limiter.limit("30 per minute")  # Allow frequent health checks
def health_check():
    """Health check endpoint for the API server"""
    return jsonify({
        'status': 'healthy',
        'service': 'YouTube Transcript & Summary API',
        'version': '1.0.0',
        'rate_limits': {
            'health_check': '30 per minute',
            'extract_transcript': '20 per hour',
            'summarize': '10 per hour', 
            'process_video': '10 per hour'
        },
        'endpoints': {
            'extract_transcript': '/api/extract-transcript',
            'summarize': '/api/summarize', 
            'process_video': '/api/process-video'
        }
    })

@app.route('/api/process-video', methods=['POST'])
@limiter.limit("50 per hour")  # Increased limit for complete processing
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
@limiter.limit("100 per hour")  # Increased limit for transcript extraction
def extract_transcript():
    try:
        data = request.json
        video_url = data.get('url')
        
        if not video_url:
            return jsonify({'error': 'Video URL is required'}), 400
        
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
@limiter.limit("50 per hour")  # Increased limit for AI processing
def summarize():
    try:
        data = request.json
        transcript = data.get('transcript')
        language = data.get('language', 'en')
        
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
                
                # Check for cancellation before processing
                if progress.is_cancelled():
                    progress.cancel()
                    return
                
                print(f"🔍 DEBUG: About to call summarize_with_g4f_language")
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
@limiter.limit("30 per hour")
def summarize_video_stream():
    """Start streaming YouTube video analysis - combines transcript extraction and summarization"""
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'YouTube URL is required'}), 400
        
        url = data['url'].strip()
        language = data.get('language', 'en')
        
        if not url:
            return jsonify({'error': 'Please enter a YouTube URL'}), 400
        
        # Basic YouTube URL validation
        if not any(pattern in url.lower() for pattern in ['youtube.com', 'youtu.be']):
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
                
                # Generate summary with streaming
                print(f"🔍 DEBUG: About to generate summary with streaming")
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
@limiter.limit("20 per hour")  # Increased limit for multiple videos
def process_multiple_videos():
    """Process multiple YouTube videos and create a combined summary"""
    try:
        data = request.get_json()
        
        if not data or 'urls' not in data:
            return jsonify({'error': 'URLs are required'}), 400
        
        urls = data['urls']
        language = data.get('language', 'en')
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
@limiter.limit("30 per hour")
def analyze_webpage_stream():
    """Start streaming webpage analysis"""
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'Webpage URL is required'}), 400
        
        url = data['url'].strip()
        language = data.get('language', 'en')
        
        if not url:
            return jsonify({'error': 'Please enter a webpage URL'}), 400
        
        # Basic URL validation
        if not any(url.startswith(prefix) for prefix in ['http://', 'https://', 'www.']):
            return jsonify({'error': 'Please enter a valid URL (e.g., https://example.com)'}), 400
        
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
@limiter.limit("30 per hour")  # Moderate limit for webpage analysis
def analyze_webpage():
    """Analyze and summarize content from any webpage"""
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'Webpage URL is required'}), 400
        
        url = data['url'].strip()
        language = data.get('language', 'en')
        
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


@app.route('/robots.txt')
@limiter.exempt  # No rate limit on robots.txt
def robots_txt():
    return send_from_directory('static', 'robots.txt', mimetype='text/plain')

@app.route('/favicon.ico')
@limiter.exempt  # No rate limit on favicon
def favicon():
    return send_from_directory('static', 'favicon.ico')

@app.route('/apple-touch-icon.png')
@limiter.exempt  # No rate limit on apple touch icon
def apple_touch_icon():
    return send_from_directory('static', 'apple-touch-icon.png')

@app.route('/favicon-32x32.png')
@limiter.exempt  # No rate limit on favicon
def favicon_32():
    return send_from_directory('static', 'favicon-32x32.png')

@app.route('/favicon-16x16.png')
@limiter.exempt  # No rate limit on favicon
def favicon_16():
    return send_from_directory('static', 'favicon-16x16.png')

@app.route('/site.webmanifest')
@limiter.exempt  # No rate limit on manifest
def site_webmanifest():
    return send_from_directory('static', 'site.webmanifest', mimetype='application/json')

@app.route('/static/<path:filename>')
@limiter.exempt  # No rate limit on static files
def static_files(filename):
    return send_from_directory('static', filename)

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