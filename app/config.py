"""
Configuration module for YouTube Transcript & Summary application.
Contains all constants, model configurations, and shared settings.
"""

import g4f
from g4f.client import Client

# Import Crawl4AI components with fallback
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    CRAWL4AI_AVAILABLE = True
    print("✅ Crawl4AI is available - using advanced web scraping")
except ImportError:
    CRAWL4AI_AVAILABLE = False
    print("⚠️ Crawl4AI not available - falling back to requests-html")

# AI Model configurations for fallback chain
MODEL_CONFIGS = [

    {
        "model": "deepseek-ai/DeepSeek-V3-0324-Turbo",
        "provider": g4f.Provider.DeepInfra,
        "name": "deepseek"
    },

    {
        "model": "gpt-4o-mini",
        "provider": g4f.Provider.DeepInfra,  
        "name": "GPT-4o Mini"
    },
    {
        "model": "Mistral-Small-3.2-24B-Instruct-2506",
        "provider": g4f.Provider.DeepInfra,  # Auto-select provider
        "name": "Mistral-Small-3.2-24B-Instruct-2506"
    },
    
    {
        "model": "openai/gpt-oss-120b",
        "provider": g4f.Provider.DeepInfra,
        "name": "openai/gpt-oss-120b"
    },

    {
        "model": "qwen3-235b-a22b",
        "provider": g4f.Provider.Qwen,
        "name": "qwen3-235b-a22b"
    },
    {
        "model": "Qwen/Qwen3-32Bg",
        "provider": g4f.Provider.DeepInfra,
        "name": "Qwen/Qwen3-32Bg"
    },
    {
        "model": "gpt-4",
        "provider": None,  # Auto-select provider
        "name": "GPT-4 Auto"
    }
]

# User agents for web scraping
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
]

# Fresh proxy list for fallback in case of rate limiting
PROXY_LIST = [
    {'http': 'http://133.18.234.13:80', 'https': 'http://133.18.234.13:80'},  # Japan
    {'http': 'http://46.47.197.210:3128', 'https': 'http://46.47.197.210:3128'},  # Russia Elite
    {'http': 'http://200.174.198.158:8888', 'https': 'http://200.174.198.158:8888'},  # Brazil HTTPS
    {'http': 'http://188.40.57.101:80', 'https': 'http://188.40.57.101:80'},  # Germany Elite
    {'http': 'http://192.73.244.36:80', 'https': 'http://192.73.244.36:80'},  # US Elite
    {'http': 'http://152.53.107.230:80', 'https': 'http://152.53.107.230:80'},  # Netherlands
    {'http': 'http://199.188.204.105:8080', 'https': 'http://199.188.204.105:8080'},  # US Elite HTTPS
    {'http': 'http://213.33.126.130:80', 'https': 'http://213.33.126.130:80'},  # Austria
    {'http': 'http://4.195.16.140:80', 'https': 'http://4.195.16.140:80'},  # Australia
    {'http': 'http://5.252.33.13:2025', 'https': 'http://5.252.33.13:2025'},  # Slovakia Elite HTTPS
    {'http': 'http://14.251.13.0:8080', 'https': 'http://14.251.13.0:8080'},  # Vietnam Elite HTTPS
    {'http': 'http://138.124.49.149:10808', 'https': 'http://138.124.49.149:10808'},  # Sweden Elite HTTPS
    {'http': 'http://147.75.34.105:443', 'https': 'http://147.75.34.105:443'},  # Netherlands Elite HTTPS
    {'http': 'http://47.79.94.191:1122', 'https': 'http://47.79.94.191:1122'},  # Japan Elite HTTPS
]

