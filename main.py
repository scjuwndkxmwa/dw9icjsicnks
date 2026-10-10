
import subprocess
import sys
from pathlib import Path

# Your TikTok video
TIKTOK_VIDEO_URL = "https://vt.tiktok.com/ZSbnqudwt/"

# YouTube stream key supplied by you
YOUTUBE_STREAM_KEY = "0fy0-xbfb-dbjt-cym2-2pvc"

YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/"
DOWNLOAD_DIR = Path("/tmp/tiktok_download")
STATE_DIR = Path("/data")
DONE_FILE = STATE_DIR / "youtube_attempted.txt"


def log(message):
    print(message, flush=True)


def run(command):
    result = subprocess.run(command)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if DONE_FILE.exists():
        log("[STOP] Previous attempt recorded; refusing to replay.")
        return

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    output_template = str(DOWNLOAD_DIR / "video.%(ext)s")

    log("[DOWNLOAD] Downloading TikTok post...")
    run([
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "--format", "best",
        "--output", output_template,
        TIKTOK_VIDEO_URL,
    ])

    videos = [
        p for p in DOWNLOAD_DIR.glob("video.*")
        if p.is_file() and p.stat().st_size > 1024
    ]
    if not videos:
        raise RuntimeError(
            "TikTok video download failed. Check Railway logs."
        )

    video = videos[0]
    log(f"[DOWNLOAD] Saved {video.stat().st_size / 1048576:.2f} MB")

    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0 or not probe.stdout.strip():
        raise RuntimeError("Downloaded file has no readable video stream")

    codec = probe.stdout.strip().lower()
    if codec == "h264":
        video_args = ["-c:v", "copy"]
        log("[VIDEO] H.264: copy mode enabled")
    else:
        video_args = [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
        ]
        log("[VIDEO] Converting video to H.264")

    # Save the marker before streaming to avoid automatic replay.
    DONE_FILE.write_text(
        "Transmission attempt started; no automatic replay.\n",
        encoding="utf-8",
    )

    target = YOUTUBE_RTMP + YOUTUBE_STREAM_KEY
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel", "warning",
        "-re",
        "-i", str(video),
        "-map", "0:v:0",
        *video_args,
        "-map", "0:a:0?",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        "-f", "flv",
        target,
    ]

    log("[YOUTUBE] Sending video once; looping disabled")
    run(command)
    log("[SUCCESS] Transmission finished")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"[FATAL] {exc}")
        sys.exit(1)
