import streamlit as st
import subprocess
import random
import os
import shutil
from datetime import datetime
import time
import cv2
import numpy as np

# ===================== BASIC UTILS =====================
def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def init_render_seed():
    seed = random.randint(100000, 999999)
    random.seed(seed)
    return seed

def human_delay(a=0.15, b=0.45):
    time.sleep(random.uniform(a, b))

def x264_args(final=False):
    if final:
        return ["-c:v", "libx264", "-preset", "slow", "-crf", "18"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]

# ===================== PATH =====================
OUTPUT_DIR = "output"
TEMP_DIR = "temp"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# ===================== PROFILE =====================
EDIT_PROFILES = {
    "affiliate_soft_A": {
        "segment_time": (3.2, 4.1),
        "flip_prob": 0.08,
        "shuffle_mode": "local",
        "speed_range": (0.99, 1.01),
    },
    "affiliate_soft_B": {
        "segment_time": (3.0, 3.8),
        "flip_prob": 0.12,
        "shuffle_mode": "local",
        "speed_range": (0.985, 1.015),
    },
    "mass_hard": {
        "segment_time": (2.4, 3.0),
        "flip_prob": 0.35,
        "shuffle_mode": "neighbor",
        "speed_range": (0.98, 1.02),
    }
}

# ===================== VIDEO CORE =====================
def normalize_video(inp, out):
    run([
        "ffmpeg", "-y", "-i", inp,
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-r", "30",
        *x264_args(),
        "-c:a", "aac", "-b:a", "128k",
        out
    ])

def add_micro_motion(inp, out):
    # time-based micro drift (lebih natural)
    run([
        "ffmpeg", "-y", "-i", inp,
        "-vf",
        "scale=1086:1926,crop=1080:1920:x='3+2*sin(t*1.3)':y='3+2*cos(t*1.1)'",
        *x264_args(),
        "-c:a", "copy",
        out
    ])

def split_video(inp, prefix, seg_time):
    for f in os.listdir(TEMP_DIR):
        if f.startswith(prefix):
            try:
                os.remove(os.path.join(TEMP_DIR, f))
            except:
                pass

    run([
        "ffmpeg", "-y", "-i", inp,
        *x264_args(),
        "-c:a", "aac",
        "-force_key_frames", f"expr:gte(t,n_forced*{seg_time})",
        "-segment_time", str(seg_time),
        "-f", "segment",
        f"{TEMP_DIR}/{prefix}%03d.mp4"
    ])

    return sorted(
        os.path.join(TEMP_DIR, f)
        for f in os.listdir(TEMP_DIR)
        if f.startswith(prefix)
    )

def filter_short_segments(segs, min_dur=2.0):
    valid = []
    for s in segs:
        try:
            dur = float(subprocess.check_output([
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nokey=1:noprint_wrappers=1",
                s
            ]))
            if dur >= min_dur:
                valid.append(s)
        except:
            continue
    return valid

def dynamic_crop(inp, out):
    run([
        "ffmpeg", "-y", "-i", inp,
        "-vf",
        "crop=iw-8:ih-8:x='4+2*sin(t*1.5)':y='4+2*cos(t*1.2)'",
        *x264_args(),
        "-c:a", "copy",
        out
    ])

def flip_prob(seg, prob):
    # batasi flip agar tidak berlebihan
    prob = min(prob, 0.15)
    if random.random() > prob:
        return seg, False

    out = os.path.join(TEMP_DIR, "flip_" + os.path.basename(seg))
    run([
        "ffmpeg", "-y", "-i", seg,
        "-vf", "hflip",
        *x264_args(),
        "-c:a", "copy",
        out
    ])
    return out, True

def apply_speed(inp, out, speed):
    run([
        "ffmpeg", "-y", "-i", inp,
        "-filter:v", f"setpts={1/speed}*PTS",
        *x264_args(),
        "-c:a", "aac", "-b:a", "128k",
        out
    ])

def concat_files(files, out):
    txt = f"{TEMP_DIR}/list.txt"
    with open(txt, "w") as f:
        for x in files:
            f.write(f"file '{os.path.abspath(x)}'\n")

    run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", txt,
        *x264_args(),
        "-c:a", "aac",
        out
    ])

def final_effect(inp, out):
    run([
        "ffmpeg", "-y", "-i", inp,
        "-vf",
        "unsharp=5:5:0.4,eq=saturation=1.04:contrast=1.02",
        *x264_args(final=True),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-video_track_timescale", "90000",
        "-c:a", "aac", "-b:a", "128k",
        out
    ])

