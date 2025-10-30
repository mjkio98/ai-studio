/**
 * Caption Testing Script
 * 
 * This script helps test and debug caption functionality.
 * Run in browser console after loading the video processor.
 */

async function testCaptions() {
    console.log('🧪 Starting Caption Test...');
    
    // Check if video processor is available
    if (typeof clientVideoProcessor === 'undefined') {
        console.error('❌ clientVideoProcessor not found. Make sure it\'s loaded first.');
        return;
    }
    
    // Initialize if needed
    if (!clientVideoProcessor.ffmpegLoaded) {
        console.log('⚡ Initializing FFmpeg.wasm...');
        try {
            await clientVideoProcessor.initialize();
            console.log('✅ FFmpeg.wasm initialized');
        } catch (error) {
            console.error('❌ FFmpeg.wasm initialization failed:', error);
            return;
        }
    }
    
    // Enable captions
    console.log('⚙️ Enabling captions...');
    clientVideoProcessor.enableCaptions();
    
    // Debug current state
    console.log('🔍 Debugging caption setup...');
    const debugInfo = clientVideoProcessor.debugCaptions();
    
    // Test capabilities
    console.log('🧪 Testing capabilities...');
    const capabilities = await clientVideoProcessor.testCaptionCapabilities();
    console.log('📊 Capabilities:', capabilities);
    
    // Mock caption data for testing
    const mockCaptions = [
        { start: 0, duration: 2.0, text: 'Hello world' },
        { start: 2, duration: 2.0, text: 'This is a test' },
        { start: 4, duration: 2.0, text: 'Amazing caption!' }
    ];
    
    console.log('📝 Mock captions prepared:', mockCaptions);
    
    if (capabilities.captionRendererAvailable) {
        // Test caption segment generation
        console.log('🔄 Testing caption segment generation...');
        const segments = clientVideoProcessor.captionRenderer.getCaptionSegments(mockCaptions, 0, 6);
        console.log('📋 Generated segments:', segments);
        
        if (segments.length > 0) {
            console.log('✅ Caption segments generated successfully');
            console.log(`📊 First segment: "${segments[0].text}" (${segments[0].start}s-${segments[0].end}s)`);
        } else {
            console.warn('⚠️  No caption segments generated');
        }
    }
    
    console.log('🎯 Caption test complete! Check the logs above for any issues.');
    console.log('💡 To test with a real video, use: processVideoWithCaptions(clipData, videoUrl, captions)');
    
    return {
        initialized: clientVideoProcessor.ffmpegLoaded,
        captionsEnabled: clientVideoProcessor.captionSettings.enabled,
        rendererAvailable: !!clientVideoProcessor.captionRenderer,
        capabilities: capabilities,
        mockSegments: capabilities.captionRendererAvailable ? 
            clientVideoProcessor.captionRenderer.getCaptionSegments(mockCaptions, 0, 6).length : 0
    };
}

// Test with minimal video processing (for when you have a video blob)
async function testCaptionOnVideo(videoBlob, mockCaptions = null) {
    console.log('🎬 Testing captions on actual video...');
    
    if (!videoBlob) {
        console.error('❌ No video blob provided');
        return null;
    }
    
    // Use default mock captions if none provided
    if (!mockCaptions) {
        mockCaptions = [
            { start: 0, duration: 3.0, text: 'TEST CAPTION' },
            { start: 3, duration: 3.0, text: 'ANOTHER TEST' }
        ];
    }
    
    console.log(`📝 Testing with ${mockCaptions.length} captions on ${(videoBlob.size / 1024 / 1024).toFixed(2)}MB video`);
    
    try {
        // Prepare caption segments
        const segments = clientVideoProcessor.captionRenderer.getCaptionSegments(mockCaptions, 0, 6);
        
        if (segments.length === 0) {
            console.error('❌ No caption segments generated');
            return null;
        }
        
        console.log(`📋 Using ${segments.length} caption segments`);
        
        // Test the caption processing directly
        const result = await clientVideoProcessor.addCaptionsTestMethod(
            videoBlob, 
            segments, 
            720,  // width
            1280, // height
            6,    // duration
            (progress, message) => console.log(`📊 ${progress.toFixed(1)}% - ${message}`)
        );
        
        console.log(`✅ Caption test complete: ${(result.size / 1024 / 1024).toFixed(2)}MB`);
        return result;
        
    } catch (error) {
        console.error('❌ Caption test failed:', error);
        return null;
    }
}

// Export functions for global use
if (typeof window !== 'undefined') {
    window.testCaptions = testCaptions;
    window.testCaptionOnVideo = testCaptionOnVideo;
    
    console.log('📋 Caption test functions loaded:');
    console.log('   • testCaptions() - Test basic caption setup');
    console.log('   • testCaptionOnVideo(videoBlob, captions) - Test on actual video');
}