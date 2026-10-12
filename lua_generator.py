import re
import math
import unicodedata
import pathlib
import json

def slugify(text: str) -> str:
    """Normalize and convert text to valid Lua identifier: joao_e_maria_01."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    slug = re.sub(r'[-\s]+', '_', text)
    if not slug:
        slug = "musica"
    return slug

def process_lyrics_timestamps(
    lyrics: list[dict],
    verse_start_sec: float,
    verse_end_sec: float,
    audio_start_sec: float = None,
    align_first_verse_zero: bool = True,
    offset_sec: float = 0.0,
    time_scale: float = 1.0
) -> list[dict]:
    """Filter lyrics within [verse_start_sec, verse_end_sec] and calculate new timestamps.
    - align_first_verse_zero:
        True: First verse starts at 0.0s, subsequent verses follow exact relative intervals.
        False: Verses are relative to audio_start_sec (with intro buffer if any).
    - offset_sec: Manual delay/lead offset in seconds.
    - time_scale: Speed scale factor (e.g. 1.05 for Nightcore).
    """
    in_range = [
        item for item in lyrics
        if (verse_start_sec - 0.5) <= item["time"] <= (verse_end_sec + 0.5)
    ]

    if not in_range:
        return []

    if align_first_verse_zero or audio_start_sec is None:
        base_time = in_range[0]["time"]
    else:
        base_time = audio_start_sec

    processed = []
    for item in in_range:
        raw_diff = (item["time"] - base_time) + offset_sec
        if time_scale != 1.0 and time_scale > 0:
            raw_diff = raw_diff / time_scale

        diff = round(max(0.0, raw_diff), 1)
        processed.append({
            "tempo": diff,
            "texto": item["text"].strip()
        })

    if processed and align_first_verse_zero:
        processed[0]["tempo"] = 0.0

    return processed

def generate_roblox_lua(
    song_id: str,
    title: str,
    artist: str,
    genre: str,
    duration: float,
    lyrics: list[dict],
    sound_id: str = "rbxassetid://COLOQUE_SEU_AUDIO_AQUI",
    icon_id: str = "rbxassetid://123677416568279"
) -> str:
    """Generate the exact Roblox Lua table matching format.txt."""
    if not song_id:
        song_id = f"{slugify(title)}_01"

    duration_rounded = int(math.ceil(duration)) + 1

    lines = [
        f'["{song_id}"] = {{',
        f'\t\tTitle = "{title}",',
        f'\t\tArtist = "{artist}",',
        f'\t\tGenre = "{genre}",',
        f'\t\tSoundId = "{sound_id}",',
        f'\t\tDuration = {duration_rounded}, -- Duração aproximada com uma folguinha no final do corte',
        '\t\t',
        '\t\tLyrics = {'
    ]

    for item in lyrics:
        tempo_str = f"{item['tempo']:.1f}"
        escaped_text = item['texto'].replace('"', '\\"')
        lines.append(f'\t\t\t{{tempo = {tempo_str}, texto = "{escaped_text}"}},')

    lines.append('\t\t},')
    lines.append(f'\t\tIconId = "{icon_id}"')
    lines.append('\t}')

    return "\n".join(lines)

def export_outputs(
    out_dir: pathlib.Path,
    song_id: str,
    title: str,
    artist: str,
    genre: str,
    duration: float,
    lyrics_processed: list[dict],
    sound_id: str = "rbxassetid://COLOQUE_SEU_AUDIO_AQUI",
    icon_id: str = "rbxassetid://123677416568279"
) -> dict:
    """Export Roblox Lua file, adjusted LRC file, and JSON sync file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not song_id:
        song_id = f"{slugify(title)}_01"

    # 1. Roblox Lua table
    lua_code = generate_roblox_lua(
        song_id=song_id,
        title=title,
        artist=artist,
        genre=genre,
        duration=duration,
        lyrics=lyrics_processed,
        sound_id=sound_id,
        icon_id=icon_id
    )
    lua_path = out_dir / f"{song_id}.lua"
    lua_path.write_text(lua_code, encoding="utf-8")

    # 2. Adjusted LRC
    lrc_lines = []
    for item in lyrics_processed:
        t = item["tempo"]
        mins = int(t // 60)
        secs = int(t % 60)
        tenths = int(round((t - int(t)) * 10))
        tag = f"[{mins:02d}:{secs:02d}.{tenths:01d}0]"
        lrc_lines.append(f"{tag} {item['texto']}")

    lrc_path = out_dir / f"{song_id}_adjusted.lrc"
    lrc_path.write_text("\n".join(lrc_lines), encoding="utf-8")

    # 3. JSON sync
    json_path = out_dir / f"{song_id}_sync.json"
    json_path.write_text(json.dumps(lyrics_processed, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "lua_path": lua_path,
        "lrc_path": lrc_path,
        "json_path": json_path,
        "lua_code": lua_code
    }
