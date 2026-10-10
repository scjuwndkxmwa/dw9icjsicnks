import os
import sys
import shutil
import subprocess
from pathlib import Path

TIKTOK_URL = os.getenv("TIKTOK_URL", "https://vt.tiktok.com/ZSbnqudwt/")
YOUTUBE_STREAM_KEY = os.getenv("YOUTUBE_STREAM_KEY", "")

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
    if not TIKTOK_URL:
        raise RuntimeError("TIKTOK_URL is missing.")

    if not YOUTUBE_STREAM_KEY:
        raise RuntimeError("YOUTUBE_STREAM_KEY is missing.")

    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is not installed.")

    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp is not installed.")

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # Remove only this run's old temporary video.
    if VIDEO_FILE.exists():
        VIDEO_FILE.unlink()

    print("=" * 55, flush=True)
    print("TikTok VIDEO -> YouTube LIVE", flush=True)
    print("Mode: Download complete video, then stream once", flush=True)
    print("Video encoding: COPY when compatible", flush=True)
    print("=" * 55, flush=True)

    # Download the complete posted video before starting YouTube.
    download_command = [
        "yt-dlp",
        "--no-playlist",
        "--no-part",
        "--retries", "10",
        "--fragment-retries", "10",
        "-f", "best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(VIDEO_FILE),
        TIKTOK_URL,
    ]

    run_command(download_command)

    if not VIDEO_FILE.exists() or VIDEO_FILE.stat().st_size < 1024:
        raise RuntimeError("Download failed or produced an empty video.")

    print(
        f"\n[OK] Download complete: {VIDEO_FILE.stat().st_size} bytes",
        flush=True,
    )

    # Inspect the downloaded video codec.
    probe = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(VIDEO_FILE),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    video_codec = probe.stdout.strip().lower()
    print(f"[INFO] Video codec: {video_codec or 'unknown'}", flush=True)

    # FLV/RTMP commonly expects H.264 video.
    # Copy H.264 directly; convert incompatible codecs for compatibility.
    if video_codec == "h264":
        video_options = ["-c:v", "copy"]
    else:
        video_options = [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-b:v", "4500k",
            "-maxrate", "4500k",
            "-bufsize", "9000k",
            "-g", "60",
        ]
        print(
            "[INFO] Video will be encoded as H.264 for RTMP compatibility.",
            flush=True,
        )

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
        *video_options,
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        "-max_muxing_queue_size", "2048",
        "-flvflags", "no_duration_filesize",
        "-f", "flv",
        output_url,
    ]

    print("\n[INFO] Starting YouTube broadcast...", flush=True)
    run_command(ffmpeg_command)

    print("\n[DONE] The complete video has finished streaming once.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
