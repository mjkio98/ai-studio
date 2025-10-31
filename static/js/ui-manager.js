(function (global) {
    const uiMixin = {
        initializeComponents() {
            // Safety check - only initialize if we have relevant elements on the current page
            if (typeof window.PageUtils !== 'undefined') {
                const hasRelevantElements = window.PageUtils.hasAnyElement([
                    'youtube-url', 'webpage-url', 'single-mode-btn', 'multi-mode-btn'
                ]);
                if (!hasRelevantElements) {
                    console.log('UI Manager: No relevant elements found, skipping initialization');
                    return;
                }
            }

            // Get DOM elements (with null checks)
            this.urlInput = document.getElementById('youtube-url');
            this.summarizeVideoBtn = document.getElementById('summarize-video-btn');

            // Multi-video elements
            this.singleModeBtn = document.getElementById('single-mode-btn');
            this.multiModeBtn = document.getElementById('multi-mode-btn');
            this.webpageModeBtn = document.getElementById('webpage-mode-btn');
            this.chatAgentModeBtn = document.getElementById('chat-agent-mode-btn');
            this.singleVideoSection = document.getElementById('single-video-section');
            this.multiVideoSection = document.getElementById('multi-video-section');
            this.webpageSection = document.getElementById('webpage-section');
            this.chatAgentSection = document.getElementById('chat-agent-section');
            this.addUrlBtn = document.getElementById('add-url-btn');
            this.summarizeMultiBtn = document.getElementById('summarize-multi-btn');
            this.urlInputsContainer = document.getElementById('url-inputs-container');

            // Webpage elements
            this.webpageUrlInput = document.getElementById('webpage-url');
            this.analyzeWebpageBtn = document.getElementById('analyze-webpage-btn');

            this.isMultiMode = false;
            this.isWebpageMode = false;
            this.isChatAgentMode = false;

            // Initialize existing remove buttons
            if (this.urlInputsContainer) {
                this.initializeRemoveButtons();
            }

            this.statusContainer = document.getElementById('status-container');
            this.loadingState = document.getElementById('loading-state');
            this.errorState = document.getElementById('error-state');
            this.loadingText = document.getElementById('loading-text');
            this.errorMessage = document.getElementById('error-message');

            this.videoInfo = document.getElementById('video-info');
            this.webpageInfo = document.getElementById('webpage-info');
            this.videoThumbnail = document.getElementById('video-thumbnail');
            this.videoTitle = document.getElementById('video-title');
            this.videoChannel = document.getElementById('video-channel');

            this.summarySection = document.getElementById('summary-section');
            this.summaryText = document.getElementById('summary-text');
            this.copySummaryBtn = document.getElementById('copy-summary-btn');
            this.cancelBtn = document.getElementById('cancel-btn');

            // Bind event listeners (with null checks)
            if (this.summarizeVideoBtn) {
                this.summarizeVideoBtn.addEventListener('click', () => this.summarizeVideoDirectly());
            }
            if (this.summarizeMultiBtn) {
                this.summarizeMultiBtn.addEventListener('click', () => this.summarizeMultipleVideos());
            }

            // Mode switching (with null checks)
            if (this.singleModeBtn) {
                this.singleModeBtn.addEventListener('click', () => this.switchToSingleMode());
            }
            if (this.multiModeBtn) {
                this.multiModeBtn.addEventListener('click', () => this.switchToMultiMode());
            }
            if (this.webpageModeBtn) {
                this.webpageModeBtn.addEventListener('click', () => this.switchToWebpageMode());
            }
            if (this.chatAgentModeBtn) {
                this.chatAgentModeBtn.addEventListener('click', () => this.switchToChatAgentMode());
            }

            // Add URL functionality (with null check)
            if (this.addUrlBtn) {
                this.addUrlBtn.addEventListener('click', () => this.addUrlInput());
            }

            // Webpage functionality (with null check)
            if (this.analyzeWebpageBtn) {
                this.analyzeWebpageBtn.addEventListener('click', () => this.analyzeWebpage());
            }

            // Copy button functionality (with null check)
            if (this.copySummaryBtn) {
                this.copySummaryBtn.addEventListener('click', () => this.copySummaryToClipboard());
            }

            // URL input event listeners (with null checks)
            if (this.urlInput) {
                this.urlInput.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') this.summarizeVideoDirectly();
                });

                this.urlInput.addEventListener('input', () => {
                    this.resetSections();
                });
            }

            if (this.webpageUrlInput) {
                this.webpageUrlInput.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') this.analyzeWebpage();
                });

                this.webpageUrlInput.addEventListener('input', () => {
                    this.resetSections();
                });
            }

            // Default to single mode layout if the relevant sections exist
            if (this.singleModeBtn && this.singleVideoSection) {
                this.switchToSingleMode();
            } else {
                this.resetSections();
            }
        },

        switchToSingleMode() {
            this.isMultiMode = false;
            this.isWebpageMode = false;
            this.isChatAgentMode = false;

            // Update button states
            this.singleModeBtn.classList.add('active');
            this.multiModeBtn.classList.remove('active');
            this.webpageModeBtn.classList.remove('active');
            if (this.chatAgentModeBtn) {
                this.chatAgentModeBtn.classList.remove('active');
            }

            // Update section visibility
            this.singleVideoSection.classList.remove('hidden');
            this.multiVideoSection.classList.add('hidden');
            this.webpageSection.classList.add('hidden');
            if (this.chatAgentSection) {
                this.chatAgentSection.classList.add('hidden');
            }
            this.resetSections();

            // Single video mode - where shorts generation happens
        },

        switchToMultiMode() {
            // Cancel any active shorts generation task when leaving single video section
            this.cancelActiveTaskIfExists();
            
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

            this.resetSections();
        },

        switchToWebpageMode() {
            // Cancel any active shorts generation task when leaving single video section
            this.cancelActiveTaskIfExists();
            
            this.isMultiMode = false;
            this.isWebpageMode = true;
            this.isChatAgentMode = false;

            // Update button states
            this.webpageModeBtn.classList.add('active');
            this.singleModeBtn.classList.remove('active');
            this.multiModeBtn.classList.remove('active');
            if (this.chatAgentModeBtn) {
                this.chatAgentModeBtn.classList.remove('active');
            }

            // Update section visibility
            this.singleVideoSection.classList.add('hidden');
            this.multiVideoSection.classList.add('hidden');
            this.webpageSection.classList.remove('hidden');
            if (this.chatAgentSection) {
                this.chatAgentSection.classList.add('hidden');
            }
            this.resetSections();
        },

        switchToChatAgentMode() {
            // Cancel any active tasks when switching modes
            this.cancelActiveTaskIfExists();
            
            this.isMultiMode = false;
            this.isWebpageMode = false;
            this.isChatAgentMode = true;

            // Update button states
            if (this.chatAgentModeBtn) {
                this.chatAgentModeBtn.classList.add('active');
            }
            this.singleModeBtn.classList.remove('active');
            this.multiModeBtn.classList.remove('active');
            this.webpageModeBtn.classList.remove('active');

            // Update section visibility
            this.singleVideoSection.classList.add('hidden');
            this.multiVideoSection.classList.add('hidden');
            this.webpageSection.classList.add('hidden');
            if (this.chatAgentSection) {
                this.chatAgentSection.classList.remove('hidden');
            }
            this.resetSections();
        },

        addUrlInput() {
            const container = this.urlInputsContainer;
            const currentCount = container.children.length;

            if (currentCount >= 4) {
                this.showError(this.t('errors.maxVideos'));
                return;
            }

            const urlCount = currentCount + 1;
            const englishPlaceholder = `https://www.youtube.com/watch?v=... (Video ${urlCount})`;
            const arabicPlaceholder = `https://www.youtube.com/watch?v=... (فيديو ${urlCount})`;
            const placeholder = this.currentLanguage === 'ar' ? arabicPlaceholder : englishPlaceholder;

            const div = document.createElement('div');
            div.className = 'input-row url-input-row mb-3';
            div.innerHTML = `
                <input 
                    type="url" 
                    class="youtube-url-multi form-control"
                    placeholder="${placeholder}"
                    data-en="${englishPlaceholder}"
                    data-ar="${arabicPlaceholder}"
                >
                <button type="button" class="btn btn-outline-danger btn-sm ms-2 remove-url-btn" title="${this.currentLanguage === 'ar' ? 'إزالة الرابط' : 'Remove URL'}">
                    <i class="fas fa-times"></i>
                </button>
            `;

            const removeBtn = div.querySelector('.remove-url-btn');
            removeBtn.addEventListener('click', () => {
                div.remove();
                this.updateUrlPlaceholders();
                this.updateAddButtonState();
            });

            container.appendChild(div);
            this.updateUrlPlaceholders();
            this.updateAddButtonState();
        },

        updateUrlPlaceholders() {
            const inputs = this.urlInputsContainer.querySelectorAll('.youtube-url-multi');
            inputs.forEach((input, index) => {
                const englishPlaceholder = `https://www.youtube.com/watch?v=... (Video ${index + 1})`;
                const arabicPlaceholder = `https://www.youtube.com/watch?v=... (فيديو ${index + 1})`;

                input.setAttribute('data-en', englishPlaceholder);
                input.setAttribute('data-ar', arabicPlaceholder);

                input.placeholder = this.currentLanguage === 'ar' ? arabicPlaceholder : englishPlaceholder;
            });
        },

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
        },

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
        },

        showLoading(message) {
            this.loadingText.textContent = message;
            this.statusContainer.classList.remove('hidden');
            this.loadingState.classList.remove('hidden');
            this.errorState.classList.add('hidden');
        },

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
        },

        showInfo(message) {
            this.loadingText.textContent = message;
            this.statusContainer.classList.remove('hidden');
            this.loadingState.classList.remove('hidden');
            this.errorState.classList.add('hidden');

            // Auto-hide info messages after 3 seconds
            setTimeout(() => {
                this.hideStatus();
            }, 3000);
        },

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
        },

        resetSections() {
            if (this.videoInfo) {
                this.videoInfo.classList.add('hidden');
            }
            if (this.webpageInfo) {
                this.webpageInfo.classList.add('hidden');
                this.webpageInfo.innerHTML = '';
            }
            if (this.summarySection) {
                this.summarySection.classList.add('hidden');
            }
            if (this.copySummaryBtn) {
                this.copySummaryBtn.classList.add('hidden'); // Hide copy button initially
            }
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
        },

        enableButtons() {
            // Re-enable buttons based on current mode and available elements
            if (this.isWebpageMode && this.analyzeWebpageBtn) {
                this.analyzeWebpageBtn.disabled = false;
            } 
            
            if (this.isMultiMode && this.summarizeMultiBtn) {
                this.summarizeMultiBtn.disabled = false;
            } 
            
            if (!this.isWebpageMode && !this.isMultiMode && this.summarizeVideoBtn) {
                this.summarizeVideoBtn.disabled = false;
            }

            // Handle separate page scenarios by checking what buttons exist
            if (window.PageUtils) {
                if (window.PageUtils.hasElement('summarize-video-btn') && this.summarizeVideoBtn) {
                    this.summarizeVideoBtn.disabled = false;
                }
                if (window.PageUtils.hasElement('summarize-multi-btn') && this.summarizeMultiBtn) {
                    this.summarizeMultiBtn.disabled = false;
                }
                if (window.PageUtils.hasElement('analyze-webpage-btn') && this.analyzeWebpageBtn) {
                    this.analyzeWebpageBtn.disabled = false;
                }
            }
        },

        showReadyForNext() {
            // Add a subtle visual cue that user can process another item
            setTimeout(() => {
                // Focus the appropriate input field to indicate readiness
                if (this.urlInput && window.PageUtils && window.PageUtils.hasElement('youtube-url')) {
                    this.urlInput.style.borderColor = '#22c55e';
                    this.urlInput.placeholder = this.urlInput.getAttribute('data-' + this.currentLanguage) || 'Enter next YouTube URL...';
                    setTimeout(() => {
                        this.urlInput.style.borderColor = '';
                    }, 3000);
                } else if (this.webpageUrlInput && window.PageUtils && window.PageUtils.hasElement('webpage-url')) {
                    this.webpageUrlInput.style.borderColor = '#22c55e';
                    this.webpageUrlInput.placeholder = this.webpageUrlInput.getAttribute('data-' + this.currentLanguage) || 'Enter next webpage URL...';
                    setTimeout(() => {
                        this.webpageUrlInput.style.borderColor = '';
                    }, 3000);
                }

                // Show a brief success message
                this.showInfo(this.t('readyForNext') || 'Ready to process another item!');
            }, 1000);
        },

        // Cancel active task when navigating away from shorts generation
        cancelActiveTaskIfExists() {
            if (this.currentTaskId && typeof this.cancelCurrentTask === 'function') {
                console.log('🚫 Cancelling active task due to section navigation:', this.currentTaskId);
                this.cancelCurrentTask();
                
                // Show brief notification
                if (this.showInfo) {
                    this.showInfo('Cancelled active shorts generation task', 2000);
                }
            }
            
            // Also clear any stored tasks
            if (typeof this.clearActiveTask === 'function') {
                this.clearActiveTask();
            }
        }
    };

    global.YouTubeTranscriptAppMixins = global.YouTubeTranscriptAppMixins || [];
    global.YouTubeTranscriptAppMixins.push(uiMixin);
})(window);
