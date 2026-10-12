import sys
import argparse
import pathlib
from downloader import download_mp3
from lyric_fetcher import fetch_lrc_lrclib
from clipper import trim_mp3
from vocal_remover import remove_vocals
from midi_converter import audio_to_midi, midi_to_synth_mp3
from audio_effects import apply_single_anticopyright_effect
from lua_generator import slugify, process_lyrics_timestamps, export_outputs

def time_to_seconds(val: str) -> float:
    if ":" in val:
        parts = val.split(":")
        return float(parts[0]) * 60 + float(parts[1])
    return float(val)

def main():
    if len(sys.argv) == 1:
        import gui
        gui.main()
        return

    parser = argparse.ArgumentParser(description="KBR Karaoke - Automação de corte e sincronização para Roblox")
    parser.add_argument("--url", help="URL do vídeo no YouTube")
    parser.add_argument("--input", help="Arquivo de áudio local existente (MP3/WAV)")
    parser.add_argument("--title", required=False, default="Musica", help="Título da música")
    parser.add_argument("--artist", required=False, default="Artista", help="Nome do artista")
    parser.add_argument("--genre", required=False, default="ACUSTICO/MPB", help="Gênero da música")
    parser.add_argument("--start", required=False, default="00:00", help="Tempo inicial de corte do áudio (mm:ss ou segundos)")
    parser.add_argument("--end", required=False, default="01:00", help="Tempo final de corte do áudio (mm:ss ou segundos)")
    parser.add_argument("--v-start", required=False, default=None, help="Tempo do primeiro verso da letra")
    parser.add_argument("--v-end", required=False, default=None, help="Tempo do último verso da letra")
    parser.add_argument("--offset", type=float, default=0.0, help="Offset manual da letra em segundos")
    parser.add_argument("--vocal-mode", choices=["none", "demucs", "audio_separator", "aggressive", "standard"], default="none", help="Modo de remoção de vocais")
    parser.add_argument("--anti-copyright", choices=["none", "pitch_up", "pitch_down", "stage_reverb", "lofi_warmth", "nightcore", "midi_synth"], default="none", help="Efeito anti-copyright exclusivo")
    parser.add_argument("--output-dir", default="music/generated_output", help="Diretório de saída")
    parser.add_argument("--gui", action="store_true", help="Abrir interface gráfica")

    args = parser.parse_args()

    if args.gui:
        import gui
        gui.main()
        return

    out_dir = pathlib.Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    song_id = f"{slugify(args.title)}_01"
    start_sec = time_to_seconds(args.start)
    end_sec = time_to_seconds(args.end)
    v_start_sec = time_to_seconds(args.v_start) if args.v_start else start_sec
    v_end_sec = time_to_seconds(args.v_end) if args.v_end else end_sec

    print(f"[*] Processando: {args.title} - {args.artist}")

    # 1. Obter áudio
    if args.input:
        source_audio = pathlib.Path(args.input)
    elif args.url:
        print("[*] Baixando áudio do YouTube...")
        raw_mp3 = out_dir / f"{song_id}_original.mp3"
        download_mp3(args.url, raw_mp3)
        source_audio = raw_mp3
    else:
        print("Erro: especifique --url ou --input.")
        sys.exit(1)

    # 2. Cortar áudio
    print(f"[*] Cortando áudio de {args.start} até {args.end}...")
    trimmed_mp3 = out_dir / f"{song_id}.mp3"
    trim_mp3(source_audio, start_sec, end_sec, trimmed_mp3)
    current_mp3 = trimmed_mp3

    # 3. Remover vocal se solicitado
    if args.vocal_mode != "none":
        print(f"[*] Removendo vocais ({args.vocal_mode})...")
        vocal_out = out_dir / f"{song_id}_karaoke.mp3"
        remove_vocals(current_mp3, vocal_out, mode=args.vocal_mode)
        current_mp3 = vocal_out

    # 4. Anti-Copyright (Apenas 1 efeito!)
    time_scale = 1.0
    if args.anti_copyright != "none":
        print(f"[*] Aplicando efeito anti-copyright: {args.anti_copyright}...")
        eff_mp3 = out_dir / f"{song_id}_anticopy.mp3"

        def _midi_cb(in_p, out_p):
            mid_file = out_dir / f"{song_id}.mid"
            audio_to_midi(in_p, mid_file)
            return midi_to_synth_mp3(mid_file, out_p)

        res_audio, time_scale = apply_single_anticopyright_effect(
            current_mp3,
            eff_mp3,
            effect_key=args.anti_copyright,
            midi_callback=_midi_cb
        )
        current_mp3 = res_audio

    # 5. Buscar letra no lrclib.net
    print("[*] Buscando letra no lrclib.net...")
    try:
        raw_lrc, parsed_lyrics = fetch_lrc_lrclib(title=args.title, artist=args.artist)
    except Exception as e:
        print(f"[!] Aviso: Não foi possível obter letra no lrclib: {e}")
        parsed_lyrics = []

    # 6. Processar tempos relativos com suporte a offset e escala
    processed_lyrics = process_lyrics_timestamps(
        parsed_lyrics,
        verse_start_sec=v_start_sec,
        verse_end_sec=v_end_sec,
        audio_start_sec=start_sec,
        align_first_verse_zero=True,
        offset_sec=args.offset,
        time_scale=time_scale
    )

    duration = (end_sec - start_sec) / time_scale
    res = export_outputs(
        out_dir=out_dir,
        song_id=song_id,
        title=args.title,
        artist=args.artist,
        genre=args.genre,
        duration=duration,
        lyrics_processed=processed_lyrics
    )

    print(f"\n[+] Concluído com sucesso em {out_dir.resolve()}!")
    print(f"[+] Áudio final: {current_mp3.name}")
    print(f"[+] Código Roblox gerado:")
    print("-" * 50)
    print(res["lua_code"])
    print("-" * 50)

if __name__ == "__main__":
    main()
