(function (global) {
    const languageMixin = {
        detectBrowserLanguage() {
            // Check for saved language preference first
            const savedLang = localStorage.getItem('preferred-language');
            if (savedLang && (savedLang === 'en' || savedLang === 'ar')) {
                return savedLang;
            }

            // Always default to English instead of browser detection
            // User can manually switch to Arabic if needed
            return 'en';
        },

        loadTranslations() {
            return {
                en: {
                    title: 'Get It Fast',
                    subtitle: 'conveys the idea of quick understanding and summarization',
                    urlLabel: 'YouTube Video URLs',
                    urlPlaceholder: 'https://www.youtube.com/watch?v=...',
                    summarizeBtn: 'Summarize Video',
                    singleMode: 'Single Video',
                    multiMode: 'Multiple Videos',
                    webpageMode: 'Webpage Analysis',
                    addUrl: 'Add Another URL',
                    summarizeMulti: 'Combine & Synthesize',
                    analyzeWebpage: 'Analyze Webpage',
                    webpageUrlLabel: 'Webpage URL',
                    webpageUrlPlaceholder: 'https://example.com/article...',
                    webpageSummary: 'Webpage Summary',
                    videoSummary: 'Video Summary',
                    multiVideoSummary: 'Combined Video Summary',
                    processing: 'Processing video...',
                    processingMulti: 'Processing multiple videos...',
                    processingWebpage: 'Processing webpage...',
                    extracting: 'Processing content...',
                    extractingMulti: 'Processing content...',
                    extractingWebpage: 'Loading content...',
                    generating: 'Creating intelligent summary...',
                    generatingMulti: 'Synthesizing comprehensive insight...',
                    poweredBy: 'Powered by Advanced AI',
                    formatting: {
                        videoSummaryTitle: 'Video Summary',
                        mainTopics: 'Main Topics & Themes',
                        keyPoints: 'Key Points & Information',
                        actionableTakeaways: 'Actionable Takeaways',
                        notableInsights: 'Notable Insights & Conclusions',
                        bottomLine: 'Bottom Line:'
                    },
                    copyBtn: 'Copy Summary',
                    copied: 'Copied!',
                    noSummaryToCopy: 'No summary available to copy',
                    copyFailed: 'Failed to copy to clipboard',
                    cancelBtn: 'Cancel',
                    cancelled: 'Cancelled',
                    cancelConfirm: 'Are you sure you want to cancel this operation?',
                    stepProcessing: 'Processing',
                    stepAnalyzing: 'Analyzing',
                    stepFinalizing: 'Finalizing',
                    stepExtractVideo: 'Extract Video',
                    stepExtractTranscript: 'Extract Transcript',
                    stepFetchContent: 'Fetch Content',
                    stepExtractText: 'Extract Text',
                    stepAIAnalysis: 'AI Analysis',
                    stepGenerateSummary: 'Generate Summary',
                    stepCreateClips: 'Create Clips',
                    stepComplete: 'Complete',
                    initializing: 'Starting...',
                    cacheFound: 'Using cached result',
                    cacheAgo: 'ago',
                    cacheCleared: 'Cache cleared successfully',
                    readyForNext: 'Ready to process another item!',
                    aiGenerating: 'AI is generating your summary...',
                    contentProcessing: 'Your content is being processed in real-time',
                    liveIndicator: 'Live',
                    errors: {
                        enterUrl: 'Please enter a YouTube URL',
                        invalidUrl: 'Please enter a valid YouTube URL',
                        enterWebpageUrl: 'Please enter a webpage URL',
                        invalidWebpageUrl: 'Please enter a valid webpage URL',
                        noTranscript: 'No content available to regenerate summary',
                        maxVideos: 'Maximum 4 videos allowed for comparison',
                        duplicateUrls: 'Duplicate URLs are not allowed. Please enter unique video URLs.'
                    }
                },
                ar: {
                    title: 'فهمني بسرعة',
                    subtitle: ' يوصل فكرة التلخيص والفهم السريع',
                    urlLabel: 'رابط الفيديو',
                    urlPlaceholder: 'https://www.youtube.com/watch?v=...',
                    summarizeBtn: 'تلخيص الفيديو',
                    singleMode: 'فيديو واحد',
                    multiMode: 'فيديوهات متعددة',
                    webpageMode: 'تحليل صفحات الويب',
                    addUrl: 'إضافة رابط آخر',
                    summarizeMulti: 'دمج وتكوين فكرة شاملة',
                    analyzeWebpage: 'تحليل الصفحة',
                    webpageUrlLabel: 'رابط الصفحة',
                    webpageUrlPlaceholder: 'https://example.com/article...',
                    webpageSummary: 'ملخص الصفحة',
                    videoSummary: 'ملخص الفيديو',
                    multiVideoSummary: 'الفكرة الشاملة المدمجة',
                    processing: 'معالجة الفيديو...',
                    processingMulti: 'معالجة فيديوهات متعددة...',
                    processingWebpage: 'معالجة الصفحة...',
                    extracting: 'جاري المعالجة...',
                    extractingMulti: 'جاري المعالجة...',
                    extractingWebpage: 'تحميل المحتوى...',
                    generating: 'إنشاء ملخص ذكي...',
                    generatingMulti: 'تكوين فكرة شاملة موحدة...',
                    poweredBy: 'مدعوم بالذكاء الاصطناعي المتطور',
                    formatting: {
                        videoSummaryTitle: 'ملخص الفيديو',
                        mainTopics: 'المواضيع الرئيسية',
                        keyPoints: 'النقاط الأساسية والمعلومات',
                        actionableTakeaways: 'الاستنتاجات القابلة للتطبيق',
                        notableInsights: 'الرؤى والاستنتاجات المهمة',
                        bottomLine: 'الخلاصة:'
                    },
                    copyBtn: 'نسخ الملخص',
                    copied: 'تم النسخ!',
                    noSummaryToCopy: 'لا يوجد ملخص متاح للنسخ',
                    copyFailed: 'فشل في النسخ للحافظة',
                    cancelBtn: 'إلغاء',
                    cancelled: 'تم الإلغاء',
                    cancelConfirm: 'هل أنت متأكد من إلغاء هذه العملية؟',
                    stepProcessing: 'المعالجة',
                    stepAnalyzing: 'التحليل',
                    stepFinalizing: 'الإنهاء',
                    stepExtractVideo: 'استخراج الفيديو',
                    stepExtractTranscript: 'استخراج النص',
                    stepFetchContent: 'جلب المحتوى',
                    stepExtractText: 'استخراج النص',
                    stepAIAnalysis: 'تحليل الذكاء الاصطناعي',
                    stepGenerateSummary: 'إنشاء الملخص',
                    stepCreateClips: 'إنشاء المقاطع',
                    stepComplete: 'اكتمل',
                    initializing: 'جاري البدء...',
                    cacheFound: 'استخدام نتيجة محفوظة',
                    cacheAgo: 'منذ',
                    cacheCleared: 'تم مسح الذاكرة المؤقتة بنجاح',
                    readyForNext: 'جاهز لمعالجة عنصر آخر!',
                    aiGenerating: 'الذكاء الاصطناعي ينشئ ملخصك...',
                    contentProcessing: 'يتم معالجة المحتوى الخاص بك في الوقت الفعلي',
                    liveIndicator: 'مباشر',
                    errors: {
                        enterUrl: 'يرجى إدخال رابط يوتيوب',
                        invalidUrl: 'يرجى إدخال رابط يوتيوب صحيح',
                        enterWebpageUrl: 'يرجى إدخال رابط الصفحة',
                        invalidWebpageUrl: 'يرجى إدخال رابط صفحة صحيح',
                        noTranscript: 'لا يوجد محتوى متاح لإعادة توليد الملخص',
                        maxVideos: 'الحد الأقصى 4 فيديوهات للمقارنة',
                        duplicateUrls: 'الروابط المكررة غير مسموحة. يرجى إدخال روابط فيديوهات مختلفة.'
                    }
                }
            };
        },

        t(key) {
            // Translation helper function
            const keys = key.split('.');
            let value = this.translations[this.currentLanguage];

            for (const k of keys) {
                value = value?.[k];
            }

            return value || key;
        },

        applyLanguage() {
            const isArabic = this.currentLanguage === 'ar';

            document.documentElement.dir = isArabic ? 'rtl' : 'ltr';
            document.documentElement.lang = this.currentLanguage;

            document.body.classList.toggle('arabic-font', isArabic);
            document.body.classList.toggle('rtl', isArabic);
            document.body.style.direction = isArabic ? 'rtl' : '';

            const sidenav = document.getElementById('sidenav-main');
            if (sidenav) {
                sidenav.classList.toggle('fixed-end', isArabic);
                sidenav.classList.toggle('me-3', isArabic);
                sidenav.classList.toggle('rotate-caret', isArabic);
                sidenav.classList.toggle('fixed-start', !isArabic);
                sidenav.classList.toggle('ms-3', !isArabic);
            }

            const mainContent = document.querySelector('.main-content');
            if (mainContent) {
                mainContent.classList.toggle('overflow-x-hidden', isArabic);
            }

            this.updateUITexts();
        },

        updateUITexts() {
            const isArabic = this.currentLanguage === 'ar';

            document.querySelectorAll('[data-en]').forEach((element) => {
                const translatedValue = isArabic ? element.getAttribute('data-ar') : element.getAttribute('data-en');
                if (!translatedValue) {
                    return;
                }

                const tag = element.tagName.toLowerCase();

                if (tag === 'input' || tag === 'textarea') {
                    if (element.hasAttribute('placeholder')) {
                        element.placeholder = translatedValue;
                    }
                    if (element.type === 'button' || element.type === 'submit') {
                        element.value = translatedValue;
                    }
                } else if (tag === 'option') {
                    element.text = translatedValue;
                } else if (tag === 'button') {
                    element.innerText = translatedValue;
                } else {
                    element.textContent = translatedValue;
                }
            });

            // Ensure dynamic multi-video inputs receive localized placeholders
            document.querySelectorAll('.youtube-url-multi').forEach((input, index) => {
                const hasCustomTranslation = input.hasAttribute('data-en') && input.hasAttribute('data-ar');
                if (hasCustomTranslation) {
                    const placeholderTranslation = isArabic ? input.getAttribute('data-ar') : input.getAttribute('data-en');
                    if (placeholderTranslation) {
                        input.placeholder = placeholderTranslation;
                    }
                    return;
                }

                const numberedPlaceholder = isArabic
                    ? `https://www.youtube.com/watch?v=... (فيديو ${index + 1})`
                    : `https://www.youtube.com/watch?v=... (Video ${index + 1})`;
                input.placeholder = numberedPlaceholder;
            });

            this.updateLanguageSwitcher();
        },

        switchLanguage(lang) {
            this.currentLanguage = lang;
            this.applyLanguage();

            // Save language preference
            localStorage.setItem('preferred-language', lang);
        },

        initializeLanguageSwitcher() {
            const attachListener = (button, lang) => {
                if (!button || button.dataset.langListenerAttached === 'true') {
                    return;
                }

                button.addEventListener('click', () => this.switchLanguage(lang));
                button.dataset.langListenerAttached = 'true';
            };

            attachListener(document.getElementById('lang-en'), 'en');
            attachListener(document.getElementById('lang-ar'), 'ar');
        },

        initializeLanguageSystem() {
            if (!this.translations || Object.keys(this.translations).length === 0) {
                this.translations = this.loadTranslations();
            }

            this.currentLanguage = this.detectBrowserLanguage();
            this.applyLanguage();
            this.initializeLanguageSwitcher();
        },

        updateLanguageSwitcher() {
            const enBtn = document.getElementById('lang-en');
            const arBtn = document.getElementById('lang-ar');

            if (!enBtn || !arBtn) {
                return;
            }

            const isArabic = this.currentLanguage === 'ar';

            enBtn.classList.toggle('active', !isArabic);
            arBtn.classList.toggle('active', isArabic);

            enBtn.setAttribute('aria-pressed', String(!isArabic));
            arBtn.setAttribute('aria-pressed', String(isArabic));
        }
    };

    global.YouTubeTranscriptAppMixins = global.YouTubeTranscriptAppMixins || [];
    global.YouTubeTranscriptAppMixins.push(languageMixin);
})(window);
