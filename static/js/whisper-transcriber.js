/**
 * Client-side Whisper transcription using Transformers.js
 * Generates accurate captions with perfect timing for video segments
 */

class WhisperTranscriber {
    constructor() {
        this.pipeline = null;
        this.isInitialized = false;
        this.isInitializing = false;
        this.modelName = 'Xenova/whisper-tiny'; // Multilingual support including Arabic (77MB)
        // Alternative models:
        // 'Xenova/whisper-base' - Better multilingual accuracy (148MB)
        // 'Xenova/whisper-small' - Even better multilingual (488MB)
        // 'Xenova/whisper-tiny.en' - English-only, smaller (39MB)
    }

    /**
     * Initialize Whisper model (downloads model on first use)
     */
    async initialize(progressCallback = null) {
        if (this.isInitialized) {
            console.log('✅ Whisper already initialized');
            return;
        }

        if (this.isInitializing) {
            console.log('⏳ Whisper initialization already in progress...');
            // Wait for initialization to complete
            while (this.isInitializing) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            return;
        }

        try {
            this.isInitializing = true;
            console.log('🎤 Initializing Whisper transcriber...');
            console.log(`📦 Loading model: ${this.modelName}`);

            if (progressCallback) {
                progressCallback({ status: 'loading', message: 'Loading Whisper model...' });
            }

            // Dynamically import Transformers.js
            const { pipeline, env } = await import('https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2');

            // Configure to use remote models from Hugging Face CDN
            env.allowRemoteModels = true;
            env.allowLocalModels = false;

            // Create automatic speech recognition pipeline
            this.pipeline = await pipeline('automatic-speech-recognition', this.modelName, {
                quantized: true, // Use quantized version for smaller size & faster inference
            });

            this.isInitialized = true;
            this.isInitializing = false;
            console.log('✅ Whisper transcriber ready');

            if (progressCallback) {
                progressCallback({ status: 'ready', message: 'Whisper ready' });
            }

        } catch (error) {
            this.isInitializing = false;
            console.error('❌ Failed to initialize Whisper:', error);
            throw new Error(`Whisper initialization failed: ${error.message}`);
        }
    }

