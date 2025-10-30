/**
 * Client-Side Caption Renderer
 * Renders timestamped captions onto video frames using Canvas API
 */

class ClientCaptionRenderer {
    constructor() {
        this.captionStyle = {
            fontFamily: 'Arial Black, Arial, sans-serif',
            fontSize: 72,  // Much larger for TikTok/Shorts style
            fontSizeHook: 84,  // Hook words extra large
            fontWeight: '900', // Extra bold
            textColor: '#FFFFFF',  // White
            strokeColor: '#000000',  // Black
            strokeWidth: 8,  // Thick outline for readability
            strokeWidthHook: 10,  // Even thicker for hook words
            backgroundColor: 'rgba(0, 0, 0, 0.7)', // Semi-transparent black
            backgroundColorHook: 'rgba(0, 0, 0, 0.65)', // Slightly more transparent for hooks
            padding: 24,  // More padding for large text
            maxWidth: 650,
            position: 'center',  // Center of screen
            marginBottom: 400, // Position closer to center (400px from bottom = ~middle-lower)
            highlightColor: '#FFFF00', // Yellow for hook words (high visibility)
            displayMode: 'word-by-word'
        };
    }

    /**
     * Get caption segments for a specific time range with word-by-word timing
     * @param {Array} allCaptions - Full timestamped transcript
     * @param {number} clipStart - Start time in original video
     * @param {number} clipEnd - End time in original video
     * @returns {Array} Word-by-word caption events
     */
    getCaptionSegments(allCaptions, clipStart, clipEnd) {
        if (!allCaptions || !Array.isArray(allCaptions)) {
            console.warn('⚠️ No captions provided');
            return [];
        }

        const wordEvents = [];
        
        console.log(`🔍 Looking for captions between ${clipStart}s-${clipEnd}s`);
        console.log(`📊 Available caption time ranges:`);
        
        // Show first few and last few captions to understand the time range
        for (let i = 0; i < Math.min(3, allCaptions.length); i++) {
            const cap = allCaptions[i];
            console.log(`   Caption ${i}: "${cap.text?.substring(0, 30)}..." (${cap.start}s-${cap.start + cap.duration}s)`);
        }
        console.log(`   ... ${allCaptions.length - 6} more captions ...`);
        for (let i = Math.max(allCaptions.length - 3, 3); i < allCaptions.length; i++) {
            const cap = allCaptions[i];
            console.log(`   Caption ${i}: "${cap.text?.substring(0, 30)}..." (${cap.start}s-${cap.start + cap.duration}s)`);
        }

        for (const caption of allCaptions) {
            const segStart = caption.start || 0;
            const segDuration = caption.duration || 2;
            const segEnd = segStart + segDuration;

            // Check if segment overlaps with clip timeframe
            if (segEnd > clipStart && segStart < clipEnd) {
                console.log(`✅ FOUND MATCH: "${caption.text?.substring(0, 50)}..." (${segStart}s-${segEnd}s) overlaps with ${clipStart}s-${clipEnd}s`);
                console.log(`📊 Segment duration: ${segDuration}s - ${segDuration > 120 ? 'LARGE SEGMENT (will extract portion)' : 'NORMAL SEGMENT (will use full text)'}`);
                
                const text = (caption.text || '').trim();
                if (!text) continue;

                // Handle large segments (like YouTube auto-captions with full transcript)
                if (segDuration > 120) { // Large segment (> 2 minutes) likely contains entire transcript
                    console.log(`📝 Processing large caption segment (${segDuration}s) for clip ${clipStart}s-${clipEnd}s`);
                    console.log(`💡 Extracting real transcript text for time range ${clipStart}s-${clipEnd}s`);
                    console.log(`📖 Full transcript sample: "${text.substring(0, 300)}..."`);
                    console.log(`📖 Full transcript length: ${text.length} characters`);
                    
                    // Calculate which portion of the transcript corresponds to our clip
                    const clipDuration = clipEnd - clipStart;
                    
                    // Calculate relative position within the full transcript
                    const relativeStart = (clipStart - segStart) / segDuration; // 0.0 to 1.0
                    const relativeEnd = (clipEnd - segStart) / segDuration;     // 0.0 to 1.0
                    
                    // Extract the corresponding portion of text
                    const totalChars = text.length;
                    const startCharIndex = Math.floor(totalChars * Math.max(0, relativeStart));
                    const endCharIndex = Math.floor(totalChars * Math.min(1, relativeEnd));
                    
                    // Get the text slice for this time range
                    let clipText = text.slice(startCharIndex, endCharIndex).trim();
                    
                    // Clean up the text - ensure we have complete words
                    const textWords = clipText.split(/\s+/).filter(w => w.length > 0);
                    if (textWords.length > 2) {
                        // Remove first and last word if they seem incomplete
                        if (textWords[0].length < 3) textWords.shift();
                        if (textWords[textWords.length - 1].length < 3) textWords.pop();
                        clipText = textWords.join(' ');
                    }
                    
                    console.log(`📝 Extracted text portion: "${clipText.substring(0, 200)}..."`);
                    console.log(`📊 Character range: ${startCharIndex}-${endCharIndex} (${clipText.length} chars from ${totalChars} total)`);
                    console.log(`📊 Timing calculation: clipStart=${clipStart}s, segStart=${segStart}s, segDuration=${segDuration}s`);
                    console.log(`📊 Relative positions: start=${relativeStart.toFixed(3)}, end=${relativeEnd.toFixed(3)}`);
                    
                    if (clipText.length === 0) {
                        console.log(`⚠️  No valid text extracted for this time range`);
                        continue;
                    }
                    
                    // Split the extracted text into words
                    const clipWords = clipText.split(/\s+/).filter(w => w.length > 0);
                    
                    if (clipWords.length === 0) {
                        console.log(`⚠️  No words found in extracted text`);
                        continue;
                    }
                    
                    console.log(`📝 Found ${clipWords.length} words in real transcript for this time range`);
                    console.log(`📝 First few words: "${clipWords.slice(0, 8).join(' ')}"`);
                    
                    // Calculate smart word timings for the clip duration
                    const wordTimings = this.calculateSmartWordTimings(clipWords, clipDuration);
                    
                    // Create word-by-word events starting from clip time 0
                    let currentTime = 0;
                    
                    clipWords.forEach((word, index) => {
                        const duration = wordTimings[index];
                        const wordStart = currentTime;
                        const wordEnd = Math.min(currentTime + duration, clipDuration);
                        
                        if (wordEnd > wordStart && wordStart >= 0) {
                            const cleanWord = this.cleanWordForDisplay(word);
                            const isHook = this.isHookWord(cleanWord, index, clipWords.length);
                            
                            wordEvents.push({
                                start: wordStart,
                                end: wordEnd,
                                duration: wordEnd - wordStart,
                                text: cleanWord,
                                isHook: isHook
                            });
                        }
                        
                        currentTime = wordEnd;
                    });
                    
                    console.log(`✅ Created ${wordEvents.length} caption events from real transcript`);
                    
                } else {
                    // Handle normal-sized segments (properly timestamped captions)
                    console.log(`📝 Processing NORMAL segment: "${text.substring(0, 100)}..."`);
                    console.log(`📊 Segment: ${segStart}s-${segEnd}s, Clip: ${clipStart}s-${clipEnd}s`);
                    
                    const words = text.split(/\s+/).filter(w => w.length > 0);
                    if (words.length === 0) continue;
                    
                    console.log(`📝 Found ${words.length} words in this segment: "${words.slice(0, 10).join(' ')}..."`);

                    // Calculate smart word timings
                    const wordTimings = this.calculateSmartWordTimings(words, segDuration);
                    
                    // Adjust timing relative to clip start
                    const relativeStart = segStart - clipStart;
                    console.log(`⏰ Timing calculation: relativeStart = ${relativeStart}s (segStart=${segStart}s - clipStart=${clipStart}s)`);
                    
                    // Skip segments that start before the clip (they would overlap incorrectly)
                    if (relativeStart < 0) {
                        console.log(`⚠️  SKIPPING segment that starts before clip (${relativeStart}s < 0)`);
                        continue;
                    }
                    
                    // Create word-by-word events
                    let currentTime = relativeStart;
                    
                    words.forEach((word, index) => {
                        const duration = wordTimings[index];
                        const wordStart = currentTime;
                        const wordEnd = Math.min(currentTime + duration, clipEnd - clipStart);
                        
                        if (wordEnd > wordStart && wordStart >= 0) {
                            const cleanWord = this.cleanWordForDisplay(word);
                            const isHook = this.isHookWord(cleanWord, index, words.length);
                            
                            wordEvents.push({
                                start: wordStart,
                                end: wordEnd,
                                duration: wordEnd - wordStart,
                                text: cleanWord,
                                isHook: isHook
                            });
                        }
                        
                        currentTime = wordEnd;
                    });
                }
            }
        }

        console.log(`📋 Found ${wordEvents.length} word events for this clip`);
        return wordEvents;
    }

