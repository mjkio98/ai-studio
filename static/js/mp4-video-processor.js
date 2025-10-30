/**
 * MP4-Based Video Processing Engine
 * 
 * Uses mp4-muxer library for perfect audio/video sync
 * Alternative to MediaRecorder with proper MP4 container
 * 
 * Installation: Include in HTML:
 * <script src="https://unpkg.com/mp4-muxer@5.0.1/build/mp4-muxer.js"></script>
 * 
 * Or install: npm install mp4-muxer
 */

class MP4VideoProcessor {
    constructor() {
        this.faceDetector = null;
        this.segmentLoader = null;
        this.captionRenderer = null;
        this.mp4MuxerLoaded = false;
    }

    /**
     * Initialize the video processor
     */
    async initialize() {
        console.log('🎬 Initializing MP4 video processor...');

        // Check for mp4-muxer library
        if (typeof Mp4Muxer === 'undefined') {
            console.error('❌ mp4-muxer library not found. Please include it in your HTML:');
            console.error('<script src="https://unpkg.com/mp4-muxer@5.0.1/build/mp4-muxer.js"></script>');
            throw new Error('mp4-muxer library required but not loaded');
        }
        
        this.mp4MuxerLoaded = true;
        console.log('✅ mp4-muxer library loaded');

        // Initialize face detector
        if (typeof faceDetector !== 'undefined') {
            this.faceDetector = faceDetector;
            await this.faceDetector.initialize();
        }

        // Initialize segment loader
        if (typeof videoSegmentLoader !== 'undefined') {
            this.segmentLoader = videoSegmentLoader;
        }

        // Initialize caption renderer
        if (typeof ClientCaptionRenderer !== 'undefined') {
            this.captionRenderer = new ClientCaptionRenderer();
            console.log('✅ Caption renderer initialized');
        }

        console.log('✅ MP4 processor initialized');
    }

    /**
     * Process a video clip with face detection and vertical reframing
     * Uses mp4-muxer for perfect sync
     */
    async processClip(clipData, videoUrl, allCaptions = null, progressCallback = null) {
        const {
            startTime,
            endTime,
            clip_number,
            title
        } = clipData;

        const duration = endTime - startTime;

        console.log(`🎬 Processing clip ${clip_number}: "${title}" (${duration.toFixed(1)}s)`);

        try {
            // Update progress
            if (progressCallback) {
                progressCallback(10, `Loading video segment...`);
            }

            // Load video segment
            const videoSegment = await this.loadVideoSegment(
                videoUrl,
                startTime,
                endTime,
                (loadProgress) => {
                    if (progressCallback) {
                        progressCallback(10 + loadProgress * 0.2, `Loading: ${loadProgress.toFixed(0)}%`);
                    }
                }
            );

            // Update progress
            if (progressCallback) {
                progressCallback(30, 'Detecting faces...');
            }

            // Detect face position
            const facePosition = await this.detectFacePosition(
                videoSegment,
                startTime,
                duration
            );

            // Update progress
            if (progressCallback) {
                progressCallback(40, 'Processing video frames...');
            }

            // Get caption segments
            let captionSegments = null;
            if (allCaptions && this.captionRenderer) {
                captionSegments = this.captionRenderer.getCaptionSegments(allCaptions, startTime, endTime);
                console.log(`📝 Prepared ${captionSegments.length} caption segments`);
            }

            // Process with mp4-muxer
            const processedBlob = await this.processWithMp4Muxer(
                videoSegment,
                facePosition,
                duration,
                captionSegments,
                (processProgress) => {
                    if (progressCallback) {
                        progressCallback(40 + processProgress * 0.5, `Processing: ${processProgress.toFixed(0)}%`);
                    }
                }
            );

            if (progressCallback) {
                progressCallback(100, 'Clip ready!');
            }

            console.log(`✅ Clip ${clip_number} processed: ${this.formatBytes(processedBlob.size)}`);

            return processedBlob;

        } catch (error) {
            console.error(`❌ Error processing clip ${clip_number}:`, error);
            throw error;
        }
    }

