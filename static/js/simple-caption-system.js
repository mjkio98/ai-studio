/**
 * Simple Caption System for Client-Side Video Processing
 * 
 * A clean, straightforward implementation that:
 * - Uses FFmpeg drawtext filters for caption burning
 * - Matches server-side caption positioning and styling EXACTLY
 * - Handles word-by-word caption timing
 * - Never breaks video processing (captions are optional)
 * 
 * POSITIONING:
 * - Horizontal: x=(w-text_w)/2 (perfectly centered)
 * - Vertical: y=h-640 (TRUE CENTER on 1280px video = middle of screen)
 * 
 * STYLING:
 * - Normal words: 32px white, black box @0.9 opacity
 * - Hook words: 36px cyan, black box @0.8 opacity
 * 
 * Usage:
 *   const captionSystem = new SimpleCaptionSystem();
 *   const filter = captionSystem.createCaptionFilter(segments, videoWidth, videoHeight);
 *   // Use filter in FFmpeg command
 */

class SimpleCaptionSystem {
    constructor(options = {}) {
        this.options = {
            // Position from bottom (in pixels) - for TRUE CENTERING on 1280px video
            // Use 640 (h/2) for perfect center, or 400-500 for lower-center
            marginBottom: options.marginBottom || 640,  // TRUE CENTER (h/2 on 1280px video)
            
            // Font sizes - OPTIMIZED FOR MOBILE/SHORTS (larger than server for readability)
            // Server uses 32/36, but mobile shorts need bigger text for engagement
            normalFontSize: options.normalFontSize || 64,  // Large for mobile visibility
            hookFontSize: options.hookFontSize || 72,      // Extra large for hooks
            
            // Colors - matches server exactly
            normalColor: options.normalColor || 'white',   // Server: white
            hookColor: options.hookColor || 'cyan',        // Server: cyan
            
            // Box styling - matches server exactly
            normalBoxColor: options.normalBoxColor || 'black@0.9',  // Server: black@0.9
            hookBoxColor: options.hookBoxColor || 'black@0.8',      // Server: black@0.8
            normalBoxBorder: options.normalBoxBorder || 8,          // Server: 8
            hookBoxBorder: options.hookBoxBorder || 10,             // Server: 10
            
            // Limits to prevent FFmpeg filter overflow
            maxWords: options.maxWords || 20,  // Same as server
            
            // Hook word detection - MATCHES SERVER EXACTLY
            hookWords: options.hookWords || [
                // Attention grabbers
                'shocking', 'amazing', 'incredible', 'unbelievable', 'mind-blowing',
                'wow', 'omg', 'whoa', 'insane', 'crazy', 'wild', 'stunning',
                
                // Numbers and statistics
                'million', 'billion', 'thousand', 'percent', 'times', 'years',
                
                // Emotional words
                'love', 'hate', 'fear', 'angry', 'excited', 'surprised', 'shocked',
                'happy', 'sad', 'terrified', 'devastated', 'thrilled',
                
                // Superlatives
                'best', 'worst', 'biggest', 'smallest', 'fastest', 'slowest',
                'first', 'last', 'only', 'never', 'always', 'most', 'least',
                
                // Action words
                'revealed', 'exposed', 'discovered', 'found', 'caught', 'busted',
                'failed', 'succeeded', 'won', 'lost', 'died', 'born', 'created',
                
                // Mystery/intrigue
                'secret', 'hidden', 'mystery', 'unknown', 'conspiracy', 'truth',
                'lie', 'fake', 'real', 'hoax', 'scam', 'exposed',
                
                // Money/success
                'money', 'rich', 'poor', 'millionaire', 'billionaire', 'broke',
                'success', 'failure', 'profit', 'loss', 'expensive', 'cheap'
            ]
        };
    }

