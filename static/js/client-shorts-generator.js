/**
 * Client-Side Shorts Generator
 * 
 * Main orchestrator for generating YouTube Shorts entirely in the browser.
 * Handles the full pipeline: AI analysis → segment loading → processing → export
 */

class ClientSideShortsGenerator {
    constructor() {
        this.videoProcessor = null;
        this.faceDetector = null;
        this.isProcessing = false;
        this.currentProgress = 0;
        this.processedClips = [];
    }

    /**
     * Initialize the shorts generator
     */
    async initialize() {
        console.log('🎬 Initializing client-side shorts generator...');

        // Initialize video processor
        if (typeof clientVideoProcessor !== 'undefined') {
            this.videoProcessor = clientVideoProcessor;
            console.log('⏳ Initializing video processor with FFmpeg...');
            await this.videoProcessor.initialize();
            console.log('✅ Video processor initialized');
        } else {
            throw new Error('Client video processor not available');
        }

        // Initialize face detector
        if (typeof faceDetector !== 'undefined') {
            this.faceDetector = faceDetector;
            console.log('⏳ Initializing face detector...');
            await this.faceDetector.initialize();
            console.log('✅ Face detector initialized');
        }

        console.log('✅ Shorts generator ready');
    }

    /**
     * Generate shorts from a YouTube video
     * @param {string} youtubeUrl - YouTube video URL
     * @param {Function} progressCallback - Progress updates
     * @param {Function} clipReadyCallback - Called when each clip is ready
     * @param {string} language - Language for transcription ('auto', 'en', 'ar', etc.)
     * @returns {Promise<Array>} Array of processed clips with download URLs
     */
    async generateShorts(youtubeUrl, progressCallback = null, clipReadyCallback = null, language = 'auto') {
        if (this.isProcessing) {
            throw new Error('Already processing a video');
        }

        this.isProcessing = true;
        this.processedClips = [];

        try {
            // Step 1: Get video stream URL and metadata
            this.updateProgress(progressCallback, 5, 'Getting video information...');
            
            const videoInfo = await this.getVideoStreamInfo(youtubeUrl);
            
            // Step 2: Extract captions/transcripts (server-side)
            this.updateProgress(progressCallback, 15, 'Extracting captions...');
            
            const captions = await this.extractCaptions(youtubeUrl);
            console.log(`📝 Extracted captions: ${captions?.length || 0} segments`);
            if (captions && captions.length > 0) {
                console.log(`📝 First caption: "${captions[0].text}" (${captions[0].start}s-${captions[0].end || captions[0].start + captions[0].duration}s)`);
                console.log(`📝 Caption structure:`, captions[0]);
            }
            
            // Auto-detect language from captions if needed
            console.log(`🔍 Language detection check: language='${language}', captions=${captions?.length || 0}`);
            
            if (language === 'auto' && captions && captions.length > 0) {
                // Analyze first few captions to detect language
                let totalText = '';
                const samplesToCheck = Math.min(10, captions.length); // Check first 10 captions
                for (let i = 0; i < samplesToCheck; i++) {
                    totalText += captions[i].text + ' ';
                }
                
                console.log(`🔍 Sample text for analysis: "${totalText.substring(0, 100)}..."`);
                
                // Count Arabic vs English characters
                let arabicChars = 0;
                let englishChars = 0;
                let totalChars = 0;
                
                for (const char of totalText) {
                    if (char.match(/[A-Za-z]/)) {
                        englishChars++;
                        totalChars++;
                    } else if (char.match(/[\u0600-\u06FF\u0750-\u077F]/)) {
                        arabicChars++;
                        totalChars++;
                    }
                }
                
                console.log(`🔍 Character analysis: Arabic=${arabicChars}, English=${englishChars}, Total=${totalChars}`);
                
                if (totalChars > 0) {
                    const arabicRatio = arabicChars / totalChars;
                    const englishRatio = englishChars / totalChars;
                    
                    if (arabicRatio > 0.25) { // If more than 25% Arabic characters
                        language = 'ar';
                        console.log(`🔍 ✅ Auto-detected Arabic language: ${(arabicRatio * 100).toFixed(1)}% Arabic, ${(englishRatio * 100).toFixed(1)}% English`);
                    } else {
                        language = 'en';
                        console.log(`🔍 ✅ Auto-detected English language: ${(arabicRatio * 100).toFixed(1)}% Arabic, ${(englishRatio * 100).toFixed(1)}% English`);
                    }
                } else {
                    language = 'en'; // Default fallback
                    console.log(`🔍 ❌ No text found for language detection, defaulting to English`);
                }
            } else if (language !== 'auto') {
                console.log(`🔍 ⏭️  Skipping auto-detection - language already set to: ${language}`);
            } else {
                console.log(`🔍 ❌ Cannot auto-detect - no captions available`);
            }
            
            console.log(`🌐 Final language for shorts generation: ${language}`);
            
            // Step 3: AI analysis to find best segments (server-side)
            this.updateProgress(progressCallback, 30, 'AI analyzing content...');
            
            const clipsAnalysis = await this.analyzeForShorts(captions, videoInfo.duration);
            
            // Determine number of clips to generate
            const clipsToGenerate = this.determineClipCount(videoInfo.duration, clipsAnalysis.clips);
            
            console.log(`🎬 Will generate ${clipsToGenerate.length} shorts from ${videoInfo.duration.toFixed(0)}s video`);
            
            // Step 4: Process each clip (client-side)
            const totalClips = clipsToGenerate.length;
            
            for (let i = 0; i < totalClips; i++) {
                const clip = clipsToGenerate[i];
                const clipNum = i + 1;
                
                this.updateProgress(
                    progressCallback,
                    30 + (i / totalClips) * 60,
                    `Creating clip ${clipNum}/${totalClips}...`
                );
                
                try {
                    // Process this clip in the browser with captions
                    console.log(`🌐 Processing clip ${clipNum} with language: ${language}`);
                    const processedBlob = await this.videoProcessor.processClip(
                        clip,
                        videoInfo.streamUrl,
                        captions, // Pass full timestamped transcript
                        (clipProgress, message) => {
                            const overallProgress = 30 + ((i + clipProgress / 100) / totalClips) * 60;
                            this.updateProgress(
                                progressCallback,
                                overallProgress,
                                `Clip ${clipNum}/${totalClips}: Creating...`
                            );
                        },
                        language // Pass the language parameter for transcription
                    );
                    
                    // Create download URL for this clip
                    const downloadUrl = URL.createObjectURL(processedBlob);
                    
                    const processedClip = {
                        ...clip,
                        blob: processedBlob,
                        downloadUrl,
                        size: processedBlob.size,
                        ready: true
                    };
                    
                    this.processedClips.push(processedClip);
                    
                    // Notify that this clip is ready
                    if (clipReadyCallback) {
                        clipReadyCallback(processedClip, clipNum, totalClips);
                    }
                    
                } catch (clipError) {
                    console.error(`❌ Failed to process clip ${clipNum}:`, clipError);
                    // Continue with other clips even if one fails
                }
            }
            
            // Step 5: Complete
            this.updateProgress(progressCallback, 100, 'All clips ready!');
            
            return this.processedClips;
            
        } catch (error) {
            console.error('❌ Shorts generation failed:', error);
            throw error;
        } finally {
            this.isProcessing = false;
        }
    }

