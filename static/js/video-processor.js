(function (global) {
    const videoProcessorMixin = {
        async summarizeVideoDirectly() {
            const url = this.urlInput.value.trim();

            if (!url) {
                this.showError(this.t('errors.enterUrl'));
                return;
            }

            if (!this.isValidYouTubeUrl(url)) {
                this.showError(this.t('errors.invalidUrl'));
                return;
            }

            // Check cache first
            const cachedResult = this.getCachedResult(url, 'video');
            if (cachedResult) {
                this.showCacheStatus(url, 'video');
                this.displayVideoInfo(cachedResult.videoInfo, cachedResult.videoId);
                this.displaySummary(cachedResult.summary);
                this.hideStatus();
                return;
            }

            this.summarizeVideoBtn.disabled = true;
            this.resetSections();

            try {
                // Start streaming video analysis (combines transcript extraction and summarization)
                this.showStreamingProgress('Processing video...', 'summary');

                const response = await fetch('/api/summarize-video-stream', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        url: url,
                        language: this.currentLanguage
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to start video analysis');
                }

                // Start listening to progress stream
                await this.listenToProgress(data.task_id);

            } catch (error) {
                if (error.name === 'CancelError') {
                    // Don't show error for user-initiated cancellation
                    // The cancelCurrentTask() method already handles the UI
                } else {
                    this.showError(error.message);
                }
            } finally {
                this.summarizeVideoBtn.disabled = false;
                this.currentTaskId = null;
                this.currentEventSource = null;
                this.hideCancelButton();
            }
        },

        async summarizeMultipleVideos() {
            const urlInputs = this.urlInputsContainer.querySelectorAll('.youtube-url-multi');
            const urls = Array.from(urlInputs).map(input => input.value.trim()).filter(url => url);

            if (urls.length === 0) {
                this.showError(this.t('errors.enterUrl'));
                return;
            }

            // Check for maximum limit
            if (urls.length > 4) {
                this.showError(this.t('errors.maxVideos'));
                return;
            }

            // Check for duplicate URLs
            const uniqueUrls = new Set(urls);
            if (uniqueUrls.size !== urls.length) {
                this.showError(this.t('errors.duplicateUrls'));
                return;
            }

            // Validate all URLs
            for (let url of urls) {
                if (!this.isValidYouTubeUrl(url)) {
                    this.showError(`Invalid URL: ${url}`);
                    return;
                }
            }

            // Check cache for multiple videos (use sorted URLs as cache key)
            const sortedUrls = [...urls].sort();
            const multiCacheKey = sortedUrls.join('|');
            const cachedResult = this.getCachedResult(multiCacheKey, 'multi');
            if (cachedResult) {
                this.showCacheStatus(multiCacheKey, 'multi');
                this.displayMultiVideoSummary(cachedResult.combinedSummary, cachedResult.videoInfos);
                this.hideStatus();
                return;
            }

            this.summarizeMultiBtn.disabled = true;
            this.resetSections();

            // Set up abort controller for cancellation
            this.currentAbortController = new AbortController();
            this.showCancelButton();

            try {
                this.showLoading(this.t('processingMulti'));

                // Start multi-video processing
                const response = await fetch('/api/process-multiple-videos', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        urls: urls,
                        language: this.currentLanguage
                    }),
                    signal: this.currentAbortController.signal
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to start multi-video processing');
                }

                // Wait for processing to complete
                const result = await this.waitForTaskCompletion(data.task_id);
                if (!result) return; // Task was cancelled

                // Display results - check if streaming content was already shown
                const streamingContent = document.getElementById('streaming-summary-content');
                if (!streamingContent || streamingContent.textContent.trim().length < 50) {
                    // No meaningful streaming content was shown, display normally
                    this.displayMultiVideoSummary(result.combined_summary, result.video_infos);
                } else {
                    // Streaming content was shown, just show the copy button
                    this.copySummaryBtn.classList.remove('hidden');
                    // Update the final content in the streaming area
                    this.updateStreamingSummary(result.combined_summary);
                }
                this.hideStatus();

                // Cache the successful result
                const sortedUrlsResult = [...urls].sort();
                const multiCacheKeyResult = sortedUrlsResult.join('|');
                this.setCachedResult(multiCacheKeyResult, {
                    combinedSummary: result.combined_summary,
                    videoInfos: result.video_infos
                }, 'multi');

            } catch (error) {
                if (error.name === 'AbortError' || error.name === 'CancelError') {
                    // Don't show error for user-initiated cancellation
                    // The cancelCurrentTask() method already handles the UI
                } else {
                    this.showError(error.message);
                }
            } finally {
                this.summarizeMultiBtn.disabled = false;
                this.currentAbortController = null;
                this.currentTaskId = null;
                this.currentEventSource = null;
                this.hideCancelButton();
            }
        },

        displayMultiVideoSummary(summary, videoInfos) {
            // Show video information for all processed videos
            if (videoInfos && videoInfos.length > 0) {
                const infoHtml = videoInfos.map((info, index) => `
                    <div class="flex flex-col sm:flex-row gap-4 p-4 border border-gray-200 rounded-lg">
                        <img src="${info.thumbnail}" class="w-full sm:w-32 h-24 object-cover rounded-lg" alt="Video ${index + 1} thumbnail">
                        <div class="flex-1">
                            <h4 class="font-medium text-gray-900">Video ${index + 1}: ${info.title}</h4>
                            <p class="text-sm text-gray-600 mt-1">${info.channel}</p>
                            <div class="flex items-center mt-2">
                                <i class="fas fa-clock text-gray-400 mr-1"></i>
                                <span class="text-xs text-gray-500">${info.duration || 'Unknown duration'}</span>
                            </div>
                        </div>
                    </div>
                `).join('');

                this.videoInfo.innerHTML = `
                    <div class="space-y-3">
                        <h3 class="font-medium text-gray-900 mb-3">Processed Videos (${videoInfos.length})</h3>
                        ${infoHtml}
                        <div class="flex items-center mt-4 p-2 bg-green-50 rounded">
                            <i class="fas fa-robot text-green-600 mr-2"></i>
                            <span class="text-sm text-green-700 font-medium">${this.t('multiVideoSummary')} - ${this.t('poweredBy')}</span>
                        </div>
                    </div>
                `;
                this.videoInfo.classList.remove('hidden');
            }

            // Display the combined summary
            this.displaySummary(summary);
        },

        async analyzeWebpage() {
            const url = this.webpageUrlInput.value.trim();

            if (!url) {
                this.showError(this.t('errors.enterWebpageUrl'));
                return;
            }

            if (!this.isValidWebpageUrl(url)) {
                this.showError(this.t('errors.invalidWebpageUrl'));
                return;
            }

            // Check cache first
            const cachedResult = this.getCachedResult(url, 'webpage');
            if (cachedResult) {
                this.showCacheStatus(url, 'webpage');
                this.displaySummary(cachedResult.summary);
                this.hideStatus();
                return;
            }

            this.analyzeWebpageBtn.disabled = true;
            this.resetSections();

            try {
                // Start streaming analysis
                this.showStreamingProgress('Starting webpage analysis...', 'webpage');

                const response = await fetch('/api/analyze-webpage-stream', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        url: url,
                        language: this.currentLanguage
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to start webpage analysis');
                }

                // Start listening to progress stream
                await this.listenToProgress(data.task_id);

            } catch (error) {
                if (error.name === 'CancelError') {
                    // Don't show error for user-initiated cancellation
                    // The cancelCurrentTask() method already handles the UI
                } else {
                    this.showError(error.message);
                }
            } finally {
                this.analyzeWebpageBtn.disabled = false;
                this.currentTaskId = null;
                this.currentEventSource = null;
                this.hideCancelButton();
            }
        },

        displayWebpageInfo(data) {
            // Show webpage information
            const infoContainer = this.webpageInfo || this.videoInfo;
            if (!infoContainer) {
                console.warn('No container available to display webpage info');
                return;
            }

            infoContainer.innerHTML = `
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
            infoContainer.classList.remove('hidden');
        },

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
        },

        isValidYouTubeUrl(url) {
            const patterns = [
                /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)/,
                /youtube\.com\/watch\?.*v=([^&\n?#]+)/
            ];

            return patterns.some(pattern => pattern.test(url));
        },

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
        },

        displayVideoInfo(videoInfo, videoId) {
            this.videoThumbnail.src = videoInfo.thumbnail || `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;
            this.videoTitle.textContent = videoInfo.title;
            this.videoChannel.textContent = `Channel: ${videoInfo.author}`;

            this.videoInfo.classList.remove('hidden');
        },

        displaySummary(summary) {
            this.ensureSummaryStyles && this.ensureSummaryStyles();
            // Format the summary with enhanced markdown-like styling
            let formattedSummary = summary
                // First, temporarily replace double asterisks to avoid conflicts
                .replace(/\*\*(.*?)\*\*/g, '___DOUBLE_BOLD___$1___END_DOUBLE_BOLD___')

                // Convert single *bold* text (now safe from double asterisk interference)
                .replace(/\*([^*\n]+?)\*/g, '<span class="summary-italic">$1</span>')

                // Restore double asterisk bold formatting
                .replace(/___DOUBLE_BOLD___(.*?)___END_DOUBLE_BOLD___/g, '<span class="summary-bold">$1</span>')

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
            formattedSummary = formattedSummary.replace(/(<li class="mb-3 text-gray-700[^\"]*">.*?<\/li>(?:<br>)*)+/g, (match) => {
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
        },

        ensureSummaryStyles() {
            if (document.getElementById('summary-style-rules')) {
                return;
            }

            const style = document.createElement('style');
            style.id = 'summary-style-rules';
            style.textContent = `
                #summary-text {
                    font-size: 1rem;
                    line-height: 1.7;
                    color: #1f2937;
                }
                #summary-text p {
                    margin-bottom: 1rem;
                    font-weight: 400;
                    line-height: 1.7;
                    color: inherit;
                }
                #summary-text ul,
                #summary-text ol {
                    font-size: 1rem;
                    line-height: 1.65;
                    color: inherit;
                    padding-inline-start: 1.25rem;
                }
                #summary-text li {
                    font-weight: 400;
                }
                #summary-text h1,
                #summary-text h2,
                #summary-text h3 {
                    font-weight: 600;
                    color: #1f2937;
                }
                #summary-text h1 {
                    font-size: 1.35rem;
                }
                #summary-text h2 {
                    font-size: 1.2rem;
                }
                #summary-text h3 {
                    font-size: 1.05rem;
                }
                #summary-text .summary-bold {
                    font-weight: 600;
                    color: #111827;
                    background: rgba(251, 191, 36, 0.25);
                    padding: 0 0.18rem;
                    border-radius: 0.25rem;
                }
                #summary-text .summary-italic {
                    font-style: italic;
                    color: inherit;
                }
                #summary-text table {
                    font-size: 0.95rem;
                }
            `;
            document.head.appendChild(style);
        },

        formatTables(text) {
            // Enhanced markdown table formatting with better styling
            return text.replace(/(\|.*?\|(?:\r?\n|\r))+/gm, (match) => {
                const lines = match.trim().split(/\r?\n|\r/);
                if (lines.length < 2) return match;

                // Check if it's a proper markdown table (has separator row)
                const hasSeparator = lines[1] && lines[1].match(/^[\|\s\-\|:]+\|$/);
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
        },

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
        },

        async generateShortsDirectly() {
            this.addDebugMessage('🎬 Generate Shorts clicked - Using CLIENT-SIDE CE.SDK Processing');
            const url = document.getElementById('shorts-youtube-url').value.trim();

            if (!url) {
                this.showError(this.t('errors.enterUrl'));
                return;
            }

            if (!this.isValidYouTubeUrl(url)) {
                this.showError(this.t('errors.invalidUrl'));
                return;
            }

            const generateBtn = document.getElementById('generate-shorts-btn');
            generateBtn.disabled = true;
            this.resetSections();

            try {
                // Use CLIENT-SIDE processing with CE.SDK instead of server API
                this.addDebugMessage('🎨 Initializing CreativeEditor SDK for client-side processing...');
                this.showStreamingProgress('Initializing CE.SDK...', 'shorts');

                // Check if client-side integration is available
                if (typeof clientShortsIntegration === 'undefined') {
                    throw new Error('Client-side shorts integration not loaded. Please refresh the page.');
                }

                this.addDebugMessage('✅ CE.SDK integration found, starting generation...');
                
                // Call client-side processing
                await clientShortsIntegration.generateShortsClientSide();
                
                this.addDebugMessage('✅ Client-side shorts generation complete');

            } catch (error) {
                if (error.message === 'Task cancelled') {
                    // Don't show error for user-initiated cancellation
                    this.addDebugMessage('📋 Task cancelled by user');
                } else {
                    this.addDebugMessage(`❌ Error: ${error.message}`);
                    this.showError(`Shorts generation failed: ${error.message}`);
                }
            } finally {
                generateBtn.disabled = false;
            }
        },

        async listenToShortsProgress(taskId, streamUrl) {
            return new Promise((resolve, reject) => {
                this.currentTaskId = taskId;
                this.taskCancelled = false;

                console.log('🔍 DEBUG: Creating EventSource for URL:', streamUrl);
                const eventSource = new EventSource(streamUrl);
                this.currentEventSource = eventSource;

                eventSource.onopen = (event) => {
                    console.log('🔍 DEBUG: EventSource opened successfully', event);
                    this.addDebugMessage('🔗 EventSource connected');
                };

                eventSource.onmessage = (event) => {
                    if (this.taskCancelled) return;

                    try {
                        console.log('📡 RAW SSE event received:', event.data);
                        this.addDebugMessage('📡 SSE event received');
                        
                        const data = JSON.parse(event.data);
                        console.log('📡 Shorts progress update:', data);
                        this.addDebugMessage(`📊 Progress: ${data.percentage}% - ${data.message}`);
                        
                        // Handle queue status
                        if (data.status === 'queued') {
                            console.log('🎯 DEBUG: In queue, position:', data.queue_position);
                            const queueMessage = `Queue position: #${data.queue_position} (estimated wait: ${data.estimated_wait_minutes} minutes)`;
                            this.updateLoadingProgress(data.percentage, queueMessage, '⏳ Queued');
                            this.showCancelButton(taskId);
                            return;
                        }
                        
                        if (data.status === 'processing') {
                            console.log('🔍 DEBUG: Processing status received, percentage:', data.percentage);
                            
                            // Show cancel button for processing tasks during early stages
                            if (data.percentage < 60) {  // Show cancel until 60% progress
                                console.log('🚫 DEBUG: Showing cancel button at', data.percentage, '% progress');
                                this.showCancelButton(taskId);
                                
                                // Extra debug - check if button exists after showing it
                                setTimeout(() => {
                                    const btn = document.getElementById('cancel-shorts-btn');
                                    console.log('🧪 DEBUG: Cancel button exists after showing?', !!btn);
                                    if (btn) {
                                        console.log('🧪 DEBUG: Button properties:', {
                                            disabled: btn.disabled,
                                            onclick: btn.onclick,
                                            innerHTML: btn.innerHTML
                                        });
                                    }
                                }, 100);
                            } else {
                                console.log('🚫 DEBUG: Hiding cancel button at', data.percentage, '% progress');
                                this.hideCancelButton(); // Hide cancel button after 60% progress
                            }
                            
                            // Enhanced progress with stage-specific messaging
                            let enhancedMessage = data.message;
                            let stageInfo = '';
                            
                            // Add visual indicators based on progress stages
                            if (data.percentage <= 10) {
                                stageInfo = '🔄 Initializing...';
                            } else if (data.percentage <= 50) {
                                stageInfo = '🤖 AI Analysis...';
                                enhancedMessage += ' <span class="loading-dots"></span>';
                            } else if (data.percentage <= 65) {
                                stageInfo = '📋 Preparing Clips...';
                            } else if (data.percentage < 95) {
                                stageInfo = '🎬 Creating Videos...';
                                // Add clip counter if available
                                if (data.extra_data && data.extra_data.current_clip) {
                                    stageInfo = `🎬 Creating Clip ${data.extra_data.current_clip}/${data.extra_data.total_clips}`;
                                }
                            } else {
                                stageInfo = '✨ Finalizing...';
                            }
                            
                            // Stop any ongoing progress simulation when real update arrives
                            this.stopProgressSimulation();
                            
                            // Update progress with enhanced messaging
                            this.updateLoadingProgress(data.percentage, enhancedMessage, stageInfo);
                            
                            // Start progress simulation for long-running stages
                            if (data.percentage >= 40 && data.percentage < 55) {
                                // AI analysis can take long - simulate progress to 55%
                                this.simulateProgressFill(data.percentage, 55, 15000);
                            }
                            // Removed simulation for video creation (60-95%) since backend now provides granular updates
                            
                            // Handle partial results - show clips as they become ready
                            if (data.partial_result && data.partial_result.new_clip) {
                                console.log('🎬 New clip ready:', data.partial_result.new_clip);
                                console.log('🔍 DEBUG: Partial result received:', data.partial_result);
                                console.log('🔍 DEBUG: About to call showNewClip...');
                                this.addDebugMessage(`🎬 New clip ready: ${data.partial_result.new_clip.title}`);
                                this.showNewClip(data.partial_result.new_clip, data.partial_result);
                                console.log('🔍 DEBUG: showNewClip call completed');
                            } else {
                                console.log('🔍 DEBUG: No partial result in processing update, partial_result:', data.partial_result);
                            }
                        } else if (data.status === 'completed') {
                            console.log('🎉 Shorts generation completed!', data);
                            
                            // Stop any progress simulation
                            this.stopProgressSimulation();
                            
                            // Final completion animation
                            this.updateLoadingProgress(100, 'All clips ready! 🎉', '✅ Complete');
                            
                            // Add completion delay for better UX
                            setTimeout(() => {
                                eventSource.close();
                                this.currentEventSource = null;
                                this.currentTaskId = null;
                                
                                // Display results
                                if (data.result && data.result.success) {
                                    this.displayVideoInfo(data.result.video_info, data.result.video_id);
                                    this.displayShortsClips(data.result.clips);
                                } else {
                                    this.showError('Shorts generation completed but no results received');
                                }
                                
                                this.hideStatus();
                                
                                // Add celebration effect to all clips
                                setTimeout(() => {
                                    const clipItems = document.querySelectorAll('.clip-item');
                                    clipItems.forEach((item, index) => {
                                        setTimeout(() => {
                                            item.classList.add('newly-created');
                                        }, index * 100);
                                    });
                                }, 500);
                            }, 1500);
                            resolve(data.result);
                        } else if (data.status === 'error') {
                            eventSource.close();
                            this.currentEventSource = null;
                            this.currentTaskId = null;
                            this.showError(data.message || 'Shorts generation failed');
                            reject(new Error(data.message || 'Shorts generation failed'));
                        } else if (data.status === 'cancelled') {
                            eventSource.close();
                            this.currentEventSource = null;
                            this.currentTaskId = null;
                            this.hideStatus();
                            this.showInfo('Shorts generation cancelled');
                            // Reject like other functions to trigger catch block
                            reject(new Error('Task cancelled'));
                        }
                    } catch (err) {
                        console.error('Error parsing progress data:', err);
                    }
                };

                eventSource.onerror = (error) => {
                    console.error('🔍 DEBUG: EventSource error:', error);
                    console.error('🔍 DEBUG: EventSource readyState:', eventSource.readyState);
                    console.error('🔍 DEBUG: EventSource url:', eventSource.url);
                    
                    if (this.taskCancelled) return;
                    
                    eventSource.close();
                    this.currentEventSource = null;
                    this.currentTaskId = null;
                    this.showError('Connection lost during shorts generation');
                    reject(new Error('Connection error'));
                };
            });
        },

        displayShortsClips(clips) {
            console.log('🎬 displayShortsClips called with:', clips?.length, 'clips');
            
            if (!clips || clips.length === 0) {
                console.log('❌ No clips to display');
                this.showError('No clips were generated');
                return;
            }

            // Log clip details for debugging
            clips.forEach((clip, index) => {
                console.log(`📹 Clip ${index + 1}:`, {
                    clip_id: clip.clip_id,
                    title: clip.title,
                    has_file: clip.has_file,
                    filename: clip.filename
                });
            });

            // Store clips for use in other functions
            this.currentShortsClips = clips;
            this.currentViewMode = this.currentViewMode || 'grid'; // Default to grid view

            const clipsSection = document.getElementById('shorts-clips-section');
            const clipsContainer = document.getElementById('shorts-clips-container');
            const clipsCountText = document.getElementById('clips-count-text');

            // Update clips count
            clipsCountText.textContent = `${clips.length} clips`;

            // Set container class based on view mode
            console.log('🎨 Current view mode:', this.currentViewMode);
            clipsContainer.className = '';
            if (this.currentViewMode === 'grid') {
                clipsContainer.classList.add('video-clips-grid');
                console.log('✅ Added video-clips-grid class');
            } else {
                clipsContainer.classList.add('video-clips-list');
                console.log('✅ Added video-clips-list class');
            }

            // Generate clips HTML based on view mode
            let clipsHtml = '';
            clips.forEach((clip, index) => {
                const clipNumber = clip.clip_number || index + 1;
                const title = clip.title || `Clip ${clipNumber}`;
                const description = clip.description || 'No description available';
                const duration = clip.duration || 30;
                const startTime = clip.start_time || 0;
                const endTime = clip.end_time || 30;
                const selectionReason = clip.selection_reason || 'Selected by AI';
                const fileSize = clip.file_size ? this.formatFileSize(clip.file_size) : 'Timestamp Only';
                const processingMethod = clip.processing_method || 'Standard';
                const hasFile = clip.has_video_file && clip.clip_id; // Updated for in-memory clips
                const clipId = clip.clip_id || '';

                // Different styling based on whether we have actual files or just timestamps
                const cardClass = hasFile ? 'clip-item-success' : 'clip-item-timestamp';
                const badgeClass = hasFile ? 'bg-success' : 'bg-warning';
                const downloadInstructions = clip.download_instructions || '';

                console.log(`Clip ${clipNumber}: hasFile=${hasFile}, clipId=${clipId}, video_ready=${clip.video_ready}`); // Debug

                if (this.currentViewMode === 'grid') {
                    // Grid view - YouTube-style card with inline video support
                    clipsHtml += `
                        <div class="video-clip-card">
                            <div class="video-container" data-clip-id="${clipId}">
                                <div class="video-placeholder" id="placeholder-${clipId}">
                                    <!-- Video thumbnail image -->
                                    <img class="video-thumbnail-image" id="thumbnail-${clipId}" src="" alt="Video thumbnail" style="display: none;" loading="lazy">
                                    
                                    <!-- Video overlay -->
                                    <div class="video-overlay"></div>
                                    
                                    <!-- Status badge -->
                                    <div class="video-status-badge ${hasFile ? 'ready' : 'processing'}">
                                        ${hasFile ? '▶' : '⚡'}
                                    </div>
                                    
                                    <!-- Video number -->
                                    <div class="video-number">${clipNumber}</div>
                                    
                                    <!-- Play button in center -->
                                    <div class="video-play-button" onclick="youtubeApp.playInlineVideo('${clipId}', ${clipNumber})">
                                        <i class="fas fa-play"></i>
                                    </div>
                                </div>
                                <video class="inline-video-player" id="video-${clipId}" style="display: none;" controls>
                                    <source src="" type="video/mp4">
                                    Your browser does not support the video tag.
                                </video>
                            </div>
                            <div class="video-clip-info">
                                <h6 class="video-title">${this.escapeHtml(title)}</h6>
                                <p class="video-description">${this.escapeHtml(description)}</p>
                                <div class="video-meta">
                                    <small class="text-muted">
                                        <i class="fas fa-clock me-1"></i>
                                        ${this.formatTime(startTime)} - ${this.formatTime(endTime)}
                                    </small>
                                </div>
                                <div class="video-actions mt-2">
                                    ${hasFile ? `
                                        <button class="btn btn-primary btn-sm" onclick="youtubeApp.playInlineVideo('${clipId}', ${clipNumber})">
                                            <i class="fas fa-play me-1"></i>Play
                                        </button>
                                        <button class="btn btn-outline-primary btn-sm" onclick="youtubeApp.downloadVideoClip('${clipId}')">
                                            <i class="fas fa-download me-1"></i>Download
                                        </button>
                                    ` : `
                                        <button class="btn btn-outline-secondary btn-sm" disabled>
                                            <i class="fas fa-spinner fa-spin me-1"></i>
                                            Processing...
                                        </button>
                                    `}
                                </div>
                            </div>
                        </div>
                    `;
                } else {
                    // List view - detailed layout with inline video support
                    clipsHtml += `
                        <div class="clip-item mb-4 p-3 border rounded ${cardClass}">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <h5 class="clip-title mb-1">
                                    <i class="fas fa-${hasFile ? 'video' : 'clock'} text-primary me-2"></i>
                                    ${this.escapeHtml(title)}
                                </h5>
                                <div class="d-flex gap-2">
                                    <span class="badge ${badgeClass}">
                                        ${duration}s
                                    </span>
                                    <span class="badge bg-info">
                                        ${processingMethod}
                                    </span>
                                </div>
                            </div>
                        
                        <div class="row mb-3">
                            <div class="col-md-3">
                                <div class="video-container">
                                    <div class="video-placeholder" id="placeholder-${clipId}" style="aspect-ratio: 3/4; background: url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 300 400\"><rect width=\"300\" height=\"400\" fill=\"%23f8f9fa\"/><circle cx=\"150\" cy=\"200\" r=\"40\" fill=\"%23dee2e6\"/><polygon points=\"135,185 135,215 165,200\" fill=\"%23ffffff\"/></svg>'); display: flex; align-items: center; justify-content: center; border-radius: 8px; position: relative;">
                                        <div class="video-status-badge ${hasFile ? 'ready' : 'processing'}" style="position: absolute; top: 8px; left: 8px; width: 24px; height: 24px; border-radius: 50%; background: rgba(0, 0, 0, 0.7); display: flex; align-items: center; justify-content: center; font-size: 12px; color: white;">
                                            ${hasFile ? '▶' : '⚡'}
                                        </div>
                                        <div class="video-number" style="position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.8); color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px;">${clipNumber}</div>
                                    </div>
                                    <video class="inline-video-player" id="video-${clipId}" style="display: none; width: 100%; aspect-ratio: 3/4; border-radius: 8px;" controls>
                                        <source src="" type="video/mp4">
                                        Your browser does not support the video tag.
                                    </video>
                                </div>
                            </div>
                            <div class="col-md-9">
                                <p class="clip-description text-muted mb-2">
                                    ${this.escapeHtml(description)}
                                </p>
                                <div class="clip-reason">
                                    <small class="text-info">
                                        <i class="fas fa-lightbulb me-1"></i>
                                        <strong>Why selected:</strong> ${this.escapeHtml(selectionReason)}
                                    </small>
                                </div>
                                ${downloadInstructions ? `
                                    <div class="download-instructions mt-2">
                                        <small class="text-warning">
                                            <i class="fas fa-terminal me-1"></i>
                                            <strong>Manual Download:</strong> ${this.escapeHtml(downloadInstructions)}
                                        </small>
                                    </div>
                                ` : ''}
                                <div class="clip-meta mt-2">
                                    <div class="mb-1">
                                        <small class="text-muted">
                                            <i class="fas fa-clock me-1"></i>
                                            ${this.formatTime(startTime)} - ${this.formatTime(endTime)} |
                                            <i class="fas fa-${hasFile ? 'hdd' : 'info-circle'} me-1"></i>
                                            ${fileSize}
                                        </small>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="clip-actions">
                            <button class="btn btn-outline-primary btn-sm me-2" onclick="youtubeApp.copyClipInfo(${clipNumber})">
                                <i class="fas fa-copy me-1"></i>
                                Copy Info
                            </button>
                            ${hasFile ? `
                                <div class="btn-group btn-group-sm">
                                    <button class="btn btn-primary" onclick="youtubeApp.playInlineVideo('${clip.clip_id || ''}', ${clipNumber})">
                                        <i class="fas fa-play me-1"></i>
                                        Play
                                    </button>
                                    <button class="btn btn-outline-primary" onclick="youtubeApp.downloadVideoClip('${clip.clip_id || ''}')">
                                        <i class="fas fa-download me-1"></i>
                                        Download
                                    </button>
                                </div>
                            ` : `
                                <div class="btn-group btn-group-sm">
                                    <button class="btn btn-outline-secondary" onclick="youtubeApp.copyDownloadCommand(${clipNumber})">
                                        <i class="fas fa-terminal me-1"></i>
                                        yt-dlp
                                    </button>
                                    <button class="btn btn-outline-secondary" onclick="youtubeApp.copyFFmpegCommand(${clipNumber})">
                                        <i class="fas fa-code me-1"></i>
                                        ffmpeg
                                    </button>
                                    <button class="btn btn-outline-primary" onclick="youtubeApp.viewOnYoutube(${clipNumber})">
                                        <i class="fab fa-youtube me-1"></i>
                                        View
                                    </button>
                                </div>
                            `}
                        </div>
                    </div>
                    `;
                }
            });

            clipsContainer.innerHTML = clipsHtml;
            clipsSection.classList.remove('hidden');

            // Scroll to clips section
            clipsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        },

        formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },

        formatTime(seconds) {
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        },

        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        switchToGridView() {
            console.log('Switching to grid view');
            this.currentViewMode = 'grid';
            document.getElementById('grid-view-btn').classList.add('active');
            document.getElementById('list-view-btn').classList.remove('active');
            
            if (this.currentShortsClips) {
                this.displayShortsClips(this.currentShortsClips);
            }
        },

        switchToListView() {
            console.log('Switching to list view');
            this.currentViewMode = 'list';
            document.getElementById('list-view-btn').classList.add('active');
            document.getElementById('grid-view-btn').classList.remove('active');
            
            if (this.currentShortsClips) {
                this.displayShortsClips(this.currentShortsClips);
            }
        },

        copyClipInfo(clipNumber) {
            try {
                const clipElement = document.querySelector(`.clip-item:nth-child(${clipNumber})`);
                if (!clipElement) return;

                const title = clipElement.querySelector('.clip-title').textContent.trim();
                const description = clipElement.querySelector('.clip-description').textContent.trim();
                const reason = clipElement.querySelector('.clip-reason small').textContent.trim();
                const timeRange = clipElement.querySelector('.clip-meta small').textContent.trim();

                const clipInfo = `${title}\n\n${description}\n\n${reason}\n\n${timeRange}`;

                navigator.clipboard.writeText(clipInfo).then(() => {
                    this.showInfo('Clip info copied to clipboard!');
                }).catch(() => {
                    this.fallbackCopyText(clipInfo);
                });
            } catch (error) {
                this.showError('Failed to copy clip info');
            }
        },

        copyDownloadCommand(clipNumber) {
            try {
                const clipElement = document.querySelector(`.clip-item:nth-child(${clipNumber})`);
                if (!clipElement) return;

                const downloadInstructions = clipElement.querySelector('.download-instructions small');
                if (downloadInstructions) {
                    const command = downloadInstructions.textContent.replace('Manual Download: ', '').trim();
                    
                    navigator.clipboard.writeText(command).then(() => {
                        this.showInfo('Download command copied! Run this in your terminal to get the clip.');
                    }).catch(() => {
                        this.fallbackCopyText(command);
                    });
                } else {
                    this.showError('No download command available for this clip');
                }
            } catch (error) {
                this.showError('Failed to copy download command');
            }
        },

        fallbackCopyText(text) {
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            this.showInfo('Clip info copied to clipboard!');
        },

        copyFFmpegCommand(clipNumber) {
            try {
                if (!this.currentShortsClips || !this.currentShortsClips[clipNumber - 1]) {
                    this.showError('Clip data not available');
                    return;
                }

                const clip = this.currentShortsClips[clipNumber - 1];
                const ffmpegCommand = clip.ffmpeg_command;
                
                if (ffmpegCommand) {
                    navigator.clipboard.writeText(ffmpegCommand).then(() => {
                        this.showInfo('FFmpeg command copied! Run this to extract the clip with FFmpeg.');
                    }).catch(() => {
                        this.fallbackCopyText(ffmpegCommand);
                    });
                } else {
                    this.showError('FFmpeg command not available for this clip');
                }
            } catch (error) {
                this.showError('Failed to copy FFmpeg command');
            }
        },

        playInlineVideo(clipId, clipNumber) {
            console.log('playInlineVideo called with clipId:', clipId, 'clipNumber:', clipNumber);
            if (!clipId) {
                console.error('No clipId provided to playInlineVideo');
                this.showError('Video clip ID not available');
                return;
            }

            // Find the video elements
            const placeholder = document.getElementById(`placeholder-${clipId}`);
            const videoPlayer = document.getElementById(`video-${clipId}`);
            
            if (!placeholder || !videoPlayer) {
                console.error('Video elements not found for clipId:', clipId);
                this.showError('Video player not found');
                return;
            }

            // Set the video source
            const videoSource = videoPlayer.querySelector('source');
            if (videoSource) {
                videoSource.src = `/api/stream-clip/${clipId}`;
            }

            // Hide placeholder and show video
            placeholder.style.display = 'none';
            videoPlayer.style.display = 'block';
            
            // Start playing the video
            videoPlayer.load();
            videoPlayer.play().catch(error => {
                console.error('Error playing video:', error);
                this.showError('Failed to play video');
                // Restore placeholder if video fails
                placeholder.style.display = 'flex';
                videoPlayer.style.display = 'none';
            });

            // Add event listener to restore placeholder when video ends
            videoPlayer.addEventListener('ended', () => {
                placeholder.style.display = 'flex';
                videoPlayer.style.display = 'none';
                videoPlayer.currentTime = 0; // Reset video to beginning
            });

            // Add event listener to restore placeholder if user pauses (optional)
            videoPlayer.addEventListener('pause', () => {
                // Only restore if video has ended or is at the beginning
                if (videoPlayer.currentTime === 0 || videoPlayer.ended) {
                    placeholder.style.display = 'flex';
                    videoPlayer.style.display = 'none';
                }
            });

            console.log('Inline video playback started for clip:', clipNumber);
            
            // Load thumbnail after element creation if not already loaded
            this.loadVideoThumbnail(clipId);
        },

        loadVideoThumbnail(clipId) {
            // Check if thumbnail is already loaded
            const thumbnailImg = document.getElementById(`thumbnail-${clipId}`);
            if (!thumbnailImg) {
                return;
            }
            
            if (thumbnailImg.src && thumbnailImg.src !== window.location.href) {
                return;
            }

            // Try to get thumbnail from server
            const thumbnailUrl = `/api/thumbnail/${clipId}`;
            
            // Test if thumbnail exists using fetch first
            fetch(thumbnailUrl, { method: 'HEAD' })
                .then(response => {
                    if (response.ok) {
                        // Load the actual thumbnail
                        const img = new Image();
                        img.onload = () => {
                            thumbnailImg.src = thumbnailUrl;
                            thumbnailImg.style.display = 'block';
                            
                            // Update placeholder background to show thumbnail
                            const placeholder = document.getElementById(`placeholder-${clipId}`);
                            if (placeholder) {
                                placeholder.style.background = 'none';
                            }
                        };
                        
                        img.onerror = () => {
                            // Thumbnail failed to load - no fallback
                        };
                        
                        img.src = thumbnailUrl;
                    }
                })
                .catch(error => {
                    // Network error - no fallback
                });
        },

        // Test function to create mock clips with thumbnails
        createTestClips() {
            console.log('� Creating fallback thumbnail for:', clipId);
            
            const thumbnailImg = document.getElementById(`thumbnail-${clipId}`);
            if (!thumbnailImg) return;
            
            // Create a canvas-based thumbnail
            const canvas = document.createElement('canvas');
            canvas.width = 320;
            canvas.height = 240;
            const ctx = canvas.getContext('2d');
            
            // Create gradient background
            const gradient = ctx.createLinearGradient(0, 0, 320, 240);
            gradient.addColorStop(0, '#667eea');
            gradient.addColorStop(1, '#764ba2');
            ctx.fillStyle = gradient;
            ctx.fillRect(0, 0, 320, 240);
            
            // Add video icon
            ctx.fillStyle = 'white';
            ctx.font = 'bold 40px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('🎬', 160, 120);
            
            // Add text
            ctx.font = 'bold 16px Arial';
            ctx.fillText('Video Clip', 160, 160);
            ctx.font = '12px Arial';
            ctx.fillText(clipId, 160, 180);
            
            thumbnailImg.src = canvas.toDataURL();
            thumbnailImg.style.display = 'block';
            
            // Update placeholder background
            const placeholder = document.getElementById(`placeholder-${clipId}`);
            if (placeholder) {
                placeholder.style.background = 'none';
            }
            
            console.log('✅ Fallback thumbnail created for:', clipId);
        },

        // Test function to create mock clips with thumbnails
        createTestClips() {
            console.log('🧪 Creating test clips for thumbnail demonstration');
            
            const mockClips = [
                {
                    clip_id: 'test-clip-1',
                    title: 'Test Video Clip 1',
                    description: 'This is a test clip to demonstrate thumbnail functionality',
                    selection_reason: 'Selected for testing thumbnail feature',
                    start_time: 10,
                    end_time: 25,
                    has_file: true,
                    filename: 'test_clip_1.mp4',
                    file_size: 1024000,
                    clip_number: 1
                },
                {
                    clip_id: 'test-clip-2', 
                    title: 'Test Video Clip 2',
                    description: 'Another test clip with mock thumbnail',
                    selection_reason: 'Testing grid layout with thumbnails',
                    start_time: 45,
                    end_time: 60,
                    has_file: true,
                    filename: 'test_clip_2.mp4',
                    file_size: 2048000,
                    clip_number: 2
                },
                {
                    clip_id: 'test-clip-3',
                    title: 'Test Video Clip 3', 
                    description: 'Third test clip for thumbnail grid',
                    selection_reason: 'Completing the test set',
                    start_time: 80,
                    end_time: 95,
                    has_file: true,
                    filename: 'test_clip_3.mp4',
                    file_size: 1536000,
                    clip_number: 3
                }
            ];

            // Display the mock clips
            this.displayShortsClips(mockClips);
            
            // Show the clips section
            const clipsSection = document.getElementById('shorts-clips-section');
            if (clipsSection) {
                clipsSection.style.display = 'block';
            }
            
            // Create thumbnails immediately (no delay)
            mockClips.forEach(clip => {
                this.loadMockThumbnail(clip.clip_id);
            });
        },

        // Load mock thumbnails using placeholder images
        loadMockThumbnail(clipId) {
            console.log('🖼️ Loading mock thumbnail for:', clipId);
            
            const thumbnailImg = document.getElementById(`thumbnail-${clipId}`);
            if (!thumbnailImg) {
                console.log('❌ Thumbnail element not found for:', clipId);
                return;
            }

            // Create a simple colored canvas as thumbnail immediately
            const canvas = document.createElement('canvas');
            canvas.width = 320;
            canvas.height = 240;
            const ctx = canvas.getContext('2d');
            
            // Create gradient background based on clip ID
            const gradient = ctx.createLinearGradient(0, 0, 320, 240);
            if (clipId.includes('1')) {
                gradient.addColorStop(0, '#ff6b6b');
                gradient.addColorStop(1, '#ffa500');
            } else if (clipId.includes('2')) {
                gradient.addColorStop(0, '#4ecdc4');
                gradient.addColorStop(1, '#45b7d1');
            } else {
                gradient.addColorStop(0, '#9b59b6');
                gradient.addColorStop(1, '#e74c3c');
            }
            
            ctx.fillStyle = gradient;
            ctx.fillRect(0, 0, 320, 240);
            
            // Add thumbnail text
            ctx.fillStyle = 'white';
            ctx.font = 'bold 24px Arial';
            ctx.textAlign = 'center';
            ctx.strokeStyle = 'black';
            ctx.lineWidth = 2;
            
            // Add shadow effect
            ctx.strokeText('THUMBNAIL', 160, 100);
            ctx.fillText('THUMBNAIL', 160, 100);
            
            ctx.font = 'bold 18px Arial';
            ctx.strokeText(clipId.toUpperCase(), 160, 140);
            ctx.fillText(clipId.toUpperCase(), 160, 140);
            
            // Add play icon
            ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
            ctx.beginPath();
            ctx.arc(160, 180, 20, 0, 2 * Math.PI);
            ctx.fill();
            
            ctx.fillStyle = 'black';
            ctx.beginPath();
            ctx.moveTo(150, 170);
            ctx.lineTo(150, 190);
            ctx.lineTo(170, 180);
            ctx.closePath();
            ctx.fill();
            
            // Set the thumbnail
            thumbnailImg.src = canvas.toDataURL();
            thumbnailImg.style.display = 'block';
            console.log('✅ Canvas thumbnail created for:', clipId);
            
            // Update placeholder background
            const placeholder = document.getElementById(`placeholder-${clipId}`);
            if (placeholder) {
                placeholder.style.background = 'none';
                console.log('🎨 Updated placeholder background for:', clipId);
            }
        },

        // Enhanced playInlineVideo to also handle thumbnail loading
        playInlineVideo(clipId, clipNumber) {
            console.log('playInlineVideo called with clipId:', clipId, 'clipNumber:', clipNumber);
            if (!clipId) {
                console.error('No clipId provided to playInlineVideo');
                this.showError('Video clip ID not available');
                return;
            }

            // Find the video elements
            const placeholder = document.getElementById(`placeholder-${clipId}`);
            const videoPlayer = document.getElementById(`video-${clipId}`);
            
            if (!placeholder || !videoPlayer) {
                console.error('Video elements not found for clipId:', clipId);
                this.showError('Video player not found');
                return;
            }

            // Set the video source
            const videoSource = videoPlayer.querySelector('source');
            if (videoSource) {
                videoSource.src = `/api/stream-clip/${clipId}`;
            }

            // Hide placeholder and show video
            placeholder.style.display = 'none';
            videoPlayer.style.display = 'block';
            
            // Start playing the video
            videoPlayer.load();
            videoPlayer.play().catch(error => {
                console.error('Error playing video:', error);
                this.showError('Failed to play video');
                // Restore placeholder if video fails
                placeholder.style.display = 'flex';
                videoPlayer.style.display = 'none';
            });

            // Add event listener to restore placeholder when video ends
            videoPlayer.addEventListener('ended', () => {
                placeholder.style.display = 'flex';
                videoPlayer.style.display = 'none';
                videoPlayer.currentTime = 0; // Reset video to beginning
            });

            // Add event listener to restore placeholder if user pauses (optional)
            videoPlayer.addEventListener('pause', () => {
                // Only restore if video has ended or is at the beginning
                if (videoPlayer.currentTime === 0 || videoPlayer.ended) {
                    placeholder.style.display = 'flex';
                    videoPlayer.style.display = 'none';
                }
            });

            console.log('Inline video playback started for clip:', clipNumber);
        },

        playVideoClip(clipId) {
            console.log('playVideoClip called with clipId:', clipId); // Debug
            if (!clipId) {
                console.error('No clipId provided to playVideoClip'); // Debug
                this.showError('Video clip ID not available');
                return;
            }
            
            // Create a modal to play the video
            const modal = document.createElement('div');
            modal.className = 'modal fade';
            modal.innerHTML = `
                <div class="modal-dialog modal-sm modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header border-0 pb-0">
                            <h5 class="modal-title">
                                <i class="fas fa-play-circle text-primary me-2"></i>
                                Vertical Video Clip
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body text-center p-3">
                            <video controls autoplay style="width: 100%; border-radius: 8px;">
                                <source src="/api/stream-clip/${clipId}" type="video/mp4">
                                Your browser does not support the video tag.
                            </video>
                            <div class="mt-3">
                                <a href="/api/download-clip/${clipId}" class="btn btn-success btn-sm" download>
                                    <i class="fas fa-download me-1"></i>
                                    Download Video
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            const modalInstance = new bootstrap.Modal(modal);
            modalInstance.show();
            
            // Clean up modal when closed
            modal.addEventListener('hidden.bs.modal', () => {
                document.body.removeChild(modal);
            });
        },

        downloadVideoClip(clipId) {
            console.log('downloadVideoClip called with clipId:', clipId); // Debug
            if (!clipId) {
                console.error('No clipId provided to downloadVideoClip'); // Debug
                this.showError('Video clip ID not available');
                return;
            }
            
            try {
                // Create a temporary link to trigger download
                const downloadLink = document.createElement('a');
                downloadLink.href = `/api/download-clip/${clipId}`;
                downloadLink.download = '';
                downloadLink.style.display = 'none';
                
                document.body.appendChild(downloadLink);
                downloadLink.click();
                document.body.removeChild(downloadLink);
                
                this.showInfo('Video download started! Check your downloads folder.');
                
            } catch (error) {
                this.showError('Failed to start download');
            }
        },

        viewOnYoutube(clipNumber) {
            try {
                if (!this.currentShortsClips || !this.currentShortsClips[clipNumber - 1]) {
                    this.showError('Clip data not available');
                    return;
                }

                const clip = this.currentShortsClips[clipNumber - 1];
                const videoUrl = clip.video_url;
                const startTime = Math.floor(clip.start_time);
                
                if (videoUrl) {
                    const youtubeUrl = `${videoUrl}&t=${startTime}s`;
                    window.open(youtubeUrl, '_blank');
                } else {
                    this.showError('Video URL not available');
                }
            } catch (error) {
                this.showError('Failed to open YouTube link');
            }
        },

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
        },

        showNewClip(newClip, partialResult) {
            console.log('🎬 Showing new clip:', newClip);
            console.log('🔍 DEBUG: Partial result details:', partialResult);
            this.addDebugMessage(`🎬 showNewClip called for: ${newClip.title}`);
            
            // Initialize shorts display if not already done
            if (!document.getElementById('shorts-clips-container')) {
                console.log('🔍 DEBUG: Initializing shorts display for first clip');
                this.addDebugMessage('🎬 Initializing shorts display');
                this.initializeShortsDisplay();
                
                // Also show video info section if this is the first clip
                if (partialResult.total_ready === 1) {
                    console.log('🔍 DEBUG: This is the first clip, ensuring video info is visible');
                    const shortsSection = document.getElementById('shorts-clips-section');
                    if (shortsSection) {
                        shortsSection.classList.remove('hidden');
                        shortsSection.style.display = 'block';
                        this.addDebugMessage('📺 Shorts section shown');
                    } else {
                        this.addDebugMessage('❌ Shorts section not found');
                    }
                }
            } else {
                this.addDebugMessage('📺 Shorts display already initialized');
            }
            
            const container = document.getElementById('shorts-clips-container');
            if (!container) {
                console.error('❌ Shorts clips container not found after initialization');
                this.addDebugMessage('❌ Container not found after init');
                return;
            } else {
                console.log('✅ DEBUG: Container found:', container);
                console.log('✅ DEBUG: Container classList:', container.className);
                console.log('✅ DEBUG: Container parent:', container.parentElement);
                console.log('✅ DEBUG: Container visible:', window.getComputedStyle(container).display);
                this.addDebugMessage(`✅ Container found (display: ${window.getComputedStyle(container).display})`);
                
                // CRITICAL FIX: Force the shorts-clips-section to be visible
                const shortsSection = document.getElementById('shorts-clips-section');
                if (shortsSection) {
                    shortsSection.classList.remove('hidden');
                    shortsSection.style.cssText = 'display: block !important; visibility: visible !important; opacity: 1 !important;';
                    console.log('🔧 DEBUG: Forced shorts section visible');
                    console.log('🔧 DEBUG: Shorts section classes:', shortsSection.className);
                    console.log('🔧 DEBUG: Shorts section display:', window.getComputedStyle(shortsSection).display);
                    this.addDebugMessage('🔧 Forced shorts section visible');
                }
                
                // Ensure container has correct view mode class
                this.currentViewMode = this.currentViewMode || 'grid'; // Default to grid
                if (this.currentViewMode === 'grid') {
                    container.classList.add('video-clips-grid');
                    container.setAttribute('style', 'display: grid !important;');
                    console.log('🔧 DEBUG: Added video-clips-grid class to container during processing');
                    this.addDebugMessage('✅ Grid layout enforced during processing');
                } else {
                    container.classList.remove('video-clips-grid');
                    console.log('🔧 DEBUG: Removed video-clips-grid class from container during processing');
                }
                
                // Clear placeholder content on first clip
                if (container.children.length > 0 && !container.querySelector('[data-clip-id]')) {
                    console.log('🧹 DEBUG: Clearing placeholder content');
                    this.addDebugMessage('🧹 Clearing placeholder');
                    container.innerHTML = '';
                }
            }
            
            // Check if this clip already exists (avoid duplicates)
            const existingClip = container.querySelector(`[data-clip-id="${newClip.clip_id}"]`);
            if (existingClip) {
                console.log(`🔍 DEBUG: Clip ${newClip.clip_number} already exists, skipping`);
                this.addDebugMessage(`⚠️ Clip ${newClip.clip_number} already exists`);
                return;
            }
            
            // Create and add the new clip element
            console.log(`🔍 DEBUG: Creating element for clip ${newClip.clip_number}`);
            this.addDebugMessage(`🎬 Creating element for clip ${newClip.clip_number}`);
            
            try {
                const clipElement = this.createClipElement(newClip);
                clipElement.setAttribute('data-clip-id', newClip.clip_id);
                
                console.log(`🔍 DEBUG: Clip element created:`, clipElement);
                console.log(`🔍 DEBUG: Clip element className:`, clipElement.className);
                console.log(`🔍 DEBUG: Clip element innerHTML length:`, clipElement.innerHTML.length);
                console.log(`🔍 DEBUG: Container before append - children:`, container.children.length);
                
                container.appendChild(clipElement);
                
                console.log(`🔍 DEBUG: Container after append - children:`, container.children.length);
                console.log(`🔍 DEBUG: Clip ${newClip.clip_number} added to container`);
                this.addDebugMessage(`✅ Clip ${newClip.clip_number} added to UI`);
                
                // Force a reflow to ensure the element is rendered
                clipElement.offsetHeight;
                
                // Log the actual DOM state
                console.log(`🔍 DEBUG: Clip element offsetHeight:`, clipElement.offsetHeight);
                console.log(`🔍 DEBUG: Clip element display:`, window.getComputedStyle(clipElement).display);
                console.log(`🔍 DEBUG: Clip element visibility:`, window.getComputedStyle(clipElement).visibility);
                
                // Check parent chain visibility
                const shortsSection = document.getElementById('shorts-clips-section');
                const parentCard = shortsSection?.parentElement;
                console.log(`🔍 DEBUG: Shorts section display:`, shortsSection ? window.getComputedStyle(shortsSection).display : 'not found');
                console.log(`🔍 DEBUG: Shorts section visibility:`, shortsSection ? window.getComputedStyle(shortsSection).visibility : 'not found');
                console.log(`🔍 DEBUG: Shorts section offsetHeight:`, shortsSection?.offsetHeight);
                console.log(`🔍 DEBUG: Parent card display:`, parentCard ? window.getComputedStyle(parentCard).display : 'not found');
                console.log(`🔍 DEBUG: Parent card className:`, parentCard?.className);
                console.log(`🔍 DEBUG: Container display:`, window.getComputedStyle(container).display);
                console.log(`🔍 DEBUG: Container visibility:`, window.getComputedStyle(container).visibility);
                console.log(`🔍 DEBUG: Container offsetHeight:`, container.offsetHeight);
                this.addDebugMessage(`🔍 Clip height: ${clipElement.offsetHeight}px, Container height: ${container.offsetHeight}px`);
                
                // Update progress info
                this.updateShortsProgress(partialResult.total_ready, partialResult.total_clips);
                
                // Scroll to the new clip
                clipElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                console.log(`🔍 DEBUG: Scrolled to clip ${newClip.clip_number}`);
                this.addDebugMessage(`📜 Scrolled to clip ${newClip.clip_number}`);
                
            } catch (error) {
                console.error('❌ Error creating clip element:', error);
                this.addDebugMessage(`❌ Error creating clip: ${error.message}`);
            }
        },

        initializeShortsDisplay() {
            console.log('🎬 Initializing shorts display');
            this.addDebugMessage('🎬 initializeShortsDisplay called');
            
            // Set default view mode to grid immediately
            this.currentViewMode = 'grid';
            
            // Use the existing shorts-clips-section instead of results-section
            const shortsClipsSection = document.getElementById('shorts-clips-section');
            if (shortsClipsSection) {
                this.addDebugMessage('📺 Found shorts-clips-section');
                
                // Make the section visible - use !important in style
                shortsClipsSection.classList.remove('hidden');
                shortsClipsSection.setAttribute('style', 'display: block !important; visibility: visible !important; opacity: 1 !important;');
                
                console.log('📺 DEBUG: Removed hidden class');
                console.log('📺 DEBUG: Current classes:', shortsClipsSection.className);
                console.log('📺 DEBUG: Computed display:', window.getComputedStyle(shortsClipsSection).display);
                
                // Also check parent visibility
                const parentCard = shortsClipsSection.closest('.card');
                if (parentCard) {
                    parentCard.setAttribute('style', 'display: block !important; visibility: visible !important;');
                    console.log('📺 DEBUG: Made parent card visible');
                }
                
                this.addDebugMessage('📺 Made shorts-clips-section visible');
                
                // Find the existing container in the HTML structure
                let container = document.getElementById('shorts-clips-container');
                if (container) {
                    this.addDebugMessage('📺 Found existing container, setting up grid layout');
                    // Clear the placeholder content but keep the container
                    container.innerHTML = '';
                    // IMPORTANT: Apply grid class immediately!
                    container.className = 'video-clips-grid';
                    container.setAttribute('style', 'display: grid !important;');
                    console.log('📺 DEBUG: Applied grid layout immediately');
                    console.log('📺 DEBUG: Container className:', container.className);
                    this.addDebugMessage('✅ Grid layout applied immediately');
                } else {
                    this.addDebugMessage('❌ Container not found, this should not happen');
                }
                
                // Update the clips count badge
                const countBadge = document.getElementById('clips-count-badge');
                if (countBadge) {
                    const countText = document.getElementById('clips-count-text');
                    if (countText) {
                        countText.textContent = '0 clips';
                    }
                    this.addDebugMessage('� Reset clips count badge');
                }
                
                this.addDebugMessage('📺 Shorts section ready');
            } else {
                this.addDebugMessage('❌ shorts-clips-section not found!');
            }
        },

        createClipElement(clip) {
            console.log('🎨 DEBUG: createClipElement called with:', clip);
            
            const clipNumber = clip.clip_number;
            const hasFile = clip.has_video_file && clip.video_ready;
            const fileSize = hasFile ? this.formatFileSize(clip.file_size) : 'Processing...';
            const startTime = clip.start_time;
            const endTime = clip.end_time;

            // Check current view mode and create appropriate element
            const isGridView = this.currentViewMode === 'grid';
            console.log('🎨 DEBUG: Current view mode:', this.currentViewMode, 'isGridView:', isGridView);
            
            if (isGridView) {
                // Create grid view element (YouTube-style card)
                const clipId = clip.clip_id || '';
                const colDiv = document.createElement('div');
                colDiv.className = 'video-clip-card';
                
                console.log('🎨 DEBUG: Creating GRID element with className:', colDiv.className);
                
                colDiv.innerHTML = `
                    <div class="video-container" data-clip-id="${clipId}">
                        <div class="video-placeholder" id="placeholder-${clipId}">
                            <!-- Video thumbnail image (will be loaded dynamically) -->
                            <img class="video-thumbnail-image" id="thumbnail-${clipId}" src="" alt="Video thumbnail" style="display: none;" loading="lazy">
                            
                            <!-- Video overlay for better contrast -->
                            <div class="video-overlay"></div>
                            
                            <!-- Status badge -->
                            <div class="video-status-badge ${hasFile ? 'ready' : 'processing'}">
                                ${hasFile ? '▶' : '⚡'}
                            </div>
                            
                            <!-- Video number -->
                            <div class="video-number">${clipNumber}</div>
                            
                            <!-- Play button in center -->
                            <div class="video-play-button" onclick="youtubeApp.playInlineVideo('${clipId}', ${clipNumber})">
                                <i class="fas fa-play"></i>
                            </div>
                        </div>
                        <video class="inline-video-player" id="video-${clipId}" style="display: none;" controls>
                            <source src="" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                    </div>
                    <div class="video-clip-info">
                        <h6 class="video-title">${this.escapeHtml(clip.title)}</h6>
                        <p class="video-description">${this.escapeHtml(clip.description)}</p>
                        <div class="video-meta">
                            <small class="text-muted">
                                <i class="fas fa-clock me-1"></i>
                                ${this.formatTime(startTime)} - ${this.formatTime(endTime)}
                            </small>
                        </div>
                        <div class="video-actions mt-2">
                            ${hasFile ? `
                                <button class="btn btn-success btn-sm" onclick="youtubeApp.playInlineVideo('${clipId}', ${clipNumber})">
                                    <i class="fas fa-play me-1"></i>Play
                                </button>
                                <button class="btn btn-outline-success btn-sm" onclick="youtubeApp.downloadVideoClip('${clipId}')">
                                    <i class="fas fa-download me-1"></i>Download
                                </button>
                            ` : `
                                <button class="btn btn-outline-secondary btn-sm" disabled>
                                    <i class="fas fa-spinner fa-spin me-1"></i>
                                    Processing...
                                </button>
                            `}
                        </div>
                    </div>
                `;
                
                // Load thumbnail after creating the element
                setTimeout(() => {
                    if (clip.clip_id) {
                        this.loadVideoThumbnail(clip.clip_id);
                    }
                }, 100);
                
                return colDiv;
            } else {
                // Create list view element (original layout)
                const colDiv = document.createElement('div');
                colDiv.className = 'col-12 mb-4';
                
                console.log('🎨 DEBUG: Creating LIST element with className:', colDiv.className);
                
                colDiv.innerHTML = `
                    <div class="card h-100 clip-item">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col-md-3">
                                    <div class="video-container">
                                        <div class="video-placeholder" id="placeholder-${clip.clip_id || ''}" style="aspect-ratio: 3/4; background: url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 300 400\"><rect width=\"300\" height=\"400\" fill=\"%23f8f9fa\"/><circle cx=\"150\" cy=\"200\" r=\"40\" fill=\"%23dee2e6\"/><polygon points=\"135,185 135,215 165,200\" fill=\"%23ffffff\"/></svg>'); display: flex; align-items: center; justify-content: center; border-radius: 8px; position: relative;">
                                            <!-- Video thumbnail image -->
                                            <img class="video-thumbnail-image" id="thumbnail-${clip.clip_id || ''}" src="" alt="Video thumbnail" style="display: none; width: 100%; height: 100%; object-fit: cover; border-radius: 8px;" loading="lazy">
                                            
                                            <!-- Video overlay -->
                                            <div class="video-overlay" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(180deg, rgba(0, 0, 0, 0.3) 0%, rgba(0, 0, 0, 0.1) 50%, rgba(0, 0, 0, 0.4) 100%); z-index: 2; border-radius: 8px;"></div>
                                            
                                            <!-- Status badge -->
                                            <div class="video-status-badge ${hasFile ? 'ready' : 'processing'}" style="position: absolute; top: 8px; left: 8px; width: 24px; height: 24px; border-radius: 50%; background: rgba(0, 0, 0, 0.7); display: flex; align-items: center; justify-content: center; font-size: 12px; color: white; z-index: 15;">
                                                ${hasFile ? '▶' : '⚡'}
                                            </div>
                                            
                                            <!-- Video number -->
                                            <div class="video-number" style="position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.8); color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; z-index: 15;">${clipNumber}</div>
                                            
                                            <!-- Play button -->
                                            <div class="video-play-button" onclick="youtubeApp.playInlineVideo('${clip.clip_id || ''}', ${clipNumber})" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 40px; height: 40px; background: rgba(0, 0, 0, 0.7); border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; z-index: 10;">
                                                <i class="fas fa-play" style="font-size: 16px; color: white; margin-left: 2px;"></i>
                                            </div>
                                        </div>
                                        <video class="inline-video-player" id="video-${clip.clip_id || ''}" style="display: none; width: 100%; aspect-ratio: 3/4; border-radius: 8px;" controls>
                                            <source src="" type="video/mp4">
                                            Your browser does not support the video tag.
                                        </video>
                                    </div>
                                </div>
                                <div class="col-md-9">
                                    <div class="clip-info">
                                        <h5 class="card-title mb-2">
                                            <span class="badge bg-gradient-primary me-2">${clipNumber}</span>
                                            ${this.escapeHtml(clip.title)}
                                        </h5>
                                        <p class="card-text text-muted mb-2">
                                            ${this.escapeHtml(clip.description)}
                                        </p>
                                        <div class="clip-reason mb-2">
                                            <small class="text-info">
                                                <i class="fas fa-lightbulb me-1"></i>
                                                <strong>Why selected:</strong> ${this.escapeHtml(clip.selection_reason)}
                                            </small>
                                        </div>
                                        <div class="clip-meta mb-2">
                                            <small class="text-muted">
                                                <i class="fas fa-clock me-1"></i>
                                                ${this.formatTime(startTime)} - ${this.formatTime(endTime)} |
                                                <i class="fas fa-${hasFile ? 'hdd' : 'info-circle'} me-1"></i>
                                                ${fileSize}
                                            </small>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="clip-actions mt-3">
                                ${hasFile ? `
                                    <div class="btn-group btn-group-sm">
                                        <button class="btn btn-success" onclick="youtubeApp.playInlineVideo('${clip.clip_id || ''}', ${clipNumber})">
                                            <i class="fas fa-play me-1"></i>
                                            Play
                                        </button>
                                        <button class="btn btn-outline-success" onclick="youtubeApp.downloadVideoClip('${clip.clip_id || ''}')">
                                            <i class="fas fa-download me-1"></i>
                                            Download
                                        </button>
                                    </div>
                                ` : `
                                    <div class="btn-group btn-group-sm">
                                        <button class="btn btn-outline-secondary" disabled>
                                            <i class="fas fa-spinner fa-spin me-1"></i>
                                            Processing...
                                        </button>
                                    </div>
                                `}
                            </div>
                        </div>
                    </div>
                `;
                
                return colDiv;
            }
            
            // Load thumbnail after creating the element
            setTimeout(() => {
                if (clip.clip_id) {
                    this.loadVideoThumbnail(clip.clip_id);
                }
            }, 100);
        },

        updateShortsProgress(ready, total) {
            // Update the existing clips count badge in the HTML
            const countText = document.getElementById('clips-count-text');
            const countBadge = document.getElementById('clips-count-badge');
            
            if (countText) {
                countText.textContent = `${ready}/${total} clips`;
                this.addDebugMessage(`📊 Updated count: ${ready}/${total} clips`);
            }
            
            if (countBadge && ready === total) {
                countBadge.className = 'badge bg-gradient-success';
                this.addDebugMessage('✅ All clips ready - badge updated to success');
            }
        },

        formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },

        addDebugMessage(message) {
            // Debug messages disabled - no UI debug panel
            // console.log('DEBUG:', message); // Uncomment for console debugging if needed
        },

        showCancelButton(taskId) {
            console.log('🚫 DEBUG: showCancelButton called for task:', taskId);
            
            // Use the existing cancel button in the template instead of creating a new one
            const existingCancelBtn = document.getElementById('cancel-btn');
            
            if (existingCancelBtn) {
                // Check if this button is already configured for streaming (video summarization)
                if (existingCancelBtn.getAttribute('data-cancel-type') === 'streaming') {
                    console.log('🚫 DEBUG: Button already configured for streaming, skipping video-processor handler');
                    return;
                }
                
                console.log('🚫 DEBUG: Found existing cancel button, attaching event listener...');
                
                // Remove any existing event listeners
                const newBtn = existingCancelBtn.cloneNode(true);
                existingCancelBtn.parentNode.replaceChild(newBtn, existingCancelBtn);
                
                // Mark this as a shorts generation cancel button
                newBtn.setAttribute('data-cancel-type', 'shorts');
                
                // Store reference to the cancel function globally for easier access
                window.currentCancelFunction = () => {
                    console.log('🚫 Cancel function called for task:', taskId);
                    if (window.youtubeApp && typeof window.youtubeApp.cancelShortsGeneration === 'function') {
                        console.log('🚫 Calling cancelShortsGeneration...');
                        window.youtubeApp.cancelShortsGeneration(taskId);
                    } else {
                        console.error('❌ YouTube app or cancelShortsGeneration method not found');
                        console.log('Available methods:', Object.keys(window.youtubeApp || {}));
                    }
                };
                
                // Attach event listener to the existing cancel button
                newBtn.addEventListener('click', () => {
                    console.log('🚫 SHORTS CANCEL BUTTON CLICKED! Calling cancel function...');
                    window.currentCancelFunction();
                });
                
                console.log('✅ Cancel functionality attached to existing button for task:', taskId);
                
            } else {
                console.error('❌ No cancel button found in DOM');
                console.log('Available buttons:', {
                    'cancel-btn': !!document.getElementById('cancel-btn'),
                    'status-container': !!document.getElementById('status-container'),
                    'loading-state': !!document.getElementById('loading-state')
                });
            }
        },

        hideCancelButton() {
            // Don't remove the existing cancel button since it's part of the template
            // Just clean up the global function reference
            if (window.currentCancelFunction) {
                delete window.currentCancelFunction;
            }
            console.log('🚫 DEBUG: Cancel functionality cleaned up (keeping button in DOM)');
        },

        async cancelShortsGeneration(taskId) {
            try {
                console.log('🚫 Cancelling task:', taskId);
                
                // Disable the existing cancel button to prevent double-clicks
                const cancelBtn = document.getElementById('cancel-btn');
                if (cancelBtn) {
                    cancelBtn.disabled = true;
                    const cancelText = cancelBtn.querySelector('span');
                    if (cancelText) {
                        cancelText.textContent = 'Cancelling...';
                    }
                    const icon = cancelBtn.querySelector('i');
                    if (icon) {
                        icon.className = 'fas fa-spinner fa-spin me-1';
                    }
                }
                
                console.log('📡 Sending cancel request to:', `/api/cancel/${taskId}`);
                
                const response = await fetch(`/api/cancel/${taskId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                
                console.log('📡 Cancel response status:', response.status);
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const result = await response.json();
                console.log('📡 Cancel response data:', result);
                
                if (result.success) {
                    this.taskCancelled = true;
                    if (this.currentEventSource) {
                        this.currentEventSource.close();
                        this.currentEventSource = null;
                    }
                    this.currentTaskId = null;
                    this.hideCancelButton();
                    
                    // Show success message using available UI methods
                    if (typeof this.showStatus === 'function') {
                        this.showStatus('Task cancelled successfully', 'info');
                    } else if (typeof this.showMessage === 'function') {
                        this.showMessage('Task cancelled successfully', 'success');
                    } else {
                        console.log('✅ Task cancelled successfully');
                        // Show a simple alert as fallback
                        const alert = document.createElement('div');
                        alert.className = 'alert alert-success alert-dismissible fade show';
                        alert.innerHTML = `
                            ✅ Task cancelled successfully
                            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                        `;
                        const container = document.querySelector('.container-fluid') || document.body;
                        container.insertBefore(alert, container.firstChild);
                        setTimeout(() => alert.remove(), 3000);
                    }
                    
                    this.hideStatus();
                    
                    // Re-enable the generate button
                    const generateBtn = document.getElementById('generate-shorts-btn');
                    if (generateBtn) {
                        generateBtn.disabled = false;
                    }
                } else {
                    throw new Error(result.error || 'Failed to cancel task');
                }
                
            } catch (error) {
                console.error('❌ Cancel error:', error);
                
                // Show error message using available UI methods
                if (typeof this.showError === 'function') {
                    this.showError(`Failed to cancel: ${error.message}`);
                } else {
                    console.error(`Failed to cancel: ${error.message}`);
                    // Show a simple alert as fallback
                    const alert = document.createElement('div');
                    alert.className = 'alert alert-danger alert-dismissible fade show';
                    alert.innerHTML = `
                        ❌ Failed to cancel: ${error.message}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    `;
                    const container = document.querySelector('.container-fluid') || document.body;
                    container.insertBefore(alert, container.firstChild);
                    setTimeout(() => alert.remove(), 5000);
                }
                
                // Re-enable cancel button on error
                const cancelBtn = document.getElementById('cancel-btn');
                if (cancelBtn) {
                    cancelBtn.disabled = false;
                    const cancelText = cancelBtn.querySelector('span');
                    if (cancelText) {
                        cancelText.textContent = 'Cancel';
                    }
                    const icon = cancelBtn.querySelector('i');
                    if (icon) {
                        icon.className = 'fas fa-times me-1';
                    }
                }
            }
        }
    };

    global.YouTubeTranscriptAppMixins = global.YouTubeTranscriptAppMixins || [];
    global.YouTubeTranscriptAppMixins.push(videoProcessorMixin);
})(window);
