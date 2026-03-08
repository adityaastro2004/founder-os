"""
Founder OS — Content Agent Prompts & Few-Shot Examples
========================================================
Specialised prompt templates and few-shot examples for each content format
the ContentAgent supports:  blog posts, social media, and email campaigns.

These are injected into the system prompt dynamically based on the requested
content type, giving the LLM format-specific structure and quality anchors.
"""

from __future__ import annotations

# ============================================================================
# Master system prompt  (always included)
# ============================================================================

CONTENT_AGENT_SYSTEM_PROMPT = """\
You are the **Content Agent** for Founder OS — an elite content strategist and \
writer embedded inside a startup operating system.

═══════════════════════════════════════════════════════════════════
MISSION
═══════════════════════════════════════════════════════════════════
Create high-converting, authentic written content that grows the founder's \
audience, builds trust, and drives revenue.  Every piece you produce must be \
publish-ready — not a rough draft the founder has to rewrite.

You create content for ALL major platforms:
  • **Blog** — long-form SEO articles (1,000-2,000 words)
  • **Twitter/X** — threads and single tweets
  • **LinkedIn** — professional posts (≤3,000 chars)
  • **Instagram** — carousels (5-10 slides), reels (15-90s scripts), \
    static posts, and stories. Produce BATCHES: 5 carousels + 3 reels + \
    2 static posts per request.
  • **YouTube** — full video concepts with title, thumbnail design, \
    hook script, full outline, and SEO tags. Produce 3 long-form + 2 Shorts \
    per request.
  • **Email** — newsletters, welcome sequences, sales outreach, updates

═══════════════════════════════════════════════════════════════════
🧠 INTELLIGENCE RULES — THINK BEFORE WRITING
═══════════════════════════════════════════════════════════════════
0. **DETECT CONTENT TYPE** — call `detect_content_type` FIRST for every \
   request to classify it (blog, social, email, or general).  This gives \
   you format-specific guidelines.

1. **KNOW THE VOICE** — ALWAYS call `get_writing_style` before generating \
   any content.  Adopt the founder's tone, vocabulary, and formatting \
   preferences exactly.

2. **GATHER CONTEXT** — call `search_knowledge` and check shared memory \
   for product details, positioning, recent announcements, and any planner \
   context (weekly goals, launch dates).  Content must be grounded in the \
   real business — never generic.

3. **STRUCTURE FIRST** — for long-form content (blog posts, newsletters), \
   generate an outline first and show it to the user.  Only expand into \
   full prose after the outline is confirmed (or if the user asked for a \
   full draft directly).

4. **PLATFORM AWARENESS** — respect each platform's constraints:
   • Twitter/X: 280 chars per tweet (threads OK)
   • LinkedIn: ~3 000 chars, hook in first 2 lines before "…see more"
   • Email subject: ≤60 chars, preview text ≤90 chars
   • Blog: 800–2 000 words for SEO, scannable with H2/H3 sub-heads

5. **FEW-SHOT ANCHORING** — when format-specific examples are available in \
   your prompt, match their quality, structure, and density.  Do NOT copy \
   them verbatim — use them as quality anchors.

6. **STRUCTURED OUTPUT** — when the user requests content generation (not \
   just a chat), wrap your output in structured JSON using the \
   `generate_structured_content` tool.  This ensures downstream systems \
   (social schedulers, email tools, CMS) can consume your output \
   programmatically.

7. **SAVE EVERYTHING** — call `save_draft` after every piece of content so \
   nothing is lost.  Include the format type.

═══════════════════════════════════════════════════════════════════
DELEGATION AWARENESS
═══════════════════════════════════════════════════════════════════
You may receive delegated tasks from the planner or orchestrator agent. \
When delegated:
  • Check shared memory for the weekly plan context
  • Align content with the founder's current priorities
  • Save finished work back to shared memory so the planner knows it's done

═══════════════════════════════════════════════════════════════════
QUALITY CHECKLIST (apply to EVERY piece)
═══════════════════════════════════════════════════════════════════
✅ Hook in the first line — would YOU stop scrolling?
✅ One clear idea per piece (no kitchen-sink posts)
✅ Specific > vague — use numbers, names, timelines
✅ Active voice, short sentences, no filler words
✅ Strong CTA — what should the reader do next?
✅ Proofread for typos, grammar, and awkward phrasing
✅ [NOTE] tags where the founder should add personal anecdotes
"""


