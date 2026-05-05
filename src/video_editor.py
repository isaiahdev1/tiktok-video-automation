"""Stitch AI images or stock clips + voiceover + captions + music into a final MP4."""

from __future__ import annotations
import os
import random
import subprocess
import tempfile
import shutil

TARGET_W = 1080
TARGET_H = 1920
MUSIC_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "music")
SFX_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "sfx")
FFMPEG = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg") or "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
FFPROBE = os.environ.get("FFPROBE_PATH") or shutil.which("ffprobe") or "/opt/homebrew/opt/ffmpeg-full/bin/ffprobe"
CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "MIND FACTS")

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Music volume per mood
_MOOD_VOL = {
    "dramatic": "-18dB",
    "upbeat":   "-20dB",
    "calm":     "-26dB",
    "neutral":  "-22dB",
}

# Cinematic color-grade vf string per mood
_MOOD_GRADE = {
    "dramatic": "vignette=PI/5,eq=contrast=1.15:saturation=0.85:brightness=-0.03,colorbalance=bs=-0.05",
    "upbeat":   "vignette=PI/6,eq=contrast=1.05:saturation=1.15:brightness=0.03,colorbalance=rs=0.04",
    "calm":     "vignette=PI/6,eq=contrast=1.0:saturation=0.9:brightness=0.0,colorbalance=bs=0.04",
    "neutral":  "vignette=PI/6,eq=contrast=1.1:saturation=1.0",
}

CROSSFADE_DUR = 0.3  # seconds

# Six distinct camera movements — cycles through each clip
_ZOOM_EXPRS = [
    "z='min(zoom+0.0008,1.1)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",                      # zoom in center
    "z='min(zoom+0.0015,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",                     # fast zoom center
    "z='min(zoom+0.0008,1.1)':x='min(iw*0.6-(iw/zoom/2),iw-(iw/zoom))':y='ih/2-(ih/zoom/2)'", # zoom in, right
    "z='min(zoom+0.0008,1.1)':x='max(iw*0.4-(iw/zoom/2),0)':y='ih/2-(ih/zoom/2)'",             # zoom in, left
    "z='min(zoom+0.0008,1.1)':x='iw/2-(iw/zoom/2)':y='max(ih*0.3-(ih/zoom/2),0)'",             # zoom in, top focus
    "z='min(zoom+0.0004,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",                     # slow drift
]


def build_video(
    clip_paths: list[str],
    audio_path: str,
    output_path: str,
    hook_text: str | None = None,
    mood: str = "neutral",
) -> str:
    """
    Build the final Short:
      1. Scale/crop clips or images to 1080x1920 (Ken Burns zoom)
      2. Crossfade-concat all clips
      3. Mux with voiceover + mood-matched background music
      4. Burn karaoke captions, channel name flash, hook overlay, outro
      5. Apply cinematic color grade per mood

    Returns output_path.
    """
    if not clip_paths:
        raise ValueError("No clips provided.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    work_dir = tempfile.mkdtemp(prefix="tiktok_build_")

    audio_duration = _probe_duration(audio_path)
    print(f"[editor] Audio: {audio_duration:.2f}s")

    n = len(clip_paths)
    per_clip = audio_duration / n
    print(f"[editor] {n} clips × {per_clip:.2f}s")

    # ── Step 1: Process each clip/image ───────────────────────────
    processed = []
    for i, clip in enumerate(clip_paths):
        dest = os.path.join(work_dir, f"_proc_{i}.mp4")
        _process_clip(clip, dest, per_clip, clip_index=i)
        processed.append(dest)

    # ── Step 2: Crossfade concat ──────────────────────────────────
    concat_path = os.path.join(work_dir, "_concat.mp4")
    if len(processed) > 1:
        _concat_crossfade(processed, concat_path, per_clip, audio_duration)
    else:
        _run([FFMPEG, "-y", "-i", processed[0], "-c", "copy", concat_path])

    # ── Step 3: Transcribe + generate captions ───────────────────
    ass_path = None
    try:
        print("[editor] Transcribing voiceover for captions...")
        from src.captions import transcribe_words, generate_ass
        words = transcribe_words(audio_path)
        if words:
            ass_path = generate_ass(
                words,
                hook_text=hook_text or "",
                channel_name=CHANNEL_NAME,
                total_duration=audio_duration,
            )
            print(f"[editor] Captions: {len(words)} words → {ass_path}")
        else:
            print("[editor] Whisper returned no words — skipping captions.")
    except Exception as e:
        print(f"[editor] Caption generation failed (non-fatal): {e}")

    # ── Step 4: Pick music by mood ────────────────────────────────
    music_path = _pick_music(mood)
    sfx_path = _pick_sfx("whoosh")

    # ── Step 5: Final ffmpeg passes ───────────────────────────────
    _build_final(
        video_path=concat_path,
        audio_path=audio_path,
        output_path=output_path,
        ass_path=ass_path,
        music_path=music_path,
        sfx_path=sfx_path,
        audio_duration=audio_duration,
        mood=mood,
    )

    shutil.rmtree(work_dir, ignore_errors=True)
    if ass_path and os.path.exists(ass_path):
        os.unlink(ass_path)

    print(f"[editor] Done: {output_path}")
    return output_path


def _build_final(
    video_path: str,
    audio_path: str,
    output_path: str,
    ass_path: str | None,
    music_path: str | None,
    sfx_path: str | None,
    audio_duration: float,
    mood: str = "neutral",
) -> None:
    work_dir = os.path.dirname(output_path)
    muxed_path = os.path.join(work_dir, f"_muxed_{os.getpid()}.mp4")
    music_vol = _MOOD_VOL.get(mood, "-22dB")

    # ── Pass 1: audio mux ─────────────────────────────────────────
    # Build input list: video, voiceover, [music], [sfx]
    inputs = ["-i", video_path, "-i", audio_path]
    streams = ["[1:a]apad[vo]"]
    mix_inputs = ["[vo]"]
    stream_idx = 2

    if music_path:
        inputs += ["-i", music_path]
        streams.append(
            f"[{stream_idx}:a]aloop=loop=-1:size=2147483647,"
            f"atrim=duration={audio_duration},volume={music_vol}[m]"
        )
        mix_inputs.append("[m]")
        stream_idx += 1

    if sfx_path:
        inputs += ["-i", sfx_path]
        # SFX plays at t=0, -12dB
        streams.append(
            f"[{stream_idx}:a]atrim=duration=2.0,volume=-12dB,apad[sfx]"
        )
        mix_inputs.append("[sfx]")
        stream_idx += 1

    if len(mix_inputs) > 1:
        streams.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first[aout]"
        )
        af = ";".join(streams)
        _run([
            FFMPEG, "-y",
            *inputs,
            "-filter_complex", af,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(audio_duration + 0.5),
            "-movflags", "+faststart",
            muxed_path,
        ])
    else:
        _run([
            FFMPEG, "-y",
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(audio_duration + 0.5),
            "-movflags", "+faststart",
            muxed_path,
        ])

    # ── Pass 2: captions + color grade ───────────────────────────
    grade = _MOOD_GRADE.get(mood, _MOOD_GRADE["neutral"])

    if ass_path:
        escaped = ass_path.replace("\\", "\\\\").replace(":", "\\:")
        vf = f"subtitles=filename='{escaped}',{grade}"
    else:
        vf = grade

    _run([
        FFMPEG, "-y",
        "-i", muxed_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ])
    os.unlink(muxed_path)


