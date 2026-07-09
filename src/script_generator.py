"""Generate a high-retention 60-second video script using Claude."""

import json
import time
import anthropic


def generate_script(topic: str) -> dict:
    # Script override: if SCRIPT_OVERRIDE_FILE points to a JSON script, use it verbatim
    # (lets us hand-write a HOLMEZ brand script instead of the fact-channel generator).
    import os as _os, json as _json
    _ov = _os.getenv("SCRIPT_OVERRIDE_FILE")
    if _ov and _os.path.exists(_ov):
        with open(_ov) as _f:
            script = _json.load(_f)
        segs = script.get("narration_segments", [])
        derived = [s["image_prompt"] for s in segs if isinstance(s, dict)] if (segs and isinstance(segs[0], dict)) else script.get("stock_queries", [])
        script["image_prompts"] = derived
        script.setdefault("stock_queries", derived)
        script.setdefault("keywords", derived[:5])
        return script

    client = anthropic.Anthropic()

    prompt = f"""You are the writer behind the most-shared educational short-form videos on the internet.
Your videos feel like someone leaning across a table and saying "you're not going to believe this."
They don't sound like textbooks. They sound like secrets.

Write a script about: "{topic}"

BEFORE YOU WRITE — pick the emotion. Sharing is driven by physiological AROUSAL, not mood
(Berger & Milkman, peer-reviewed). Choose ONE high-arousal emotion and engineer the whole
script to detonate it: AWE (jaw-drop wonder), ANGER (this was done TO you / someone's getting
away with it), or ANXIETY (a hidden thing about your own body/money is working against you).
Never aim for "calm," "sad," or "mildly interesting" — those actively kill shares.

THE NON-NEGOTIABLES:
1. First sentence: one shocking claim stated as pure fact — a genuine pattern-interrupt. No question marks. No "did you know". No "here's why". Just the claim, dropped like a bomb, in the first 3 seconds. It has to make a scrolling thumb physically stop. If the first sentence could open a hundred other videos, it's wrong — rewrite it until it could only open THIS one.
2. Every reveal must be MORE surprising than the last. Stack them. The viewer should feel like they're tumbling downhill.
3. Real specificity only. "Harvard researchers" not "scientists." "11 minutes" not "a few minutes." "1973" not "decades ago." Every specific — names, numbers, dates, studies — must be factually TRUE and verifiable. Never invent facts. If you're unsure a detail is real, pick a different real one rather than fabricate. Accuracy is what keeps the channel alive on both platforms.
4. Zero filler words. No "basically", "actually", "so", "well". Every word earns its place.
5. Sentence length: short. Medium. Short. Short. Vary it. Create rhythm.
6. WITHHOLD THE PAYOFF. The hook opens a loop; do NOT close it until the final line. Curiosity is a drive state — the second the viewer "gets it," they leave. Keep the real answer dangling the entire way; each reveal deepens the mystery instead of resolving it. Never front-load the answer.
7. THE PAYOFF must reframe everything they just heard — a twist that makes the hook mean something completely different. It lands ONLY in the last line.
8. LOOP IT. Write the final line so it hands straight back into the hook — a viewer who lets it replay should feel the end flow seamlessly into the start. (Rewatches count as amplified watch time.)
9. CTA: must DEMAND a comment, folded INTO that final line (no separate "comment below" tag). A specific question the viewer feels compelled to answer, or a "be honest, did you just try it?" mechanic tied to the theme. Our videos get views but almost zero comments — the CTA's #1 job is to break that. NEVER "follow for more facts." Make the viewer reply.

STRUCTURE — KEEP IT SHORT (50-70 words, ~20-28 seconds). This is not a preference, it's from
this channel's OWN retention data: viewers watch ~19 seconds of a 70-second video, and almost
nobody stays past the 0:30 mark. Completion rate is the #1 algorithm signal — a tight 25s video
that gets watched to the end crushes a 60s video that gets abandoned. Every second past ~28s is
dead weight that drags completion down. Cut ruthlessly:
- Hook (1 sentence, 8-12 words): Impossible-sounding fact. Present tense. Active voice.
- Build (3 reveals, 30-46 words): Each one tops the last and deepens the open loop. Specifics. Names. Numbers. Short punchy sentences that hit like body blows.
- Payoff + CTA (1 sentence, 10-16 words): The twist that reframes everything AND loops back to the hook AND demands a reply — all in one closing line.

THE FIRST 10 SECONDS DECIDE EVERYTHING. This channel's real retention curve shows ~60% of
viewers gone within the first 10 seconds — a cliff. So the hook sentence AND the very first reveal
must both be gut-punches. Zero throat-clearing, zero setup, zero "in this video." Hit hard, immediately.

For narration_segments: break the narration into 5-6 individual sentences. For each sentence, write an image_prompt that shows EXACTLY what that sentence is describing — not mood, not theme, the literal subject.

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
  "narration": "<the script, 50-70 words, every sentence a gut punch, payoff withheld to the last line>",
  "hook": "<4-7 words — this is BURNED ON SCREEN as a title card for the first 2 seconds, so make it a punchy, self-contained gut-punch that reads instantly. The single most impossible-sounding thing in the video.>",
  "emotion": "<the ONE high-arousal emotion this script is engineered to trigger: awe | anger | anxiety>",
  "narration_segments": [
    {{"text": "<exact sentence from narration>", "search_query": "<3-4 plain keywords for stock photo search, e.g. 'man stressed paycheck desk'>", "image_prompt": "<detailed AI image description if stock photo fails, cinematic, photorealistic>"}},
    {{"text": "<next sentence>", "search_query": "<...>", "image_prompt": "<...>"}},
    "<5-6 total items covering the entire narration>"
  ],
  "mood": "<upbeat | calm | dramatic | neutral>",
  "description": "<2-3 sentence YouTube description with relevant hashtags and #Shorts>",
  "tags": ["<12-15 highly specific tags>"]
}}"""

    for attempt in range(5):
        try:
            message = client.messages.create(
                # The script is the single most creative call in the pipeline and
                # runs once per video — worth the best model for hook quality.
                model="claude-opus-4-8",
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
