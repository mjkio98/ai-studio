/**
 * Client-Side Video Segment Loader
 * 
 * Efficiently loads specific video segments using HTTP range requests
 * or blob slicing to avoid downloading the full video file.
 */

class VideoSegmentLoader {
    constructor() {
        this.cache = new Map();
        this.maxCacheSize = 100 * 1024 * 1024; // 100MB cache limit
        this.currentCacheSize = 0;
    }

    /**
     * Load a specific segment of a YouTube video
     * @param {string} videoUrl - YouTube video URL
     * @param {number} startTime - Start time in seconds
     * @param {number} endTime - End time in seconds
     * @param {Function} progressCallback - Progress update callback
     * @returns {Promise<Blob>} Video segment as blob
     */
    async loadSegment(videoUrl, startTime, endTime, progressCallback = null) {
        const cacheKey = `${videoUrl}-${startTime}-${endTime}`;
        
        // Check cache first
        if (this.cache.has(cacheKey)) {
            console.log(`✅ Using cached segment: ${startTime}s - ${endTime}s`);
            return this.cache.get(cacheKey);
        }

        console.log(`📥 Preparing video content...`);

        try {
            // Use server-side proxy to get the segment
            // This bypasses CORS and only downloads the needed 30-60s segment
            const segment = await this.loadViaProxy(
                videoUrl,
                startTime,
                endTime,
                progressCallback
            );

            // Cache the segment
            this.cacheSegment(cacheKey, segment);

            return segment;

        } catch (error) {
            console.error('❌ Failed to load segment via proxy:', error);
            throw error;
        }
    }

    /**
     * Load video segment using server-side proxy
     * This bypasses CORS and only downloads the requested segment
     */
    async loadViaProxy(videoUrl, startTime, endTime, progressCallback) {
        console.log(`🔄 Processing video...`);
        
        if (progressCallback) {
            progressCallback(10, 'Loading content...');
        }

        const response = await fetch('/api/proxy-video-segment', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: videoUrl,
                startTime,
                endTime
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load segment');
        }

        if (progressCallback) {
            progressCallback(50, 'Receiving video data...');
        }

        // Get the video blob from the proxy
        const blob = await response.blob();
        
        console.log(`✅ Content ready`);
        
        if (progressCallback) {
            progressCallback(100, 'Ready!');
        }

        return blob;
    }

    /**
     * Load video segment using HTTP range requests
     */
    async loadWithRangeRequest(videoUrl, startTime, endTime, progressCallback) {
        // First, get video metadata to calculate byte ranges
        const metadata = await this.getVideoMetadata(videoUrl);
        
        if (!metadata.supportsRangeRequests) {
            throw new Error('Server does not support range requests');
        }

        // Calculate approximate byte range based on bitrate
        const duration = endTime - startTime;
        const bitrate = metadata.bitrate || 2000000; // Default 2Mbps
        const estimatedBytes = (bitrate * duration) / 8;
        
        // Add buffer for keyframes
        const bufferBytes = estimatedBytes * 0.2;
        const startByte = Math.max(0, Math.floor((startTime / metadata.duration) * metadata.fileSize) - bufferBytes);
        const endByte = Math.min(metadata.fileSize, startByte + estimatedBytes + bufferBytes * 2);

        console.log(`📊 Byte range: ${startByte} - ${endByte} (${this.formatBytes(endByte - startByte)})`);

        // Download the byte range
        const response = await fetch(videoUrl, {
            headers: {
                'Range': `bytes=${startByte}-${endByte}`
            }
        });

        if (!response.ok) {
            throw new Error(`Range request failed: ${response.status}`);
        }

        // Read the response with progress tracking
        return await this.readResponseWithProgress(response, progressCallback);
    }