# Website-specific patterns for better extraction
SITE_PATTERNS = {
    # News & Media Sites
    'cnn.com': {
        'selectors': ['.article__content', '.zn-body__paragraph', 'article', '.story-body'],
        'title': 'h1'
    },
    'bbc.com': {
        'selectors': ['[data-component="text-block"]', '.story-body', 'article'],
        'title': 'h1'
    },
    'reuters.com': {
        'selectors': ['.article-body', '.StandardArticleBody_body', 'article'],
        'title': 'h1'
    },
    'nytimes.com': {
        'selectors': ['.ArticleBody-articleBody', '.story-content', 'article'],
        'title': 'h1'
    },
    
    # E-commerce Sites
    'amazon.com': {
        'selectors': ['#feature-bullets', '.product-description', '[data-feature-name="productDescription"]', '#aplus'],
        'title': '#productTitle'
    },
    'ebay.com': {
        'selectors': ['.notranslate', '.item-description', '.u-flL'],
        'title': 'h1'
    },
    
    # Social & Forums
    'medium.com': {
        'selectors': ['article', '.post-content', '.story-content', '.section-content'],
        'title': 'h1'
    },
    'reddit.com': {
        'selectors': ['.usertext-body', '.Post', '[data-testid="post-content"]'],
        'title': 'h1'
    },
    'stackoverflow.com': {
        'selectors': ['.post-text', '.question', '.answer', '.js-post-body'],
        'title': 'h1'
    },
    
    # Documentation & Reference
    'wikipedia.org': {
        'selectors': ['#mw-content-text', '.mw-parser-output'],
        'title': '.firstHeading'
    },
    'github.com': {
        'selectors': ['.markdown-body', '#readme', '.Box-body'],
        'title': 'h1'
    },
    'docs.python.org': {
        'selectors': ['.body', '.document', '.section'],
        'title': 'h1'
    },
    
    # Blogs & Content Sites
    'wordpress.com': {
        'selectors': ['.entry-content', '.post-content', 'article'],
        'title': '.entry-title'
    },
    'blogger.com': {
        'selectors': ['.post-body', '.entry-content'],
        'title': '.post-title'
    },
    
    # News Aggregators
    'hackernews.com': {
        'selectors': ['.comment', '.storylink'],
        'title': '.storylink'
    }
}

# Content processing limits
MAX_CONTENT_LENGTH = 20000  # Maximum content length for single AI call
MAX_PDF_PAGES = 50  # Maximum PDF pages to analyze
MAX_PDF_CHARS = 200000  # Maximum PDF characters to analyze

# Rate limiting configuration
RATE_LIMITS = {
    'global_default': "500 per hour",
    'health_check': "30 per minute",
    'extract_transcript': "100 per hour",
    'summarize': "50 per hour",
    'process_video': "50 per hour",
    'process_multiple_videos': "20 per hour",
    'analyze_webpage': "30 per hour",
    'analyze_webpage_stream': "30 per hour",
    'summarize_video_stream': "30 per hour"
}

