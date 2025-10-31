/**
 * Client-Side Shorts UI Integration
 * 
 * Integrates the client-side video processing with the existing UI
 * Preserves the current grid layout, progress indicators, and thumbnails
 */

(function(global) {
    const clientShortsIntegration = {
        /**
         * Initialize client-side shorts generation
         * This replaces the server-side processing
         */
        async initializeClientSideProcessing() {
            console.log('🎬 Initializing client-side shorts processing...');

            // Check browser compatibility
            if (!this.checkBrowserCompatibility()) {
                console.error('❌ Browser does not support required features');
                this.showError('Your browser does not support client-side video processing. Please use a modern browser like Chrome, Edge, or Firefox.');
                return false;
            }

            try {
                // Initialize the shorts generator
                if (typeof shortsGenerator !== 'undefined') {
                    await shortsGenerator.initialize();
                    console.log('✅ Client-side processing ready');
                    return true;
                } else {
                    throw new Error('Shorts generator module not loaded');
                }
            } catch (error) {
                console.error('❌ Failed to initialize client-side processing:', error);
                this.showError(`Failed to initialize: ${error.message}`);
                return false;
            }
        },

        /**
         * Check if browser supports required features
         */
        checkBrowserCompatibility() {
            const required = {
                'Canvas API': !!document.createElement('canvas').getContext,
                'MediaRecorder API': typeof MediaRecorder !== 'undefined',
                'WebGL': this.checkWebGLSupport(),
                'Fetch API': typeof fetch !== 'undefined',
                'Promises': typeof Promise !== 'undefined'
            };

            console.log('🔍 Browser compatibility check:', required);

            return Object.values(required).every(supported => supported);
        },

        /**
         * Check WebGL support (required for TensorFlow.js)
         */
        checkWebGLSupport() {
            try {
                const canvas = document.createElement('canvas');
                return !!(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'));
            } catch (e) {
                return false;
            }
        },

        /**
         * Generate shorts using client-side processing
         * This is called when user clicks "Generate Shorts"
         */
        async generateShortsClientSide() {
            console.log('🎯 generateShortsClientSide() called');
            
            const url = document.getElementById('shorts-youtube-url')?.value?.trim();
            
            console.log('📝 URL input value:', url);
            
            if (!url) {
                this.showError('Please enter a YouTube URL');
                return;
            }

            if (!this.isValidYouTubeUrl(url)) {
                this.showError('Please enter a valid YouTube URL');
                return;
            }

            console.log('🎬 Starting client-side shorts generation for:', url);

            // Show processing UI
            this.showProcessingUI();

            try {
                // Initialize if not already done
                const initialized = await this.initializeClientSideProcessing();
                if (!initialized) {
                    throw new Error('Failed to initialize processing');
                }

                // Clear previous results
                this.clearPreviousResults();

                // Get language preference from localStorage (force auto for better detection)
                let language = localStorage.getItem('preferred-language') || 'auto';
                
                // Force auto-detection for better language support
                if (language === 'en' || language === 'ar') {
                    language = 'auto';
                    console.log(`🔄 Forcing auto-detection instead of fixed language for better accuracy`);
                }
                
                console.log(`🌐 Starting shorts generation with language preference: ${language}`);

                // Generate shorts
                const clips = await shortsGenerator.generateShorts(
                    url,
                    // Progress callback
                    (percentage, message) => {
                        this.updateProgress(percentage, message);
                    },
                    // Clip ready callback
                    (clip, clipNum, totalClips) => {
                        this.displayNewClip(clip, clipNum, totalClips);
                    },
                    // Language parameter
                    language
                );

                console.log(`✅ Generated ${clips.length} shorts successfully`);

                // Show completion message
                this.showCompletionMessage(clips.length);

            } catch (error) {
                console.error('❌ Shorts generation failed:', error);
                this.showError(`Failed to generate shorts: ${error.message}`);
            }
        },

        /**
         * Display a newly processed clip in the existing grid
         */
        displayNewClip(clip, clipNum, totalClips) {
            console.log(`🎬 Displaying clip ${clipNum}/${totalClips}`);

            const container = document.getElementById('shorts-clips-container');
            if (!container) {
                console.error('❌ Clips container not found');
                return;
            }

            // Ensure grid layout is active for mobile compatibility
            if (!container.classList.contains('video-clips-grid')) {
                container.classList.add('video-clips-grid');
                console.log('✅ Applied video-clips-grid class for mobile display');
            }

            // Force display and visibility for mobile
            container.style.display = 'grid';
            container.style.width = '100%';
            container.style.visibility = 'visible';

            // Create clip card element
            const clipCard = this.createClientSideClipCard(clip, clipNum);

            // Add to container
            container.appendChild(clipCard);

            // Show the clips section if hidden
            const clipsSection = document.getElementById('shorts-clips-section');
            if (clipsSection) {
                clipsSection.classList.remove('hidden');
                clipsSection.style.display = 'block';
                clipsSection.style.visibility = 'visible';
                
                // Force card visibility
                const cardElement = clipsSection.querySelector('.card');
                if (cardElement) {
                    cardElement.style.display = 'block';
                    cardElement.style.width = '100%';
                }
            }

            // Update clips count
            this.updateClipsCount(clipNum, totalClips);

            // Scroll to the new clip with mobile-friendly behavior
            setTimeout(() => {
                clipCard.scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'nearest',
                    inline: 'nearest'
                });
            }, 100);

            console.log('✅ Clip displayed and made visible for mobile');
        },

        /**
         * Create clip card element for client-side processed clip
         */
        createClientSideClipCard(clip, clipNum) {
            const div = document.createElement('div');
            div.className = 'video-clip-card';
            div.setAttribute('data-clip-id', `client-clip-${clipNum}`);
            
            // Force display styles for mobile compatibility
            div.style.display = 'block';
            div.style.width = '100%';
            div.style.visibility = 'visible';
            div.style.opacity = '1';

            // Generate thumbnail from blob
            const thumbnailUrl = URL.createObjectURL(clip.blob);

            div.innerHTML = `
                <div class="video-container" style="display: flex; width: 100%; aspect-ratio: 9/16;">
                    <div class="video-placeholder" id="placeholder-client-${clipNum}" style="display: flex; width: 100%; height: 100%;">
                        <video class="video-thumbnail-video" 
                               src="${thumbnailUrl}" 
                               preload="metadata"
                               style="width: 100%; height: 100%; object-fit: cover; display: block;"></video>
                        <div class="video-overlay"></div>
                        <div class="video-status-badge ready">▶</div>
                        <div class="video-number">${clipNum}</div>
                        <div class="video-play-button" onclick="youtubeApp.playClientClip('client-clip-${clipNum}', ${clipNum})">
                            <i class="fas fa-play"></i>
                        </div>
                    </div>
                    <video class="inline-video-player" id="video-client-${clipNum}" style="display: none; width: 100%; height: 100%;" controls>
                        <source src="${clip.downloadUrl}" type="video/webm">
                        Your browser does not support the video tag.
                    </video>
                </div>
                <div class="video-clip-info" style="display: block; padding: 8px;">
                    <h6 class="video-title" style="display: block; margin: 0 0 4px 0;">${this.escapeHtml(clip.title)}</h6>
                    <p class="video-description" style="display: block; margin: 0 0 4px 0;">${this.escapeHtml(clip.description || '')}</p>
                    <div class="video-meta" style="display: block; margin-bottom: 4px;">
                        <small class="text-muted" style="display: block;">
                            <i class="fas fa-clock me-1"></i>
                            ${this.formatTime(clip.startTime)} - ${this.formatTime(clip.endTime)}
                            <span class="ms-2">
                                <i class="fas fa-hdd me-1"></i>
                                ${this.formatBytes(clip.size)}
                            </span>
                        </small>
                    </div>
                    <div class="video-actions mt-2" style="display: flex; gap: 4px;">
                        <button class="btn btn-success btn-sm" onclick="youtubeApp.playClientClip('client-clip-${clipNum}', ${clipNum})" style="display: inline-block;">
                            <i class="fas fa-play me-1"></i>Play
                        </button>
                        <button class="btn btn-outline-success btn-sm" onclick="youtubeApp.downloadClientClip('client-clip-${clipNum}')" style="display: inline-block;">
                            <i class="fas fa-download me-1"></i>Download
                        </button>
                    </div>
                </div>
            `;

            return div;
        },

        /**
         * Play client-side processed clip
         */
        playClientClip(clipId, clipNum) {
            // Handle both 'client-clip-1' format and direct number
            const num = typeof clipNum === 'number' ? clipNum : clipId.replace('client-clip-', '');
            
            const placeholder = document.getElementById(`placeholder-client-${num}`);
            const videoPlayer = document.getElementById(`video-client-${num}`);

            if (!placeholder || !videoPlayer) {
                console.error('Video elements not found for:', clipId, 'num:', num);
                return;
            }

            // Hide placeholder, show video
            placeholder.style.display = 'none';
            videoPlayer.style.display = 'block';

            // Play the video
            videoPlayer.play().catch(error => {
                console.error('Error playing video:', error);
                placeholder.style.display = 'flex';
                videoPlayer.style.display = 'none';
            });

            // Reset when video ends
            videoPlayer.onended = () => {
                placeholder.style.display = 'flex';
                videoPlayer.style.display = 'none';
                videoPlayer.currentTime = 0;
            };
        },

        /**
         * Download client-side processed clip
         */
        downloadClientClip(clipId) {
            const clip = shortsGenerator.processedClips.find(c => 
                `client-clip-${shortsGenerator.processedClips.indexOf(c) + 1}` === clipId
            );

            if (!clip) {
                console.error('Clip not found:', clipId);
                return;
            }

            // Create download link
            const a = document.createElement('a');
            a.href = clip.downloadUrl;
            a.download = `${clip.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_short.webm`;
            a.click();

            console.log('📥 Download started:', clip.title);
        },

        /**
         * Update progress indicator
         */
        updateProgress(percentage, message) {
            const progressBar = document.querySelector('.progress-fill');
            const progressText = document.querySelector('.progress-message');

            if (progressBar) {
                progressBar.style.width = `${percentage}%`;
            }

            if (progressText) {
                progressText.textContent = message;
            }
        },

        /**
         * Update clips count badge
         */
        updateClipsCount(current, total) {
            const countText = document.getElementById('clips-count-text');
            if (countText) {
                countText.textContent = `${current}/${total} clips`;
            }
        },

        /**
         * Show processing UI
         */
        showProcessingUI() {
            const statusContainer = document.getElementById('status-container');
            if (statusContainer) {
                statusContainer.classList.remove('hidden');
                statusContainer.innerHTML = `
                    <div class="processing-status">
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: 0%"></div>
                        </div>
                        <p class="progress-message">Starting shorts generation...</p>
                    </div>
                `;
            }
        },

        /**
         * Clear previous results
         */
        clearPreviousResults() {
            const container = document.getElementById('shorts-clips-container');
            if (container) {
                container.innerHTML = '';
                // Ensure grid class is maintained for mobile
                if (!container.classList.contains('video-clips-grid')) {
                    container.classList.add('video-clips-grid');
                }
                // Force visibility styles for mobile
                container.style.display = 'grid';
                container.style.width = '100%';
                container.style.visibility = 'visible';
                console.log('✅ Previous results cleared, grid maintained for mobile');
            }

            // Cleanup previous clip URLs (only if generator was initialized)
            if (typeof shortsGenerator !== 'undefined' && shortsGenerator && shortsGenerator.processedClips) {
                try {
                    if (typeof shortsGenerator.dispose === 'function') {
                        shortsGenerator.dispose();
                    }
                } catch (error) {
                    console.warn('⚠️ Error disposing shorts generator:', error);
                }
            }
        },

        /**
         * Show completion message
         */
        showCompletionMessage(clipCount) {
            const statusContainer = document.getElementById('status-container');
            if (statusContainer) {
                setTimeout(() => {
                    statusContainer.classList.add('hidden');
                }, 2000);
            }
        },

        /**
         * Utility functions
         */
        isValidYouTubeUrl(url) {
            const patterns = [
                /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)/,
                /youtube\.com\/watch\?.*v=([^&\n?#]+)/
            ];
            return patterns.some(pattern => pattern.test(url));
        },

        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        formatTime(seconds) {
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        },

        formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
        },

        showError(message) {
            const statusContainer = document.getElementById('status-container');
            if (statusContainer) {
                statusContainer.classList.remove('hidden');
                statusContainer.innerHTML = `
                    <div class="error-message">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>${message}</p>
                    </div>
                `;
            }
        }
    };

    // Add to global app
    global.YouTubeTranscriptAppMixins = global.YouTubeTranscriptAppMixins || [];
    global.YouTubeTranscriptAppMixins.push(clientShortsIntegration);

})(window);
