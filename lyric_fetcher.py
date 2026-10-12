import re
import requests
import pathlib

HEADERS = {
    "User-Agent": "KBRKaraokeTool/1.0 (https://github.com/user/kbr_system)",
    "Lrclib-Client": "KBRKaraokeTool/1.0"
}

TIME_TAG_REGEX = re.compile(r"\[(\d{1,2}):(\d{2})(?:[\.:](\d{2,3}))?\]")

def parse_time_tag(tag: str) -> float:
    """Convert [mm:ss.xx] tag into float seconds."""
    m = TIME_TAG_REGEX.search(tag)
    if not m:
        return 0.0
    minutes = int(m.group(1))
    seconds = int(m.group(2))
    fraction = m.group(3) or "0"
    if len(fraction) == 2:
        ms = int(fraction) * 10
    else:
        ms = int(fraction[:3])
    return minutes * 60 + seconds + (ms / 1000.0)

def format_seconds_to_tag(total_seconds: float) -> str:
    """Convert float seconds into [mm:ss.xx] format."""
    if total_seconds < 0:
        total_seconds = 0.0
    mins = int(total_seconds // 60)
    secs = int(total_seconds % 60)
    hundredths = int(round((total_seconds - int(total_seconds)) * 100))
    if hundredths >= 100:
        hundredths = 0
        secs += 1
    return f"[{mins:02d}:{secs:02d}.{hundredths:02d}]"

def parse_lrc_content(lrc_text: str) -> list[dict]:
    """Parse raw LRC text into a structured list:
    [{ 'time': 15.5, 'tag': '[00:15.50]', 'text': 'Verse text' }, ...]
    """
    lines = lrc_text.splitlines()
    entries = []
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        matches = list(TIME_TAG_REGEX.finditer(line_clean))
        if not matches:
            continue
        # Extract text after the last timestamp tag
        last_match = matches[-1]
        text = line_clean[last_match.end():].strip()
        # For each tag in line (handling repeat tags if any)
        for m in matches:
            t = parse_time_tag(m.group(0))
            entries.append({
                "time": round(t, 2),
                "tag": m.group(0),
                "text": text
            })
    # Sort chronologically
    entries.sort(key=lambda x: x["time"])
    return entries

def search_lrclib(title: str, artist: str = "") -> list[dict]:
    """Search lyrics on lrclib.net.
    Returns list of song matches with syncedLyrics.
    """
    url = "https://lrclib.net/api/search"
    results = []

    # First try search with query string
    q = f"{artist} {title}".strip()
    try:
        resp = requests.get(url, params={"q": q}, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                results.extend(data)
    except Exception:
        pass

    # If nothing found or empty, try specific params
    if not results and title:
        try:
            params = {"track_name": title}
            if artist:
                params["artist_name"] = artist
            resp = requests.get(url, params=params, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    results.extend(data)
        except Exception:
            pass

    return results

def fetch_lrc_lrclib(title: str, artist: str = "", out_path: pathlib.Path = None) -> tuple[str, list[dict]]:
    """Search lrclib.net and return (raw_lrc_text, parsed_entries)."""
    results = search_lrclib(title, artist)
    if not results:
        raise FileNotFoundError(f"Nenhuma letra sincronizada encontrada para '{title}' no lrclib.net")

    for item in results:
        synced = item.get("syncedLyrics")
        if synced:
            if out_path:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(synced, encoding="utf-8")
            return synced, parse_lrc_content(synced)

    raise ValueError(f"Encontrados registros para '{title}', mas nenhum continha syncedLyrics.")
