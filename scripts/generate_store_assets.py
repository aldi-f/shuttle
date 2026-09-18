from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRANDING = ROOT / "assets" / "branding"
STORE = ROOT / "assets" / "store" / "windows"
SCREENSHOTS = STORE / "screenshots"
MSIX_ASSETS = ROOT / "packaging" / "windows" / "msix" / "Assets"

NAVY = "#0B2447"
BLUE = "#12356B"
TEAL = "#087E88"
CYAN = "#A8F1E1"
INK = "#172033"
MUTED = "#5C677D"
BORDER = "#C9D3E1"
SURFACE = "#FFFFFF"
CANVAS = "#F3F6FA"
ACCENT = "#0B7285"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    filenames = (
        ("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
    )
    for filename in filenames:
        if Path(filename).exists():
            return ImageFont.truetype(filename, size)
    raise RuntimeError("No supported TrueType font was found")


def _gradient(size: tuple[int, int], start: str, end: str) -> Image.Image:
    width, height = size
    first = tuple(bytes.fromhex(start.removeprefix("#")))
    last = tuple(bytes.fromhex(end.removeprefix("#")))
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(round(a + ((b - a) * ratio)) for a, b in zip(first, last, strict=True))
        draw.line((0, y, width, y), fill=color)
    return image


def _cubic(
    start: tuple[float, float],
    control_1: tuple[float, float],
    control_2: tuple[float, float],
    end: tuple[float, float],
) -> list[tuple[float, float]]:
    points = []
    for step in range(65):
        position = step / 64
        inverse = 1 - position
        x = (
            (inverse**3 * start[0])
            + (3 * inverse**2 * position * control_1[0])
            + (3 * inverse * position**2 * control_2[0])
            + (position**3 * end[0])
        )
        y = (
            (inverse**3 * start[1])
            + (3 * inverse**2 * position * control_1[1])
            + (3 * inverse * position**2 * control_2[1])
            + (position**3 * end[1])
        )
        points.append((x, y))
    return points


def _icon(size: int) -> Image.Image:
    scale = size * 4 / 1024
    canvas_size = size * 4
    background = _gradient((canvas_size, canvas_size), BLUE, TEAL).convert("RGBA")
    mask = Image.new("L", (canvas_size, canvas_size))
    ImageDraw.Draw(mask).rounded_rectangle(
        (64 * scale, 64 * scale, 960 * scale, 960 * scale),
        radius=224 * scale,
        fill=255,
    )
    image = Image.new("RGBA", (canvas_size, canvas_size))
    image.paste(background, mask=mask)
    draw = ImageDraw.Draw(image)

    top = _cubic((278, 397), (390, 243), (641, 232), (757, 363))
    bottom = _cubic((746, 627), (634, 781), (383, 792), (267, 661))
    draw.line(
        [(x * scale, y * scale) for x, y in top],
        fill="white",
        width=round(92 * scale),
        joint="curve",
    )
    draw.line(
        [(x * scale, y * scale) for x, y in bottom],
        fill=CYAN,
        width=round(92 * scale),
        joint="curve",
    )
    radius = 46 * scale
    for x, y, color in ((278, 397, "white"), (746, 627, CYAN)):
        draw.ellipse(
            (
                (x * scale) - radius,
                (y * scale) - radius,
                (x * scale) + radius,
                (y * scale) + radius,
            ),
            fill=color,
        )
    draw.polygon(
        [(728 * scale, 318 * scale), (842 * scale, 397 * scale), (722 * scale, 466 * scale)],
        fill="white",
    )
    draw.polygon(
        [(296 * scale, 706 * scale), (182 * scale, 627 * scale), (302 * scale, 558 * scale)],
        fill=CYAN,
    )
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _save_icons() -> Image.Image:
    BRANDING.mkdir(parents=True, exist_ok=True)
    MSIX_ASSETS.mkdir(parents=True, exist_ok=True)
    master = _icon(1024)
    master.save(BRANDING / "shuttle-icon-1024.png")
    master.save(
        BRANDING / "shuttle.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    for filename, size in (
        ("StoreLogo.png", 50),
        ("Square44x44Logo.png", 44),
        ("Square150x150Logo.png", 150),
        ("Square310x310Logo.png", 310),
    ):
        _icon(size).save(MSIX_ASSETS / filename)
    return master


def _centered(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font,
    fill,
) -> None:
    draw.text(
        ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2),
        text,
        font=font,
        fill=fill,
        anchor="mm",
        align="center",
    )


