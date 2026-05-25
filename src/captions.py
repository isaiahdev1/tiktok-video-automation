"""Transcribe voiceover and burn karaoke captions — viral TikTok style."""

from __future__ import annotations
import os
import tempfile

_model = None


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
    words_per_line: int = 1,
    channel_name: str = "",
    total_duration: float = 0.0,
) -> str:
    """
    Burn minimal captions:
    - 1 word at a time, centered in lower frame
    - All white — no yellow highlight
    - Thick black outline, drop shadow — readable over any footage
    """
    # ASS color format: &HAABBGGRR&
    WHITE = "&H00FFFFFF&"
    BLACK = "&H00000000&"

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

        # Main captions — white, bold, thick outline, lower-center
        f"Style: Cap,Arial Black,110,{WHITE},{WHITE},{BLACK},"
        "&H88000000,-1,0,0,0,100,100,2,0,1,8,3,2,50,50,480,1\n\n"

        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events = []

    # One word at a time, all white
    for i in range(0, len(words), words_per_line):
        chunk = words[i: i + words_per_line]

        for j, word_data in enumerate(chunk):
            start = word_data["start"]
            end   = word_data["end"]
            end   = max(end, start + 0.25)

            # Extend last word of chunk to next chunk's start (no gap)
            if j == len(chunk) - 1 and i + words_per_line < len(words):
                end = max(end, words[i + words_per_line]["start"])

            text = "  ".join(w["word"].upper() for w in chunk)
            events.append(
                f"Dialogue: 0,{_fmt(start)},{_fmt(end)},Cap,,0,0,0,,{text}"
            )

    fd, path = tempfile.mkstemp(suffix=".ass", prefix="tiktok_")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
    return path


def _fmt(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    s = s % 60
    return f"{h}:{m:02d}:{s:05.2f}"