    /**
     * Transcribe audio from a video segment
     * @param {Blob} videoBlob - Video blob to transcribe
     * @param {Object} options - Transcription options
     * @returns {Array} Array of caption segments with {text, start, end}
     */
    async transcribe(videoBlob, options = {}) {
        const {
            language = null, // Use null for auto-detection, or specify language code
            returnTimestamps = 'word', // 'word' for word-level, true for segment-level
            chunkLengthS = 30, // Process in 30s chunks
            strideLengthS = 5, // 5s overlap between chunks
            progressCallback = null
        } = options;

        if (!this.isInitialized) {
            console.log('⚠️  Whisper not initialized, initializing now...');
            await this.initialize(progressCallback);
        }

        try {
            console.log('🎤 Starting transcription...');
            console.log(`📊 Video size: ${(videoBlob.size / 1024 / 1024).toFixed(2)} MB`);

            if (progressCallback) {
                progressCallback({ status: 'extracting', message: 'Extracting audio...' });
            }

            // Extract audio from video blob
            const audioData = await this.extractAudioFromVideo(videoBlob);

            if (progressCallback) {
                progressCallback({ status: 'transcribing', message: 'Transcribing with Whisper...' });
            }

            console.log('🔍 Running Whisper transcription...');
            console.log('🔍 Audio data to Whisper:', {
                type: audioData.constructor.name,
                length: audioData.length,
                sampleRate: 16000,
                duration: (audioData.length / 16000).toFixed(2) + 's',
                min: Math.min(...Array.from(audioData.slice(0, 100))),
                max: Math.max(...Array.from(audioData.slice(0, 100))),
                mean: Array.from(audioData.slice(0, 1000)).reduce((a, b) => a + Math.abs(b), 0) / 1000
            });
            
            const startTime = performance.now();

            // Run Whisper transcription
            // NOTE: Transformers.js Whisper in browser REQUIRES chunk_length_s for audio >30s
            // This is different from Python Whisper - browser version needs explicit chunking
            const transcriptionOptions = {
                chunk_length_s: 30,        // Required for browser - chunks audio into 30s segments
                stride_length_s: 5,        // 5s overlap between chunks for better accuracy
                return_timestamps: 'word'  // Word-level timestamps
            };

            // Add language parameter for multilingual model
            if (language && language !== 'auto') {
                transcriptionOptions.language = language; // Specify target language for better accuracy
                console.log(`🌐 Whisper: Using specified language: ${language}`);
            } else {
                console.log(`🌐 Whisper: Using auto-detection for multilingual content`);
            }

            console.log(`🔍 Whisper options:`, transcriptionOptions);
            const result = await this.pipeline(audioData, transcriptionOptions);

            const duration = ((performance.now() - startTime) / 1000).toFixed(2);
            console.log(`✅ Transcription complete in ${duration}s`);
            
            // DEBUG: Comprehensive result logging
            console.log('🔍 Whisper raw result:', JSON.stringify(result, null, 2));
            console.log('🔍 Result type:', typeof result);
            console.log('🔍 Result keys:', Object.keys(result));
            console.log('🔍 Result.text type:', typeof result.text, 'length:', result.text?.length);
            console.log('🔍 Result.chunks type:', typeof result.chunks, 'length:', result.chunks?.length);
            
            // Check if this is an array of results (multiple chunks)
            if (Array.isArray(result)) {
                console.log('⚠️  Result is an array with', result.length, 'items');
                console.log('🔍 First item:', result[0]);
            }
            
            if (result.text) console.log('🔍 Result.text:', result.text);
            if (result.chunks) console.log('🔍 Result.chunks:', result.chunks);

            // Convert Whisper output to our caption format
            const captions = this.formatCaptions(result);
            console.log(`📝 Generated ${captions.length} caption segments`);

            if (captions.length > 0) {
                console.log(`📍 First caption: "${captions[0].text}" (${captions[0].start}s-${captions[0].end}s)`);
                console.log(`📍 Last caption: "${captions[captions.length - 1].text}" (${captions[captions.length - 1].start}s-${captions[captions.length - 1].end}s)`);
            }

            if (progressCallback) {
                progressCallback({ status: 'complete', message: 'Transcription complete' });
            }

            return captions;

        } catch (error) {
            console.error('❌ Transcription failed:', error);
            if (progressCallback) {
                progressCallback({ status: 'error', message: `Transcription failed: ${error.message}` });
            }
            throw error;
        }
    }