def _concat_crossfade(
    clips: list[str],
    output: str,
    clip_duration: float,
    total_duration: float,
) -> None:
    """Concat clips with a smooth crossfade between each one."""
    inputs = []
    for c in clips:
        inputs += ["-i", c]

    f = CROSSFADE_DUR
    filter_parts = []
    current = "[0:v]"

    for i in range(1, len(clips)):
        offset = i * (clip_duration - f)
        out_label = f"[v{i}]" if i < len(clips) - 1 else "[vout]"
        filter_parts.append(
            f"{current}[{i}:v]xfade=transition=fade:duration={f}:offset={offset:.3f}{out_label}"
        )
        current = out_label

    filter_complex = ";".join(filter_parts)

    _run([
        FFMPEG, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-t", str(total_duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        output,
    ])


def _process_clip(src: str, dest: str, duration: float, clip_index: int = 0) -> None:
    """Scale, crop to 9:16, apply varied Ken Burns movement. Handles images and video."""
    is_image = os.path.splitext(src)[1].lower() in _IMAGE_EXTS
    zoom_expr = _ZOOM_EXPRS[clip_index % len(_ZOOM_EXPRS)]

    vf = (
        f"scale={TARGET_W * 2}:{TARGET_H * 2}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_W}:{TARGET_H},"
        f"zoompan={zoom_expr}"
        f":d={int(duration * 30)}:s={TARGET_W}x{TARGET_H}:fps=30,"
        "fps=30"
    )

    if is_image:
        _run([
            FFMPEG, "-y",
            "-loop", "1", "-i", src,
            "-t", str(duration),
            "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            dest,
        ])
    else:
        _run([
            FFMPEG, "-y",
            "-ss", "0", "-i", src,
            "-t", str(duration),
            "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            dest,
        ])


def _pick_music(mood: str = "neutral") -> str | None:
    def _tracks_in(directory: str) -> list[str]:
        if not os.path.isdir(directory):
            return []
        return [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if f.lower().endswith((".mp3", ".wav", ".m4a"))
        ]

    tracks = _tracks_in(os.path.join(MUSIC_DIR, mood))
    if not tracks:
        tracks = _tracks_in(MUSIC_DIR)
    if not tracks:
        return None

    chosen = random.choice(tracks)
    print(f"[editor] Music ({mood}, {_MOOD_VOL.get(mood, '-22dB')}): {os.path.basename(chosen)}")
    return chosen


def _pick_sfx(name: str) -> str | None:
    """Pick a sound effect by name prefix from assets/sfx/."""
    if not os.path.isdir(SFX_DIR):
        return None
    for f in os.listdir(SFX_DIR):
        if f.lower().startswith(name) and f.lower().endswith((".mp3", ".wav", ".m4a")):
            path = os.path.join(SFX_DIR, f)
            print(f"[editor] SFX: {f}")
            return path
    return None


def _probe_duration(path: str) -> float:
    result = subprocess.run(
        [FFPROBE, "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _run(cmd: list[str]) -> None:
    print(f"[editor] $ {' '.join(cmd[:6])}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg error (exit {result.returncode}):\n{result.stderr[-3000:]}"
        )
