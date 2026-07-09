"""Auto-generate and queue video topics — tries Google Trends first, falls back to Claude."""

from __future__ import annotations
import json
import os
import anthropic

TOPICS_FILE = os.path.join(os.path.dirname(__file__), "..", "topics_queue.json")

_CLAUDE_PROMPT = """Generate 25 viral short-form video topics for TikTok/YouTube Shorts.

PROVEN WINNING FORMAT (this is what our audience rewards with 10x the views):
Facts about the VIEWER'S OWN body, brain, senses, and behavior. Second-person "you".
Our biggest hits were about the viewer's own pinky finger, eyes, phone-in-hand sensation,
and food rules — things people can feel or test on themselves RIGHT NOW.

Rules:
- AT LEAST 16 of the 25 must be second-person "you/your" hooks about the body, brain, senses,
  habits, or hidden self ("Your tongue is lying to you about...", "Why your brain deletes...").
- The viewer must be able to feel, test, or notice it on themselves while watching.
- The remaining ~9 can be surprising science/psychology/history/money/nature facts.
- Curiosity-driven, surprising, or counterintuitive. Each works as a 45-second narrated video.
- No political or controversial topics.
- Phrased as a hook statement or question (not a dry title).

Examples of our winning format:
- "Your pinky finger controls 50% of your hand's strength"
- "Why you can touch your own eye but it feels wrong"
- "Your phone feels heavier when the battery is full (your brain is lying)"
- "The 3-second rule is real, but not for the reason you think"
- "Why you can't tickle yourself (and what it reveals about your brain)"

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

Whenever possible, reframe the hook in SECOND PERSON about the viewer's own body, brain, senses,
or behavior — that format gets ~10x our normal views (e.g. turn a topic about sleep into
"Why your brain replays embarrassing moments at 3am").

Skip: breaking news, celebrity gossip, sports scores, political events.
Focus on: the human body, the brain, the senses, psychology, surprising science, money, nature.

Return ONLY a JSON array of strings. No markdown."""

        msg = client.messages.create(
            model="claude-sonnet-5",
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
        model="claude-sonnet-5",
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
