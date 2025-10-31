/**
 * Client-Side Face Detection Module
 * 
 * Uses TensorFlow.js with BlazeFace model for lightweight face detection in browser.
 * Optimized for real-time performance without blocking the UI.
 */

class FaceDetector {
    constructor() {
        this.model = null;
        this.isLoading = false;
        this.isLoaded = false;
        this.worker = null;
    }

    /**
     * Initialize TensorFlow.js and load BlazeFace model
     */
    async initialize() {
        if (this.isLoaded) {
            return true;
        }

        if (this.isLoading) {
            // Wait for existing load to complete
            return await this.waitForLoad();
        }

        this.isLoading = true;

        try {
            console.log('🔍 Initializing TensorFlow.js BlazeFace model...');
            
            // Load TensorFlow.js and BlazeFace if not already loaded
            if (typeof tf === 'undefined') {
                await this.loadScript('https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.11.0/dist/tf.min.js');
            }
            
            if (typeof blazeface === 'undefined') {
                await this.loadScript('https://cdn.jsdelivr.net/npm/@tensorflow-models/blazeface@0.0.7/dist/blazeface.js');
            }

            // Set backend to WebGL for performance
            await tf.setBackend('webgl');
            await tf.ready();

            // Load BlazeFace model (quantized for smaller size)
            this.model = await blazeface.load();
            
            this.isLoaded = true;
            this.isLoading = false;
            
            console.log('✅ BlazeFace model loaded successfully');
            return true;
            
        } catch (error) {
            console.error('❌ Failed to load BlazeFace model:', error);
            this.isLoading = false;
            return false;
        }
    }

    /**
     * Load external script dynamically
     */
    loadScript(src) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    /**
     * Wait for model to finish loading
     */
    async waitForLoad() {
        return new Promise((resolve) => {
            const checkInterval = setInterval(() => {
                if (this.isLoaded) {
                    clearInterval(checkInterval);
                    resolve(true);
                } else if (!this.isLoading) {
                    clearInterval(checkInterval);
                    resolve(false);
                }
            }, 100);
        });
    }

    /**
     * Detect faces in a video frame
     * @param {HTMLVideoElement|HTMLCanvasElement|ImageData} input - Video element, canvas, or image data
     * @param {Object} options - Detection options
     * @returns {Promise<Array>} Array of face predictions with bounding boxes
     */
    async detectFaces(input, options = {}) {
        if (!this.isLoaded) {
            await this.initialize();
        }

        if (!this.model) {
            throw new Error('BlazeFace model not loaded');
        }

        try {
            // Detect faces with optional parameters
            const predictions = await this.model.estimateFaces(input, {
                flipHorizontal: options.flipHorizontal || false,
                returnTensors: false
            });

            return predictions;
            
        } catch (error) {
            console.error('❌ Face detection error:', error);
            return [];
        }
    }