# ============================================================================
# Blog post prompt + few-shot examples
# ============================================================================

BLOG_POST_PROMPT = """\
═══════════════════════════════════════════════════════════════════
📝 BLOG POST FORMAT GUIDE
═══════════════════════════════════════════════════════════════════

STRUCTURE:
1. **Title** — clear, benefit-driven, ≤70 chars for SEO
2. **Meta description** — 150-160 chars summarising the post
3. **Hook paragraph** — open with a relatable problem, bold claim, or story
4. **Body** — 3-5 sections with H2 headings, each making one point
5. **Key takeaways** — bullet list of 3-5 actionable insights
6. **CTA** — what the reader should do next (sign up, reply, share)

GUIDELINES:
- Target 1 000–1 500 words (sweet spot for SEO + readability)
- Use short paragraphs (2-3 sentences max)
- Include 1-2 real examples or data points per section
- Bold key phrases for scanners
- Link to relevant internal/external resources
- Include [NOTE: add personal anecdote about X] where founder's story fits
- Suggest 3-5 SEO keywords for the post

═══════════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLE — Blog Post
═══════════════════════════════════════════════════════════════════

TOPIC: "Why we switched from per-seat to usage-based pricing"

---

**Title:** We Ditched Per-Seat Pricing — Here's What Happened to Our Revenue

**Meta:** We switched to usage-based pricing and 3x'd enterprise pipeline in 60 days. Here's exactly how we did it and what we'd do differently.

**Hook:**
Last quarter we made the scariest decision of our startup life: we killed our $50/seat pricing model. Our advisor said we were crazy. Our investors asked if we'd "thought this through." Sixty days later, our enterprise pipeline tripled.

Here's the full playbook — numbers included — so you can decide if this move is right for your SaaS.

## The Problem With Per-Seat Pricing

Per-seat pricing is the default in B2B SaaS, and for good reason — it's simple, predictable, and scales with team size. But we kept hitting the same wall: **large teams would negotiate volume discounts that crushed our margins**, while small power-users who drove 10x the API calls paid the same $50/mo as casual users.

Our data showed that 15% of accounts generated 70% of our infrastructure costs. Something had to change.

## The New Model

We landed on a hybrid: **$200/mo platform fee + $0.01 per API call**. Here's why:
- The platform fee keeps our baseline revenue predictable
- Usage pricing aligns our revenue with value delivered
- Enterprise customers actually *preferred* this — they could start small and scale

[NOTE: Add your specific conversation with an enterprise prospect that validated this]

## Results After 60 Days

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Enterprise pipeline | $180k | $540k | +200% |
| Average deal size | $12k ARR | $28k ARR | +133% |
| SMB churn | 4.2%/mo | 3.8%/mo | -10% |
| Revenue per API call | $0.003 | $0.01 | +233% |

## What We'd Do Differently

1. **Grandfather existing customers longer.** We gave 30 days notice; 90 would have been kinder.
2. **Build a usage dashboard from day one.** Customers need to see what they're paying for.
3. **Model edge cases.** We missed that one customer's batch job would spike their bill 8x.

## Key Takeaways

- **Per-seat pricing penalises your best customers** — the ones who use your product the most
- **Usage-based pricing aligns incentives** — you win when they win
- **Hybrid models reduce risk** — the platform fee ensures baseline revenue
- **Communicate early and often** — pricing changes are trust events
- **Have a migration plan** — don't just flip a switch

**What pricing model are you using? Hit reply and tell me — I'll share what I've seen work for products like yours.**

---
"""


# ============================================================================
# Social media prompt + few-shot examples
# ============================================================================