    /**
     * Get video stream URL using yt-dlp (server-side helper)
     */
    async getVideoStreamInfo(youtubeUrl) {
        const response = await fetch('/api/get-video-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: youtubeUrl })
        });

        if (!response.ok) {
            throw new Error('Failed to get video stream info');
        }

        return await response.json();
    }

    /**
     * Extract captions/transcripts (server-side)
     */
    async extractCaptions(youtubeUrl) {
        const response = await fetch('/api/extract-captions-only', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: youtubeUrl })
        });

        if (!response.ok) {
            throw new Error('Failed to extract captions');
        }

        const data = await response.json();
        return data.captions;
    }

    /**
     * Analyze content for best shorts segments (server-side AI)
     */
    async analyzeForShorts(captions, duration) {
        const response = await fetch('/api/analyze-for-shorts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                captions,
                duration
            })
        });

        if (!response.ok) {
            throw new Error('Failed to analyze content');
        }

        return await response.json();
    }

    /**
     * Determine how many clips to generate based on video duration
     */
    determineClipCount(videoDuration, suggestedClips) {
        // Rule: If video < 60s, generate 1 short
        if (videoDuration < 60) {
            console.log('📝 Short video (<60s) - generating 1 clip');
            return suggestedClips.slice(0, 1);
        }

        // Rule: For longer videos, generate up to 5 shorts
        // Each short should be 30-45 seconds
        const maxClips = Math.min(5, suggestedClips.length);
        
        console.log(`📝 Long video (${videoDuration.toFixed(0)}s) - generating up to ${maxClips} clips`);
        
        return suggestedClips.slice(0, maxClips);
    }

    /**
     * Update progress callback
     */
    updateProgress(callback, percentage, message) {
        this.currentProgress = percentage;
        if (callback) {
            callback(percentage, message);
        }
    }

    /**
     * Cancel current processing
     */
    cancel() {
        this.isProcessing = false;
        console.log('🛑 Shorts generation cancelled');
    }

    /**
     * Cleanup resources
     */
    dispose() {
        // Revoke all download URLs
        if (this.processedClips && Array.isArray(this.processedClips)) {
            this.processedClips.forEach(clip => {
                if (clip.downloadUrl) {
                    try {
                        URL.revokeObjectURL(clip.downloadUrl);
                    } catch (error) {
                        console.warn('⚠️ Error revoking URL:', error);
                    }
                }
            });
        }

        this.processedClips = [];

        if (this.videoProcessor && typeof this.videoProcessor.dispose === 'function') {
            try {
                this.videoProcessor.dispose();
            } catch (error) {
                console.warn('⚠️ Error disposing video processor:', error);
            }
        }

        if (this.faceDetector && typeof this.faceDetector.dispose === 'function') {
            try {
                this.faceDetector.dispose();
            } catch (error) {
                console.warn('⚠️ Error disposing face detector:', error);
            }
        }
    }
}

// Create singleton instance
const shortsGenerator = new ClientSideShortsGenerator();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = shortsGenerator;
}
