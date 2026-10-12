import sys
import subprocess
import pathlib
import tempfile
from ffmpeg_utils import get_ffmpeg_path

def remove_vocals_demucs(input_audio: pathlib.Path, output_mp3: pathlib.Path) -> pathlib.Path:
    """Uses Meta's Demucs deep learning model (HTDemucs) to extract instrumental.
    Runs with --two-stems vocals for optimal speed.
    """
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)
        cmd = [
            sys.executable, "-m", "demucs.separate",
            "--two-stems", "vocals",
            "-n", "htdemucs",
            "-o", str(tmp_path),
            str(input_audio)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Erro ao executar Demucs:\n{result.stderr or result.stdout}")

        # Locate no_vocals.wav
        found = list(tmp_path.rglob("no_vocals.wav"))
        if not found:
            raise FileNotFoundError("O Demucs não encontrou ou não gerou o arquivo instrumental (no_vocals.wav).")

        conv_cmd = [
            ffmpeg_exe, "-y",
            "-i", str(found[0]),
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(output_mp3)
        ]
        subprocess.run(conv_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return output_mp3

def remove_vocals_audio_separator(input_audio: pathlib.Path, output_mp3: pathlib.Path) -> pathlib.Path:
    """Uses Audio Separator (UVR / MDX-Net ONNX) to extract high-quality instrumental."""
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()

    from audio_separator.separator import Separator

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)
        separator = Separator(output_dir=str(tmp_path), output_format="WAV")
        separator.load_model(model_filename="UVR-MDX-NET-Inst_HQ_3.onnx")
        outputs = separator.separate(str(input_audio))

        inst_file = None
        for f in outputs:
            f_lower = f.lower()
            if "instrumental" in f_lower or "inst" in f_lower or "no_vocals" in f_lower:
                inst_file = tmp_path / f
                break

        if not inst_file and outputs:
            for f in outputs:
                if "vocal" not in f.lower():
                    inst_file = tmp_path / f
                    break

        if not inst_file and outputs:
            inst_file = tmp_path / outputs[0]

        if not inst_file or not inst_file.exists():
            raise FileNotFoundError("O Audio Separator não gerou o arquivo instrumental.")

        conv_cmd = [
            ffmpeg_exe, "-y",
            "-i", str(inst_file),
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(output_mp3)
        ]
        subprocess.run(conv_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return output_mp3

def remove_vocals(input_audio: pathlib.Path, output_mp3: pathlib.Path, mode: str = "aggressive") -> pathlib.Path:
    """Removes vocals using the selected method:
    - 'demucs': Meta's HTDemucs AI neural network (State-of-the-art separation)
    - 'audio_separator': UVR / MDX-Net ONNX neural network
    - 'aggressive': 3-Band separation + vocal formant notch suppression (fast via FFmpeg)
    - 'standard': Stereo phase subtraction with bass preservation (fast via FFmpeg)
    """
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()

    if mode == "demucs":
        return remove_vocals_demucs(input_audio, output_mp3)
    elif mode == "audio_separator":
        return remove_vocals_audio_separator(input_audio, output_mp3)

    if mode == "aggressive":
        filter_complex = (
            "[0:a]asplit=3[bass][mid][air]; "
            "[bass]lowpass=f=160[bassout]; "
            "[mid]highpass=f=160,lowpass=f=8000,pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c1-0.5*c0,equalizer=f=2400:t=q:w=1.8:g=-8[midout]; "
            "[air]highpass=f=8000[airout]; "
            "[bassout][midout][airout]amix=inputs=3:weights=1.2 1.0 0.9,volume=1.7"
        )
    else:
        filter_complex = (
            "[0:a]asplit=2[bass][mids]; "
            "[bass]lowpass=f=150[bassout]; "
            "[mids]highpass=f=150,pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c1-0.5*c0[instout]; "
            "[bassout][instout]amix=inputs=2:weights=1.1 1.0,volume=1.5"
        )

    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", str(input_audio),
        "-filter_complex", filter_complex,
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_mp3)
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        fallback_cmd = [
            ffmpeg_exe,
            "-y",
            "-i", str(input_audio),
            "-af", "stereotools=mlev=0.01",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(output_mp3)
        ]
        fallback_res = subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if fallback_res.returncode != 0:
            raise RuntimeError(f"Erro ao remover vocal com FFmpeg: {result.stderr}")

    return output_mp3