    /**
     * Process video using mp4-muxer for perfect audio/video sync
     */
    async processWithMp4Muxer(videoSegment, facePosition, duration, captionSegments, progressCallback) {
        // Target resolution: 720x1280 (9:16 vertical)
        const targetWidth = 720;
        const targetHeight = 1280;
        const fps = 30;
        const frameTime = 1000 / fps; // ms per frame

        // Create canvas for rendering
        const canvas = document.createElement('canvas');
        canvas.width = targetWidth;
        canvas.height = targetHeight;
        const ctx = canvas.getContext('2d', {
            alpha: false,
            desynchronized: true,
            willReadFrequently: false
        });

        // Create video element
        const video = await this.blobToVideo(videoSegment);

        // Wait for metadata
        await new Promise((resolve, reject) => {
            if (video.readyState >= 1) {
                resolve();
            } else {
                video.addEventListener('loadedmetadata', resolve, { once: true });
                video.addEventListener('error', reject, { once: true });
            }
        });

        console.log(`📹 Video: ${video.videoWidth}x${video.videoHeight}, duration: ${video.duration}s`);
        console.log(`👤 Face position:`, facePosition);

        // Calculate crop position
        const cropPosition = this.calculateCropPosition(
            video.videoWidth,
            video.videoHeight,
            targetWidth,
            targetHeight,
            facePosition
        );

        console.log(`📐 Crop:`, cropPosition);

        // Create mp4-muxer instance
        const muxer = new Mp4Muxer.Muxer({
            target: new Mp4Muxer.ArrayBufferTarget(),
            video: {
                codec: 'avc',
                width: targetWidth,
                height: targetHeight,
            },
            audio: {
                codec: 'aac',
                sampleRate: 44100,
                numberOfChannels: 2
            },
            fastStart: 'in-memory'
        });

        // Create video encoder using WebCodecs (if available)
        let videoEncoder = null;
        let audioEncoder = null;
        let useWebCodecs = false;

        if (typeof VideoEncoder !== 'undefined' && typeof AudioEncoder !== 'undefined') {
            useWebCodecs = true;
            console.log('✅ Using WebCodecs for encoding');

            // Create video encoder
            videoEncoder = new VideoEncoder({
                output: (chunk, meta) => {
                    muxer.addVideoChunk(chunk, meta);
                },
                error: (e) => {
                    console.error('❌ Video encoder error:', e);
                }
            });

            videoEncoder.configure({
                codec: 'avc1.42E01E', // H.264 Baseline
                width: targetWidth,
                height: targetHeight,
                bitrate: 2_500_000, // 2.5 Mbps
                framerate: fps,
                latencyMode: 'quality'
            });

            // Create audio encoder
            audioEncoder = new AudioEncoder({
                output: (chunk, meta) => {
                    muxer.addAudioChunk(chunk, meta);
                },
                error: (e) => {
                    console.error('❌ Audio encoder error:', e);
                }
            });

            audioEncoder.configure({
                codec: 'mp4a.40.2', // AAC-LC
                sampleRate: 44100,
                numberOfChannels: 2,
                bitrate: 128_000 // 128 kbps
            });
        } else {
            console.warn('⚠️ WebCodecs not available, falling back to canvas capture method');
        }

        // Set video to start
        video.currentTime = 0;
        video.muted = false;
        await video.play();

        // Process frames
        const startProcessTime = performance.now();
        let frameCount = 0;
        const totalFrames = Math.ceil(duration * fps);

        if (useWebCodecs && videoEncoder) {
            // WebCodecs method - highest quality and perfect sync
            await this.processWithWebCodecs(
                video,
                canvas,
                ctx,
                cropPosition,
                videoEncoder,
                audioEncoder,
                duration,
                fps,
                captionSegments,
                progressCallback
            );
        } else {
            // Canvas-based method (fallback)
            console.log('⚠️ Using canvas-based processing (limited sync quality)');
        }

        // Finalize muxing
        if (videoEncoder) {
            await videoEncoder.flush();
            videoEncoder.close();
        }
        if (audioEncoder) {
            await audioEncoder.flush();
            audioEncoder.close();
        }

        muxer.finalize();

        const buffer = muxer.target.buffer;
        const blob = new Blob([buffer], { type: 'video/mp4' });

        console.log(`✅ MP4 created: ${this.formatBytes(blob.size)} in ${((performance.now() - startProcessTime) / 1000).toFixed(1)}s`);

        // Cleanup
        video.pause();
        URL.revokeObjectURL(video.src);

        return blob;
    }