    /**
     * Extract audio from video blob using Web Audio API
     * @private
     */
    async extractAudioFromVideo(videoBlob) {
        return new Promise(async (resolve, reject) => {
            try {
                console.log('🎵 Extracting audio from video...');

                // Convert video blob to ArrayBuffer
                const arrayBuffer = await videoBlob.arrayBuffer();
                
                // Create audio context with 16kHz sample rate (Whisper requirement)
                const audioContext = new (window.AudioContext || window.webkitAudioContext)({
                    sampleRate: 16000
                });

                try {
                    // Decode audio data from video
                    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
                    
                    // Get mono channel PCM data (Whisper expects mono)
                    let audioData;
                    if (audioBuffer.numberOfChannels === 1) {
                        audioData = audioBuffer.getChannelData(0);
                    } else {
                        // Mix down to mono if stereo
                        const left = audioBuffer.getChannelData(0);
                        const right = audioBuffer.getChannelData(1);
                        audioData = new Float32Array(left.length);
                        for (let i = 0; i < left.length; i++) {
                            audioData[i] = (left[i] + right[i]) / 2;
                        }
                    }
                    
                    // Calculate max amplitude across ALL samples using loop (avoids stack overflow)
                    let maxAmplitude = 0;
                    for (let i = 0; i < audioData.length; i++) {
                        const absValue = Math.abs(audioData[i]);
                        if (absValue > maxAmplitude) {
                            maxAmplitude = absValue;
                        }
                    }
                    
                    console.log(`✅ Audio extracted: ${(audioData.length / audioBuffer.sampleRate).toFixed(2)}s @ ${audioBuffer.sampleRate}Hz`);
                    console.log(`🔊 Original max amplitude: ${maxAmplitude.toFixed(4)}`);
                    
                    // NORMALIZE AUDIO: Boost quiet audio to ensure Whisper can detect speech
                    // Whisper works best with audio normalized to near -3dB (amplitude ~0.7)
                    if (maxAmplitude > 0 && maxAmplitude < 0.5) {
                        // Audio is too quiet - normalize to 0.7 amplitude
                        const boostFactor = 0.7 / maxAmplitude;
                        console.log(`🔧 Normalizing audio: boosting by ${boostFactor.toFixed(2)}x (${maxAmplitude.toFixed(4)} → 0.7)`);
                        
                        const normalizedData = new Float32Array(audioData.length);
                        for (let i = 0; i < audioData.length; i++) {
                            normalizedData[i] = Math.max(-1, Math.min(1, audioData[i] * boostFactor)); // Clamp to [-1, 1]
                        }
                        audioData = normalizedData;
                        
                        // Recalculate max amplitude to verify normalization
                        let newMaxAmplitude = 0;
                        for (let i = 0; i < audioData.length; i++) {
                            const absValue = Math.abs(audioData[i]);
                            if (absValue > newMaxAmplitude) {
                                newMaxAmplitude = absValue;
                            }
                        }
                        console.log(`✅ Audio normalized: new max amplitude: ${newMaxAmplitude.toFixed(4)}`);
                    }
                    
                    // DEBUG: Check audio data properties (use loop for max to avoid stack overflow)
                    let sampleMax = 0;
                    for (let i = 0; i < Math.min(1000, audioData.length); i++) {
                        const absValue = Math.abs(audioData[i]);
                        if (absValue > sampleMax) {
                            sampleMax = absValue;
                        }
                    }
                    
                    console.log('🔍 Audio data debug:', {
                        samples: audioData.length,
                        duration: (audioData.length / audioBuffer.sampleRate).toFixed(2),
                        sampleRate: audioBuffer.sampleRate,
                        firstSamples: Array.from(audioData.slice(0, 10)),
                        maxAmplitude: sampleMax,
                        hasSound: sampleMax > 0.01
                    });
                    
                    audioContext.close();
                    resolve(audioData);
                    
                } catch (decodeError) {
                    audioContext.close();
                    reject(new Error(`Audio decoding failed: ${decodeError.message}`));
                }

            } catch (error) {
                reject(new Error(`Audio extraction failed: ${error.message}`));
            }
        });
    }

    /**
     * Format Whisper output to our caption format
     * @private
     */
    formatCaptions(whisperResult) {
        const captions = [];

        if (!whisperResult || !whisperResult.chunks) {
            // Fallback: single segment without timestamps
            if (whisperResult && whisperResult.text) {
                return [{
                    text: whisperResult.text.trim(),
                    start: 0,
                    end: 30 // Default duration
                }];
            }
            return [];
        }

        // Process timestamp chunks
        for (const chunk of whisperResult.chunks) {
            if (chunk.text && chunk.text.trim().length > 0) {
                captions.push({
                    text: chunk.text.trim(),
                    start: chunk.timestamp[0] || 0,
                    end: chunk.timestamp[1] || (chunk.timestamp[0] + 1)
                });
            }
        }

        return captions;
    }

    /**
     * Unload model to free memory
     */
    async unload() {
        if (this.pipeline) {
            // Transformers.js doesn't have explicit cleanup, but we can null the reference
            this.pipeline = null;
            this.isInitialized = false;
            console.log('🗑️  Whisper model unloaded');
        }
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WhisperTranscriber;
}
