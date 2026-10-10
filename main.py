import os
import sys
import shutil
import subprocess
from pathlib import Path

TIKTOK_URL = "https://www.tiktok.com/@user7977723596063/video/7694847593028816136?is_from_webapp=1&sender_device=pc"

YOUTUBE_STREAM_KEY = "9gs2-gayu-3pjh-wda0-1tp7"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2"

WORK_DIR = Path("/tmp/tiktok_video_relay")
VIDEO_FILE = WORK_DIR / "video.mp4"


def run_command(command):
    print("\n[RUN]", " ".join(str(x) for x in command), flush=True)
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )


def main():
    for tool in ("ffmpeg", "ffprobe", "yt-dlp"):
        if not shutil.which(tool):
            raise RuntimeError(f"{tool} is not installed.")

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    if VIDEO_FILE.exists():
        VIDEO_FILE.unlink()

    print("[1/3] Downloading the complete TikTok video...", flush=True)

    run_command([
        "yt-dlp",
        "--no-playlist",
        "--no-part",
        "--retries", "10",
        "--fragment-retries", "10",
        "-f", "best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(VIDEO_FILE),
        TIKTOK_URL,
    ])

    if not VIDEO_FILE.exists() or VIDEO_FILE.stat().st_size < 1024:
        raise RuntimeError("Video download failed or file is empty.")

    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(VIDEO_FILE),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if probe.returncode != 0:
        raise RuntimeError("Could not inspect the downloaded video.")

    codec = probe.stdout.strip().lower()
    print(f"[INFO] Video codec: {codec}", flush=True)

    if codec == "h264":
        video_args = ["-c:v", "copy"]
    else:
        video_args = [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-b:v", "4500k",
            "-maxrate", "4500k",
            "-bufsize", "9000k",
            "-g", "60",
        ]

    output_url = f"{YOUTUBE_RTMP}/{YOUTUBE_STREAM_KEY}"

    ffmpeg_command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "info",
        "-nostdin",
        "-re",
        "-i", str(VIDEO_FILE),

        "-map", "0:v:0",
        "-map", "0:a:0?",

        *video_args,

        "-c:a", "aac",
        "-b:a", "160k",
        "-ar", "48000",
        "-ac", "2",
        "-af", "aresample=async=1:first_pts=0",

        "-max_muxing_queue_size", "2048",
        "-flvflags", "no_duration_filesize",
        "-f", "flv",
        output_url,
    ]

    print(
        f"[INFO] Download complete: {VIDEO_FILE.stat().st_size} bytes",
        flush=True,
    )
    print("[2/3] Starting YouTube broadcast...", flush=True)

    run_command(ffmpeg_command)

    print("[3/3] Video finished streaming once.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
