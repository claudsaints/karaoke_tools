import subprocess
import pathlib
from ffmpeg_utils import get_ffmpeg_path

def apply_pitch_shift(input_audio: pathlib.Path, output_mp3: pathlib.Path, semitones: float = 1.0) -> pathlib.Path:
    """Shift pitch up or down without changing playback duration or speed.
    1 semitone = 2^(1/12) ≈ 1.059463.
    """
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    ratio = 2.0 ** (semitones / 12.0)
    inv_ratio = 1.0 / ratio

    ffmpeg_exe = get_ffmpeg_path()
    # asetrate changes pitch+speed, atempo restores original speed
    filter_str = f"asetrate=44100*{ratio:.6f},aresample=44100,atempo={inv_ratio:.6f}"

    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(input_audio),
        "-af", filter_str,
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_mp3)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_mp3

def apply_stage_reverb(input_audio: pathlib.Path, output_mp3: pathlib.Path) -> pathlib.Path:
    """Apply live karaoke stage ambience: acoustic reverb + stereo widening.
    Smears frequency fingerprint peaks to bypass content filters while sounding great.
    """
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()

    # Echo/reverb + stereo widening + mild warming
    filter_str = "aecho=0.8:0.88:35|55:0.25|0.20,extrastereo=m=1.35,volume=1.05"

    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(input_audio),
        "-af", filter_str,
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_mp3)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_mp3

def apply_lofi_warmth(input_audio: pathlib.Path, output_mp3: pathlib.Path) -> pathlib.Path:
    """Apply aesthetic vintage lo-fi warmth (soft roll-off + warm mid presence).
    Keeps instruments fully readable and distinct while altering spectral characteristics.
    """
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()

    filter_str = "lowpass=f=10500,highpass=f=45,equalizer=f=2800:t=q:w=1.2:g=2.0,volume=1.12"

    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(input_audio),
        "-af", filter_str,
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_mp3)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_mp3

def apply_nightcore(input_audio: pathlib.Path, output_mp3: pathlib.Path, speed_ratio: float = 1.05) -> pathlib.Path:
    """Increase playback speed and pitch together (+5% by default).
    Returns path to output MP3.
    """
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()

    filter_str = f"asetrate=44100*{speed_ratio:.4f},aresample=44100"

    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(input_audio),
        "-af", filter_str,
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_mp3)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_mp3

def apply_single_anticopyright_effect(
    input_audio: pathlib.Path,
    output_mp3: pathlib.Path,
    effect_key: str,
    midi_callback=None
) -> tuple[pathlib.Path, float]:
    """Applies exactly ONE anti-copyright effect to avoid degrading audio quality.
    Returns (output_path, time_scale_factor).
    time_scale_factor is 1.0 for all effects except Nightcore (1.05).
    """
    if effect_key == "pitch_up":
        return apply_pitch_shift(input_audio, output_mp3, semitones=1.0), 1.0
    elif effect_key == "pitch_down":
        return apply_pitch_shift(input_audio, output_mp3, semitones=-1.0), 1.0
    elif effect_key == "stage_reverb":
        return apply_stage_reverb(input_audio, output_mp3), 1.0
    elif effect_key == "lofi_warmth":
        return apply_lofi_warmth(input_audio, output_mp3), 1.0
    elif effect_key == "nightcore":
        return apply_nightcore(input_audio, output_mp3, speed_ratio=1.05), 1.05
    elif effect_key == "midi_synth":
        if midi_callback:
            return midi_callback(input_audio, output_mp3), 1.0
        return output_mp3, 1.0
    else:
        # None
        return input_audio, 1.0
