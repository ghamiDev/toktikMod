import streamlit as st
import subprocess
import random
import os
import shutil
from datetime import datetime

OUTPUT_DIR = "output"
TEMP_DIR = "temp"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# ================== SESSION CONTROL ==================
if "output_video" not in st.session_state:
    st.session_state["output_video"] = None

st.title("TokTikMod - Versi Stabil 1.1 (Req - Gu51m1n)")

uploaded_files = st.file_uploader(
    "Upload 1 atau 2 video",
    type=["mp4", "mov", "mkv"],
    accept_multiple_files=True
)

if uploaded_files and len(uploaded_files) > 2:
    st.warning("Hanya bisa upload maksimal 2 video!")
    uploaded_files = uploaded_files[:2]


def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


# ==============================================================    
def normalize_video(input_path, output_path):
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "128k",
        output_path
    ]
    run(cmd)


# ==============================================================    
def concat_safest(videos, output):
    list_file = f"{TEMP_DIR}/concat_list.txt"
    with open(list_file, "w") as f:
        for v in videos:
            f.write(f"file '{os.path.abspath(v)}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac",
        output
    ]
    run(cmd)


# ==============================================================    
def split_reencode(input_path):
    for f in os.listdir(TEMP_DIR):
        if f.startswith("seg_"):
            os.remove(f"{TEMP_DIR}/{f}")

    pattern = f"{TEMP_DIR}/seg_%03d.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac",
        "-force_key_frames", "expr:gte(t,n_forced*3)",
        "-segment_time", "3",
        "-f", "segment",
        pattern
    ]

    run(cmd)

    return sorted([f"{TEMP_DIR}/{f}" for f in os.listdir(TEMP_DIR) if f.startswith("seg_")])


# ==============================================================    
def random_flip_segments(segments, progress, start, end):
    total = len(segments)
    flip_count = total // 2
    flip_targets = random.sample(segments, flip_count)

    flipped_segments = []
    step = (end - start) / total
    current = start

    for seg in segments:
        if seg in flip_targets:
            out = seg.replace("seg_", "flip_")
            cmd = [
                "ffmpeg", "-y",
                "-i", seg,
                "-vf", "hflip",
                "-c:v", "libx264", "-preset", "veryfast",
                "-c:a", "aac",
                out
            ]
            run(cmd)
            flipped_segments.append(out)
        else:
            flipped_segments.append(seg)

        current += step
        progress.progress(min(int(current), 100))

    return flipped_segments


# ==============================================================    
def apply_effect(input_path, output_path):
    zoom_h = "iw*1.07"
    zoom_v = "ih*1.07"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf",
        (
            f"scale={zoom_h}:{zoom_v},"
            "crop=1080:1920,"
            "eq=saturation=1.05:contrast=1.03:brightness=0.02"
        ),
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac",
        output_path
    ]

    run(cmd)


# ============= CLEANING FUNCTIONS =============
def clean_temp(temp_dir):
    try:
        for file in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
            else:
                shutil.rmtree(file_path)
    except Exception as e:
        st.warning(f"Failed to clean temp folder: {e}")


def delete_file_after_download(path):
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            st.warning(f"Cannot delete file: {e}")
    st.session_state["output_video"] = None


# ============================== MAIN PROCESS =================================

# Jika video SUDAH digenerate → jangan proses ulang, langsung tampilkan
if st.session_state["output_video"]:
    out_path = st.session_state["output_video"]

    st.success("Video sudah siap! Silakan download.")

    st.video(out_path)

    with open(out_path, "rb") as f:
        st.download_button(
            label="Download Hasil",
            data=f,
            file_name=os.path.basename(out_path),
            mime="video/mp4",
            on_click=lambda: delete_file_after_download(out_path)
        )
    st.stop()


# ======================== PROSES GENERATE VIDEO (1x saja) ========================

if len(uploaded_files) > 0:
    if st.button("Proses Video"):
        # selalu bersihkan temp di awal proses
        clean_temp(TEMP_DIR)

        progress = st.progress(0)
        pct = 0

        normalized_paths = []

        # ===================== 10%: SIMPAN + NORMALISASI =====================
        for i, file in enumerate(uploaded_files):
            raw_path = f"{TEMP_DIR}/raw_{i}.mp4"
            norm_path = f"{TEMP_DIR}/norm_{i}.mp4"

            with open(raw_path, "wb") as f:
                f.write(file.getbuffer())

            normalize_video(raw_path, norm_path)
            normalized_paths.append(norm_path)

            pct += 10
            progress.progress(pct)

        # ===================== 20%: CONCAT =====================
        if len(normalized_paths) == 1:
            merged = normalized_paths[0]
        else:
            merged = f"{TEMP_DIR}/merged.mp4"
            concat_safest(normalized_paths, merged)

        pct = 20
        progress.progress(pct)

        # ===================== 40%: SPLIT =====================
        st.info("Memecah video menjadi segmen 3 detik…")
        segments = split_reencode(merged)

        pct = 40
        progress.progress(pct)

        # ===================== FILTER SEGMENT < 2 DETIK =====================
        valid_segments = []
        for seg in segments:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                seg
            ]
            try:
                dur = float(subprocess.check_output(cmd).decode().strip())
                if dur >= 2:
                    valid_segments.append(seg)
            except:
                continue

        segments = valid_segments

        # ===================== 70%: RANDOM FLIP =====================
        st.info("Memberikan efek horizontal flip, croping dan scaling pada segmen…")
        segments = random_flip_segments(segments, progress, 40, 70)

        # ===================== 80%: SHUFFLE =====================
        random.shuffle(segments)
        pct = 80
        progress.progress(pct)

        # ===================== 90%: CONCAT FINAL =====================
        list_file = f"{TEMP_DIR}/final_list.txt"
        with open(list_file, "w") as f:
            for seg in segments:
                f.write(f"file '{os.path.abspath(seg)}'\n")

        shuffled_path = f"{TEMP_DIR}/shuffled.mp4"

        run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac",
            shuffled_path
        ])

        pct = 90
        progress.progress(pct)

        # ===================== 100%: FINAL EFFECT =====================
        st.info("Menerapkan beberapa efek visual ke video…")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"{OUTPUT_DIR}/toktikmod_{ts}.mp4"

        apply_effect(shuffled_path, out_path)

        pct = 100
        progress.progress(pct)

        # SELESAI
        st.success("Video berhasil diproses 100%!")

        st.video(out_path)

        st.session_state["output_video"] = out_path  # SIMPAN HASIL

        clean_temp(TEMP_DIR)

        with open(out_path, "rb") as f:
            st.download_button(
                label="Download Hasil",
                data=f,
                file_name=os.path.basename(out_path),
                mime="video/mp4",
                on_click=lambda: delete_file_after_download(out_path)
            )
