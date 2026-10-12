import os
import sys
import math
import pathlib
import threading
import winsound
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from ffmpeg_utils import get_ffmpeg_path
from downloader import get_video_metadata, download_mp3, search_youtube_karaoke
from lyric_fetcher import search_lrclib, parse_lrc_content, format_seconds_to_tag
from clipper import trim_mp3
from vocal_remover import remove_vocals
from midi_converter import audio_to_midi, midi_to_synth_mp3
from audio_effects import apply_single_anticopyright_effect
from lua_generator import slugify, process_lyrics_timestamps, export_outputs

def time_str_to_seconds(time_str: str) -> float:
    """Parse 'mm:ss' or 'ss' or 'mm:ss.xx' to float seconds."""
    time_str = str(time_str).strip()
    if not time_str:
        return 0.0
    if ":" in time_str:
        parts = time_str.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return float(time_str)

def seconds_to_mmss(total_seconds: float) -> str:
    """Format float seconds into 'mm:ss' string."""
    mins = int(total_seconds // 60)
    secs = int(total_seconds % 60)
    return f"{mins:02d}:{secs:02d}"

class KaraokeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KBR Karaoke - Gerador e Sincronizador para Roblox")
        self.geometry("1020x860")
        self.minsize(880, 720)

        # Output folder
        self.output_dir = pathlib.Path(__file__).parent / "music" / "generated_output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # State
        self.parsed_lyrics = []
        self.downloaded_source_mp3 = None
        self.current_preview_file = None
        self.is_playing = False

        self._init_styles()
        self._build_ui()

    def _init_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TLabel", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9))
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))

    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ---------------- Section 1: Audio Source ----------------
        sec1 = ttk.LabelFrame(main_frame, text=" 1. Fonte do Áudio (YouTube ou Arquivo Local) ", padding=8)
        sec1.pack(fill=tk.X, pady=(0, 6))

        row1 = ttk.Frame(sec1)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="URL do YouTube:").pack(side=tk.LEFT, padx=(0, 6))
        self.entry_url = ttk.Entry(row1, width=50)
        self.entry_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        
        self.btn_fetch_info = ttk.Button(row1, text="⚡ Identificar Vídeo", command=self.on_fetch_youtube_info)
        self.btn_fetch_info.pack(side=tk.LEFT, padx=3)

        self.btn_search_karaoke_yt = ttk.Button(row1, text="🎤 Buscar Playback no YouTube", command=self.on_search_karaoke_yt)
        self.btn_search_karaoke_yt.pack(side=tk.LEFT, padx=3)

        ttk.Label(row1, text="OU").pack(side=tk.LEFT, padx=6)
        self.btn_browse_local = ttk.Button(row1, text="📂 MP3 do PC", command=self.on_browse_local_audio)
        self.btn_browse_local.pack(side=tk.LEFT)

        self.lbl_local_audio = ttk.Label(sec1, text="Nenhum arquivo local selecionado.", foreground="#555555")
        self.lbl_local_audio.pack(anchor="w", pady=(2, 0))

        # ---------------- Section 2: Song Metadata ----------------
        sec2 = ttk.LabelFrame(main_frame, text=" 2. Metadados do Jogo (Roblox) ", padding=8)
        sec2.pack(fill=tk.X, pady=(0, 6))

        meta_grid = ttk.Frame(sec2)
        meta_grid.pack(fill=tk.X)

        ttk.Label(meta_grid, text="Título:").grid(row=0, column=0, sticky="w", padx=3, pady=2)
        self.entry_title = ttk.Entry(meta_grid, width=28)
        self.entry_title.grid(row=0, column=1, sticky="ew", padx=3, pady=2)
        self.entry_title.bind("<KeyRelease>", self.on_title_change)

        ttk.Label(meta_grid, text="Artista:").grid(row=0, column=2, sticky="w", padx=3, pady=2)
        self.entry_artist = ttk.Entry(meta_grid, width=24)
        self.entry_artist.grid(row=0, column=3, sticky="ew", padx=3, pady=2)

        ttk.Label(meta_grid, text="Gênero:").grid(row=0, column=4, sticky="w", padx=3, pady=2)
        self.combo_genre = ttk.Combobox(meta_grid, width=16, values=[
            "ACUSTICO/MPB", "POP", "SERTANEJO", "ROCK", "FUNK", "TRAP", "RAP", "GOSPEL", "OUTRO"
        ])
        self.combo_genre.set("ACUSTICO/MPB")
        self.combo_genre.grid(row=0, column=5, sticky="ew", padx=3, pady=2)

        ttk.Label(meta_grid, text="ID Música:").grid(row=1, column=0, sticky="w", padx=3, pady=2)
        self.entry_song_id = ttk.Entry(meta_grid, width=28)
        self.entry_song_id.grid(row=1, column=1, sticky="ew", padx=3, pady=2)

        ttk.Label(meta_grid, text="SoundId:").grid(row=1, column=2, sticky="w", padx=3, pady=2)
        self.entry_sound_id = ttk.Entry(meta_grid, width=24)
        self.entry_sound_id.insert(0, "rbxassetid://COLOQUE_SEU_AUDIO_AQUI")
        self.entry_sound_id.grid(row=1, column=3, sticky="ew", padx=3, pady=2)

        ttk.Label(meta_grid, text="IconId:").grid(row=1, column=4, sticky="w", padx=3, pady=2)
        self.entry_icon_id = ttk.Entry(meta_grid, width=16)
        self.entry_icon_id.insert(0, "rbxassetid://123677416568279")
        self.entry_icon_id.grid(row=1, column=5, sticky="ew", padx=3, pady=2)

        meta_grid.columnconfigure(1, weight=1)
        meta_grid.columnconfigure(3, weight=1)
        meta_grid.columnconfigure(5, weight=1)

        # ---------------- Section 3: Lyrics & Cutting ----------------
        sec3 = ttk.LabelFrame(main_frame, text=" 3. Letra e Controles de Corte (Manual ou Automático) ", padding=8)
        sec3.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        lyric_top = ttk.Frame(sec3)
        lyric_top.pack(fill=tk.X, pady=(0, 4))

        self.btn_fetch_lyrics = ttk.Button(lyric_top, text="🔍 Buscar Letra no lrclib.net", command=self.on_fetch_lyrics)
        self.btn_fetch_lyrics.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_load_lrc_file = ttk.Button(lyric_top, text="📂 Abrir .LRC Local", command=self.on_load_lrc_file)
        self.btn_load_lrc_file.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_lyrics_status = ttk.Label(lyric_top, text="Busque a letra para listar os versos.", foreground="#444444")
        self.lbl_lyrics_status.pack(side=tk.LEFT, padx=4)

        # Table showing lyrics
        table_container = ttk.Frame(sec3)
        table_container.pack(fill=tk.BOTH, expand=True)

        columns = ("time", "text")
        self.lyrics_tree = ttk.Treeview(table_container, columns=columns, show="headings", height=6, selectmode="browse")
        self.lyrics_tree.heading("time", text="Tempo Original")
        self.lyrics_tree.heading("text", text="Verso da Música")
        self.lyrics_tree.column("time", width=105, anchor="center")
        self.lyrics_tree.column("text", width=720, anchor="w")

        tree_scroll = ttk.Scrollbar(table_container, orient="vertical", command=self.lyrics_tree.yview)
        self.lyrics_tree.configure(yscrollcommand=tree_scroll.set)
        self.lyrics_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Separation of Verse Selection vs Audio Cut
        ctrl_frame = ttk.Frame(sec3)
        ctrl_frame.pack(fill=tk.X, pady=(6, 0))

        # Row 1: Verse Selection buttons & Auto-sync checkbox
        v_sel_row = ttk.Frame(ctrl_frame)
        v_sel_row.pack(fill=tk.X, pady=(0, 4))

        self.btn_mark_v_start = ttk.Button(v_sel_row, text="📍 Marcar como 1º Verso da Letra", command=self.on_mark_verse_start)
        self.btn_mark_v_start.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_mark_v_end = ttk.Button(v_sel_row, text="🏁 Marcar como Último Verso da Letra", command=self.on_mark_verse_end)
        self.btn_mark_v_end.pack(side=tk.LEFT, padx=(0, 12))

        self.var_auto_sync_cut = tk.BooleanVar(value=True)
        self.chk_auto_sync = ttk.Checkbutton(
            v_sel_row,
            text="⚡ Sincronizar Corte do Áudio automaticamente com os versos",
            variable=self.var_auto_sync_cut
        )
        self.chk_auto_sync.pack(side=tk.LEFT)

        # Row 2: Inputs for Audio Cut and Lyric Verses
        times_row = ttk.Frame(ctrl_frame)
        times_row.pack(fill=tk.X, pady=(2, 0))

        # Audio Cut Section
        ttk.Label(times_row, text="Corte Áudio Início:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 2))
        self.entry_audio_start = ttk.Entry(times_row, width=8)
        self.entry_audio_start.insert(0, "00:00")
        self.entry_audio_start.pack(side=tk.LEFT, padx=(0, 8))
        self.entry_audio_start.bind("<KeyRelease>", self.update_duration_display)

        ttk.Label(times_row, text="Corte Áudio Fim:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 2))
        self.entry_audio_end = ttk.Entry(times_row, width=8)
        self.entry_audio_end.insert(0, "00:00")
        self.entry_audio_end.pack(side=tk.LEFT, padx=(0, 12))
        self.entry_audio_end.bind("<KeyRelease>", self.update_duration_display)

        # Verse Boundaries
        ttk.Label(times_row, text="Verso Início:").pack(side=tk.LEFT, padx=(0, 2))
        self.entry_v_start = ttk.Entry(times_row, width=8)
        self.entry_v_start.insert(0, "00:00")
        self.entry_v_start.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(times_row, text="Verso Fim:").pack(side=tk.LEFT, padx=(0, 2))
        self.entry_v_end = ttk.Entry(times_row, width=8)
        self.entry_v_end.insert(0, "00:00")
        self.entry_v_end.pack(side=tk.LEFT, padx=(0, 12))

        # Offset / Delay
        ttk.Label(times_row, text="Offset/Delay (s):").pack(side=tk.LEFT, padx=(0, 2))
        self.entry_offset = ttk.Entry(times_row, width=6)
        self.entry_offset.insert(0, "0.0")
        self.entry_offset.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_calc_duration = ttk.Label(times_row, text="Duração Áudio: 0s", font=("Segoe UI", 9, "bold"), foreground="#000088")
        self.lbl_calc_duration.pack(side=tk.LEFT)

        # ---------------- Section 4: Options & Anti-Copyright ----------------
        sec4 = ttk.Frame(main_frame)
        sec4.pack(fill=tk.X, pady=(0, 6))

        opt_frame = ttk.LabelFrame(sec4, text=" 4. Separação de Vocal & Anti-Copyright ", padding=8)
        opt_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        # Vocal Removal Mode
        voc_row = ttk.Frame(opt_frame)
        voc_row.pack(fill=tk.X, pady=2)
        ttk.Label(voc_row, text="Remoção de Vocais:").pack(side=tk.LEFT, padx=(0, 6))
        self.combo_vocal_mode = ttk.Combobox(voc_row, width=48, state="readonly", values=[
            "Desativado (Manter áudio original / já é playback)",
            "Demucs IA (Separação Neural Profunda - Meta)",
            "Audio Separator IA (UVR / MDX-Net ONNX)",
            "Remoção Rápida Agressiva (Multi-Band + Supressão Formantes)",
            "Remoção Rápida Padrão (Cancelamento Central Estéreo)"
        ])
        self.combo_vocal_mode.current(0)
        self.combo_vocal_mode.pack(side=tk.LEFT)

        # Mutually Exclusive Anti-Copyright Option
        cp_row = ttk.Frame(opt_frame)
        cp_row.pack(fill=tk.X, pady=4)
        ttk.Label(cp_row, text="Anti-Copyright (Roblox):").pack(side=tk.LEFT, padx=(0, 6))
        self.combo_anticopyright = ttk.Combobox(cp_row, width=44, state="readonly", values=[
            "Nenhum (Áudio normal / sem modificação)",
            "Alteração de Tom (+1 Semitom / Pitch Up) [Nítido]",
            "Alteração de Tom (-1 Semitom / Pitch Down) [Nítido]",
            "Ambiência de Palco / Sala de Karaokê (Reverb + Stereo)",
            "Estilo Lo-Fi Vintage / Tape Warmth (Aesthetic)",
            "Velocidade Nightcore (+5% Aceleração)",
            "Sintetizador MIDI (Notas Sintetizadas)"
        ])
        self.combo_anticopyright.current(0)
        self.combo_anticopyright.pack(side=tk.LEFT)

        self.var_align_zero = tk.BooleanVar(value=True)
        self.chk_align = ttk.Checkbutton(
            opt_frame, text="⏱ Iniciar 1º verso selecionado em 0.0s (sincronização relativa automática)",
            variable=self.var_align_zero
        )
        self.chk_align.pack(anchor="w", pady=(2, 0))

        # Main Action Button Frame
        action_frame = ttk.Frame(sec4)
        action_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.btn_run = tk.Button(
            action_frame,
            text="⚡ GERAR KARAOKE COMPLETO\n(Áudio MP3 + Roblox Lua em Segundos)",
            bg="#2e7d32",
            fg="white",
            activebackground="#1b5e20",
            activeforeground="white",
            font=("Segoe UI", 11, "bold"),
            relief="raised",
            bd=3,
            cursor="hand2",
            command=self.on_start_full_process
        )
        self.btn_run.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Progress bar & Status label
        self.progress_bar = ttk.Progressbar(main_frame, mode="indeterminate")
        self.progress_bar.pack(fill=tk.X, pady=(0, 3))

        self.lbl_status = ttk.Label(main_frame, text="Pronto para processar.", font=("Segoe UI", 9, "italic"))
        self.lbl_status.pack(anchor="w", pady=(0, 4))

        # ---------------- Section 5: Roblox Output & Controls ----------------
        sec5 = ttk.LabelFrame(main_frame, text=" 5. Código Roblox Gerado (format.txt) ", padding=8)
        sec5.pack(fill=tk.BOTH, expand=True)

        out_btn_bar = ttk.Frame(sec5)
        out_btn_bar.pack(fill=tk.X, pady=(0, 4))

        self.btn_copy_lua = ttk.Button(out_btn_bar, text="📋 Copiar Código Roblox", command=self.on_copy_lua)
        self.btn_copy_lua.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_open_folder = ttk.Button(out_btn_bar, text="📁 Abrir Pasta no Explorer", command=self.on_open_output_folder)
        self.btn_open_folder.pack(side=tk.LEFT, padx=(0, 15))

        self.btn_play_audio = ttk.Button(out_btn_bar, text="▶ Ouvir Áudio Cortado", command=self.on_play_preview)
        self.btn_play_audio.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_stop_audio = ttk.Button(out_btn_bar, text="⏹ Parar Áudio", command=self.on_stop_preview)
        self.btn_stop_audio.pack(side=tk.LEFT)

        self.text_lua_output = tk.Text(sec5, height=8, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4", insertbackground="white")
        self.text_lua_output.pack(fill=tk.BOTH, expand=True)

    # ---------------- Event Handlers ----------------

    def on_title_change(self, event=None):
        title = self.entry_title.get().strip()
        if title:
            suggested_id = f"{slugify(title)}_01"
            self.entry_song_id.delete(0, tk.END)
            self.entry_song_id.insert(0, suggested_id)

    def on_browse_local_audio(self):
        file_path = filedialog.askopenfilename(
            title="Selecione a música em MP3 ou WAV",
            filetypes=[("Arquivos de Áudio", "*.mp3 *.wav *.m4a *.aac *.ogg"), ("Todos os Arquivos", "*.*")]
        )
        if file_path:
            p = pathlib.Path(file_path)
            self.downloaded_source_mp3 = p
            self.lbl_local_audio.config(text=f"Arquivo selecionado: {p.name}", foreground="#006600")
            stem = p.stem
            if not self.entry_title.get():
                if " - " in stem:
                    parts = stem.split(" - ", 1)
                    self.entry_artist.delete(0, tk.END)
                    self.entry_artist.insert(0, parts[0].strip())
                    self.entry_title.delete(0, tk.END)
                    self.entry_title.insert(0, parts[1].strip())
                else:
                    self.entry_title.delete(0, tk.END)
                    self.entry_title.insert(0, stem)
                self.on_title_change()

    def on_fetch_youtube_info(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("Aviso", "Por favor, insira a URL do YouTube.")
            return

        def _task():
            self.set_busy(True, "Obtendo dados do vídeo no YouTube...")
            try:
                meta = get_video_metadata(url)
                title = meta.get("title", "")
                artist = meta.get("artist", "")
                dur = meta.get("duration", 0)

                self.entry_title.delete(0, tk.END)
                self.entry_title.insert(0, title)
                self.entry_artist.delete(0, tk.END)
                self.entry_artist.insert(0, artist)
                self.on_title_change()

                if dur > 0:
                    self.entry_audio_end.delete(0, tk.END)
                    self.entry_audio_end.insert(0, seconds_to_mmss(dur))
                    self.update_duration_display()

                self.set_status(f"Vídeo identificado: {title} ({seconds_to_mmss(dur)})")
                self.on_fetch_lyrics()
            except Exception as e:
                self.set_status(f"Erro ao identificar vídeo: {e}")
                messagebox.showerror("Erro", f"Não foi possível obter dados do vídeo:\n{e}")
            finally:
                self.set_busy(False)

        threading.Thread(target=_task, daemon=True).start()

    def on_search_karaoke_yt(self):
        title = self.entry_title.get().strip()
        artist = self.entry_artist.get().strip()
        if not title:
            messagebox.showwarning("Aviso", "Preencha o título da música para buscar versões de karaokê.")
            return

        def _task():
            self.set_busy(True, "Buscando versões de playback/karaokê no YouTube...")
            try:
                results = search_youtube_karaoke(title, artist, limit=4)
                if not results:
                    messagebox.showinfo("Busca", "Nenhum vídeo de karaokê encontrado para este termo.")
                    return
                self.after(0, lambda: self._show_karaoke_yt_dialog(results))
            except Exception as e:
                messagebox.showerror("Erro", f"Falha na busca: {e}")
            finally:
                self.set_busy(False)

        threading.Thread(target=_task, daemon=True).start()

    def _show_karaoke_yt_dialog(self, results):
        win = tk.Toplevel(self)
        win.title("Selecione a Versão Karaokê do YouTube")
        win.geometry("640x300")
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text="Selecione um vídeo instrumental já sem vocal:", font=("Segoe UI", 10, "bold")).pack(padx=10, pady=8, anchor="w")

        lb = tk.Listbox(win, font=("Segoe UI", 9))
        lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        for r in results:
            d_str = seconds_to_mmss(r["duration"]) if r["duration"] else ""
            lb.insert(tk.END, f"{r['title']} [{d_str}] - Canal: {r['uploader']}")

        def _use_selected():
            sel = lb.curselection()
            if not sel:
                return
            chosen = results[sel[0]]
            self.entry_url.delete(0, tk.END)
            self.entry_url.insert(0, chosen["url"])
            if chosen.get("duration"):
                self.entry_audio_end.delete(0, tk.END)
                self.entry_audio_end.insert(0, seconds_to_mmss(chosen["duration"]))
                self.update_duration_display()
            self.combo_vocal_mode.current(0) # Already instrumental!
            win.destroy()
            messagebox.showinfo("Sucesso", f"URL do Playback selecionada!\n{chosen['title']}")

        btn_box = ttk.Frame(win)
        btn_box.pack(fill=tk.X, padx=10, pady=8)
        ttk.Button(btn_box, text="✔ Usar Este Áudio", command=_use_selected).pack(side=tk.RIGHT)
        ttk.Button(btn_box, text="Cancelar", command=win.destroy).pack(side=tk.RIGHT, padx=6)

    def on_fetch_lyrics(self):
        title = self.entry_title.get().strip()
        artist = self.entry_artist.get().strip()
        if not title:
            messagebox.showwarning("Aviso", "Preencha o título da música para buscar a letra.")
            return

        def _task():
            self.set_busy(True, f"Buscando letra para '{title}' no lrclib.net...")
            try:
                results = search_lrclib(title, artist)
                synced = None
                for res in results:
                    if res.get("syncedLyrics"):
                        synced = res.get("syncedLyrics")
                        break

                if not synced:
                    self.set_status("Nenhuma letra sincronizada encontrada no lrclib.net.")
                    messagebox.showinfo("lrclib.net", f"Nenhuma letra sincronizada (LRC) encontrada para '{title}'. Você pode carregar um arquivo .lrc local.")
                    return

                entries = parse_lrc_content(synced)
                self.after(0, lambda: self._populate_lyrics_table(entries))
                self.set_status(f"Letra carregada: {len(entries)} versos encontrados no lrclib.net.")
            except Exception as e:
                self.set_status(f"Erro ao buscar letra: {e}")
                messagebox.showerror("Erro", f"Falha na consulta ao lrclib.net:\n{e}")
            finally:
                self.set_busy(False)

        threading.Thread(target=_task, daemon=True).start()

    def on_load_lrc_file(self):
        file_path = filedialog.askopenfilename(
            title="Selecione o arquivo .lrc",
            filetypes=[("Arquivos LRC", "*.lrc"), ("Texto", "*.txt"), ("Todos os Arquivos", "*.*")]
        )
        if file_path:
            text = pathlib.Path(file_path).read_text(encoding="utf-8", errors="ignore")
            entries = parse_lrc_content(text)
            self._populate_lyrics_table(entries)
            self.set_status(f"Arquivo LRC carregado ({len(entries)} versos).")

    def _populate_lyrics_table(self, entries):
        self.parsed_lyrics = entries
        for row in self.lyrics_tree.get_children():
            self.lyrics_tree.delete(row)

        for item in entries:
            tag_str = format_seconds_to_tag(item["time"])
            self.lyrics_tree.insert("", tk.END, values=(tag_str, item["text"]))

        if entries:
            # Set default boundaries
            self.entry_v_start.delete(0, tk.END)
            self.entry_v_start.insert(0, seconds_to_mmss(entries[0]["time"]))
            self.entry_v_end.delete(0, tk.END)
            self.entry_v_end.insert(0, seconds_to_mmss(entries[-1]["time"]))

            if self.var_auto_sync_cut.get():
                self.entry_audio_start.delete(0, tk.END)
                self.entry_audio_start.insert(0, seconds_to_mmss(max(0.0, entries[0]["time"] - 1.0)))
                self.entry_audio_end.delete(0, tk.END)
                self.entry_audio_end.insert(0, seconds_to_mmss(entries[-1]["time"] + 3.0))
                self.update_duration_display()

        self.lbl_lyrics_status.config(
            text=f"{len(entries)} versos carregados. Selecione um verso para marcar Início/Fim.",
            foreground="#006600"
        )

    def on_mark_verse_start(self):
        selected = self.lyrics_tree.selection()
        if not selected:
            messagebox.showinfo("Aviso", "Selecione um verso na tabela primeiro.")
            return
        idx = self.lyrics_tree.index(selected[0])
        t_sec = self.parsed_lyrics[idx]["time"]
        self.entry_v_start.delete(0, tk.END)
        self.entry_v_start.insert(0, seconds_to_mmss(t_sec))

        if self.var_auto_sync_cut.get():
            audio_s = max(0.0, t_sec - 1.0)
            self.entry_audio_start.delete(0, tk.END)
            self.entry_audio_start.insert(0, seconds_to_mmss(audio_s))
            self.update_duration_display()

    def on_mark_verse_end(self):
        selected = self.lyrics_tree.selection()
        if not selected:
            messagebox.showinfo("Aviso", "Selecione um verso na tabela primeiro.")
            return
        idx = self.lyrics_tree.index(selected[0])
        t_sec = self.parsed_lyrics[idx]["time"]
        self.entry_v_end.delete(0, tk.END)
        self.entry_v_end.insert(0, seconds_to_mmss(t_sec))

        if self.var_auto_sync_cut.get():
            audio_e = t_sec + 3.0
            self.entry_audio_end.delete(0, tk.END)
            self.entry_audio_end.insert(0, seconds_to_mmss(audio_e))
            self.update_duration_display()

    def update_duration_display(self, event=None):
        try:
            s = time_str_to_seconds(self.entry_audio_start.get())
            e = time_str_to_seconds(self.entry_audio_end.get())
            diff = max(0.0, e - s)
            self.lbl_calc_duration.config(text=f"Duração Áudio: {int(diff)}s")
        except Exception:
            pass

    # ---------------- Full Process Execution ----------------

    def on_start_full_process(self):
        url = self.entry_url.get().strip()
        local_mp3 = self.downloaded_source_mp3

        if not url and not local_mp3:
            messagebox.showerror("Aviso", "Insira uma URL do YouTube ou selecione um arquivo de áudio local.")
            return

        title = self.entry_title.get().strip()
        if not title:
            messagebox.showerror("Aviso", "Preencha o título da música.")
            return

        artist = self.entry_artist.get().strip() or "Desconhecido"
        genre = self.combo_genre.get().strip() or "ACUSTICO/MPB"
        song_id = self.entry_song_id.get().strip() or f"{slugify(title)}_01"
        sound_id = self.entry_sound_id.get().strip() or "rbxassetid://COLOQUE_SEU_AUDIO_AQUI"
        icon_id = self.entry_icon_id.get().strip() or "rbxassetid://123677416568279"

        audio_start = time_str_to_seconds(self.entry_audio_start.get())
        audio_end = time_str_to_seconds(self.entry_audio_end.get())
        v_start = time_str_to_seconds(self.entry_v_start.get())
        v_end = time_str_to_seconds(self.entry_v_end.get())

        try:
            offset_val = float(self.entry_offset.get().strip() or "0.0")
        except ValueError:
            offset_val = 0.0

        if audio_end <= audio_start:
            messagebox.showerror("Aviso", "O tempo de Fim do áudio deve ser maior que o tempo de Início.")
            return

        vocal_mode_idx = self.combo_vocal_mode.current()
        anticopy_idx = self.combo_anticopyright.current()
        align_zero = self.var_align_zero.get()

        anticopy_map = {
            0: "none",
            1: "pitch_up",
            2: "pitch_down",
            3: "stage_reverb",
            4: "lofi_warmth",
            5: "nightcore",
            6: "midi_synth"
        }
        effect_key = anticopy_map.get(anticopy_idx, "none")

        def _task():
            self.set_busy(True, "Iniciando processamento...")
            try:
                # 1. Obter áudio fonte
                if local_mp3 and local_mp3.exists():
                    source_audio = local_mp3
                    self.set_status("Usando arquivo de áudio local...")
                else:
                    self.set_status("1/4 Baixando áudio do YouTube...")
                    raw_mp3_path = self.output_dir / f"{song_id}_original.mp3"
                    download_mp3(url, raw_mp3_path)
                    source_audio = raw_mp3_path

                # 2. Cortar áudio no trecho manual especificado
                self.set_status("2/4 Cortando áudio no intervalo selecionado...")
                trimmed_mp3 = self.output_dir / f"{song_id}.mp3"
                trim_mp3(source_audio, audio_start, audio_end, trimmed_mp3)
                current_mp3 = trimmed_mp3

                # 3. Remoção de vocal (se habilitado)
                if vocal_mode_idx == 1:
                    self.set_status("3/4 Removendo vocais com Demucs IA (Meta)...")
                    vocals_mp3 = self.output_dir / f"{song_id}_karaoke.mp3"
                    remove_vocals(current_mp3, vocals_mp3, mode="demucs")
                    current_mp3 = vocals_mp3
                elif vocal_mode_idx == 2:
                    self.set_status("3/4 Removendo vocais com Audio Separator (MDX-Net)...")
                    vocals_mp3 = self.output_dir / f"{song_id}_karaoke.mp3"
                    remove_vocals(current_mp3, vocals_mp3, mode="audio_separator")
                    current_mp3 = vocals_mp3
                elif vocal_mode_idx == 3:
                    self.set_status("3/4 Removendo vocais (Multi-Band Agressivo)...")
                    vocals_mp3 = self.output_dir / f"{song_id}_karaoke.mp3"
                    remove_vocals(current_mp3, vocals_mp3, mode="aggressive")
                    current_mp3 = vocals_mp3
                elif vocal_mode_idx == 4:
                    self.set_status("3/4 Removendo vocais (Cancelamento Central)...")
                    vocals_mp3 = self.output_dir / f"{song_id}_karaoke.mp3"
                    remove_vocals(current_mp3, vocals_mp3, mode="standard")
                    current_mp3 = vocals_mp3

                # 4. Efeito Anti-Copyright (Apenas 1 ativo!)
                time_scale_factor = 1.0
                if effect_key != "none":
                    self.set_status(f"Aplicando efeito anti-copyright: {self.combo_anticopyright.get()}...")

                    def _midi_cb(in_p, out_p):
                        mid_file = self.output_dir / f"{song_id}.mid"
                        audio_to_midi(in_p, mid_file)
                        return midi_to_synth_mp3(mid_file, out_p)

                    eff_out_mp3 = self.output_dir / f"{song_id}_anticopy.mp3"
                    res_audio, time_scale_factor = apply_single_anticopyright_effect(
                        current_mp3,
                        eff_out_mp3,
                        effect_key=effect_key,
                        midi_callback=_midi_cb
                    )
                    current_mp3 = res_audio

                # 5. Processar letra e calcular tempos
                self.set_status("4/4 Re-calculando tempos das letras e gerando Roblox Lua...")
                processed_lyrics = process_lyrics_timestamps(
                    self.parsed_lyrics,
                    verse_start_sec=v_start,
                    verse_end_sec=v_end,
                    audio_start_sec=audio_start,
                    align_first_verse_zero=align_zero,
                    offset_sec=offset_val,
                    time_scale=time_scale_factor
                )

                duration_audio = (audio_end - audio_start) / time_scale_factor

                res = export_outputs(
                    out_dir=self.output_dir,
                    song_id=song_id,
                    title=title,
                    artist=artist,
                    genre=genre,
                    duration=duration_audio,
                    lyrics_processed=processed_lyrics,
                    sound_id=sound_id,
                    icon_id=icon_id
                )

                lua_code = res["lua_code"]
                self.current_preview_file = current_mp3

                self.after(0, lambda: self._on_process_complete(lua_code, current_mp3, song_id))

            except Exception as e:
                self.set_status(f"Erro: {e}")
                messagebox.showerror("Erro durante o processamento", f"Ocorreu um erro:\n{e}")
            finally:
                self.set_busy(False)

        threading.Thread(target=_task, daemon=True).start()

    def _on_process_complete(self, lua_code: str, final_audio_path: pathlib.Path, song_id: str):
        self.text_lua_output.delete("1.0", tk.END)
        self.text_lua_output.insert(tk.END, lua_code)
        self.set_status(f"Concluído! Arquivos salvos em: {self.output_dir.resolve()}")
        messagebox.showinfo(
            "Sucesso!",
            f"Processamento concluído em segundos!\n\n"
            f"• Áudio pronto: {final_audio_path.name}\n"
            f"• Tabela Roblox: {song_id}.lua\n"
            f"• LRC sincronizado: {song_id}_adjusted.lrc\n\n"
            f"O código Lua já está exibido abaixo. Clique em 'Copiar Código Roblox' para colar no jogo!"
        )

    def on_copy_lua(self):
        code = self.text_lua_output.get("1.0", tk.END).strip()
        if not code:
            messagebox.showinfo("Aviso", "Nenhum código gerado para copiar.")
            return
        self.clipboard_clear()
        self.clipboard_append(code)
        messagebox.showinfo("Copiado!", "Código da tabela Lua copiado para a área de transferência!")

    def on_open_output_folder(self):
        p = str(self.output_dir.resolve())
        if sys.platform == "win32":
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.run(["open", p])
        else:
            subprocess.run(["xdg-open", p])

    def on_play_preview(self):
        if not self.current_preview_file or not self.current_preview_file.exists():
            messagebox.showinfo("Aviso", "Nenhum áudio processado para tocar ainda.")
            return

        def _play():
            try:
                ffmpeg_exe = get_ffmpeg_path()
                tmp_wav = self.output_dir / "preview_temp.wav"
                cmd = [
                    ffmpeg_exe, "-y",
                    "-i", str(self.current_preview_file),
                    "-ar", "44100", "-ac", "2",
                    str(tmp_wav)
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.is_playing = True
                winsound.PlaySound(str(tmp_wav), winsound.SND_ASYNC | winsound.SND_FILENAME)
            except Exception as e:
                print(f"Preview error: {e}")

        threading.Thread(target=_play, daemon=True).start()

    def on_stop_preview(self):
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
            self.is_playing = False
        except Exception:
            pass

    def set_busy(self, busy: bool, message: str = ""):
        self.after(0, lambda: self._apply_busy(busy, message))

    def _apply_busy(self, busy: bool, message: str):
        if busy:
            self.progress_bar.start(10)
            self.btn_run.config(state="disabled")
            if message:
                self.lbl_status.config(text=message, foreground="#000088")
        else:
            self.progress_bar.stop()
            self.btn_run.config(state="normal")

    def set_status(self, text: str):
        self.after(0, lambda: self.lbl_status.config(text=text))

def main():
    app = KaraokeApp()
    app.mainloop()

if __name__ == "__main__":
    main()
