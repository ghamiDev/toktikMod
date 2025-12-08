import streamlit as st
import subprocess
import random
import os
import re
import shutil
from datetime import datetime

# ----------------------------
# Config
# ----------------------------
OUTPUT_DIR = "output"
TEMP_DIR = "temp"
MAX_DURATION = 20  # detik

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

st.set_page_config(page_title="TokTikMod v2.2", layout="centered")
st.title("TokTikMod - Versi 2.2 (Stable)")

uploaded = st.file_uploader("Upload video panjenengan", type=["mp4", "mov", "mkv"])

# ----------------------------
# Session state init
# ----------------------------
if "video_ready" not in st.session_state:
    st.session_state.video_ready = False
if "out_path" not in st.session_state:
    st.session_state.out_path = None
if "delete_after" not in st.session_state:
    st.session_state.delete_after = False
if "processing" not in st.session_state:
    st.session_state.processing = False

# ----------------------------
# Helpers
# ----------------------------
def cleanup_temp():
    if os.path.exists(TEMP_DIR):
        try:
            shutil.rmtree(TEMP_DIR)
        except Exception:
            pass
    os.makedirs(TEMP_DIR, exist_ok=True)

def metadata_opts():
    encoder_name = random.choice([
        "Lavf59.50", "HandBrake 1.6", "Premiere CC",
        "DaVinci Resolve", "Vegas Pro"
    ])
    return [
        "-metadata", "title=",
        "-metadata", "comment=",
        "-metadata", "description=",
        "-metadata", "artist=",
        "-metadata", f"encoder={encoder_name}",
        "-map_metadata", "-1"
    ]


# ----------------------------
# ffmpeg with progress
# ----------------------------
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
        if duration is None and "Duration" in line:
            match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", line)
            if match:
                h, m, s = match.groups()
                duration = int(h) * 3600 + int(m) * 60 + float(s)

        if duration is not None and "time=" in line:
            match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
            if match:
                h, m, s = match.groups()
                current = int(h) * 3600 + int(m) * 60 + float(s)
                progress = min(current / duration, 1.0)
                try:
                    progress_bar.progress(progress)
                    status_text.text(f"Processing... {int(progress * 100)}%")
                except:
                    pass

    process.wait()
    return process


# ----------------------------
# Main pipeline
# ----------------------------
def run_ffmpeg(input_path, output_path, progress_bar, status_text):

    st.session_state.processing = True

    rotate_deg = round(random.uniform(-0.6, 0.6), 2)
    sat        = round(random.uniform(1.01, 1.04), 3)
    contrast   = round(random.uniform(1.01, 1.03), 3)
    brightness = round(random.uniform(-0.02, 0.02), 3)

    filtergraph = (
        "hflip,"
        "scale=iw*1.25:ih*1.03,"
        "crop=ih*9/16:ih,"
        f"rotate={rotate_deg}*PI/180:fillcolor=black,"
        f"eq=saturation={sat}:contrast={contrast}:brightness={brightness},"
        "setsar=1,setpts=PTS/1,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    )

    # Split
    split_cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter_complex", "split=3[v1][v2][v3]",
        "-map", "[v1]", f"{TEMP_DIR}/p1.mp4",
        "-map", "[v2]", f"{TEMP_DIR}/p2.mp4",
        "-map", "[v3]", f"{TEMP_DIR}/p3.mp4",
    ]
    subprocess.run(split_cmd)

    # fallback
    for p in ["p1.mp4", "p2.mp4", "p3.mp4"]:
        fp = f"{TEMP_DIR}/{p}"
        if not os.path.exists(fp) or os.path.getsize(fp) < 50000:
            for q in ["p1.mp4", "p2.mp4", "p3.mp4"]:
                shutil.copy(input_path, f"{TEMP_DIR}/{q}")
            break

    # concat
    parts = ["p1.mp4", "p2.mp4", "p3.mp4"]
    random.shuffle(parts)

    with open(f"{TEMP_DIR}/list.txt", "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")

    concat_out = f"{TEMP_DIR}/concat.mp4"
    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", f"{TEMP_DIR}/list.txt",
        "-c", "copy",
        concat_out
    ]
    subprocess.run(concat_cmd)

    if not os.path.exists(concat_out):
        shutil.copy(input_path, concat_out)

    # trim
    trimmed_out = f"{TEMP_DIR}/trimmed.mp4"
    trim_cmd = [
        "ffmpeg", "-y",
        "-i", concat_out,
        "-t", str(MAX_DURATION),
        "-c", "copy",
        trimmed_out
    ]
    subprocess.run(trim_cmd)

    src = trimmed_out if os.path.exists(trimmed_out) else concat_out

    # final render
    final_cmd = [
        "ffmpeg", "-y",
        "-i", src,
        "-vf", filtergraph,
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        *metadata_opts(),
        "-movflags", "+faststart",
        output_path
    ]

    proc = ffmpeg_with_progress(final_cmd, progress_bar, status_text)

    st.session_state.processing = False
    return proc


# ----------------------------
# UI
# ----------------------------
def main_ui():
    global uploaded

    if st.session_state.video_ready:
        st.video(st.session_state.out_path)

        with open(st.session_state.out_path, "rb") as f:
            downloaded = st.download_button(
                "Download Video",
                f,
                file_name=os.path.basename(st.session_state.out_path),
                key="download_video"
            )

        if downloaded:
            st.session_state.delete_after = True

        return

    if not uploaded:
        st.info("Silakan upload video terlebih dahulu.")
        return

    if not st.session_state.video_ready and not st.session_state.processing:
        if st.button("Mulai Proses Video"):
            temp_input = f"{TEMP_DIR}/input.mp4"
            with open(temp_input, "wb") as fh:
                fh.write(uploaded.read())

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = f"{OUTPUT_DIR}/edited_{ts}.mp4"

            progress_bar = st.progress(0)
            status_text = st.empty()

            proc = run_ffmpeg(temp_input, out_path, progress_bar, status_text)

            if proc.returncode != 0:
                st.error("Ada error, tapi file backup diselamatkan!")
            else:
                status_text.text("Selesai 100%")
                st.success("Video berhasil diproses!")

                st.session_state.video_ready = True
                st.session_state.out_path = out_path
                st.video(st.session_state.out_path)
                with open(st.session_state.out_path, "rb") as f:
                    st.download_button(
                        "Download Video",
                        f,
                        file_name=os.path.basename(st.session_state.out_path),
                        key="download_video"
                    )
            cleanup_temp()
    else:
        st.info("Sedang memproses...")


# ----------------------------
# Auto Delete ONLY that one file
# ----------------------------
def auto_delete_single_file():
    if st.session_state.get("delete_after", False) and st.session_state.get("video_ready", False):

        try:
            os.remove(st.session_state.out_path)
        except:
            pass

        st.session_state.video_ready = False
        st.session_state.delete_after = False
        st.session_state.out_path = None

        st.success("File video telah dihapus otomatis setelah download!")

# ----------------------------
# Run
# ----------------------------
main_ui()
auto_delete_single_file()

if not st.session_state.get("processing", False):
    cleanup_temp()
