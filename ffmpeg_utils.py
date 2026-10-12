import os
import shutil
import pathlib
import imageio_ffmpeg

def ensure_ffmpeg_in_path():
    """Ensure ffmpeg.exe exists and its directory is in PATH."""
    try:
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and os.path.exists(bundled):
            bin_dir = os.path.dirname(bundled)
            target_exe = os.path.join(bin_dir, "ffmpeg.exe")
            if not os.path.exists(target_exe):
                try:
                    shutil.copy2(bundled, target_exe)
                except Exception:
                    pass
            if bin_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

ensure_ffmpeg_in_path()

def get_ffmpeg_path() -> str:
    """Returns the absolute path to a working ffmpeg binary.
    Prioritizes system PATH, falls back to imageio_ffmpeg bundled binary.
    """
    ensure_ffmpeg_in_path()
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and os.path.exists(bundled):
            return bundled
    except Exception:
        pass
    return "ffmpeg"