    /**
     * Load full video and extract segment (fallback)
     */
    async loadWithExtraction(videoUrl, startTime, endTime, progressCallback) {
        console.log('📥 Loading full video for segment extraction...');
        
        // Create video element to load the source
        const video = document.createElement('video');
        video.crossOrigin = 'anonymous';
        video.preload = 'auto';
        
        // Load video
        video.src = videoUrl;
        
        await new Promise((resolve, reject) => {
            video.onloadedmetadata = resolve;
            video.onerror = reject;
        });

        console.log(`📹 Video loaded: ${video.duration.toFixed(1)}s, ${video.videoWidth}x${video.videoHeight}`);

        // This approach requires MediaRecorder to extract the segment
        // We'll handle this in the video processor
        return { video, startTime, endTime, type: 'video-element' };
    }

    /**
     * Get video metadata (duration, file size, bitrate)
     */
    async getVideoMetadata(videoUrl) {
        try {
            // Try HEAD request to get content length and accept ranges
            const response = await fetch(videoUrl, { method: 'HEAD' });
            
            const fileSize = parseInt(response.headers.get('content-length') || '0');
            const supportsRangeRequests = response.headers.get('accept-ranges') === 'bytes';

            // Get duration from video element
            const video = document.createElement('video');
            video.src = videoUrl;
            
            await new Promise((resolve, reject) => {
                video.onloadedmetadata = resolve;
                video.onerror = reject;
                setTimeout(() => reject(new Error('Metadata load timeout')), 10000);
            });

            const duration = video.duration;
            const bitrate = fileSize > 0 && duration > 0 ? (fileSize * 8) / duration : null;

            return {
                duration,
                fileSize,
                bitrate,
                supportsRangeRequests,
                width: video.videoWidth,
                height: video.videoHeight
            };

        } catch (error) {
            console.error('❌ Failed to get video metadata:', error);
            return {
                duration: 0,
                fileSize: 0,
                bitrate: null,
                supportsRangeRequests: false
            };
        }
    }

    /**
     * Read response with progress tracking
     */
    async readResponseWithProgress(response, progressCallback) {
        const reader = response.body.getReader();
        const contentLength = parseInt(response.headers.get('content-length') || '0');
        
        let receivedLength = 0;
        const chunks = [];

        while (true) {
            const { done, value } = await reader.read();

            if (done) break;

            chunks.push(value);
            receivedLength += value.length;

            if (progressCallback && contentLength) {
                progressCallback((receivedLength / contentLength) * 100);
            }
        }

        // Combine chunks into single blob
        const blob = new Blob(chunks, { type: 'video/mp4' });
        
        console.log(`✅ Content ready`);
        
        return blob;
    }

    /**
     * Cache a video segment
     */
    cacheSegment(key, data) {
        const dataSize = data.size || (data.video ? 0 : 0);

        // Check cache size limit
        if (this.currentCacheSize + dataSize > this.maxCacheSize) {
            this.clearOldestCacheEntries(dataSize);
        }

        this.cache.set(key, data);
        this.currentCacheSize += dataSize;
    }

    /**
     * Clear oldest cache entries to make space
     */
    clearOldestCacheEntries(spaceNeeded) {
        const entries = Array.from(this.cache.entries());
        let freedSpace = 0;

        for (const [key, value] of entries) {
            const entrySize = value.size || 0;
            this.cache.delete(key);
            freedSpace += entrySize;
            this.currentCacheSize -= entrySize;

            if (freedSpace >= spaceNeeded) {
                break;
            }
        }

        console.log(`🧹 Cleared ${this.formatBytes(freedSpace)} from cache`);
    }

    /**
     * Format bytes to human-readable string
     */
    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
    }

    /**
     * Clear all cached segments
     */
    clearCache() {
        this.cache.clear();
        this.currentCacheSize = 0;
        console.log('🧹 Cache cleared');
    }

    /**
     * Get cache statistics
     */
    getCacheStats() {
        return {
            entries: this.cache.size,
            size: this.currentCacheSize,
            sizeFormatted: this.formatBytes(this.currentCacheSize),
            maxSize: this.maxCacheSize,
            maxSizeFormatted: this.formatBytes(this.maxCacheSize)
        };
    }
}

// Create singleton instance
const videoSegmentLoader = new VideoSegmentLoader();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = videoSegmentLoader;
}
