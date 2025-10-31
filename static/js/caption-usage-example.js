/**
 * Example: How to use the improved caption system
 * This demonstrates the memory-efficient caption processing
 */

// Example usage of the updated caption system
async function demonstrateCaptionUsage() {
    console.log('📝 Caption System Demo - Memory Optimized');
    
    // Initialize the video processor (this should already be done)
    if (!clientVideoProcessor.ffmpegLoaded) {
        console.log('⚡ Initializing FFmpeg.wasm...');
        await clientVideoProcessor.initialize();
    }
    
    // Test caption capabilities
    console.log('🧪 Testing caption capabilities...');
    const capabilities = await clientVideoProcessor.testCaptionCapabilities();
    console.log('📊 Capabilities:', capabilities);
    
    // Configure caption settings for memory efficiency
    clientVideoProcessor.configureCaptions({
        enabled: true,
        burnInCaptions: true,
        useCanvas: false,           // Disabled to prevent OOM
        useFallback: false,
        style: 'tiktok',
        maxCaptionsPerBatch: 10,    // Smaller batches for safety
        maxTotalCaptions: 30,       // Reduced from 60
        maxVideoDuration: 45        // Reduced from 60
    });
    
    // Example caption data (what you'd get from YouTube transcript)
    const sampleCaptions = [
        { start: 0, duration: 1.5, text: 'Hello everyone' },
        { start: 1.5, duration: 1.2, text: 'welcome to this' },
        { start: 2.7, duration: 1.8, text: 'amazing tutorial' },
        { start: 4.5, duration: 1.5, text: 'about video processing' },
        { start: 6, duration: 2.0, text: 'with captions!' }
    ];
    
    // Check if this workload is feasible
    const mockSegments = clientVideoProcessor.captionRenderer ? 
        clientVideoProcessor.captionRenderer.getCaptionSegments(sampleCaptions, 0, 8) : [];
    
    const feasibility = clientVideoProcessor.checkCaptionFeasibility(mockSegments, 8);
    console.log('📋 Feasibility check:', feasibility);
    
    if (!feasibility.feasible) {
        console.warn('⚠️  Caption processing not recommended:', feasibility.issues);
        console.log('💡 Recommendation:', feasibility.recommendation);
        return;
    }
    
    console.log('✅ Caption system is ready and optimized for memory efficiency');
    console.log('🎯 Key improvements:');
    console.log('   • Batch processing to prevent OOM errors');
    console.log('   • Memory limits and feasibility checks');
    console.log('   • Efficient drawtext filters instead of PNG overlays');
    console.log('   • Configurable limits for different scenarios');
    
    return {
        ready: true,
        memoryOptimized: true,
        capabilities: capabilities,
        settings: clientVideoProcessor.captionSettings
    };
}

// Example of processing a video clip with captions
async function processVideoWithCaptions(clipData, videoUrl, captions) {
    console.log('🎬 Processing video with memory-optimized captions...');
    
    try {
        // The processClip method will now use the optimized caption system
        const processedVideo = await clientVideoProcessor.processClip(
            clipData, 
            videoUrl, 
            captions,
            (progress, message) => {
                console.log(`📊 Progress: ${progress.toFixed(1)}% - ${message}`);
            }
        );
        
        console.log('✅ Video processed with captions successfully');
        return processedVideo;
        
    } catch (error) {
        if (error.message && error.message.includes('OOM')) {
            console.error('💥 Out of Memory Error - Try these solutions:');
            console.log('   • Reduce video duration (current limit: 45s)');
            console.log('   • Reduce caption count (current limit: 30)');
            console.log('   • Use fallback mode: configureCaptions({useFallback: true})');
        } else {
            console.error('❌ Video processing error:', error);
        }
        throw error;
    }
}

// Export for use in other modules
if (typeof window !== 'undefined') {
    window.demonstrateCaptionUsage = demonstrateCaptionUsage;
    window.processVideoWithCaptions = processVideoWithCaptions;
}

// Auto-run demo if this script is loaded directly
if (typeof window !== 'undefined' && window.clientVideoProcessor) {
    console.log('🚀 Caption system example loaded. Run demonstrateCaptionUsage() to test.');
}