    /**
     * Sample frames from video and detect faces
     * @param {HTMLVideoElement} video - Video element
     * @param {Object} options - Sampling options
     * @returns {Promise<Object>} Face position data
     */
    async detectFacesInVideoSegment(video, options = {}) {
        const {
            startTime = 0,
            duration = 5,
            sampleCount = 3,
            downscaleSize = 224
        } = options;

        console.log(`🔍 Detecting faces: ${sampleCount} samples over ${duration}s`);

        try {
            // Create canvas for frame extraction
            const canvas = document.createElement('canvas');
            canvas.width = downscaleSize;
            canvas.height = downscaleSize;
            const ctx = canvas.getContext('2d');

            const facePositions = [];
            const sampleInterval = duration / sampleCount;

            // Sample frames at intervals
            for (let i = 0; i < sampleCount; i++) {
                const sampleTime = startTime + (i * sampleInterval);
                
                // Seek to sample time
                video.currentTime = sampleTime;
                
                // Wait for seek to complete
                await new Promise(resolve => {
                    video.onseeked = resolve;
                    // Also resolve if already at position
                    setTimeout(resolve, 100);
                });
                
                // Ensure video has valid dimensions
                if (!video.videoWidth || !video.videoHeight) {
                    console.warn(`⚠️ Video has invalid dimensions at frame ${i + 1}`);
                    continue;
                }

                // Draw frame to canvas (downscaled for faster detection)
                ctx.drawImage(video, 0, 0, downscaleSize, downscaleSize);

                // Detect faces in this frame
                const predictions = await this.detectFaces(canvas);

                if (predictions && predictions.length > 0) {
                    // Take the largest face (most likely main subject)
                    const largestFace = predictions.reduce((largest, face) => {
                        const faceSize = this.getFaceSize(face);
                        const largestSize = this.getFaceSize(largest);
                        return faceSize > largestSize ? face : largest;
                    }, predictions[0]);

                    // Get normalized face position
                    const faceCenter = this.getFaceCenter(largestFace, downscaleSize, downscaleSize);
                    
                    // Validate face center values
                    if (isNaN(faceCenter.x) || isNaN(faceCenter.y)) {
                        console.warn(`⚠️ Invalid face center at frame ${i + 1}:`, largestFace);
                        continue;
                    }
                    
                    facePositions.push(faceCenter);

                    console.log(`   📍 Frame ${i + 1}: Face at (${faceCenter.x.toFixed(2)}, ${faceCenter.y.toFixed(2)})`);
                } else {
                    console.log(`   ℹ️ Frame ${i + 1}: No faces detected`);
                }
            }

            if (facePositions.length === 0) {
                console.log('ℹ️ No faces detected - will use center crop');
                return null;
            }

            // Calculate average face position
            const avgPosition = {
                x: facePositions.reduce((sum, pos) => sum + pos.x, 0) / facePositions.length,
                y: facePositions.reduce((sum, pos) => sum + pos.y, 0) / facePositions.length
            };

            console.log(`✅ Face detected! Average position: (${avgPosition.x.toFixed(2)}, ${avgPosition.y.toFixed(2)})`);

            return avgPosition;

        } catch (error) {
            console.error('❌ Error detecting faces in video segment:', error);
            return null;
        }
    }

    /**
     * Get face size from prediction
     */
    getFaceSize(prediction) {
        const box = prediction.topLeft && prediction.bottomRight 
            ? {
                x: prediction.bottomRight[0] - prediction.topLeft[0],
                y: prediction.bottomRight[1] - prediction.topLeft[1]
              }
            : { x: 0, y: 0 };
        return box.x * box.y;
    }

    /**
     * Get normalized face center position (0-1 range)
     */
    getFaceCenter(prediction, frameWidth, frameHeight) {
        try {
            // BlazeFace returns topLeft and bottomRight as arrays or array-like objects
            let topLeft, bottomRight;
            
            // Handle both tensor and array formats
            if (prediction.topLeft) {
                topLeft = Array.isArray(prediction.topLeft) 
                    ? prediction.topLeft 
                    : Array.from(prediction.topLeft);
            }
            
            if (prediction.bottomRight) {
                bottomRight = Array.isArray(prediction.bottomRight) 
                    ? prediction.bottomRight 
                    : Array.from(prediction.bottomRight);
            }
            
            if (topLeft && bottomRight && topLeft.length >= 2 && bottomRight.length >= 2) {
                const centerX = (topLeft[0] + bottomRight[0]) / 2;
                const centerY = (topLeft[1] + bottomRight[1]) / 2;

                // Validate the values
                if (!isNaN(centerX) && !isNaN(centerY)) {
                    return {
                        x: centerX / frameWidth,
                        y: centerY / frameHeight
                    };
                }
            }
        } catch (error) {
            console.warn('⚠️ Error extracting face center:', error);
        }

        // Fallback to center if unable to extract
        return { x: 0.5, y: 0.5 };
    }

    /**
     * Cleanup resources
     */
    dispose() {
        if (this.model) {
            // Check if dispose method exists before calling it
            if (typeof this.model.dispose === 'function') {
                try {
                    this.model.dispose();
                } catch (error) {
                    console.warn('⚠️ Error disposing face detection model:', error);
                }
            }
            this.model = null;
        }
        if (this.worker) {
            this.worker.terminate();
            this.worker = null;
        }
        this.isLoaded = false;
    }
}

// Create singleton instance
const faceDetector = new FaceDetector();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = faceDetector;
}