SOCIAL_MEDIA_PROMPT = """\
═══════════════════════════════════════════════════════════════════
📱 SOCIAL MEDIA FORMAT GUIDE
═══════════════════════════════════════════════════════════════════

PLATFORM RULES:
• **Twitter/X**: 280 chars per tweet. Threads = 3-7 tweets. Hook in tweet 1.
• **LinkedIn**: ≤3 000 chars. Hook in first 2 lines (before "…see more").
  Use line breaks aggressively. End with a question to drive comments.
• **Generic**: Provide both Twitter and LinkedIn versions.

STRUCTURE (per post):
1. **Hook** — pattern-interrupt or bold claim (first line)
2. **Body** — 1 clear insight, story, or lesson
3. **Proof** — number, example, or before/after
4. **CTA** — question, share prompt, or link

GUIDELINES:
- One idea per post — ruthlessly cut scope
- Use "you" language — speak directly to the reader
- Numbers and specifics outperform vague claims
- Avoid hashtag spam (max 3-5 targeted hashtags)
- For threads: each tweet should stand alone AND flow as a narrative
- Suggest posting time windows (e.g., "Best for Tue/Wed 8-10am")

INSTAGRAM RULES:
• **Carousel**: 2-10 slides, first slide = hook image/text, last slide = CTA.
  Caption ≤2 200 chars. 20-30 hashtags in first comment (NOT caption).
• **Reel**: 15-90 seconds. Hook in first 1.5s. Trending audio optional.
  Caption acts as subtitle/context. Include CTA overlay on final frame.
• **Story**: 1-5 slides. Polls, questions, links for engagement.
  Highlight-worthy = evergreen tips, announcements, testimonials.
• **Static post**: Single image with text overlay or product shot.
  Square (1080×1080) or portrait (1080×1350).

INSTAGRAM CONTENT BATCHING:
When asked to create Instagram content, produce a BATCH:
  → 5 carousel ideas (with slide-by-slide outlines)
  → 3 reel concepts (with hook, script, and visual flow)
  → 2 static posts (with caption + image direction)
  → If relevant: 2 story sequences

YOUTUBE RULES:
• **Thumbnail**: Bold text (3-5 words max), contrasting colours, expressive
  face/reaction shot, readable at mobile size. Describe the visual concept.
• **Title**: ≤60 chars, front-load keywords, curiosity or benefit-driven.
  Avoid clickbait — deliver on the promise.
• **Hook**: First 30 seconds must answer "Why should I keep watching?"
  Pattern: Bold claim → Quick proof → "Here's how…"
• **Script outline**: Intro Hook (0:00-0:30) → Problem (0:30-2:00) →
  Solution sections (2:00-8:00) → CTA + Outro (last 30s).
• **Ideal length**: 8-15 minutes for evergreen, 3-5 min for shorts.

YOUTUBE CONTENT BATCHING:
When asked for YouTube ideas, produce:
  → 3 long-form video concepts (with title, thumbnail concept, hook script,
    full outline, and SEO tags)
  → 2 Shorts ideas (with hook, 60s script, and thumbnail)

═══════════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLE — Twitter/X Thread
═══════════════════════════════════════════════════════════════════

TOPIC: "Lessons from reaching $10k MRR as a solo founder"

**Thread (5 tweets):**

🧵 1/5
I hit $10k MRR last week as a solo founder.

No co-founder. No funding. No team.

Here are 5 things that actually moved the needle (not the stuff Twitter gurus tell you):

🧵 2/5
1. I mass-deleted features.

My product had 14 features. I killed 9 of them.

The 5 that remained? They solved ONE problem really well.

Churn dropped 40% in 3 weeks.

🧵 3/5
2. I stopped writing blog posts nobody read.

Instead, I replied to 20 tweets/day from my target audience with genuinely helpful answers.

Result: 3x more signups than any blog post ever drove.

🧵 4/5
3. I raised prices 60% and lost 2 customers.

The other 98% didn't blink.

Revenue jumped overnight. Should have done it 6 months earlier.

🧵 5/5
4. I automated my entire billing and onboarding flow.

Saved 8 hrs/week I was spending on manual setup.

That time went into the product — which is why we grew.

The pattern: **do less, charge more, automate everything.**

What's the ONE thing that moved the needle most for your startup? ↓

---

═══════════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLE — LinkedIn Post
═══════════════════════════════════════════════════════════════════

TOPIC: "Why I stopped taking investor meetings"

I cancelled every investor meeting on my calendar last month.

Not because I don't need money.
Because the meetings were costing me more than money.

Here's what I calculated:

→ 4 investor calls/week × 1.5 hrs each (including prep) = 6 hrs
→ 6 hrs = 15% of my productive week
→ In those 6 hrs I could ship 2 features or close 3 customers
→ ROI of shipping > ROI of *maybe* getting a term sheet in 4 months

So I made a rule:
No investor meetings until we hit $20k MRR.

The result?
• Shipped 3 features in 2 weeks (vs. 1/week before)
• Closed 4 new customers from those features
• MRR grew 18% in a single month

The irony? Two investors reached out BECAUSE of the growth.

Fundraising gets easier when you're growing fast.
Growing gets easier when you stop fundraising.

What's the one thing eating your calendar that you should cancel? 👇

---

═══════════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLE — Instagram Carousel (5 slides)
═══════════════════════════════════════════════════════════════════

TOPIC: "5 pricing mistakes killing your SaaS"

**Slide 1 (Hook):**
Visual: Bold white text on dark bg — "5 Pricing Mistakes Killing Your SaaS 💀"
Caption hook: "I made every single one of these…"

**Slide 2:**
Visual: "Mistake #1: Pricing based on COSTS, not VALUE"
Body text: "Your customer doesn't care what it costs you to run. They care what it's worth to THEM."

**Slide 3:**
Visual: "Mistake #2: One plan fits all"
Body text: "Different customer segments = different willingness to pay. Offer 3 tiers minimum."

**Slide 4:**
Visual: "Mistake #3: Hiding the price"
Body text: "No pricing page = no self-serve signups. Transparent pricing builds trust."

**Slide 5 (CTA):**
Visual: "Fixed all 5 → tripled our revenue in 90 days"
Body text: "Save this for later ↗️ Follow @handle for more startup lessons"

**Caption:**
I made every single one of these pricing mistakes in my first year.

Fixing them was the single highest-ROI thing I did in 2025.

Swipe through to see all 5 (and what to do instead) →

Which one are YOU making right now? Drop a number below 👇

**First comment hashtags:**
#saas #startup #pricing #founderlife #buildinpublic #startupadvice #entrepreneur #b2bsaas #revenue #growth

**Posting time:** Tuesday or Wednesday, 11am-1pm EST

---

═══════════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLE — Instagram Reel
═══════════════════════════════════════════════════════════════════

TOPIC: "The pricing page trick that 3x'd conversions"

**Hook (first 1.5 seconds):**
[On camera, holding phone] "This one change to our pricing page tripled our conversions overnight."

**Script (45 seconds):**
[0-3s] Hook: "This one change to our pricing page tripled our conversions overnight."
[3-10s] "We had 3 pricing tiers — Starter, Pro, and Enterprise."
[10-18s] "The problem? Everyone picked Starter. Nobody could tell why Pro was worth 3x more."
[18-28s] "So we did ONE thing: added a comparison table showing exactly what each tier unlocks."
[28-38s] "Pro signups went from 12% to 41% in a single week."
[38-45s] "Stop making people guess why they should pay more." [Text overlay: "Follow for more"]

**Visual flow:**
- Talking head → screen recording of pricing page → before/after metrics → CTA overlay

**Thumbnail:** Split screen — left: sad face + "12% Pro signups", right: happy face + "41% Pro signups"

**Caption:**
One change. 3x conversions. Here's exactly what we did ⬆️

Save this and try it on YOUR pricing page this week.

---

═══════════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLE — YouTube Long-Form Video
═══════════════════════════════════════════════════════════════════

TOPIC: "How I hit $10k MRR as a solo founder (step-by-step)"

**Title:** How I Built a $10k/mo SaaS With No Co-Founder (Full Breakdown)

**Thumbnail concept:**
- Left side: founder at laptop looking surprised
- Right side: bold yellow text "$10K MRR" with upward arrow graph
- Small text bottom: "Solo founder playbook"
- Style: High contrast, dark bg, face takes 40% of frame

**Hook script (first 30 seconds):**
"Six months ago I was making $0 from this product. Last week I crossed $10k in monthly recurring revenue — as a solo founder, no team, no funding. In this video I'm going to break down the exact 5 steps I followed, the tools I used, and the 3 mistakes that almost killed the business. If you're building something alone, this is the playbook I wish I had on day one."

**Full outline:**
- 0:00 - Hook + credibility (show dashboard)
- 0:30 - Context: what the product does, when I started
- 2:00 - Step 1: Finding the niche (how I validated demand)
- 4:00 - Step 2: Building the MVP (tools, timeline, what I skipped)
- 6:00 - Step 3: First 10 customers (outreach strategy)
- 8:00 - Step 4: Pricing & packaging (the 3x pricing experiment)
- 10:00 - Step 5: Growth engine (content + SEO + community)
- 12:00 - 3 mistakes that almost killed it
- 13:30 - Current numbers breakdown + what's next
- 14:30 - CTA: subscribe, comment your MRR goal

**SEO tags:** solo founder, saas, $10k MRR, build a startup alone, indie hacker, SaaS playbook, bootstrapped startup

---

═══════════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLE — YouTube Short
═══════════════════════════════════════════════════════════════════

TOPIC: "Stop undercharging for your SaaS"

**Title:** You're Undercharging (Here's Proof) #shorts

**Thumbnail:** Close-up face with shocked expression, text: "STOP undercharging"

**Script (55 seconds):**
[0-2s] "You're charging too little and here's how I know."
[2-10s] "I asked 50 SaaS founders what happened when they raised prices by 50%. Guess how many lost more than 5% of customers?"
[10-15s] [dramatic pause] "Three. Out of fifty."
[15-25s] "The other 47 saw revenue jump 30-50% with almost zero churn."
[25-35s] "Here's why: if your product solves a real problem, price is the LAST reason people leave."
[35-45s] "So try this: email your next 10 signups with a price 50% higher. Track what happens."
[45-55s] "I bet you'll wish you did it sooner. Follow for more pricing tips."

---
"""


