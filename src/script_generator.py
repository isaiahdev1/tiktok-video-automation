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

For the stock_queries: think like a video editor sourcing B-roll. What footage would a documentary director cut to during each sentence? Be specific and concrete — these need to actually exist as stock footage (e.g. "woman forgetting name awkward pause conversation", "ancient roman aqueduct stone ruins", "scientist pipette laboratory research"). Avoid abstract concepts. Real scenes only.

Respond ONLY with valid JSON, no markdown:
{{
  "title": "<curiosity-gap title, 50 chars max, must make someone stop scrolling>",
  "narration": "<the script, 135-155 words, every sentence a gut punch>",
  "hook": "<5-8 words, the single most impossible-sounding thing in the video>",
  "stock_queries": [
    "<scene 1 — hook moment: specific concrete searchable footage description>",
    "<scene 2 — first reveal: specific real-world scene>",
    "<scene 3 — second reveal: specific real-world scene>",
    "<scene 4 — third reveal: specific real-world scene>",
    "<scene 5 — tension peak: specific real-world scene>",
    "<scene 6 — payoff/twist: specific real-world scene>"
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

    # Backwards compat: expose stock_queries as keywords + image_prompts
    script.setdefault("keywords", script.get("stock_queries", [])[:5])
    script.setdefault("image_prompts", script.get("stock_queries", []))

    return script