    /**
     * Calculate smart word timings based on word characteristics
     * (Matches server-side logic)
     */
    calculateSmartWordTimings(words, totalDuration) {
        if (!words || words.length === 0) return [];
        
        const weights = [];
        const commonWords = new Set([
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have',
            'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'
        ]);
        
        const emphasisWords = new Set([
            'amazing', 'incredible', 'shocking', 'unbelievable', 'fantastic',
            'wow', 'never', 'always', 'everything', 'nothing', 'everyone',
            'important', 'crucial', 'essential', 'perfect', 'terrible'
        ]);
        
        // Calculate weight for each word
        words.forEach(word => {
            let weight = 1.0;
            
            // Length factor
            const lengthFactor = word.length / 5.0;
            weight *= (0.7 + lengthFactor * 0.6);
            
            // Syllable factor (approximate by vowel count)
            const vowels = (word.match(/[aeiouAEIOU]/g) || []).length;
            const syllables = Math.max(1, vowels);
            weight *= (0.8 + syllables * 0.15);
            
            // Punctuation pauses
            if (/[.!?;]$/.test(word)) {
                weight *= 1.4; // Longer pause
            } else if (/[,:]$/.test(word)) {
                weight *= 1.2; // Shorter pause
            }
            
            // Common words spoken faster
            const cleanWord = word.toLowerCase().replace(/[.,!?;:]/g, '');
            if (commonWords.has(cleanWord)) {
                weight *= 0.7;
            }
            
            // Emphasis words spoken slower
            if (emphasisWords.has(cleanWord)) {
                weight *= 1.3;
            }
            
            // Numbers spoken more deliberately
            if (/\d/.test(word)) {
                weight *= 1.2;
            }
            
            weights.push(weight);
        });
        
        // Normalize weights to fit total duration
        const totalWeight = weights.reduce((sum, w) => sum + w, 0);
        const minDuration = 0.15; // Minimum 150ms per word
        const maxDuration = 2.0;   // Maximum 2s per word
        
        return weights.map(weight => {
            const duration = (weight / totalWeight) * totalDuration;
            return Math.max(minDuration, Math.min(maxDuration, duration));
        });
    }