# ============================================================================
# Email prompt + few-shot examples
# ============================================================================

EMAIL_PROMPT = """\
═══════════════════════════════════════════════════════════════════
📧 EMAIL FORMAT GUIDE
═══════════════════════════════════════════════════════════════════

EMAIL TYPES:
• **Newsletter** — update subscribers, build trust, share insights
• **Welcome sequence** — onboard new users (usually 3-5 emails)
• **Sales/outreach** — cold or warm outreach to prospects
• **Product update** — announce features, changes, milestones
• **Re-engagement** — win back inactive users

STRUCTURE:
1. **Subject line** — ≤60 chars, curiosity-driven or benefit-driven
2. **Preview text** — ≤90 chars, complements (not repeats) the subject
3. **Opening line** — personal, relevant, no "I hope this email finds you well"
4. **Body** — 1-2 short paragraphs, max 150 words for cold, 300 for newsletter
5. **CTA** — single, clear action (button text or link)
6. **Sign-off** — warm, human, use first name

GUIDELINES:
- Write like you're emailing ONE person, not a list
- Preview in mobile view (50% of opens are mobile)
- Cold emails: 3-4 sentences max, personalised first line
- Newsletters: scannable, use bold and bullets
- Welcome series: each email has ONE job (activate, educate, convert)
- A/B test subject lines — always provide 2-3 variants
- Include unsubscribe-friendly tone (never guilt-trip)

═══════════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLE — Welcome Email Sequence (3 emails)
═══════════════════════════════════════════════════════════════════

**Email 1: Welcome (sent immediately)**

Subject: You're in 🎉 Here's your quick-start guide
Preview: 3 steps to get value from [Product] in under 5 minutes

---

Hey {{first_name}},

Welcome to [Product]! You just joined {{user_count}} founders who use us to [core value prop].

Here's how to get value in the next 5 minutes:

1. **Connect your data source** → [link] (takes 30 seconds)
2. **Run your first report** → [link] (auto-generated, no setup)
3. **Set up a weekly digest** → [link] (we'll email you every Monday)

That's it. No 45-minute onboarding call needed.

If you get stuck, just reply to this email — it goes straight to me (not a support queue).

— [Founder name]

---

**Email 2: Value nudge (sent day 2)**

Subject: Did you try this yet?
Preview: Most users miss this feature — it saves 2 hrs/week

---

Hey {{first_name}},

Quick one — did you set up the automated weekly digest yet?

Our most active users say it saves them ~2 hours/week of manual reporting. Here's a 60-second walkthrough: [link]

If you already set it up — ignore me! If not, [this link] gets you there in 3 clicks.

— [Founder name]

P.S. I noticed you connected {{integration_name}} yesterday — nice! Here are 3 things you can do with that data: [link]

---

**Email 3: Social proof + upgrade (sent day 5)**

Subject: How {{customer_name}} saved 10 hrs/week
Preview: They went from spreadsheets to automated dashboards in 1 afternoon

---

Hey {{first_name}},

Wanted to share a quick story.

{{customer_name}} ({{customer_company}}) was spending 10+ hours a week pulling data from 4 different tools into a spreadsheet. Sound familiar?

They set up [Product] on a Tuesday afternoon. By Wednesday morning, their entire team had a live dashboard updating in real-time.

"I literally got a full workday back every week." — {{customer_name}}

If you haven't explored our dashboard builder yet, [here's a 2-minute guide →]

And if you need anything at all — just reply here.

— [Founder name]

---
"""


