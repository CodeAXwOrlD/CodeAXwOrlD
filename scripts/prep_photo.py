#!/usr/bin/env python3
"""
Prepare portrait photo for clean monochrome ASCII conversion:
  1. Crop strictly to head + beard/chin using top-level LANDMARKS (pixel coords).
  2. Isolate subject with rembg (or grabCut fallback) + keep largest component.
  3. Extract crisp hair/beard ridges, subtle cheekbone shading, and LAB lip tone.
  4. Locally contrast-stretch real luminance inside each eye for readable eyes.
  5. Render sleek rounded-square spectacles (temple from ear, bridge, and
     outward-protruding right rim) plus nose bridge & nostrils, then trace a
     crisp jaw/cheek/forehead face border outside the lenses.
  6. Composite onto pure white (255) 384x384 canvas with soft neck fade.
"""
import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# Landmark coordinates in source-photo.png pixel space (currently 1024x1024 selfie crop region).
LANDMARKS = {
    "crop": (215, 42, 544, 413),
    "left_lens": ((375, 234), (447, 236), (437, 289), (381, 288)),   # TL, TR, BR, BL
    "right_lens": ((465, 239), (535, 238), (524, 290), (472, 289)),  # TL, TR, BR, BL
    "bridge": ((447, 238), (465, 239)),
    "temple": ((294, 240), (375, 235)),
    "left_eye": {"center": (412, 246), "rx": 21, "ry": 8.0, "sclera_x": 398, "sclera_w": 8.0},
    "right_eye": {"center": (488, 249), "rx": 17, "ry": 8.5, "sclera_x": 475, "sclera_w": 6.0},
    "brow_gap_left": ((378, 229), (415, 228), (448, 231)),
    "brow_gap_right": ((465, 234), (496, 233), (525, 233)),
    "hinge_clear": (367, 255, 11, 18),  # x, y, rx, ry
    "cheek_poly": (
        (352, 240), (465, 240), (508, 240), (505, 296),
        (480, 304), (435, 304), (380, 296), (352, 275),
    ),
    "nose_bridge": ((455, 255), (459, 271), (465, 286), (473, 296)),
    "nose_base": (439, 294, 483, 311),  # x0, y0, x1, y1
    "mouth_frac": (0.76, 0.89, 0.56, 0.84),  # tight mouth seam & lower-lip curve bounds
    "lip_seam": ((420, 341), (446, 339), (462, 340), (478, 342)),
    "philtrum_gap": ((445, 313), (468, 313)),
    "chin_curve": ((310, 368), (345, 385), (376, 398), (415, 407), (452, 407), (475, 394), (492, 365)),
}


