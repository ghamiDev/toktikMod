import streamlit as st
import subprocess
import random
import os
import re
import shutil
from datetime import datetime

OUTPUT_DIR = "output"
TEMP_DIR = "temp"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

st.title("TokTikMod - Versi 1.1")

uploaded = st.file_uploader("Upload video panjenengan", type=["mp4", "mov", "mkv"])


# =============== REAL-TIME FFMPEG PROGRESS ===============
def ffmpeg_with_progress(cmd, progress_bar, status_text):
    process = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1
    )

    duration = None

    for line in process.stderr:
        # Get duration
        if "Duration" in line:
            match = re.search(r"Duration: (\d+):(\d+):(\d+.\d+)", line)
            if match:
                h, m, s = match.groups()
                duration = int(h) * 3600 + int(m) * 60 + float(s)

        # Current time
        if "time=" in line and duration:
            match = re.search(r"time=(\d+):(\d+):(\d+.\d+)", line)
            if match:
                h, m, s = match.groups()
                current = int(h) * 3600 + int(m) * 60 + float(s)
                progress = current / duration
                progress_bar.progress(min(progress, 1.0))
                status_text.text(f"Processing... {int(progress*100)}%")

    process.wait()
    return process


# ===================== AUTO CLEANUP ======================
def cleanup_temp():
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR, exist_ok=True)


# ================ ORIGINAL FFMPEG PIPELINE ===============
def run_ffmpeg(input_path, output_path, progress_bar, status_text):
    crop_factor   = round(random.uniform(0.92, 0.97), 3)
    rotate_deg    = round(random.uniform(-1.6, 1.6), 2)
    scale_factor  = round(random.uniform(0.98, 1.03), 3)
    speed_factor  = round(random.uniform(0.95, 1.05), 3)
    blur_sigma    = round(random.uniform(0.25, 0.55), 3)
    grain_strength = round(random.uniform(0.08, 0.14), 3)

    filtergraph = (
        f"crop=iw*{crop_factor}:ih*{crop_factor},"
        f"rotate=0.0174533*{rotate_deg}:fillcolor=black,"
        f"scale=iw*{scale_factor}:ih*{scale_factor},"
        f"setsar=1,setpts=PTS/{speed_factor},"
        f"eq=saturation=1.02:contrast=1.03:brightness=0.01:gamma=1.02,"
        f"boxblur={blur_sigma}:{blur_sigma},"
        f"noise=alls={grain_strength}:allf=t+u,"
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2,"
        f"pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2"
    )

    # Split video
    split_cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex", "split=3[v1][v2][v3]",
        "-map", "[v1]", "-map", "0:a?", "-c:v", "libx264", "-c:a", "aac", f"{TEMP_DIR}/p1.mp4",
        "-map", "[v2]", "-map", "0:a?", "-c:v", "libx264", "-c:a", "aac", f"{TEMP_DIR}/p2.mp4",
        "-map", "[v3]", "-map", "0:a?", "-c:v", "libx264", "-c:a", "aac", f"{TEMP_DIR}/p3.mp4"
    ]
    subprocess.run(split_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Shuffle part
    parts = ["p1.mp4", "p2.mp4", "p3.mp4"]
    random.shuffle(parts)

    with open(f"{TEMP_DIR}/list.txt", "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")

    concat_out = f"{TEMP_DIR}/concat_temp.mp4"
    concat_cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", f"{TEMP_DIR}/list.txt", "-c:v", "libx264", "-c:a", "aac",
        "-vsync", "vfr", "-pix_fmt", "yuv420p", concat_out
    ]
    subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Final effect (progress tracked)
    final_cmd = [
        "ffmpeg", "-y",
        "-i", concat_out,
        "-vf", filtergraph,
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]

    return ffmpeg_with_progress(final_cmd, progress_bar, status_text)


# ===================== STREAMLIT UI ======================
if uploaded:
    temp_input = f"{TEMP_DIR}/temp_input_video.mp4"
    with open(temp_input, "wb") as f:
        f.write(uploaded.read())

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"{OUTPUT_DIR}/edited_{ts}.mp4"

    st.info("Processing... mohon tunggu")

    progress_bar = st.progress(0)
    status_text = st.empty()

    process = run_ffmpeg(temp_input, out_path, progress_bar, status_text)

    if process.returncode != 0 or not os.path.exists(out_path):
        st.error("FFmpeg gagal memproses video")
        cleanup_temp()
    else:
        progress_bar.progress(1.0)
        status_text.text("Selesai 100%")
        st.success("Video berhasil diproses!")
        st.video(out_path)

        with open(out_path, "rb") as f:
            st.download_button("Download Video", f, file_name=f"edited_{ts}.mp4")

        cleanup_temp()
