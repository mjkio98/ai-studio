(function (global) {
    class YouTubeTranscriptApp {
        constructor() {
            this.currentTranscript = '';
            this.currentVideoInfo = null;
            // Language state defaults (initialized after DOM is ready)
            this.currentLanguage = 'en';
            this.translations = {};
            this.currentTaskId = null;
            this.currentEventSource = null;
            this.currentAbortController = null;
            this.taskCancelled = false; // Flag to ignore progress updates after cancellation

            // Initialize caching system
            this.cache = new Map();
            this.cacheVersion = '1.0'; // Increment to invalidate all caches
            this.maxCacheSize = 50; // Maximum number of cached items
            this.cacheExpiryDays = 7; // Cache expiry in days

            this.initializeComponents();
            // Initialize language after a short delay to ensure DOM is ready
            setTimeout(() => {
                if (typeof this.initializeLanguageSystem === 'function') {
                    this.initializeLanguageSystem();
                } else {
                    // Fallback to previous behaviour if mixin is unavailable
                    if (!this.translations || Object.keys(this.translations).length === 0) {
                        this.translations = this.loadTranslations();
                    }
                    this.currentLanguage = this.detectBrowserLanguage ? this.detectBrowserLanguage() : this.currentLanguage;
                    this.applyLanguage && this.applyLanguage();
                }
            }, 100);
            
            // No longer checking for active tasks - we cancel them on navigation instead

            // Handle page unload - cancel any ongoing tasks (only on actual page close/refresh)
            window.addEventListener('beforeunload', () => {
                this.cancelCurrentTask();
            });

            // Also cancel tasks when navigating to different pages (not just closing)
            window.addEventListener('pagehide', () => {
                if (this.currentTaskId) {
                    console.log('🚫 Page navigation detected, cancelling active task');
                    this.cancelCurrentTask();
                }
            });

            // Note: Removed visibilitychange listener to allow users to switch tabs
            // while videos are processing without cancelling the task

            // Initialize cache from localStorage
            this.loadCacheFromStorage();
        }
    }

    global.YouTubeTranscriptApp = YouTubeTranscriptApp;

    const mixins = global.YouTubeTranscriptAppMixins || [];
    mixins.forEach((mixin) => {
        Object.assign(YouTubeTranscriptApp.prototype, mixin);
    });
    delete global.YouTubeTranscriptAppMixins;

    document.addEventListener('DOMContentLoaded', () => {
        if (!global.youtubeApp) {
            global.youtubeApp = new YouTubeTranscriptApp();
            
            // Debug: Check if cancel method exists
            console.log('🧪 DEBUG: App initialized. cancelShortsGeneration method exists?', 
                typeof global.youtubeApp.cancelShortsGeneration === 'function');
            
            if (typeof global.youtubeApp.cancelShortsGeneration === 'function') {
                console.log('✅ Cancel method is available');
                // Make it globally accessible for testing
                window.testCancelMethod = (taskId) => {
                    console.log('🧪 Global test cancel called for:', taskId);
                    return global.youtubeApp.cancelShortsGeneration(taskId);
                };
            } else {
                console.error('❌ Cancel method is NOT available');
                console.log('Available methods:', Object.getOwnPropertyNames(global.youtubeApp).filter(name => typeof global.youtubeApp[name] === 'function'));
            }
        }
    });
})(window);