    /**
     * Clean word for display
     */
    cleanWordForDisplay(word) {
        // Remove excessive punctuation but keep end punctuation
        return word.replace(/^[.,!?;:]+/, '').trim();
    }

    /**
     * Check if word is a "hook" word (should be highlighted)
     */
    isHookWord(word, index, totalWords) {
        const cleanWord = word.toLowerCase().replace(/[.,!?;:]/g, '');
        
        // Hook words that should stand out
        const hookWords = new Set([
            'amazing', 'incredible', 'shocking', 'unbelievable', 'wow',
            'never', 'always', 'perfect', 'terrible', 'insane',
            'crazy', 'mindblowing', 'secret', 'revealed', 'truth'
        ]);
        
        // First word is often a hook
        if (index === 0 && totalWords > 3) return true;
        
        // Last word can be a hook
        if (index === totalWords - 1 && totalWords > 3) return true;
        
        // Check if it's in hook words list
        return hookWords.has(cleanWord);
    }

    /**
     * Get active word at current time (word-by-word display)
     * @param {Array} wordEvents - Word-by-word caption events
     * @param {number} currentTime - Current playback time (relative to clip start)
     * @returns {Object|null} Active word event or null
     */
    getActiveCaption(wordEvents, currentTime) {
        for (const event of wordEvents) {
            if (currentTime >= event.start && currentTime < event.end) {
                return event;
            }
        }
        return null;
    }

    /**
     * Split text into words for word-by-word highlighting
     * @param {string} text - Text to split
     * @returns {Array} Array of words
     */
    splitIntoWords(text) {
        if (!text) return [];
        return text.split(/\s+/).filter(word => word.length > 0);
    }

