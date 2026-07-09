"""Transcribe voiceover and burn captions — viral TikTok style.

Two on-screen layers are produced here:
  1. A bold HOOK title card over the opening ~2.2s (top-center). This is the
     single biggest retention lever — the first frame is what stops the scroll.
     (It was previously accepted as a param but never rendered — dead code.)
  2. Karaoke captions: 3-word phrases in the lower third with the currently
     spoken word popped in bright yellow + scaled up. The active-word highlight
     is what separates a native-feeling clip from generic AI-slop captions.
"""

from __future__ import annotations
import os
import tempfile

_model = None

# How long the hook title card stays on screen (seconds).
HOOK_DURATION = 2.2
# Words shown together in the lower-third karaoke line.
WORDS_PER_LINE = 3


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


def transcribe_words(audio_path: str) -> list[dict]:
    model = _get_model()
    segments, _ = model.transcribe(audio_path, word_timestamps=True)
    words = []
    for segment in segments:
        for word in segment.words:
            words.append({
                "word": word.word.strip(),
                "start": word.start,
                "end": word.end,
            })
    return words


def generate_ass(
    words: list[dict],
    hook_text: str = "",
    words_per_line: int = WORDS_PER_LINE,
    channel_name: str = "",
    total_duration: float = 0.0,
) -> str:
    """
    Build the ASS subtitle file:
    - Hook title card (top-center) over the first HOOK_DURATION seconds
    - Karaoke captions (lower third), N words per line, active word highlighted
    """
    # ASS colour format is &HAABBGGRR& (alpha, blue, green, red).
    WHITE     = "&H00FFFFFF&"
    BLACK     = "&H00000000&"
    HIGHLIGHT = "&H0000F2FF&"  # punchy yellow for the active word (RGB #FFF200)
    SHADOW    = "&H88000000"

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 1\n\n"

        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"

        # Karaoke captions — white, bold, thick outline, lower-center (align 2)
        f"Style: Cap,Arial Black,86,{WHITE},{WHITE},{BLACK},"
        f"{SHADOW},-1,0,0,0,100,100,1,0,1,7,3,2,60,60,470,1\n"

        # Hook title card — bigger, top-center (align 8), heavy outline
        f"Style: Hook,Arial Black,96,{WHITE},{WHITE},{BLACK},"
        f"{SHADOW},-1,0,0,0,100,100,1,0,1,9,4,8,80,80,300,1\n\n"

        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events = []

    # ── Hook title card (first ~2.2s) ────────────────────────────────
    hook = (hook_text or "").strip().upper()
    if hook:
        # Soft fade in/out so it doesn't just snap on/off.
        events.append(
            f"Dialogue: 1,{_fmt(0.0)},{_fmt(HOOK_DURATION)},Hook,,0,0,0,,"
            f"{{\\fad(150,200)}}{_escape(hook)}"
        )

    # ── Karaoke captions with active-word highlight ──────────────────
    n = len(words)
    for i in range(0, n, words_per_line):
        chunk = words[i: i + words_per_line]

        for j, word_data in enumerate(chunk):
            start = word_data["start"]
            end   = max(word_data["end"], start + 0.20)

            # Extend the active word to the next word's start (no flicker gap).
            global_idx = i + j
            if global_idx + 1 < n:
                end = max(end, words[global_idx + 1]["start"])

            # Render the whole chunk; the active word gets colour + scale pop.
            parts = []
            for k, w in enumerate(chunk):
                token = _escape(w["word"].upper())
                if k == j:
                    parts.append(
                        f"{{\\c{HIGHLIGHT}\\fscx116\\fscy116}}{token}{{\\r}}"
                    )
                else:
                    parts.append(token)
            text = "  ".join(parts)

            events.append(
                f"Dialogue: 0,{_fmt(start)},{_fmt(end)},Cap,,0,0,0,,{text}"
            )

    fd, path = tempfile.mkstemp(suffix=".ass", prefix="tiktok_")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
    return path


def _escape(text: str) -> str:
    """Escape characters that ASS treats as override syntax."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _fmt(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    s = s % 60
    return f"{h}:{m:02d}:{s:05.2f}"