def _segment_subject(crop_rgb: np.ndarray) -> np.ndarray:
    """Return alpha mask (0..255) isolating the head silhouette."""
    repo_u2net = Path(__file__).resolve().parent.parent / ".u2net"
    if repo_u2net.exists() and "U2NET_HOME" not in os.environ:
        os.environ["U2NET_HOME"] = str(repo_u2net)

    alpha = None
    try:
        import rembg

        cut = rembg.remove(Image.fromarray(crop_rgb))
        alpha = np.array(cut)[:, :, 3]
    except Exception:
        alpha = None

    if alpha is None:
        h, w = crop_rgb.shape[:2]
        bgr = crop_rgb[:, :, ::-1]
        mask = np.zeros((h, w), np.uint8)
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(bgr, mask, (8, 6, w - 16, h - 12), bgd, fgd, 6, cv2.GC_INIT_WITH_RECT)
        alpha = np.where((mask == 1) | (mask == 3), 255, 0).astype(np.uint8)

    bin_a = (alpha > 155).astype(np.uint8)
    kern_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    bin_a = cv2.morphologyEx(bin_a, cv2.MORPH_OPEN, kern_open)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(bin_a)
    if num > 1:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        clean_bin = (labels == largest).astype(np.uint8)
        clean_bin = cv2.dilate(clean_bin, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        alpha = np.where(clean_bin > 0, alpha, 0).astype(np.uint8)

    return alpha


def _soft_zone(h: int, w: int, y1_frac: float, y2_frac: float, x1_frac: float, x2_frac: float) -> np.ndarray:
    """Create a Gaussian-feathered spatial weight mask in [0, 1]."""
    zone = np.zeros((h, w), dtype=np.float32)
    zone[int(h * y1_frac):int(h * y2_frac), int(w * x1_frac):int(w * x2_frac)] = 1.0
    return cv2.GaussianBlur(zone, (15, 15), 5.0)


def _quad_arc(p0: np.ndarray, ctrl: np.ndarray, p1: np.ndarray, steps: int = 8) -> np.ndarray:
    """Sample points along a quadratic Bezier curve."""
    t = np.linspace(0.0, 1.0, steps, dtype=np.float32)[:, None]
    return (1.0 - t) ** 2 * p0 + 2.0 * (1.0 - t) * t * ctrl + t ** 2 * p1


def _square_lens_poly(
    corners: tuple, x_off: int, y_off: int, rt: float = 6.0, rb: float = 10.5
) -> np.ndarray:
    """Build a sleek rounded-square spectacle lens polygon mapped into crop coordinates."""
    def unit(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        v = b - a
        return v / (np.linalg.norm(v) + 1e-6)

    p_tl, p_tr, p_br, p_bl = [np.array(p, dtype=np.float32) for p in corners]
    segments = [
        _quad_arc(p_tl + rt * unit(p_tl, p_tr), (p_tl + p_tr) * 0.5 - np.array([0.0, 1.0]), p_tr - rt * unit(p_tl, p_tr), 10),
        _quad_arc(p_tr - rt * unit(p_tl, p_tr), p_tr, p_tr + rt * unit(p_tr, p_br), 7),
        _quad_arc(p_tr + rt * unit(p_tr, p_br), (p_tr + p_br) * 0.5, p_br - rb * unit(p_tr, p_br), 8),
        _quad_arc(p_br - rb * unit(p_tr, p_br), p_br, p_br - rb * unit(p_bl, p_br), 8),
        _quad_arc(p_br - rb * unit(p_bl, p_br), (p_br + p_bl) * 0.5 + np.array([0.0, 1.5]), p_bl + rb * unit(p_bl, p_br), 10),
        _quad_arc(p_bl + rb * unit(p_bl, p_br), p_bl, p_bl - rb * unit(p_tl, p_bl), 8),
        _quad_arc(p_bl - rb * unit(p_tl, p_bl), (p_bl + p_tl) * 0.5, p_tl + rt * unit(p_tl, p_bl), 8),
        _quad_arc(p_tl + rt * unit(p_tl, p_bl), p_tl, p_tl + rt * unit(p_tl, p_tr), 7),
    ]
    pts = np.vstack(segments)
    pts[:, 0] -= x_off
    pts[:, 1] -= y_off
    return pts.astype(np.int32)


def _stamp_natural_eye(
    out: np.ndarray,
    gray_f: np.ndarray,
    eye_cfg: dict,
    x_off: int,
    y_off: int,
    p_lo_pct: float,
    p_hi_pct: float,
    dark_gamma: float,
) -> None:
    """Enhance natural photo eye luminance locally so iris, lashes, and sclera pop cleanly."""
    cx_e = eye_cfg["center"][0] - x_off
    cy_e = eye_cfg["center"][1] - y_off
    ex0, ex1 = int(cx_e - eye_cfg["rx"]), int(cx_e + eye_cfg["rx"])
    ey0, ey1 = int(cy_e - eye_cfg["ry"]), int(cy_e + eye_cfg["ry"])
    patch = gray_f[ey0:ey1, ex0:ex1].copy()

    xs_loc = np.arange(ex0, ex1, dtype=np.float32)
    sclera_x = eye_cfg["sclera_x"] - x_off
    boost = 38.0 * np.exp(-((xs_loc - sclera_x) / eye_cfg["sclera_w"]) ** 2)
    patch += boost[None, :]

    p_lo, p_hi = np.percentile(patch, [p_lo_pct, p_hi_pct])
    eye_norm = np.clip((patch - p_lo) / (p_hi - p_lo + 1e-5), 0, 1) ** dark_gamma * 255.0

    em = np.zeros_like(patch, np.float32)
    cv2.ellipse(
        em,
        (patch.shape[1] // 2, patch.shape[0] // 2),
        (max(1, patch.shape[1] // 2 - 1), max(1, patch.shape[0] // 2 - 1)),
        0,
        0,
        360,
        1.0,
        -1,
    )
    em = cv2.GaussianBlur(em, (5, 5), 1.4)
    out[ey0:ey1, ex0:ex1] = out[ey0:ey1, ex0:ex1] * (1.0 - em) + eye_norm * em


def _save_landmark_overlay(
    crop_rgb: np.ndarray,
    left_poly: np.ndarray,
    right_poly: np.ndarray,
    x_off: int,
    y_off: int,
    overlay_path: str,
) -> None:
    """Save diagnostic PNG showing LANDMARKS plotted over the cropped source photo."""
    vis = crop_rgb[:, :, ::-1].copy()
    cv2.polylines(vis, [left_poly], True, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.polylines(vis, [right_poly], True, (0, 255, 0), 2, cv2.LINE_AA)
    b0, b1 = LANDMARKS["bridge"]
    cv2.line(vis, (b0[0] - x_off, b0[1] - y_off), (b1[0] - x_off, b1[1] - y_off), (0, 255, 255), 2)
    t0, t1 = LANDMARKS["temple"]
    cv2.line(vis, (t0[0] - x_off, t0[1] - y_off), (t1[0] - x_off, t1[1] - y_off), (0, 255, 255), 2)

    for key in ("left_eye", "right_eye"):
        ec = LANDMARKS[key]
        cv2.circle(vis, (ec["center"][0] - x_off, ec["center"][1] - y_off), 4, (0, 0, 255), -1)
        cv2.ellipse(
            vis,
            (ec["center"][0] - x_off, ec["center"][1] - y_off),
            (int(ec["rx"]), int(ec["ry"])),
            0, 0, 360, (255, 160, 0), 1,
        )

    nb = np.array([[p[0] - x_off, p[1] - y_off] for p in LANDMARKS["nose_bridge"]], np.int32)
    cv2.polylines(vis, [nb], False, (255, 0, 255), 2, cv2.LINE_AA)
    nx0, ny0, nx1, ny1 = LANDMARKS["nose_base"]
    cv2.rectangle(vis, (nx0 - x_off, ny0 - y_off), (nx1 - x_off, ny1 - y_off), (255, 0, 255), 1)
    cv2.imwrite(overlay_path, vis)
    print(f"Saved landmark overlay: {overlay_path}")


def prep_photo(input_path: str, output_path: str, overlay_path: str | None = None) -> bool:
    in_file = Path(input_path)
    if not in_file.exists():
        print(f"Error: input file '{input_path}' not found.", file=sys.stderr)
        return False

    orig = Image.open(in_file).convert("RGB")
    x1, y1, x2, y2 = LANDMARKS["crop"]
    rgb = np.array(orig.crop((x1, y1, x2, y2)))
    h, w = rgb.shape[:2]

    def pt(ox: int | float, oy: int | float) -> tuple[int, int]:
        return int(ox - x1), int(oy - y1)

    alpha = _segment_subject(rgb)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    smooth = gray.copy()
    for _ in range(3):
        smooth = cv2.bilateralFilter(smooth, 7, 22, 7)

    fg_pixels = smooth[alpha > 128]
    if fg_pixels.size == 0:
        print("Error: foreground segmentation returned empty mask.", file=sys.stderr)
        return False

    interior = cv2.erode((alpha > 145).astype(np.float32), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    interior = cv2.GaussianBlur(interior, (7, 7), 2.0)

    illum = cv2.GaussianBlur(smooth, (0, 0), 42).astype(np.float32) + 1e-5
    flat = np.clip((smooth.astype(np.float32) / illum) * 188.0, 0, 255)
    blended = np.clip(0.58 * smooth.astype(np.float32) + 0.42 * flat, 0, 255)
    lo, hi = np.percentile(blended[alpha > 128], [1, 68])
    tone = np.clip((blended - lo) / (hi - lo + 1e-5), 0, 1)

    fine = cv2.GaussianBlur(smooth, (0, 0), 0.85).astype(np.float32)
    coarse = cv2.GaussianBlur(smooth, (0, 0), 3.8).astype(np.float32)
    dark_ridges = np.clip((coarse - fine) / 22.0, 0, 1) * interior

    # Preserve cheek/jaw beard texture while keeping lips sculpted rather than a solid dark block
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    a_ch = lab[:, :, 1]
    mf_y1, mf_y2, mf_x1, mf_x2 = LANDMARKS["mouth_frac"]
    mouth_zone = _soft_zone(h, w, mf_y1, mf_y2, mf_x1, mf_x2)
    lip_thresh = np.percentile(a_ch[int(h * mf_y1):int(h * mf_y2), int(w * mf_x1):int(w * mf_x2)], 72)
    lip_mask = np.clip((a_ch - lip_thresh) / 10.0, 0, 1) * mouth_zone

    beard_zone = _soft_zone(h, w, 0.72, 0.96, 0.25, 0.90) * (1.0 - 0.75 * mouth_zone)
    ridge_weight = 0.58 + 0.24 * beard_zone
    out = np.clip(tone - ridge_weight * dark_ridges - 0.10 * lip_mask, 0, 1) * 255.0

    # Keep plump center of lower lip soft/bright and draw subtle curved lip-parting seam
    lip_hl = np.zeros((h, w), np.float32)
    cv2.ellipse(lip_hl, pt(453, 349), (17, 4), 0, 0, 360, 1.0, -1)
    lip_hl = cv2.GaussianBlur(lip_hl, (7, 7), 2.0)
    out = out * (1.0 - 0.42 * lip_hl) + 225.0 * (0.42 * lip_hl)

    seam_mask = np.zeros((h, w), np.float32)
    seam_pts = np.array([[p[0] - x1, p[1] - y1] for p in LANDMARKS["lip_seam"]], np.int32)
    cv2.polylines(seam_mask, [seam_pts], False, 1.0, thickness=2, lineType=cv2.LINE_AA)
    seam_mask = cv2.GaussianBlur(seam_mask, (3, 3), 0.7)
    out = out * (1.0 - 0.55 * seam_mask) + 68.0 * (0.55 * seam_mask)

    left_poly = _square_lens_poly(LANDMARKS["left_lens"], x1, y1)
    right_poly = _square_lens_poly(LANDMARKS["right_lens"], x1, y1)

    if overlay_path:
        _save_landmark_overlay(rgb, left_poly, right_poly, x1, y1, overlay_path)

    # Keep lens interiors clean (1.0) for crisp eyes while preserving subtle cheek shading (0.60)
    lens_fill = np.zeros((h, w), np.float32)
    cv2.fillPoly(lens_fill, [left_poly], 1.0)
    cv2.fillPoly(lens_fill, [right_poly], 1.0)
    lens_fill = cv2.dilate(lens_fill, np.ones((3, 3), np.float32))

    cheek_clear = np.zeros((h, w), np.float32)
    cheek_pts = np.array([[p[0] - x1, p[1] - y1] for p in LANDMARKS["cheek_poly"]], np.int32)
    cv2.fillPoly(cheek_clear, [cheek_pts], 1.0)
    cheek_clear = cv2.GaussianBlur(cheek_clear, (21, 21), 6.5)

    wipe_mask = np.maximum(lens_fill, cheek_clear * 0.60)
    top_brow_y = min(p[1] for p in LANDMARKS["brow_gap_left"]) + 1 - y1
    wipe_mask[:max(0, top_brow_y), :] = 0.0
    out = out * (1.0 - wipe_mask) + 255.0 * wipe_mask

    hx, hy, hrx, hry = LANDMARKS["hinge_clear"]
    left_hinge_clear = np.zeros((h, w), np.float32)
    cv2.ellipse(left_hinge_clear, pt(hx, hy), (hrx, hry), 0, 0, 360, 1.0, -1)
    left_hinge_clear = cv2.GaussianBlur(left_hinge_clear, (9, 9), 3.0)
    out = out * (1.0 - left_hinge_clear) + 255.0 * left_hinge_clear

    # Real photo-extracted eyes inside both lenses
    g_f = gray.astype(np.float32)
    _stamp_natural_eye(out, g_f, LANDMARKS["left_eye"], x1, y1, 14, 47, 1.30)
    _stamp_natural_eye(out, g_f, LANDMARKS["right_eye"], x1, y1, 18, 56, 1.65)

    for brow_key, thick in (("brow_gap_left", 4), ("brow_gap_right", 4)):
        bpts = np.array([[p[0] - x1, p[1] - y1] for p in LANDMARKS[brow_key]], np.int32)
        cv2.polylines(out, [bpts], False, 255.0, thickness=thick, lineType=cv2.LINE_AA)

    # White outer halo around protruding top-right corner so it stands clear of right hair lock
    outer_r_halo = np.zeros((h, w), np.float32)
    cv2.polylines(outer_r_halo, [right_poly], True, 1.0, thickness=6, lineType=cv2.LINE_AA)
    outer_r_halo[:, :pt(508, 0)[0]] = 0.0
    out = out * (1.0 - outer_r_halo) + 255.0 * outer_r_halo

    # Frame mask: lenses + bridge + temple arm extending from top of ear
    frame_mask = np.zeros((h, w), np.uint8)
    cv2.polylines(frame_mask, [left_poly], True, 255, thickness=3, lineType=cv2.LINE_AA)
    cv2.polylines(frame_mask, [right_poly], True, 255, thickness=3, lineType=cv2.LINE_AA)
    b0, b1 = LANDMARKS["bridge"]
    cv2.line(frame_mask, pt(*b0), pt(*b1), 255, thickness=3, lineType=cv2.LINE_AA)

    t0, t1 = LANDMARKS["temple"]
    hair_temple_clear = np.zeros((h, w), np.float32)
    cv2.line(hair_temple_clear, pt(t0[0] + 2, t0[1]), pt(t1[0] - 1, t1[1]), 1.0, thickness=10, lineType=cv2.LINE_AA)
    out = out * (1.0 - hair_temple_clear) + 255.0 * hair_temple_clear
    cv2.line(frame_mask, pt(*t0), pt(*t1), 255, thickness=3, lineType=cv2.LINE_AA)

    f_alpha = frame_mask.astype(np.float32) / 255.0
    out = out * (1.0 - f_alpha) + 34.0 * f_alpha

    # Soft feathered nose bridge shade + crisp natural tip/nostrils
    nb_soft = np.zeros((h, w), np.float32)
    nb_pts = np.array([[p[0] - x1, p[1] - y1] for p in LANDMARKS["nose_bridge"]], np.int32)
    cv2.polylines(nb_soft, [nb_pts], False, 1.0, thickness=3, lineType=cv2.LINE_AA)
    nb_soft = cv2.GaussianBlur(nb_soft, (5, 5), 1.6)
    out = out * (1.0 - 0.58 * nb_soft) + 55.0 * (0.58 * nb_soft)

    nx0_o, ny0_o, nx1_o, ny1_o = LANDMARKS["nose_base"]
    nx0, ny0 = pt(nx0_o, ny0_o)
    nx1, ny1 = pt(nx1_o, ny1_o)
    nose_patch = g_f[ny0:ny1, nx0:nx1].copy()
    p_n0, p_n1 = np.percentile(nose_patch, [10, 44])
    nose_norm = np.clip((nose_patch - p_n0) / (p_n1 - p_n0 + 1e-5), 0, 1) ** 1.35 * 255.0
    nm = np.zeros_like(nose_patch, np.float32)
    cv2.ellipse(
        nm,
        (nm.shape[1] // 2, nm.shape[0] // 2 + 1),
        (nm.shape[1] // 2 - 2, nm.shape[0] // 2 - 2),
        0, 0, 360, 1.0, -1,
    )
    nm = cv2.GaussianBlur(nm, (7, 7), 2.0)
    out[ny0:ny1, nx0:nx1] = out[ny0:ny1, nx0:nx1] * (1.0 - nm) + np.minimum(out[ny0:ny1, nx0:nx1], nose_norm) * nm

    # Soft philtrum separation so nostrils never bleed into the mustache peak
    pg_mask = np.zeros((h, w), np.float32)
    pg_pts = np.array([[p[0] - x1, p[1] - y1] for p in LANDMARKS["philtrum_gap"]], np.int32)
    cv2.polylines(pg_mask, [pg_pts], False, 1.0, thickness=3, lineType=cv2.LINE_AA)
    pg_mask = cv2.GaussianBlur(pg_mask, (7, 7), 1.8)
    out = out * (1.0 - 0.65 * pg_mask) + 240.0 * (0.65 * pg_mask)

    # Shape lower chin/jaw silhouette along LANDMARKS["chin_curve"], fading left neck softly
    chin_pts = np.array([[p[0] - x1, p[1] - y1] for p in LANDMARKS["chin_curve"]], np.int32)
    head_poly = np.vstack([np.array([[0, 0], [w, 0], [w, chin_pts[-1, 1]]]), chin_pts[::-1], np.array([[0, chin_pts[0, 1]]])])
    chin_mask = np.zeros((h, w), np.float32)
    cv2.fillPoly(chin_mask, [head_poly], 1.0)
    chin_mask = cv2.GaussianBlur(chin_mask, (15, 15), 5.0)

    eff_alpha = (alpha.astype(np.float32) * chin_mask).astype(np.uint8)

    # Face border (ear, cheek, jaw, chin); skips flat left-neck fade & upper hair/lens bulge
    a_bin = (cv2.GaussianBlur(eff_alpha, (0, 0), 1.6) > 145).astype(np.uint8)
    cnts, _ = cv2.findContours(a_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    border_line = np.zeros((h, w), np.float32)
    if cnts:
        big = max(cnts, key=cv2.contourArea)
        dist = cv2.distanceTransform(a_bin, cv2.DIST_L2, 5)
        rim = np.clip(1.0 - dist / 9.0, 0.0, 1.0) ** 1.6

        border_zone = np.ones((h, w), dtype=np.float32)
        temple_y = pt(*LANDMARKS["temple"][1])[1]
        right_cheek_y = max(p[1] for p in LANDMARKS["right_lens"]) - y1 + 11
        mid_x = w // 2
        border_zone[:max(0, temple_y), :] = 0.0
        border_zone[:max(0, right_cheek_y), mid_x:] = 0.0
        # Zero horizontal flat neck cut on lower-left so neck fades gently instead of forming an L-shelf
        left_jaw_x = pt(358, 0)[0]
        neck_cut_y = pt(0, 360)[1]
        border_zone[max(0, neck_cut_y):, :max(0, left_jaw_x)] = 0.0

        skin_like = np.clip((smooth.astype(np.float32) - 42.0) / 36.0, 0.0, 1.0)
        skin_mask = cv2.GaussianBlur(skin_like, (9, 9), 3.0)
        lower_jaw_boost = _soft_zone(h, w, 0.85, 0.99, 0.43, 0.90)
        border_zone *= (1.0 - lens_fill) * np.maximum(skin_mask, lower_jaw_boost)

        rim *= border_zone
        out = out * (1.0 - 0.58 * rim)
        cv2.polylines(border_line, [big], True, 1.0, thickness=3, lineType=cv2.LINE_AA)
        border_line *= border_zone
        out = out * (1.0 - border_line) + 30.0 * border_line

    mask_float = cv2.GaussianBlur(eff_alpha.astype(np.float32) / 255.0, (0, 0), 0.8)
    mask_float[eff_alpha < 100] = 0.0
    mask_float[border_line > 0.2] = np.maximum(mask_float[border_line > 0.2], border_line[border_line > 0.2])
    mask_float[frame_mask > 20] = np.maximum(mask_float[frame_mask > 20], frame_mask[frame_mask > 20] / 255.0)

    comp = np.clip(out * mask_float + 255.0 * (1.0 - mask_float), 0, 255).astype(np.uint8)
    ys, xs = np.where((eff_alpha > 100) | (frame_mask > 20) | (border_line > 0.2))
    side = int(max(xs.max() - xs.min(), ys.max() - ys.min()) + 28)
    sq = Image.new("L", (side, side), 255)
    crop_box = (int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1))
    fg = Image.fromarray(comp).crop(crop_box)
    sq.paste(fg, ((side - fg.width) // 2, (side - fg.height) // 2))

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    sq.resize((384, 384), Image.LANCZOS).save(out_file)
    print(f"Saved {out_file} (384x384)")
    return True


def main():
    ap = argparse.ArgumentParser(description="Preprocess portrait photo for clean ASCII art.")
    ap.add_argument("--input", "-i", default="source-photo.png")
    ap.add_argument("--output", "-o", default="source-prepped.png")
    ap.add_argument("--overlay", default=None, help="Optional path to save landmark overlay PNG.")
    args = ap.parse_args()
    sys.exit(0 if prep_photo(args.input, args.output, args.overlay) else 1)


if __name__ == "__main__":
    main()