    /**
     * Calculate which word should be highlighted based on time
     * @param {Object} segment - Caption segment
     * @param {number} currentTime - Current time in clip
     * @returns {number} Index of word to highlight (-1 if none)
     */
    getCurrentWordIndex(segment, currentTime) {
        if (!this.captionStyle.wordHighlight) return -1;
        
        const timeInSegment = currentTime - segment.start;
        const words = this.splitIntoWords(segment.text);
        
        if (words.length === 0) return -1;
        
        const timePerWord = segment.duration / words.length;
        const wordIndex = Math.floor(timeInSegment / timePerWord);
        
        return Math.min(wordIndex, words.length - 1);
    }

    /**
     * Wrap text to fit within max width
     * @param {CanvasRenderingContext2D} ctx - Canvas context
     * @param {string} text - Text to wrap
     * @param {number} maxWidth - Maximum width in pixels
     * @returns {Array} Array of text lines
     */
    wrapText(ctx, text, maxWidth) {
        const words = text.split(' ');
        const lines = [];
        let currentLine = '';

        for (const word of words) {
            const testLine = currentLine + (currentLine ? ' ' : '') + word;
            const metrics = ctx.measureText(testLine);

            if (metrics.width > maxWidth && currentLine) {
                lines.push(currentLine);
                currentLine = word;
            } else {
                currentLine = testLine;
            }
        }

        if (currentLine) {
            lines.push(currentLine);
        }

        return lines;
    }

    /**
     * Draw single word caption on canvas (word-by-word like server)
     * @param {CanvasRenderingContext2D} ctx - Canvas context
     * @param {Object} wordEvent - Single word event with timing
     * @param {number} currentTime - Current time
     * @param {number} canvasWidth - Canvas width
     * @param {number} canvasHeight - Canvas height
     */
    drawCaption(ctx, wordEvent, currentTime, canvasWidth, canvasHeight) {
        if (!wordEvent || !wordEvent.text) {
            return;
        }

        const style = this.captionStyle;
        const word = wordEvent.text;
        const isHook = wordEvent.isHook;

        // Use larger sizes for better mobile visibility
        const fontSize = isHook ? style.fontSizeHook : style.fontSize;
        const textColor = isHook ? style.highlightColor : style.textColor;
        const strokeWidth = isHook ? style.strokeWidthHook : style.strokeWidth;
        const bgColor = isHook ? style.backgroundColorHook : style.backgroundColor;

        // Set font
        ctx.font = `${style.fontWeight} ${fontSize}px ${style.fontFamily}`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';  // Center text vertically in box

        // Position: centered horizontally, in lower third of screen
        const x = canvasWidth / 2;
        const y = canvasHeight - style.marginBottom;

        // Measure text
        const metrics = ctx.measureText(word);
        const textWidth = metrics.width;
        const textHeight = fontSize * 1.3;  // Approximate height

        // Draw background box with padding
        const padding = style.padding;
        const boxX = x - textWidth / 2 - padding;
        const boxY = y - textHeight / 2 - padding;
        const boxWidth = textWidth + padding * 2;
        const boxHeight = textHeight + padding * 2;

        // Draw box with rounded corners for modern look
        ctx.fillStyle = bgColor;
        this.roundRect(ctx, boxX, boxY, boxWidth, boxHeight, 8);
        ctx.fill();

        // Draw text stroke (outline) for readability
        ctx.strokeStyle = style.strokeColor;
        ctx.lineWidth = strokeWidth;
        ctx.lineJoin = 'round';
        ctx.miterLimit = 2;
        ctx.strokeText(word, x, y);

        // Draw text fill
        ctx.fillStyle = textColor;
        ctx.fillText(word, x, y);
    }

    /**
     * Draw rounded rectangle (for modern caption boxes)
     */
    roundRect(ctx, x, y, width, height, radius) {
        ctx.beginPath();
        ctx.moveTo(x + radius, y);
        ctx.lineTo(x + width - radius, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
        ctx.lineTo(x + width, y + height - radius);
        ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
        ctx.lineTo(x + radius, y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
        ctx.lineTo(x, y + radius);
        ctx.quadraticCurveTo(x, y, x + radius, y);
        ctx.closePath();
    }

    /**
     * Update caption style
     * @param {Object} newStyle - Style options to update
     */
    updateStyle(newStyle) {
        this.captionStyle = { ...this.captionStyle, ...newStyle };
    }
}

// Make available globally
if (typeof window !== 'undefined') {
    window.ClientCaptionRenderer = ClientCaptionRenderer;
}