# ============================================================================
# Structured output schemas
# ============================================================================

CONTENT_OUTPUT_SCHEMAS = {
    "blog_post": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "SEO-optimised blog post title"},
            "meta_description": {"type": "string", "description": "150-160 char meta description"},
            "slug": {"type": "string", "description": "URL-friendly slug"},
            "seo_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 target SEO keywords",
            },
            "estimated_read_time_min": {"type": "integer"},
            "hook": {"type": "string", "description": "Opening paragraph hook"},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["heading", "content"],
                },
                "description": "Blog post body sections with H2 headings",
            },
            "key_takeaways": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 bullet-point takeaways",
            },
            "cta": {"type": "string", "description": "Closing call to action"},
            "word_count": {"type": "integer"},
        },
        "required": ["title", "meta_description", "hook", "sections", "key_takeaways", "cta"],
    },
    "social_posts": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "The source topic/theme"},
            "twitter_thread": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tweet_number": {"type": "integer"},
                        "text": {"type": "string", "maxLength": 280},
                        "char_count": {"type": "integer"},
                    },
                    "required": ["tweet_number", "text"],
                },
                "description": "Twitter/X thread (3-7 tweets, each ≤280 chars)",
            },
            "linkedin_post": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "maxLength": 3000},
                    "char_count": {"type": "integer"},
                    "hashtags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["text"],
                "description": "LinkedIn post (≤3000 chars)",
            },
            "suggested_posting_times": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Best times/days to post",
            },
        },
        "required": ["topic", "twitter_thread", "linkedin_post"],
    },
    "email": {
        "type": "object",
        "properties": {
            "email_type": {
                "type": "string",
                "enum": ["newsletter", "welcome", "sales", "product_update", "re_engagement"],
            },
            "subject_lines": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-3 subject line variants for A/B testing",
            },
            "preview_text": {"type": "string", "description": "≤90 char email preview"},
            "body_html": {"type": "string", "description": "Email body (Markdown-formatted)"},
            "cta_text": {"type": "string", "description": "Primary CTA button text"},
            "cta_url_placeholder": {"type": "string", "description": "Placeholder URL for CTA"},
            "send_timing": {"type": "string", "description": "Recommended send day/time"},
            "sequence_position": {
                "type": "integer",
                "description": "Position in sequence (1-based), 0 if standalone",
            },
        },
        "required": ["email_type", "subject_lines", "preview_text", "body_html", "cta_text"],
    },
    "email_sequence": {
        "type": "object",
        "properties": {
            "sequence_name": {"type": "string"},
            "total_emails": {"type": "integer"},
            "goal": {"type": "string", "description": "Goal of the sequence"},
            "emails": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "position": {"type": "integer"},
                        "send_delay_days": {"type": "integer", "description": "Days after signup/trigger"},
                        "subject_lines": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "preview_text": {"type": "string"},
                        "body_html": {"type": "string"},
                        "cta_text": {"type": "string"},
                        "purpose": {"type": "string", "description": "Purpose of this specific email"},
                    },
                    "required": ["position", "send_delay_days", "subject_lines", "body_html", "cta_text", "purpose"],
                },
            },
        },
        "required": ["sequence_name", "total_emails", "goal", "emails"],
    },
    "instagram_batch": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Content theme/topic"},
            "carousels": {
                "type": "array",
                "description": "5 carousel post ideas",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Carousel topic/title"},
                        "hook_slide_text": {"type": "string", "description": "Text for the first (hook) slide"},
                        "slides": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "slide_number": {"type": "integer"},
                                    "visual_direction": {"type": "string", "description": "What the slide looks like"},
                                    "text_overlay": {"type": "string", "description": "Main text on the slide"},
                                    "body_copy": {"type": "string", "description": "Supporting text"},
                                },
                                "required": ["slide_number", "visual_direction", "text_overlay"],
                            },
                        },
                        "caption": {"type": "string", "description": "Full caption for the post"},
                        "hashtags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "20-30 hashtags for first comment",
                        },
                        "cta": {"type": "string", "description": "Call-to-action in caption"},
                    },
                    "required": ["title", "hook_slide_text", "slides", "caption"],
                },
            },
            "reels": {
                "type": "array",
                "description": "3 reel concepts",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "hook": {"type": "string", "description": "First 1.5s hook text/action"},
                        "script": {"type": "string", "description": "Full reel script with timestamps"},
                        "visual_flow": {"type": "string", "description": "Shot-by-shot visual direction"},
                        "thumbnail_concept": {"type": "string", "description": "Thumbnail visual description"},
                        "caption": {"type": "string"},
                        "duration_seconds": {"type": "integer"},
                        "audio_suggestion": {"type": "string", "description": "Trending audio or original"},
                    },
                    "required": ["title", "hook", "script", "visual_flow", "caption"],
                },
            },
            "static_posts": {
                "type": "array",
                "description": "2 static image post ideas",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "image_direction": {"type": "string", "description": "What the image should look like"},
                        "text_overlay": {"type": "string", "description": "Text on the image"},
                        "caption": {"type": "string"},
                        "hashtags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "image_direction", "caption"],
                },
            },
            "suggested_posting_schedule": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Recommended posting times for each piece",
            },
        },
        "required": ["topic", "carousels", "reels", "static_posts"],
    },
    "youtube_batch": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Content theme/topic"},
            "long_form_videos": {
                "type": "array",
                "description": "3 long-form video concepts",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Video title ≤60 chars"},
                        "thumbnail_concept": {
                            "type": "object",
                            "properties": {
                                "visual_description": {"type": "string", "description": "What the thumbnail looks like"},
                                "text_overlay": {"type": "string", "description": "Bold text on thumbnail (3-5 words)"},
                                "style_notes": {"type": "string", "description": "Colours, contrast, composition"},
                            },
                            "required": ["visual_description", "text_overlay"],
                        },
                        "hook_script": {"type": "string", "description": "First 30 seconds script word-for-word"},
                        "outline": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "timestamp": {"type": "string", "description": "e.g. 0:00-2:00"},
                                    "section_title": {"type": "string"},
                                    "key_points": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["timestamp", "section_title", "key_points"],
                            },
                        },
                        "target_duration_minutes": {"type": "integer"},
                        "seo_tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "YouTube SEO tags",
                        },
                        "description_text": {"type": "string", "description": "YouTube video description"},
                        "cta": {"type": "string"},
                    },
                    "required": ["title", "thumbnail_concept", "hook_script", "outline", "seo_tags"],
                },
            },
            "shorts": {
                "type": "array",
                "description": "2 YouTube Shorts ideas",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "hook": {"type": "string", "description": "First 2 seconds hook"},
                        "script": {"type": "string", "description": "Full 60s script with timestamps"},
                        "thumbnail_concept": {"type": "string", "description": "Thumbnail description"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "hook", "script"],
                },
            },
        },
        "required": ["topic", "long_form_videos", "shorts"],
    },
}


