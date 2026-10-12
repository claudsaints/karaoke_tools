import subprocess
import pathlib
import numpy as np
import scipy.io.wavfile as wav
import scipy.signal as signal
import pretty_midi
from ffmpeg_utils import get_ffmpeg_path

def hz_to_midi(f: float) -> int:
    """Convert frequency in Hz to MIDI note number (21 to 108)."""
    if f <= 20:
        return 60
    note = int(round(69 + 12 * np.log2(f / 440.0)))
    return max(21, min(108, note))

def midi_to_hz(note: int) -> float:
    """Convert MIDI note number to frequency in Hz."""
    return 440.0 * (2.0 ** ((note - 69) / 12.0))

def audio_to_midi(input_audio: pathlib.Path, midi_path: pathlib.Path) -> pathlib.Path:
    """Transcribe audio to a full multi-instrument harmonic arrangement in MIDI:
    1. Bass Track: Fundamental low frequencies (35Hz - 220Hz)
    2. Harmony / Chords Track: Polyphonic mid-frequency chord layers (180Hz - 1200Hz)
    3. Lead Melody Track: Salient melodic voice line (300Hz - 2500Hz)
    4. Rhythm / Drums Track: Percussive transients (Kick 36, Snare 38, Hi-Hat 42)
    All tracks are saved in the same MIDI file.
    """
    midi_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()
    temp_wav = midi_path.with_suffix('.tmp_multi.wav')

    try:
        # Convert audio to mono 22050Hz 16-bit WAV for fast multi-band spectral analysis
        cmd = [
            ffmpeg_exe, "-y", "-i", str(input_audio),
            "-ar", "22050", "-ac", "1",
            str(temp_wav)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        sr, data = wav.read(temp_wav)
        if data.ndim > 1:
            data = data[:, 0]
        data = data.astype(np.float32) / 32768.0

        total_audio_duration = len(data) / sr

        # Compute STFT
        n_fft = 2048
        hop_length = 512
        freqs, times, Zxx = signal.stft(data, fs=sr, nperseg=n_fft, noverlap=n_fft - hop_length)
        magnitudes = np.abs(Zxx)
        n_frames = magnitudes.shape[1]

        pm = pretty_midi.PrettyMIDI()

        # ---------------- 1. BASS TRACK (Electric Bass - Program 33) ----------------
        inst_bass = pretty_midi.Instrument(program=33, name="Bass (Baixo)")
        bass_idx = np.where((freqs >= 35) & (freqs <= 220))[0]
        if len(bass_idx) > 0:
            bass_freqs = freqs[bass_idx]
            bass_mag = magnitudes[bass_idx, :]
            bass_threshold = np.mean(bass_mag) * 1.6

            curr_bass_note = None
            curr_bass_start = 0.0

            for col in range(n_frames):
                t = times[col]
                spec = bass_mag[:, col]
                peak_i = np.argmax(spec)
                if spec[peak_i] > bass_threshold:
                    note = hz_to_midi(bass_freqs[peak_i])
                    # Bass range clamp: MIDI 28 (E1) to 55 (G3)
                    note = max(28, min(55, note))
                    if curr_bass_note is None:
                        curr_bass_note = note
                        curr_bass_start = t
                    elif abs(note - curr_bass_note) > 1:
                        dur = t - curr_bass_start
                        if dur >= 0.12:
                            inst_bass.notes.append(pretty_midi.Note(
                                velocity=85, pitch=int(curr_bass_note),
                                start=float(curr_bass_start), end=float(t)
                            ))
                        curr_bass_note = note
                        curr_bass_start = t
                else:
                    if curr_bass_note is not None:
                        dur = t - curr_bass_start
                        if dur >= 0.12:
                            inst_bass.notes.append(pretty_midi.Note(
                                velocity=85, pitch=int(curr_bass_note),
                                start=float(curr_bass_start), end=float(t)
                            ))
                        curr_bass_note = None

            if curr_bass_note is not None and len(times) > 0:
                dur = times[-1] - curr_bass_start
                if dur >= 0.12:
                    inst_bass.notes.append(pretty_midi.Note(
                        velocity=85, pitch=int(curr_bass_note),
                        start=float(curr_bass_start), end=float(times[-1])
                    ))

        # ---------------- 2. HARMONY / CHORDS (Electric Piano - Program 4) ----------------
        inst_harmony = pretty_midi.Instrument(program=4, name="Harmony / Chords (Acordes)")
        harm_idx = np.where((freqs >= 180) & (freqs <= 1200))[0]
        if len(harm_idx) > 0:
            harm_freqs = freqs[harm_idx]
            harm_mag = magnitudes[harm_idx, :]
            harm_threshold = np.mean(harm_mag) * 1.4

            # Group frames into chord blocks (approx 0.25s per harmonic block)
            chord_step = max(1, int(0.25 / (hop_length / sr)))
            for col in range(0, n_frames, chord_step):
                chunk = harm_mag[:, col:min(col + chord_step, n_frames)]
                if chunk.shape[1] == 0:
                    continue
                avg_spec = np.mean(chunk, axis=1)
                peaks, props = signal.find_peaks(avg_spec, height=harm_threshold, distance=3)
                if len(peaks) > 0:
                    # Sort by amplitude and take up to 3 chord notes
                    sorted_p = sorted(peaks, key=lambda p: avg_spec[p], reverse=True)[:3]
                    chord_start = float(times[col])
                    chord_end = float(min(total_audio_duration, times[min(col + chord_step, n_frames - 1)]))
                    if chord_end - chord_start >= 0.15:
                        used_pitches = set()
                        for p in sorted_p:
                            midi_n = hz_to_midi(harm_freqs[p])
                            # Chord mid range: MIDI 48 (C3) to 84 (C6)
                            midi_n = max(48, min(84, midi_n))
                            if midi_n not in used_pitches:
                                used_pitches.add(midi_n)
                                inst_harmony.notes.append(pretty_midi.Note(
                                    velocity=75, pitch=int(midi_n),
                                    start=chord_start, end=chord_end
                                ))

        # ---------------- 3. LEAD MELODY (Acoustic Guitar - Program 24) ----------------
        inst_lead = pretty_midi.Instrument(program=24, name="Lead Melody (Melodia)")
        lead_idx = np.where((freqs >= 260) & (freqs <= 2400))[0]
        if len(lead_idx) > 0:
            lead_freqs = freqs[lead_idx]
            lead_mag = magnitudes[lead_idx, :]
            lead_threshold = np.mean(lead_mag) * 1.5

            curr_lead_note = None
            curr_lead_start = 0.0

            for col in range(n_frames):
                t = times[col]
                spec = lead_mag[:, col]
                peak_i = np.argmax(spec)
                if spec[peak_i] > lead_threshold:
                    note = hz_to_midi(lead_freqs[peak_i])
                    note = max(55, min(96, note)) # Melodic vocal/lead range
                    if curr_lead_note is None:
                        curr_lead_note = note
                        curr_lead_start = t
                    elif abs(note - curr_lead_note) > 1:
                        dur = t - curr_lead_start
                        if dur >= 0.10:
                            inst_lead.notes.append(pretty_midi.Note(
                                velocity=90, pitch=int(curr_lead_note),
                                start=float(curr_lead_start), end=float(t)
                            ))
                        curr_lead_note = note
                        curr_lead_start = t
                else:
                    if curr_lead_note is not None:
                        dur = t - curr_lead_start
                        if dur >= 0.10:
                            inst_lead.notes.append(pretty_midi.Note(
                                velocity=90, pitch=int(curr_lead_note),
                                start=float(curr_lead_start), end=float(t)
                            ))
                        curr_lead_note = None

            if curr_lead_note is not None and len(times) > 0:
                dur = times[-1] - curr_lead_start
                if dur >= 0.10:
                    inst_lead.notes.append(pretty_midi.Note(
                        velocity=90, pitch=int(curr_lead_note),
                        start=float(curr_lead_start), end=float(times[-1])
                    ))

        # ---------------- 4. DRUMS / RHYTHM (Channel 10, is_drum=True) ----------------
        inst_drums = pretty_midi.Instrument(program=0, is_drum=True, name="Drums (Bateria)")
        
        # Detect rhythmic energy transients across sub-bass (Kick) and high (Hi-Hat)
        kick_idx = np.where((freqs >= 40) & (freqs <= 110))[0]
        hat_idx = np.where((freqs >= 4500) & (freqs <= 9000))[0]

        if len(kick_idx) > 0 and len(hat_idx) > 0:
            kick_energy = np.mean(magnitudes[kick_idx, :], axis=0)
            hat_energy = np.mean(magnitudes[hat_idx, :], axis=0)

            # Detect onsets using spectral difference
            kick_diff = np.diff(kick_energy, prepend=kick_energy[0])
            kick_diff = np.maximum(0, kick_diff)
            hat_diff = np.diff(hat_energy, prepend=hat_energy[0])
            hat_diff = np.maximum(0, hat_diff)

            k_threshold = np.mean(kick_diff) * 2.5
            h_threshold = np.mean(hat_diff) * 2.2

            min_drum_dist = int(0.18 / (hop_length / sr))

            k_peaks, _ = signal.find_peaks(kick_diff, height=k_threshold, distance=min_drum_dist)
            h_peaks, _ = signal.find_peaks(hat_diff, height=h_threshold, distance=min_drum_dist)

            for kp in k_peaks:
                t = float(times[kp])
                inst_drums.notes.append(pretty_midi.Note(
                    velocity=100, pitch=36, # Bass Drum / Kick
                    start=t, end=t + 0.08
                ))

            for hp in h_peaks:
                t = float(times[hp])
                inst_drums.notes.append(pretty_midi.Note(
                    velocity=80, pitch=42, # Closed Hi-Hat
                    start=t, end=t + 0.05
                ))

        # Add all instruments to MIDI container
        pm.instruments.extend([inst_bass, inst_harmony, inst_lead, inst_drums])
        pm.write(str(midi_path))
        return midi_path

    finally:
        if temp_wav.exists():
            temp_wav.unlink(missing_ok=True)

def midi_to_synth_mp3(midi_path: pathlib.Path, output_mp3: pathlib.Path) -> pathlib.Path:
    """Synthesize multi-instrument MIDI into an acoustic/synth arrangement:
    - Bass: Deep sub-harmonic punch and sustain
    - Harmony: Polyphonic Electric Piano with warm chorus harmonics
    - Lead: Crisp melodic guitar/synth timbre
    - Drums: Synthesized Kick (pitch drop) and Hi-Hat (metallic click)
    Mixes all layers into a complete harmonic backing track.
    """
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    pm = pretty_midi.PrettyMIDI(str(midi_path))

    sr = 44100
    total_time = pm.get_end_time() + 0.5
    if total_time <= 0:
        total_time = 5.0

    total_samples = int(total_time * sr)
    buffer = np.zeros(total_samples, dtype=np.float32)

    for inst in pm.instruments:
        is_bass = "bass" in inst.name.lower() or inst.program in [32, 33, 34, 35]
        is_harm = "harm" in inst.name.lower() or "chord" in inst.name.lower() or inst.program in [0, 4, 5]
        is_drum = inst.is_drum

        for note in inst.notes:
            start_s = int(note.start * sr)
            dur_s = int((note.end - note.start) * sr)
            if start_s >= total_samples or dur_s <= 0:
                continue

            end_s = min(start_s + dur_s, total_samples)
            actual_dur = end_s - start_s
            t = np.linspace(0, actual_dur / sr, actual_dur, endpoint=False)

            if is_drum:
                # Drum synthesis
                if note.pitch == 36: # Kick
                    # Frequency drop from 130Hz to 45Hz
                    kick_f = np.linspace(130, 45, actual_dur)
                    phase = 2 * np.pi * np.cumsum(kick_f) / sr
                    drum_env = np.exp(-t * 22.0)
                    wave = np.sin(phase) * drum_env * 1.2
                else: # Hi-hat
                    noise = (np.random.rand(actual_dur) * 2.0 - 1.0)
                    hat_env = np.exp(-t * 80.0)
                    wave = noise * hat_env * 0.5
                gain = (note.velocity / 127.0) * 0.40
                buffer[start_s:end_s] += (wave * gain)

            elif is_bass:
                # Deep bass sound: Fundamental + 2nd harmonic
                freq = midi_to_hz(note.pitch)
                wave = (
                    1.0 * np.sin(2 * np.pi * freq * t) +
                    0.4 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 1.5)
                )
                # Smooth bass envelope
                att = min(int(0.01 * sr), actual_dur // 2)
                rel = min(int(0.05 * sr), actual_dur // 2)
                env = np.ones(actual_dur, dtype=np.float32)
                if att > 0:
                    env[:att] = np.linspace(0, 1, att)
                if rel > 0:
                    env[-rel:] = np.linspace(1, 0, rel)
                gain = (note.velocity / 127.0) * 0.38
                buffer[start_s:end_s] += (wave * env * gain)

            elif is_harm:
                # Polyphonic Chords: Electric Piano warmth
                freq = midi_to_hz(note.pitch)
                wave = (
                    0.8 * np.sin(2 * np.pi * freq * t) +
                    0.4 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 1.0) +
                    0.2 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t * 2.0)
                )
                att = min(int(0.02 * sr), actual_dur // 2)
                rel = min(int(0.08 * sr), actual_dur // 2)
                env = np.ones(actual_dur, dtype=np.float32)
                if att > 0:
                    env[:att] = np.linspace(0, 1, att)
                if rel > 0:
                    env[-rel:] = np.linspace(1, 0, rel)
                gain = (note.velocity / 127.0) * 0.25
                buffer[start_s:end_s] += (wave * env * gain)

            else:
                # Lead Melody (Guitar/Synth)
                freq = midi_to_hz(note.pitch)
                wave = (
                    0.9 * np.sin(2 * np.pi * freq * t) +
                    0.5 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 2.5) +
                    0.3 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t * 3.5)
                )
                att = min(int(0.015 * sr), actual_dur // 2)
                rel = min(int(0.05 * sr), actual_dur // 2)
                env = np.ones(actual_dur, dtype=np.float32)
                if att > 0:
                    env[:att] = np.linspace(0, 1, att)
                if rel > 0:
                    env[-rel:] = np.linspace(1, 0, rel)
                gain = (note.velocity / 127.0) * 0.32
                buffer[start_s:end_s] += (wave * env * gain)

    # Normalize audio
    max_val = np.max(np.abs(buffer))
    if max_val > 1e-4:
        buffer = (buffer / max_val) * 0.90

    int_audio = (buffer * 32767).astype(np.int16)
    temp_wav = output_mp3.with_suffix('.syn_multi_tmp.wav')
    wav.write(temp_wav, sr, int_audio)

    ffmpeg_exe = get_ffmpeg_path()
    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(temp_wav),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_mp3)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    temp_wav.unlink(missing_ok=True)
    return output_mp3
