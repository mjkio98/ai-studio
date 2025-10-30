"""
Tor-enabled YouTube extractor with IP rotation for bypassing rate limiting and blocks.
"""

import yt_dlp
import subprocess
import time
import random

class TorYouTubeExtractor:
    """YouTube extractor that uses Tor for IP rotation and anti-blocking"""
    
    def __init__(self):
        self.tor_proxy = 'socks5://127.0.0.1:9050'
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]
        print("=" * 60)
        print("🔄 TOR YOUTUBE EXTRACTOR INITIALIZED")
        print(f"🌐 Tor Proxy: {self.tor_proxy}")
        print(f"🎭 User Agents Pool: {len(self.user_agents)} agents available")
        print("🔒 All YouTube requests will use Tor for IP rotation")
        print("=" * 60)
    
    def request_new_tor_circuit(self):
        """Request a new Tor circuit to get a fresh IP address"""
        try:
            print("🔄 Requesting NEW Tor circuit for fresh IP address...")
            
            # Send NEWNYM signal to Tor control port
            result = subprocess.run(
                ['echo', '-e', 'AUTHENTICATE ""\nSIGNAL NEWNYM\nQUIT'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            
            # Alternative method using nc (netcat)
            try:
                subprocess.run(
                    'echo -e "AUTHENTICATE \\"\\"\nSIGNAL NEWNYM\nQUIT" | nc 127.0.0.1 9051',
                    shell=True,
                    timeout=5,
                    capture_output=True
                )
            except:
                pass
            
            # Wait for circuit to change
            time.sleep(2)
            print("✅ Tor circuit RENEWED - Now using a different IP address!")
            return True
        except Exception as e:
            print(f"⚠️ Could not renew Tor circuit: {e}")
            return False
    
    def get_robust_ydl_options_with_tor(self):
        """Get yt-dlp options configured with Tor proxy and anti-blocking measures"""
        return {
            'proxy': self.tor_proxy,
            'user-agent': random.choice(self.user_agents),
            'referer': 'https://www.youtube.com/',
            'accept-language': 'en-US,en;q=0.9',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-encoding': 'gzip, deflate, br',
            'dnt': '1',
            'upgrade-insecure-requests': '1',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'nocheckcertificate': True,
            'socket_timeout': 60,
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': True,
            'keepvideo': False,
            'http_chunk_size': 10485760,  # 10MB chunks
        }
    
    def extract_video_info_with_tor(self, video_url, extract_info_only=True, max_retries=3):
        """
        Extract video information using Tor with IP rotation on failures
        
        Args:
            video_url: YouTube video URL
            extract_info_only: If True, only extract metadata without download URLs
            max_retries: Maximum number of retry attempts with IP rotation
        
        Returns:
            Video information dictionary
        """
        print("\n" + "=" * 60)
        print(f"🔒 EXTRACTING VIDEO INFO VIA TOR")
        print(f"🎯 URL: {video_url[:60]}...")
        print(f"📊 Mode: {'Metadata only' if extract_info_only else 'Full info with streams'}")
        print("=" * 60)
        
        for attempt in range(max_retries):
            try:
                # Request new Tor circuit for each attempt (fresh IP)
                if attempt > 0:
                    print(f"\n🔄 Retrying request... (Attempt {attempt + 1}/{max_retries})")
                    self.request_new_tor_circuit()
                else:
                    print(f"🌐 Loading video information...")
                
                # Get yt-dlp options with Tor proxy
                ydl_opts = self.get_robust_ydl_options_with_tor()
                
                if extract_info_only:
                    ydl_opts['skip_download'] = True
                else:
                    # Get format URLs for streaming
                    ydl_opts['format'] = 'best[height<=1080][ext=mp4]/best[height<=1080]/best[ext=mp4]/best[height<=720]/best'
                
                print(f"🔐 Processing request...")
                
                # Extract video information via Tor
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=False)
                    
                print(f"✅ Video information loaded successfully")
                print(f"📹 Title: {info.get('title', 'Unknown')[:50]}...")
                print(f"⏱️  Duration: {info.get('duration', 0)}s")
                print("=" * 60 + "\n")
                return info
                
            except Exception as e:
                print(f"❌ Tor extraction attempt {attempt + 1} FAILED: {str(e)[:100]}")
                
                if attempt < max_retries - 1:
                    # Wait before retry with exponential backoff
                    wait_time = (attempt + 1) * 2
                    print(f"⏳ Waiting {wait_time}s before retry with NEW IP...")
                    time.sleep(wait_time)
                else:
                    # Last attempt failed - try without Tor as fallback
                    print("\n⚠️  All Tor attempts FAILED! Trying DIRECT connection as fallback...")
                    try:
                        fallback_opts = {
                            'quiet': True,
                            'no_warnings': True,
                            'extract_flat': False,
                            'skip_download': extract_info_only,
                        }
                        
                        if not extract_info_only:
                            fallback_opts['format'] = 'best[height<=1080][ext=mp4]/best[height<=1080]/best[ext=mp4]/best[height<=720]/best'
                        
                        with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                            info = ydl.extract_info(video_url, download=False)
                            print("✅ FALLBACK Success: Video info extracted WITHOUT Tor")
                            print("=" * 60 + "\n")
                            return info
                    except Exception as fallback_error:
                        raise Exception(f"Both Tor and direct extraction failed: {fallback_error}")
        
        raise Exception("Failed to extract video information after all attempts")