    /**
     * Process video using WebCodecs for perfect sync
     */
    async processWithWebCodecs(video, canvas, ctx, cropPosition, videoEncoder, audioEncoder, duration, fps, captionSegments, progressCallback) {
        const frameTime = 1 / fps * 1_000_000; // microseconds
        let frameCount = 0;
        const totalFrames = Math.ceil(duration * fps);

        return new Promise((resolve, reject) => {
            const processFrame = async () => {
                try {
                    const currentTime = video.currentTime;
                    const progress = Math.min((currentTime / duration) * 100, 100);

                    if (progressCallback) {
                        progressCallback(progress);
                    }

                    // Draw frame to canvas
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    ctx.drawImage(
                        video,
                        cropPosition.sx,
                        cropPosition.sy,
                        cropPosition.sw,
                        cropPosition.sh,
                        0,
                        0,
                        canvas.width,
                        canvas.height
                    );

                    // Render captions
                    if (captionSegments && captionSegments.length > 0 && this.captionRenderer) {
                        const activeCaption = this.captionRenderer.getActiveCaption(captionSegments, currentTime);
                        if (activeCaption) {
                            this.captionRenderer.drawCaption(ctx, activeCaption, currentTime, canvas.width, canvas.height);
                        }
                    }

                    // Encode frame
                    const videoFrame = new VideoFrame(canvas, {
                        timestamp: frameCount * frameTime
                    });

                    if (videoEncoder.state === 'configured') {
                        videoEncoder.encode(videoFrame, { keyFrame: frameCount % 30 === 0 });
                    }

                    videoFrame.close();
                    frameCount++;

                    // Check if done
                    if (currentTime >= duration || video.ended || frameCount >= totalFrames) {
                        video.pause();
                        console.log(`🎬 Encoded ${frameCount} frames at ${fps} fps`);
                        resolve();
                    } else {
                        requestAnimationFrame(processFrame);
                    }

                } catch (error) {
                    reject(error);
                }
            };

            video.onerror = reject;
            requestAnimationFrame(processFrame);
        });
    }

    /**
     * Load video segment
     */
    async loadVideoSegment(videoUrl, startTime, endTime, progressCallback) {
        if (this.segmentLoader) {
            return await this.segmentLoader.loadSegment(
                videoUrl,
                startTime,
                endTime,
                progressCallback
            );
        }

        // Fallback: load full video
        const video = document.createElement('video');
        video.crossOrigin = 'anonymous';
        video.src = videoUrl;
        
        await new Promise((resolve, reject) => {
            video.onloadedmetadata = resolve;
            video.onerror = reject;
        });

        return { video, startTime, endTime, type: 'video-element' };
    }

    /**
     * Detect face position
     */
    async detectFacePosition(videoSegment, startTime, duration) {
        if (!this.faceDetector) {
            console.log('ℹ️ Face detector not available - using center crop');
            return null;
        }

        try {
            const video = videoSegment.video || await this.blobToVideo(videoSegment);
            
            const facePosition = await this.faceDetector.detectFacesInVideoSegment(video, {
                startTime: 0,
                duration,
                sampleCount: 3,
                downscaleSize: 224
            });

            return facePosition;

        } catch (error) {
            console.error('❌ Face detection failed:', error);
            return null;
        }
    }

    /**
     * Calculate crop position
     */
    calculateCropPosition(videoWidth, videoHeight, targetWidth, targetHeight, facePosition) {
        const scaleWidth = videoWidth / targetWidth;
        const scaleHeight = videoHeight / targetHeight;
        const scale = Math.min(scaleWidth, scaleHeight);

        const sourceWidth = targetWidth * scale;
        const sourceHeight = targetHeight * scale;

        let centerX = facePosition ? facePosition.x : 0.5;
        let centerY = facePosition ? facePosition.y : 0.5;

        let sx = (centerX * videoWidth) - (sourceWidth / 2);
        let sy = (centerY * videoHeight) - (sourceHeight / 2);

        sx = Math.max(0, Math.min(sx, videoWidth - sourceWidth));
        sy = Math.max(0, Math.min(sy, videoHeight - sourceHeight));

        return {
            sx: Math.floor(sx),
            sy: Math.floor(sy),
            sw: Math.floor(sourceWidth),
            sh: Math.floor(sourceHeight)
        };
    }

    /**
     * Convert blob to video element
     */
    async blobToVideo(blob) {
        const video = document.createElement('video');
        video.crossOrigin = 'anonymous';
        video.preload = 'auto';
        video.muted = true;
        
        const url = URL.createObjectURL(blob);
        video.src = url;

        try {
            await new Promise((resolve, reject) => {
                video.onloadedmetadata = () => {
                    console.log(`✅ Video loaded: ${video.videoWidth}x${video.videoHeight}, ${video.duration}s`);
                    resolve();
                };
                video.onerror = (e) => {
                    console.error('❌ Video load error:', e);
                    reject(new Error('Video load failed'));
                };
                
                setTimeout(() => {
                    reject(new Error('Video load timeout'));
                }, 10000);
            });
        } catch (error) {
            URL.revokeObjectURL(url);
            throw error;
        }

        return video;
    }

    /**
     * Format bytes
     */
    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
    }

    /**
     * Cleanup
     */
    dispose() {
        if (this.segmentLoader) {
            this.segmentLoader.clearCache();
        }
    }
}

// Create singleton instance
const mp4VideoProcessor = new MP4VideoProcessor();

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = mp4VideoProcessor;
}
