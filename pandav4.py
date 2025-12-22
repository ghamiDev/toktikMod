import streamlit as st
import subprocess
import random
import os
from datetime import datetime
import time
import cv2
import numpy as np

# ===================== BASIC =====================
def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def seed_init():
    s = random.randint(100000, 999999)
    random.seed(s)
    return s

def delay():
    time.sleep(random.uniform(0.2, 0.5))

def x264(final=False):
    return ["-c:v","libx264","-preset","slow" if final else "medium","-crf","18" if final else "20"]

# ===================== PATH =====================
OUT, TMP = "output", "temp"
os.makedirs(OUT, exist_ok=True)
os.makedirs(TMP, exist_ok=True)

# ===================== AI PROFILE (STATE) =====================
def init_profile():
    return {
        "segment": [3.2, 4.0],
        "speed": [0.99, 1.01],
        "flip": 0.10,
        "motion_boost": 1.0,
        "history": []
    }

# ===================== CORE VIDEO =====================
def normalize(inp, out):
    run(["ffmpeg","-y","-i",inp,
         "-vf","scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
         "-r","30",*x264(),"-c:a","aac","-b:a","128k",out])

def micro_motion(inp, out, boost=1.0):
    run(["ffmpeg","-y","-i",inp,
         "-vf",f"scale=1086:1926,crop=1080:1920:x='3+{2*boost}*sin(t*1.3)':y='3+{2*boost}*cos(t*1.1)'",
         *x264(),"-c:a","copy",out])

def split(inp, prefix, seg):
    run(["ffmpeg","-y","-i",inp,
         "-force_key_frames",f"expr:gte(t,n_forced*{seg})",
         "-segment_time",str(seg),
         "-f","segment",f"{TMP}/{prefix}%03d.mp4"])
    return sorted(f"{TMP}/{x}" for x in os.listdir(TMP) if x.startswith(prefix))

def crop(inp, out):
    run(["ffmpeg","-y","-i",inp,
         "-vf","crop=iw-8:ih-8:x='4+2*sin(t*1.4)':y='4+2*cos(t*1.2)'",
         *x264(),"-c:a","copy",out])

def flip(inp, prob):
    if random.random() > prob:
        return inp, False
    out = f"{TMP}/flip_{os.path.basename(inp)}"
    run(["ffmpeg","-y","-i",inp,"-vf","hflip",*x264(),"-c:a","copy",out])
    return out, True

def concat(files, out):
    txt = f"{TMP}/list.txt"
    with open(txt,"w") as f:
        for x in files:
            f.write(f"file '{os.path.abspath(x)}'\n")
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",txt,*x264(),"-c:a","aac",out])

def speed(inp, out, sp):
    run(["ffmpeg","-y","-i",inp,
         "-filter:v",f"setpts={1/sp}*PTS",
         *x264(),"-c:a","aac","-b:a","128k",out])

def finalize(inp, out):
    run(["ffmpeg","-y","-i",inp,
         "-vf","unsharp=5:5:0.4,eq=saturation=1.04:contrast=1.02",
         *x264(final=True),
         "-pix_fmt","yuv420p",
         "-movflags","+faststart",
         "-c:a","aac","-b:a","128k",out])

# ===================== AUDIT =====================
def audit(video, meta):
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = int(fps * 2)

    prev, motion, bright = None, [], []
    for _ in range(frames):
        r,f = cap.read()
        if not r: break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        bright.append(np.mean(g))
        if prev is not None:
            motion.append(np.mean(cv2.absdiff(prev, g)))
        prev = g
    cap.release()

    m = np.mean(motion) if motion else 0
    b = np.std(bright) if bright else 0

    score, reasons = 0, []
    if m < 3.5: score += 20; reasons.append("motion_low")
    if b < 4: score += 15; reasons.append("brightness_flat")
    if abs(meta["speed"]-1.0) > 0.015: score += 15; reasons.append("speed_noticeable")
    if meta["flip"]/max(meta["seg"],1) > 0.25: score += 20; reasons.append("flip_excess")
    if meta["seg"] > 18: score += 10; reasons.append("segment_over")

    level = "LOW" if score < 30 else "MEDIUM" if score < 60 else "HIGH"
    return score, level, reasons

# ===================== AI DECISION ENGINE =====================
def ai_tweak(profile, reasons):
    """
    Weighted decision:
    hanya tweak faktor yang benar-benar memicu skor
    """
    if "motion_low" in reasons:
        profile["motion_boost"] *= 1.25
        profile["segment"][0] += 0.3
        profile["segment"][1] += 0.3

    if "brightness_flat" in reasons:
        profile["motion_boost"] *= 1.1

    if "speed_noticeable" in reasons:
        profile["speed"] = [0.997, 1.003]

    if "flip_excess" in reasons:
        profile["flip"] *= 0.6

    if "segment_over" in reasons:
        profile["segment"][0] += 0.4
        profile["segment"][1] += 0.4

    # clamp safety
    profile["flip"] = max(0.02, min(profile["flip"], 0.15))
    profile["motion_boost"] = min(profile["motion_boost"], 2.0)

    return profile

# ===================== AUTO RENDER =====================
def auto_render(src, max_try=6):
    profile = init_profile()
    last_score = 999

    for attempt in range(1, max_try+1):
        for f in os.listdir(TMP):
            try: os.remove(f"{TMP}/{f}")
            except: pass

        n, m = f"{TMP}/n.mp4", f"{TMP}/m.mp4"
        normalize(src, n)
        micro_motion(n, m, profile["motion_boost"])

        seg_t = random.uniform(*profile["segment"])
        segs = split(m, "seg_", seg_t)

        final, flip_c = [], 0
        for s in segs:
            c = f"{TMP}/c_{os.path.basename(s)}"
            crop(s, c)
            f2, fl = flip(c, profile["flip"])
            if fl: flip_c += 1
            final.append(f2)

        random.shuffle(final)
        merged = f"{TMP}/merge.mp4"
        concat(final, merged)

        sp = random.uniform(*profile["speed"])
        sped = f"{TMP}/spd.mp4"
        speed(merged, sped, sp)

        out = f"{OUT}/toktik_{datetime.now().strftime('%H%M%S')}_A{attempt}.mp4"
        finalize(sped, out)

        score, level, reasons = audit(out, {
            "speed": sp,
            "flip": flip_c,
            "seg": len(final)
        })

        st.info(f"Attempt {attempt} → Score {score} ({level}) | {reasons}")

        # early stop: trend membaik tajam
        if score < 30:
            return out, score, attempt

        if score >= last_score - 5:
            profile = ai_tweak(profile, reasons)

        last_score = score
        delay()

    return out, score, attempt

# ===================== UI =====================
st.title("TokTikMod – Panda V1.4 (AI Decision Tweak)")

file = st.file_uploader("Upload video", type=["mp4","mov","mkv"])
max_try = st.slider("Max Auto Rerender", 3, 10, 6)

if file and st.button("PROSES AI AUTO"):
    seed_init()
    raw = f"{TMP}/raw.mp4"
    with open(raw,"wb") as f:
        f.write(file.getbuffer())

    out, score, attempt = auto_render(raw, max_try)

    st.success(f"SELESAI di attempt {attempt} | Final Score {score}")
    st.video(out)

    with open(out,"rb") as f:
        st.download_button("Download Final", f, file_name=os.path.basename(out))