def _save_marketing_art(master: Image.Image) -> None:
    STORE.mkdir(parents=True, exist_ok=True)

    box = _gradient((1080, 1080), "#071A38", TEAL)
    box_icon = master.resize((500, 500), Image.Resampling.LANCZOS)
    box.paste(box_icon, (290, 140), box_icon)
    draw = ImageDraw.Draw(box)
    _centered(draw, (100, 690, 980, 790), "Shuttle", _font(72, bold=True), "white")
    _centered(
        draw,
        (100, 790, 980, 870),
        "Browse, download, and mirror S3",
        _font(28),
        "#D6F7F4",
    )
    box.save(STORE / "box-art-1x1.png")

    poster = _gradient((1000, 1500), "#071A38", TEAL)
    poster_icon = master.resize((620, 620), Image.Resampling.LANCZOS)
    poster.paste(poster_icon, (190, 200), poster_icon)
    draw = ImageDraw.Draw(poster)
    _centered(draw, (80, 890, 920, 1020), "Shuttle", _font(78, bold=True), "white")
    _centered(
        draw,
        (100, 1030, 900, 1180),
        "Your files.\nYour AWS account.",
        _font(36),
        "#D6F7F4",
    )
    poster.save(STORE / "poster-art-2x3.png")

    wide = _gradient((310, 150), "#071A38", TEAL)
    wide_icon = master.resize((114, 114), Image.Resampling.LANCZOS)
    wide.paste(wide_icon, (18, 18), wide_icon)
    draw = ImageDraw.Draw(wide)
    draw.text((148, 38), "Shuttle", font=_font(25, bold=True), fill="white")
    draw.text((149, 80), "S3 client", font=_font(15), fill="#D6F7F4")
    wide.save(MSIX_ASSETS / "Wide310x150Logo.png")


def _control(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    *,
    button: bool = False,
    muted: bool = False,
) -> None:
    fill = "#E8EEF5" if muted else SURFACE
    outline = "#D5DCE7" if muted else BORDER
    draw.rounded_rectangle(box, radius=6, fill=fill, outline=outline, width=1)
    text_fill = "#7D8798" if muted else INK
    if button:
        _centered(draw, box, text, _font(14, bold=True), text_fill)
    else:
        draw.text(
            (box[0] + 12, (box[1] + box[3]) / 2),
            text,
            font=_font(14),
            fill=text_fill,
            anchor="lm",
        )


def _checkbox(draw: ImageDraw.ImageDraw, x: int, y: int, checked: bool) -> None:
    fill = ACCENT if checked else SURFACE
    draw.rounded_rectangle((x, y, x + 18, y + 18), radius=3, fill=fill, outline=BORDER)
    if checked:
        draw.line((x + 4, y + 9, x + 8, y + 13, x + 15, y + 5), fill="white", width=2)


def _base_screenshot(master: Image.Image) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1366, 768), CANVAS)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1366, 42), fill=NAVY)
    small_icon = master.resize((30, 30), Image.Resampling.LANCZOS)
    image.paste(small_icon, (14, 6), small_icon)
    draw.text(
        (54, 21),
        "Shuttle — an S3 client",
        font=_font(16, bold=True),
        fill="white",
        anchor="lm",
    )
    draw.rectangle((0, 42, 1366, 76), fill=SURFACE)
    for x, text in ((18, "File"), (72, "Settings"), (154, "Help")):
        draw.text((x, 59), text, font=_font(13), fill=INK, anchor="lm")
    draw.line((0, 76, 1366, 76), fill=BORDER)
    return image, draw


