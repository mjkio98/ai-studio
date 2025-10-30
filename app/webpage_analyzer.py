"""
Web page analysis module.
Handles webpage content extraction, PDF processing, and AI-powered summarization.
"""

import re
import requests
import random
import asyncio
import concurrent.futures
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from requests_html import HTMLSession
import PyPDF2
from io import BytesIO
import g4f
from g4f.client import Client

from .config import CRAWL4AI_AVAILABLE, MODEL_CONFIGS, SITE_PATTERNS, MAX_CONTENT_LENGTH, LANGUAGE_TEMPLATES

if CRAWL4AI_AVAILABLE:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

class WebPageAnalyzer:
    def __init__(self):
        # Initialize G4F client for summarization
        self.g4f_client = Client()
        
        # Primary and fallback configurations (same as YouTubeProcessor)
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
                'نستخدم خوارزميات متطورة لفهم الصفحة...',
                'جاري استخراج أهم المعلومات من المحتوى...',
                'نحلل كل عنصر لإنشاء ملخص رائع...',
                'الذكاء الاصطناعي يعمل على تحسين النتائج...',
                'جاري فهم سياق المحتوى وتحليله...',
                'نستخدم تقنيات متقدمة لتحليل النصوص...',
                'جاري إنشاء ملخصات ذكية ومفيدة...',
            ]
        else:
            messages = [
                'Analyzing content with advanced AI...',
                'Using sophisticated algorithms to understand the page...',
                'Extracting the most important information from content...',
                'Analyzing every element to create amazing summaries...',
                'AI is working to optimize results...',
                'Understanding context and analyzing content...',
                'Using advanced techniques to analyze texts...',
                'Creating smart and useful summaries...',
            ]
        return random.choice(messages)
        
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
        self.site_patterns = SITE_PATTERNS

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
        last_error = None
        original_config_index = self.current_config_index
        
        # Try each model in the fallback chain
        while self.current_config_index < len(self.model_configs):
            try:
                config = self.model_configs[self.current_config_index]
                print(f"🤖 Trying model: {config['name']}")
                
                # Update progress with random engaging message
                if progress:
                    model_attempt = self.current_config_index + 1
                    total_models = len(self.model_configs)
                    random_message = self._get_random_progress_message(language, config["name"])
                    progress.update('ai_request', 65 + (model_attempt * 5), random_message)
                
                # Make the request
                if stream:
                    response = self.g4f_client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        provider=self.provider,
                        stream=True
                    )
                else:
                    response = self.g4f_client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        provider=self.provider
                    )
                
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
            max_content_length = MAX_CONTENT_LENGTH
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
        """Standard summarization for content ≤ 20K characters"""
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
            else:
                template = LANGUAGE_TEMPLATES[detected_language]['webpage_template']
                prompt = template.format(content=content, title=title)

            # Check for cancellation before AI processing
            if progress and progress.is_cancelled():
                return {'success': False, 'error': 'Task cancelled by user'}
                
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
                # Attempt streaming with smart fallback
                response = self.make_ai_request_with_fallback(prompt, progress, 'en', stream=True)
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
                response = self.make_ai_request_with_fallback(prompt, progress, 'en', stream=False)
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

    def extract_content(self, url, return_summary=True, target_language=None, progress=None):
        """Extract and optionally summarize content from any webpage or PDF"""
        try:
            # Normalize URL
            url = self._normalize_url(url)
            
            # PDF detection (by extension)
            if url.lower().endswith('.pdf'):
                return self._process_pdf(url, return_summary, target_language, progress)
            
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
            return self._fallback_extraction(url, return_summary, target_language, progress)
            
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

    def _process_pdf(self, url, return_summary, target_language, progress):
        """Process PDF files"""
        print(f"Fetching PDF file from: {url}")
        resp = requests.get(url, stream=True, timeout=20)
        resp.raise_for_status()
        
        # Check content-type header as well
        if 'application/pdf' not in resp.headers.get('Content-Type', ''):
            raise Exception("URL does not point to a valid PDF file.")
        
        # Read PDF bytes in memory
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

    def _fallback_extraction(self, url, return_summary, target_language, progress):
        """Fallback extraction using requests-html"""
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
        domain = urlparse(url).netloc.lower()
        
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
                    return self._process_pdf_from_response(response, url, return_summary, target_language, progress)
                
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                if attempt == max_retries - 1:
                    print(f"⚠️ All {max_retries} attempts failed for {domain}")
                    raise Exception(f"Unable to access {domain}. The website may be temporarily unavailable or have strict access controls.")
                print(f"🔄 Attempt {attempt + 1} failed, retrying in {(attempt + 1) * 2} seconds...")
                import time
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
        
        raise Exception("Unable to extract meaningful content from this webpage")

    def _process_pdf_from_response(self, response, url, return_summary, target_language, progress):
        """Process PDF from HTTP response"""
        print("Detected PDF by content-type header.")
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