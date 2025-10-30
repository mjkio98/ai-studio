/**
 * Chat Agent - URL Q&A Interface with Webscout AI
 * Handles webpage analysis and interactive chat with streaming responses
 */

class ChatAgent {
    constructor() {
        this.isAnalyzing = false;
        this.isResponding = false;
        this.currentRequest = null;
        this.pendingQuestion = null; // For handling mixed text+URL inputs
        
        // Load session history from localStorage first
        this.loadHistoryFromStorage();
        
        // Generate new sessionId only if we don't have one from localStorage
        if (!this.sessionId) {
            this.sessionId = this.generateSessionId();
        }
        
        this.initializeElements();
        this.bindEvents();
        
        console.log('🤖 Chat Agent initialized with sessionId:', this.sessionId);
    }
    
    generateSessionId() {
        return 'chat_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    // Load chat history from localStorage
    loadHistoryFromStorage() {
        try {
            const storedHistory = localStorage.getItem('chatAgent_analyzedUrls');
            if (storedHistory) {
                const historyData = JSON.parse(storedHistory);
                this.analyzedUrls = new Map(historyData.urls || []);
                this.currentPageUrl = historyData.currentPageUrl || null;
                this.isPageAnalyzed = historyData.isPageAnalyzed || false;
                
                // Restore sessionId for current page if available
                if (this.currentPageUrl && this.analyzedUrls.has(this.currentPageUrl)) {
                    const urlData = this.analyzedUrls.get(this.currentPageUrl);
                    this.sessionId = urlData.sessionId;
                    console.log('🔄 Restored sessionId from localStorage:', this.sessionId, 'for URL:', this.currentPageUrl);
                } else {
                    console.log('📝 No current page or sessionId to restore from localStorage');
                }
                
                console.log('📚 Loaded chat history from localStorage:', this.analyzedUrls.size, 'URLs');
            } else {
                this.analyzedUrls = new Map();
                this.currentPageUrl = null;
                this.isPageAnalyzed = false;
            }
        } catch (error) {
            console.error('Error loading chat history from localStorage:', error);
            this.analyzedUrls = new Map();
            this.currentPageUrl = null;
            this.isPageAnalyzed = false;
        }
    }
    
    // Save chat history to localStorage
    saveHistoryToStorage() {
        try {
            const historyData = {
                urls: Array.from(this.analyzedUrls.entries()),
                currentPageUrl: this.currentPageUrl,
                isPageAnalyzed: this.isPageAnalyzed,
                lastUpdated: Date.now()
            };
            localStorage.setItem('chatAgent_analyzedUrls', JSON.stringify(historyData));
            console.log('💾 Saved chat history to localStorage');
        } catch (error) {
            console.error('Error saving chat history to localStorage:', error);
        }
    }
    
    // Clear chat history from localStorage
    clearHistoryFromStorage() {
        try {
            localStorage.removeItem('chatAgent_analyzedUrls');
            this.analyzedUrls.clear();
            this.currentPageUrl = null;
            this.isPageAnalyzed = false;
            console.log('🗑️ Cleared chat history from localStorage');
        } catch (error) {
            console.error('Error clearing chat history from localStorage:', error);
        }
    }
    
    // Clear current page context and start fresh session
    async clearPageContext() {
        try {
            // First, clear the old session on the backend if it exists
            if (this.sessionId) {
                try {
                    console.log('🗑️ Clearing old session on backend:', this.sessionId);
                    await fetch(`/api/chat-agent/clear?session_id=${this.sessionId}`, {
                        method: 'POST'
                    });
                } catch (error) {
                    console.warn('Warning: Failed to clear old session on backend:', error);
                }
            }
            
            // Generate new session ID for fresh conversation
            this.sessionId = this.generateSessionId();
            console.log('🆕 Generated new sessionId for fresh conversation:', this.sessionId);
            
            // Clear current page context
            this.currentPageUrl = null;
            this.isPageAnalyzed = false;
            
            // Save updated state to localStorage
            this.saveHistoryToStorage();
            
            // Optionally clear the chat messages for a completely fresh start
            // Uncomment the line below if you want to clear chat history on fresh start
            // this.chatMessages.innerHTML = '';
            
            console.log('🔄 Cleared page context, starting fresh conversation');
        } catch (error) {
            console.error('Error clearing page context:', error);
        }
    }
    
    initializeElements() {
        // Main containers
        this.chatSection = document.getElementById('chat-agent-section');
        this.chatInterface = this.chatSection; // In new layout, no separate interface
        this.chatMessages = document.getElementById('chat-messages');
        this.pageInfo = null; // Not used in new layout
        this.statusContainer = null; // Not used in new layout
        
        // Input elements - no URL input in new layout, chat input handles everything
        this.urlInput = null; // Removed in new layout
        this.chatInput = document.getElementById('chat-input');
        
        // Buttons
        this.analyzeBtn = null; // No separate analyze button
        this.summarizeBtn = document.getElementById('summarize-page-btn');
        this.sendBtn = document.getElementById('send-message-btn');
        this.stopBtn = document.getElementById('stop-message-btn');
        this.cancelBtn = null; // Not used
        this.clearChatBtn = document.getElementById('clear-chat-btn');
        
        // Status elements
        this.statusText = null; // Not used in new layout
        this.statusDetails = null;
        this.charCount = document.getElementById('char-count');
        
        // Page info elements - not used in new layout
        this.pageTitle = null;
        this.pageUrl = null;
        this.pageLength = null;
        
        // State tracking
        this.currentPageUrl = null;
        this.isPageAnalyzed = false;
    }
    
    bindEvents() {
        // Chat input events - handles both URL and chat messages
        this.chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleInput();
            }
        });
        
        this.chatInput.addEventListener('input', () => {
            this.updateCharacterCount();
            this.updateSendButton();
        });
        
        // Button events
        if (this.summarizeBtn) {
            this.summarizeBtn.addEventListener('click', () => this.summarizePage());
        }
        
        this.sendBtn.addEventListener('click', () => this.handleInput());
        
        if (this.stopBtn) {
            this.stopBtn.addEventListener('click', () => this.stopResponse());
        }
        
        if (this.clearChatBtn) {
            this.clearChatBtn.addEventListener('click', () => this.clearChat());
        }
    }
    
    updateCharacterCount() {
        const count = this.chatInput.value.length;
        if (this.charCount) {
            this.charCount.textContent = count;
            
            // Update styling based on character count
            const parent = this.charCount.parentElement;
            if (parent) {
                if (count > 450) {
                    parent.className = 'character-count mt-1 text-danger';
                } else if (count > 400) {
                    parent.className = 'character-count mt-1 text-warning';
                } else {
                    parent.className = 'character-count mt-1 text-muted';
                }
            }
        }
    }
    
    updateSendButton() {
        const hasText = this.chatInput.value.trim().length > 0;
        this.sendBtn.disabled = !hasText || this.isResponding;
        
        // Show/hide stop button based on response state
        if (this.stopBtn) {
            if (this.isResponding || this.isAnalyzing) {
                this.stopBtn.classList.remove('hidden');
            } else {
                this.stopBtn.classList.add('hidden');
            }
        }
    }
    
    // New method to handle both URL analysis and chat messages
    handleInput() {
        const input = this.chatInput.value.trim();
        
        if (!input) {
            return;
        }
        
        // First check if the entire input is a URL (pure URL input)
        if (this.isURL(input)) {
            // Check if this URL was previously analyzed
            if (this.analyzedUrls.has(input)) {
                // Switch to previously analyzed URL
                this.switchToAnalyzedUrl(input);
            } else {
                // Analyze new URL
                this.analyzeUrl(input);
            }
        } else {
            // Check if the message contains a URL within text
            const extractedData = this.extractURLFromMessage(input);
            
            if (extractedData.hasUrl) {
                // Message contains both text and URL - analyze the webpage with the user's question
                console.log('📄 Mixed message detected:', extractedData.text, 'URL:', extractedData.url);
                
                // Clear input immediately to prevent double processing
                this.chatInput.value = '';
                this.updateCharacterCount();
                
                // Check if this URL was previously analyzed
                if (this.analyzedUrls.has(extractedData.url)) {
                    const urlData = this.analyzedUrls.get(extractedData.url);
                    
                    // For mixed messages with URLs, validate session and handle accordingly
                    fetch(`/api/chat-agent/validate-session?session_id=${urlData.sessionId}`)
                        .then(response => {
                            if (response.ok) {
                                // Session is valid, use existing analysis
                                this.currentPageUrl = extractedData.url;
                                this.sessionId = urlData.sessionId;
                                this.isPageAnalyzed = true;
                                
                                console.log('📄 Using existing analysis for:', extractedData.url, 'sessionId:', this.sessionId);
                                
                                // Add user message with just the question
                                this.addUserMessage(extractedData.text || 'Tell me about this webpage');
                                
                                // Send the question directly to backend
                                this.sendQuestionToBackend(extractedData.text || 'Tell me about this webpage');
                            } else {
                                // Session is invalid, analyze fresh
                                console.log('⚠️ Session invalid for:', extractedData.url, 'analyzing fresh');
                                this.analyzedUrls.delete(extractedData.url);
                                this.saveHistoryToStorage();
                                
                                // Analyze as new URL
                                this.pendingQuestion = extractedData.text || 'Tell me about this webpage';
                                this.analyzeUrl(extractedData.url);
                            }
                        })
                        .catch(error => {
                            console.log('⚠️ Session validation failed for:', extractedData.url, 'analyzing fresh');
                            this.analyzedUrls.delete(extractedData.url);
                            this.saveHistoryToStorage();
                            
                            // Analyze as new URL
                            this.pendingQuestion = extractedData.text || 'Tell me about this webpage';
                            this.analyzeUrl(extractedData.url);
                        });
                } else {
                    // Store the user's question for after analysis
                    this.pendingQuestion = extractedData.text || 'Tell me about this webpage';
                    // Analyze new URL
                    this.analyzeUrl(extractedData.url);
                }
                
                // Return early to prevent normal sendMessage flow
                return;
            } else {
                // Send as general chat message (no URL analysis required)
                this.sendMessage();
            }
        }
    }
    
    // Switch to a previously analyzed URL
    switchToAnalyzedUrl(url) {
        const urlData = this.analyzedUrls.get(url);
        if (urlData) {
            console.log('🔄 Re-analyzing previously analyzed URL:', url);
            
            // Clear input
            this.chatInput.value = '';
            this.updateCharacterCount();
            
            // Add system message indicating this is a re-analysis
            this.addSystemMessage(`🔄 ${this.getLocalizedMessage('re_analyzing')} ${urlData.title || 'Webpage'} (${this.getLocalizedMessage('previously_analyzed')} ${this.formatTimestamp(urlData.timestamp)})`);
            
            // Re-analyze the URL with current sessionId to ensure server session exists
            // Note: analyzeUrl will handle adding the user message
            this.analyzeUrl(url);
        }
    }
    
    // Helper method to format timestamp
    formatTimestamp(timestamp) {
        const now = Date.now();
        const diff = now - timestamp;
        
        if (diff < 60000) { // Less than 1 minute
            return 'just now';
        } else if (diff < 3600000) { // Less than 1 hour
            const minutes = Math.floor(diff / 60000);
            return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
        } else if (diff < 86400000) { // Less than 1 day
            const hours = Math.floor(diff / 3600000);
            return `${hours} hour${hours > 1 ? 's' : ''} ago`;
        } else {
            const days = Math.floor(diff / 86400000);
            return `${days} day${days > 1 ? 's' : ''} ago`;
        }
    }
    
    // Convert basic markdown to HTML - Fixed to prevent content being wrapped in single header
    convertMarkdownToHtml(text) {
        if (!text) return '';
        
        // Split text into lines for proper processing
        const lines = text.split('\n');
        const processedLines = [];
        
        for (let i = 0; i < lines.length; i++) {
            let line = lines[i];
            const trimmedLine = line.trim();
            
            // Skip empty lines for now
            if (!trimmedLine) {
                processedLines.push('');
                continue;
            }
            
            // Headers (h1-h6) - handle first to prevent content being wrapped in headers
            if (trimmedLine.startsWith('### ')) {
                processedLines.push(`<h3>${this.formatInlineMarkdown(trimmedLine.substring(4))}</h3>`);
            } else if (trimmedLine.startsWith('## ')) {
                processedLines.push(`<h2>${this.formatInlineMarkdown(trimmedLine.substring(3))}</h2>`);
            } else if (trimmedLine.startsWith('# ')) {
                processedLines.push(`<h1>${this.formatInlineMarkdown(trimmedLine.substring(2))}</h1>`);
            } else if (trimmedLine.startsWith('#### ')) {
                processedLines.push(`<h4>${this.formatInlineMarkdown(trimmedLine.substring(5))}</h4>`);
            } else if (trimmedLine.startsWith('##### ')) {
                processedLines.push(`<h5>${this.formatInlineMarkdown(trimmedLine.substring(6))}</h5>`);
            } else if (trimmedLine.startsWith('###### ')) {
                processedLines.push(`<h6>${this.formatInlineMarkdown(trimmedLine.substring(7))}</h6>`);
            }
            // List items
            else if (trimmedLine.match(/^[\-\*\+\•]\s/)) {
                let content = this.formatInlineMarkdown(trimmedLine.substring(2));
                // Remove redundant periods at the end of list items unless they end a sentence
                content = content.replace(/\.$/, '');
                processedLines.push(`<li>${content}</li>`);
            } else if (trimmedLine.match(/^\d+\.\s/)) {
                const match = trimmedLine.match(/^\d+\.\s(.*)$/);
                let content = this.formatInlineMarkdown(match[1]);
                // Remove redundant periods at the end of numbered list items unless they end a sentence
                content = content.replace(/\.$/, '');
                processedLines.push(`<li class="numbered">${content}</li>`);
            }
            // Regular paragraphs
            else {
                let content = this.formatInlineMarkdown(trimmedLine);
                processedLines.push(`<p>${content}</p>`);
            }
        }
        
        // Join processed lines
        let formatted = processedLines.join('\n');
        
        // Handle lists properly
        if (formatted.includes('<li>')) {
            // Regular bullet lists
            formatted = formatted.replace(/(<li>(?!class="numbered").*?<\/li>(\s*\n\s*<li>(?!class="numbered").*?<\/li>)*)/gs, '<ul>$1</ul>');
            // Numbered lists
            formatted = formatted.replace(/(<li class="numbered">.*?<\/li>(\s*\n\s*<li class="numbered">.*?<\/li>)*)/gs, '<ol>$1</ol>');
            // Clean up class attributes
            formatted = formatted.replace(/class="numbered"/g, '');
        }
        
        // Clean up extra newlines and empty paragraphs
        formatted = formatted.replace(/\n+/g, '\n');
        formatted = formatted.replace(/<p><\/p>/g, '');
        formatted = formatted.replace(/<p>\s*<\/p>/g, '');
        
        // Improve spacing consistency to match single video format
        formatted = formatted.replace(/(<\/h[1-6]>)\n*(<p>)/g, '$1\n$2');
        formatted = formatted.replace(/(<\/ul>)\n*(<p>)/g, '$1\n$2');
        formatted = formatted.replace(/(<\/ol>)\n*(<p>)/g, '$1\n$2');
        formatted = formatted.replace(/(<\/p>)\n*(<h[1-6]>)/g, '$1\n$2');
        
        return formatted;
    }

    // Helper function to format inline markdown (bold, italic, code)
    formatInlineMarkdown(text) {
        return text
            // Bold
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            // Code blocks (inline)
            .replace(/`(.*?)`/g, '<code>$1</code>');
    }
    
    // Helper method to detect URLs
    isURL(str) {
        try {
            new URL(str);
            return true;
        } catch {
            // Also check for URLs without protocol
            if (str.includes('.') && !str.includes(' ') && str.length > 4) {
                return true;
            }
            return false;
        }
    }

    // Extract URLs from a text message
    extractURLFromMessage(message) {
        // Regular expression to find URLs in text
        const urlRegex = /(https?:\/\/[^\s]+|www\.[^\s]+|[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]?\.[a-zA-Z]{2,}(?:\/[^\s]*)?)/gi;
        const matches = message.match(urlRegex);
        
        if (matches && matches.length > 0) {
            // Return the first URL found and the remaining text
            let firstUrl = matches[0];
            
            // Add protocol if missing
            if (!firstUrl.startsWith('http')) {
                firstUrl = 'https://' + firstUrl;
            }
            
            // Remove the URL from the message to get the remaining text
            const remainingText = message.replace(matches[0], '').trim();
            
            return {
                url: firstUrl,
                text: remainingText,
                hasUrl: true
            };
        }
        
        return {
            url: null,
            text: message,
            hasUrl: false
        };
    }
    
    // Detect if page is in Arabic layout
    isArabicLayout() {
        // Check if document direction is RTL or if Arabic content is detected
        return document.dir === 'rtl' || 
               document.documentElement.lang === 'ar' ||
               document.querySelector('html[dir="rtl"]') !== null ||
               this.detectArabicInPage();
    }
    
    // Detect Arabic content in the page
    detectArabicInPage() {
        // Check for Arabic characters in the page content
        const bodyText = document.body.textContent || '';
        const arabicRegex = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/;
        return arabicRegex.test(bodyText);
    }
    
    // Get localized messages
    getLocalizedMessage(key) {
        const messages = {
            'successfully_analyzed': {
                'en': 'Successfully analyzed:',
                'ar': 'تم تحليل الصفحة بنجاح:'
            },
            'comprehensive_summary': {
                'en': 'Please provide a comprehensive summary of this webpage, highlighting the main points and key information.',
                'ar': 'يرجى تقديم ملخص شامل لهذه الصفحة، مع تسليط الضوء على النقاط الرئيسية والمعلومات المهمة.'
            },
            're_analyzing': {
                'en': 'Re-analyzing:',
                'ar': 'إعادة تحليل:'
            },
            'previously_analyzed': {
                'en': 'previously analyzed',
                'ar': 'تم تحليلها سابقاً'
            },
            'error_processing': {
                'en': 'Sorry, I encountered an error while processing your question. Please try again.',
                'ar': 'عذراً، واجهت خطأ أثناء معالجة سؤالك. يرجى المحاولة مرة أخرى.'
            },
            'providers_busy': {
                'en': 'All AI providers are currently busy or unavailable. Please wait a moment and try again.',
                'ar': 'جميع موفري الذكاء الاصطناعي مشغولون أو غير متوفرين حالياً. يرجى الانتظار قليلاً والمحاولة مرة أخرى.'
            },
            'thinking_analyzing': {
                'en': 'Analyzing webpage...',
                'ar': 'تحليل الصفحة...'
            },
            'thinking_processing': {
                'en': 'Processing your question...',
                'ar': 'معالجة سؤالك...'
            },
            'thinking_thinking': {
                'en': 'AI is thinking...',
                'ar': 'الذكاء الاصطناعي يفكر...'
            },
            'thinking_generating': {
                'en': 'Generating response...',
                'ar': 'توليد الإجابة...'
            },
            'thinking_complete': {
                'en': 'Complete',
                'ar': 'مكتمل'
            }
        };
        
        const lang = this.isArabicLayout() ? 'ar' : 'en';
        return messages[key] && messages[key][lang] ? messages[key][lang] : messages[key]['en'];
    }
    
    showStatus(message, details = '') {
        if (this.statusText) {
            this.statusText.textContent = message;
        }
        // Note: statusDetails doesn't exist in new structure, so we skip it
        if (this.statusDetails) {
            this.statusDetails.textContent = details;
        }
        if (this.statusContainer) {
            this.statusContainer.classList.remove('hidden');
        }
    }
    
    hideStatus() {
        if (this.statusContainer) {
            this.statusContainer.classList.add('hidden');
        }
    }
    
    showPageInfo(data) {
        if (this.pageTitle) {
            this.pageTitle.textContent = data.title || 'Untitled Page';
        }
        if (this.pageUrl) {
            this.pageUrl.textContent = data.url;
        }
        if (this.pageLength) {
            this.pageLength.textContent = `${data.content_length} characters`;
        }
        
        if (this.pageInfo) {
            this.pageInfo.classList.remove('hidden');
        }
        if (this.chatInterface) {
            this.chatInterface.classList.remove('hidden');
        }
        
        this.updateSendButton();
    }
    
    async analyzeUrl(url = null) {
        // Get URL from parameter or chat input
        const targetUrl = url || this.chatInput.value.trim();
        
        if (!targetUrl) {
            this.showError('Please enter a URL to analyze');
            return;
        }
        
        if (this.isAnalyzing) {
            return;
        }
        
        // Reset state for new URL analysis
        if (this.currentPageUrl && this.currentPageUrl !== targetUrl) {
            this.isPageAnalyzed = false;
            this.currentPageUrl = null;
            
            // Generate a new session ID when switching to a different URL to avoid session conflicts
            this.sessionId = this.generateSessionId();
            console.log('🆕 Generated new sessionId for different URL:', this.sessionId, 'URL:', targetUrl);
        } else {
            console.log('🔄 Reusing existing sessionId for same/new URL:', this.sessionId, 'URL:', targetUrl);
        }
        
        this.isAnalyzing = true;
        this.updateSendButton();
        this.hideError();
        
        // Clear input after URL submission (don't add user message yet, will be added with success message)
        this.chatInput.value = '';
        this.updateCharacterCount();
        
        // Show AI thinking for analysis
        this.showAIThinking();
        this.updateAIThinking('thinking_analyzing');
        
        try {
            // Get selected analysis mode
            const analysisMode = document.getElementById('analysis-mode-select')?.value || 'fast';
            
            // Use EventSource for server-sent events
            const eventSource = new EventSource(`/api/chat-agent/analyze?url=${encodeURIComponent(targetUrl)}&session_id=${this.sessionId}&analysis_mode=${analysisMode}`);
            
            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'progress') {
                        this.updateAIThinking(data.message);
                    } else if (data.type === 'analysis_complete') {
                        // Analysis is complete, now summary will start
                        this.hideAIThinking();
                        this.currentPageUrl = targetUrl;
                        this.isPageAnalyzed = true;
                        
                        // Keep our existing sessionId, don't overwrite with server's sessionId
                        console.log('✅ Analysis complete, keeping sessionId:', this.sessionId);
                        
                        // Save to analyzed URLs history
                        this.analyzedUrls.set(targetUrl, {
                            sessionId: this.sessionId,
                            title: data.data.title || 'Webpage',
                            timestamp: Date.now(),
                            messageCount: 1
                        });
                        this.saveHistoryToStorage();
                        
                        // Add user message for the URL
                        if (this.pendingQuestion && this.pendingQuestion.trim()) {
                            // Mixed input: URL + question
                            this.addUserMessage(this.pendingQuestion);
                        } else {
                            // URL only
                            this.addUserMessage(targetUrl);
                        }
                        
                        // Add success message
                        this.addSystemMessage(`✅ ${this.getLocalizedMessage('successfully_analyzed')} ${data.data.title || 'Webpage'}`);
                        
                    } else if (data.type === 'summary_start') {
                        // Summary generation is starting
                        this.showAIThinking(data.message || 'Generating summary...');
                        
                    } else if (data.type === 'summary_thinking') {
                        // Update thinking process for summary
                        this.updateThinkingContent(data.message);
                        
                    } else if (data.type === 'summary_streaming') {
                        // Summary is being streamed
                        this.hideAIThinking();
                        
                        if (!this.currentStreamingMessageId) {
                            // Create new AI message for summary
                            this.currentStreamingMessageId = this.addAIMessage('');
                        }
                        
                        // Update the streaming message
                        this.updateAIMessage(this.currentStreamingMessageId, data.text || data.message, 'AI Assistant', true);
                        
                    } else if (data.type === 'summary_complete') {
                        // Summary is complete
                        this.hideAIThinking();
                        this.completeThinkingSection();
                        
                        if (this.currentStreamingMessageId) {
                            this.updateAIMessage(this.currentStreamingMessageId, data.answer || '', 'AI Assistant', false);
                            this.currentStreamingMessageId = null;
                        }
                        
                        // Now handle any pending question
                        if (this.pendingQuestion && this.pendingQuestion.trim()) {
                            console.log('📝 Now handling pending question after summary:', this.pendingQuestion);
                            this.sendQuestionToBackend(this.pendingQuestion);
                            this.pendingQuestion = null;
                        }
                        
                        eventSource.close();
                        this.isAnalyzing = false;
                        this.updateSendButton();
                        
                    } else if (data.type === 'summary_error') {
                        // Error during summary generation
                        this.hideAIThinking();
                        this.addErrorMessage(`❌ Failed to generate summary: ${data.message}`);
                        
                        // Still handle pending question if any
                        if (this.pendingQuestion && this.pendingQuestion.trim()) {
                            this.sendQuestionToBackend(this.pendingQuestion);
                            this.pendingQuestion = null;
                        }
                        
                        eventSource.close();
                        this.isAnalyzing = false;
                        this.updateSendButton();
                        
                    } else if (data.type === 'complete') {
                        // Fallback for old complete type (shouldn't happen with new implementation)
                        this.hideAIThinking();
                        this.currentPageUrl = targetUrl;
                        this.isPageAnalyzed = true;
                        
                        console.log('✅ Analysis complete, keeping sessionId:', this.sessionId);
                        
                        this.analyzedUrls.set(targetUrl, {
                            sessionId: this.sessionId,
                            title: data.data.title || 'Webpage',
                            timestamp: Date.now(),
                            messageCount: 1
                        });
                        this.saveHistoryToStorage();
                        
                        eventSource.close();
                        this.isAnalyzing = false;
                        this.updateSendButton();
                        
                        if (this.pendingQuestion && this.pendingQuestion.trim()) {
                            const userMessageId = this.addUserMessage(this.pendingQuestion);
                            this.addSystemMessage(`✅ ${this.getLocalizedMessage('successfully_analyzed')} ${data.data.title || 'Webpage'}`);
                            this.sendQuestionToBackend(this.pendingQuestion);
                            this.pendingQuestion = null;
                        } else {
                            const userMessageId = this.addUserMessage(targetUrl);
                            this.appendToUserMessage(userMessageId, `\n✅ ${this.getLocalizedMessage('successfully_analyzed')} ${data.data.title || 'Webpage'}`);
                        }
                        
                    } else if (data.type === 'error') {
                        throw new Error(data.message);
                    }
                } catch (e) {
                    console.error('Error parsing analysis data:', e);
                }
            };
            
            eventSource.onerror = (error) => {
                console.error('Analysis EventSource error:', error);
                this.hideAIThinking();
                this.addSystemMessage('❌ Failed to analyze webpage. Please try again.');
                eventSource.close();
                this.isAnalyzing = false;
                this.updateSendButton();
            };
            
            // Store current request for cancellation
            this.currentRequest = eventSource;
            
        } catch (error) {
            console.error('Analysis error:', error);
            this.hideAIThinking();
            this.addSystemMessage('❌ Failed to analyze webpage: ' + error.message);
            this.isAnalyzing = false;
            this.updateSendButton();
        }
    }
    
    async summarizePage() {
        if (!this.isPageAnalyzed) {
            this.showError('Please analyze a webpage first');
            return;
        }
        
        this.chatInput.value = this.getLocalizedMessage('comprehensive_summary');
        this.updateCharacterCount();
        this.updateSendButton();
        this.sendMessage();
    }
    
    async sendMessage() {
        const message = this.chatInput.value.trim();
        
        if (!message || this.isResponding) {
            return;
        }
        
        // Validate message length (2000 character limit)
        if (message.length > 2000) {
            this.addErrorMessage(`❌ Message too long. Please limit your message to 2000 characters. Current length: ${message.length}`);
            return;
        }
        
        // Check if this is a fresh conversation start (no URL in message and user seems to be starting fresh)
        const hasUrlInMessage = this.isURL(message) || this.extractURLFromMessage(message).hasUrl;
        const isGeneralGreeting = /^(hi|hello|hey|greetings|good morning|good afternoon|good evening)$/i.test(message.trim());
        
        // If user says a general greeting and there's no URL in the message, start fresh
        if (!hasUrlInMessage && isGeneralGreeting && this.isPageAnalyzed) {
            console.log('🔄 User started fresh conversation, clearing old webpage context');
            this.clearPageContext();
        }
        
        // Allow general chat even without webpage analysis
        // No need to check this.isPageAnalyzed anymore
        
        this.isResponding = true;
        this.updateSendButton();
        
        // Add user message to chat
        this.addUserMessage(message);
        
        // If there's a webpage context, show a subtle indicator
        if (this.isPageAnalyzed && this.currentPageUrl) {
            const urlData = this.analyzedUrls.get(this.currentPageUrl);
            const title = urlData ? urlData.title : 'Analyzed Webpage';
            console.log(`📄 Question will be answered in context of: ${title}`);
        }
        
        // Update message count for current URL if it's in history, or for general chat
        if (this.currentPageUrl && this.analyzedUrls.has(this.currentPageUrl)) {
            const urlData = this.analyzedUrls.get(this.currentPageUrl);
            urlData.messageCount = (urlData.messageCount || 0) + 1;
            this.saveHistoryToStorage();
        } else {
            // For general chat sessions, we could track them separately if needed
            // For now, we'll just continue without tracking message count
        }
        
        // Clear input
        this.chatInput.value = '';
        this.updateCharacterCount();
        
        // Show AI thinking
        this.showAIThinking();
        
        console.log('🤖 Sending message with sessionId:', this.sessionId);
        console.log('📊 Current state - isPageAnalyzed:', this.isPageAnalyzed, 'currentPageUrl:', this.currentPageUrl);
        
        // Defensive check: ensure we have a valid sessionId
        if (!this.sessionId || this.sessionId === 'undefined' || this.sessionId === null) {
            console.error('❌ Invalid sessionId detected:', this.sessionId, 'generating new one');
            this.sessionId = this.generateSessionId();
            console.log('🆕 Generated new sessionId:', this.sessionId);
        }
        
        // Additional context logging for debugging
        if (this.isPageAnalyzed && this.currentPageUrl) {
            console.log('📝 Using webpage context for question about:', this.currentPageUrl);
        } else {
            console.log('💬 Using general chat mode (no webpage context)');
        }
        
        try {
            // Create AI message container
            const aiMessageId = this.addAIMessage('');
            
            // Get selected analysis mode
            const analysisMode = document.getElementById('analysis-mode-select')?.value || 'fast';
            
            // Use EventSource for streaming response
            const eventSource = new EventSource(`/api/chat-agent/ask?question=${encodeURIComponent(message)}&session_id=${this.sessionId}&analysis_mode=${analysisMode}`);
            
            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'progress') {
                        this.updateAIThinking(data.message);
                    } else if (data.type === 'thinking_content') {
                        // Stream thinking content to collapsible section
                        this.showThinkingContent(data.text, data.message);
                    } else if (data.type === 'final_answer') {
                        // Hide thinking animation and show final answer prominently
                        this.hideAIThinking();
                        this.completeThinkingSection();
                        this.updateAIMessage(aiMessageId, data.text, data.provider, true);
                    } else if (data.type === 'word_streaming') {
                        // Hide thinking, show word-by-word streaming response
                        this.hideAIThinking();
                        this.updateAIMessage(aiMessageId, data.text, data.provider, true);
                    } else if (data.type === 'streaming') {
                        // Hide thinking, show streaming response
                        this.hideAIThinking();
                        this.updateAIMessage(aiMessageId, data.text, data.provider, true);
                    } else if (data.type === 'complete') {
                        this.hideAIThinking();
                        this.updateAIMessage(aiMessageId, data.answer, data.provider, false);
                        eventSource.close();
                        this.isResponding = false;
                        this.updateSendButton();
                    } else if (data.type === 'error') {
                        // Check if it's a specific error message we can localize
                        let errorMessage = data.message;
                        if (errorMessage.includes('All AI providers are currently busy')) {
                            errorMessage = this.getLocalizedMessage('providers_busy');
                        } else if (errorMessage.includes('Sorry, I encountered an error')) {
                            errorMessage = this.getLocalizedMessage('error_processing');
                        }
                        throw new Error(errorMessage);
                    }
                } catch (e) {
                    console.error('Error parsing chat data:', e);
                }
            };
            
            eventSource.onerror = (error) => {
                console.error('Chat EventSource error:', error);
                this.hideAIThinking();
                this.updateAIMessage(aiMessageId, `❌ ${this.getLocalizedMessage('error_processing')}`, 'Error');
                eventSource.close();
                this.isResponding = false;
                this.updateSendButton();
            };
            
            // Store current request for cancellation
            this.currentRequest = eventSource;
            
        } catch (error) {
            console.error('Chat error:', error);
            this.hideAIThinking();
            this.showError('Failed to send message: ' + error.message);
            this.isResponding = false;
            this.updateSendButton();
        }
    }

    async sendQuestionToBackend(question) {
        if (!question || this.isResponding) {
            return;
        }
        
        this.isResponding = true;
        this.updateSendButton();
        
        // Show AI thinking
        this.showAIThinking();
        
        console.log('🤖 Sending question to backend with sessionId:', this.sessionId, 'Question:', question);
        
        try {
            // Create AI message container
            const aiMessageId = this.addAIMessage('');
            
            // Get selected analysis mode
            const analysisMode = document.getElementById('analysis-mode-select')?.value || 'fast';
            
            // Use EventSource for streaming response
            const eventSource = new EventSource(`/api/chat-agent/ask?question=${encodeURIComponent(question)}&session_id=${this.sessionId}&analysis_mode=${analysisMode}`);
            
            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'progress') {
                        this.updateAIThinking(data.message);
                    } else if (data.type === 'word_streaming') {
                        this.hideAIThinking();
                        this.updateAIMessage(aiMessageId, data.text, data.provider, true);
                    } else if (data.type === 'streaming') {
                        this.hideAIThinking();
                        this.updateAIMessage(aiMessageId, data.text, data.provider, true);
                    } else if (data.type === 'complete') {
                        this.hideAIThinking();
                        this.updateAIMessage(aiMessageId, data.answer, data.provider, false);
                        eventSource.close();
                        this.isResponding = false;
                        this.updateSendButton();
                    } else if (data.type === 'error') {
                        let errorMessage = data.message;
                        if (errorMessage.includes('All AI providers are currently busy')) {
                            errorMessage = this.getLocalizedMessage('providers_busy');
                        } else if (errorMessage.includes('Sorry, I encountered an error')) {
                            errorMessage = this.getLocalizedMessage('error_processing');
                        }
                        throw new Error(errorMessage);
                    }
                } catch (e) {
                    console.error('Error parsing chat data:', e);
                }
            };
            
            eventSource.onerror = (error) => {
                console.error('Question EventSource error:', error);
                this.hideAIThinking();
                this.updateAIMessage(aiMessageId, `❌ ${this.getLocalizedMessage('error_processing')}`, 'Error');
                eventSource.close();
                this.isResponding = false;
                this.updateSendButton();
            };
            
            // Store current request for cancellation
            this.currentRequest = eventSource;
            
        } catch (error) {
            console.error('Question error:', error);
            this.hideAIThinking();
            this.showError('Failed to send question: ' + error.message);
            this.isResponding = false;
            this.updateSendButton();
        }
    }
    
    stopResponse() {
        if (this.currentRequest) {
            this.currentRequest.close();
            this.currentRequest = null;
        }
        
        // Cancel on server side
        fetch(`/api/chat-agent/cancel?session_id=${this.sessionId}`, {
            method: 'POST'
        }).catch(console.error);
        
        this.hideAIThinking();
        this.isResponding = false;
        this.isAnalyzing = false;  // Also reset analysis state
        this.updateSendButton();
        this.resetButtons();
        
        // Add cancellation message
        this.addSystemMessage('Response cancelled by user');
    }
    
    cancelAnalysis() {
        if (this.currentRequest) {
            this.currentRequest.close();
            this.currentRequest = null;
        }
        
        // Cancel on server side
        fetch(`/api/chat-agent/cancel?session_id=${this.sessionId}`, {
            method: 'POST'
        }).catch(console.error);
        
        this.hideStatus();
        this.isAnalyzing = false;
        this.analyzeBtn.disabled = false;
    }
    
    clearChat() {
        // Clear local chat
        const chatWelcome = this.chatMessages.querySelector('.chat-welcome');
        this.chatMessages.innerHTML = '';
        if (chatWelcome) {
            this.chatMessages.appendChild(chatWelcome);
        }
        
        // Clear on server side
        fetch(`/api/chat-agent/clear?session_id=${this.sessionId}`, {
            method: 'POST'
        }).catch(console.error);
    }
    
    resetButtons() {
        if (this.stopBtn) {
            this.stopBtn.classList.add('hidden');
        }
        this.updateSendButton();
    }
    
    addUserMessage(message) {
        const messageId = 'user-msg-' + Date.now();
        const messageEl = document.createElement('div');
        messageEl.id = messageId;
        messageEl.className = 'message-bubble user';
        
        // Create message structure
        const messageAvatar = document.createElement('div');
        messageAvatar.className = 'message-avatar';
        messageAvatar.innerHTML = '<i class="fas fa-user"></i>';
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        
        const messageText = document.createElement('div');
        messageText.className = 'message-text';
        messageText.textContent = message;
        
        const messageTime = document.createElement('div');
        messageTime.className = 'message-time';
        messageTime.textContent = this.formatTime(new Date());
        
        messageContent.appendChild(messageText);
        messageContent.appendChild(messageTime);
        messageEl.appendChild(messageContent);
        messageEl.appendChild(messageAvatar);
        
        // Remove welcome message if exists
        const welcome = this.chatMessages.querySelector('.welcome-container');
        if (welcome) {
            welcome.remove();
        }
        
        this.chatMessages.appendChild(messageEl);
        this.scrollToBottom();
        
        return messageId;
    }
    
    appendToUserMessage(messageId, additionalText) {
        const messageEl = document.getElementById(messageId);
        if (messageEl) {
            const messageText = messageEl.querySelector('.message-text');
            if (messageText) {
                // Use innerHTML to handle line breaks properly
                const currentText = messageText.textContent;
                messageText.innerHTML = currentText + '<br>' + additionalText.replace(/\n/g, '<br>');
            }
        }
    }
    
    addAIMessage(content, provider = '') {
        const messageId = 'ai-msg-' + Date.now();
        const messageEl = document.createElement('div');
        messageEl.id = messageId;
        messageEl.className = 'message-bubble ai';
        
        // Create message structure
        const messageAvatar = document.createElement('div');
        messageAvatar.className = 'message-avatar';
        messageAvatar.innerHTML = '<i class="fas fa-robot"></i>';
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        
        const messageText = document.createElement('div');
        messageText.className = 'message-text';
        if (content) {
            // Convert basic markdown to HTML for better formatting
            messageText.innerHTML = this.convertMarkdownToHtml(content);
        }
        
        const messageTime = document.createElement('div');
        messageTime.className = 'message-time';
        messageTime.innerHTML = `
            ${this.formatTime(new Date())}
            ${provider ? `<span class="provider-badge">via ${provider}</span>` : ''}
        `;
        
        messageContent.appendChild(messageText);
        messageContent.appendChild(messageTime);
        messageEl.appendChild(messageAvatar);
        messageEl.appendChild(messageContent);
        
        this.chatMessages.appendChild(messageEl);
        this.scrollToBottom();
        
        return messageId;
    }
    
    updateAIMessage(messageId, content, provider = '', isStreaming = false) {
        const messageEl = document.getElementById(messageId);
        if (!messageEl) return;
        
        const textEl = messageEl.querySelector('.message-text');
        const timeEl = messageEl.querySelector('.message-time');
        
        if (textEl) {
            if (isStreaming) {
                // Word-by-word streaming effect
                this.typeWriterEffect(textEl, content);
            } else {
                // Final content update - convert markdown to HTML
                textEl.innerHTML = this.convertMarkdownToHtml(content);
                textEl.classList.remove('streaming-text');
            }
        }
        
        if (timeEl && provider) {
            timeEl.innerHTML = `
                ${this.formatTime(new Date())}
                <span class="provider-badge">via ${provider}</span>
            `;
        }
        
        this.scrollToBottom();
    }
    
    typeWriterEffect(textEl, newContent) {
        // Add streaming class for cursor effect
        textEl.classList.add('streaming-text');
        
        // Always update with formatted content during streaming
        textEl.innerHTML = this.convertMarkdownToHtml(newContent);
        
        // Smooth scroll to bottom without jarring movement
        requestAnimationFrame(() => {
            this.scrollToBottom();
        });
    }
    
    addSystemMessage(message) {
        const messageEl = document.createElement('div');
        messageEl.className = 'chat-message system-message';
        messageEl.innerHTML = `
            <div class="system-message-content">
                <i class="fas fa-info-circle me-2"></i>
                ${this.escapeHtml(message)}
            </div>
        `;
        
        this.chatMessages.appendChild(messageEl);
        this.scrollToBottom();
    }
    

    resetButtons() {
        // Reset any button states if needed
        this.updateSendButton();
    }
    
    updateCharacterCount() {
        // Update character count if there's a counter element
        const counter = document.getElementById('char-count');
        if (counter) {
            const currentLength = this.chatInput.value.length;
            const maxLength = 2000;
            counter.textContent = currentLength;
            
            // Update counter color based on usage
            const counterElement = counter.parentElement;
            if (currentLength > maxLength * 0.9) {
                counterElement.style.color = '#ef4444'; // Red when near limit
            } else if (currentLength > maxLength * 0.7) {
                counterElement.style.color = '#f59e0b'; // Orange when getting close
            } else {
                counterElement.style.color = '#6b7280'; // Gray for normal
            }
        }
    }
    
    showTypingIndicator() {
        // Don't add if already exists
        if (this.chatMessages.querySelector('.typing-indicator')) {
            return;
        }
        
        const typingEl = document.createElement('div');
        typingEl.className = 'typing-indicator';
        
        // Create typing structure to match new design
        const typingAvatar = document.createElement('div');
        typingAvatar.className = 'message-avatar';
        typingAvatar.innerHTML = '<i class="fas fa-robot"></i>';
        
        const typingContent = document.createElement('div');
        typingContent.className = 'typing-content';
        
        const typingDots = document.createElement('div');
        typingDots.className = 'typing-dots';
        typingDots.innerHTML = '<span></span><span></span><span></span>';
        
        typingContent.appendChild(typingDots);
        typingEl.appendChild(typingAvatar);
        typingEl.appendChild(typingContent);
        
        this.chatMessages.appendChild(typingEl);
        this.scrollToBottom();
    }
    
    hideTypingIndicator() {
        const typingEl = this.chatMessages.querySelector('.typing-indicator');
        if (typingEl) {
            typingEl.remove();
        }
    }
    
    showAIThinking() {
        // Hide any existing thinking indicators
        this.hideAIThinking();
        
        const thinkingEl = document.getElementById('ai-thinking');
        if (thinkingEl) {
            // Keep the original hidden, only show the clone in chat
            thinkingEl.classList.add('hidden');
            
            // Clone the element and show it in chat messages
            const thinkingClone = thinkingEl.cloneNode(true);
            thinkingClone.id = 'ai-thinking-active';
            thinkingClone.classList.remove('hidden'); // Make sure clone is visible
            this.chatMessages.appendChild(thinkingClone);
            this.scrollToBottom();
        }
    }
    
    hideAIThinking() {
        // Hide the original thinking element
        const thinkingEl = document.getElementById('ai-thinking');
        if (thinkingEl) {
            thinkingEl.classList.add('hidden');
        }
        
        // Remove any active thinking clone from chat
        const activeThinking = document.getElementById('ai-thinking-active');
        if (activeThinking) {
            activeThinking.remove();
        }
    }
    
    updateAIThinking(message) {
        // Localize the message if it's a known key
        const localizedMessage = this.getLocalizedMessage(message);
        
        // Update thinking text in both original and active clone
        const thinkingText = document.querySelector('.thinking-text');
        if (thinkingText) {
            thinkingText.textContent = localizedMessage;
        }
        
        // Also update the active thinking clone if it exists
        const activeThinking = document.getElementById('ai-thinking-active');
        if (activeThinking) {
            const activeThinkingText = activeThinking.querySelector('.thinking-text');
            if (activeThinkingText) {
                activeThinkingText.textContent = localizedMessage;
            }
        }
    }

    // Collapsible Thinking Content Methods (DeepSeek-style)
    showThinkingContent(text, statusMessage = 'Processing...') {
        // Create or update thinking section
        let thinkingSection = document.getElementById('active-thinking-section');
        
        if (!thinkingSection) {
            // Create new thinking section from template
            const template = document.getElementById('thinking-template');
            if (!template) return;
            
            thinkingSection = template.cloneNode(true);
            thinkingSection.id = 'active-thinking-section';
            thinkingSection.classList.remove('hidden');
            
            // Add click handler for toggle
            const header = thinkingSection.querySelector('.thinking-header');
            if (header) {
                header.addEventListener('click', () => this.toggleThinkingContent());
                header.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        this.toggleThinkingContent();
                    }
                });
            }
            
            // Remove welcome message if exists
            const welcome = this.chatMessages.querySelector('.welcome-container');
            if (welcome) {
                welcome.remove();
            }
            
            // Hide any existing AI thinking animation
            this.hideAIThinking();
            
            // Add to chat messages
            this.chatMessages.appendChild(thinkingSection);
            this.scrollToBottom();
        }
        
        // Update thinking content
        const thinkingText = thinkingSection.querySelector('.thinking-text');
        if (thinkingText) {
            thinkingText.textContent = text;
        }
        
        // Update status message
        const statusText = thinkingSection.querySelector('.thinking-status-text');
        if (statusText) {
            statusText.textContent = statusMessage;
        }
        
        // Add processing state
        const statusEl = thinkingSection.querySelector('.thinking-status');
        if (statusEl) {
            statusEl.classList.add('processing');
            statusEl.classList.remove('completed');
        }
    }

    completeThinkingSection() {
        const thinkingSection = document.getElementById('active-thinking-section');
        if (thinkingSection) {
            // Update status to completed
            const statusText = thinkingSection.querySelector('.thinking-status-text');
            if (statusText) {
                statusText.textContent = this.getLocalizedMessage('thinking_complete') || 'Complete';
            }
            
            // Update status styling
            const statusEl = thinkingSection.querySelector('.thinking-status');
            if (statusEl) {
                statusEl.classList.remove('processing');
                statusEl.classList.add('completed');
            }
            
            // Update icon to show completion
            const icon = thinkingSection.querySelector('.thinking-icon i');
            if (icon) {
                icon.className = 'fas fa-check-circle';
            }
        }
    }

    toggleThinkingContent() {
        const thinkingSection = document.getElementById('active-thinking-section');
        if (!thinkingSection) return;
        
        const container = thinkingSection.querySelector('.thinking-container');
        const content = thinkingSection.querySelector('.thinking-content');
        
        if (!container || !content) return;
        
        // Toggle expanded state
        if (container.classList.contains('expanded')) {
            // Collapse
            container.classList.remove('expanded');
            content.classList.remove('expanded');
            content.classList.add('collapsed');
        } else {
            // Expand
            container.classList.add('expanded');
            content.classList.add('expanded');
            content.classList.remove('collapsed');
        }
        
        // Scroll to keep section in view after expanding
        setTimeout(() => {
            this.scrollToBottom();
        }, 300); // Wait for animation to complete
    }
    
    showError(message) {
        // Create or update error alert
        let errorEl = document.getElementById('chat-agent-error');
        if (!errorEl) {
            errorEl = document.createElement('div');
            errorEl.id = 'chat-agent-error';
            errorEl.className = 'alert alert-danger mt-3';
            this.chatSection.appendChild(errorEl);
        }
        
        errorEl.innerHTML = `
            <div class="d-flex align-items-start">
                <i class="fas fa-exclamation-triangle me-3 mt-1"></i>
                <div class="flex-grow-1">
                    <h6 class="alert-heading">Error</h6>
                    <p class="mb-0">${this.escapeHtml(message)}</p>
                </div>
            </div>
        `;
        
        errorEl.classList.remove('hidden');
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            this.hideError();
        }, 5000);
    }
    
    hideError() {
        const errorEl = document.getElementById('chat-agent-error');
        if (errorEl) {
            errorEl.classList.add('hidden');
        }
    }
    
    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    formatTime(date) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
}

// Initialize chat agent when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if chat agent section exists
    if (document.getElementById('chat-agent-section')) {
        window.chatAgent = new ChatAgent();
        console.log('✅ Chat Agent ready');
    }
});