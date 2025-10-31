/**
 * Custom Header JavaScript
 * Handles mobile menu toggle, language switching, and responsive behavior
 */

class CustomHeader {
    constructor() {
        this.isInitialized = false;
        this.currentLanguage = 'en';
        this.isMobileMenuOpen = false;
        
        // DOM elements
        this.header = null;
        this.mobileMenuToggle = null;
        this.navbarMenu = null;
        this.mobileMenuOverlay = null;
        this.langButtons = null;
        this.settingsBtn = null;
        this.settingsDropdown = null;
        
        // Bind methods
        this.toggleMobileMenu = this.toggleMobileMenu.bind(this);
        this.closeMobileMenu = this.closeMobileMenu.bind(this);
        this.switchLanguage = this.switchLanguage.bind(this);
        this.handleResize = this.handleResize.bind(this);
        this.handleClickOutside = this.handleClickOutside.bind(this);
    }

    /**
     * Initialize the custom header
     */
    init() {
        if (this.isInitialized) {
            console.log('Custom header already initialized');
            return;
        }

        try {
            // Get DOM elements
            this.getDOMElements();
            
            if (!this.header) {
                console.warn('Custom header not found in DOM');
                return;
            }

            // Set up event listeners
            this.setupEventListeners();
            
            // Initialize language system
            this.initializeLanguageSystem();
            
            // Set active navigation
            this.setActiveNavigation();
            
            // Handle initial responsive state
            this.handleResize();
            
            this.isInitialized = true;
            console.log('✅ Custom header initialized successfully');
            
        } catch (error) {
            console.error('❌ Failed to initialize custom header:', error);
        }
    }

    /**
     * Get all required DOM elements
     */
    getDOMElements() {
        this.header = document.getElementById('custom-header');
        this.mobileMenuToggle = document.getElementById('mobile-menu-toggle');
        this.navbarMenu = document.getElementById('navbar-menu');
        this.mobileMenuOverlay = document.getElementById('mobile-menu-overlay');
        
        // Language buttons
        this.langButtons = {
            en: document.getElementById('lang-en-header'),
            ar: document.getElementById('lang-ar-header')
        };
    }

