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
    with open(list_file, "w", encoding="utf-8") as f:
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
def split_reencode(input_path, prefix="seg_", segment_time=3):
    for f in os.listdir(TEMP_DIR):
        if f.startswith(prefix):
            try:
                os.remove(os.path.join(TEMP_DIR, f))
            except Exception:
                pass

    pattern = f"{TEMP_DIR}/{prefix}%03d.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac",
        "-force_key_frames", f"expr:gte(t,n_forced*{segment_time})",
        "-segment_time", str(segment_time),
        "-f", "segment",
        pattern
    ]

    run(cmd)

    return sorted([
        os.path.join(TEMP_DIR, f)
        for f in os.listdir(TEMP_DIR)
        if f.startswith(prefix)
    ])


# ==============================================================    
def random_flip_segments(segments, progress, start, end):
    total = len(segments)
    if total == 0:
        return []

    flip_count = total // 2
    flip_targets = random.sample(segments, flip_count) if flip_count > 0 else []

    flipped_segments = []
    step = (end - start) / total if total > 0 else 0
    current = start

    for seg in segments:
        if seg in flip_targets:
            out = os.path.join(
                TEMP_DIR,
                os.path.basename(seg)
                .replace("seg_", "flip_")
                .replace("seg2_", "flip2_")
            )
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
        try:
            progress.progress(min(int(current), 100))
        except:
            pass

    return flipped_segments


# ==============================================================    
def apply_effect(input_path, output_path, mute_final=False):
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf",
        (
            "crop=1080:1920,"
            "unsharp=5:5:0.5,"
            "eq=saturation=1.05:contrast=1.03:brightness=0.02"
        ),
    ]

    if mute_final:
        cmd += ["-an"]
    else:
        cmd += ["-c:a", "aac"]

    cmd += [
        "-c:v", "libx264", "-preset", "medium",
        output_path
    ]

    run(cmd)


# ================= CROP PER SEGMENT (FIXED) =================
def apply_crop_segment(input_path, output_path, crop_y):
    crop_h = 1800 

    vf = (
        f"crop=1080:{crop_h}:0:{crop_y},"
        "scale=1080:1920,"
        "unsharp=5:5:0.5,"
        "eq=saturation=1.05:contrast=1.03:brightness=0.02"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac",
        output_path
    ]

    run(cmd)


# ============= CLEANING FUNCTIONS =============
def clean_temp(temp_dir):
    try:
        for file in os.listdir(temp_dir):
            path = os.path.join(temp_dir, file)
            if os.path.isfile(path):
                os.remove(path)
            else:
                shutil.rmtree(path)
    except Exception as e:
        st.warning(f"Failed to clean temp folder: {e}")


def delete_file_after_download(path):
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            st.warning(f"Cannot delete file: {e}")
    st.session_state["output_video"] = None


def mute_video(input_path, output_path):
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-an",
        "-c:v", "libx264", "-preset", "veryfast",
        output_path
    ]
    run(cmd)


# ============================== MAIN PROCESS =================================

if st.session_state["output_video"]:
    out_path = st.session_state["output_video"]
    st.success("Video sudah siap! Silakan download.")
    st.video(out_path)

    with open(out_path, "rb") as f:
        st.download_button(
            "Download Hasil",
            f,
            os.path.basename(out_path),
            "video/mp4",
            on_click=lambda: delete_file_after_download(out_path)
        )
    st.stop()


if len(uploaded_files) > 0:
    if st.button("Proses Video"):
        clean_temp(TEMP_DIR)
        progress = st.progress(0)
        pct = 0

        normalized_paths = []

        st.info("Pengaturan audio untuk tiap video")
        mute_vid1 = st.checkbox("Matikan suara Video 1", value=True)
        mute_vid2 = False
        if len(uploaded_files) > 1:
            mute_vid2 = st.checkbox("Matikan suara Video 2", value=True)

        for i, file in enumerate(uploaded_files):
            raw = f"{TEMP_DIR}/raw_{i}.mp4"
            norm = f"{TEMP_DIR}/norm_{i}.mp4"

            with open(raw, "wb") as f:
                f.write(file.getbuffer())

            normalize_video(raw, norm)

            if i == 0 and mute_vid1:
                muted = f"{TEMP_DIR}/norm_{i}_muted.mp4"
                mute_video(norm, muted)
                normalized_paths.append(muted)
            elif i == 1 and mute_vid2:
                muted = f"{TEMP_DIR}/norm_{i}_muted.mp4"
                mute_video(norm, muted)
                normalized_paths.append(muted)
            else:
                normalized_paths.append(norm)

            pct += 10
            progress.progress(pct)

        processed_outputs = []
        pct = 20
        progress.progress(pct)

        for i, norm_path in enumerate(normalized_paths):
            prefix = f"seg{i}_"
            segments = split_reencode(norm_path, prefix=prefix)

            valid_segments = []
            for seg in segments:
                try:
                    dur = float(subprocess.check_output([
                        "ffprobe", "-v", "error",
                        "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        seg
                    ]).decode().strip())
                    if dur >= 2:
                        valid_segments.append(seg)
                except:
                    pass

            positions = ["0", "(ih-1920)/2", "ih-1920"]
            cropped_segments = []

            for idx, seg in enumerate(valid_segments):
                crop_y = positions[idx % 3]
                out_seg = os.path.join(TEMP_DIR, "crop_" + os.path.basename(seg))
                apply_crop_segment(seg, out_seg, crop_y)
                cropped_segments.append(out_seg)

            random.shuffle(cropped_segments)

            final_list = f"{TEMP_DIR}/final_list_{i}.txt"
            with open(final_list, "w") as f:
                for seg in cropped_segments:
                    f.write(f"file '{os.path.abspath(seg)}'\n")

            processed = f"{TEMP_DIR}/processed_{i}.mp4"
            run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", final_list,
                "-c:v", "libx264", "-preset", "veryfast",
                "-c:a", "aac",
                processed
            ])

            processed_outputs.append(processed)

        merged = processed_outputs[0] if len(processed_outputs) == 1 else f"{TEMP_DIR}/merged_final.mp4"
        if len(processed_outputs) > 1:
            concat_safest(processed_outputs, merged)

        out = f"{OUTPUT_DIR}/toktikmod_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        apply_effect(merged, out)

        st.session_state["output_video"] = out
        st.success("Video berhasil diproses!")
        st.video(out)
