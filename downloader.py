import os
import pathlib
import yt_dlp
from ffmpeg_utils import get_ffmpeg_path

def get_video_metadata(youtube_url: str) -> dict:
    """Extract metadata (title, artist, duration) from a YouTube video without downloading."""
    ffmpeg_exe = get_ffmpeg_path()
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'ffmpeg_location': ffmpeg_exe,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        title = info.get('title', '')
        # Try to infer artist and track name if formatted as "Artist - Title"
        artist = info.get('artist', '') or info.get('uploader', '') or info.get('channel', '')
        if " - " in title and not info.get('artist'):
            parts = title.split(" - ", 1)
            artist = parts[0].strip()
            title = parts[1].strip()

        return {
            'title': title,
            'artist': artist,
            'duration': info.get('duration', 0),
            'id': info.get('id', '')
        }

def search_youtube_karaoke(title: str, artist: str = "", limit: int = 4) -> list[dict]:
    """Search YouTube for existing instrumental/karaoke versions of the track."""
    ffmpeg_exe = get_ffmpeg_path()
    query = f"{artist} {title} karaoke playback instrumental".strip()
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'ffmpeg_location': ffmpeg_exe,
        'extract_flat': 'in_playlist',
    }
    results = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_res = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        entries = search_res.get('entries', [])
        for entry in entries:
            results.append({
                'title': entry.get('title', ''),
                'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                'duration': entry.get('duration', 0),
                'uploader': entry.get('uploader', '')
            })
    return results

def download_mp3(youtube_url: str, out_path: pathlib.Path, progress_callback=None) -> pathlib.Path:
    """Download audio from YouTube and export as MP3."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()

    # Base path without extension for yt-dlp
    base_target = out_path.with_suffix('')

    def ytdl_hook(d):
        if progress_callback and d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            downloaded = d.get('downloaded_bytes', 0)
            percent = (downloaded / total) * 100
            progress_callback(percent, "Baixando áudio...")
        elif progress_callback and d.get('status') == 'finished':
            progress_callback(100, "Convertendo para MP3...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(base_target) + '.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'ffmpeg_location': ffmpeg_exe,
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [ytdl_hook] if progress_callback else [],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])

    final_mp3 = out_path.with_suffix('.mp3')
    return final_mp3
