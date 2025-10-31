/**
 * Page Detection Utility
 * Provides safe DOM element checking to prevent JavaScript errors
 */
window.PageUtils = {
    /**
     * Check if an element exists in the DOM
     * @param {string} id - Element ID to check
     * @returns {boolean} - True if element exists
     */
    hasElement: (id) => {
        return document.getElementById(id) !== null;
    },

    /**
     * Detect current page type based on key elements
     * @param {string} pageType - Type of page to check for
     * @returns {boolean} - True if current page matches type
     */
    isPage: (pageType) => {
        const indicators = {
            'single-video': ['youtube-url', 'summarize-video-btn'],
            'multi-video': ['multi-video-section', 'add-url-btn', 'summarize-multi-btn'], 
            'webpage': ['webpage-url', 'analyze-webpage-btn'],
            'dashboard': ['single-mode-btn', 'multi-mode-btn', 'webpage-mode-btn']
        };
        
        const pageIndicators = indicators[pageType];
        if (!pageIndicators) return false;
        
        return pageIndicators.some(id => PageUtils.hasElement(id));
    },

    /**
     * Safe element getter - returns element or null
     * @param {string} id - Element ID
     * @returns {HTMLElement|null} - Element or null if not found
     */
    safeGet: (id) => {
        return document.getElementById(id);
    },

    /**
     * Check if any of multiple elements exist
     * @param {string[]} ids - Array of element IDs
     * @returns {boolean} - True if any element exists
     */
    hasAnyElement: (ids) => {
        return ids.some(id => PageUtils.hasElement(id));
    },

    /**
     * Get page type based on current elements
     * @returns {string} - Current page type
     */
    getCurrentPageType: () => {
        if (PageUtils.isPage('single-video')) return 'single-video';
        if (PageUtils.isPage('multi-video')) return 'multi-video';
        if (PageUtils.isPage('webpage')) return 'webpage';
        if (PageUtils.isPage('dashboard')) return 'dashboard';
        return 'unknown';
    }
};

// Console log for debugging (remove in production)
document.addEventListener('DOMContentLoaded', () => {
    console.log('Page detected as:', PageUtils.getCurrentPageType());
});