    /**
     * Set up all event listeners
     */
    setupEventListeners() {
        // Mobile menu toggle
        if (this.mobileMenuToggle) {
            this.mobileMenuToggle.addEventListener('click', this.toggleMobileMenu);
        }

        // Mobile menu overlay
        if (this.mobileMenuOverlay) {
            this.mobileMenuOverlay.addEventListener('click', this.closeMobileMenu);
        }

        // Language switcher buttons
        Object.keys(this.langButtons).forEach(lang => {
            const btn = this.langButtons[lang];
            if (btn) {
                btn.addEventListener('click', () => this.switchLanguage(lang));
            }
        });

        // Navigation links (close mobile menu when clicked)
        const navLinks = this.header?.querySelectorAll('.nav-link');
        navLinks?.forEach(link => {
            link.addEventListener('click', () => {
                if (this.isMobileMenuOpen) {
                    this.closeMobileMenu();
                }
            });
        });

        // Window events
        window.addEventListener('resize', this.handleResize);
        document.addEventListener('click', this.handleClickOutside);

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isMobileMenuOpen) {
                this.closeMobileMenu();
            }
        });
    }

    /**
     * Set active navigation based on current page
     */
    setActiveNavigation() {
        const currentPath = window.location.pathname;
        const navLinks = this.header?.querySelectorAll('.nav-link');
        
        navLinks?.forEach(link => {
            link.classList.remove('active');
            
            const href = link.getAttribute('href');
            if (href && (currentPath === href || currentPath.startsWith(href + '/'))) {
                link.classList.add('active');
            }
        });
    }

    /**
     * Toggle mobile menu
     */
    toggleMobileMenu() {
        if (this.isMobileMenuOpen) {
            this.closeMobileMenu();
        } else {
            this.openMobileMenu();
        }
    }

    /**
     * Open mobile menu
     */
    openMobileMenu() {
        this.isMobileMenuOpen = true;
        
        if (this.mobileMenuToggle) {
            this.mobileMenuToggle.classList.add('active');
        }
        
        if (this.navbarMenu) {
            this.navbarMenu.classList.add('active');
        }
        
        if (this.mobileMenuOverlay) {
            this.mobileMenuOverlay.classList.add('active');
        }

        // Prevent body scroll
        document.body.style.overflow = 'hidden';
        
        // Add ARIA attributes
        if (this.mobileMenuToggle) {
            this.mobileMenuToggle.setAttribute('aria-expanded', 'true');
        }
    }

    /**
     * Close mobile menu
     */
    closeMobileMenu() {
        this.isMobileMenuOpen = false;
        
        if (this.mobileMenuToggle) {
            this.mobileMenuToggle.classList.remove('active');
        }
        
        if (this.navbarMenu) {
            this.navbarMenu.classList.remove('active');
        }
        
        if (this.mobileMenuOverlay) {
            this.mobileMenuOverlay.classList.remove('active');
        }

        // Restore body scroll
        document.body.style.overflow = '';
        
        // Add ARIA attributes
        if (this.mobileMenuToggle) {
            this.mobileMenuToggle.setAttribute('aria-expanded', 'false');
        }
    }

    /**
     * Handle window resize
     */
    handleResize() {
        // Close mobile menu on desktop
        if (window.innerWidth > 768 && this.isMobileMenuOpen) {
            this.closeMobileMenu();
        }
    }

    /**
     * Handle clicks outside mobile menu
     */
    handleClickOutside(e) {
        if (!this.isMobileMenuOpen) return;
        
        const isInsideMenu = this.navbarMenu?.contains(e.target);
        const isToggleButton = this.mobileMenuToggle?.contains(e.target);
        
        if (!isInsideMenu && !isToggleButton) {
            this.closeMobileMenu();
        }
    }

    /**
     * Switch language
     */
    switchLanguage(lang) {
        if (this.currentLanguage === lang) return;
        
        this.currentLanguage = lang;
        
        // Update button states
        Object.keys(this.langButtons).forEach(btnLang => {
            const btn = this.langButtons[btnLang];
            if (btn) {
                if (btnLang === lang) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            }
        });

        // Update text content
        this.updateLanguageContent(lang);
        
        // Store language preference
        localStorage.setItem('preferred_language', lang);
        
        // Trigger custom event for other scripts to listen to
        window.dispatchEvent(new CustomEvent('languageChanged', {
            detail: { language: lang }
        }));

        console.log(`🌐 Language switched to: ${lang}`);
    }

    /**
     * Update language content
     */
    updateLanguageContent(lang) {
        const elements = document.querySelectorAll('[data-en][data-ar]');
        
        elements.forEach(element => {
            const text = element.getAttribute(`data-${lang}`);
            if (text) {
                element.textContent = text;
            }
        });

        // Update document language
        document.documentElement.lang = lang;
        
        // Update direction for Arabic
        if (lang === 'ar') {
            document.documentElement.dir = 'rtl';
            document.body.classList.add('rtl');
        } else {
            document.documentElement.dir = 'ltr';
            document.body.classList.remove('rtl');
        }
    }

    /**
     * Initialize language system
     */
    initializeLanguageSystem() {
        // Get stored language preference
        const storedLang = localStorage.getItem('preferred_language');
        const browserLang = navigator.language.startsWith('ar') ? 'ar' : 'en';
        const defaultLang = storedLang || browserLang;
        
        // Switch to preferred language
        this.switchLanguage(defaultLang);
    }

    /**
     * Destroy the header instance
     */
    destroy() {
        if (!this.isInitialized) return;
        
        // Remove event listeners
        if (this.mobileMenuToggle) {
            this.mobileMenuToggle.removeEventListener('click', this.toggleMobileMenu);
        }
        
        if (this.mobileMenuOverlay) {
            this.mobileMenuOverlay.removeEventListener('click', this.closeMobileMenu);
        }
        
        Object.values(this.langButtons).forEach(btn => {
            if (btn) {
                btn.removeEventListener('click', this.switchLanguage);
            }
        });
        
        window.removeEventListener('resize', this.handleResize);
        document.removeEventListener('click', this.handleClickOutside);
        
        // Reset state
        this.closeMobileMenu();
        this.isInitialized = false;
        
        console.log('Custom header destroyed');
    }
}

// Global instance
window.customHeader = null;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Initializing custom header...');
    
    // Create and initialize header
    window.customHeader = new CustomHeader();
    window.customHeader.init();
    
    // Integration with existing language system
    if (window.YouTubeTranscriptAppMixins) {
        const languageManager = window.YouTubeTranscriptAppMixins.find(
            mixin => typeof mixin.initializeLanguageSystem === 'function'
        );
        
        if (languageManager && window.customHeader.isInitialized) {
            // Sync with existing language system
            console.log('🔗 Syncing with existing language system');
            
            // Listen for language changes from the main app
            window.addEventListener('languageChanged', (e) => {
                if (languageManager.updateLanguageContent) {
                    languageManager.updateLanguageContent(e.detail.language);
                }
            });
        }
    }
});

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    if (window.customHeader) {
        window.customHeader.destroy();
    }
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CustomHeader;
}