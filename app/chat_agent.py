"""
Chat Agent for URL Q&A using Webscout
Handles webpage content extraction and interactive Q&A using multiple AI providers
Enhanced with Crawl4AI for dynamic content support
"""

import re
import requests
import random
import time
import html
import urllib.parse
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import webscout
import threading
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
import g4f
from g4f.client import Client

# Import Crawl4AI components
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False

class ChatAgent:
    def __init__(self):
        """Initialize chat agent with Webscout AI providers and G4F client"""
        import time
        instance_id = f"ChatAgent_{int(time.time() * 1000)}"
        self.instance_id = instance_id
        # Working AI providers for fast analysis
        self.ai_providers = [
            ('Venice', webscout.Venice, 'chat'),
            ('ChatGPTClone', webscout.ChatGPTClone, 'chat'),
            ('ClaudeOnline', webscout.ClaudeOnline, 'ask'),
            ('OpenGPT', webscout.OpenGPT, 'chat'),
            ('Apriel', webscout.Apriel, 'chat')
        ]
        
        # G4F client for deep analysis (same as webpage analyzer)
        self.g4f_client = Client()
        
        # Use same model configurations as webpage analyzer
        from .config import MODEL_CONFIGS
        self.model_configs = MODEL_CONFIGS
        self.current_config_index = 0
        self.model = self.model_configs[0]["model"]
        self.provider = self.model_configs[0]["provider"]
        
        # Store session data
        self.sessions = {}
        self.cancel_flags = {}
        self.analyzing_sessions = {}  # Track sessions currently being analyzed
        
        # Content extraction settings
        self.max_content_length_fast = 4000  # For Webscout providers
        self.max_content_length_deep = 15000  # For G4F providers (can handle more)
        
        # User agent rotation for bot detection avoidance
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'
        ]
        
    def get_random_headers(self):
        """Get randomized headers to avoid bot detection"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }
        
    def is_arabic_text(self, text):
        """Detect if the text contains Arabic characters"""
        arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
        arabic_chars = len(arabic_pattern.findall(text))
        total_chars = len([c for c in text if c.isalpha()])
        
        # If more than 30% of alphabetic characters are Arabic, consider it Arabic text
        if total_chars > 0:
            return (arabic_chars / total_chars) > 0.3
        return False
    
    def decode_arabic_response(self, text):
        """Comprehensive decoding for Arabic text that may be URL-encoded or HTML-encoded"""
        if not text:
            return text
            
        decoded_text = str(text)
        
        try:
            # First try HTML entity decoding
            decoded_text = html.unescape(decoded_text)
            
            # Try URL decoding (handles %D9%87%D8%B0%D9%87 format)
            try:
                url_decoded = urllib.parse.unquote(decoded_text, encoding='utf-8')
                if url_decoded != decoded_text:
                    decoded_text = url_decoded
            except:
                pass
            
            # Try to handle the specific encoding pattern we're seeing (ÙØ°Ù format)
            # This looks like UTF-8 bytes interpreted as Latin-1
            try:
                # If text contains this pattern, try to fix it
                if 'Ù' in decoded_text or 'Ø' in decoded_text:
                    # Convert back to bytes as latin-1, then decode as utf-8
                    fixed_text = decoded_text.encode('latin-1').decode('utf-8')
                    decoded_text = fixed_text
            except:
                pass
                
            # Additional cleanup for any remaining HTML entities
            decoded_text = html.unescape(decoded_text)
            
        except Exception as e:
            print(f"DEBUG: Error decoding Arabic text: {e}")
            # If all decoding fails, return original text
            pass
            
        return decoded_text
        
    async def scrape_with_crawl4ai(self, url):
        """Advanced web scraping using Crawl4AI with dynamic content support"""
        try:
            # Browser configuration for dynamic content
            browser_config = BrowserConfig(
                browser_type="chromium",
                headless=True,
                viewport_width=1920,
                viewport_height=1080,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                verbose=False
            )
            
            # Crawler configuration optimized for dynamic content
            crawler_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,  # Always get fresh content
                page_timeout=40000,  # 40 seconds for complex sites
                delay_before_return_html=4.0,  # Wait for dynamic content
                excluded_tags=['script', 'style', 'noscript'],
                screenshot=False,
                verbose=False,
                js_only=False  # Allow JavaScript execution
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                # JavaScript to handle dynamic content and clean up page
                js_code = """
                // Remove ads and unwanted elements
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
                
                // Close modals and dialogs
                document.querySelectorAll('[role="dialog"], .dialog, .modal-backdrop').forEach(el => {
                    try { el.remove(); } catch(e) {}
                });
                
                // Handle cookie banners
                const dismissButtons = document.querySelectorAll(
                    '[data-testid*="accept"], [data-testid*="dismiss"], [aria-label*="close"], ' +
                    'button[class*="accept"], button[class*="dismiss"], .cookie-accept, .accept-cookies'
                );
                dismissButtons.forEach(btn => {
                    try { btn.click(); } catch(e) {}
                });
                
                // Wait for dynamic content to load
                await new Promise(resolve => setTimeout(resolve, 3000));
                
                // Trigger lazy loading by scrolling
                window.scrollTo(0, document.body.scrollHeight / 2);
                await new Promise(resolve => setTimeout(resolve, 1000));
                window.scrollTo(0, document.body.scrollHeight);
                await new Promise(resolve => setTimeout(resolve, 1000));
                """
                
                result = await crawler.arun(
                    url=url,
                    config=crawler_config.clone(js_code=js_code)
                )
                
                if result.success:
                    # Process the extracted content
                    markdown_content = result.markdown or ""
                    cleaned_html = result.cleaned_html or ""
                    
                    # Clean up markdown content
                    clean_markdown = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', markdown_content)
                    clean_markdown = re.sub(r'!\[([^\]]*)\]\([^)]*\)', '', clean_markdown)
                    clean_markdown = re.sub(r'#{1,6}\s*', '', clean_markdown)
                    clean_markdown = re.sub(r'\*+', '', clean_markdown)
                    clean_markdown = re.sub(r'\s+', ' ', clean_markdown).strip()
                    
                    # Extract text from HTML
                    clean_html_text = ""
                    try:
                        soup = BeautifulSoup(cleaned_html, 'html.parser')
                        for element in soup(['script', 'style', 'nav', 'footer', 'aside', 'header']):
                            element.decompose()
                        clean_html_text = soup.get_text(separator=' ', strip=True)
                        clean_html_text = re.sub(r'\s+', ' ', clean_html_text).strip()
                    except Exception as e:
                        print(f"⚠️ HTML parsing error: {e}")
                    
                    # Choose the best content
                    candidates = [
                        ('cleaned_markdown', clean_markdown),
                        ('cleaned_html_text', clean_html_text),
                        ('raw_markdown', markdown_content),
                    ]
                    
                    best_content = ""
                    for method, candidate in candidates:
                        if len(candidate) > 500 and len(candidate.split()) > 50:
                            best_content = candidate
                            break
                    
                    # Fallback to raw HTML if needed
                    if not best_content and result.html:
                        best_content = result.html
                    
                    return {
                        'content': best_content,
                        'title': result.metadata.get('title', 'No title'),
                        'url': url,
                        'method': 'Crawl4AI (Dynamic)',
                        'success': True
                    }
                else:
                    return {
                        'success': False,
                        'error': result.error_message or "Unknown error",
                        'method': 'Crawl4AI (Dynamic)'
                    }
                    
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'method': 'Crawl4AI (Dynamic)'
            }

    def fetch_webpage_content_fallback(self, url, session_id, progress_callback=None):
        """Fallback method using basic requests (original implementation)"""
        try:
            if progress_callback:
                progress_callback(session_id, 'fetching', 10, f"🌐 Fetching: {url}", '')
            
            # Get randomized headers to avoid bot detection
            headers = self.get_random_headers()
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            if progress_callback:
                progress_callback(session_id, 'processing', 30, "🧹 Cleaning content...", '')
            
            # Basic HTML cleaning
            content = response.text
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
            content = re.sub(r'<[^>]+>', '', content)
            content = re.sub(r'\s+', ' ', content).strip()
            
            # Validate content quality
            if len(content) < 100:
                raise ValueError(f"Insufficient content extracted (only {len(content)} characters). The page may be empty or require JavaScript.")
            
            # Extract title
            title = "Unknown Title"
            try:
                soup = BeautifulSoup(response.text, 'html.parser')
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.get_text().strip()
            except:
                pass
            
            return {
                'content': content,
                'title': title,
                'url': url,
                'method': 'Basic Requests',
                'success': True
            }
            
        except Exception as e:
            error_msg = str(e)
            if "Connection" in error_msg:
                error_msg = f"Connection failed - please check the URL and your internet connection"
            elif "timeout" in error_msg.lower():
                error_msg = f"Request timed out - the website may be slow or unavailable"
            elif "404" in error_msg:
                error_msg = f"Page not found (404) - please check if the URL is correct"
            elif "403" in error_msg:
                error_msg = f"Access forbidden (403) - the website may be blocking requests"
            else:
                error_msg = f"Request failed: {error_msg}"
            
            return {
                'success': False,
                'error': error_msg,
                'method': 'Basic Requests'
            }

    def fetch_webpage_content(self, url, session_id, analysis_mode='fast', progress_callback=None):
        """Enhanced webpage content fetching optimized for analysis mode"""
        try:
            # Mark analysis as starting
            import time
            self.analyzing_sessions[session_id] = {'url': url, 'start_time': time.time()}
            print(f"DEBUG: Started analysis for session {session_id}, URL: {url}")
            
            # Check if this session already exists with different content
            if session_id in self.sessions:
                existing_url = self.sessions[session_id].get('url', 'unknown')
                print(f"DEBUG: Session {session_id} already exists with URL: {existing_url}, replacing with new URL: {url}")
            # Clean and validate URL
            url = url.strip()
            
            # Remove common prefixes that might be accidentally added
            if url.startswith(('hello', 'hi', 'Hey', 'test')):
                # Look for http/https pattern in the URL
                import re
                url_match = re.search(r'https?://[^\s]+', url)
                if url_match:
                    url = url_match.group()
                else:
                    # If no valid URL found, try to extract domain-like pattern
                    domain_match = re.search(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', url)
                    if domain_match:
                        url = 'https://' + domain_match.group()
            
            # Add https if no protocol
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Basic URL validation
            try:
                parsed = urlparse(url)
                if not parsed.netloc:
                    raise ValueError("Invalid URL format")
            except Exception as e:
                error_msg = f"❌ Invalid URL format: {url}"
                if progress_callback:
                    progress_callback(session_id, 'error', 0, error_msg, '')
                return {'success': False, 'error': error_msg}
            
            if progress_callback:
                progress_callback(session_id, 'fetching', 10, f"🌐 Analyzing: {url}", '')
            
            # For fast analysis, prefer basic extraction (better for Webscout)
            # For deep analysis, use Crawl4AI for comprehensive content
            if analysis_mode == 'deep' and CRAWL4AI_AVAILABLE:
                if progress_callback:
                    progress_callback(session_id, 'processing', 20, "� Using deep content extraction (Crawl4AI)...", '')
                
                try:
                    # Run Crawl4AI in async context
                    crawl_result = asyncio.run(self.scrape_with_crawl4ai(url))
                    
                    if crawl_result['success'] and len(crawl_result['content']) > 200:
                        content = crawl_result['content']
                        title = crawl_result['title']
                        
                        # Store full content for flexible analysis modes
                        # Content limiting will be done per analysis type
                        
                        if progress_callback:
                            progress_callback(session_id, 'content_ready', 80, f"✅ Dynamic content extracted ({len(content)} characters)", content[:200] + "...")
                        
                        # Store content in session
                        self.sessions[session_id] = {
                            'url': url,
                            'title': title,
                            'content': content,
                            'chat_history': [],
                            'method': 'Crawl4AI (Deep Analysis)',
                            'analysis_mode': analysis_mode
                        }
                        print(f"DEBUG: Session {session_id} created with Crawl4AI, content length: {len(content)}")
                        print(f"DEBUG: Total sessions now: {len(self.sessions)}")
                        
                        # Mark analysis as complete
                        if session_id in self.analyzing_sessions:
                            del self.analyzing_sessions[session_id]
                            print(f"DEBUG: Analysis completed for session {session_id}")
                        
                        return {
                            'success': True,
                            'url': url,
                            'title': title,
                            'content': content,
                            'content_length': len(content),
                            'method': 'Crawl4AI (Deep Analysis)',
                            'analysis_mode': analysis_mode
                        }
                    else:
                        print(f"Crawl4AI returned insufficient content (length: {len(crawl_result.get('content', ''))}), falling back to basic requests")
                        if progress_callback:
                            progress_callback(session_id, 'processing', 30, "📄 Crawl4AI insufficient, using basic extraction...", '')
                except Exception as e:
                    print(f"Crawl4AI error: {e}, falling back to basic requests")
                    if progress_callback:
                        progress_callback(session_id, 'processing', 30, "📄 Crawl4AI failed, using basic extraction...", '')
            
            # Use basic requests (preferred for fast analysis or fallback)
            if progress_callback:
                mode_text = "🚀 Fast extraction" if analysis_mode == 'fast' else "📄 Basic extraction (fallback)"
                progress_callback(session_id, 'processing', 40, f"{mode_text}...", '')
            
            fallback_result = self.fetch_webpage_content_fallback(url, session_id, progress_callback)
            
            if fallback_result['success']:
                content = fallback_result['content']
                title = fallback_result['title']
                
                # Store full content for flexible analysis modes
                # Content limiting will be done per analysis type
                
                method_name = 'Fast Extraction (Webscout-optimized)' if analysis_mode == 'fast' else 'Basic Requests (Fallback)'
                if progress_callback:
                    progress_callback(session_id, 'content_ready', 80, f"✅ Content extracted ({len(content)} characters)", content[:200] + "...")
                
                # Store content in session
                self.sessions[session_id] = {
                    'url': url,
                    'title': title,
                    'content': content,
                    'chat_history': [],
                    'method': method_name,
                    'analysis_mode': analysis_mode
                }
                print(f"DEBUG: Session {session_id} created with basic requests, content length: {len(content)}")
                print(f"DEBUG: Total sessions now: {len(self.sessions)}")
                
                # Mark analysis as complete
                if session_id in self.analyzing_sessions:
                    del self.analyzing_sessions[session_id]
                    print(f"DEBUG: Analysis completed for session {session_id}")
                
                return {
                    'success': True,
                    'url': url,
                    'title': title,
                    'content': content,
                    'content_length': len(content),
                    'method': method_name,
                    'analysis_mode': analysis_mode
                }
            else:
                error_msg = f"❌ Failed to fetch webpage: {fallback_result['error']}"
                if progress_callback:
                    progress_callback(session_id, 'error', 0, error_msg, '')
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except Exception as e:
            error_msg = f"❌ Failed to fetch webpage: {str(e)}"
            if progress_callback:
                progress_callback(session_id, 'error', 0, error_msg, '')
            return {
                'success': False,
                'error': error_msg
            }
    
    def clean_ai_response(self, response):
        """Clean up AI response to extract just the answer, removing thinking and reasoning sections"""
        response = str(response)
        
        # Use comprehensive Arabic decoding
        response = self.decode_arabic_response(response)
        
        # Patterns that indicate thinking/reasoning sections that should be removed
        thinking_patterns = [
            "Comprehensive Response to",
            "Understanding \"",
            "in Human-AI Interaction",
            "Thank you for your greeting!",
            "Below, I'll provide a detailed breakdown",
            "This response adheres strictly to your formatting guidelines",
            "Why \"Hello\" Matters in AI Communication",
            "A greeting like \"hello\" serves multiple critical functions:",
            "Social Protocol:", "Intent Signal:", "Cultural Nuance:", "Technical Trigger:",
            "Here are my reasoning steps:",
            "Let me think about this step by step",
            "I need to analyze",
            "First, let me consider",
            "My thought process:",
            "Reasoning:",
            "Analysis:",
        ]
        
        # Check if this looks like a thinking model response
        is_thinking_response = any(pattern in response for pattern in thinking_patterns)
        
        if is_thinking_response:
            # Try to extract the actual answer from thinking models
            lines = response.split('\n')
            clean_lines = []
            in_thinking = True
            found_actual_answer = False
            
            for i, line in enumerate(lines):
                line = line.strip()
                
                # Skip empty lines
                if not line:
                    continue
                
                # Detect end of thinking/start of actual answer
                if any(marker in line.lower() for marker in [
                    "final answer:", "answer:", "response:", "here's", "simply put:",
                    "to answer your question:", "in short:", "the answer is:",
                    "hello!", "hi there!", "greetings!", "nice to meet you"
                ]):
                    in_thinking = False
                    found_actual_answer = True
                    # Include this line if it contains the actual greeting response
                    if any(greeting in line.lower() for greeting in ["hello", "hi", "greetings", "nice to meet"]):
                        clean_lines.append(line)
                    continue
                
                # Skip thinking sections
                if in_thinking:
                    # Check if this line starts the actual conversational response
                    if (line.lower().startswith(('hello', 'hi', 'hey', 'greetings', 'nice to meet')) or
                        line.lower().startswith(('i\'m', 'i am', 'thanks for', 'thank you')) or
                        ('!' in line and len(line) < 50)):  # Short exclamatory responses
                        in_thinking = False
                        found_actual_answer = True
                        clean_lines.append(line)
                    continue
                
                # Keep non-thinking content, but stop at analysis indicators
                if not in_thinking:
                    # Stop if we hit analysis/meta content again
                    if any(stop_word in line.lower() for stop_word in [
                        "let me provide", "let me analyze", "comprehensive analysis", 
                        "detailed breakdown", "below, i'll provide", "this matters because"
                    ]):
                        break
                    clean_lines.append(line)
            
            # If we found actual answer content, use it
            if found_actual_answer and clean_lines:
                response = '\n'.join(clean_lines)
            else:
                # Fallback: try to find a simple greeting response
                simple_response = self._extract_simple_response(response)
                if simple_response:
                    response = simple_response
        
        # Remove reasoning steps and meta text (existing logic)
        if "Here are my reasoning steps:" in response:
            lines = response.split('\n')
            clean_lines = []
            in_reasoning = False
            
            for line in lines:
                if "Here are my reasoning steps:" in line:
                    in_reasoning = True
                    continue
                if "[BEGIN FINAL RESPONSE" in line or "Thus final answer" in line:
                    in_reasoning = False
                    continue
                if "[END FINAL" in line or "<|end|" in line:
                    break
                if not in_reasoning and line.strip():
                    clean_lines.append(line.strip())
            
            if clean_lines:
                response = '\n'.join(clean_lines)
        
        # Clean up common AI artifacts
        response = response.replace("[BEGIN FINAL RESPONSE", "")
        response = response.replace("[END FINAL RESPONSE]", "")
        response = response.replace("<|end|", "")
        response = response.replace("Thus final answer.", "")
        response = response.replace("Answer:", "")
        
        # Remove meta-commentary about formatting guidelines
        response = response.replace("This response adheres strictly to your formatting guidelines", "")
        response = response.replace("while delivering substantive context", "")
        
        # Clean up excessive formatting indicators
        response = response.replace("---", "")
        response = response.replace("###", "")
        
        # Remove excessive whitespace while preserving proper line breaks and spacing
        lines = response.split('\n')
        clean_lines = []
        prev_was_empty = False
        consecutive_empty_count = 0
        
        for i, line in enumerate(lines):
            cleaned_line = ' '.join(line.split())  # Remove extra spaces within lines
            
            if cleaned_line:  # Non-empty line
                # Clean up redundant periods at the end of lines that are list items or short phrases
                if cleaned_line.endswith('.') and len(cleaned_line) < 100 and not cleaned_line.endswith('...'):
                    # Check if it's a list item or heading-like content
                    if (cleaned_line.count('.') == 1 and 
                        not cleaned_line[:-1].endswith(('Inc', 'Ltd', 'Corp', 'Dr', 'Mr', 'Mrs', 'Ms')) and
                        not cleaned_line.startswith(('https://', 'http://', 'www.'))):
                        # Check if it looks like a title or list item (short, no sentence structure)
                        words = cleaned_line[:-1].split()
                        if len(words) <= 8 and not any(word in cleaned_line.lower() for word in ['the', 'is', 'are', 'was', 'were', 'has', 'have']):
                            cleaned_line = cleaned_line[:-1]  # Remove the period
                
                clean_lines.append(cleaned_line)
                prev_was_empty = False
                consecutive_empty_count = 0
            else:  # Empty line
                # Only allow one empty line for spacing, and only between content sections
                if (not prev_was_empty and clean_lines and consecutive_empty_count == 0 and 
                    i < len(lines) - 1):
                    # Check if there's meaningful content after this empty line
                    remaining_lines = lines[i+1:]
                    if any(' '.join(line.split()) for line in remaining_lines):
                        clean_lines.append('')
                        consecutive_empty_count = 1
                prev_was_empty = True
        
        response = '\n'.join(clean_lines)
        
        # Remove trailing empty lines and whitespace more aggressively
        lines = response.split('\n')
        # Remove trailing empty lines
        while lines and not lines[-1].strip():
            lines.pop()
        response = '\n'.join(lines)
        
        # Ensure we never return None
        cleaned = response.strip()
        return cleaned if cleaned else ""
    
    def _detect_content_type(self, text):
        """Detect if text is thinking content, final answer, or regular content
        
        Returns:
            'thinking' - Internal reasoning/analysis that should be collapsible
            'answer' - Final answer/response that should be prominently displayed  
            'regular' - Regular content that should be streamed normally
        """
        if not text or len(text.strip()) < 10:
            return 'regular'
            
        text_lower = text.lower().strip()
        
        # Patterns that indicate final answer/response
        final_answer_patterns = [
            "final answer:",
            "in conclusion:",
            "to summarize:",
            "the answer is:",
            "here's my response:",
            "here's the answer:",
            "my response is:",
            "simply put:",
            "in short:",
            "to answer your question:",
            "based on the analysis above:",
            "therefore:",
            "so in summary:"
        ]
        
        # Check for final answer indicators
        for pattern in final_answer_patterns:
            if pattern in text_lower:
                return 'answer'
        
        # Verbose analytical/thinking patterns (internal reasoning)
        # Enhanced to catch webpage analysis thinking content
        thinking_patterns = [
            "let me think about this",
            "i need to analyze", 
            "comprehensive analysis",
            "comprehensive",  # Catches "### Comprehensive" and similar
            "analysis of the webpage",  # Catches "Comprehensive Analysis of the Webpage"
            "analysis of",  # More flexible matching
            "detailed analysis",
            "thorough analysis",
            "based on the provided content",  # From user examples
            "based on the provided webpage content",  # Specific webpage analysis pattern
            "based on the webpage content",  # Alternative webpage pattern
            "here's a detailed",  # Catches "here's a detailed analysis/breakdown"
            "below is a detailed breakdown",  # From user examples
            "thorough exploration",
            "here's a",
            "detailed examination", 
            "in-depth analysis",
            "let me break this down",
            "i'll analyze this step by step",
            "first, let me consider",
            "my reasoning process:",
            "thinking through this:",
            "step-by-step analysis:",
            "breaking this down:",
            "here's my thinking:",
            "let me work through this:",
            "analyzing the content:",
            "processing this information:",
            "examining the details:",
            "considering the context:",
            "working through the logic:",
            # Removed greeting blockers to allow normal conversation
            # "hello! welcome to your comprehensive ai assistant",
            # "welcome to your comprehensive ai assistance", 
            # "hello! welcome to your ai",
            "i'll provide a comprehensive",
            "let me analyze this request", 
            "i'll structure my response",
            "below is a thorough",
            "demonstrates how i approach",
            # Added patterns for webpage analysis
            "analyzing this webpage",
            "based on the webpage content",
            "examining this content",
            "reviewing the information",
            # Common AI analysis starters that should be collapsible
            "after analyzing",
            "upon reviewing",
            "examining the webpage",
            "looking at this website",
            "from the content provided",
            "according to the webpage"
        ]
        
        # Check for thinking indicators
        for pattern in thinking_patterns:
            if pattern in text_lower:
                return 'thinking'
        
        # Check if it's mostly meta-commentary (internal reasoning)
        meta_words = ["i'll", "i'm", "let me", "i will", "i can", "i understand", "i need to", "let me think"]
        words = text_lower.split()
        meta_count = sum(1 for word in words if any(meta in word for meta in meta_words))
        
        # If more than 40% meta-commentary and longer text, likely thinking content
        if len(words) > 10 and meta_count / len(words) > 0.4:
            return 'thinking'
            
        return 'regular'
    
    def _extract_simple_response(self, response):
        """Extract clean response from AI text, removing meta commentary and thinking patterns"""
        if not response:
            return ""
        
        import re
        
        # Remove common thinking patterns and verbose introductions
        thinking_patterns = [
            r'^.*?(hello!|hi!|thank you for reaching out)[^\.]*\.?\s*',
            r'^.*?(i\'m delighted to assist)[^\.]*\.?\s*',
            r'^.*?(while your message was brief)[^\.]*\.?\s*',
            r'^.*?(i\'ll provide a comprehensive)[^\.]*\.?\s*',
            r'^.*?(let me break this down)[^\.]*\.?\s*',
            r'^.*?(here\'s what i can tell you)[^\.]*\.?\s*',
            r'^.*?(let me analyze)[^\.]*\.?\s*',
            r'^.*?(i understand you\'re asking)[^\.]*\.?\s*'
        ]
        
        cleaned = response
        for pattern in thinking_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Clean up extra whitespace and return meaningful content
        cleaned = re.sub(r'\s+', ' ', cleaned).strip() if cleaned else ""
        
        # If we have meaningful content after cleaning, return it
        if cleaned and len(cleaned) > 10 and self._detect_content_type(cleaned) != 'thinking':
            return cleaned
            
        # If the cleaned text is too short or still contains thinking patterns, 
        # try to extract any actual response content
        if response:
            sentences = response.split('.')
            for sentence in sentences:
                sentence = sentence.strip() if sentence else ""
                if sentence and len(sentence) > 15 and self._detect_content_type(sentence) != 'thinking':
                    return sentence + '.'
                
        # Return original text if we can't clean it effectively
        return response if response else ""
    
    def ask_question_streaming(self, session_id, question, analysis_mode='fast', progress_callback=None):
        """Ask a question with streaming response - supports both webpage analysis and general chat
        
        Args:
            session_id: Session identifier
            question: User's question
            analysis_mode: 'fast' (Webscout) or 'deep' (G4F)
            progress_callback: Progress callback function
        """
        print(f"DEBUG: ask_question_streaming called with session_id={session_id}, mode={analysis_mode}, question='{question[:50]}...'")
        
        # Check if task was cancelled
        if self.cancel_flags.get(session_id, False):
            return {'success': False, 'error': 'Task cancelled by user'}
        
        # Limit question length
        if len(question) > 500:
            question = question[:500] + "..."
        
        # Debug session state
        print(f"DEBUG: Sessions available: {list(self.sessions.keys())}")
        if session_id in self.sessions:
            session_data = self.sessions[session_id]
            has_content = 'content' in session_data and session_data['content']
            has_url = 'url' in session_data and session_data['url']
            print(f"DEBUG: Session {session_id} - has_content: {has_content}, has_url: {has_url}")
            if has_url:
                print(f"DEBUG: Session URL: {session_data['url']}")
        else:
            print(f"DEBUG: Session {session_id} not found in sessions")
        
        # Check if we have webpage content or if this is general chat
        if session_id in self.sessions and 'content' in self.sessions[session_id]:
            # Webpage analysis mode
            session_data = self.sessions[session_id]
            original_content = session_data['content']
            
            print(f"DEBUG: Webpage mode - content length: {len(original_content)}")
            
            # Use different analysis methods based on mode
            if analysis_mode == 'deep':
                return self._ask_question_with_g4f(session_id, question, original_content, session_data, progress_callback)
            else:
                return self._ask_question_with_webscout(session_id, question, original_content, session_data, progress_callback)
        else:
            # General chat mode (no webpage content)
            print(f"DEBUG: General chat mode")
            return self._handle_general_chat(session_id, question, analysis_mode, progress_callback)
    
    def _ask_question_with_webscout(self, session_id, question, original_content, session_data, progress_callback):
        """Handle question using Webscout providers (fast analysis)"""
        # Safety check for None content
        if original_content is None:
            return {
                'success': False,
                'error': 'Webpage content is not available. Please analyze a webpage first.'
            }
        
        # Limit content for Webscout providers
        content = original_content
        if len(content) > self.max_content_length_fast:
            content = content[:self.max_content_length_fast] + "..."
            
        print(f"DEBUG: Using Webscout analysis, truncated content length: {len(content)}")
        
        # Detect language from both question AND content (prioritize content)
        is_arabic_question = self.is_arabic_text(question)
        is_arabic_content = self.is_arabic_text(content)
        
        # Use content language as primary indicator, question language as fallback
        should_respond_in_arabic = is_arabic_content or is_arabic_question
        
        print(f"DEBUG: Language detection - Arabic question: {is_arabic_question}, Arabic content: {is_arabic_content}, Respond in Arabic: {should_respond_in_arabic}")
        
        # Create focused prompt with proper language instruction
        language_instruction = ""
        if should_respond_in_arabic:
            language_instruction = "\nمهم جداً: يجب أن تجيب باللغة العربية فقط. لا تستخدم الإنجليزية نهائياً. المحتوى والسؤال باللغة العربية."
        
        # Create focused prompt
        if should_respond_in_arabic:
            prompt = f"""لقد تم استخراج وتوفير محتوى كامل من صفحة ويب. يرجى تحليل المحتوى والإجابة على سؤال المستخدم بناءً على المحتوى المقدم.

