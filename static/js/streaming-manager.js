(function (global) {
    const streamingMixin = {
        // Persistent task tracking methods
        storeActiveTask(taskId, taskType = 'shorts') {
            const taskInfo = {
                taskId: taskId,
                taskType: taskType,
                startTime: Date.now(),
                section: 'shorts' // Track which section started the task
            };
            localStorage.setItem('activeTask', JSON.stringify(taskInfo));
        },

        getActiveTask() {
            const stored = localStorage.getItem('activeTask');
            if (stored) {
                try {
                    return JSON.parse(stored);
                } catch (e) {
                    this.clearActiveTask();
                    return null;
                }
            }
            return null;
        },

        clearActiveTask() {
            localStorage.removeItem('activeTask');
        },

        // Check for active tasks when returning to a section or page
        async checkAndRestoreActiveTask() {
            const activeTask = this.getActiveTask();
            if (activeTask && activeTask.taskId && activeTask.section === 'shorts') {
                const taskAge = Date.now() - activeTask.startTime;
                const maxTaskAge = 30 * 60 * 1000; // 30 minutes
                
                // Check if task is too old (likely expired)
                if (taskAge > maxTaskAge) {
                    console.log('� Task too old, clearing stored task');
                    this.clearActiveTask();
                    return;
                }
                
                console.log('�🔄 Found active shorts generation task, attempting to restore:', activeTask.taskId);
                
                // Show a brief notification that we're restoring the task
                if (this.showInfo) {
                    this.showInfo('Reconnecting to your active shorts generation...', 3000);
                }
                
                // Check if task is still active by trying to connect
                try {
                    await this.reconnectToTask(activeTask.taskId);
                    console.log('✅ Successfully reconnected to task');
                } catch (error) {
                    console.log('❌ Task no longer active, clearing stored task:', error.message);
                    this.clearActiveTask();
                    
                    // Hide progress UI since there's no active task
                    const progressContainer = document.getElementById('progress-container');
                    if (progressContainer) {
                        progressContainer.style.display = 'none';
                    }
                    
                    if (this.showInfo) {
                        this.showInfo('Previous task has completed or expired.', 3000);
                    }
                }
            }
        },

        async reconnectToTask(taskId) {
            console.log('🔗 Reconnecting to task:', taskId);
            this.currentTaskId = taskId;
            this.taskCancelled = false;
            
            // Ensure we're on the correct page/section for shorts
            this.ensureShortsSection();
            
            // Initialize progress UI components
            this.initializeProgressUI();
            
            // Show progress indicator immediately with stepper
            this.updateProgress(0, 'Reconnecting to active task...');
            
            // Show cancel button
            this.showCancelButton();
            
            // Try to connect to the progress stream
            return this.listenToProgress(taskId);
        },

        ensureShortsSection() {
            // Make sure we're in the single video section (where shorts generation happens)
            const singleVideoSection = document.getElementById('single-video-section');
            const multiVideoSection = document.getElementById('multi-video-section');
            const webpageSection = document.getElementById('webpage-section');
            
            if (singleVideoSection) {
                singleVideoSection.classList.remove('hidden');
            }
            if (multiVideoSection) {
                multiVideoSection.classList.add('hidden');
            }
            if (webpageSection) {
                webpageSection.classList.add('hidden');
            }
            
            // Update navigation button states
            const singleModeBtn = document.getElementById('single-mode-btn');
            const multiModeBtn = document.getElementById('multi-mode-btn');
            const webpageModeBtn = document.getElementById('webpage-mode-btn');
            
            if (singleModeBtn) singleModeBtn.classList.add('active');
            if (multiModeBtn) multiModeBtn.classList.remove('active');
            if (webpageModeBtn) webpageModeBtn.classList.remove('active');
        },

        initializeProgressUI() {
            // Ensure all progress UI elements are visible and properly initialized
            const progressContainer = document.getElementById('progress-container');
            const stepperProgress = document.getElementById('stepper-progress');
            const progressMessage = document.getElementById('progress-message');
            const progressPercentage = document.getElementById('progress-percentage');
            
            if (progressContainer) {
                progressContainer.style.display = 'block';
                progressContainer.classList.remove('hidden');
            }
            
            if (stepperProgress) {
                stepperProgress.style.display = 'block';
                stepperProgress.classList.remove('hidden');
            }
            
            // Initialize stepper to first step if not already set
            if (!document.querySelector('.stepper-item.active')) {
                const firstStep = document.getElementById('step-1');
                if (firstStep) {
                    firstStep.classList.add('active');
                    firstStep.classList.remove('pending');
                }
            }
            
            // Ensure progress text elements are visible
            if (progressMessage) {
                progressMessage.style.display = 'block';
                progressMessage.innerHTML = 'Initializing...';
            }
            
            if (progressPercentage) {
                progressPercentage.style.display = 'block';
                progressPercentage.textContent = '0%';
            }
        },

        async listenToProgress(taskId) {
            // Track current task for cancellation
            this.currentTaskId = taskId;
            this.taskCancelled = false; // Reset cancellation flag for new task
            this.showCancelButton();

            // Task will be cancelled if user navigates away

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
                            this.clearActiveTask(); // Clear stored task on completion
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
                            this.clearActiveTask(); // Clear stored task on cancellation
                            this.hideCancelButton();
                            this.showError(this.t('cancelled'));
                            reject(new Error('Task cancelled'));
                        } else if (progress.status === 'error') {
                            eventSource.close();
                            this.currentEventSource = null;
                            this.currentTaskId = null;
                            this.clearActiveTask(); // Clear stored task on error
                            this.hideCancelButton();
                            
                            // Show error in stepper progress indicator
                            this.showStepperError(progress.error || 'Analysis failed');
                            
                            // Also show traditional error for compatibility
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
                    
                    // Check if this was a reconnection attempt
                    const activeTask = this.getActiveTask();
                    const isReconnecting = activeTask && activeTask.taskId === taskId;
                    
                    if (isReconnecting) {
                        // This might be a completed task, clear it
                        console.log('🔌 Connection failed during reconnection - task may be completed');
                        this.clearActiveTask();
                        this.currentTaskId = null;
                        this.hideCancelButton();
                        
                        // Hide progress UI
                        const progressContainer = document.getElementById('progress-container');
                        if (progressContainer) {
                            progressContainer.style.display = 'none';
                        }
                        
                        reject(new Error('Task no longer available - may have completed'));
                    } else {
                        // New task connection failed
                        this.currentTaskId = null;
                        this.clearActiveTask();
                        this.hideCancelButton();
                        
                        // Show error in stepper progress indicator
                        this.showStepperError('Connection to progress stream failed');
                        
                        // Also show traditional error for compatibility
                        this.showError('Connection to progress stream failed');
                        reject(error);
                    }
                };

                // Timeout after 5 minutes
                setTimeout(() => {
                    if (eventSource.readyState !== EventSource.CLOSED) {
                        eventSource.close();
                        this.currentEventSource = null;
                        this.currentTaskId = null;
                        this.hideCancelButton();
                        // Show timeout error in stepper progress indicator
                        this.showStepperError('Analysis timed out - please try again');
                        
                        // Also show traditional error for compatibility
                        this.showError('Analysis timed out');
                        reject(new Error('Timeout'));
                    }
                }, 300000);
            });
        },

        async cancelCurrentTask() {
            console.log('🚫 DEBUG: cancelCurrentTask called');
            console.log('🚫 DEBUG: Current task ID:', this.currentTaskId);
            console.log('🚫 DEBUG: Current event source:', this.currentEventSource);
            
            // Set flag to ignore any further progress updates
            this.taskCancelled = true;
            console.log('🚫 DEBUG: Task cancelled flag set to true');

            // Clean up streaming first - this will trigger EventSource error handler
            if (this.currentEventSource) {
                this.currentEventSource.close();
                this.currentEventSource = null;
            }

            // Handle streaming tasks (webpage analysis & video processing)
            if (this.currentTaskId) {
                const taskIdToCancel = this.currentTaskId;
                this.currentTaskId = null; // Clear immediately to prevent race conditions
                this.clearActiveTask(); // Clear stored task

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
        },

        showCancelButton() {
            console.log('🚫 DEBUG: showCancelButton called in streaming-manager');
            // Re-get the cancel button reference since it might have been recreated by showStreamingProgress
            this.cancelBtn = document.getElementById('cancel-btn');
            console.log('🚫 DEBUG: Cancel button element:', this.cancelBtn);
            if (this.cancelBtn) {
                console.log('🚫 DEBUG: Before - Button classes:', this.cancelBtn.className);
                this.cancelBtn.classList.remove('hidden');
                console.log('🚫 DEBUG: After - Button classes:', this.cancelBtn.className);
                this.cancelBtn.textContent = this.t('cancelBtn');
                console.log('🚫 DEBUG: Button text set to:', this.cancelBtn.textContent);
                
                // IMPORTANT: Mark this button as "streaming" BEFORE cloning
                // This ensures the attribute is preserved after cloning
                this.cancelBtn.setAttribute('data-cancel-type', 'streaming');
                console.log('🚫 DEBUG: Set data-cancel-type to streaming');
                
                // Remove any existing event listeners by cloning and replacing
                const newBtn = this.cancelBtn.cloneNode(true);
                this.cancelBtn.parentNode.replaceChild(newBtn, this.cancelBtn);
                this.cancelBtn = newBtn;
                console.log('🚫 DEBUG: Button cloned and replaced, data-cancel-type:', this.cancelBtn.getAttribute('data-cancel-type'));
                
                this.cancelBtn.onclick = () => {
                    console.log('🚫 DEBUG: STREAMING Cancel button clicked! Showing confirmation...');
                    if (confirm(this.t('cancelConfirm'))) {
                        console.log('🚫 DEBUG: User confirmed cancellation, calling cancelCurrentTask...');
                        this.cancelCurrentTask();
                    } else {
                        console.log('🚫 DEBUG: User declined cancellation');
                    }
                };
                console.log('✅ Streaming cancel button is now visible and has click handler attached');
            } else {
                console.error('❌ Cancel button element not found!');
            }
        },

        hideCancelButton() {
            if (this.cancelBtn) {
                this.cancelBtn.classList.add('hidden');
            }
        },

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
                            this.clearActiveTask(); // Clear stored task on completion
                            resolve(progress.result);
                        } else if (progress.status === 'cancelled') {
                            eventSource.close();
                            this.currentEventSource = null;
                            this.currentTaskId = null;
                            this.clearActiveTask(); // Clear stored task on cancellation
                            const cancelError = new Error(this.t('cancelled'));
                            cancelError.name = 'CancelError';
                            reject(cancelError); // Reject with cancel error to trigger catch block
                        } else if (progress.status === 'error') {
                            eventSource.close();
                            this.currentEventSource = null;
                            this.currentTaskId = null;
                            this.clearActiveTask(); // Clear stored task on error
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
        },

        updateLoadingProgress(percentage, message, stageInfo = null) {
            // Stop any ongoing progress simulation when real backend update comes in
            if (this.progressFillInterval) {
                clearInterval(this.progressFillInterval);
                this.progressFillInterval = null;
            }
            
            if (this.loadingText) {
                this.loadingText.innerHTML = message;  // Changed to innerHTML to support HTML tags
            }
            
            // Use the stepper progress system
            this.updateStreamingProgress(percentage, message);
        },

        // Helper function to animate percentage counting
        animatePercentage(element, start, end, duration = 500) {
            const startTime = Date.now();
            const animate = () => {
                const elapsed = Date.now() - startTime;
                const progress = Math.min(elapsed / duration, 1);
                
                // Use easing function for smooth animation
                const easeProgress = 1 - Math.pow(1 - progress, 3);
                const current = Math.round(start + (end - start) * easeProgress);
                
                element.textContent = `${current}%`;
                
                if (progress < 1) {
                    requestAnimationFrame(animate);
                }
            };
            
            requestAnimationFrame(animate);
        },

        // Simulate intermediate progress for better UX during long operations
        simulateProgressFill(startPercent, endPercent, duration = 30000) {
            if (this.progressFillInterval) {
                clearInterval(this.progressFillInterval);
            }
            
            const increment = (endPercent - startPercent) / (duration / 1000); // per second
            let currentPercent = startPercent;
            
            this.progressFillInterval = setInterval(() => {
                currentPercent += increment;
                
                if (currentPercent >= endPercent) {
                    clearInterval(this.progressFillInterval);
                    this.progressFillInterval = null;
                    return;
                }
                
                // Update with simulated progress
                const progressBar = document.getElementById('progress-bar');
                const progressPercentage = document.getElementById('progress-percentage');
                
                if (progressBar && !progressBar.classList.contains('processing-pulse')) {
                    progressBar.style.width = `${Math.min(currentPercent, endPercent)}%`;
                }
                
                if (progressPercentage) {
                    progressPercentage.textContent = `${Math.round(Math.min(currentPercent, endPercent))}%`;
                }
            }, 1000);
        },

        // Stop progress simulation when real update arrives
        stopProgressSimulation() {
            if (this.progressFillInterval) {
                clearInterval(this.progressFillInterval);
                this.progressFillInterval = null;
            }
        },

        showStreamingProgress(message, operationType = 'summary') {
            // Create or update streaming progress UI
            const statusContainer = this.statusContainer;

            // Clear existing content
            statusContainer.innerHTML = '';
            statusContainer.classList.remove('hidden');
            
            // Get localized step labels based on operation type
            let stepLabels;
            
            if (operationType === 'shorts') {
                // Steps for Shorts Generation
                stepLabels = {
                    step1: this.t('stepProcessing') || 'Processing',
                    step2: this.t('stepAnalyzing') || 'Analyzing',
                    step3: this.t('stepFinalizing') || 'Finalizing',
                    step4: this.t('stepComplete') || 'Complete',
                    initializing: this.t('initializing') || 'Starting...',
                    cancel: this.t('cancelBtn') || 'Cancel'
                };
            } else if (operationType === 'webpage') {
                // Steps for Webpage Analysis
                stepLabels = {
                    step1: this.t('stepProcessing') || 'Processing',
                    step2: this.t('stepAnalyzing') || 'Analyzing',
                    step3: this.t('stepFinalizing') || 'Finalizing',
                    step4: this.t('stepComplete') || 'Complete',
                    initializing: this.t('initializing') || 'Starting...',
                    cancel: this.t('cancelBtn') || 'Cancel'
                };
            } else {
                // Steps for Video Summary (default)
                stepLabels = {
                    step1: this.t('stepProcessing') || 'Processing',
                    step2: this.t('stepAnalyzing') || 'Analyzing',
                    step3: this.t('stepFinalizing') || 'Finalizing',
                    step4: this.t('stepComplete') || 'Complete',
                    initializing: this.t('initializing') || 'Starting...',
                    cancel: this.t('cancelBtn') || 'Cancel'
                };
            }

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
                        class="btn btn-outline-danger btn-sm"
                        data-cancel-type="streaming"
                        title="Cancel current operation">
                        <i class="fas fa-times me-1"></i>${stepLabels.cancel}
                    </button>
                </div>
                <!-- Modern Stepper Progress Indicator -->
                <div class="stepper-wrapper" id="stepper-progress">
                    <div class="stepper-item" id="step-1" data-step="1">
                        <div class="stepper-circle">
                            <div class="stepper-icon">
                                <svg class="w-4 h-4 success-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4"></path>
                                </svg>
                                <svg class="w-4 h-4 error-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="display: none;">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                </svg>
                                <span class="stepper-number">1</span>
                            </div>
                            <div class="stepper-pulse"></div>
                        </div>
                        <div class="stepper-label">${stepLabels.step1}</div>
                    </div>
                    
                    <div class="stepper-line" id="line-1">
                        <div class="stepper-line-progress"></div>
                    </div>
                    
                    <div class="stepper-item" id="step-2" data-step="2">
                        <div class="stepper-circle">
                            <div class="stepper-icon">
                                <svg class="w-4 h-4 success-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4"></path>
                                </svg>
                                <svg class="w-4 h-4 error-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="display: none;">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                </svg>
                                <span class="stepper-number">2</span>
                            </div>
                            <div class="stepper-pulse"></div>
                        </div>
                        <div class="stepper-label">${stepLabels.step2}</div>
                    </div>
                    
                    <div class="stepper-line" id="line-2">
                        <div class="stepper-line-progress"></div>
                    </div>
                    
                    <div class="stepper-item" id="step-3" data-step="3">
                        <div class="stepper-circle">
                            <div class="stepper-icon">
                                <svg class="w-4 h-4 success-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4"></path>
                                </svg>
                                <svg class="w-4 h-4 error-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="display: none;">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                </svg>
                                <span class="stepper-number">3</span>
                            </div>
                            <div class="stepper-pulse"></div>
                        </div>
                        <div class="stepper-label">${stepLabels.step3}</div>
                    </div>
                    
                    <div class="stepper-line" id="line-3">
                        <div class="stepper-line-progress"></div>
                    </div>
                    
                    <div class="stepper-item" id="step-4" data-step="4">
                        <div class="stepper-circle">
                            <div class="stepper-icon">
                                <svg class="w-4 h-4 success-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4"></path>
                                </svg>
                                <svg class="w-4 h-4 error-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="display: none;">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                </svg>
                                <span class="stepper-number">4</span>
                            </div>
                            <div class="stepper-pulse"></div>
                        </div>
                        <div class="stepper-label">${stepLabels.step4}</div>
                    </div>
                </div>
                <div class="stepper-message" id="progress-message">${stepLabels.initializing}</div>
                <div class="stepper-percentage" id="progress-percentage">0%</div>
                <div class="mt-4 bg-gray-50 rounded-lg p-4 min-h-20" id="streaming-content" style="display: none;">
                    <div class="text-sm text-gray-600" id="partial-content"></div>
                </div>
            `;

            statusContainer.appendChild(progressContainer);

            // Set up cancel button after creating the new container
            // Use setTimeout to ensure DOM is fully updated
            setTimeout(() => {
                this.showCancelButton();
            }, 100);
            
            // Also attach directly as backup
            setTimeout(() => {
                const cancelBtn = document.getElementById('cancel-btn');
                if (cancelBtn && !cancelBtn.dataset.handlerAttached) {
                    console.log('🚫 DEBUG: Attaching backup cancel handler');
                    cancelBtn.dataset.handlerAttached = 'true';
                    cancelBtn.addEventListener('click', (e) => {
                        console.log('🚫 DEBUG: Backup handler - Cancel button clicked!');
                        if (confirm(this.t('cancelConfirm') || 'Are you sure you want to cancel?')) {
                            console.log('🚫 DEBUG: Backup handler - User confirmed, cancelling...');
                            this.cancelCurrentTask();
                        }
                    });
                }
            }, 150);
        },

        updateStreamingProgress(percentage, message) {
            const progressMessage = document.getElementById('progress-message');
            const progressPercentage = document.getElementById('progress-percentage');

            // Update message and percentage
            if (progressMessage) {
                progressMessage.innerHTML = message;  // Changed to innerHTML to support HTML tags
            }
            if (progressPercentage) {
                progressPercentage.textContent = `${Math.round(percentage)}%`;
            }

            // Update stepper based on percentage
            this.updateStepperProgress(percentage);
        },

        showStepperError(errorMessage) {
            const progressMessage = document.getElementById('progress-message');
            const progressPercentage = document.getElementById('progress-percentage');
            const stepperContainer = document.getElementById('stepper-progress');

            // Update message to show error
            if (progressMessage) {
                progressMessage.innerHTML = errorMessage || 'An error occurred during processing';  // Changed to innerHTML
                progressMessage.style.color = '#ef4444'; // Red color for error
            }
            
            // Show error percentage
            if (progressPercentage) {
                progressPercentage.textContent = 'Error';
                progressPercentage.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
                progressPercentage.style.webkitBackgroundClip = 'text';
                progressPercentage.style.webkitTextFillColor = 'transparent';
            }

            // Add error class to stepper container
            if (stepperContainer) {
                stepperContainer.classList.add('stepper-error');
            }

            // Mark current active step as failed
            const activeStep = document.querySelector('.stepper-item.active');
            if (activeStep) {
                activeStep.classList.remove('active');
                activeStep.classList.add('error');
                
                // Show error icon instead of number/success icon
                const numberElement = activeStep.querySelector('.stepper-number');
                const successIcon = activeStep.querySelector('.success-icon');
                const errorIcon = activeStep.querySelector('.error-icon');
                
                if (numberElement) numberElement.style.display = 'none';
                if (successIcon) successIcon.style.display = 'none';
                if (errorIcon) errorIcon.style.display = 'block';
            }

            // Stop any ongoing animations
            if (this.progressFillInterval) {
                clearInterval(this.progressFillInterval);
                this.progressFillInterval = null;
            }

            // Add retry button
            this.addRetryButton();
        },

        addRetryButton() {
            const stepperContainer = document.getElementById('stepper-progress');
            if (!stepperContainer) return;

            // Remove existing retry button if any
            const existingRetry = stepperContainer.querySelector('.retry-button');
            if (existingRetry) existingRetry.remove();

            // Create retry button
            const retryButton = document.createElement('button');
            retryButton.className = 'retry-button';
            retryButton.innerHTML = `
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                </svg>
                Try Again
            `;

            retryButton.addEventListener('click', () => {
                // Reset the form and allow user to retry
                location.reload();
            });

            // Add to stepper container
            stepperContainer.appendChild(retryButton);
        },

        updateStepperProgress(percentage) {
            // Determine current step based on percentage (updated ranges for shorts generation)
            let currentStep = 1;
            if (percentage >= 40) currentStep = 2;      // AI Analysis (40-55%)
            if (percentage >= 60) currentStep = 3;      // Create Clips (60-95%) 
            if (percentage >= 95) currentStep = 4;      // Complete (95-100%)

            // Update step states
            for (let i = 1; i <= 4; i++) {
                const stepElement = document.getElementById(`step-${i}`);
                if (!stepElement) continue;

                // Remove all state classes
                stepElement.classList.remove('pending', 'active', 'completed');
                
                // Apply appropriate state
                if (i < currentStep) {
                    stepElement.classList.add('completed');
                } else if (i === currentStep) {
                    stepElement.classList.add('active');
                } else {
                    stepElement.classList.add('pending');
                }
            }

            // Update connecting lines
            for (let i = 1; i <= 3; i++) {
                const line = document.getElementById(`line-${i}`);
                const lineProgress = line?.querySelector('.stepper-line-progress');
                if (!lineProgress) continue;

                let linePercentage = 0;
                
                // Calculate line progress based on current step and percentage
                if (currentStep > i + 1) {
                    linePercentage = 100; // Completed
                } else if (currentStep === i + 1) {
                    // Currently transitioning to next step  
                    const stepRanges = [
                        { start: 0, end: 40 },    // Step 1 range (Extract Video)
                        { start: 40, end: 60 },   // Step 2 range (AI Analysis)
                        { start: 60, end: 95 },   // Step 3 range (Create Clips)
                        { start: 95, end: 100 }   // Step 4 range (Complete)
                    ];
                    
                    const currentRange = stepRanges[i - 1];
                    const progress = Math.max(0, Math.min(100, 
                        ((percentage - currentRange.start) / (currentRange.end - currentRange.start)) * 100
                    ));
                    linePercentage = Math.min(100, progress);
                }
                
                lineProgress.style.width = `${linePercentage}%`;
            }
        },

        updateStreamingContent(partialContent) {
            const streamingContent = document.getElementById('streaming-content');
            const partialContentDiv = document.getElementById('partial-content');

            if (streamingContent && partialContentDiv && partialContent) {
                streamingContent.style.display = 'block';
                partialContentDiv.textContent = partialContent;
            }
        },

        showStreamingSummary() {
            this.ensureStreamingStyles();
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
                        <div class="text-blue-800 font-semibold">🤖 ${this.t('aiGenerating') || 'AI is generating your summary...'}</div>
                        <div class="text-blue-600 text-sm mt-1">${this.t('contentProcessing') || 'Your content is being processed in real-time'}</div>
                    </div>
                </div>
                <div id="streaming-summary-content" class="prose max-w-none p-6 bg-white rounded-lg border border-gray-200 relative" style="height: 500px; overflow-y: auto;">
                    <div class="streaming-content" style="line-height: 1.8; word-wrap: break-word;"></div>
                    <div class="absolute top-2 right-2 text-xs text-green-500 font-medium bg-white bg-opacity-90 px-2 py-1 rounded shadow-sm">● ${this.t('liveIndicator') || 'Live'}</div>
                </div>
            `;
        },

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
        },

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
        },

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
        },

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
        },

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
        },

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
        },

        getStreamingDelay(chunk) {
            // Optimized ChatGPT-style timing for smooth streaming
            if (chunk.includes('\n')) return 150; // Moderate pause at line breaks
            if (chunk.match(/[.!?]/)) return 200; // Pause at sentence endings
            if (chunk.match(/[,;:]/)) return 100; // Short pause at punctuation
            if (chunk === ' ') return 15; // Very quick for spaces
            if (chunk.length > 5) return 30; // Fast for longer words
            if (chunk.length > 2) return 25; // Fast for medium words
            return 20; // Fast for short chunks - smooth like ChatGPT
        },

        displayWordsOneByOne(container, existingContent, newWords) {
            // Legacy method - redirect to new implementation
            const newPart = newWords.join(' ');
            const fullContent = existingContent + (existingContent ? ' ' : '') + newPart;
            this.displayWordByWordWithFormatting(container, existingContent, newPart, fullContent);
        },

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
        },

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
        },

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
        },

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
        },

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
        },

        formatStreamingContent(content) {
            this.ensureStreamingStyles();
            if (!content) return '';

            return content
                .split('\n')
                .map(line => this.formatStreamingLine(line, { realtime: false }))
                .join('');
        },

        formatStreamingContentRealtime(content) {
            this.ensureStreamingStyles();
            if (!content) return '';

            return content
                .split('\n')
                .map(line => this.formatStreamingLine(line, { realtime: true }))
                .join('');
        },

        formatStreamingLine(line, { realtime } = {}) {
            const trimmedLine = line.trim();
            const formatter = realtime
                ? this.formatInlineMarkdownRealtime.bind(this)
                : this.formatInlineMarkdown.bind(this);

            if (!trimmedLine) {
                return '<div class="streaming-gap"></div>';
            }

            if (trimmedLine.startsWith('### ')) {
                return `<p class="streaming-heading streaming-heading-3">${formatter(trimmedLine.substring(4))}</p>`;
            }

            if (trimmedLine.startsWith('## ')) {
                return `<p class="streaming-heading streaming-heading-2">${formatter(trimmedLine.substring(3))}</p>`;
            }

            if (trimmedLine.startsWith('# ')) {
                return `<p class="streaming-heading streaming-heading-1">${formatter(trimmedLine.substring(2))}</p>`;
            }

            if (/^(💡|📝|🔍|⚡|🎯|📊)/.test(trimmedLine)) {
                return `<div class="streaming-highlight">${formatter(trimmedLine)}</div>`;
            }

            const labeledBullet = trimmedLine.match(/^•\s*\*\*(.*?)\*\*\s*[-–—:]\s*(.*)$/);
            if (labeledBullet) {
                return `<div class="streaming-bullet streaming-bullet-with-title"><span class="streaming-bullet-dot">•</span><div class="streaming-bullet-body"><span class="streaming-bullet-title">${formatter(labeledBullet[1])}</span><span class="streaming-bullet-separator">—</span><span class="streaming-bullet-text">${formatter(labeledBullet[2])}</span></div></div>`;
            }

            const plainBullet = trimmedLine.match(/^•\s+(.*)$/);
            if (plainBullet) {
                return `<div class="streaming-bullet"><span class="streaming-bullet-dot">•</span><span class="streaming-bullet-text">${formatter(plainBullet[1])}</span></div>`;
            }

            const dashedBullet = trimmedLine.match(/^[-–*]\s+(.*)$/);
            if (dashedBullet) {
                return `<div class="streaming-bullet"><span class="streaming-bullet-dot">•</span><span class="streaming-bullet-text">${formatter(dashedBullet[1])}</span></div>`;
            }

            return `<p class="streaming-paragraph">${formatter(trimmedLine)}</p>`;
        },

        formatInlineMarkdown(text) {
            if (!text) return '';
            return text
                .replace(/\*\*(.*?)\*\*/g, '<span class="streaming-bold">$1</span>')
                .replace(/\*([^*]+)\*/g, '<span class="streaming-italic">$1</span>');
        },

        formatInlineMarkdownRealtime(text) {
            if (!text) return '';

            // Handle complete bold formatting
            let formatted = text.replace(/\*\*(.*?)\*\*/g, '<span class="streaming-bold">$1</span>');

            // Handle incomplete bold formatting (when user is still typing)
            formatted = formatted.replace(/\*\*([^*]+)$/g, '<span class="streaming-bold">$1</span>');

            // Handle complete italic formatting
            formatted = formatted.replace(/\*([^*]+)\*/g, '<span class="streaming-italic">$1</span>');

            // Handle incomplete italic formatting
            formatted = formatted.replace(/\*([^*\s]+)$/g, '<span class="streaming-italic">$1</span>');

            return formatted;
        },

        ensureStreamingStyles() {
            if (document.getElementById('streaming-style-rules')) {
                return;
            }

            const style = document.createElement('style');
            style.id = 'streaming-style-rules';
            style.textContent = `
                .streaming-content {
                    font-size: 0.95rem;
                    line-height: 1.6;
                    color: #1f2937;
                }
                .streaming-content * {
                    font-family: inherit;
                }
                .streaming-heading {
                    font-weight: 500;
                    margin: 0.75rem 0 0.35rem;
                    line-height: 1.5;
                    color: #1f2937;
                }
                .streaming-heading-1 {
                    font-size: 1.08rem;
                }
                .streaming-heading-2 {
                    font-size: 1.02rem;
                }
                .streaming-heading-3 {
                    font-size: 0.98rem;
                }
                .streaming-paragraph {
                    margin: 0.4rem 0;
                    font-size: 0.95rem;
                    line-height: 1.65;
                    color: #1f2937;
                    font-weight: 400;
                }
                .streaming-highlight {
                    margin: 0.55rem 0;
                    padding: 0.6rem 0.85rem;
                    border-radius: 0.75rem;
                    background: rgba(219, 234, 254, 0.75);
                    color: #1e3a8a;
                    font-weight: 500;
                    font-size: 0.96rem;
                    line-height: 1.55;
                }
                .streaming-bullet {
                    display: flex;
                    gap: 0.45rem;
                    align-items: flex-start;
                    margin: 0.35rem 0;
                    font-size: 0.95rem;
                    line-height: 1.55;
                    color: #374151;
                    font-weight: 400;
                }
                .streaming-bullet-dot {
                    color: #2563eb;
                    font-weight: 600;
                    margin-top: 0.32rem;
                }
                .streaming-bullet-body {
                    display: inline-flex;
                    flex-wrap: wrap;
                    gap: 0.3rem;
                }
                .streaming-bullet-title {
                    font-weight: 500;
                    color: #1f2937;
                }
                .streaming-bullet-separator {
                    color: #9ca3af;
                }
                .streaming-bullet-text {
                    color: #374151;
                    font-weight: 400;
                }
                .streaming-gap {
                    height: 0.5rem;
                }
                .streaming-bold {
                    font-weight: 500;
                    color: #111827;
                }
                .streaming-italic {
                    font-style: italic;
                    color: #1f2937;
                }
                .streaming-content strong,
                .streaming-content b {
                    font-weight: 500;
                }
            `;
            document.head.appendChild(style);
        }
    };

    global.YouTubeTranscriptAppMixins = global.YouTubeTranscriptAppMixins || [];
    global.YouTubeTranscriptAppMixins.push(streamingMixin);
})(window);
