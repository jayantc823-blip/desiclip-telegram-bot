"""FFmpeg-based vertical clip renderer with captions, hook banner, narration and BGM."""
import asyncio
import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", " ")

def _write_ass(path: Path, caption: str, seconds: float):
    words = caption.split()[:16] or ["BHAI", "YE", "SCENE", "DEKHO!"]
    duration = max(1.0, seconds)
    step = duration / len(words)
    header = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,DejaVu Sans,66,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,1,4,2,2,60,60,230,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    events = []
    for i, word in enumerate(words):
        start, end = i*step, min(duration, (i+1)*step)
        def stamp(t):
            cs = int((t % 1)*100); total = int(t); return f"{total//3600}:{(total%3600)//60:02}:{total%60:02}.{cs:02}"
        events.append(f"Dialogue: 0,{stamp(start)},{stamp(end)},Default,,0,0,0,,{{\\c&H0000FFFF&}}{_ass_escape(word)}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")

async def _run(args):
    def work():
        return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        await asyncio.to_thread(work)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("FFmpeg render failed: " + (exc.stderr or "")[-1200:]) from exc

async def render(source: Path, output: Path, workdir: Path, start: float, end: float, script: dict, voice_path: Path | None, avatar: Path | None, bgm: Path | None):
    duration = max(1.0, end - start)
    ass = workdir / "captions.ass"
    _write_ass(ass, script.get("caption", ""), duration)
    sub = str(ass.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    hook = script.get("hook", "")[:60].replace("'", "").replace(":", "\\:")
    video_filter = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,subtitles='{sub}',drawbox=x=0:y=0:w=iw:h=230:color=yellow@0.94:t=fill,drawtext=text='{hook}':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:fontsize=58:fontcolor=black:x=(w-text_w)/2:y=70"
    args = ["ffmpeg", "-y", "-threads", "1", "-filter_threads", "1", "-ss", str(start), "-i", str(source)]
    voice_index = bgm_index = avatar_index = 0
    if voice_path and voice_path.exists():
        args += ["-i", str(voice_path)]; voice_index = 1
    if bgm and bgm.exists():
        args += ["-stream_loop", "-1", "-i", str(bgm)]; bgm_index = len([x for x in args if x == "-i"])
    if avatar and avatar.exists():
        args += ["-i", str(avatar)]; avatar_index = len([x for x in args if x == "-i"])
    filters = [f"[0:v]{video_filter}[base]"]
    vmap = "[base]"
    if avatar_index:
        filters.append(f"[{avatar_index}:v]scale=230:-1,format=rgba,colorchannelmixer=aa=0.88[face];[base][face]overlay=W-w-35:H-h-330:shortest=1[vout]")
        vmap = "[vout]"
    args += ["-filter_complex", ";".join(filters), "-map", vmap]
    if voice_index and bgm_index:
        filters_audio = f"[{voice_index}:a]volume=1.0[voice];[{bgm_index}:a]volume=0.14[beat];[voice][beat]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        args[-2] = ";".join(filters) + ";" + filters_audio
        args += ["-map", "[aout]"]
    elif voice_index:
        args += ["-map", f"{voice_index}:a"]
    elif bgm_index:
        args += ["-map", f"{bgm_index}:a"]
    else:
        args += ["-map", "0:a?"]
    args += ["-t", str(duration), "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1", "-crf", "28", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(output)]
    await _run(args)
    return output
