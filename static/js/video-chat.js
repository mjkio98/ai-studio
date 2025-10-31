/**
 * Video Chat Interface - YouTube Video Analysis with Q&A
 * Similar to Chat Agent but specialized for video content
 */

class VideoChat {
    constructor() {
        this.sessionId = this.generateSessionId();
        this.currentVideo = null;
        this.chatHistory = [];
        this.isProcessing = false;
        
        // DOM elements
        this.messagesContainer = document.getElementById('video-chat-messages');
        this.chatInput = document.getElementById('video-chat-input');
        this.sendBtn = document.getElementById('send-video-message-btn');
        this.stopBtn = document.getElementById('stop-video-message-btn');
        this.clearBtn = document.getElementById('clear-video-chat-btn');
        this.charCount = document.getElementById('video-char-count');
        
        this.initializeEventListeners();
        this.initializeLanguage();
        console.log('✅ Video Chat initialized with session:', this.sessionId);
    }
    
    generateSessionId() {
        return 'video_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    initializeEventListeners() {
        // Input handling
        if (this.chatInput) {
            this.chatInput.addEventListener('input', () => this.handleInputChange());
            this.chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }
        
        // Button handlers
        if (this.sendBtn) {
            this.sendBtn.addEventListener('click', () => this.sendMessage());
        }
        
        if (this.stopBtn) {
            this.stopBtn.addEventListener('click', () => this.stopProcessing());
        }
        
        if (this.clearBtn) {
            this.clearBtn.addEventListener('click', () => this.clearChat());
        }
        
        // Language change event listeners
        window.addEventListener('languageChanged', (e) => {
            const language = e.detail.language;
            console.log('🌐 Video Chat: Language changed to', language);
            this.updateLanguageElements(language);
        });
        
        // Also listen for storage changes in case language is changed in another tab
        window.addEventListener('storage', (e) => {
            if (e.key === 'preferred-language' || e.key === 'preferred_language') {
                const newLang = e.newValue;
                if (newLang) {
                    console.log('🌐 Video Chat: Language changed via storage to', newLang);
                    this.updateLanguageElements(newLang);
                }
            }
        });
        
        // Listen for document attribute changes
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'attributes' && 
                    (mutation.attributeName === 'dir' || mutation.attributeName === 'lang')) {
                    const dir = document.documentElement.getAttribute('dir');
                    const lang = document.documentElement.getAttribute('lang');
                    const detectedLang = dir === 'rtl' ? 'ar' : (lang || 'en');
                    console.log('🌐 Video Chat: Document attribute changed, detected language:', detectedLang);
                    this.updateLanguageElements(detectedLang);
                }
            });
        });
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['dir', 'lang'] });
    }
    
    handleInputChange() {
        const text = this.chatInput.value;
        const length = text.length;
        const maxLength = 2000;
        
        // Update character counter
        if (this.charCount) {
            this.charCount.textContent = length;
            
            // Update counter color based on usage
            const counterElement = this.charCount.parentElement;
            if (length > maxLength * 0.9) {
                counterElement.style.color = '#ef4444'; // Red when near limit
            } else if (length > maxLength * 0.7) {
                counterElement.style.color = '#f59e0b'; // Orange when getting close
            } else {
                counterElement.style.color = '#6b7280'; // Gray for normal
            }
        }
        
        // Enable/disable send button
        const isEmpty = text.trim().length === 0;
        if (this.sendBtn) {
            this.sendBtn.disabled = isEmpty || this.isProcessing;
        }
        
        // Auto-resize input (optional)
        this.chatInput.style.height = 'auto';
        this.chatInput.style.height = Math.min(this.chatInput.scrollHeight, 120) + 'px';
    }
    
    async sendMessage() {
        const message = this.chatInput.value.trim();
        if (!message || this.isProcessing) return;
        
        // Validate message length (2000 character limit)
        if (message.length > 2000) {
            this.addErrorMessage(`❌ Message too long. Please limit your message to 2000 characters. Current length: ${message.length}`);
            return;
        }
        
        // Clear input and update UI
        this.chatInput.value = '';
        this.handleInputChange();
        
        // Add user message to chat
        this.addUserMessage(message);
        
        // Detect if it's a YouTube URL
        const isYouTubeUrl = this.isYouTubeURL(message);
        
        if (isYouTubeUrl) {
            await this.processVideoURL(message);
        } else {
            await this.askVideoQuestion(message);
        }
    }
    
    isYouTubeURL(text) {
        return text.includes('youtube.com') || text.includes('youtu.be');
    }
    
    async processVideoURL(url) {
        this.isProcessing = true;
        this.updateProcessingState(true);
        
        try {
            // Show collapsible thinking process
            const thinkingId = this.showThinkingProcess('🔍 Starting video analysis...');
            
            // Use EventSource for streaming response
            const eventSource = new EventSource(`/api/video-chat/stream?message=${encodeURIComponent(url)}&session_id=${this.sessionId}`);
            
            let aiMessageId = null;
            let firstStreamingResponse = true;
            
            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('Video EventSource received:', data);
                    
                    if (data.type === 'progress') {
                        // Update thinking process with progress
                        this.updateThinkingProcess(thinkingId, data.message, `${data.message} (${data.progress || 0}%)`);
                    } else if (data.type === 'streaming') {
                        console.log('Streaming data received:', data.text.substring(0, 100) + '...');
                        
                        // Complete thinking process and start AI response
                        if (firstStreamingResponse) {
                            this.completeThinkingProcess(thinkingId, '✅ Analysis complete');
                            aiMessageId = this.createAIMessage(data.text);
                            firstStreamingResponse = false;
                        } else if (aiMessageId) {
                            this.updateAIMessage(aiMessageId, data.text, 'YouTube AI', true);
                        }
                    } else if (data.type === 'complete') {
                        console.log('Complete data received:', data);
                        if (thinkingId) {
                            this.completeThinkingProcess(thinkingId, '✅ Analysis complete');
                        }
                        this.currentVideo = data.video_info;
                        if (aiMessageId) {
                            this.updateAIMessage(aiMessageId, data.content, 'YouTube AI', false);
                        } else {
                            // If no streaming happened, create final message
                            aiMessageId = this.createAIMessage(data.content);
                        }
                        eventSource.close();
                        this.isProcessing = false;
                        this.updateProcessingState(false);
                    } else if (data.type === 'error') {
                        console.error('Error from backend:', data.message);
                        if (thinkingId) {
                            this.updateThinkingProcess(thinkingId, '❌ Error occurred', data.message);
                        }
                        if (aiMessageId) {
                            this.updateAIMessage(aiMessageId, data.message, 'Error', false);
                        } else {
                            this.addErrorMessage(data.message);
                        }
                        eventSource.close();
                        this.isProcessing = false;
                        this.updateProcessingState(false);
                    }
                } catch (e) {
                    console.error('Error parsing video data:', e, 'Raw data:', event.data);
                }
            };
            
            eventSource.onerror = (error) => {
                console.error('Video processing EventSource error:', error);
                if (thinkingId) {
                    this.updateThinkingProcess(thinkingId, '❌ Connection error', 'Failed to connect to analysis service');
                }
                if (aiMessageId) {
                    this.updateAIMessage(aiMessageId, '❌ Failed to process video. Please try again.', 'Error', false);
                } else {
                    this.addErrorMessage('❌ Failed to process video. Please try again.');
                }
                eventSource.close();
                this.isProcessing = false;
                this.updateProcessingState(false);
            };
            
            // Store current request for cancellation
            this.currentRequest = eventSource;
            
        } catch (error) {
            this.addErrorMessage(`❌ Network error: ${error.message}`);
            this.isProcessing = false;
            this.updateProcessingState(false);
        }
    }
    
    async askVideoQuestion(question) {
        if (!this.currentVideo) {
            this.addErrorMessage('❌ Please analyze a YouTube video first before asking questions.');
            return;
        }
        
        this.isProcessing = true;
        this.updateProcessingState(true);
        
        try {
            // Show collapsible thinking process for Q&A
            const thinkingId = this.showThinkingProcess('🤔 Thinking about your question...');
            
            // Use EventSource for streaming response
            const eventSource = new EventSource(`/api/video-chat/stream?message=${encodeURIComponent(question)}&session_id=${this.sessionId}`);
            
            let aiMessageId = null;
            let firstStreamingResponse = true;
            
            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'progress') {
                        this.updateThinkingProcess(thinkingId, data.message, 'Analyzing video content for your question...');
                    } else if (data.type === 'streaming') {
                        // Complete thinking process and start AI response
                        if (firstStreamingResponse) {
                            this.completeThinkingProcess(thinkingId, '✅ Found relevant information');
                            aiMessageId = this.createAIMessage(data.text);
                            firstStreamingResponse = false;
                        } else if (aiMessageId) {
                            this.updateAIMessage(aiMessageId, data.text, 'YouTube AI', true);
                        }
                    } else if (data.type === 'qa_response') {
                        if (thinkingId) {
                            this.completeThinkingProcess(thinkingId, '✅ Answer generated');
                        }
                        if (aiMessageId) {
                            this.updateAIMessage(aiMessageId, data.answer, 'YouTube AI', false);
                        } else {
                            aiMessageId = this.createAIMessage(data.answer);
                        }
                        eventSource.close();
                        this.isProcessing = false;
                        this.updateProcessingState(false);
                    } else if (data.type === 'complete') {
                        if (thinkingId) {
                            this.completeThinkingProcess(thinkingId, '✅ Complete');
                        }
                        eventSource.close();
                        this.isProcessing = false;
                        this.updateProcessingState(false);
                    } else if (data.type === 'error') {
                        if (thinkingId) {
                            this.updateThinkingProcess(thinkingId, '❌ Error occurred', data.message);
                        }
                        if (aiMessageId) {
                            this.updateAIMessage(aiMessageId, data.message, 'Error', false);
                        } else {
                            this.addErrorMessage(data.message);
                        }
                        eventSource.close();
                        this.isProcessing = false;
                        this.updateProcessingState(false);
                    }
                } catch (e) {
                    console.error('Error parsing Q&A data:', e);
                }
            };
            
            eventSource.onerror = (error) => {
                console.error('Q&A EventSource error:', error);
                if (thinkingId) {
                    this.updateThinkingProcess(thinkingId, '❌ Connection error', 'Failed to connect to Q&A service');
                }
                if (aiMessageId) {
                    this.updateAIMessage(aiMessageId, '❌ Failed to process question. Please try again.', 'Error', false);
                } else {
                    this.addErrorMessage('❌ Failed to process question. Please try again.');
                }
                eventSource.close();
                this.isProcessing = false;
                this.updateProcessingState(false);
            };
            
            // Store current request for cancellation
            this.currentRequest = eventSource;
            
        } catch (error) {
            this.addErrorMessage(`❌ Network error: ${error.message}`);
            this.isProcessing = false;
            this.updateProcessingState(false);
        }
    }
    
    addUserMessage(message) {
        const messageElement = this.createMessageElement('user', message);
        this.appendMessage(messageElement);
    }
    
    addVideoSummaryMessage(data) {
        const videoInfo = data.video_info;
        const summary = data.summary;
        
        // Create video info card
        const videoCard = `
            <div class="video-info-card">
                <div class="video-thumbnail">
                    <img src="${videoInfo.thumbnail}" alt="Video thumbnail" onerror="this.style.display='none'">
                </div>
                <div class="video-details">
                    <h3 class="video-title">${this.escapeHtml(videoInfo.title)}</h3>
                    <p class="video-channel">📺 ${this.escapeHtml(videoInfo.author)}</p>
                </div>
            </div>
            <div class="video-summary">
                <h4>📝 Video Summary</h4>
                <div class="summary-content">${this.formatMarkdown(summary)}</div>
            </div>
            <div class="video-actions">
                <p class="help-text"><i class="fas fa-lightbulb"></i> You can now ask questions about this video! Try asking about specific topics, key points, or request explanations.</p>
            </div>
        `;
        
        const messageElement = this.createMessageElement('ai', videoCard);
        messageElement.classList.add('video-summary-message');
        this.appendMessage(messageElement);
    }
    
    addQAResponseMessage(data) {
        const answer = data.answer;
        const formattedAnswer = this.formatMarkdown(answer);
        
        const messageElement = this.createMessageElement('ai', formattedAnswer);
        messageElement.classList.add('qa-response-message');
        this.appendMessage(messageElement);
    }
    
    addErrorMessage(message) {
        const messageElement = this.createMessageElement('error', message);
        this.appendMessage(messageElement);
    }
    
    createMessageElement(type, content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message-container ${type}-message`;
        
        let avatarIcon;
        let bubbleClass;
        
        switch (type) {
            case 'user':
                avatarIcon = 'fas fa-user';
                bubbleClass = 'user-bubble';
                break;
            case 'ai':
                avatarIcon = 'fab fa-youtube text-danger';
                bubbleClass = 'ai-bubble';
                break;
            case 'error':
                avatarIcon = 'fas fa-exclamation-triangle text-danger';
                bubbleClass = 'error-bubble';
                break;
        }
        
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="${avatarIcon}"></i>
            </div>
            <div class="message-bubble ${bubbleClass}">
                <div class="message-content">${content}</div>
                <div class="message-time">${this.formatTime(new Date())}</div>
            </div>
        `;
        
        return messageDiv;
    }
    
    appendMessage(messageElement) {
        // Remove welcome message if it exists
        const welcomeContainer = this.messagesContainer.querySelector('.welcome-container');
        if (welcomeContainer) {
            welcomeContainer.remove();
        }
        
        this.messagesContainer.appendChild(messageElement);
        this.scrollToBottom();
        
        // Animate message appearance
        requestAnimationFrame(() => {
            messageElement.style.opacity = '0';
            messageElement.style.transform = 'translateY(20px)';
            requestAnimationFrame(() => {
                messageElement.style.transition = 'all 0.3s ease';
                messageElement.style.opacity = '1';
                messageElement.style.transform = 'translateY(0)';
            });
        });
    }
    
    showThinkingProcess(message) {
        // Create unique ID for this thinking process
        const thinkingId = 'thinking-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        
        // Clone the thinking template
        const template = document.getElementById('video-thinking-template');
        if (!template) {
            console.error('Video thinking template not found');
            return this.showThinkingIndicator(message); // Fallback to old method
        }
        
        const thinkingElement = template.cloneNode(true);
        thinkingElement.id = '';
        thinkingElement.classList.remove('hidden');
        thinkingElement.setAttribute('data-message-id', thinkingId);
        
        // Set initial message
        const statusText = thinkingElement.querySelector('.thinking-status-text');
        if (statusText) {
            statusText.textContent = message;
        }
        
        // Add click handler for toggle
        const header = thinkingElement.querySelector('.thinking-header');
        const content = thinkingElement.querySelector('.thinking-content');
        const toggle = thinkingElement.querySelector('.thinking-toggle i');
        
        if (header && content && toggle) {
            header.addEventListener('click', () => {
                const isCollapsed = content.classList.contains('collapsed');
                if (isCollapsed) {
                    content.classList.remove('collapsed');
                    toggle.classList.remove('fa-chevron-down');
                    toggle.classList.add('fa-chevron-up');
                } else {
                    content.classList.add('collapsed');
                    toggle.classList.remove('fa-chevron-up');
                    toggle.classList.add('fa-chevron-down');
                }
            });
        }
        
        // Remove welcome message if it exists
        const welcomeContainer = this.messagesContainer.querySelector('.welcome-container');
        if (welcomeContainer) {
            welcomeContainer.remove();
        }
        
        // Append to messages
        this.messagesContainer.appendChild(thinkingElement);
        this.scrollToBottom();
        
        return thinkingId;
    }
    
    updateThinkingProcess(thinkingId, message, details = '') {
        const thinkingElement = document.querySelector(`[data-message-id="${thinkingId}"]`);
        if (!thinkingElement) return;
        
        // Update status text
        const statusText = thinkingElement.querySelector('.thinking-status-text');
        if (statusText) {
            statusText.textContent = message;
        }
        
        // Update thinking content if details provided
        if (details) {
            const thinkingText = thinkingElement.querySelector('.thinking-text');
            if (thinkingText) {
                thinkingText.innerHTML += `<div class="thinking-step">${this.escapeHtml(details)}</div>`;
            }
        }
        
        this.scrollToBottom();
    }
    
    completeThinkingProcess(thinkingId, finalMessage = 'Complete') {
        const thinkingElement = document.querySelector(`[data-message-id="${thinkingId}"]`);
        if (!thinkingElement) return;
        
        // Update status to complete
        const statusText = thinkingElement.querySelector('.thinking-status-text');
        if (statusText) {
            statusText.textContent = finalMessage;
        }
        
        // Stop spinning icon
        const icon = thinkingElement.querySelector('.thinking-icon i');
        if (icon) {
            icon.classList.remove('fa-spin');
            icon.classList.remove('fa-cog');
            icon.classList.add('fa-check');
        }
        
        // Keep the thinking process visible for user to review
        this.scrollToBottom();
    }
    
    showThinkingIndicator(message) {
        // Create unique ID for this AI message
        const aiMessageId = 'ai-msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        
        const indicator = document.getElementById('video-ai-thinking');
        if (indicator) {
            const messageElement = indicator.querySelector('.thinking-text');
            if (messageElement) {
                messageElement.textContent = message;
            }
            indicator.classList.remove('hidden');
            indicator.setAttribute('data-message-id', aiMessageId);
            this.scrollToBottom();
        }
        
        return aiMessageId;
    }
    
    updateThinkingMessage(message) {
        const indicator = document.getElementById('video-ai-thinking');
        if (indicator && !indicator.classList.contains('hidden')) {
            const messageElement = indicator.querySelector('.thinking-text');
            if (messageElement) {
                messageElement.textContent = message;
            }
        }
    }
    
    hideThinkingIndicator() {
        const indicator = document.getElementById('video-ai-thinking');
        if (indicator) {
            indicator.classList.add('hidden');
        }
    }
    
    createAIMessage(content) {
        // Create unique ID for this AI message
        const aiMessageId = 'ai-msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        
        // Create the AI message element
        const messageElement = this.createMessageElement('ai', content);
        messageElement.setAttribute('data-message-id', aiMessageId);
        this.appendMessage(messageElement);
        
        return aiMessageId;
    }
    
    updateAIMessage(messageId, content, provider, isStreaming = false) {
        console.log('updateAIMessage called:', {messageId, contentLength: content.length, provider, isStreaming});
        
        // Look for existing AI message with this ID first
        let messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        
        // If no existing message found, check if the thinking indicator has this message ID
        if (!messageElement) {
            const thinkingIndicator = document.getElementById('video-ai-thinking');
            if (thinkingIndicator && thinkingIndicator.getAttribute('data-message-id') === messageId) {
                console.log('Replacing thinking indicator with AI message');
                // Hide the thinking indicator first
                this.hideThinkingIndicator();
                
                // Create a new AI message to replace the thinking indicator
                messageElement = this.createMessageElement('ai', content);
                messageElement.setAttribute('data-message-id', messageId);
                this.appendMessage(messageElement);
                
                this.scrollToBottom();
                return;
            }
        }
        
        if (!messageElement) {
            console.log('Creating new AI message');
            // Create new AI message if it doesn't exist
            messageElement = this.createMessageElement('ai', content);
            messageElement.setAttribute('data-message-id', messageId);
            this.appendMessage(messageElement);
        } else {
            console.log('Updating existing AI message');
            // Update existing message content
            const contentDiv = messageElement.querySelector('.message-content');
            if (contentDiv) {
                if (isStreaming) {
                    // For streaming, update content directly for smooth typing effect
                    contentDiv.innerHTML = this.formatMarkdown(content);
                } else {
                    // For final content, format properly
                    contentDiv.innerHTML = this.formatMarkdown(content);
                }
            }
        }
        
        // Add provider info if provided and not streaming
        if (provider && !isStreaming) {
            const providerDiv = messageElement.querySelector('.message-provider');
            if (providerDiv) {
                providerDiv.textContent = provider;
            } else {
                const bubbleDiv = messageElement.querySelector('.message-bubble');
                if (bubbleDiv) {
                    const providerElement = document.createElement('div');
                    providerElement.className = 'message-provider';
                    providerElement.textContent = provider;
                    bubbleDiv.appendChild(providerElement);
                }
            }
        }
        
        this.scrollToBottom();
    }
    
    hideThinkingIndicator() {
        const indicator = document.getElementById('video-ai-thinking');
        if (indicator) {
            indicator.classList.add('hidden');
        }
    }
    
    
    escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
    
    updateProcessingState(isProcessing) {
        this.isProcessing = isProcessing;
        
        if (this.sendBtn) {
            this.sendBtn.style.display = isProcessing ? 'none' : 'flex';
        }
        
        if (this.stopBtn) {
            this.stopBtn.style.display = isProcessing ? 'flex' : 'none';
        }
        
        if (this.chatInput) {
            this.chatInput.disabled = isProcessing;
        }
    }
    
    stopProcessing() {
        // For now, just reset the UI state
        // In a full implementation, you'd cancel the network request
        this.isProcessing = false;
        this.updateProcessingState(false);
        this.hideThinkingIndicator();
    }
    
    async clearChat() {
        try {
            // Clear session on server
            await fetch('/api/video-chat/clear', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: this.sessionId
                })
            });
            
            // Reset local state
            this.currentVideo = null;
            this.chatHistory = [];
            this.sessionId = this.generateSessionId();
            
            // Clear UI
            this.messagesContainer.innerHTML = `
                <div class="welcome-container">
                    <div class="welcome-avatar">
                        <i class="fab fa-youtube text-danger"></i>
                    </div>
                    <div class="welcome-message">
                        <h2>Welcome! 🎥</h2>
                        <p>Send me a YouTube video URL to get an AI-powered summary, then ask questions about the video content!</p>
                        <div class="example-bubble">
                            <span class="example-label">Try:</span>
                            <code>https://www.youtube.com/watch?v=...</code>
                        </div>
                    </div>
                </div>
            `;
            
            console.log('✅ Chat cleared, new session:', this.sessionId);
            
        } catch (error) {
            console.error('Error clearing chat:', error);
        }
    }
    
    scrollToBottom() {
        requestAnimationFrame(() => {
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        });
    }
    
    formatTime(date) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    formatMarkdown(text) {
        if (!text) return '';
        
        // Enhanced markdown formatting
        let formatted = text
            // Headers (h1-h6)
            .replace(/^### (.*$)/gm, '<h3>$1</h3>')
            .replace(/^## (.*$)/gm, '<h2>$1</h2>')
            .replace(/^# (.*$)/gm, '<h1>$1</h1>')
            .replace(/^#### (.*$)/gm, '<h4>$1</h4>')
            .replace(/^##### (.*$)/gm, '<h5>$1</h5>')
            .replace(/^###### (.*$)/gm, '<h6>$1</h6>')
            // Bold
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            // Code blocks (inline)
            .replace(/`(.*?)`/g, '<code>$1</code>')
            // Bullet points (handle nested lists)
            .replace(/^- (.*$)/gm, '<li>$1</li>')
            .replace(/^• (.*$)/gm, '<li>$1</li>')
            .replace(/^\* (.*$)/gm, '<li>$1</li>')
            // Numbered lists
            .replace(/^\d+\. (.*$)/gm, '<li class="numbered">$1</li>');
        
        // Convert double line breaks to paragraph breaks
        formatted = formatted.replace(/\n\n/g, '</p><p>');
        
        // Handle lists properly
        if (formatted.includes('<li>')) {
            // Regular bullet lists
            formatted = formatted.replace(/(<li>(?!class="numbered").*?<\/li>(\s*<li>(?!class="numbered").*?<\/li>)*)/gs, '<ul>$1</ul>');
            // Numbered lists
            formatted = formatted.replace(/(<li class="numbered">.*?<\/li>(\s*<li class="numbered">.*?<\/li>)*)/gs, '<ol>$1</ol>');
            // Clean up class attributes
            formatted = formatted.replace(/class="numbered"/g, '');
        }
        
        // Convert remaining single line breaks to <br>
        formatted = formatted.replace(/\n/g, '<br>');
        
        // Wrap in paragraphs if not already wrapped
        if (!formatted.match(/^<[h1-6]|<ul|<ol|<p>/)) {
            formatted = '<p>' + formatted + '</p>';
        }
        
        // Clean up empty paragraphs
        formatted = formatted.replace(/<p><\/p>/g, '');
        formatted = formatted.replace(/<p><br><\/p>/g, '');
        
        return formatted;
    }
    
    // Update language elements when language changes
    updateLanguageElements(lang) {
        // Update all elements with data-en and data-ar attributes
        document.querySelectorAll('[data-en][data-ar]').forEach(element => {
            const text = element.getAttribute(`data-${lang}`);
            if (text) {
                element.textContent = text;
            }
        });
        
        // Update placeholder text for inputs
        document.querySelectorAll('input[data-en][data-ar], textarea[data-en][data-ar]').forEach(input => {
            const placeholder = input.getAttribute(`data-${lang}`);
            if (placeholder) {
                input.placeholder = placeholder;
            }
        });
        
        // Update select options
        document.querySelectorAll('option[data-en][data-ar]').forEach(option => {
            const text = option.getAttribute(`data-${lang}`);
            if (text) {
                option.textContent = text;
            }
        });
        
        console.log(`🌐 Video Chat: Updated language elements to ${lang}`);
    }
    
    // Initialize language on load
    initializeLanguage() {
        // Wait a bit to ensure other language systems are ready
        setTimeout(() => {
            // Get current language from multiple sources
            const savedLang = localStorage.getItem('preferred-language') || 
                            localStorage.getItem('preferred_language');
            const docLang = document.documentElement.getAttribute('lang');
            const dirAttr = document.documentElement.getAttribute('dir');
            const currentLang = savedLang || docLang || (dirAttr === 'rtl' ? 'ar' : 'en');
            
            // Apply language elements
            this.updateLanguageElements(currentLang);
            
            console.log(`🌐 Video Chat: Initialized with language ${currentLang} (saved: ${savedLang}, doc: ${docLang}, dir: ${dirAttr})`);
        }, 100);
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('video-chat-section')) {
        window.VideoChat = VideoChat;
        window.videoChat = new VideoChat();
        console.log('✅ Video Chat interface initialized');
    }
});