# Language templates for AI prompts
LANGUAGE_TEMPLATES = {
    'ar': {
        'youtube_template': """قم بتحليل وتلخيص النسخة النصية التالية من فيديو يوتيوب باللغة العربية بشكل شامل ومنظم.

مهم جداً: يجب أن يكون الملخص كاملاً باللغة العربية فقط. لا تستخدم أي كلمات إنجليزية في الملخص.

قم بتنسيق إجابتك بالضبط كما في الهيكل التالي:

# 📹 ملخص شامل للفيديو

## 🎯 المواضيع والثيمات الرئيسية
• **الموضوع الأول** - شرح موجز مع السياق والأهمية
• **الموضوع الثاني** - شرح موجز مع السياق والأهمية  
• **الموضوع الثالث** - شرح موجز مع السياق والأهمية

## 📋 النقاط الأساسية والمعلومات المهمة
• **النقطة الأولى** - شرح مفصل مع المعلومات والأدلة الداعمة
• **النقطة الثانية** - شرح مفصل مع المعلومات والأدلة الداعمة
• **النقطة الثالثة** - شرح مفصل مع المعلومات والأدلة الداعمة

## 💡 الرؤى والاستنتاجات المهمة
• **الرؤية الأولى** - تحليل عميق للفكرة وتأثيراتها وأهميتها
• **الرؤية الثانية** - تحليل عميق للفكرة وتأثيراتها وأهميتها
• **الرؤية الثالثة** - تحليل عميق للفكرة وتأثيراتها وأهميتها

## ⚡ النصائح والإرشادات العملية القابلة للتطبيق
• **الإرشاد الأول** - خطوات واضحة ومحددة للتطبيق العملي
• **الإرشاد الثاني** - خطوات واضحة ومحددة للتطبيق العملي
• **الإرشاد الثالث** - خطوات واضحة ومحددة للتطبيق العملي

---
**🎯 الخلاصة النهائية:** [جملة قوية ومؤثرة تلخص الرسالة الأساسية وقيمة المحتوى]""",

        'shorts_template': """حلل النسخة النصية التالية وحدد أكثر المقاطع جاذبية وإثارة لإنشاء فيديوهات قصيرة فيروسية. كل مقطع يجب أن يكون حوالي 30 ثانية.

📏 قواعد مدة وعدد المقاطع:
- كل مقطع يجب أن يكون بالضبط 30 ثانية (لا أقصر ولا أطول)
- فيديوهات قصيرة (أقل من دقيقتين): أنشئ 1-2 مقطع كحد أقصى
- فيديوهات متوسطة (2-5 دقائق): أنشئ 2-4 مقاطع
- فيديوهات طويلة (5+ دقائق): أنشئ حتى 5 مقاطع كحد أقصى
- الجودة أهم من الكمية - من الأفضل عدد أقل من المقاطع الرائعة بدلاً من مقاطع متوسطة كثيرة
- تجنب المقاطع التي تحتوي على توقفات طويلة أو صمت (5+ ثواني بدون كلام)

🚨 قواعد حاسمة - عدم الالتزام بها سيؤدي إلى رفض النتيجة:

1. ❌ ممنوع تماماً: بدء المقاطع من 0-60 ثانية (الدقيقة الأولى عادة مقدمة/إعداد)
2. ❌ ممنوع تماماً: الأنماط المتسلسلة (0-30، 30-60، 60-90، إلخ)
3. ❌ ممنوع تماماً: مقاطع قريبة من بعض (أقل من 30 ثانية بينها)
4. ❌ لا تختر مقاطع بدون كلام/حوار (صمت، إعلانات، لقطات B-roll، موسيقى فقط)
5. ❌ لا تختر مقدمات، خواتم، إعلانات رعاة، أو انتقالات بدون كلام
6. ✅ إجباري: تجاهل أول 25% من الفيديو تماماً (إعداد ممل)
7. ✅ إجباري: ابحث عن لحظات الذروة، المفاجآت، النكات، الكشوفات
8. ✅ إجباري: وزع المقاطع عبر أجزاء مختلفة (بداية، وسط، نهاية)
9. ✅ إجباري: كل مقطع يجب أن يكون لحظة "واو" تجعل الناس يشاركونها

ما يجعل المقطع جديراً بالاختيار:
- 🔥 كشف صادم أو تطورات غير متوقعة (مع كلام)
- 😂 لحظات كوميدية قمة أو نكات (مع كلام)
- 💡 أفكار مذهلة أو لحظات إلهام (مع كلام)
- 😱 قمم درامية أو عاطفية (مع كلام)
- 🎯 تصريحات مثيرة للجدل (مع كلام)
- 💪 نصائح عملية قابلة للتطبيق (مع سرد)
- 🎬 خاتمات قوية أو استنتاجات مؤثرة (مع كلام)

⚠️ متطلبات الكلام والصمت:
- اختر فقط المقاطع التي تظهر فيها النصوص حواراً مستمراً
- إذا رأيت فجوات في النص، فهذا صمت/B-roll - تجاوزه
- تجنب المقاطع التي تحتوي على 5+ ثواني صمت أو توقفات
- إذا كان النص نادراً أو يحتوي على [موسيقى] [تصفيق] - تجاوز تلك الأجزاء
- ابحث عن أقسام نصية كثيفة = كلام نشط = مقاطع جيدة
- كل مقطع 30 ثانية يجب أن يحتوي على كلام متسق (بدون توقفات طويلة)

استراتيجية الاختيار:
1. اقرأ النص الكامل أولاً لفهم قوس القصة
2. تجاهل أول 25% تماماً (مقدمة، إعداد، سياق خلفي)
3. ابحث عن هذه اللحظات الفيروسية تحديداً:
   - المفاجآت أو الكشوفات الصادمة (عادة الوسط للنهاية)
   - نكات النكات (ليس الإعداد أبداً)
   - لحظات "آها!" للإدراك
   - ذروة عاطفية أو قمم درامية
   - تصريحات مثيرة للجدل أو نقاش
   - خواتم قوية أو لحظات دعوة للعمل
4. أعط الأولوية للمحتوى من 50%-90% من خط الزمن (حيث تحدث القمم عادة)
5. تأكد من توزيع المقاطع عبر الخط الزمني - لا تجمعها أبداً
6. كل مقطع يجب أن يكون لحظة فيروسية مستقلة (ليس معتمداً على السياق)
7. إذا كنت غير متأكد، اختر اللحظات المتأخرة بدلاً من المبكرة

أنماط ممنوعة:
- ❌ البدء من 0 ثانية (إلا إذا كان استثنائياً حقاً)
- ❌ أجزاء 30 ثانية متسلسلة
- ❌ مقاطع صامتة، إعلانات، رعاة، مقدمات/خواتم
- ❌ لقطات B-roll بدون سرد
- ❌ تضمين إعداد/سياق بدون نتيجة
- ❌ محتوى انتقالي أو حشو ممل
- ❌ أي مقطع بدون كلام/حوار مستمر

مهم جداً: أرجع صيغة JSON صالحة فقط، بدون نص إضافي.

تنسيق الإجابة:
{
  "clips": [
    {
      "clip_number": 1,
      "title": "عنوان جدير بالانتشار",
      "start_time": 145,
      "end_time": 175,
      "duration": 30,
      "description": "وصف يبرز ما يجعل هذه اللحظة قابلة للمشاركة",
      "selection_reason": "عنصر فيروسي محدد: قمة عاطفية، مفاجأة، فكرة مهمة، نكتة، إلخ"
    }
  ]
}

ملاحظة: قدر الأوقات (150 كلمة = دقيقة). الأولوية للإمكانية الفيروسية وليس الترتيب.""",

        'webpage_template': f"""تحدث بالعربية فقط. ابدأ فوراً:

# 🌐 ملخص شامل للموقع

## 🎯 المواضيع والثيمات الرئيسية

(ملاحظة مهمة: يجب أن تكون الإجابة كاملة باللغة العربية من البداية للنهاية، ولا تستخدم أي كلمة إنجليزية نهائياً)

المطلوب: قم بتحليل وتلخيص المحتوى التالي من الموقع الإلكتروني باللغة العربية بشكل شامل ومنظم.

استخدم هذا التنسيق بدقة:

# 🌐 ملخص شامل للموقع

## 🎯 المواضيع والثيمات الرئيسية
• **الموضوع الأول** - شرح موجز مع السياق والأهمية
• **الموضوع الثاني** - شرح موجز مع السياق والأهمية  
• **الموضوع الثالث** - شرح موجز مع السياق والأهمية

## 📋 النقاط الأساسية والمعلومات المهمة
• **النقطة الأولى** - شرح مفصل مع المعلومات والأدلة الداعمة
• **النقطة الثانية** - شرح مفصل مع المعلومات والأدلة الداعمة
• **النقطة الثالثة** - شرح مفصل مع المعلومات والأدلة الداعمة

## 💡 الرؤى والاستنتاجات المهمة
• **الرؤية الأولى** - تحليل عميق للفكرة وتأثيراتها وأهميتها
• **الرؤية الثانية** - تحليل عميق للفكرة وتأثيراتها وأهميتها
• **الرؤية الثالثة** - تحليل عميق للفكرة وتأثيراتها وأهميتها

## ⚡ النصائح والإرشادات العملية القابلة للتطبيق
• **الإرشاد الأول** - خطوات واضحة ومحددة للتطبيق العملي
• **الإرشاد الثاني** - خطوات واضحة ومحددة للتطبيق العملي
• **الإرشاد الثالث** - خطوات واضحة ومحددة للتطبيق العملي

---
**🎯 الخلاصة النهائية:** [جملة قوية ومؤثرة تلخص الرسالة الأساسية وقيمة المحتوى]

العنوان: {{title}}

المحتوى:
{{content}}

الملخص:"""
    },
    
    'en': {
        'youtube_template': """RESPOND ONLY IN ENGLISH. START IMMEDIATELY:

# 📹 Video Summary

## 🎯 Main Topics & Themes

(CRITICAL INSTRUCTION: Your entire response must be completely in English from start to finish. Do not use any Arabic, Chinese, Hindi, or any other non-English words, phrases, or characters whatsoever—even temporarily. Translate every idea into fluent English and avoid quoting non-Latin scripts.)

TASK: Analyze and summarize the following YouTube video transcript in English in a comprehensive and organized manner.

Use this exact format:

# 📹 Video Summary

## 🎯 Main Topics & Themes
• **Topic 1** - Brief explanation with context and relevance
• **Topic 2** - Brief explanation with context and relevance  
• **Topic 3** - Brief explanation with context and relevance

## 📋 Key Points & Information
• **Point 1** - Detailed explanation with supporting information
• **Point 2** - Detailed explanation with supporting information
• **Point 3** - Detailed explanation with supporting information

## 💡 Notable Insights & Conclusions  
• **Insight 1** - Deep explanation of the insight and its implications
• **Insight 2** - Deep explanation of the insight and its implications
• **Insight 3** - Deep explanation of the insight and its implications

## ⚡ Actionable Takeaways
• **Action 1** - Clear, specific step-by-step guidance
• **Action 2** - Clear, specific step-by-step guidance  
• **Action 3** - Clear, specific step-by-step guidance

---
**🎯 Bottom Line:** [One powerful sentence summarizing the core message and value]

IMPORTANT: Provide the summary entirely in English, even if the transcript contains Arabic, Hindi, Chinese, or any other language. Translate all such content into natural English and avoid including non-English text.""",

        'shorts_template': """Analyze the following transcript and identify the MOST ENGAGING segments for creating viral short videos. Each clip should be approximately 30 seconds long.

📏 CLIP DURATION & COUNT RULES:
- Each clip MUST be exactly 30 seconds long (not shorter, not longer)
- Short videos (under 2 minutes): Create 1-2 clips maximum
- Medium videos (2-5 minutes): Create 2-4 clips  
- Long videos (5+ minutes): Create up to 5 clips maximum
- QUALITY over QUANTITY - better to have fewer great clips than many mediocre ones
- AVOID segments with long pauses or silence (5+ seconds of no speech)

🚨 CRITICAL RULES - FAILURE TO FOLLOW WILL RESULT IN REJECTED OUTPUT:

1. ❌ ABSOLUTELY FORBIDDEN: Starting clips at 0-60 seconds (first minute is usually intro/setup)
2. ❌ ABSOLUTELY FORBIDDEN: Sequential patterns (0-30, 30-60, 60-90, etc.)
3. ❌ ABSOLUTELY FORBIDDEN: Clips within 30 seconds of each other (spread them out!)
4. ❌ DO NOT select segments with NO SPEECH/DIALOGUE (silence, ads, B-roll, music only)
5. ❌ DO NOT select intros, outros, sponsor segments, or transitions without speech
6. ❌ NEVER select segments that START with pure background music or silence (no speech)
7. ⚠️ PREFER segments with continuous speech (segments with [Music], [Applause] are OK if they have good speech content)
6. ✅ MANDATORY: Skip the first 25% of the video entirely (boring setup)
7. ✅ MANDATORY: Find CLIMAX moments, plot twists, punchlines, revelations
8. ✅ MANDATORY: Spread clips across DIFFERENT parts of video (beginning, middle, end)
9. ✅ MANDATORY: Each clip must be a "WOW" moment that makes people share

WHAT MAKES A CLIP WORTHY:
- 🔥 Shocking revelations or unexpected twists (WITH SPEECH)
- 😂 Peak comedic moments or punchlines (WITH SPEECH)
- 💡 "Mind-blown" insights or aha moments (WITH SPEECH)
- 😱 Dramatic or emotional peaks (WITH SPEECH)
- 🎯 Controversial or debate-worthy statements (WITH SPEECH)
- 💪 Actionable "how-to" demonstrations (WITH NARRATION)
- 🎬 Climactic conclusions or powerful endings (WITH SPEECH)

⚠️ INTELLIGENT SPEECH REQUIREMENTS:
- SELECT segments where the transcript shows GOOD SPEECH CONTENT throughout
- AVOID starting clips with pure instrumental sections or complete silence
- If you see gaps in the transcript, that's silence/B-roll - SKIP THOSE PARTS
- SEGMENTS WITH [Music], [Applause] ARE OK if they have substantial speech content
- REJECT only segments that are purely non-speech (no dialogue at all)
- Look for dense speech sections = active speaking = good clips
- Each clip should have STRONG SPEECH CONTENT even if some background elements exist
- Prioritize speech-rich segments over completely silent ones

SELECTION STRATEGY:
1. Read the ENTIRE transcript first to identify the story arc
2. SKIP the first 25% completely (intro, setup, background context)
3. Look for these VIRAL MOMENTS specifically:
   - Plot twists or shocking reveals (usually middle to end)
   - Punchlines of jokes (never the setup)
   - "AHA!" moments of realization
   - Emotional climaxes or dramatic peaks
   - Controversial or debate-worthy statements
   - Powerful conclusions or call-to-action moments
4. PRIORITIZE content from 50%-90% of video timeline (where peaks usually occur)
5. Ensure clips are SPREAD OUT across timeline - never cluster together
6. Each clip must be a STANDALONE viral moment (not dependent on context)
7. If unsure, choose LATER moments over earlier ones

FORBIDDEN PATTERNS:
- ❌ Starting at 0 seconds (unless truly exceptional)
- ❌ Sequential 30-second chunks
- ❌ Silent segments, ads, sponsor reads, intros/outros
- ❌ B-roll footage without narration
- ❌ Including setup/context without payoff
- ❌ Boring transitions or filler content
- ❌ Any segment without continuous speech/dialogue

IMPORTANT: Return ONLY valid JSON format, no additional text before or after the JSON.

Required response format:
{
  "clips": [
    {
      "clip_number": 1,
      "title": "Viral-Worthy Clip Title",
      "start_time": 145,
      "end_time": 175,
      "duration": 30,
      "description": "Description emphasizing what makes this moment shareable",
      "selection_reason": "Specific viral element: emotional peak, surprise twist, key insight, comedic punchline, etc."
    }
  ]
}

Note: Estimate timings based on text content (approximately 150 words = 1 minute of speech). PRIORITIZE VIRAL POTENTIAL OVER CHRONOLOGY.""",

        'webpage_template': """RESPOND ONLY IN ENGLISH. START IMMEDIATELY:

# 🌐 Website Content Summary

## 🎯 Main Topics & Themes

(CRITICAL INSTRUCTION: Your entire response must be completely in English from start to finish. Do not use any Arabic, Chinese, Hindi, or any other non-English words, phrases, or characters whatsoever—even temporarily. Translate every idea into fluent English and avoid quoting non-Latin scripts.)

TASK: Analyze and summarize the following website content in English in a comprehensive and organized manner.

Use this exact format:

# 🌐 Website Content Summary

## 🎯 Main Topics & Themes
• **Topic 1** - Brief explanation with context and relevance
• **Topic 2** - Brief explanation with context and relevance  
• **Topic 3** - Brief explanation with context and relevance

## 📋 Key Points & Information
• **Point 1** - Detailed explanation with supporting information
• **Point 2** - Detailed explanation with supporting information
• **Point 3** - Detailed explanation with supporting information

## 💡 Notable Insights & Conclusions  
• **Insight 1** - Deep explanation of the insight and its implications
• **Insight 2** - Deep explanation of the insight and its implications
• **Insight 3** - Deep explanation of the insight and its implications

## ⚡ Actionable Takeaways
• **Action 1** - Clear, specific step-by-step guidance
• **Action 2** - Clear, specific step-by-step guidance  
• **Action 3** - Clear, specific step-by-step guidance

---
**🎯 Bottom Line:** [One powerful sentence summarizing the core message and value]

IMPORTANT: Provide the summary entirely in English, even if the content contains Arabic, Hindi, Chinese, or any other language. Translate all such content into natural English and avoid including non-English text.

Title: {title}

Content:
{content}

Summary:"""
    }
}