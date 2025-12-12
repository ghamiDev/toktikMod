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
    """
    Split input into segments with given prefix (to avoid collisions between videos).
    Returns sorted list of generated segment paths.
    """
    # clean old segments with same prefix
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

    return sorted([os.path.join(TEMP_DIR, f) for f in os.listdir(TEMP_DIR) if f.startswith(prefix)])


# ==============================================================    
def random_flip_segments(segments, progress, start, end):
    """
    Randomly flip ~half segments. Guard against zero length.
    """
    total = len(segments)
    if total == 0:
        return []

    flip_count = total // 2
    flip_targets = random.sample(segments, flip_count) if flip_count > 0 else []

    flipped_segments = []
    # prevent division by zero
    step = (end - start) / total if total > 0 else 0
    current = start

    for seg in segments:
        if seg in flip_targets:
            out = os.path.join(TEMP_DIR, os.path.basename(seg).replace("seg_", "flip_").replace("seg2_", "flip2_"))
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
        except Exception:
            pass

    return flipped_segments


# ==============================================================    
def apply_effect(input_path, output_path, mute_final=False):
    zoom_h = "iw*1.05"
    zoom_v = "ih*1.05"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf",
        (
            f"scale={zoom_h}:{zoom_v},"
            "crop=1080:1920,"
            "unsharp=5:5:0.5,"
            "eq=saturation=1.05:contrast=1.03:brightness=0.02"
        ),
    ]

    if mute_final:
        # drop audio
        cmd += ["-an"]
    else:
        cmd += ["-c:a", "aac"]

    cmd += [
        "-c:v", "libx264", "-preset", "medium",
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


# -----------------------
# Helper: mute file by re-encoding without audio
# -----------------------
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

        # ----------------------------
        # Pilihan mute per-video (UI)
        # ----------------------------
        st.info("Pengaturan audio untuk tiap video")
        mute_vid1 = st.checkbox("Matikan suara Video 1", value=True)
        mute_vid2 = False
        if len(uploaded_files) > 1:
            mute_vid2 = st.checkbox("Matikan suara Video 2", value=True)

        # ===================== 10%: SIMPAN + NORMALISASI =====================
        for i, file in enumerate(uploaded_files):
            raw_path = f"{TEMP_DIR}/raw_{i}.mp4"
            norm_path = f"{TEMP_DIR}/norm_{i}.mp4"

            with open(raw_path, "wb") as f:
                f.write(file.getbuffer())

            normalize_video(raw_path, norm_path)

            # apply mute per user's choice — create a separate file so original normalized stays if needed
            if i == 0 and mute_vid1:
                norm_muted = f"{TEMP_DIR}/norm_{i}_muted.mp4"
                mute_video(norm_path, norm_muted)
                normalized_paths.append(norm_muted)
            elif i == 1 and mute_vid2:
                norm_muted = f"{TEMP_DIR}/norm_{i}_muted.mp4"
                mute_video(norm_path, norm_muted)
                normalized_paths.append(norm_muted)
            else:
                normalized_paths.append(norm_path)

            pct += 10
            progress.progress(pct)

        # ===================== 20%: Jika satu file → proses langsung; jika dua file → proses per-file terpisah =====================
        processed_outputs = []  # akan menampung hasil processed per-file (masih belum digabung)
        pct = 20
        progress.progress(pct)

        for i, norm_path in enumerate(normalized_paths):
            st.info(f"Memproses file ke-{i+1} secara terpisah...")
            # split -> filter -> flip -> shuffle -> concat (per-file)
            prefix = f"seg{i}_"  # unikkan prefix per file
            segments = split_reencode(norm_path, prefix=prefix)

            pct += 5
            progress.progress(pct)

            # filter segmen < 2 detik (konsep awal)
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

            # fallback: jika semua terfilter, coba split ulang dengan segment_time=2 (prefix seg{i}2_)
            if len(valid_segments) == 0:
                st.warning(f"Semua segmen file ke-{i+1} kurang dari 2 detik. Melakukan split ulang 2 detik untuk file ini.")
                # clean seg{i}2_ files if any
                for f in os.listdir(TEMP_DIR):
                    if f.startswith(f"{prefix}2_"):
                        try:
                            os.remove(os.path.join(TEMP_DIR, f))
                        except Exception:
                            pass
                segments2 = split_reencode(norm_path, prefix=f"{prefix}2_", segment_time=2)
                # accept these segments as fallback
                valid_segments = [s for s in segments2 if os.path.exists(s)]

                if len(valid_segments) == 0:
                    st.error(f"Gagal membuat segmen valid untuk file ke-{i+1}. Melewatkan file ini.")
                    continue

            pct += 5
            progress.progress(pct)

            # random flip on file's segments
            st.info(f"Memberi efek flip pada segmen file ke-{i+1}...")
            valid_segments = random_flip_segments(valid_segments, progress, pct, pct+20)

            pct += 10
            progress.progress(pct)

            # shuffle segments
            random.shuffle(valid_segments)

            pct += 5
            progress.progress(pct)

            # concat these segments into single processed file for this input
            final_list = f"{TEMP_DIR}/final_list_{i}.txt"
            with open(final_list, "w", encoding="utf-8") as f:
                for seg in valid_segments:
                    f.write(f"file '{os.path.abspath(seg)}'\n")

            processed_out = f"{TEMP_DIR}/processed_{i}.mp4"
            run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", final_list,
                "-c:v", "libx264", "-preset", "veryfast",
                "-c:a", "aac",
                processed_out
            ])

            processed_outputs.append(processed_out)

            pct += 5
            progress.progress(pct)

        # ===================== 80%: Jika ada 2 processed_outputs -> concat di akhir, jika hanya 1 -> langsung pakai itu =====================
        pct = 80
        progress.progress(pct)

        if len(processed_outputs) == 0:
            st.error("Tidak ada file yang berhasil diproses.")
            st.stop()

        if len(processed_outputs) == 1:
            merged_final = processed_outputs[0]
        else:
            st.info("Menggabungkan hasil kedua video di akhir...")
            merged_final = f"{TEMP_DIR}/merged_final.mp4"
            concat_safest(processed_outputs, merged_final)

        pct = 90
        progress.progress(pct)

        # ===================== 100%: FINAL EFFECT =====================
        st.info("Menerapkan beberapa efek visual ke video…")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"{OUTPUT_DIR}/toktikmod_{ts}.mp4"

        # jika ingin mute final juga: set mute_final=True
        apply_effect(merged_final, out_path, mute_final=False)

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
       