def _draw_session(
    draw: ImageDraw.ImageDraw,
    *,
    status: str,
    profile: str = "demo-reader",
    enabled: bool = True,
) -> None:
    draw.text((30, 103), "IAM Identity Center profile:", font=_font(14), fill=INK)
    _control(draw, (230, 90, 1020, 124), profile)
    _control(draw, (1032, 90, 1122, 124), "Refresh", button=True)
    _control(draw, (1134, 90, 1234, 124), "Sign in", button=True)
    draw.text((30, 145), "Session:", font=_font(14), fill=INK)
    draw.text((230, 145), status, font=_font(14), fill=ACCENT if enabled else MUTED)


def _draw_browser(
    draw: ImageDraw.ImageDraw,
    *,
    rows: list[tuple[str, str, str, bool, bool]],
    bucket: str,
    path: str,
    status: str,
    disabled: bool = False,
) -> None:
    draw.text((30, 183), "Bucket:", font=_font(14), fill=INK)
    _control(draw, (110, 169, 1092, 203), bucket, muted=disabled)
    _control(draw, (1104, 169, 1234, 203), "Load buckets", button=True, muted=disabled)
    draw.rounded_rectangle((22, 217, 1344, 500), radius=8, fill=SURFACE, outline=BORDER)
    draw.text((38, 235), "Browse", font=_font(15, bold=True), fill=INK)
    _control(draw, (38, 253, 76, 287), "↑", button=True)
    draw.text((90, 270), "S3 path:", font=_font(14), fill=INK, anchor="lm")
    _control(draw, (158, 253, 1286, 287), path or "/")
    _control(draw, (1296, 253, 1328, 287), "↻", button=True)
    headers = (("Select files and folders", 42), ("Size", 865), ("Last modified", 1030))
    draw.rectangle((38, 299, 1328, 331), fill="#E8EEF5")
    for text, x in headers:
        draw.text((x, 315), text, font=_font(13, bold=True), fill=INK, anchor="lm")
    for index, (name, size, modified, checked, folder) in enumerate(rows):
        top = 331 + (index * 31)
        if index % 2:
            draw.rectangle((38, top, 1328, top + 31), fill="#F7F9FC")
        _checkbox(draw, 45, top + 6, checked)
        prefix = "▸  " if folder else "    "
        draw.text((72, top + 16), f"{prefix}{name}", font=_font(13), fill=INK, anchor="lm")
        draw.text((865, top + 16), size, font=_font(13), fill=MUTED, anchor="lm")
        draw.text((1030, top + 16), modified, font=_font(13), fill=MUTED, anchor="lm")
    draw.text((42, 477), status, font=_font(13), fill=MUTED, anchor="lm")
    _control(draw, (1020, 460, 1115, 489), "Select all", button=True)
    _control(draw, (1125, 460, 1328, 489), "Clear selection", button=True)


def _draw_transfer(
    draw: ImageDraw.ImageDraw,
    *,
    destination: str = "",
    mirror: bool = False,
    preview: bool = False,
) -> None:
    draw.text((30, 535), "Local destination:", font=_font(14), fill=INK)
    _control(draw, (170, 520, 1120, 554), destination)
    _control(draw, (1132, 520, 1234, 554), "Choose…", button=True)
    draw.text((30, 577), "Options:", font=_font(14), fill=INK)
    option = "Mirror (delete extra local files)" if mirror else "Download / update"
    _control(draw, (170, 562, 470, 596), option)
    _checkbox(draw, 490, 570, False)
    draw.text((518, 579), "Overwrite existing files", font=_font(13), fill=INK, anchor="lm")
    _control(draw, (30, 613, 175, 646), "Saved jobs…")
    _control(draw, (187, 613, 330, 646), "Save current job", button=True)
    _control(draw, (342, 613, 500, 646), "Delete saved job", button=True)
    for box, text in (
        ((925, 613, 1015, 646), "Run now"),
        ((1025, 613, 1115, 646), "Preview"),
        ((1125, 613, 1205, 646), "Run"),
        ((1215, 613, 1305, 646), "Cancel"),
    ):
        _control(draw, box, text, button=True, muted=text in {"Run", "Cancel"} and not preview)
    draw.rounded_rectangle((30, 661, 1336, 691), radius=5, fill=SURFACE, outline=BORDER)
    if preview:
        draw.rectangle((31, 662, 1335, 690), fill="#DDF3F0")
        _centered(draw, (31, 662, 1335, 690), "Preview ready", _font(13, bold=True), ACCENT)
    draw.rectangle((0, 728, 1366, 768), fill=SURFACE)
    draw.line((0, 728, 1366, 728), fill=BORDER)
    draw.text((1290, 748), "v0.7.0", font=_font(12), fill=MUTED, anchor="lm")


