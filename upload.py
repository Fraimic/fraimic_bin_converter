#!/usr/bin/env python3
"""
Send an image to a Fraimic frame over its local REST API.

The converter in this repo produces a `.bin`; this script performs the step the
"Loading onto the display" section used to leave as a TODO -- it pushes a `.bin`
to the panel (POST /api/image), and can optionally convert an ordinary image
first so you go from JPEG/PNG to a rendered frame in one command.

Examples:
    # already have a .bin -> just upload it:
    python upload.py fraimic.local sunset_1200x1600_s6.bin

    # convert an image and upload in one shot:
    python upload.py 192.168.1.42 sunset.jpg --fit crop

    # landscape-mounted frame: rotate 90 deg clockwise before converting:
    python upload.py fraimic.local sunset.jpg --fit crop --rotate 90

The frame must be awake (tap it -- it deep-sleeps and is unreachable when
asleep) and on the same LAN. No authentication is required. If mDNS
(`fraimic.local`) doesn't resolve, pass the frame's IP address instead (find it
in your router's DHCP table). With more than one frame, always use IPs -- the
`fraimic.local` name only points at one of them.
"""
import sys
import os
import json
import argparse
import subprocess
import tempfile
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
CONVERTER = os.path.join(HERE, "convert_to_bin_spectra6.py")
EXPECTED_BYTES = 960000
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".gif", ".heic"}


def convert_image_to_bin(image_path, fit, dither, rotate):
    """Convert an image to a .bin using this repo's converter; return the .bin path."""
    tmpdir = tempfile.mkdtemp(prefix="fraimic_upload_")
    src = image_path
    if rotate:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(image_path))
        img = img.rotate(-rotate, expand=True)  # PIL rotates CCW; negate for clockwise
        src = os.path.join(tmpdir, "rotated.png")
        img.save(src)
    subprocess.run(
        [sys.executable, CONVERTER, "--fit", fit, "--dither", dither,
         "--output-dir", tmpdir, src],
        check=True,
    )
    stem = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(tmpdir, stem + "_1200x1600_s6.bin")
    if not os.path.exists(out):
        raise RuntimeError(f"conversion did not produce expected output: {out}")
    return out


def upload_bin(host, bin_path, timeout=30):
    """POST a .bin to http://<host>/api/image. Return (http_status, body_text)."""
    with open(bin_path, "rb") as f:
        data = f.read()
    if len(data) != EXPECTED_BYTES:
        raise ValueError(
            f"{bin_path}: expected {EXPECTED_BYTES} bytes, got {len(data)} "
            f"(not a valid 1200x1600 Spectra 6 .bin)"
        )
    req = urllib.request.Request(
        f"http://{host}/api/image",
        data=data,
        method="POST",
        headers={"Content-Type": "application/octet-stream"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser(
        description="Upload a .bin (or convert an image and upload it) to a Fraimic frame."
    )
    ap.add_argument("host", help="frame address, e.g. fraimic.local or 192.168.1.42")
    ap.add_argument("path", help="a .bin file, or an image to convert first")
    ap.add_argument("--fit", choices=["letterbox", "rotate", "crop"], default="letterbox",
                    help="how the converter fits the image (only used when converting an image)")
    ap.add_argument("--dither", choices=["atkinson", "fs"], default="atkinson",
                    help="dithering used when converting an image")
    ap.add_argument("--rotate", type=int, choices=[90, 180, 270], default=None,
                    help="rotate the image clockwise before converting "
                         "(useful for landscape-mounted frames)")
    args = ap.parse_args()

    ext = os.path.splitext(args.path)[1].lower()
    if ext == ".bin":
        if args.rotate:
            sys.exit("--rotate only applies when converting an image, not to an existing .bin")
        bin_path = args.path
    elif ext in IMAGE_EXTS:
        print(f"Converting {args.path} ...")
        bin_path = convert_image_to_bin(args.path, args.fit, args.dither, args.rotate)
    else:
        sys.exit(f"Unrecognized input '{args.path}': expected a .bin or an image "
                 f"({', '.join(sorted(IMAGE_EXTS))}).")

    print(f"Uploading {os.path.basename(bin_path)} -> {args.host} ...")
    try:
        status, body = upload_bin(args.host, bin_path)
    except urllib.error.URLError as e:
        sys.exit(f"Upload failed -- is the frame awake and on this LAN? ({e})")

    print(f"HTTP {status}: {body}")
    try:
        if json.loads(body).get("status") == "rendering":
            print("OK -- the frame accepted the image and is rendering; it appears in ~20-30s.")
    except (ValueError, AttributeError):
        pass


if __name__ == "__main__":
    main()