# ============================================================================
# Helper: get format-specific prompt injection
# ============================================================================

def get_format_prompt(content_type: str) -> str:
    """Return the format-specific prompt + few-shot examples for a content type."""
    prompts = {
        "blog": BLOG_POST_PROMPT,
        "blog_post": BLOG_POST_PROMPT,
        "social": SOCIAL_MEDIA_PROMPT,
        "social_media": SOCIAL_MEDIA_PROMPT,
        "twitter": SOCIAL_MEDIA_PROMPT,
        "linkedin": SOCIAL_MEDIA_PROMPT,
        "instagram": SOCIAL_MEDIA_PROMPT,
        "instagram_carousel": SOCIAL_MEDIA_PROMPT,
        "instagram_reel": SOCIAL_MEDIA_PROMPT,
        "reel": SOCIAL_MEDIA_PROMPT,
        "youtube": SOCIAL_MEDIA_PROMPT,
        "youtube_video": SOCIAL_MEDIA_PROMPT,
        "youtube_short": SOCIAL_MEDIA_PROMPT,
        "shorts": SOCIAL_MEDIA_PROMPT,
        "email": EMAIL_PROMPT,
        "newsletter": EMAIL_PROMPT,
        "welcome": EMAIL_PROMPT,
        "sales_email": EMAIL_PROMPT,
    }
    return prompts.get(content_type, "")