def _screenshot(
    master: Image.Image,
    *,
    status: str,
    rows: list[tuple[str, str, str, bool, bool]],
    bucket: str,
    path: str,
    selection_status: str,
    destination: str = "",
    mirror: bool = False,
    preview: bool = False,
    disabled: bool = False,
) -> Image.Image:
    image, draw = _base_screenshot(master)
    _draw_session(draw, status=status, enabled=not disabled)
    _draw_browser(
        draw,
        rows=rows,
        bucket=bucket,
        path=path,
        status=selection_status,
        disabled=disabled,
    )
    _draw_transfer(draw, destination=destination, mirror=mirror, preview=preview)
    if preview:
        draw.rounded_rectangle((30, 655, 1336, 719), radius=6, fill="#F7F9FC", outline=BORDER)
        draw.multiline_text(
            (45, 665),
            "Plan: 2 downloads, 0 skipped, 1 deletion\n"
            "DOWNLOAD  executive-summary.pdf       DELETE  old-draft.txt",
            font=_font(12),
            fill=INK,
            spacing=5,
        )
    return image


def _save_screenshots(master: Image.Image) -> None:
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    empty: list[tuple[str, str, str, bool, bool]] = []
    rows = [
        ("archives", "", "", False, True),
        ("charts", "", "", False, True),
        ("executive-summary.pdf", "2.7 MB", "2026-09-16 14:30", False, False),
        ("revenue-by-region.csv", "377 KB", "2026-09-16 14:30", False, False),
        ("forecast.xlsx", "1.6 MB", "2026-09-16 14:30", False, False),
    ]
    selected_rows = [
        (name, size, modified, not folder, folder)
        for name, size, modified, _checked, folder in rows
    ]
    mirror_rows = [
        (name, size, modified, index == 0, folder)
        for index, (name, size, modified, _checked, folder) in enumerate(rows)
    ]
    screenshots = (
        (
            "01-choose-profile.png",
            _screenshot(
                master,
                status="Choose a profile and select Sign in to continue",
                rows=empty,
                bucket="Select a bucket",
                path="/",
                selection_status="Tick files or folders to download them together.",
                disabled=True,
            ),
        ),
        (
            "02-browse-s3.png",
            _screenshot(
                master,
                status="Signed in as demo-reader",
                rows=rows,
                bucket="demo-team-reports",
                path="team-reports/quarterly/",
                selection_status="Tick files or folders to download them together.",
            ),
        ),
        (
            "03-select-downloads.png",
            _screenshot(
                master,
                status="Signed in as demo-reader",
                rows=selected_rows,
                bucket="demo-team-reports",
                path="team-reports/quarterly/",
                selection_status="3 items selected for transfer.",
                destination=r"C:\Users\Demo\Documents\Quarterly reports",
            ),
        ),
        (
            "04-mirror-preview.png",
            _screenshot(
                master,
                status="Preview ready",
                rows=mirror_rows,
                bucket="demo-team-reports",
                path="team-reports/quarterly/",
                selection_status="1 item selected for transfer.",
                destination=r"C:\Users\Demo\Documents\Quarterly reports",
                mirror=True,
                preview=True,
            ),
        ),
    )
    for filename, image in screenshots:
        image.save(SCREENSHOTS / filename, optimize=True)


def main() -> int:
    master = _save_icons()
    _save_marketing_art(master)
    _save_screenshots(master)
    print(f"Generated branding assets in {BRANDING}")
    print(f"Generated Store assets in {STORE}")
    print(f"Generated MSIX assets in {MSIX_ASSETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
