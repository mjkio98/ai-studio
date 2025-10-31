(function (global) {
    const cacheMixin = {
        generateCacheKey(url, type = 'video') {
            // Create a unique key based on URL, type, and language
            return `${type}_${this.currentLanguage}_${btoa(url).slice(0, 50)}`;
        },

        loadCacheFromStorage() {
            try {
                const storedCache = localStorage.getItem('ytTranscriptCache');
                if (storedCache) {
                    const parsed = JSON.parse(storedCache);
                    if (parsed.version === this.cacheVersion) {
                        // Convert array back to Map and check expiry
                        const now = new Date().getTime();
                        this.cache = new Map(parsed.data.filter(([key, value]) => {
                            const ageInDays = (now - value.timestamp) / (1000 * 60 * 60 * 24);
                            return ageInDays < this.cacheExpiryDays;
                        }));
                    }
                }
            } catch (e) {
                this.cache = new Map();
            }
        },

        saveCacheToStorage() {
            try {
                // Convert Map to array for storage and limit size
                const cacheArray = Array.from(this.cache.entries());
                if (cacheArray.length > this.maxCacheSize) {
                    // Keep only the most recent entries
                    cacheArray.sort((a, b) => b[1].timestamp - a[1].timestamp);
                    this.cache = new Map(cacheArray.slice(0, this.maxCacheSize));
                }

                const cacheData = {
                    version: this.cacheVersion,
                    data: Array.from(this.cache.entries())
                };
                localStorage.setItem('ytTranscriptCache', JSON.stringify(cacheData));
            } catch (e) {
                // Cache saving failed, continue silently
            }
        },

        getCachedResult(url, type = 'video') {
            const key = this.generateCacheKey(url, type);
            const cached = this.cache.get(key);

            if (cached) {
                const ageInDays = (new Date().getTime() - cached.timestamp) / (1000 * 60 * 60 * 24);
                if (ageInDays < this.cacheExpiryDays) {
                    return cached.data;
                } else {
                    // Remove expired cache
                    this.cache.delete(key);
                }
            }
            return null;
        },

        setCachedResult(url, data, type = 'video') {
            const key = this.generateCacheKey(url, type);
            this.cache.set(key, {
                data: data,
                timestamp: new Date().getTime(),
                url: url
            });
            this.saveCacheToStorage();
        },

        clearCache() {
            this.cache.clear();
            localStorage.removeItem('ytTranscriptCache');
        },

        showCacheStatus(url, type = 'video') {
            const cached = this.getCachedResult(url, type);
            if (cached) {
                const cacheAge = Math.round((new Date().getTime() - cached.timestamp) / (1000 * 60 * 60));
                this.showInfo(`📋 ${this.t('cacheFound')} (${cacheAge}h ${this.t('cacheAgo')})`);
            }
        }
    };

    global.YouTubeTranscriptAppMixins = global.YouTubeTranscriptAppMixins || [];
    global.YouTubeTranscriptAppMixins.push(cacheMixin);
})(window);