# ===================== PL RISK AUDIT =====================
def audit_pl_risk(video_path, meta):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames_to_check = int(fps * 2)

    prev = None
    motion_vals = []
    brightness = []

    for _ in range(frames_to_check):
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness.append(np.mean(gray))

        if prev is not None:
            diff = cv2.absdiff(prev, gray)
            motion_vals.append(np.mean(diff))

        prev = gray

    cap.release()

    motion_avg = np.mean(motion_vals) if motion_vals else 0
    bright_std = np.std(brightness) if brightness else 0

    score = 0
    reasons = []

    if motion_avg < 3.5:
        score += 20
        reasons.append("Hook motion rendah (0–2 detik)")

    if bright_std < 4:
        score += 15
        reasons.append("Variasi brightness terlalu flat")

    if abs(meta["speed_delta"] - 1.0) > 0.015:
        score += 15
        reasons.append("Speed variation terasa")

    flip_ratio = meta["flip_count"] / max(meta["segment_count"], 1)
    if flip_ratio > 0.25:
        score += 20
        reasons.append("Flip terlalu sering")

    if meta["segment_count"] > 18:
        score += 10
        reasons.append("Jumlah segment terlalu banyak")

    level = "LOW" if score < 30 else "MEDIUM" if score < 60 else "HIGH"

    return {
        "score": min(score, 100),
        "level": level,
        "motion_avg": round(motion_avg, 2),
        "brightness_std": round(bright_std, 2),
        "flip_ratio": round(flip_ratio, 2),
        "reasons": reasons
    }

# ===================== STREAMLIT =====================
st.title("TokTikMod – Panda V1.2 (FINAL + PL Risk Audit)")

uploaded = st.file_uploader(
    "Upload video (1–2)",
    type=["mp4", "mov", "mkv"],
    accept_multiple_files=True
)

account_age = st.number_input("Umur akun TikTok (hari)", 0, 3650, 30)

def select_mode(age):
    if age < 14:
        return "mass_hard"
    return random.choice(["affiliate_soft_A", "affiliate_soft_B"])

mode = select_mode(account_age)
profile = EDIT_PROFILES[mode]
st.success(f"Mode aktif: {mode.upper()}")

if uploaded and st.button("PROSES VIDEO"):
    seed = init_render_seed()
    st.info(f"Render seed: {seed}")

    for f in os.listdir(TEMP_DIR):
        try:
            os.remove(os.path.join(TEMP_DIR, f))
        except:
            pass

    processed_all = []
    total_flip = 0
    total_segments = 0
    speed_used = 1.0

    for i, file in enumerate(uploaded):
        raw = f"{TEMP_DIR}/raw_{i}.mp4"
        norm = f"{TEMP_DIR}/norm_{i}.mp4"
        motion = f"{TEMP_DIR}/motion_{i}.mp4"

        with open(raw, "wb") as f:
            f.write(file.getbuffer())

        normalize_video(raw, norm)
        add_micro_motion(norm, motion)

        seg_time = random.uniform(*profile["segment_time"])
        segs = split_video(motion, f"seg{i}_", seg_time)
        segs = filter_short_segments(segs)

        final_segs = []
        for s in segs:
            c = f"{TEMP_DIR}/crop_{os.path.basename(s)}"
            dynamic_crop(s, c)
            f2, flipped = flip_prob(c, profile["flip_prob"])
            if flipped:
                total_flip += 1
            final_segs.append(f2)

        total_segments += len(final_segs)

        if profile["shuffle_mode"] == "local":
            for j in range(0, len(final_segs), 3):
                random.shuffle(final_segs[j:j+3])
        else:
            for j in range(len(final_segs)-1):
                if random.random() < 0.4:
                    final_segs[j], final_segs[j+1] = final_segs[j+1], final_segs[j]

        merged = f"{TEMP_DIR}/merged_{i}.mp4"
        concat_files(final_segs, merged)

        speed_used = random.uniform(*profile["speed_range"])
        sped = f"{TEMP_DIR}/speed_{i}.mp4"
        apply_speed(merged, sped, speed_used)

        processed_all.append(sped)
        human_delay()

    if len(processed_all) == 1:
        final_src = processed_all[0]
    else:
        final_src = f"{TEMP_DIR}/all_merge.mp4"
        concat_files(processed_all, final_src)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"{OUTPUT_DIR}/toktikmod_{ts}.mp4"
    final_effect(final_src, out)

    # ===================== AUDIT =====================
    audit = audit_pl_risk(
        out,
        meta={
            "speed_delta": speed_used,
            "flip_count": total_flip,
            "segment_count": total_segments
        }
    )

    st.success("SELESAI – VIDEO SIAP")
    st.video(out)

    st.subheader("🔍 PL Risk Audit")
    st.metric("PL Risk Score", f"{audit['score']} / 100", audit["level"])

    if audit["level"] == "LOW":
        st.success("Risiko PL rendah — aman untuk upload")
    elif audit["level"] == "MEDIUM":
        st.warning("Risiko PL sedang — disarankan tweak kecil")
    else:
        st.error("Risiko PL tinggi — sebaiknya rerender")

    with st.expander("Detail Analisis"):
        st.write(audit)

    with open(out, "rb") as f:
        st.download_button("Download", f, file_name=os.path.basename(out))
