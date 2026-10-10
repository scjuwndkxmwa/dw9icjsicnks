import os
import sys
import time
import shutil
import subprocess
import json
from pathlib import Path

TIKTOK_URL = "https://vt.tiktok.com/ZSbnqudwt/"
YOUTUBE_STREAM_KEY = "wew2-r2mr-0fep-k29h-debh"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2"

DOWNLOAD_DIR = Path("/tmp/tiktok_download")
DATA_DIR = Path("/data")
DONE_FILE = DATA_DIR / "youtube_attempted.txt"


def log(message):
    print(message, flush=True)


def check_dependencies():
    for program in ("ffmpeg", "ffprobe"):
        if not shutil.which(program):
            raise RuntimeError(f"Missing dependency: {program}")

    result = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--version"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError("yt-dlp is not installed correctly.")


def download_video():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for item in DOWNLOAD_DIR.iterdir():
        if item.is_file():
            item.unlink()

    command = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "--no-warnings",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(DOWNLOAD_DIR / "video.%(ext)s"),
        TIKTOK_URL
    ]

    log("[DOWNLOAD] Downloading TikTok video...")
    subprocess.run(command, check=True)

    candidates = [
        p for p in DOWNLOAD_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
    ]

    if not candidates:
        raise RuntimeError("No downloaded video file was found.")

    video = max(candidates, key=lambda p: p.stat().st_size)

    if video.stat().st_size == 0:
        raise RuntimeError("Downloaded video is empty.")

    return video


def check_media(video):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,sample_rate,channels",
            "-of", "json", str(video)
        ],
        capture_output=True,
        text=True,
        check=True
    )

    streams = json.loads(result.stdout).get("streams", [])

    for stream in streams:
        log(
            f"[MEDIA] type={stream.get('codec_type')} "
            f"codec={stream.get('codec_name')} "
            f"rate={stream.get('sample_rate')} "
            f"channels={stream.get('channels')}"
        )

    if not any(s.get("codec_type") == "video" for s in streams):
        raise RuntimeError("Downloaded file has no video stream.")

    if not any(s.get("codec_type") == "audio" for s in streams):
        raise RuntimeError("Downloaded file has no audio stream.")


def stream_to_youtube(video):
    output_url = f"{YOUTUBE_RTMP}/{YOUTUBE_STREAM_KEY}"

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "info",
        "-nostdin",
        "-re",
        "-i", str(video),
        "-map", "0:v:0",
        "-map", "0:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        "-f", "flv",
        output_url
    ]

    log("[LIVE] Video: COPY")
    log("[LIVE] Audio: AAC 128k, 44100 Hz, stereo")
    log("[LIVE] Sending video to YouTube once...")

    subprocess.run(command, check=True)

    log("[DONE] Stream finished successfully.")


def main():
    log("=" * 50)
    log("[SYSTEM] TikTok video -> YouTube Live")
    log("=" * 50)

    check_dependencies()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if DONE_FILE.exists():
        log("[STOP] This video was already attempted.")
        log("[STOP] No automatic duplicate attempt.")
        return

    video = download_video()
    check_media(video)

    # Record the attempt before streaming to avoid replay on restart.
    DONE_FILE.write_text(
        time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        encoding="utf-8"
    )

    stream_to_youtube(video)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        log(f"[ERROR] Command failed with code {exc.returncode}")
        sys.exit(exc.returncode or 1)
    except Exception as exc:
        log(f"[ERROR] {exc}")
        sys.exit(1)