    /**
     * Create FFmpeg drawtext filter for captions
     * @param {Array} segments - Caption segments with {text, start, end, isHook}
     * @param {number} videoWidth - Video width in pixels
     * @param {number} videoHeight - Video height in pixels
     * @returns {string|null} FFmpeg filter string or null if no captions
     */
    createCaptionFilter(segments, videoWidth, videoHeight) {
        if (!segments || segments.length === 0) {
            console.log('📝 No caption segments provided');
            return null;
        }

        console.log(`📝 Creating caption filter for ${segments.length} segments...`);

        // Build drawtext filters for each segment
        const filters = [];
        
        for (let i = 0; i < segments.length; i++) {
            const segment = segments[i];
            
            if (!segment || !segment.text) {
                continue;
            }

            // Clean text for FFmpeg
            let cleanText = segment.text.trim();
            
            if (!cleanText) {
                continue;
            }

            // Detect if this is a hook word - matches server logic
            const isHook = segment.isHook || this._isHookWord(cleanText, i, segments.length);
            
            // Apply styling based on hook status - EXACTLY like server
            const fontSize = isHook ? this.options.hookFontSize : this.options.normalFontSize;
            const fontColor = isHook ? this.options.hookColor : this.options.normalColor;
            const boxColor = isHook ? this.options.hookBoxColor : this.options.normalBoxColor;
            const boxBorder = isHook ? this.options.hookBoxBorder : this.options.normalBoxBorder;
            
            // DEBUG: Log the actual values being used
            if (i < 3 || isHook) {  // Log first 3 words and all hooks
                console.log(`🎨 Word "${cleanText}": isHook=${isHook}, fontSize=${fontSize}, fontColor=${fontColor}, boxColor=${boxColor}, boxBorder=${boxBorder}`);
            }
            
            // Format timing
            const startTime = parseFloat(segment.start || 0).toFixed(2);
            const endTime = parseFloat(segment.end || (parseFloat(startTime) + 0.5)).toFixed(2);
            
            // Escape text for FFmpeg
            const escapedText = this._escapeForFFmpeg(cleanText);
            
            // Create filter with TRUE CENTERED positioning:
            // - x=(w-text_w)/2 : horizontally centered
            // - y=h-640 : vertically centered (h/2 on 1280px = 640px = true center)
            const filter = `drawtext=fontfile=font.ttf:text='${escapedText}'` +
                `:fontcolor=${fontColor}` +
                `:fontsize=${fontSize}` +
                `:box=1:boxcolor=${boxColor}:boxborderw=${boxBorder}` +
                `:x=(w-text_w)/2` +  // Horizontally centered
                `:y=h-${this.options.marginBottom}` +  // Vertically centered (TRUE CENTER)
                `:enable='between(t,${startTime},${endTime})'`;  // Show only during time range
            
            filters.push(filter);
            
            // Log with hook indicator and first few filters
            const hookIndicator = isHook ? ' 🎯 HOOK' : '';
            console.log(`  Word ${i+1}: "${cleanText.substring(0, 50)}" ${startTime}s-${endTime}s${hookIndicator}`);
            
            // DEBUG: Show first filter completely
            if (i === 0) {
                console.log(`📝 FIRST FILTER EXAMPLE:\n${filter}`);
            }
        }

        if (filters.length === 0) {
            console.log('📝 No valid caption filters created');
            return null;
        }

        // Join filters with comma for FFmpeg -vf parameter
        const filterString = filters.join(',');
        
        console.log(`✅ Created ${filters.length} caption filters (${filterString.length} chars)`);
        
        return filterString;
    }

    /**
     * Wrap text into array of lines based on estimated pixel width
     * @private
     */
    _wrapTextIntoLines(text, fontSize, maxWidth) {
        // Average character width at 32px font is ~20px (varies by letter)
        const avgCharWidth = fontSize * 0.625;  // Rough estimate: 32px font = ~20px per char
        
        const words = text.split(' ');
        const lines = [];
        let currentLine = '';

        for (const word of words) {
            const testLine = currentLine ? `${currentLine} ${word}` : word;
            const estimatedWidth = testLine.length * avgCharWidth;
            
            if (estimatedWidth <= maxWidth) {
                currentLine = testLine;
            } else {
                if (currentLine) {
                    lines.push(currentLine);
                }
                currentLine = word;
            }
        }
        
        if (currentLine) {
            lines.push(currentLine);
        }

        // Limit to 3 lines maximum to avoid going off screen
        return lines.slice(0, 3);
    }

