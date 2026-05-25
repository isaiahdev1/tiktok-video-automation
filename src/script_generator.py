"""Generate a high-retention 60-second video script using Claude."""

import json
import time
import anthropic


def generate_script(topic: str) -> dict:
    client = anthropic.Anthropic()

    prompt = f"""You are the writer behind the most-shared educational short-form videos on the internet.
Your videos feel like someone leaning across a table and saying "you're not going to believe this."
They don't sound like textbooks. They sound like secrets.

Write a script about: "{topic}"

THE NON-NEGOTIABLES:
1. First sentence: one shocking claim stated as pure fact. No question marks. No "did you know". Just the claim, dropped like a bomb.
2. Every reveal must be MORE surprising than the last. Stack them. The viewer should feel like they're tumbling downhill.
3. Real specificity only. "Harvard researchers" not "scientists." "11 minutes" not "a few minutes." "1973" not "decades ago." Made-up specifics are fine — they sell the story.
4. Zero filler words. No "basically", "actually", "so", "well". Every word earns its place.
5. Sentence length: short. Medium. Short. Short. Vary it. Create rhythm.
6. The payoff must reframe everything they just heard — a twist that makes the hook mean something completely different.
7. CTA: one sentence, feels natural, NOT "follow for more facts." Make it specific to the video's theme.

STRUCTURE (135-155 words):
- Hook (1-2 sentences, 15-20 words): Impossible-sounding fact. Present tense. Active voice.
- Build (4-5 reveals, 85-100 words): Each one tops the last. Specifics. Names. Numbers. Short punchy sentences that hit like body blows.
- Payoff + CTA (2-3 sentences, 25-35 words): The twist that reframes the whole video. Then a CTA that feels earned.

For narration_segments: break the narration into 8-10 individual sentences. For each sentence, write an image_prompt that shows EXACTLY what that sentence is describing — not mood, not theme, the literal subject.

Image prompt rules:
- STOP-SCROLL quality: every image must look like it belongs on a magazine cover or viral Instagram post
- Ultra-specific to the sentence: if it says "Warren Buffett lost $23 billion in one day", write "Warren Buffett in suit looking devastated, holding head in hands, stock market crash on screens behind him, dramatic red light, cinematic close-up"
- Subject + action + setting + lighting + angle — always all five elements
- Lighting is everything: golden hour, dramatic rim light, neon glow, god rays, harsh shadows — pick the most striking option
- Mix angles aggressively: extreme close-up face, wide establishing shot, bird's eye aerial, low angle hero shot, over-the-shoulder — never two consecutive clips at the same angle
- Photorealistic people and places — real faces, real environments, real objects. No CGI, no abstract, no text
- Color contrast: pair warm subjects against cool backgrounds or vice versa for maximum visual pop

Respond ONLY with valid JSON, no markdown:
{{
  "title": "<curiosity-gap title, 50 chars max, must make someone stop scrolling>",
  "narration": "<the script, 135-155 words, every sentence a gut punch>",
  "hook": "<5-8 words, the single most impossible-sounding thing in the video>",
  "narration_segments": [
    {{"text": "<exact sentence from narration>", "search_query": "<3-4 plain keywords for stock photo search, e.g. 'man stressed paycheck desk'>", "image_prompt": "<detailed AI image description if stock photo fails, cinematic, photorealistic>"}},
    {{"text": "<next sentence>", "search_query": "<...>", "image_prompt": "<...>"}},
    "<8-10 total items covering the entire narration>"
  ],
  "mood": "<upbeat | calm | dramatic | neutral>",
  "description": "<2-3 sentence YouTube description with relevant hashtags and #Shorts>",
  "tags": ["<12-15 highly specific tags>"]
}}"""

    for attempt in range(5):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < 4:
                wait = 30 * (attempt + 1)
                print(f"[script] API overloaded, retrying in {wait}s (attempt {attempt+1}/5)...")
                time.sleep(wait)
            else:
                raise

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    script = json.loads(raw.strip())

    # Derive image_prompts and stock_queries from narration_segments for backward compat
    segments = script.get("narration_segments", [])
    if segments and isinstance(segments[0], dict):
        derived_prompts = [s["image_prompt"] for s in segments if isinstance(s, dict)]
    else:
        derived_prompts = script.get("stock_queries", [])
    script["image_prompts"] = derived_prompts
    script.setdefault("stock_queries", derived_prompts)
    script.setdefault("keywords", derived_prompts[:5])

    return script