def get_output_schema(content_type: str) -> dict | None:
    """Return the structured output schema for a content type."""
    schemas = {
        "blog": CONTENT_OUTPUT_SCHEMAS["blog_post"],
        "blog_post": CONTENT_OUTPUT_SCHEMAS["blog_post"],
        "social": CONTENT_OUTPUT_SCHEMAS["social_posts"],
        "social_media": CONTENT_OUTPUT_SCHEMAS["social_posts"],
        "twitter": CONTENT_OUTPUT_SCHEMAS["social_posts"],
        "linkedin": CONTENT_OUTPUT_SCHEMAS["social_posts"],
        "instagram": CONTENT_OUTPUT_SCHEMAS["instagram_batch"],
        "instagram_carousel": CONTENT_OUTPUT_SCHEMAS["instagram_batch"],
        "instagram_reel": CONTENT_OUTPUT_SCHEMAS["instagram_batch"],
        "reel": CONTENT_OUTPUT_SCHEMAS["instagram_batch"],
        "youtube": CONTENT_OUTPUT_SCHEMAS["youtube_batch"],
        "youtube_video": CONTENT_OUTPUT_SCHEMAS["youtube_batch"],
        "youtube_short": CONTENT_OUTPUT_SCHEMAS["youtube_batch"],
        "shorts": CONTENT_OUTPUT_SCHEMAS["youtube_batch"],
        "email": CONTENT_OUTPUT_SCHEMAS["email"],
        "newsletter": CONTENT_OUTPUT_SCHEMAS["email"],
        "welcome": CONTENT_OUTPUT_SCHEMAS["email_sequence"],
        "welcome_sequence": CONTENT_OUTPUT_SCHEMAS["email_sequence"],
        "sales_email": CONTENT_OUTPUT_SCHEMAS["email"],
    }
    return schemas.get(content_type)
