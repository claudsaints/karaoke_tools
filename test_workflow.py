import os
import pathlib
import numpy as np
import scipy.io.wavfile as wav
import subprocess

from ffmpeg_utils import get_ffmpeg_path
from lyric_fetcher import search_lrclib, parse_lrc_content, format_seconds_to_tag
from clipper import trim_mp3
from vocal_remover import remove_vocals
from midi_converter import audio_to_midi, midi_to_synth_mp3
from audio_effects import apply_pitch_shift, apply_stage_reverb, apply_lofi_warmth, apply_nightcore, apply_single_anticopyright_effect
from lua_generator import slugify, process_lyrics_timestamps, generate_roblox_lua, export_outputs

def test_ffmpeg_available():
    ffmpeg_exe = get_ffmpeg_path()
    assert os.path.exists(ffmpeg_exe), f"FFmpeg not found: {ffmpeg_exe}"

def test_slugify():
    assert slugify("João e Maria") == "joao_e_maria"
    assert slugify("Garota de Ipanema!") == "garota_de_ipanema"

def test_decoupled_lrc_and_roblox_lua():
    sample_lrc = """
    [01:15.50] Não, não fuja não
    [01:18.10] Finja que agora eu era o seu brinquedo
    [01:22.00] Eu era o seu pião
    [01:26.20] O seu bicho preferido
    [01:50.00] Verso fora do corte
    """
    entries = parse_lrc_content(sample_lrc)
    assert len(entries) == 5

    # Test independent audio cut (starts at 70s) vs lyric verses (starts at 75.5s)
    processed = process_lyrics_timestamps(
        entries,
        verse_start_sec=75.0,
        verse_end_sec=90.0,
        audio_start_sec=70.0,
        align_first_verse_zero=True,
        offset_sec=0.0
    )
    assert len(processed) == 4
    # First line must be 0.0
    assert processed[0]["tempo"] == 0.0
    assert processed[0]["texto"] == "Não, não fuja não"
    # Second line: 78.10 - 75.50 = 2.6
    assert processed[1]["tempo"] == 2.6

    # Test Roblox Lua format
    lua = generate_roblox_lua(
        song_id="joao_e_maria_01",
        title="João e Maria",
        artist="Chico Buarque",
        genre="ACUSTICO/MPB",
        duration=52.0,
        lyrics=processed
    )
    assert '["joao_e_maria_01"] = {' in lua
    assert 'Title = "João e Maria",' in lua
    assert '{tempo = 0.0, texto = "Não, não fuja não"},' in lua
    assert '{tempo = 2.6, texto = "Finja que agora eu era o seu brinquedo"},' in lua

def test_audio_pipeline_and_effects(tmp_path):
    sr = 44100
    t = np.linspace(0, 3.0, int(sr * 3.0), endpoint=False)
    ch_l = (0.5 * np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 880 * t)) * 32767
    ch_r = (0.5 * np.sin(2 * np.pi * 440 * t)) * 32767
    stereo = np.column_stack((ch_l.astype(np.int16), ch_r.astype(np.int16)))

    src_wav = tmp_path / "test_source.wav"
    wav.write(src_wav, sr, stereo)

    # 1. Trim audio
    trimmed_mp3 = tmp_path / "test_trimmed.mp3"
    trim_mp3(src_wav, start_sec=0.5, end_sec=2.5, out_path=trimmed_mp3)
    assert trimmed_mp3.exists()

    # 2. Vocal removal (both modes)
    vocal_std = tmp_path / "test_vocal_std.mp3"
    remove_vocals(trimmed_mp3, vocal_std, mode="standard")
    assert vocal_std.exists()

    vocal_agg = tmp_path / "test_vocal_agg.mp3"
    remove_vocals(trimmed_mp3, vocal_agg, mode="aggressive")
    assert vocal_agg.exists()

    # 3. Anti-copyright effects
    pitch_mp3 = tmp_path / "test_pitch.mp3"
    apply_pitch_shift(trimmed_mp3, pitch_mp3, semitones=1.0)
    assert pitch_mp3.exists()

    reverb_mp3 = tmp_path / "test_reverb.mp3"
    apply_stage_reverb(trimmed_mp3, reverb_mp3)
    assert reverb_mp3.exists()

    lofi_mp3 = tmp_path / "test_lofi.mp3"
    apply_lofi_warmth(trimmed_mp3, lofi_mp3)
    assert lofi_mp3.exists()

    nightcore_mp3 = tmp_path / "test_nightcore.mp3"
    apply_nightcore(trimmed_mp3, nightcore_mp3, speed_ratio=1.05)
    assert nightcore_mp3.exists()

    # 4. MIDI transcription & synth
    midi_file = tmp_path / "test.mid"
    audio_to_midi(trimmed_mp3, midi_file)
    assert midi_file.exists()

    synth_mp3 = tmp_path / "test_synth.mp3"
    midi_to_synth_mp3(midi_file, synth_mp3)
    assert synth_mp3.exists()

if __name__ == "__main__":
    print("Executando testes da nova suíte...")
    test_ffmpeg_available()
    print("FFmpeg: OK")
    test_slugify()
    print("Slugify: OK")
    test_decoupled_lrc_and_roblox_lua()
    print("Corte desacoplado e Roblox Lua: OK")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        test_audio_pipeline_and_effects(pathlib.Path(td))
    print("Efeitos Anti-Copyright e Separação Vocal: OK")
    print("Todos os testes passaram com sucesso!")
