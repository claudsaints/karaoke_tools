import subprocess
import pathlib
from ffmpeg_utils import get_ffmpeg_path

def trim_mp3(src: pathlib.Path, start_sec: float, end_sec: float, out_path: pathlib.Path) -> pathlib.Path:
    """Trim an audio file to [start_sec, end_sec] and export as MP3.
    Uses re-encoding with libmp3lame to ensure frame-accurate cutting.
    """
    duration = end_sec - start_sec
    if duration <= 0:
        raise ValueError("O tempo final deve ser maior que o tempo inicial.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()

    cmd = [
        ffmpeg_exe,
        "-y",
        "-ss", f"{start_sec:.3f}",
        "-i", str(src),
        "-t", f"{duration:.3f}",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_path)
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Erro ao cortar o áudio com FFmpeg:\n{result.stderr}")

    return out_path
