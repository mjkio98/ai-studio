/**
 * Main YouTube Transcript Application
 * Orchestrates all managers and handles core application logic
 */
class YouTubeTranscriptApp {
    constructor() {
        this.currentTranscript = '';
        this.currentVideoInfo = null;
        this.currentTaskId = null;
        this.currentEventSource = null;
        this.currentAbortController = null;
        this.taskCancelled = false; // Flag to ignore progress updates after cancellation
        
        // Initialize managers
        this.languageManager = new LanguageManager(this);
        this.cacheManager = new CacheManager(this);
        this.uiManager = new UIManager(this);
        this.streamingManager = new StreamingManager(this);
        this.videoProcessor = new VideoProcessor(this);
        
        this.initializeComponents();
        
        // Apply language after a short delay to ensure DOM is ready
        setTimeout(() => {
            this.languageManager.applyLanguage();
        }, 100);
        
        // Handle page unload - cancel any ongoing tasks (only on actual page close/refresh)
        window.addEventListener('beforeunload', () => {
            this.cancelCurrentTask();
        });
        
        // Note: Removed visibilitychange listener to allow users to switch tabs 
        // while videos are processing without cancelling the task
    }

    initializeComponents() {
        // Get DOM elements
        this.urlInput = document.getElementById('youtube-url');
        this.summarizeVideoBtn = document.getElementById('summarize-video-btn');
        
        // Multi-video elements
        this.singleModeBtn = document.getElementById('single-mode-btn');
        this.multiModeBtn = document.getElementById('multi-mode-btn');
        this.webpageModeBtn = document.getElementById('webpage-mode-btn');
        this.singleVideoSection = document.getElementById('single-video-section');
        this.multiVideoSection = document.getElementById('multi-video-section');
        this.webpageSection = document.getElementById('webpage-section');
        this.addUrlBtn = document.getElementById('add-url-btn');
        this.summarizeMultiBtn = document.getElementById('summarize-multi-btn');
        this.urlInputsContainer = document.getElementById('url-inputs-container');
        
        // Webpage elements
        this.webpageUrlInput = document.getElementById('webpage-url');
        this.analyzeWebpageBtn = document.getElementById('analyze-webpage-btn');
        
        this.isMultiMode = false;
        this.isWebpageMode = false;
        
        // Initialize existing remove buttons
        this.initializeRemoveButtons();
        
        this.statusContainer = document.getElementById('status-container');
        this.loadingState = document.getElementById('loading-state');
        this.errorState = document.getElementById('error-state');
        this.loadingText = document.getElementById('loading-text');
        this.errorMessage = document.getElementById('error-message');
        
        this.videoInfo = document.getElementById('video-info');
        this.videoThumbnail = document.getElementById('video-thumbnail');
        this.videoTitle = document.getElementById('video-title');
        this.videoChannel = document.getElementById('video-channel');
        
        this.summarySection = document.getElementById('summary-section');
        this.summaryText = document.getElementById('summary-text');
        this.copySummaryBtn = document.getElementById('copy-summary-btn');
        this.cancelBtn = document.getElementById('cancel-btn');

        // Bind event listeners
        this.summarizeVideoBtn.addEventListener('click', () => this.summarizeVideoDirectly());
        this.summarizeMultiBtn.addEventListener('click', () => this.summarizeMultipleVideos());
        
        // Mode switching
        this.singleModeBtn.addEventListener('click', () => this.switchToSingleMode());
        this.multiModeBtn.addEventListener('click', () => this.switchToMultiMode());
        this.webpageModeBtn.addEventListener('click', () => this.switchToWebpageMode());
        
        // Add URL functionality
        this.addUrlBtn.addEventListener('click', () => this.addUrlInput());
        
        // Webpage functionality
        this.analyzeWebpageBtn.addEventListener('click', () => this.analyzeWebpage());
        
        // Copy button functionality
        this.copySummaryBtn.addEventListener('click', () => this.uiManager.copySummaryToClipboard());
        
        this.urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.summarizeVideoDirectly();
        });

        this.urlInput.addEventListener('input', () => {
            this.uiManager.resetSections();
        });

        this.webpageUrlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.analyzeWebpage();
        });

        this.webpageUrlInput.addEventListener('input', () => {
            this.uiManager.resetSections();
        });

        // Language switcher event listeners
        document.getElementById('lang-en').addEventListener('click', () => this.languageManager.switchLanguage('en'));
        document.getElementById('lang-ar').addEventListener('click', () => this.languageManager.switchLanguage('ar'));
    }

    async summarizeVideoDirectly() {
        const url = this.urlInput.value.trim();
        await this.videoProcessor.summarizeVideoDirectly(url);
    }

    switchToSingleMode() {
        this.isMultiMode = false;
        this.isWebpageMode = false;
        
        // Update button states
        this.singleModeBtn.classList.add('active');
        this.multiModeBtn.classList.remove('active');
        this.webpageModeBtn.classList.remove('active');
        
        // Update section visibility
        this.singleVideoSection.classList.remove('hidden');
        this.multiVideoSection.classList.add('hidden');
        this.webpageSection.classList.add('hidden');
        this.uiManager.resetSections();
    }

    switchToMultiMode() {
        this.isMultiMode = true;
        this.isWebpageMode = false;
        
        // Update button states
        this.multiModeBtn.classList.add('active');
        this.singleModeBtn.classList.remove('active');
        this.webpageModeBtn.classList.remove('active');
        
        // Update section visibility
        this.singleVideoSection.classList.add('hidden');
        this.multiVideoSection.classList.remove('hidden');
        this.webpageSection.classList.add('hidden');
        this.updateAddButtonState(); // Initialize button state
        this.uiManager.resetSections();
    }

    switchToWebpageMode() {
        this.isMultiMode = false;
        this.isWebpageMode = true;
        
        // Update button states
        this.webpageModeBtn.classList.add('active');
        this.singleModeBtn.classList.remove('active');
        this.multiModeBtn.classList.remove('active');
        
        // Update section visibility
        this.singleVideoSection.classList.add('hidden');
        this.multiVideoSection.classList.add('hidden');
        this.webpageSection.classList.remove('hidden');
        this.uiManager.resetSections();
    }

    addUrlInput() {
        const container = this.urlInputsContainer;
        const currentCount = container.children.length;
        
        // Enforce maximum of 4 videos
        if (currentCount >= 4) {
            this.uiManager.showError(this.languageManager.t('errors.maxVideos'));
            return;
        }
        
        const urlCount = currentCount + 1;
        
        const div = document.createElement('div');
        div.className = 'flex gap-2 url-input-row';
        div.innerHTML = `
            <input 
                type="url" 
                class="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent outline-none youtube-url-multi"
                placeholder="https://www.youtube.com/watch?v=... (Video ${urlCount})"
            >
            <button type="button" class="px-3 py-3 text-red-600 hover:bg-red-50 rounded-lg transition-colors remove-url-btn" title="Remove URL">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        // Add event listener for remove button
        const removeBtn = div.querySelector('.remove-url-btn');
        removeBtn.addEventListener('click', () => {
            div.remove();
            this.updateUrlPlaceholders();
            this.updateAddButtonState();
        });
        
        container.appendChild(div);
        this.updateUrlPlaceholders();
        this.updateAddButtonState();
    }

    updateUrlPlaceholders() {
        const inputs = this.urlInputsContainer.querySelectorAll('.youtube-url-multi');
        inputs.forEach((input, index) => {
            input.placeholder = `https://www.youtube.com/watch?v=... (Video ${index + 1})`;
        });
    }

    updateAddButtonState() {
        const currentCount = this.urlInputsContainer.children.length;
        const addBtn = this.addUrlBtn;
        
        if (currentCount >= 4) {
            addBtn.disabled = true;
            addBtn.classList.add('opacity-50', 'cursor-not-allowed');
            addBtn.classList.remove('hover:bg-gray-200');
        } else {
            addBtn.disabled = false;
            addBtn.classList.remove('opacity-50', 'cursor-not-allowed');
            addBtn.classList.add('hover:bg-gray-200');
        }
    }

    initializeRemoveButtons() {
        const removeButtons = this.urlInputsContainer.querySelectorAll('.remove-url-btn');
        removeButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const row = e.target.closest('.url-input-row');
                if (row && this.urlInputsContainer.children.length > 1) { // Keep at least one input
                    row.remove();
                    this.updateUrlPlaceholders();
                    this.updateAddButtonState();
                }
            });
        });
    }

    async summarizeMultipleVideos() {
        const urlInputs = this.urlInputsContainer.querySelectorAll('.youtube-url-multi');
        const urls = Array.from(urlInputs).map(input => input.value.trim()).filter(url => url);
        await this.videoProcessor.summarizeMultipleVideos(urls);
    }



    async analyzeWebpage() {
        const url = this.webpageUrlInput.value.trim();
        await this.videoProcessor.analyzeWebpage(url);
    }

    async listenToProgress(taskId) {
        // Track current task for cancellation
        this.currentTaskId = taskId;
        this.taskCancelled = false; // Reset cancellation flag for new task
        this.showCancelButton();
        
        return new Promise((resolve, reject) => {
            const eventSource = new EventSource(`/progress/${taskId}`);
            this.currentEventSource = eventSource;
            let hasShownContent = false;
            
            eventSource.onmessage = (event) => {
                try {
                    // Ignore any progress updates if task has been cancelled
                    if (this.taskCancelled) {
                        return;
                    }
                    
                    const progress = JSON.parse(event.data);
                    
                    if (progress.status === 'processing') {
                        this.updateStreamingProgress(progress.percentage, progress.message);
                        
                        // Show partial results if available and display them immediately
                        if (progress.partial_result && progress.partial_result.trim().length > 20) {
                            if (!hasShownContent) {
                                // First time showing content - prepare the sections
                                this.showStreamingSummary();
                                hasShownContent = true;
                            }
                            this.updateStreamingSummary(progress.partial_result);
                        } else if (progress.step === 'streaming_start' && !hasShownContent) {
                            // Show streaming UI even before content arrives
                            this.showStreamingSummary();
                            hasShownContent = true;
                        }
                    } else if (progress.status === 'completed') {
                        eventSource.close();
                        this.currentEventSource = null;
                        this.currentTaskId = null;
                        this.hideCancelButton();
                        
                        // Determine content type and display results properly
                        if (progress.result.video_info) {
                            // Video analysis result
                            this.displayVideoInfo(progress.result.video_info, progress.result.video_id);
                            this.displaySummary(progress.result.summary);
                            this.hideStatus();
                            
                            // Cache the successful result for video
                            const videoUrl = this.urlInput.value.trim();
                            this.setCachedResult(videoUrl, {
                                summary: progress.result.summary,
                                videoInfo: progress.result.video_info,
                                videoId: progress.result.video_id
                            }, 'video');
                        } else {
                            // Webpage analysis result
                            this.displayWebpageInfo(progress.result);
                            this.displaySummary(progress.result.summary);
                            this.hideStatus();
                            
                            // Cache the successful result for webpage
                            const webpageUrl = this.webpageUrlInput.value.trim();
                            this.setCachedResult(webpageUrl, {
                                summary: progress.result.summary,
                                title: progress.result.title || 'Webpage Analysis'
                            }, 'webpage');
                        }
                        
                        resolve();
                    } else if (progress.status === 'cancelled') {
                        eventSource.close();
                        this.currentEventSource = null;
                        this.currentTaskId = null;
                        this.hideCancelButton();
                        this.showError(this.t('cancelled'));
                        reject(new Error('Task cancelled'));
                    } else if (progress.status === 'error') {
                        eventSource.close();
                        this.currentEventSource = null;
                        this.currentTaskId = null;
                        this.hideCancelButton();
                        this.showError(progress.error || 'Analysis failed');
                        reject(new Error(progress.error));
                    }
                } catch (e) {
                    // Silently handle parsing errors
                }
            };
            
            eventSource.onerror = (error) => {
                eventSource.close();
                this.currentEventSource = null;
                this.currentTaskId = null;
                this.hideCancelButton();
                this.showError('Connection to progress stream failed');
                reject(error);
            };
            
            // Timeout after 5 minutes
            setTimeout(() => {
                if (eventSource.readyState !== EventSource.CLOSED) {
                    eventSource.close();
                    this.currentEventSource = null;
                    this.currentTaskId = null;
                    this.hideCancelButton();
                    this.showError('Analysis timed out');
                    reject(new Error('Timeout'));
                }
            }, 300000);
        });
    }

    async cancelCurrentTask() {
        // Set flag to ignore any further progress updates
        this.taskCancelled = true;
        
        // Clean up streaming first - this will trigger EventSource error handler
        if (this.currentEventSource) {
            this.currentEventSource.close();
            this.currentEventSource = null;
        }
        
        // Handle streaming tasks (webpage analysis & video processing)
        if (this.currentTaskId) {
            const taskIdToCancel = this.currentTaskId;
            this.currentTaskId = null; // Clear immediately to prevent race conditions
            
            try {
                await fetch(`/api/cancel/${taskIdToCancel}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
            } catch (error) {
                // Silently handle cancellation errors
            }
        }

        // Handle fetch-based tasks (for abort controller if still in use)
        if (this.currentAbortController) {
            this.currentAbortController.abort();
            this.currentAbortController = null;
        }

        // Immediately update UI to show cancellation
        this.hideStatus();
        this.resetSections(); // This will hide all sections including streaming UI
        
        // Re-enable buttons based on current mode
        this.enableButtons();
        
        // Show cancellation message after UI is cleaned up
        setTimeout(() => {
            this.showError(this.t('cancelled'));
        }, 100);

        this.hideCancelButton();
        
        // Clear the cancellation flag after a short delay
        setTimeout(() => {
            this.taskCancelled = false;
        }, 1000);
    }

    showCancelButton() {
        // Re-get the cancel button reference since it might have been recreated by showStreamingProgress
        this.cancelBtn = document.getElementById('cancel-btn');
        if (this.cancelBtn) {
            this.cancelBtn.classList.remove('hidden');
            this.cancelBtn.textContent = this.t('cancelBtn');
            this.cancelBtn.onclick = () => {
                if (confirm(this.t('cancelConfirm'))) {
                    this.cancelCurrentTask();
                }
            };
        }
    }

    hideCancelButton() {
        if (this.cancelBtn) {
            this.cancelBtn.classList.add('hidden');
        }
    }

    enableButtons() {
        // Re-enable buttons based on current mode
        if (this.isWebpageMode) {
            if (this.analyzeWebpageBtn) {
                this.analyzeWebpageBtn.disabled = false;
            }
        } else if (this.isMultiMode) {
            if (this.summarizeMultiBtn) {
                this.summarizeMultiBtn.disabled = false;
            }
        } else {
            if (this.summarizeVideoBtn) {
                this.summarizeVideoBtn.disabled = false;
            }
        }
    }

    async waitForTaskCompletion(taskId) {
        return new Promise((resolve, reject) => {
            const eventSource = new EventSource(`/progress/${taskId}`);
            this.currentEventSource = eventSource;
            this.currentTaskId = taskId;
            this.taskCancelled = false; // Reset cancellation flag for new task
            let hasShownContent = false;
            
            eventSource.onmessage = (event) => {
                try {
                    // Ignore any progress updates if task has been cancelled
                    if (this.taskCancelled) {
                        return;
                    }
                    
                    const progress = JSON.parse(event.data);
                    
                    if (progress.status === 'processing') {
                        this.updateLoadingProgress(progress.percentage, progress.message);
                        
                        // Show partial results if available and display them immediately (for streaming)
                        if (progress.partial_result && progress.partial_result.trim().length > 20) {
                            if (!hasShownContent) {
                                // First time showing content - prepare the sections
                                this.showStreamingSummary();
                                hasShownContent = true;
                            }
                            this.updateStreamingSummary(progress.partial_result);
                        } else if (progress.step === 'streaming_start' && !hasShownContent) {
                            // Show streaming UI even before content arrives
                            this.showStreamingSummary();
                            hasShownContent = true;
                        }
                    } else if (progress.status === 'completed') {
                        eventSource.close();
                        this.currentEventSource = null;
                        this.currentTaskId = null;
                        resolve(progress.result);
                    } else if (progress.status === 'cancelled') {
                        eventSource.close();
                        this.currentEventSource = null;
                        this.currentTaskId = null;
                        const cancelError = new Error(this.t('cancelled'));
                        cancelError.name = 'CancelError';
                        reject(cancelError); // Reject with cancel error to trigger catch block
                    } else if (progress.status === 'error') {
                        eventSource.close();
                        this.currentEventSource = null;
                        this.currentTaskId = null;
                        reject(new Error(progress.error || 'Task failed'));
                    }
                } catch (e) {
                    // Silently handle parsing errors
                }
            };
            
            eventSource.onerror = (error) => {
                eventSource.close();
                this.currentEventSource = null;
                this.currentTaskId = null;
                reject(new Error('Connection to progress stream failed'));
            };
            
            // Timeout after 10 minutes for video tasks
            setTimeout(() => {
                if (eventSource.readyState !== EventSource.CLOSED) {
                    eventSource.close();
                    this.currentEventSource = null;
                    this.currentTaskId = null;
                    reject(new Error('Task timed out'));
                }
            }, 600000);
        });
    }

    updateLoadingProgress(percentage, message) {
        if (this.loadingText) {
            this.loadingText.textContent = message;
        }
    }

    isValidWebpageUrl(url) {
        try {
            // Add protocol if missing
            if (!url.startsWith('http://') && !url.startsWith('https://')) {
                url = 'https://' + url;
            }
            
            const urlObj = new URL(url);
            
            // Check for valid protocol
            if (!['http:', 'https:'].includes(urlObj.protocol)) {
                return false;
            }
            
            // Check for valid hostname
            if (!urlObj.hostname || urlObj.hostname === 'localhost') {
                return false;
            }
            
            return true;
        } catch {
            return false;
        }
    }

    displayWebpageInfo(data) {
        // Show webpage information
        this.videoInfo.innerHTML = `
            <div class="webpage-info-container">
                <div class="webpage-info-card">
                    <div class="webpage-icon">
                        <i class="fas fa-globe"></i>
                    </div>
                    <div class="webpage-details">
                        <h4 class="webpage-title">${data.title}</h4>
                        <p class="webpage-url">${data.url}</p>
                        <div class="webpage-meta">
                            <span class="meta-item">
                                <i class="fas fa-file-text"></i>
                                ${data.content_length.toLocaleString()} characters
                            </span>
                            <span class="meta-item">
                                <i class="fas fa-cog"></i>
                                ${data.extraction_method}
                            </span>
                            <span class="meta-item">
                                <i class="fas fa-language"></i>
                                ${data.language_detected === 'ar' ? 'Arabic' : 'English'}
                            </span>
                        </div>
                    </div>
                </div>
                <div class="webpage-summary-badge">
                    <i class="fas fa-robot"></i>
                    <span>${this.t('webpageSummary')} - ${this.t('poweredBy')}</span>
                </div>
            </div>
        `;
        this.videoInfo.classList.remove('hidden');
    }

    isValidYouTubeUrl(url) {
        const patterns = [
            /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)/,
            /youtube\.com\/watch\?.*v=([^&\n?#]+)/
        ];
        
        return patterns.some(pattern => pattern.test(url));
    }

    extractVideoId(url) {
        const patterns = [
            /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)/,
            /youtube\.com\/watch\?.*v=([^&\n?#]+)/
        ];
        
        for (const pattern of patterns) {
            const match = url.match(pattern);
            if (match) return match[1];
        }
        return null;
    }

    displayVideoInfo(videoInfo, videoId) {
        this.videoThumbnail.src = videoInfo.thumbnail || `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;
        this.videoTitle.textContent = videoInfo.title;
        this.videoChannel.textContent = `Channel: ${videoInfo.author}`;
        
        this.videoInfo.classList.remove('hidden');
    }

    displaySummary(summary) {
        // Format the summary with enhanced markdown-like styling
        let formattedSummary = summary
            // First, temporarily replace double asterisks to avoid conflicts
            .replace(/\*\*(.*?)\*\*/g, '___DOUBLE_BOLD___$1___END_DOUBLE_BOLD___')
            
            // Convert single *bold* text (now safe from double asterisk interference)
            .replace(/\*([^*\n]+?)\*/g, '<strong class="font-bold text-gray-900 bg-blue-100 px-1 rounded">$1</strong>')
            
            // Restore double asterisk bold formatting
            .replace(/___DOUBLE_BOLD___(.*?)___END_DOUBLE_BOLD___/g, '<strong class="font-bold text-gray-900 bg-yellow-100 px-1 rounded">$1</strong>')
            
            // Convert # main heading with icon styling - using translation
            .replace(/^# (.*$)/gm, `<h1 class="text-3xl font-bold text-blue-800 mb-6 flex items-center"><span class="mr-3 text-4xl">📹</span>${this.t('formatting.videoSummaryTitle')}</h1>`)
            
            // Convert ## section headings with emoji support and better styling
            .replace(/^## 🎯 (Main Topics.*|المواضيع.*)/gm, `<h2 class="text-xl font-bold text-green-700 mt-8 mb-4 flex items-center bg-green-50 p-3 rounded-lg border-l-4 border-green-500"><span class="mr-3 text-2xl">🎯</span>${this.t('formatting.mainTopics')}</h2>`)
            .replace(/^## 📋 (Key Points.*|النقاط.*)/gm, `<h2 class="text-xl font-bold text-blue-700 mt-8 mb-4 flex items-center bg-blue-50 p-3 rounded-lg border-l-4 border-blue-500"><span class="mr-3 text-2xl">📋</span>${this.t('formatting.keyPoints')}</h2>`)
            .replace(/^## 💡 (Actionable.*|الاستنتاجات.*)/gm, `<h2 class="text-xl font-bold text-purple-700 mt-8 mb-4 flex items-center bg-purple-50 p-3 rounded-lg border-l-4 border-purple-500"><span class="mr-3 text-2xl">💡</span>${this.t('formatting.actionableTakeaways')}</h2>`)
            // Handle section headings without emoji but with known patterns
            .replace(/^## (Main Topics.*|المواضيع.*)/gmi, `<h2 class="text-xl font-bold text-green-700 mt-8 mb-4 flex items-center bg-green-50 p-3 rounded-lg border-l-4 border-green-500"><span class="mr-3 text-2xl">🎯</span>${this.t('formatting.mainTopics')}</h2>`)
            .replace(/^## (Key Points.*|النقاط.*)/gmi, `<h2 class="text-xl font-bold text-blue-700 mt-8 mb-4 flex items-center bg-blue-50 p-3 rounded-lg border-l-4 border-blue-500"><span class="mr-3 text-2xl">📋</span>${this.t('formatting.keyPoints')}</h2>`)
            .replace(/^## (Actionable.*|الاستنتاجات.*)/gmi, `<h2 class="text-xl font-bold text-purple-700 mt-8 mb-4 flex items-center bg-purple-50 p-3 rounded-lg border-l-4 border-purple-500"><span class="mr-3 text-2xl">💡</span>${this.t('formatting.actionableTakeaways')}</h2>`)
            .replace(/^## ⚡ (.*$)/gm, '<h2 class="text-xl font-bold text-red-700 mt-8 mb-4 flex items-center bg-red-50 p-3 rounded-lg border-l-4 border-red-500"><span class="mr-3 text-2xl">⚡</span>$1</h2>')
            
            // Additional specific text replacements before fallback
            .replace(/Actionable Takeaways/gi, this.t('formatting.actionableTakeaways'))
            .replace(/Notable Insights & Conclusions/gi, this.t('formatting.notableInsights'))
            .replace(/Bottom Line/gi, this.t('formatting.bottomLine').replace(':', ''))
            .replace(/Main Topics & Themes/gi, this.t('formatting.mainTopics'))
            .replace(/Key Points & Information/gi, this.t('formatting.keyPoints'))
            
            // Fallback for any other ## headings
            .replace(/^## (.*$)/gm, '<h2 class="text-xl font-bold text-gray-800 mt-8 mb-4 bg-gray-50 p-3 rounded-lg border-l-4 border-gray-400">$1</h2>')
            
            // Convert ### subheadings
            .replace(/^### (.*$)/gm, '<h3 class="text-lg font-semibold text-gray-800 mt-6 mb-3 border-b border-gray-200 pb-2">$1</h3>')
            
            // Convert --- horizontal rules with better styling
            .replace(/^---$/gm, '<hr class="my-8 border-2 border-gray-200 rounded">')
            
            // Convert bullet points with better spacing and icons (RTL-friendly)
            .replace(/^• (.*$)/gm, '<li class="mb-3 text-gray-700 leading-relaxed flex items-start"><span class="mr-3 text-blue-500 font-bold mt-1">•</span><span class="flex-1 rtl-content">$1</span></li>')
            
            // Convert other bullet formats (including en dash and asterisk)
            .replace(/^[-–*] (.*$)/gm, '<li class="mb-3 text-gray-700 leading-relaxed flex items-start"><span class="mr-3 text-blue-500 font-bold mt-1">•</span><span class="flex-1 rtl-content">$1</span></li>')
            
            // Handle en dash specifically (–)
            .replace(/^– (.*$)/gm, '<li class="mb-3 text-gray-700 leading-relaxed flex items-start"><span class="mr-3 text-blue-500 font-bold mt-1">•</span><span class="flex-1 rtl-content">$1</span></li>')
            
            // Handle asterisk specifically (*)
            .replace(/^\* (.*$)/gm, '<li class="mb-3 text-gray-700 leading-relaxed flex items-start"><span class="mr-3 text-blue-500 font-bold mt-1">•</span><span class="flex-1 rtl-content">$1</span></li>')
            
            // Convert numbered points
            .replace(/^\d+\. (.*$)/gm, '<li class="mb-3 text-gray-700 leading-relaxed">$1</li>')
            
            // Handle bottom line with special formatting - using translation
            .replace(/\*\*🎯 Bottom Line:\*\* (.*$)/gmi, `<div class="mt-8 p-4 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg shadow-lg"><div class="flex items-center"><span class="text-2xl mr-3">🎯</span><strong class="text-lg">${this.t('formatting.bottomLine')}</strong></div><p class="mt-2 text-lg font-medium">$1</p></div>`)
            .replace(/\*\*Bottom Line:\*\* (.*$)/gmi, `<div class="mt-8 p-4 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg shadow-lg"><div class="flex items-center"><span class="text-2xl mr-3">🎯</span><strong class="text-lg">${this.t('formatting.bottomLine')}</strong></div><p class="mt-2 text-lg font-medium">$1</p></div>`)
            .replace(/\*\*الخلاصة:\*\* (.*$)/gmi, `<div class="mt-8 p-4 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg shadow-lg"><div class="flex items-center"><span class="text-2xl mr-3">🎯</span><strong class="text-lg">${this.t('formatting.bottomLine')}</strong></div><p class="mt-2 text-lg font-medium">$1</p></div>`)
            // Also handle Arabic version with emoji
            .replace(/\*\*🎯 الخلاصة:\*\* (.*$)/gmi, `<div class="mt-8 p-4 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg shadow-lg"><div class="flex items-center"><span class="text-2xl mr-3">🎯</span><strong class="text-lg">${this.t('formatting.bottomLine')}</strong></div><p class="mt-2 text-lg font-medium">$1</p></div>`)
            // Handle plain text versions without markdown
            .replace(/^Bottom Line: (.*$)/gmi, `<div class="mt-8 p-4 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg shadow-lg"><div class="flex items-center"><span class="text-2xl mr-3">🎯</span><strong class="text-lg">${this.t('formatting.bottomLine')}</strong></div><p class="mt-2 text-lg font-medium">$1</p></div>`)
            .replace(/^الخلاصة: (.*$)/gmi, `<div class="mt-8 p-4 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg shadow-lg"><div class="flex items-center"><span class="text-2xl mr-3">🎯</span><strong class="text-lg">${this.t('formatting.bottomLine')}</strong></div><p class="mt-2 text-lg font-medium">$1</p></div>`);

        // Enhanced table formatting before other conversions
        formattedSummary = this.formatTables(formattedSummary);
        
        formattedSummary = formattedSummary
            // Convert double line breaks to paragraph breaks
            .replace(/\n\n/g, '</p><p class="mb-4 leading-relaxed text-gray-700">')
            
            // Convert single line breaks to <br>
            .replace(/\n/g, '<br>');

        // Wrap consecutive <li> elements in <ul> tags with better styling
        formattedSummary = formattedSummary.replace(/(<li class="mb-3 text-gray-700[^"]*">.*?<\/li>(?:<br>)*)+/g, (match) => {
            return `<ul class="space-y-2 mb-6">${match.replace(/<br>/g, '')}</ul>`;
        });

        // Clean up any orphaned tags
        formattedSummary = formattedSummary.replace(/^<\/p>/, '');
        
        this.summaryText.innerHTML = formattedSummary;
        
        this.summarySection.classList.remove('hidden');
        // Show copy button when summary is fully displayed (task completed)
        this.copySummaryBtn.classList.remove('hidden');
        
        // Scroll summary section into view
        this.summarySection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    formatTables(text) {
        // Enhanced markdown table formatting with better styling
        return text.replace(/(\|.*?\|(?:\r?\n|\r))+/gm, (match) => {
            const lines = match.trim().split(/\r?\n|\r/);
            if (lines.length < 2) return match;
            
            // Check if it's a proper markdown table (has separator row)
            const hasSeparator = lines[1] && lines[1].match(/^\|[\s\-\|:]+\|$/);
            if (!hasSeparator) return match;
            
            const headerRow = lines[0];
            const dataRows = lines.slice(2); // Skip header and separator
            
            if (!headerRow || dataRows.length === 0) return match;
            
            // Parse header
            const headers = headerRow.split('|').map(h => h.trim()).filter(h => h);
            
            // Parse data rows
            const rows = dataRows.map(row => 
                row.split('|').map(cell => cell.trim()).filter(cell => cell)
            ).filter(row => row.length > 0);
            
            if (headers.length === 0 || rows.length === 0) return match;
            
            // Determine if this is a comparison table (contains Arabic comparison terms)
            const isComparisonTable = text.includes('⚖️') || 
                                     text.includes('وجهات نظر') || 
                                     text.includes('مقارنة') ||
                                     text.includes('Different Perspectives');
            
            const tableClass = isComparisonTable ? 'comparison-table' : '';
            
            // Build the HTML table
            let html = `<table class="${tableClass}">`;
            
            // Add header
            html += '<thead><tr>';
            headers.forEach(header => {
                html += `<th>${header}</th>`;
            });
            html += '</tr></thead>';
            
            // Add body
            html += '<tbody>';
            rows.forEach(row => {
                html += '<tr>';
                row.forEach((cell, index) => {
                    // First column in comparison tables gets special styling
                    const cellClass = (isComparisonTable && index === 0) ? 'font-semibold bg-gray-50' : '';
                    html += `<td class="${cellClass}">${cell}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody></table>';
            
            return html;
        });
    }

    showLoading(message) {
        this.loadingText.textContent = message;
        this.statusContainer.classList.remove('hidden');
        this.loadingState.classList.remove('hidden');
        this.errorState.classList.add('hidden');
    }

    showError(message) {
        // Check if original elements exist (they might have been replaced by streaming UI)
        if (!this.errorMessage || !this.statusContainer || !this.errorState || !this.loadingState) {
            // If streaming UI replaced original content, just show a simple error message
            const statusContainer = document.getElementById('status');
            if (statusContainer) {
                statusContainer.innerHTML = `<div class="error-message text-red-600 text-center py-4">${message}</div>`;
                statusContainer.classList.remove('hidden');
            }
            return;
        }
        
        this.errorMessage.textContent = message;
        this.statusContainer.classList.remove('hidden');
        this.errorState.classList.remove('hidden');
        this.loadingState.classList.add('hidden');
    }

    showInfo(message) {
        this.loadingText.textContent = message;
        this.statusContainer.classList.remove('hidden');
        this.loadingState.classList.remove('hidden');
        this.errorState.classList.add('hidden');
        
        // Auto-hide info messages after 3 seconds
        setTimeout(() => {
            this.hideStatus();
        }, 3000);
    }

    hideStatus() {
        // Hide the main status container (this handles both original and streaming UI)
        this.statusContainer.classList.add('hidden');
        
        // Try to hide original loading/error states if they still exist
        if (this.loadingState) {
            this.loadingState.classList.add('hidden');
        }
        if (this.errorState) {
            this.errorState.classList.add('hidden');
        }
        
        // Clear any streaming content that might have been created
        if (this.statusContainer.innerHTML.includes('progress-message')) {
            this.statusContainer.innerHTML = '';
        }
    }

    resetSections() {
        this.videoInfo.classList.add('hidden');
        this.summarySection.classList.add('hidden');
        this.copySummaryBtn.classList.add('hidden'); // Hide copy button initially
        this.currentTranscript = '';
        this.currentVideoInfo = null;
        this.hideStatus();
        
        // Also ensure status container is completely reset if streaming UI replaced it
        const statusContainer = document.getElementById('status');
        if (statusContainer && statusContainer.innerHTML !== '') {
            // If there's streaming content, clear it and restore original structure
            statusContainer.innerHTML = '';
            statusContainer.classList.add('hidden');
        }
    }

    async copySummaryToClipboard() {
        try {
            // Get the summary text content (removing HTML formatting)
            const summaryElement = this.summaryText;
            const summaryContent = summaryElement.textContent || summaryElement.innerText || '';
            
            if (!summaryContent.trim()) {
                this.showError(this.t('noSummaryToCopy'));
                return;
            }

            // Copy to clipboard
            await navigator.clipboard.writeText(summaryContent);
            
            // Show feedback
            const copyBtn = this.copySummaryBtn;
            const copyBtnText = document.getElementById('copy-btn-text');
            const originalText = copyBtnText.textContent;
            
            // Change button appearance temporarily
            copyBtn.classList.remove('bg-blue-100', 'hover:bg-blue-200', 'text-blue-700');
            copyBtn.classList.add('bg-green-100', 'text-green-700');
            copyBtnText.textContent = this.t('copied');
            
            // Reset after 2 seconds
            setTimeout(() => {
                copyBtn.classList.remove('bg-green-100', 'text-green-700');
                copyBtn.classList.add('bg-blue-100', 'hover:bg-blue-200', 'text-blue-700');
                copyBtnText.textContent = originalText;
            }, 2000);
            
        } catch (err) {
            // Fallback for browsers that don't support clipboard API
            this.fallbackCopyToClipboard();
        }
    }

    fallbackCopyToClipboard() {
        try {
            const summaryElement = this.summaryText;
            const summaryContent = summaryElement.textContent || summaryElement.innerText || '';
            
            // Create a temporary textarea
            const textArea = document.createElement('textarea');
            textArea.value = summaryContent;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            
            // Select and copy
            textArea.focus();
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            
            // Show feedback
            const copyBtnText = document.getElementById('copy-btn-text');
            const originalText = copyBtnText.textContent;
            copyBtnText.textContent = this.t('copied');
            setTimeout(() => {
                copyBtnText.textContent = originalText;
            }, 2000);
            
        } catch (err) {
            this.showError(this.t('copyFailed'));
        }
    }

    showStreamingProgress(message) {
        // Create or update streaming progress UI
        const statusContainer = this.statusContainer;
        
        // Clear existing content
        statusContainer.innerHTML = '';
        statusContainer.classList.remove('hidden');

        // Create streaming progress container
        const progressContainer = document.createElement('div');
        progressContainer.className = 'bg-white rounded-lg shadow-lg p-6';
        progressContainer.innerHTML = `
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center space-x-4">
                    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                    <div class="text-lg font-medium text-gray-700" id="progress-message">${message}</div>
                </div>
                <button 
                    id="cancel-btn" 
                    class="px-3 py-1 text-sm bg-red-500 hover:bg-red-600 text-white rounded transition-colors"
                    title="Cancel current operation">
                    Cancel
                </button>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-2 mb-2">
                <div class="bg-blue-600 h-2 rounded-full transition-all duration-300" id="progress-bar" style="width: 0%"></div>
            </div>
            <div class="text-sm text-gray-500 text-center" id="progress-percentage">0%</div>
            <div class="mt-4 bg-gray-50 rounded-lg p-4 min-h-20" id="streaming-content" style="display: none;">
                <div class="text-sm text-gray-600" id="partial-content"></div>
            </div>
        `;
        
        statusContainer.appendChild(progressContainer);
        
        // Set up cancel button after creating the new container
        this.showCancelButton();
    }

    updateStreamingProgress(percentage, message) {
        const progressBar = document.getElementById('progress-bar');
        const progressMessage = document.getElementById('progress-message');
        const progressPercentage = document.getElementById('progress-percentage');
        
        if (progressBar) {
            progressBar.style.width = `${percentage}%`;
        }
        if (progressMessage) {
            progressMessage.textContent = message;
        }
        if (progressPercentage) {
            progressPercentage.textContent = `${Math.round(percentage)}%`;
        }
    }

    updateStreamingContent(partialContent) {
        const streamingContent = document.getElementById('streaming-content');
        const partialContentDiv = document.getElementById('partial-content');
        
        if (streamingContent && partialContentDiv && partialContent) {
            streamingContent.style.display = 'block';
            partialContentDiv.textContent = partialContent;
        }
    }

    showStreamingSummary() {
        // Show the summary section immediately when streaming starts
        this.summarySection.classList.remove('hidden');
        // Keep copy button hidden during streaming
        this.copySummaryBtn.classList.add('hidden');
        
        // Reset streaming trackers and state
        this.currentStreamingLength = 0;
        this.lastDisplayedContent = '';
        this.lastUpdateTime = 0;
        this.pendingContent = null;
        this.streamingState = null; // Reset streaming state for new session
        
        // Add a streaming indicator to the summary
        this.summaryText.innerHTML = `
            <div class="flex items-center space-x-3 mb-6 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200">
                <div class="flex space-x-1">
                    <div class="w-3 h-3 bg-blue-500 rounded-full animate-bounce"></div>
                    <div class="w-3 h-3 bg-blue-600 rounded-full animate-bounce" style="animation-delay: 0.1s"></div>
                    <div class="w-3 h-3 bg-indigo-500 rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
                </div>
                <div class="flex-1">
                    <div class="text-blue-800 font-semibold">🤖 AI is generating your summary...</div>
                    <div class="text-blue-600 text-sm mt-1">Your content is being processed in real-time</div>
                </div>
            </div>
            <div id="streaming-summary-content" class="prose max-w-none p-6 bg-white rounded-lg border border-gray-200 relative" style="height: 500px; overflow-y: auto;">
                <div class="streaming-content" style="line-height: 1.8; word-wrap: break-word;"></div>
                <div class="absolute top-2 right-2 text-xs text-green-500 font-medium bg-white bg-opacity-90 px-2 py-1 rounded shadow-sm">● Live</div>
            </div>
        `;
    }

    updateStreamingSummary(content) {
        const summaryContentDiv = document.getElementById('streaming-summary-content');
        if (!summaryContentDiv) return;
        
        // Get or create content container
        let contentContainer = summaryContentDiv.querySelector('.streaming-content');
        if (!contentContainer) {
            contentContainer = document.createElement('div');
            contentContainer.className = 'streaming-content';
            contentContainer.style.cssText = 'line-height: 1.8; word-wrap: break-word; font-family: inherit;';
            summaryContentDiv.appendChild(contentContainer);
            this.lastDisplayedContent = '';
            
            // Add CSS for cursor animation if not already added
            if (!document.getElementById('streaming-cursor-style')) {
                const style = document.createElement('style');
                style.id = 'streaming-cursor-style';
                style.textContent = `
                    @keyframes blink {
                        0%, 50% { opacity: 1; }
                        51%, 100% { opacity: 0; }
                    }
                    .typing-cursor {
                        animation: blink 1s infinite;
                    }
                `;
                document.head.appendChild(style);
            }
        }
        
        // Always use streaming display for new content
        if (content && content !== this.lastDisplayedContent) {
            this.displayWordByWordWithFormatting(contentContainer, this.lastDisplayedContent || '', '', content);
        }
    }
    
    applyFormattedContent(content) {
        const summaryContentDiv = document.getElementById('streaming-summary-content');
        if (!summaryContentDiv) return;
        
        const contentContainer = summaryContentDiv.querySelector('.streaming-content');
        if (!contentContainer) return;
        
        // Apply formatting to the full content
        const formattedContent = this.formatStreamingContent(content);
        
        // Use requestAnimationFrame for smooth, non-blocking update
        requestAnimationFrame(() => {
            contentContainer.innerHTML = formattedContent;
            // Auto-scroll to bottom smoothly
            this.autoScrollIfNeeded(summaryContentDiv);
        });
        
        this.lastDisplayedContent = content;
        this.currentStreamingLength = content.length;
        this.lastUpdateTime = Date.now();
    }

    displayWordByWordWithFormatting(container, existingContent, newPart, fullContent) {
        // Initialize streaming state if not exists
        if (!this.streamingState) {
            this.streamingState = {
                currentText: existingContent || '',
                displayedLength: 0,
                isStreaming: false
            };
        }
        
        // Create streaming container with cursor
        if (!container.querySelector('.streaming-text')) {
            container.innerHTML = `
                <div class="streaming-wrapper" style="position: relative;">
                    <div class="streaming-text"></div>
                    <span class="typing-cursor" style="display: inline-block; animation: blink 1s infinite; color: #3b82f6; margin-left: 2px;">▋</span>
                </div>
            `;
        }
        
        const streamingDiv = container.querySelector('.streaming-text');
        const cursor = container.querySelector('.typing-cursor');
        
        // Update the target text
        this.streamingState.currentText = fullContent;
        
        // Start streaming if not already streaming
        if (!this.streamingState.isStreaming) {
            this.streamingState.isStreaming = true;
            this.streamText(streamingDiv, cursor);
        }
    }
    
    streamText(textContainer, cursor) {
        const targetText = this.streamingState.currentText;
        const currentLength = this.streamingState.displayedLength;
        
        if (currentLength >= targetText.length) {
            // Streaming complete
            this.streamingState.isStreaming = false;
            cursor.style.display = 'none';
            this.lastDisplayedContent = targetText;
            return;
        }
        
        // Get next character or word chunk
        const nextChunk = this.getNextStreamingChunk(targetText, currentLength);
        let displayText = targetText.substring(0, currentLength + nextChunk.length);
        
        // Filter for language consistency (especially for Arabic mode)
        displayText = this.filterLanguageConsistency(displayText);
        
        // Apply real-time formatting while streaming
        const formattedText = this.formatStreamingContentRealtime(displayText);
        textContainer.innerHTML = formattedText;
        this.streamingState.displayedLength += nextChunk.length;
        
        // Auto-scroll
        this.autoScrollIfNeeded(textContainer.closest('#streaming-summary-content'));
        
        // Schedule next update
        const delay = this.getStreamingDelay(nextChunk);
        setTimeout(() => this.streamText(textContainer, cursor), delay);
    }
    
    filterLanguageConsistency(text) {
        // Apply language-specific filtering only when needed
        if (this.currentLanguage === 'ar' && text) {
            // Check if we're still in the early stages of streaming for Arabic
            if (text.length < 300) {
                // Count Arabic vs English characters in the first part
                const arabicChars = (text.match(/[\u0600-\u06FF]/g) || []).length;
                const englishChars = (text.match(/[A-Za-z]/g) || []).length;
                
                // If it's mostly English in the first 200 characters, show Arabic loading message
                if (englishChars > arabicChars && englishChars > 20) {
                    return 'جاري إنتاج الملخص باللغة العربية...'; // "Generating summary in Arabic..."
                }
            }
            
            // If it starts with common English phrases but we want Arabic, filter them out
            const englishStartPatterns = [
                /^(Here|This|The|Based|According|In|As|From|With|Website|Content|Summary)/i,
                /^(# Website|# Content|# Analysis|# Summary)/i
            ];
            
            for (const pattern of englishStartPatterns) {
                if (pattern.test(text.trim()) && text.length < 100) {
                    return 'جاري إنتاج الملخص...';
                }
            }
        }
        
        // For English or when filtering is not needed, return text as-is for smooth streaming
        return text;
    }
    
    getNextStreamingChunk(text, currentPos) {
        if (currentPos >= text.length) return '';
        
        // Stream character by character for very smooth ChatGPT-like experience
        const char = text[currentPos];
        
        // Handle special characters that should appear together
        if (char === '\n') {
            // Line breaks
            return char;
        } else if (char === ' ') {
            // Spaces - but include multiple consecutive spaces together
            let endPos = currentPos;
            while (endPos < text.length && text[endPos] === ' ') {
                endPos++;
            }
            return text.substring(currentPos, endPos);
        } else if (char.match(/[#*•]/)) {
            // Formatting characters - include the whole formatting sequence
            let endPos = currentPos;
            while (endPos < text.length && text[endPos].match(/[#*•]/)) {
                endPos++;
            }
            return text.substring(currentPos, endPos || currentPos + 1);
        } else {
            // Regular character - stream one by one for smoothness
            return char;
        }
    }
    
    getStreamingDelay(chunk) {
        // Optimized ChatGPT-style timing for smooth streaming
        if (chunk.includes('\n')) return 150; // Moderate pause at line breaks
        if (chunk.match(/[.!?]/)) return 200; // Pause at sentence endings
        if (chunk.match(/[,;:]/)) return 100; // Short pause at punctuation
        if (chunk === ' ') return 15; // Very quick for spaces
        if (chunk.length > 5) return 30; // Fast for longer words
        if (chunk.length > 2) return 25; // Fast for medium words
        return 20; // Fast for short chunks - smooth like ChatGPT
    }
    


    displayWordsOneByOne(container, existingContent, newWords) {
        // Legacy method - redirect to new implementation
        const newPart = newWords.join(' ');
        const fullContent = existingContent + (existingContent ? ' ' : '') + newPart;
        this.displayWordByWordWithFormatting(container, existingContent, newPart, fullContent);
    }

    autoScrollIfNeeded(element) {
        // Only scroll if content is overflowing and user is near bottom
        const isOverflowing = element.scrollHeight > element.clientHeight;
        const isNearBottom = element.scrollTop + element.clientHeight >= element.scrollHeight - 100;
        
        if (isOverflowing && isNearBottom) {
            // Use requestAnimationFrame for smoother scrolling
            requestAnimationFrame(() => {
                element.scrollTop = element.scrollHeight;
            });
        }
    }

    animateNewContent(element, fullContent, previousLength) {
        // Get the new part of the content
        const newPart = fullContent.slice(previousLength);
        
        // Break large chunks into very small pieces to prevent UI jumping
        const maxChunkSize = 50; // Very small chunks to minimize jumping
        if (newPart.length > maxChunkSize) {
            // Split large chunks into smaller pieces and animate them sequentially
            this.animateInSmallChunks(element, fullContent, previousLength, maxChunkSize);
            return;
        }
        
        // If the element doesn't have a content container, create one
        let contentContainer = element.querySelector('.typing-content');
        let cursor = element.querySelector('.typing-cursor');
        
        if (!contentContainer) {
            // Create stable structure once with fixed dimensions to prevent jumping
            element.innerHTML = `
                <div class="typing-content" style="min-height: 350px; padding-bottom: 20px; box-sizing: border-box; overflow-wrap: break-word;"></div>
                <span class="typing-cursor animate-pulse text-blue-500 font-bold">|</span>
                <div class="absolute top-2 right-2 text-xs text-green-500 font-medium">● Live</div>
            `;
            contentContainer = element.querySelector('.typing-content');
            cursor = element.querySelector('.typing-cursor');
            
            // Set a stable line-height and prevent reflowing with better CSS
            contentContainer.style.cssText += `
                line-height: 1.6;
                overflow-anchor: none;
                contain: layout style;
                word-wrap: break-word;
                hyphens: auto;
            `;
        }
        
        // Set the old content immediately without re-rendering everything
        const oldFormatted = this.formatStreamingContent(fullContent.slice(0, previousLength));
        contentContainer.innerHTML = oldFormatted;
        
        // Create a temporary span for the new content animation
        const newContentSpan = document.createElement('span');
        contentContainer.appendChild(newContentSpan);
        
        // Animate only the new content using requestAnimationFrame for smooth performance
        let animatedLength = 0;
        let lastUpdate = Date.now();
        const targetSpeed = 80; // Increased speed for smoother experience
        
        const animate = () => {
            const now = Date.now();
            const deltaTime = now - lastUpdate;
            
            // Update every ~20ms for smooth animation (50fps)
            if (deltaTime >= 20) {
                if (animatedLength < newPart.length) {
                    // Update multiple characters based on time elapsed for consistent speed
                    const charsToAdd = Math.max(1, Math.floor((deltaTime / 1000) * targetSpeed));
                    animatedLength = Math.min(animatedLength + charsToAdd, newPart.length);
                    
                    // Only update the new span, not the entire DOM
                    newContentSpan.textContent = newPart.slice(0, animatedLength);
                    lastUpdate = now;
                    
                    // Only scroll when needed (content overflows)
                    this.smartScroll(element);
                    
                    requestAnimationFrame(animate);
                } else {
                    // Animation complete: merge content and clean up
                    const finalFormatted = this.formatStreamingContent(fullContent);
                    contentContainer.innerHTML = finalFormatted;
                    cursor.style.display = 'none';
                    
                    // Final scroll only if needed
                    this.smartScroll(element);
                    
                    // Show cursor again for next update
                    setTimeout(() => {
                        if (cursor) cursor.style.display = 'inline';
                    }, 300);
                }
            } else {
                requestAnimationFrame(animate);
            }
        };
        
        requestAnimationFrame(animate);
    }

    animateInSmallChunks(element, fullContent, startPosition, chunkSize) {
        // Break the content into smaller, manageable chunks to prevent UI jumping
        let currentPosition = startPosition;
        
        const animateNextChunk = () => {
            if (currentPosition >= fullContent.length) {
                return; // Animation complete
            }
            
            // Calculate the next chunk end position (smaller chunks)
            const nextChunkEnd = Math.min(currentPosition + chunkSize, fullContent.length);
            
            // Directly update content without recursive animation calls
            const contentToShow = fullContent.slice(0, nextChunkEnd);
            this.displayStreamingContent(element, contentToShow, true);
            
            // Only scroll when chunk causes overflow
            this.smartScroll(element);
            
            // Update position for next chunk
            currentPosition = nextChunkEnd;
            
            // Schedule next chunk animation with shorter delay
            if (currentPosition < fullContent.length) {
                setTimeout(animateNextChunk, 100); // Faster chunking
            } else {
                // Final update without cursor
                this.displayStreamingContent(element, fullContent, false);
            }
        };
        
        animateNextChunk();
    }

    smartScroll(contentElement) {
        // Only scroll if content actually overflows and user is near bottom
        const container = contentElement.parentElement || contentElement;
        const isOverflowing = container.scrollHeight > container.clientHeight;
        
        if (isOverflowing) {
            // Check if user is already near the bottom (within 100px)
            const isNearBottom = (container.scrollTop + container.clientHeight) >= (container.scrollHeight - 100);
            
            // Only auto-scroll if user was already near bottom (don't interrupt manual scrolling)
            if (isNearBottom) {
                container.scrollTo({
                    top: container.scrollHeight,
                    behavior: 'smooth'
                });
            }
        }
    }

    displayStreamingContent(element, content, showCursor = false) {
        // Use stable DOM structure to prevent flashing
        let contentContainer = element.querySelector('.typing-content');
        let cursor = element.querySelector('.typing-cursor');
        
        if (!contentContainer) {
            // Create stable structure once
            element.innerHTML = `
                <div class="typing-content"></div>
                <span class="typing-cursor animate-pulse text-blue-500 font-bold">|</span>
                <div class="absolute top-2 right-2 text-xs text-green-500 font-medium">● Live</div>
            `;
            contentContainer = element.querySelector('.typing-content');
            cursor = element.querySelector('.typing-cursor');
        }
        
        // Only update content, not the entire structure
        const formattedContent = this.formatStreamingContent(content);
        contentContainer.innerHTML = formattedContent;
        
        // Control cursor visibility without DOM manipulation
        cursor.style.display = showCursor ? 'inline' : 'none';
    }

    formatStreamingContent(content) {
        if (!content) return '';
        
        // Split content into lines for proper processing
        const lines = content.split('\n');
        const formatted = [];
        
        for (let i = 0; i < lines.length; i++) {
            let line = lines[i].trim();
            if (!line) {
                formatted.push('<br/>');
                continue;
            }
            
            // Headers
            if (line.startsWith('### ')) {
                formatted.push(`<h3 class="text-lg font-semibold text-gray-800 mb-2 mt-4">${line.substring(4)}</h3>`);
            } else if (line.startsWith('## ')) {
                formatted.push(`<h2 class="text-xl font-bold text-gray-800 mb-3 mt-6">${line.substring(3)}</h2>`);
            } else if (line.startsWith('# ')) {
                formatted.push(`<h1 class="text-2xl font-bold text-gray-900 mb-4 mt-2">${line.substring(2)}</h1>`);
            }
            // Bullet points with bold
            else if (line.match(/^•\s*\*\*(.*?)\*\*\s*-\s*(.*)$/)) {
                const match = line.match(/^•\s*\*\*(.*?)\*\*\s*-\s*(.*)$/);
                formatted.push(`<div class="mb-3 ml-4 pl-2 border-l-2 border-blue-300"><strong class="text-gray-900 font-semibold">${match[1]}</strong> - <span class="text-gray-700">${this.formatInlineMarkdown(match[2])}</span></div>`);
            }
            // Regular bullet points
            else if (line.startsWith('• ')) {
                formatted.push(`<div class="mb-2 ml-4 text-gray-700">• ${this.formatInlineMarkdown(line.substring(2))}</div>`);
            }
            // Regular paragraphs
            else {
                formatted.push(`<p class="mb-3 text-gray-800 leading-relaxed">${this.formatInlineMarkdown(line)}</p>`);
            }
        }
        
        return formatted.join('');
    }
    
    formatInlineMarkdown(text) {
        if (!text) return '';
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-900">$1</strong>')
            .replace(/\*([^*]+)\*/g, '<em class="italic">$1</em>');
    }
    
    formatStreamingContentRealtime(content) {
        if (!content) return '';
        
        // Split content into lines for real-time processing
        const lines = content.split('\n');
        const formatted = [];
        
        for (let i = 0; i < lines.length; i++) {
            let line = lines[i];
            const trimmedLine = line.trim();
            
            // Handle empty lines
            if (!trimmedLine) {
                formatted.push('<br/>');
                continue;
            }
            
            // Check for headers (including incomplete ones being typed)
            if (trimmedLine.startsWith('### ')) {
                const headerText = trimmedLine.substring(4);
                formatted.push(`<h3 class="text-lg font-semibold text-gray-800 mb-2 mt-4">${this.formatInlineMarkdownRealtime(headerText)}</h3>`);
            } else if (trimmedLine.startsWith('## ')) {
                const headerText = trimmedLine.substring(3);
                formatted.push(`<h2 class="text-xl font-bold text-gray-800 mb-3 mt-6">${this.formatInlineMarkdownRealtime(headerText)}</h2>`);
            } else if (trimmedLine.startsWith('# ')) {
                const headerText = trimmedLine.substring(2);
                formatted.push(`<h1 class="text-2xl font-bold text-gray-900 mb-4 mt-2">${this.formatInlineMarkdownRealtime(headerText)}</h1>`);
            }
            // Handle bullet points with bold (including incomplete formatting)
            else if (trimmedLine.match(/^•\s*\*\*(.*?)(\*\*.*)?$/)) {
                const match = trimmedLine.match(/^•\s*\*\*(.*?)(\*\*(.*))?$/);
                if (match[3] !== undefined) {
                    // Complete bullet with bold and description
                    formatted.push(`<div class="mb-3 ml-4 pl-2 border-l-2 border-blue-300"><strong class="text-gray-900 font-semibold">${match[1]}</strong> - <span class="text-gray-700">${this.formatInlineMarkdownRealtime(match[3])}</span></div>`);
                } else {
                    // Incomplete bold formatting - show as bold in progress
                    formatted.push(`<div class="mb-3 ml-4 pl-2 border-l-2 border-blue-300"><strong class="text-gray-900 font-semibold">${match[1]}</strong></div>`);
                }
            }
            // Regular bullet points
            else if (trimmedLine.startsWith('• ')) {
                const bulletText = trimmedLine.substring(2);
                formatted.push(`<div class="mb-2 ml-4 text-gray-700">• ${this.formatInlineMarkdownRealtime(bulletText)}</div>`);
            }
            // Handle emojis and special sections
            else if (trimmedLine.match(/^💡|^📝|^🔍|^⚡|^🎯|^📊/)) {
                formatted.push(`<div class="mb-3 p-3 bg-blue-50 rounded-lg border-l-4 border-blue-400"><span class="text-blue-800 font-medium">${this.formatInlineMarkdownRealtime(trimmedLine)}</span></div>`);
            }
            // Regular paragraphs
            else {
                formatted.push(`<p class="mb-3 text-gray-800 leading-relaxed">${this.formatInlineMarkdownRealtime(trimmedLine)}</p>`);
            }
        }
        
        return formatted.join('');
    }
    
    formatInlineMarkdownRealtime(text) {
        if (!text) return '';
        
        // Handle complete bold formatting
        let formatted = text.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-900">$1</strong>');
        
        // Handle incomplete bold formatting (when user is still typing)
        formatted = formatted.replace(/\*\*([^*]+)$/g, '<strong class="font-semibold text-gray-900">$1</strong>');
        
        // Handle complete italic formatting
        formatted = formatted.replace(/\*([^*]+)\*/g, '<em class="italic">$1</em>');
        
        // Handle incomplete italic formatting
        formatted = formatted.replace(/\*([^*\s]+)$/g, '<em class="italic">$1</em>');
        
        return formatted;
    }
}

// Initialize the app when the page loads (prevent multiple instances)
document.addEventListener('DOMContentLoaded', () => {
    if (!window.youtubeApp) {
        window.youtubeApp = new YouTubeTranscriptApp();
    }
});