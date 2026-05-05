"""Auto-generate and queue video topics — tries Google Trends first, falls back to Claude."""

from __future__ import annotations
import json
import os
import anthropic

TOPICS_FILE = os.path.join(os.path.dirname(__file__), "..", "topics_queue.json")

_CLAUDE_PROMPT = """Generate 25 viral short-form video topics for TikTok/YouTube Shorts.

Rules:
- Curiosity-driven, surprising, or counterintuitive facts
- Mix categories: science, psychology, history, money, life hacks, nature
- Each topic works as a 45-second narrated video over stock footage
- No political or controversial topics
- Phrased as a hook question or bold statement (not a dry title)

Examples of good topics:
- "Why you can't tickle yourself (and what it reveals about your brain)"
- "The Japanese technique that adds 5 years to your life"
- "Why billionaires wake up at 4am and why you shouldn't"

Return ONLY a JSON array of 25 strings. No markdown, no explanation."""


def get_next_topic() -> str:
    """Pop the next topic from the queue, refilling when empty."""
    queue = _load()
    if not queue:
        print("[topics] Queue empty — generating new batch...")
        queue = _generate()
        print(f"[topics] Generated {len(queue)} new topics.")
    topic = queue.pop(0)
    _save(queue)
    print(f"[topics] Topic: '{topic}' ({len(queue)} left in queue)")
    return topic


def _generate() -> list[str]:
    """Try Google Trends first; fall back to Claude."""
    topics = _from_trends()
    if topics:
        return topics
    return _from_claude()


def _from_trends() -> list[str]:
    """Pull trending searches and convert them into video hooks with Claude."""
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        df = pt.trending_searches(pn="united_states")
        raw = df[0].tolist()[:30]
        if not raw:
            return []

        client = anthropic.Anthropic()
        prompt = f"""These are today's trending Google searches: {raw}

Pick 10-15 that could become interesting short-form educational videos and convert each into a
curiosity-driven video hook (45-second narrated videos over visuals).

Skip: breaking news, celebrity gossip, sports scores, political events.
Focus on: science, psychology, history, money, life hacks, nature, surprising facts.

Return ONLY a JSON array of strings. No markdown."""

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = msg.content[0].text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        topics = json.loads(raw_text.strip())

        # Pad to 25 with Claude-generated ones if we got fewer
        if len(topics) < 25:
            topics += _from_claude()[: 25 - len(topics)]

        print(f"[topics] {len(topics)} topics from Google Trends + Claude filter.")
        return topics[:25]

    except Exception as e:
        print(f"[topics] Google Trends unavailable ({e}), using Claude instead.")
        return []


def _from_claude() -> list[str]:
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": _CLAUDE_PROMPT}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _load() -> list[str]:
    if not os.path.exists(TOPICS_FILE):
        return []
    with open(TOPICS_FILE) as f:
        return json.load(f)


def _save(queue: list[str]) -> None:
    with open(TOPICS_FILE, "w") as f:
        json.dump(queue, f, indent=2)
