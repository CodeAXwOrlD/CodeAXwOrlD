#!/usr/bin/env python3
"""
Convert a prepped grayscale portrait (white background, dark lines/hair) into a
clean, monochrome ASCII-art SVG with looping SMIL left-to-right terminal typing.
Works without JavaScript inside GitHub README <img> tags.
"""
import argparse
import html
import sys
from pathlib import Path
from PIL import Image, ImageEnhance

RAMP = " .`:-=+*cs#%#"  # bright (sparse) -> dark (dense); avoids flat @ blocks in hair


def _lanczos_resample():
    return getattr(Image, "Resampling", Image).LANCZOS


def image_to_ascii_rows(
    src_path: Path,
    cols: int = 155,
    gamma: float = 1.28,
    white_floor: float = 0.74,
) -> list[str]:
    im = Image.open(src_path).convert("L")
    im = ImageEnhance.Contrast(im).enhance(1.05)

    w_src, h_src = im.size
    rows = max(1, round(cols * (h_src / w_src) * (8.0 / 15.0)))
    im = im.resize((cols, rows), _lanczos_resample())
    px = im.load()

    grid = []
    for y in range(rows):
        line = []
        for x in range(cols):
            lum = pow(px[x, y] / 255.0, gamma)
            if lum >= white_floor:
                line.append(" ")
            else:
                idx = int((1.0 - lum) * (len(RAMP) - 1) + 0.5)
                idx = max(0, min(len(RAMP) - 1, idx))
                line.append(RAMP[idx])
        grid.append(line)

    # Remove isolated 1-char specks with spaces on all 4 cardinal neighbors
    for y in range(rows):
        for x in range(cols):
            if grid[y][x] != " ":
                neighbors = [
                    grid[y - 1][x] if y > 0 else " ",
                    grid[y + 1][x] if y + 1 < rows else " ",
                    grid[y][x - 1] if x > 0 else " ",
                    grid[y][x + 1] if x + 1 < cols else " ",
                ]
                if all(n == " " for n in neighbors):
                    grid[y][x] = " "

    lines = ["".join(r) for r in grid]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def render_ascii_svg(
    lines: list[str],
    output_path: Path,
    cols: int = 155,
    title: str = "akhil@github: ~$ ./portrait.sh",
) -> None:
    rows = len(lines)
    art_w_target = 520.0
    cell_w = art_w_target / cols
    cell_h = cell_w * 15.0 / 8.0

    pad = 18.0
    titlebar_h = 30.0
    status_h = 30.0
    art_w = cols * cell_w
    art_h = rows * cell_h
    canvas_w = round(art_w + pad * 2, 1)
    canvas_h = round(titlebar_h + art_h + status_h + pad * 0.7, 1)

    bg = "#0d1117"
    bg2 = "#111722"
    frame = "#30363d"
    title_text = "#7d8590"
    ink = "#c9d1d9"
    cursor_col = "#39d353"

    # 10s looping cycle: 0..4.2s types top->bottom, 4.2..9.3s holds complete, 9.3..10s clears & restarts
    cycle_dur = 10.0
    type_frac = 0.42
    hold_end = 0.93
    art_top = titlebar_h + pad * 0.35
    font_size = cell_h * 0.86

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" height="{canvas_h}" '
        f'viewBox="0 0 {canvas_w} {canvas_h}" '
        f'font-family="DejaVu Sans Mono, Courier New, ui-monospace, Menlo, Consolas, monospace">',
        f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{bg2}"/><stop offset="1" stop-color="{bg}"/>'
        f'</linearGradient></defs>',
        f'<rect width="{canvas_w}" height="{canvas_h}" rx="12" fill="url(#bg)"/>',
        f'<rect x="0.5" y="0.5" width="{canvas_w - 1}" height="{canvas_h - 1}" rx="12" '
        f'fill="none" stroke="{frame}" stroke-width="1"/>',
        f'<line x1="0" y1="{titlebar_h}" x2="{canvas_w}" y2="{titlebar_h}" stroke="{frame}"/>',
    ]

    for i, dotcol in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        parts.append(f'<circle cx="{pad + i * 16}" cy="{titlebar_h / 2}" r="5" fill="{dotcol}"/>')
    parts.append(
        f'<text x="{canvas_w / 2}" y="{titlebar_h / 2 + 4}" fill="{title_text}" font-size="11.5" '
        f'text-anchor="middle">{html.escape(title)}</text>'
    )

    n_rows = max(rows, 1)
    for ry, line in enumerate(lines):
        if not line.strip():
            continue
        padded_line = line.ljust(cols)
        y = art_top + ry * cell_h + cell_h * 0.74
        row_y = art_top + ry * cell_h

        f0 = max(0.001, (ry / n_rows) * type_frac)
        f1 = min(hold_end - 0.01, ((ry + 1) / n_rows) * type_frac)
        f0_pre = max(0.0, f0 - 0.0005)
        f1_post = min(0.999, f1 + 0.0005)

        safe = html.escape(padded_line)
        text = (
            f'<text xml:space="preserve" x="{pad}" y="{y:.1f}" fill="{ink}" '
            f'font-size="{font_size:.2f}" textLength="{art_w:.1f}" lengthAdjust="spacing">{safe}</text>'
        )
        parts.append(
            f'<clipPath id="r{ry}"><rect x="{pad}" y="{row_y:.1f}" height="{cell_h:.2f}" width="0">'
            f'<animate attributeName="width" values="0;0;{art_w:.1f};{art_w:.1f};0" '
            f'keyTimes="0;{f0:.4f};{f1:.4f};{hold_end:.4f};1" dur="{cycle_dur:.1f}s" repeatCount="indefinite"/>'
            f'</rect></clipPath>'
        )
        parts.append(f'<g clip-path="url(#r{ry})">{text}</g>')
        parts.append(
            f'<rect y="{row_y + 0.5:.1f}" width="{max(cell_w, 2.5):.2f}" height="{max(cell_h - 1, 2):.2f}" '
            f'fill="{cursor_col}" opacity="0">'
            f'<animate attributeName="x" values="{pad:.1f};{pad:.1f};{pad + art_w:.1f};{pad + art_w:.1f}" '
            f'keyTimes="0;{f0:.4f};{f1:.4f};1" dur="{cycle_dur:.1f}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0;0;0.85;0.85;0;0" '
            f'keyTimes="0;{f0_pre:.4f};{f0:.4f};{f1:.4f};{f1_post:.4f};1" '
            f'dur="{cycle_dur:.1f}s" repeatCount="indefinite"/></rect>'
        )

    status_line_y = art_top + art_h + pad * 0.35
    status_y = status_line_y + 18
    parts.append(
        f'<line x1="0" y1="{status_line_y:.1f}" x2="{canvas_w}" y2="{status_line_y:.1f}" stroke="{frame}"/>'
    )
    parts.append(
        f'<text x="{pad}" y="{status_y:.1f}" fill="{title_text}" font-size="12">'
        f'akhil@github:~$ whoami <tspan fill="{ink}">Akhil Agarwal</tspan></text>'
    )
    cursor_x = pad + len("akhil@github:~$ whoami Akhil Agarwal ") * 12 * 0.6
    parts.append(
        f'<rect x="{cursor_x:.1f}" y="{status_y - 10.5:.1f}" width="7" height="12.5" fill="{cursor_col}">'
        f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.51;1" '
        f'dur="1s" repeatCount="indefinite"/></rect>'
    )
    parts.append("</svg>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(parts), encoding="utf-8")
    print(f"Rendered {output_path} ({canvas_w}x{canvas_h}, {rows} rows, {len(''.join(parts))} bytes)")


def main():
    ap = argparse.ArgumentParser(description="Generate animated ASCII portrait SVG.")
    ap.add_argument("--input", "-i", default="source-prepped.png")
    ap.add_argument("--output", "-o", default="akhil-ascii.svg")
    ap.add_argument("--width", "-w", type=int, default=155)
    ap.add_argument("--title", default="akhil@github: ~$ ./portrait.sh")
    args = ap.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        print(f"Error: {inp} not found.", file=sys.stderr)
        sys.exit(1)

    lines = image_to_ascii_rows(inp, cols=args.width)
    render_ascii_svg(lines, Path(args.output), cols=args.width, title=args.title)


if __name__ == "__main__":
    main()