مهم: أنت لا تتصفح الويب - تم استخراج محتوى الصفحة وتوفيره لك أدناه. يجب تحليل هذا المحتوى وتقديم إجابة مفيدة.{language_instruction}

=== معلومات الصفحة ===
العنوان: {session_data['title']}
الرابط: {session_data['url']}

=== محتوى الصفحة ===
{content}

=== سؤال المستخدم ===
{question}

=== مهمتك ===
قم بتحليل محتوى الصفحة المقدم أعلاه وأجب على سؤال المستخدم. كن مباشراً ومفيداً وموجزاً:"""
        else:
            prompt = f"""I have extracted and provided you with the complete content from a webpage. You have full access to this webpage content below. Please analyze it and answer the user's question based on the provided content.

IMPORTANT: You are NOT browsing the web - the webpage content has already been extracted and provided to you below. You should analyze this content and provide a helpful answer.{language_instruction}

=== WEBPAGE INFORMATION ===
Title: {session_data['title']}
URL: {session_data['url']}

=== WEBPAGE CONTENT ===
{content}

=== USER QUESTION ===
{question}

=== YOUR TASK ===
Analyze the webpage content provided above and answer the user's question. Be direct, helpful, and concise:"""

        if progress_callback:
            progress_callback(session_id, 'thinking', 60, f"🤖 AI is thinking about: '{question[:50]}{'...' if len(question) > 50 else ''}'", '')
        
        print(f"DEBUG: Trying AI providers...")
        
        # Try each AI provider
        for name, provider_class, method_name in self.ai_providers:
            # Check if cancelled before trying each provider
            if self.cancel_flags.get(session_id, False):
                return {'success': False, 'error': 'Task cancelled by user'}
            
            try:
                print(f"DEBUG: Trying provider {name}...")
                
                if progress_callback:
                    progress_callback(session_id, 'thinking', 70, f"🤖 AI is thinking...", '')
                
                ai = provider_class()
                method = getattr(ai, method_name)
                
                response = method(prompt)
                print(f"DEBUG: Got response from {name}, type: {type(response)}")
                
                # Handle streaming responses
                if hasattr(response, '__iter__') and not isinstance(response, str):
                    answer = ""
                    accumulated_text = ""
                    word_count = 0
                    
                    for chunk in response:
                        # Check for cancellation during streaming
                        if self.cancel_flags.get(session_id, False):
                            return {'success': False, 'error': 'Task cancelled by user'}
                        
                        chunk_str = str(chunk)
                        accumulated_text += chunk_str
                        
                        # Split accumulated text into words for streaming
                        words = accumulated_text.split()
                        
                        # Stream word by word if we have complete words
                        while len(words) > 1:  # Keep last word as it might be incomplete
                            word = words.pop(0)
                            answer += word + " "
                            word_count += 1
                            
                            # Stream every 2 words to reduce flickering
                            if progress_callback and word_count % 2 == 0:
                                clean_partial = self.clean_ai_response(answer)
                                progress = min(80 + (word_count / 5), 95)
                                progress_callback(session_id, 'word_streaming', progress, f"🗣️ {name} responding...", clean_partial)
                            
                            # Small delay between words for natural typing effect
                            time.sleep(0.08)  # Slightly faster for better flow
                        
                        # Keep the last incomplete word for next iteration
                        accumulated_text = " ".join(words) if words else ""
                        
                        # Stop if we get enough content or if cancelled
                        if len(answer) > 1000:
                            break
                    
                    # Add any remaining text
                    if accumulated_text.strip():
                        answer += accumulated_text
                    
                    if len(answer) > 10:  # Got a reasonable response
                        clean_answer = self.clean_ai_response(answer)
                        if clean_answer and len(clean_answer) > 10:
                            # Add to chat history
                            session_data['chat_history'].append({
                                'question': question,
                                'answer': clean_answer,
                                'provider': name,
                                'timestamp': time.time()
                            })
                            
                            if progress_callback:
                                progress_callback(session_id, 'complete', 100, f"✅ Answer from {name}", clean_answer)
                            
                            print(f"DEBUG: Success with {name}, answer length: {len(clean_answer)}")
                            return {
                                'success': True,
                                'answer': clean_answer,
                                'provider': name,
                                'question': question
                            }
                else:
                    # Regular string response
                    if response and len(str(response)) > 10:
                        clean_answer = self.clean_ai_response(response)
                        if clean_answer and len(clean_answer) > 10:
                            # Add to chat history
                            session_data['chat_history'].append({
                                'question': question,
                                'answer': clean_answer,
                                'provider': name,
                                'timestamp': time.time()
                            })
                            
                            if progress_callback:
                                progress_callback(session_id, 'complete', 100, f"✅ Answer from {name}", clean_answer)
                            
                            print(f"DEBUG: Success with {name}, answer length: {len(clean_answer)}")
                            return {
                                'success': True,
                                'answer': clean_answer,
                                'provider': name,
                                'question': question
                            }
                
                print(f"DEBUG: {name} didn't provide a good answer")
                if progress_callback:
                    progress_callback(session_id, 'provider_failed', 75, f"❌ {name} didn't provide a good answer", '')
                
            except Exception as e:
                print(f"DEBUG: {name} failed with error: {e}")
                if progress_callback:
                    progress_callback(session_id, 'provider_error', 75, f"❌ {name} failed: {str(e)}", '')
                continue
        
        # All providers failed
        error_msg = "💡 All AI providers are currently busy. Please try again in a moment."
        print(f"DEBUG: All providers failed")
        if progress_callback:
            progress_callback(session_id, 'all_failed', 0, error_msg, '')
        
        return {
            'success': False,
            'error': error_msg
        }
    
    def _ask_question_with_g4f(self, session_id, question, original_content, session_data, progress_callback):
        """Handle question using G4F providers (deep analysis)"""
        # Safety check for None content
        if original_content is None:
            return {
                'success': False,
                'error': 'Webpage content is not available. Please analyze a webpage first.'
            }
        
        # Use more content for G4F providers
        content = original_content
        if len(content) > self.max_content_length_deep:
            content = content[:self.max_content_length_deep] + "..."
            
        print(f"DEBUG: Using G4F deep analysis, content length: {len(content)}")
        
        # Detect language from both question AND content (prioritize content)
        is_arabic_question = self.is_arabic_text(question)
        is_arabic_content = self.is_arabic_text(content)
        
        # Use content language as primary indicator, question language as fallback
        should_respond_in_arabic = is_arabic_content or is_arabic_question
        
        print(f"DEBUG: G4F Language detection - Arabic question: {is_arabic_question}, Arabic content: {is_arabic_content}, Respond in Arabic: {should_respond_in_arabic}")
        
        # Create comprehensive prompt for deep analysis
        language_instruction = ""
        if should_respond_in_arabic:
            language_instruction = "\nمهم جداً: يجب أن تجيب باللغة العربية فقط. لا تستخدم الإنجليزية نهائياً. المحتوى والسؤال باللغة العربية."
        
        if should_respond_in_arabic:
            prompt = f"""لقد تم استخراج وتوفير محتوى شامل من صفحة ويب. يرجى تحليله بعمق والإجابة على سؤال المستخدم بتفصيلات ورؤى شاملة.{language_instruction}

معلومات الصفحة:
العنوان: {session_data['title']}
الرابط: {session_data['url']}

إرشادات التنسيق:
- استخدم **النص العريض** للمصطلحات المهمة أو العناوين
- استخدم القوائم المرقمة (1. 2. 3.) للمعلومات التسلسلية
- استخدم النقاط النقطية (- أو •) لقوائم الميزات
- قدم شرحاً مفصلاً وسياقاً
- اذكر الاقتباسات أو البيانات ذات الصلة من المحتوى عند الحاجة

محتوى الصفحة:
{content}

سؤال المستخدم:
{question}

مهمة التحليل العميق:
قدم إجابة شاملة ومنظمة بناءً على محتوى الصفحة. اشمل شرحاً مفصلاً وسياقاً ذا صلة وتحليلاً شاملاً للمعلومات المتعلقة بسؤال المستخدم:"""
        else:
            prompt = f"""I have extracted and provided you with comprehensive content from a webpage. Please analyze it thoroughly and answer the user's question with detailed insights.{language_instruction}

WEBPAGE INFORMATION:
Title: {session_data['title']}
URL: {session_data['url']}

FORMATTING GUIDELINES:
- Use **bold** for important terms or headings
- Use numbered lists (1. 2. 3.) for step-by-step information
- Use bullet points (- or •) for feature lists
- Provide detailed explanations and context
- Include relevant quotes or data from the content when applicable

WEBPAGE CONTENT:
{content}

USER QUESTION:
{question}

DEEP ANALYSIS TASK:
Provide a comprehensive, well-structured answer based on the webpage content. Include detailed explanations, relevant context, and thorough analysis of the information related to the user's question:"""

        if progress_callback:
            progress_callback(session_id, 'thinking', 60, f"🔍 Deep analysis in progress: '{question[:50]}{'...' if len(question) > 50 else ''}'", '')
        
        # Use same model configs as webpage analyzer
        for config_index, model_config in enumerate(self.model_configs):
            if self.cancel_flags.get(session_id, False):
                return {'success': False, 'error': 'Task cancelled by user'}
            
            model = model_config["model"]
            provider = model_config["provider"]
            model_name = model_config["name"]
            
            try:
                print(f"DEBUG: Trying G4F model {model_name} ({model})...")
                
                if progress_callback:
                    progress_callback(session_id, 'thinking', 70, f"🤖 Deep analysis with {model_name}...", '')
                
                # Try streaming first
                try:
                    # Use provider if specified, otherwise let G4F auto-select
                    create_params = {
                        'model': model,
                        'messages': [{"role": "user", "content": prompt}],
                        'stream': True
                    }
                    if provider:
                        create_params['provider'] = provider
                    
                    response = self.g4f_client.chat.completions.create(**create_params)
                    
                    answer = ""
                    word_count = 0
                    
                    for chunk in response:
                        if self.cancel_flags.get(session_id, False):
                            return {'success': False, 'error': 'Task cancelled by user'}
                        
                        if hasattr(chunk, 'choices') and chunk.choices:
                            delta_content = getattr(chunk.choices[0].delta, 'content', None)
                            if delta_content:
                                answer += delta_content
                                word_count += len(delta_content.split())
                                
                                # Stream progress every few words
                                if progress_callback and word_count % 5 == 0:
                                    clean_partial = self.clean_ai_response(answer)
                                    progress = min(80 + (word_count / 10), 95)
                                    progress_callback(session_id, 'word_streaming', progress, f"🔍 {model} analyzing...", clean_partial)
                                
                                # Stop if content is too long
                                if len(answer) > 2000:
                                    break
                    
                    if len(answer) > 20:  # Got a reasonable response
                        clean_answer = self.clean_ai_response(answer)
                        if clean_answer and len(clean_answer) > 20:
                            # Add to chat history
                            session_data['chat_history'].append({
                                'question': question,
                                'answer': clean_answer,
                                'provider': model_name,
                                'analysis_mode': 'deep',
                                'timestamp': time.time()
                            })
                            
                            if progress_callback:
                                progress_callback(session_id, 'complete', 100, f"✅ Deep analysis complete with {model_name}", clean_answer)
                            
                            print(f"DEBUG: Success with G4F {model}, answer length: {len(clean_answer)}")
                            return {
                                'success': True,
                                'answer': clean_answer,
                                'provider': model_name,
                                'analysis_mode': 'deep',
                                'question': question
                            }
                    
                except Exception as streaming_error:
                    print(f"DEBUG: Streaming failed for {model}, trying non-streaming: {streaming_error}")
                    
                    # Fallback to non-streaming
                    create_params = {
                        'model': model,
                        'messages': [{"role": "user", "content": prompt}],
                        'stream': False
                    }
                    if provider:
                        create_params['provider'] = provider
                    
                    response = self.g4f_client.chat.completions.create(**create_params)
                    
                    if hasattr(response, 'choices') and response.choices:
                        answer = response.choices[0].message.content
                        if answer and len(answer) > 20:
                            clean_answer = self.clean_ai_response(answer)
                            if clean_answer:
                                # Add to chat history
                                session_data['chat_history'].append({
                                    'question': question,
                                    'answer': clean_answer,
                                    'provider': model_name,
                                    'analysis_mode': 'deep',
                                    'timestamp': time.time()
                                })
                                
                                if progress_callback:
                                    progress_callback(session_id, 'complete', 100, f"✅ Deep analysis complete with {model_name}", clean_answer)
                                
                                return {
                                    'success': True,
                                    'answer': clean_answer,
                                    'provider': model_name,
                                    'analysis_mode': 'deep',
                                    'question': question
                                }
                
            except Exception as e:
                print(f"DEBUG: G4F model {model} failed: {e}")
                if progress_callback:
                    progress_callback(session_id, 'provider_error', 75, f"❌ {model} failed, trying next...", '')
                continue
        
        # All G4F models failed
        error_msg = "💡 Deep analysis is currently unavailable. Please try Fast Analysis mode or try again later."
        print(f"DEBUG: All G4F models failed")
        if progress_callback:
            progress_callback(session_id, 'all_failed', 0, error_msg, '')
        
        return {
            'success': False,
            'error': error_msg
        }
    
    def _handle_general_chat(self, session_id, question, analysis_mode='fast', progress_callback=None):
        """Handle general chat without webpage context"""
        print(f"DEBUG: General chat mode - question: '{question[:50]}...'")
        
        # Initialize session for general chat if it doesn't exist
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                'url': None,
                'title': 'General Chat',
                'content': None,
                'chat_history': [],
                'method': 'General Chat',
                'analysis_mode': None
            }
        
        session_data = self.sessions[session_id]
        
        # Detect if question is in Arabic
        is_arabic_question = self.is_arabic_text(question)
        
        # Create focused prompt for general chat
        language_instruction = ""
        if is_arabic_question:
            language_instruction = "\nIMPORTANT: The user asked in Arabic, so please respond in Arabic language only. Do not use English."
        
        if analysis_mode == 'deep':
            # Use G4F for deep general chat
            prompt = f"""You are a helpful AI assistant. Please provide a comprehensive, detailed response to the user's question or request.{language_instruction}

FORMATTING GUIDELINES:
- Use **bold** for important terms or headings
- Use numbered lists (1. 2. 3.) for step-by-step information
- Use bullet points (- or •) for feature lists
- Provide detailed explanations and context
- Be thorough and informative

USER QUESTION:
{question}

RESPONSE TASK:
Provide a comprehensive, well-structured answer. Include detailed explanations, relevant context, and thorough analysis of the topic:"""
            
            return self._ask_question_with_g4f_general_chat(session_id, question, prompt, session_data, progress_callback)
        else:
            # Use Webscout for fast general chat
            prompt = f"""You are a helpful AI assistant. Please provide a clear, concise, and helpful response to the user's question or request.{language_instruction}

USER QUESTION: {question}

Please provide a direct, helpful answer:"""
            
            return self._ask_question_with_webscout_general_chat(session_id, question, prompt, session_data, progress_callback)
    
    def _ask_question_with_webscout_general_chat(self, session_id, question, prompt, session_data, progress_callback):
        """Handle general chat using Webscout providers"""
        if progress_callback:
            progress_callback(session_id, 'thinking', 60, f"🤖 AI is thinking about: '{question[:50]}{'...' if len(question) > 50 else ''}'", '')
        
        print(f"DEBUG: Using Webscout for general chat")
        
        # Try each AI provider
        for name, provider_class, method_name in self.ai_providers:
            # Check if cancelled before trying each provider
            if self.cancel_flags.get(session_id, False):
                return {'success': False, 'error': 'Task cancelled by user'}
            
            try:
                print(f"DEBUG: Trying provider {name} for general chat...")
                
                if progress_callback:
                    progress_callback(session_id, 'thinking', 70, f"🤖 {name} is thinking...", '')
                
                ai = provider_class()
                method = getattr(ai, method_name)
                
                response = method(prompt)
                print(f"DEBUG: Got response from {name}, type: {type(response)}")
                
                # Handle streaming and non-streaming responses (same logic as webpage mode)
                if hasattr(response, '__iter__') and not isinstance(response, str):
                    answer = ""
                    accumulated_text = ""
                    word_count = 0
                    
                    for chunk in response:
                        if self.cancel_flags.get(session_id, False):
                            return {'success': False, 'error': 'Task cancelled by user'}
                        
                        chunk_str = str(chunk)
                        accumulated_text += chunk_str
                        
                        words = accumulated_text.split()
                        
                        while len(words) > 1:
                            word = words.pop(0)
                            answer += word + " "
                            word_count += 1
                            
                            if progress_callback and word_count % 2 == 0:
                                clean_partial = self.clean_ai_response(answer)
                                progress = min(80 + (word_count / 5), 95)
                                progress_callback(session_id, 'word_streaming', progress, f"🗣️ {name} responding...", clean_partial)
                            
                            time.sleep(0.08)
                        
                        accumulated_text = " ".join(words) if words else ""
                        
                        if len(answer) > 1000:
                            break
                    
                    if accumulated_text.strip():
                        answer += accumulated_text
                    
                    if len(answer) > 10:
                        clean_answer = self.clean_ai_response(answer)
                        if clean_answer and len(clean_answer) > 10:
                            # Add to chat history
                            session_data['chat_history'].append({
                                'question': question,
                                'answer': clean_answer,
                                'provider': name,
                                'mode': 'general_chat',
                                'timestamp': time.time()
                            })
                            
                            if progress_callback:
                                progress_callback(session_id, 'complete', 100, f"✅ Answer from {name}", clean_answer)
                            
                            return {
                                'success': True,
                                'answer': clean_answer,
                                'provider': name,
                                'mode': 'general_chat',
                                'question': question
                            }
                else:
                    # Regular string response
                    if response and len(str(response)) > 10:
                        clean_answer = self.clean_ai_response(response)
                        if clean_answer and len(clean_answer) > 10:
                            # Add to chat history
                            session_data['chat_history'].append({
                                'question': question,
                                'answer': clean_answer,
                                'provider': name,
                                'mode': 'general_chat',
                                'timestamp': time.time()
                            })
                            
                            if progress_callback:
                                progress_callback(session_id, 'complete', 100, f"✅ Answer from {name}", clean_answer)
                            
                            return {
                                'success': True,
                                'answer': clean_answer,
                                'provider': name,
                                'mode': 'general_chat',
                                'question': question
                            }
                
                print(f"DEBUG: {name} didn't provide a good answer")
                if progress_callback:
                    progress_callback(session_id, 'provider_failed', 75, f"❌ {name} didn't provide a good answer", '')
                
            except Exception as e:
                print(f"DEBUG: {name} failed with error: {e}")
                if progress_callback:
                    progress_callback(session_id, 'provider_error', 75, f"❌ {name} failed: {str(e)}", '')
                continue
        
        # All providers failed
        error_msg = "💡 All AI providers are currently busy. Please try again in a moment."
        if progress_callback:
            progress_callback(session_id, 'all_failed', 0, error_msg, '')
        
        return {
            'success': False,
            'error': error_msg
        }
    
    def _ask_question_with_g4f_general_chat(self, session_id, question, prompt, session_data, progress_callback):
        """Handle general chat using G4F providers"""
        if progress_callback:
            progress_callback(session_id, 'thinking', 60, f"🔍 Deep analysis in progress: '{question[:50]}{'...' if len(question) > 50 else ''}'", '')
        
        # Use same model configs as webpage analyzer
        for config_index, model_config in enumerate(self.model_configs):
            if self.cancel_flags.get(session_id, False):
                return {'success': False, 'error': 'Task cancelled by user'}
            
            model = model_config["model"]
            provider = model_config["provider"]
            model_name = model_config["name"]
            
            try:
                print(f"DEBUG: Trying G4F model {model_name} for general chat...")
                
                if progress_callback:
                    progress_callback(session_id, 'thinking', 70, f"🔍 {model_name} thinking...", '')
                
                # Try streaming first
                try:
                    create_params = {
                        'model': model,
                        'messages': [{"role": "user", "content": prompt}],
                        'stream': True
                    }
                    if provider:
                        create_params['provider'] = provider
                    
                    response = self.g4f_client.chat.completions.create(**create_params)
                    
                    answer = ""
                    word_count = 0
                    
                    for chunk in response:
                        if self.cancel_flags.get(session_id, False):
                            return {'success': False, 'error': 'Task cancelled by user'}
                        
                        if hasattr(chunk, 'choices') and chunk.choices:
                            delta_content = getattr(chunk.choices[0].delta, 'content', None)
                            if delta_content:
                                answer += delta_content
                                word_count += len(delta_content.split())
                                
                                if progress_callback and word_count % 5 == 0:
                                    clean_partial = self.clean_ai_response(answer)
                                    progress = min(80 + (word_count / 10), 95)
                                    progress_callback(session_id, 'word_streaming', progress, f"🔍 {model_name} responding...", clean_partial)
                                
                                if len(answer) > 2000:
                                    break
                    
                    if len(answer) > 20:
                        clean_answer = self.clean_ai_response(answer)
                        if clean_answer and len(clean_answer) > 20:
                            # Add to chat history
                            session_data['chat_history'].append({
                                'question': question,
                                'answer': clean_answer,
                                'provider': f'G4F ({model_name})',
                                'mode': 'general_chat_deep',
                                'timestamp': time.time()
                            })
                            
                            if progress_callback:
                                progress_callback(session_id, 'complete', 100, f"✅ Deep response from {model_name}", clean_answer)
                            
                            return {
                                'success': True,
                                'answer': clean_answer,
                                'provider': f'G4F ({model_name})',
                                'mode': 'general_chat_deep',
                                'question': question
                            }
                    
                except Exception as streaming_error:
                    print(f"DEBUG: G4F streaming failed for {model_name}, trying non-streaming: {streaming_error}")
                    
                    # Fallback to non-streaming
                    create_params = {
                        'model': model,
                        'messages': [{"role": "user", "content": prompt}],
                        'stream': False
                    }
                    if provider:
                        create_params['provider'] = provider
                    
                    response = self.g4f_client.chat.completions.create(**create_params)
                    
                    if hasattr(response, 'choices') and response.choices:
                        answer = response.choices[0].message.content
                        if answer and len(answer) > 20:
                            clean_answer = self.clean_ai_response(answer)
                            if clean_answer:
                                # Add to chat history
                                session_data['chat_history'].append({
                                    'question': question,
                                    'answer': clean_answer,
                                    'provider': f'G4F ({model_name})',
                                    'mode': 'general_chat_deep',
                                    'timestamp': time.time()
                                })
                                
                                if progress_callback:
                                    progress_callback(session_id, 'complete', 100, f"✅ Deep response from {model_name}", clean_answer)
                                
                                return {
                                    'success': True,
                                    'answer': clean_answer,
                                    'provider': f'G4F ({model_name})',
                                    'mode': 'general_chat_deep',
                                    'question': question
                                }
                
            except Exception as e:
                print(f"DEBUG: G4F model {model_name} failed: {e}")
                if progress_callback:
                    progress_callback(session_id, 'provider_error', 75, f"❌ {model_name} failed, trying next...", '')
                continue
        
        # All G4F models failed, fallback to Webscout
        print("DEBUG: All G4F models failed, falling back to Webscout for general chat")
        if progress_callback:
            progress_callback(session_id, 'thinking', 80, "🔄 Switching to fast mode...", '')
        
        # Create simpler prompt for Webscout fallback
        is_arabic_question = self.is_arabic_text(question)
        language_instruction = ""
        if is_arabic_question:
            language_instruction = "\nIMPORTANT: The user asked in Arabic, so please respond in Arabic language only. Do not use English."
        
        fallback_prompt = f"""You are a helpful AI assistant. Please provide a clear, concise, and helpful response.{language_instruction}

USER QUESTION: {question}

Please provide a direct, helpful answer:"""
        
        return self._ask_question_with_webscout_general_chat(session_id, question, fallback_prompt, session_data, progress_callback)
    
    def get_session_info(self, session_id):
        """Get current session information"""
        if session_id not in self.sessions:
            return None
        
        session_data = self.sessions[session_id]
        content = session_data.get('content', '')
        return {
            'url': session_data.get('url'),
            'title': session_data.get('title', 'Unknown'),
            'content_length': len(content) if content else 0,
            'chat_history': session_data.get('chat_history', [])
        }
    
    def get_chat_history(self, session_id):
        """Get chat history for a session"""
        if session_id not in self.sessions:
            return []
        
        return self.sessions[session_id]['chat_history']
    
    def cancel_operation(self, session_id):
        """Cancel ongoing operation for a session"""
        self.cancel_flags[session_id] = True
        return {'success': True, 'message': 'Operation cancelled'}
    
    def clear_cancel_flag(self, session_id):
        """Clear cancel flag for a session"""
        if session_id in self.cancel_flags:
            del self.cancel_flags[session_id]
    
    def ask_question_word_stream(self, session_id, question, analysis_mode='fast'):
        """Ask a question with word-by-word streaming generator - supports both webpage analysis and general chat
        
        Args:
            session_id: Session identifier
            question: User's question
            analysis_mode: 'fast' (Webscout) or 'deep' (G4F)
        """
        # Debug session state
        if session_id in self.sessions:
            session_data = self.sessions[session_id]
            has_content = bool(session_data.get('content'))
            has_url = bool(session_data.get('url'))
            content_length = len(str(session_data.get('content') or ''))  # Safe len() call
            if has_url:
                pass
        else:
            pass
        
        # Check if task was cancelled
        if self.cancel_flags.get(session_id, False):
            yield {'type': 'error', 'message': 'Task cancelled by user'}
            return
        
        # Check if we have webpage content or if this is general chat
        # Add a more robust retry mechanism for timing issues
        session_has_content = False
        session_data = None
        
        # Try up to 5 times with increasing delays to handle race conditions
        import time
        for attempt in range(5):
            if session_id in self.sessions and self.sessions[session_id].get('content'):
                session_has_content = True
                session_data = self.sessions[session_id]
                break
            elif session_id in self.analyzing_sessions:
                # Analysis is ongoing, definitely wait for it
                delay = 0.3 + (attempt * 0.1)
                time.sleep(delay)
            elif attempt < 4:  # Don't sleep on the last attempt (changed from 9 to 4)
                delay = 0.2 + (attempt * 0.1)  # Increasing delay: 0.2s, 0.3s, 0.4s, etc.
                time.sleep(delay)
            else:
                pass
        
        # Check if we have valid session data with actual content
        if (session_has_content and 
            session_data and 
            session_data.get('content') and 
            session_data.get('content') is not None and
            len(str(session_data.get('content', ''))) > 0):
            # Webpage analysis mode
            original_content = session_data['content']
            yield from self._handle_webpage_word_stream(session_id, question, analysis_mode, session_data, original_content)
        else:
            # General chat mode (session not found, or session exists but has no valid content)
            if session_id in self.sessions:
                pass
            else:
                pass
            yield from self._handle_general_chat_word_stream(session_id, question, analysis_mode)
    
    def _handle_webpage_word_stream(self, session_id, question, analysis_mode, session_data, original_content):
        """Handle webpage analysis with word streaming"""
        
        # Safety check for content
        if original_content is None:
            print(f"ERROR: original_content is None for session {session_id}")
            yield {'type': 'error', 'message': 'Webpage content is not available. Please try analyzing the webpage again.'}
            return
        
        # Use appropriate content length based on analysis mode
        if analysis_mode == 'deep':
            content = original_content
            if len(content) > self.max_content_length_deep:
                content = content[:self.max_content_length_deep] + "..."
        else:
            content = original_content  
            if len(content) > self.max_content_length_fast:
                content = content[:self.max_content_length_fast] + "..."
        
        # Limit question length
        if len(question) > 500:
            question = question[:500] + "..."
        
        # Detect language from both question AND content (prioritize content)
        is_arabic_question = self.is_arabic_text(question)
        is_arabic_content = self.is_arabic_text(content)
        
        # Use content language as primary indicator, question language as fallback
        should_respond_in_arabic = is_arabic_content or is_arabic_question
        
        print(f"DEBUG: Word stream language detection - Arabic question: {is_arabic_question}, Arabic content: {is_arabic_content}, Respond in Arabic: {should_respond_in_arabic}")
        
        # Create focused prompt with language instruction
        language_instruction = ""
        if should_respond_in_arabic:
            language_instruction = "\nمهم جداً: يجب أن تجيب باللغة العربية فقط. لا تستخدم الإنجليزية نهائياً. المحتوى والسؤال باللغة العربية."
        
        # Create focused prompt
        if should_respond_in_arabic:
            prompt = f"""لقد تم استخراج وتوفير محتوى كامل من صفحة ويب. يرجى تحليل المحتوى والإجابة على سؤال المستخدم بناءً على المحتوى المقدم.

مهم: أنت لا تتصفح الويب - تم استخراج محتوى الصفحة وتوفيره لك أدناه. يجب تحليل هذا المحتوى وتقديم إجابة مفيدة.{language_instruction}

إرشادات التنسيق:
- استخدم **النص العريض** للمصطلحات المهمة أو العناوين
- استخدم القوائم المرقمة (1. 2. 3.) للمعلومات التسلسلية
- استخدم النقاط النقطية (- أو •) لقوائم الميزات
- اجعل الفقرات قصيرة وسهلة القراءة
- كن واضحاً ومباشراً

=== معلومات الصفحة ===
العنوان: {session_data['title']}
الرابط: {session_data['url']}

=== محتوى الصفحة ===
{content}

=== سؤال المستخدم ===
{question}

=== مهمتك ===
قم بتحليل محتوى الصفحة المقدم أعلاه وأجب على سؤال المستخدم. كن مباشراً ومفيداً واستخدم تنسيقاً مناسباً لجعل إجابتك سهلة القراءة:"""
        else:
            prompt = f"""I have extracted and provided you with the complete content from a webpage. You have full access to this webpage content below. Please analyze it and answer the user's question based on the provided content.

IMPORTANT: You are NOT browsing the web - the webpage content has already been extracted and provided to you below. You should analyze this content and provide a helpful answer.{language_instruction}

FORMATTING GUIDELINES:
- Use **bold** for important terms or headings
- Use numbered lists (1. 2. 3.) for step-by-step information
- Use bullet points (- or •) for feature lists
- Keep paragraphs short and readable
- Be clear and direct

=== WEBPAGE INFORMATION ===
Title: {session_data['title']}
URL: {session_data['url']}

=== WEBPAGE CONTENT ===
{content}

=== USER QUESTION ===
{question}

=== YOUR TASK ===
Analyze the webpage content provided above and answer the user's question. Be direct, helpful, and use proper formatting to make your response easy to read:"""

        yield {'type': 'progress', 'message': f"🤖 AI is thinking about: '{question[:50]}{'...' if len(question) > 50 else ''}'", 'progress': 60}
        
        # Route to appropriate analysis method
        if analysis_mode == 'deep':
            # Use G4F for deep analysis
            yield from self._handle_g4f_word_stream(session_id, question, content, session_data, should_respond_in_arabic)
            return
        
        # Use Webscout for fast analysis
        yield from self._handle_webscout_word_stream(session_id, question, content, session_data, should_respond_in_arabic)
    
    def _handle_webscout_word_stream(self, session_id, question, content, session_data, should_respond_in_arabic):
        """Handle Webscout providers for fast analysis"""
        # Create language instruction
        language_instruction = ""
        if should_respond_in_arabic:
            language_instruction = "\nمهم جداً: يجب أن تجيب باللغة العربية فقط. لا تستخدم الإنجليزية نهائياً. المحتوى والسؤال باللغة العربية."
        
        # Create focused prompt for fast analysis
        if should_respond_in_arabic:
            prompt = f"""لقد تم استخراج وتوفير محتوى كامل من صفحة ويب. يرجى تحليل المحتوى والإجابة على سؤال المستخدم بناءً على المحتوى المقدم.

مهم: أنت لا تتصفح الويب - تم استخراج محتوى الصفحة وتوفيره لك أدناه. يجب تحليل هذا المحتوى وتقديم إجابة مفيدة.{language_instruction}

=== معلومات الصفحة ===
العنوان: {session_data['title']}
الرابط: {session_data['url']}

=== محتوى الصفحة ===
{content}

=== سؤال المستخدم ===
{question}

=== مهمتك ===
قم بتحليل محتوى الصفحة المقدم أعلاه وأجب على سؤال المستخدم. كن مباشراً ومفيداً وموجزاً:"""
        else:
            prompt = f"""I have extracted and provided you with the complete content from a webpage. You have full access to this webpage content below. Please analyze it and answer the user's question based on the provided content.

IMPORTANT: You are NOT browsing the web - the webpage content has already been extracted and provided to you below. You should analyze this content and provide a helpful answer.{language_instruction}

=== WEBPAGE INFORMATION ===
Title: {session_data['title']}
URL: {session_data['url']}

=== WEBPAGE CONTENT ===
{content}

=== USER QUESTION ===
{question}

=== YOUR TASK ===
Analyze the webpage content provided above and answer the user's question. Be direct, helpful, and concise:"""
        
        # Try each AI provider
        for name, provider_class, method_name in self.ai_providers:
            # Check if cancelled before trying each provider
            if self.cancel_flags.get(session_id, False):
                yield {'type': 'error', 'message': 'Task cancelled by user'}
                return
            
            try:
                print(f"DEBUG: Trying provider {name}...")
                
                yield {'type': 'progress', 'message': f"🤖 AI is thinking...", 'progress': 70}
                
                ai = provider_class()
                method = getattr(ai, method_name)
                
                response = method(prompt)
                print(f"DEBUG: Got response from {name}, type: {type(response)}")
                
                # Handle streaming responses
                if hasattr(response, '__iter__') and not isinstance(response, str):
                    accumulated_text = ""
                    last_sent_length = 0
                    
                    for chunk in response:
                        # Check for cancellation during streaming
                        if self.cancel_flags.get(session_id, False):
                            yield {'type': 'error', 'message': 'Task cancelled by user'}
                            return
                        
                        chunk_str = str(chunk)
                        accumulated_text += chunk_str
                        
                        # Send progressive text updates while preserving original formatting
                        # Only send when we have complete words to avoid partial word display
                        words = accumulated_text.split()
                        if len(words) > 1:  # At least 2 words (keep last as it might be incomplete)
                            # Reconstruct text from complete words while preserving newlines
                            complete_text = accumulated_text.rsplit(' ', 1)[0]  # Remove last incomplete word
                            
                            # Only send update if we have new content
                            if len(complete_text) > last_sent_length:
                                # Check for cancellation more frequently during streaming
                                if self.cancel_flags.get(session_id, False):
                                    yield {'type': 'error', 'message': 'Task cancelled by user'}
                                    return
                                
                                yield {
                                    'type': 'streaming',
                                    'text': complete_text,
                                    'progress': min(80 + len(words), 95),
                                    'message': f"🗣️ {name} responding..."
                                }
                                
                                last_sent_length = len(complete_text)
                                
                                # Small delay for natural typing effect
                                time.sleep(0.1)
                        
                        # Stop if we get enough content
                        if len(accumulated_text) > 2000:  # Limit by character count instead
                            break
                    
                    # Send final accumulated text
                    if accumulated_text.strip() and len(accumulated_text) > last_sent_length:
                        yield {
                            'type': 'streaming',
                            'text': accumulated_text.strip(),
                            'progress': 95,
                            'message': f"🗣️ {name} finishing..."
                        }
                    
                    if len(accumulated_text.strip()) > 10:  # Got a reasonable response
                        clean_answer = self.clean_ai_response(accumulated_text)
                        if clean_answer and len(clean_answer) > 10:
                            # Add to chat history
                            session_data['chat_history'].append({
                                'question': question,
                                'answer': clean_answer,
                                'provider': name,
                                'timestamp': time.time()
                            })
                            
                            yield {
                                'type': 'complete',
                                'answer': clean_answer,
                                'provider': name,
                                'question': question
                            }
                            return
                
                # Handle non-streaming responses
                elif isinstance(response, str) and len(response) > 10:
                    print(f"DEBUG: Got string response from {name}, length: {len(response)}")
                    clean_answer = self.clean_ai_response(response)
                    if clean_answer and len(clean_answer) > 10:
                        # Send character by character to preserve formatting during streaming
                        words = clean_answer.split()
                        current_pos = 0
                        
                        for i, word in enumerate(words):
                            # Find the actual position in original text to preserve spacing and newlines
                            word_start = clean_answer.find(word, current_pos)
                            word_end = word_start + len(word)
                            current_text = clean_answer[:word_end]
                            current_pos = word_end
                            
                            # Send update every 2-3 words to reduce flickering
                            if i % 2 == 0 or i == len(words) - 1:
                                yield {
                                    'type': 'streaming',
                                    'text': current_text,
                                    'progress': min(80 + (i * 2), 95),
                                    'message': f"🗣️ {name} responding..."
                                }
                                time.sleep(0.15)  # Slightly longer delay for smoother effect
                        
                        # Add to chat history
                        session_data['chat_history'].append({
                            'question': question,
                            'answer': clean_answer,
                            'provider': name,
                            'timestamp': time.time()
                        })
                        
                        yield {
                            'type': 'complete',
                            'answer': clean_answer,
                            'provider': name,
                            'question': question
                        }
                        return
                
            except Exception as e:
                error_msg = str(e)
                print(f"DEBUG: Error with provider {name}: {e}")
                print(f"DEBUG: Exception type: {type(e)}")
                print(f"DEBUG: Exception args: {e.args}")
                import traceback
                print(f"DEBUG: Full traceback: {traceback.format_exc()}")
                
                # Check if it's a rate limit error
                if "429" in error_msg or "rate limit" in error_msg.lower() or "too many requests" in error_msg.lower():
                    print(f"DEBUG: Rate limit detected for {name}, trying next provider...")
                    yield {'type': 'progress', 'message': f"⏳ {name} is busy, trying alternative AI provider...", 'progress': 75}
                
                continue
        
        # If all providers failed
        yield {'type': 'error', 'message': 'All AI providers are currently busy or unavailable. Please wait a moment and try again.'}
    
    def _handle_g4f_word_stream(self, session_id, question, content, session_data, should_respond_in_arabic):
        """Handle G4F providers for deep analysis with word streaming"""
        # Create language instruction
        language_instruction = ""
        if should_respond_in_arabic:
            language_instruction = "\nمهم جداً: يجب أن تجيب باللغة العربية فقط. لا تستخدم الإنجليزية نهائياً. المحتوى والسؤال باللغة العربية."
        
        # Create comprehensive prompt for deep analysis
        if should_respond_in_arabic:
            prompt = f"""لقد تم استخراج وتوفير محتوى شامل من صفحة ويب. يرجى تحليله بعمق والإجابة على سؤال المستخدم بتفصيلات ورؤى شاملة.{language_instruction}

معلومات الصفحة:
العنوان: {session_data['title']}
الرابط: {session_data['url']}

إرشادات التنسيق:
- استخدم **النص العريض** للمصطلحات المهمة أو العناوين
- استخدم القوائم المرقمة (1. 2. 3.) للمعلومات التسلسلية
- استخدم النقاط النقطية (- أو •) لقوائم الميزات
- قدم شرحاً مفصلاً وسياقاً
- اذكر الاقتباسات أو البيانات ذات الصلة من المحتوى عند الحاجة

محتوى الصفحة:
{content}

سؤال المستخدم:
{question}

مهمة التحليل العميق:
قدم إجابة شاملة ومنظمة بناءً على محتوى الصفحة. اشمل شرحاً مفصلاً وسياقاً ذا صلة وتحليلاً شاملاً للمعلومات المتعلقة بسؤال المستخدم:"""
        else:
            prompt = f"""I have extracted and provided you with comprehensive content from a webpage. Please analyze it thoroughly and answer the user's question with detailed insights.{language_instruction}

WEBPAGE INFORMATION:
Title: {session_data['title']}
URL: {session_data['url']}

FORMATTING GUIDELINES:
- Use **bold** for important terms or headings
- Use numbered lists (1. 2. 3.) for step-by-step information
- Use bullet points (- or •) for feature lists
- Provide detailed explanations and context
- Include relevant quotes or data from the content when applicable

WEBPAGE CONTENT:
{content}

USER QUESTION:
{question}

DEEP ANALYSIS TASK:
Provide a comprehensive, well-structured answer based on the webpage content. Include detailed explanations, relevant context, and thorough analysis of the information related to the user's question:"""

        # Use same model configs as webpage analyzer
        for config_index, model_config in enumerate(self.model_configs):
            if self.cancel_flags.get(session_id, False):
                yield {'type': 'error', 'message': 'Task cancelled by user'}
                return
            
            model = model_config["model"]
            provider = model_config["provider"]
            model_name = model_config["name"]
            
            try:
                yield {'type': 'progress', 'message': f"🔍 Deep analysis with {model_name}...", 'progress': 70}
                
                # Try streaming first
                try:
                    # Use provider if specified, otherwise let G4F auto-select
                    create_params = {
                        'model': model,
                        'messages': [{"role": "user", "content": prompt}],
                        'stream': True
                    }
                    if provider:
                        create_params['provider'] = provider
                    
                    response = self.g4f_client.chat.completions.create(**create_params)
                    
                    accumulated_text = ""
                    
                    for chunk in response:
                        if self.cancel_flags.get(session_id, False):
                            yield {'type': 'error', 'message': 'Task cancelled by user'}
                            return
                        
                        if hasattr(chunk, 'choices') and chunk.choices:
                            delta_content = getattr(chunk.choices[0].delta, 'content', None)
                            if delta_content:
                                accumulated_text += delta_content
                                
                                # Stream each chunk immediately like fast mode
                                yield {
                                    'type': 'streaming',
                                    'text': accumulated_text,
                                    'progress': min(80 + len(accumulated_text) // 50, 95),
                                    'message': f"🔍 {model_name} responding..."
                                }
                                
                                # Small delay for natural typing effect  
                                time.sleep(0.05)
                                
                                # Stop if we get enough content (but allow longer responses in deep mode)
                                if len(accumulated_text) > 4000:
                                    break
                    
                    # Send final response
                    if accumulated_text.strip():
                        clean_answer = self.clean_ai_response(accumulated_text)
                        if clean_answer and len(clean_answer) > 10:
                            # Add to chat history
                            session_data['chat_history'].append({
                                'question': question,
                                'answer': clean_answer,
                                'provider': model_name,
                                'analysis_mode': 'deep',
                                'timestamp': time.time()
                            })
                            
                            yield {
                                'type': 'complete',
                                'answer': clean_answer,
                                'provider': model_name,
                                'question': question
                            }
                            return
                
                except Exception as streaming_error:
                    print(f"DEBUG: G4F streaming failed for {model_name}, trying non-streaming: {streaming_error}")
                    
                    # Fallback to non-streaming
                    create_params = {
                        'model': model,
                        'messages': [{"role": "user", "content": prompt}],
                        'stream': False
                    }
                    if provider:
                        create_params['provider'] = provider
                    
                    response = self.g4f_client.chat.completions.create(**create_params)
                    
                    if hasattr(response, 'choices') and response.choices:
                        answer = response.choices[0].message.content
                        if answer and len(answer) > 20:
                            clean_answer = self.clean_ai_response(answer)
                            if clean_answer:
                                # Simulate streaming while preserving formatting
                                words = clean_answer.split()
                                current_pos = 0
                                
                                for i, word in enumerate(words):
                                    # Find the actual position in original text to preserve spacing and newlines
                                    word_start = clean_answer.find(word, current_pos)
                                    word_end = word_start + len(word)
                                    current_text = clean_answer[:word_end]
                                    current_pos = word_end
                                    
                                    # Send update every 2-3 words
                                    if i % 3 == 0 or i == len(words) - 1:
                                        yield {
                                            'type': 'streaming',
                                            'text': current_text,
                                            'progress': min(80 + (i * 2), 95),
                                            'message': f"🔍 {model} analyzing..."
                                        }
                                        time.sleep(0.15)
                                
                                # Add to chat history
                                session_data['chat_history'].append({
                                    'question': question,
                                    'answer': clean_answer,
                                    'provider': model_name,
                                    'analysis_mode': 'deep',
                                    'timestamp': time.time()
                                })
                                
                                yield {
                                    'type': 'complete',
                                    'answer': clean_answer,
                                    'provider': model_name,
                                    'question': question
                                }
                                return
                
            except Exception as e:
                error_msg = str(e)
                
                # Check if it's a rate limit error
                if "429" in error_msg or "rate limit" in error_msg.lower() or "too many requests" in error_msg.lower():
                    yield {'type': 'progress', 'message': f"⏳ {model} is busy, trying next G4F model...", 'progress': 75}
                
                continue
        
        # If all G4F models failed
        yield {'type': 'error', 'message': 'Deep analysis is currently unavailable. Please try Fast Analysis mode or wait and try again later.'}
    
    def _handle_general_chat_word_stream(self, session_id, question, analysis_mode):
        """Handle general chat with word streaming"""
        print(f"DEBUG: General chat word stream mode - question: '{question[:50]}...'")
        
        # Initialize session for general chat if it doesn't exist
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                'url': None,
                'title': 'General Chat',
                'content': None,
                'chat_history': [],
                'method': 'General Chat',
                'analysis_mode': None
            }
        
        session_data = self.sessions[session_id]
        
        # Limit question length
        if len(question) > 500:
            question = question[:500] + "..."
        
        # Detect if question is in Arabic
        is_arabic_question = self.is_arabic_text(question)
        
        yield {'type': 'progress', 'message': f"🤖 AI is thinking: '{question[:50]}{'...' if len(question) > 50 else ''}'", 'progress': 60}
        
        # Create language instruction
        language_instruction = ""
        if is_arabic_question:
            language_instruction = "\nIMPORTANT: The user asked in Arabic, so please respond in Arabic language only. Do not use English."
        
        if analysis_mode == 'deep':
            # Use G4F for deep general chat - try each G4F model
            prompt = f"""You are a helpful AI assistant. Please provide a comprehensive, detailed response to the user's question or request.{language_instruction}

FORMATTING GUIDELINES:
- Use **bold** for important terms or headings
- Use numbered lists (1. 2. 3.) for step-by-step information
- Use bullet points (- or •) for feature lists
- Provide detailed explanations and context
- Be thorough and informative

USER QUESTION:
{question}

RESPONSE TASK:
Provide a comprehensive, well-structured answer. Include detailed explanations, relevant context, and thorough analysis of the topic:"""

            # Try G4F models
            for config_index, model_config in enumerate(self.model_configs):
                if self.cancel_flags.get(session_id, False):
                    yield {'type': 'error', 'message': 'Task cancelled by user'}
                    return
                
                model = model_config["model"]
                provider = model_config["provider"]
                model_name = model_config["name"]
                
                try:
                    print(f"DEBUG: Trying G4F model {model_name} for general chat word streaming...")
                    
                    yield {'type': 'progress', 'message': f"🔍 {model_name} thinking...", 'progress': 70}
                    
                    create_params = {
                        'model': model,
                        'messages': [{"role": "user", "content": prompt}],
                        'stream': True
                    }
                    if provider:
                        create_params['provider'] = provider
                    
                    response = self.g4f_client.chat.completions.create(**create_params)
                    
                    accumulated_text = ""
                    last_sent_length = 0
                    
                    for chunk in response:
                        if self.cancel_flags.get(session_id, False):
                            yield {'type': 'error', 'message': 'Task cancelled by user'}
                            return
                        
                        if hasattr(chunk, 'choices') and chunk.choices:
                            delta_content = getattr(chunk.choices[0].delta, 'content', None)
                            if delta_content:
                                accumulated_text += delta_content
                                
                                # Send progressive text updates while preserving original formatting
                                words = accumulated_text.split()
                                if len(words) > 1:  # At least 2 words (keep last as it might be incomplete)
                                    # Reconstruct text from complete words while preserving newlines
                                    complete_text = accumulated_text.rsplit(' ', 1)[0]  # Remove last incomplete word
                                    
                                    # Only send update if we have new content
                                    if len(complete_text) > last_sent_length:
                                        # Detect content type for proper display
                                        content_type = self._detect_content_type(complete_text)
                                        
                                        if content_type == 'thinking':
                                            # Stream thinking content to collapsible section
                                            yield {
                                                'type': 'thinking_content',
                                                'text': complete_text,
                                                'progress': min(80 + len(words) // 4, 90),
                                                'message': f"🤔 {model_name} thinking..."
                                            }
                                        elif content_type == 'answer':
                                            # Extract and stream final answer prominently
                                            clean_text = self._extract_simple_response(complete_text)
                                            if clean_text:
                                                yield {
                                                    'type': 'final_answer',
                                                    'text': clean_text,
                                                    'progress': min(85 + len(words) // 2, 95),
                                                    'message': f"✨ {model_name} responding..."
                                                }
                                        else:
                                            # Regular content - stream normally
                                            yield {
                                                'type': 'streaming',
                                                'text': complete_text,
                                                'progress': min(80 + len(words) // 2, 95),
                                                'message': f"🔍 {model_name} responding..."
                                            }
                                        
                                        last_sent_length = len(complete_text)
                                        time.sleep(0.12)
                                
                                if len(accumulated_text) > 3000:  # Limit by character count
                                    break
                    
                    # Send final accumulated text
                    if accumulated_text.strip() and len(accumulated_text) > last_sent_length:
                        yield {
                            'type': 'streaming',
                            'text': accumulated_text.strip(),
                            'progress': 95,
                            'message': f"🔍 {model_name} finishing..."
                        }
                    
                    if len(accumulated_text.strip()) > 10:  # Got a reasonable response
                        clean_answer = self.clean_ai_response(accumulated_text)
                        if clean_answer and len(clean_answer) > 10:
                            session_data['chat_history'].append({
                                'question': question,
                                'answer': clean_answer,
                                'provider': f'G4F ({model_name})',
                                'mode': 'general_chat_deep',
                                'timestamp': time.time()
                            })
                            
                            yield {
                                'type': 'complete',
                                'answer': clean_answer,
                                'provider': f'G4F ({model_name}) - General Chat',
                                'question': question
                            }
                            return
                
                except Exception as e:
                    print(f"DEBUG: G4F model {model_name} failed for general chat: {e}")
                    yield {'type': 'progress', 'message': f"⏳ {model_name} is busy, trying next...", 'progress': 75}
                    continue
            
            # All G4F models failed, fallback to Webscout
            yield {'type': 'progress', 'message': f"🔄 Switching to fast mode...", 'progress': 80}
        
        # Use Webscout for fast general chat (or as G4F fallback)
        prompt = f"""You are a helpful AI assistant. Please provide a clear, concise, and helpful response to the user's question or request.{language_instruction}

USER QUESTION: {question}

Please provide a direct, helpful answer:"""
        
        # Try each Webscout provider
        for name, provider_class, method_name in self.ai_providers:
            if self.cancel_flags.get(session_id, False):
                yield {'type': 'error', 'message': 'Task cancelled by user'}
                return
            
            try:
                print(f"DEBUG: Trying Webscout provider {name} for general chat...")
                
                yield {'type': 'progress', 'message': f"🤖 {name} thinking...", 'progress': 70}
                
                ai = provider_class()
                method = getattr(ai, method_name)
                
                response = method(prompt)
                
                # Handle streaming responses (same logic as webpage mode)
                if hasattr(response, '__iter__') and not isinstance(response, str):
                    accumulated_text = ""
                    words_sent = []
                    
                    for chunk in response:
                        if self.cancel_flags.get(session_id, False):
                            yield {'type': 'error', 'message': 'Task cancelled by user'}
                            return
                        
                        chunk_str = str(chunk)
                        accumulated_text += chunk_str
                        
                        words = accumulated_text.split()
                        
                        while len(words) > 1:
                            word = words.pop(0)
                            words_sent.append(word)
                            current_text = " ".join(words_sent)
                            
                            yield {
                                'type': 'streaming',
                                'text': current_text,
                                'progress': min(80 + len(words_sent), 95),
                                'message': f"🗣️ {name} responding..."
                            }
                            
                            time.sleep(0.1)
                        
                        accumulated_text = " ".join(words) if words else ""
                        
                        if len(words_sent) > 100:
                            break
                    
                    if accumulated_text.strip():
                        words_sent.append(accumulated_text.strip())
                        current_text = " ".join(words_sent)
                        yield {
                            'type': 'streaming',
                            'text': current_text,
                            'progress': 95,
                            'message': f"🗣️ {name} finishing..."
                        }
                    
                    if len(words_sent) > 5:
                        final_answer = " ".join(words_sent)
                        clean_answer = self.clean_ai_response(final_answer)
                        if clean_answer and len(clean_answer) > 10:
                            session_data['chat_history'].append({
                                'question': question,
                                'answer': clean_answer,
                                'provider': name,
                                'mode': 'general_chat',
                                'timestamp': time.time()
                            })
                            
                            yield {
                                'type': 'complete',
                                'answer': clean_answer,
                                'provider': f'{name} - General Chat',
                                'question': question
                            }
                            return
                
                # Handle non-streaming responses
                elif isinstance(response, str) and len(response) > 10:
                    clean_answer = self.clean_ai_response(response)
                    if clean_answer and len(clean_answer) > 10:
                        # Simulate word-by-word for non-streaming responses
                        words = clean_answer.split()
                        current_text = ""
                        for i, word in enumerate(words):
                            current_text += (word + " " if i < len(words) - 1 else word)
                            
                            if i % 2 == 0 or i == len(words) - 1:
                                yield {
                                    'type': 'streaming',
                                    'text': current_text,
                                    'progress': min(80 + (i * 2), 95),
                                    'message': f"🗣️ {name} responding..."
                                }
                                time.sleep(0.15)
                        
                        session_data['chat_history'].append({
                            'question': question,
                            'answer': clean_answer,
                            'provider': name,
                            'mode': 'general_chat',
                            'timestamp': time.time()
                        })
                        
                        yield {
                            'type': 'complete',
                            'answer': clean_answer,
                            'provider': f'{name} - General Chat',
                            'question': question
                        }
                        return
                
            except Exception as e:
                print(f"DEBUG: Webscout provider {name} failed for general chat: {e}")
                yield {'type': 'progress', 'message': f"⏳ {name} is busy, trying next AI provider...", 'progress': 75}
                continue
        
        # If all providers failed
        yield {'type': 'error', 'message': 'All AI providers are currently busy or unavailable. Please wait a moment and try again.'}

    def clear_cancel_flag(self, session_id):
        """Clear cancel flag for a session"""
        if session_id in self.cancel_flags:
            self.cancel_flags[session_id] = False
    
    def clear_session(self, session_id):
        """Clear session data"""
        if session_id in self.sessions:
            del self.sessions[session_id]
        if session_id in self.cancel_flags:
            del self.cancel_flags[session_id]
        return {'success': True, 'message': 'Session cleared'}
    
    def summarize_webpage(self, session_id):
        """Generate a summary of the webpage content"""
        if session_id not in self.sessions:
            return {'success': False, 'error': 'No content loaded. Please analyze a URL first.'}
        
        session_data = self.sessions[session_id]
        summary_question = "Please provide a comprehensive summary of this webpage content, highlighting the main points and key information."
        
        return self.ask_question_streaming(session_id, summary_question)