    /**
     * Escape text for FFmpeg drawtext filter
     * FFmpeg drawtext has special escaping rules - we need to escape special chars properly
     * @private
     */
    _escapeForFFmpeg(text) {
        return text
            .replace(/\\/g, '\\\\\\\\')   // Escape backslashes - need 4 backslashes for FFmpeg
            .replace(/'/g, "'\\\\\\''")    // Escape single quotes for shell-style quoting
            .replace(/:/g, '\\:')          // Escape colons (FFmpeg parameter separator)
            .replace(/\n/g, ' ')           // Replace newlines with spaces
            .replace(/\r/g, '')            // Remove carriage returns
            .trim();
    }

    /**
     * Wrap long text to fit within video width (720px portrait)
     * For 720px width at 32px font, we can fit ~25-28 chars safely
     * @private
     */
    _wrapText(text, maxCharsPerLine = 25) {
        const words = text.split(' ');
        const lines = [];
        let currentLine = '';

        for (const word of words) {
            const testLine = currentLine ? `${currentLine} ${word}` : word;
            
            if (testLine.length <= maxCharsPerLine) {
                currentLine = testLine;
            } else {
                if (currentLine) {
                    lines.push(currentLine);
                }
                currentLine = word;
            }
        }
        
        if (currentLine) {
            lines.push(currentLine);
        }

        // Limit to 2 lines maximum to avoid going off screen
        return lines.slice(0, 2).join('\\n');
    }

    /**
     * Check if a word should be highlighted as a hook
     * Matches server-side logic exactly
     * @private
     */
    _isHookWord(word, index, totalWords) {
        const cleanWord = word.replace(/[.,!?;:'"]/g, '');
        const lowerWord = cleanWord.toLowerCase();
        
        // First 2-3 words are often hooks for engagement (matches server)
        if (index === 0 && totalWords > 3) {
            return true;
        }
        
        if (index === 1 && totalWords > 5) {
            return true;
        }
        
        // Last word can be a hook
        if (index === totalWords - 1 && totalWords > 3) {
            return true;
        }
        
        // Check if word contains digits (numbers are engaging) - MATCHES SERVER
        if (/\d/.test(word)) {
            return true;
        }
        
        // Check if word has emphasis punctuation - MATCHES SERVER
        if (word.endsWith('!') || word.endsWith('?')) {
            return true;
        }
        
        // Check against hook word list (matches server)
        const isInHookList = this.options.hookWords.some(hookWord => 
            lowerWord === hookWord.toLowerCase()
        );
        
        if (isInHookList) {
            return true;
        }
        
        // Check if it's a long impactful word (6+ characters, not common) - MATCHES SERVER
        if (lowerWord.length >= 6) {
            const commonLongWords = new Set([
                'because', 'through', 'without', 'between', 'something', 'anything'
            ]);
            if (!commonLongWords.has(lowerWord)) {
                return true;
            }
        }
        
        return false;
    }

    /**
     * Process transcript into word-by-word segments
     * @param {Array} transcript - Transcript segments with {text, start, end}
     * @param {number} clipStart - Clip start time in seconds
     * @param {number} clipEnd - Clip end time in seconds
     * @returns {Array} Word segments for the clip
     */
    processTranscript(transcript, clipStart, clipEnd, actualVideoStart = null) {
        if (!transcript || transcript.length === 0) {
            return [];
        }

        // If actualVideoStart is provided, use it instead of clipStart for timing calculations
        // This handles cases where FFmpeg seeks to nearest keyframe (e.g., requested 420s but got 417s)
        const effectiveStart = actualVideoStart !== null ? actualVideoStart : clipStart;
        
        console.log(`📝 Processing transcript for clip ${clipStart}s-${clipEnd}s...`);
        console.log(`⏱️  Clip duration: ${(clipEnd - clipStart).toFixed(2)}s`);
        if (actualVideoStart !== null && actualVideoStart !== clipStart) {
            console.log(`⚠️  Video actually starts at ${actualVideoStart}s (${(clipStart - actualVideoStart).toFixed(2)}s before requested)`);
        }

        const captionSegments = [];

        // Find segments that overlap with this clip
        for (const segment of transcript) {
            const segStart = parseFloat(segment.start);
            const segEnd = parseFloat(segment.end);

            // Skip if segment is outside clip range (use effectiveStart for actual video content)
            if (segEnd < effectiveStart || segStart > clipEnd) {
                continue;
            }

            // Adjust times relative to the ACTUAL video start (not requested start)
            const relativeStart = Math.max(0, segStart - effectiveStart);
            const relativeEnd = segEnd - effectiveStart;
            const clipDuration = clipEnd - clipStart;

            // Include caption if it STARTS within the clip duration
            // Keep full end time so complete text shows (even if it extends slightly beyond clip)
            // But skip captions that start after the clip ends
            if (relativeStart < clipDuration && relativeEnd > relativeStart && segment.text.trim().length > 0) {
                captionSegments.push({
                    text: segment.text.trim(),
                    start: relativeStart,
                    end: relativeEnd,  // Keep original end time for full caption display
                    isHook: false  // Can be enhanced later
                });

                // Debug first few segments
                if (captionSegments.length <= 3) {
                    console.log(`  📍 Segment ${captionSegments.length}:`);
                    console.log(`     Text: "${segment.text.substring(0, 40)}..."`);
                    console.log(`     Absolute: ${segStart.toFixed(2)}s-${segEnd.toFixed(2)}s (${(segEnd-segStart).toFixed(2)}s duration)`);
                    console.log(`     Relative: ${relativeStart.toFixed(2)}s-${relativeEnd.toFixed(2)}s (${(relativeEnd-relativeStart).toFixed(2)}s duration)`);
                }
            }
        }

        console.log(`✅ Created ${captionSegments.length} caption segments for clip`);

        return captionSegments;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SimpleCaptionSystem;
}
