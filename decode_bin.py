#!/usr/bin/env python3
"""
Decode a Spectra 6 .bin back into a viewable PNG.

The converter only goes image -> .bin. This reverses it, so you can preview
exactly what a .bin will show on the panel (and catch orientation or packing
mistakes) before loading it onto the display.

Usage:
    python decode_bin.py path/to/image_1200x1600_s6.bin
    python decode_bin.py foo.bin --rotate 90    # preview as mounted (see note)

Writes <name>_decoded.png (the raw 1200x1600 portrait framebuffer). With
--rotate {90,180,270}, also writes <name>_rot<deg>.png rotated by that many
degrees clockwise -- handy when the frame is hung in landscape and you want to
preview the image the right way up for your mount.
"""
import sys
import os
import argparse
import numpy as np
from PIL import Image

BUF_W, BUF_H = 1200, 1600
BYTES_PER_HALF = (BUF_W // 2) * BUF_H // 2  # 480,000 (1600 rows * 300 bytes)

# EL133UF1 4-bit device code -> RGB (0x4 is unused by the panel)
CODE2RGB = {
    0x0: (0, 0, 0),        # black
    0x1: (255, 255, 255),  # white
    0x2: (255, 255, 0),    # yellow
    0x3: (255, 0, 0),      # red
    0x5: (0, 0, 255),      # blue
    0x6: (0, 255, 0),      # green
}
CODE_NAMES = {0x0: "black", 0x1: "white", 0x2: "yellow", 0x3: "red", 0x5: "blue", 0x6: "green"}


def decode(path):
    """Return (PIL.Image portrait RGB, codes ndarray) for a 960,000-byte .bin."""
    data = np.frombuffer(open(path, "rb").read(), dtype=np.uint8)
    if data.size != 960000:
        raise ValueError(f"{path}: expected 960000 bytes, got {data.size}")

    left_bytes = data[:BYTES_PER_HALF].reshape(BUF_H, 300)
    right_bytes = data[BYTES_PER_HALF:].reshape(BUF_H, 300)

    def unpack(half_bytes):  # high nibble = even column, low nibble = odd column
        out = np.empty((BUF_H, 600), dtype=np.uint8)
        out[:, 0::2] = (half_bytes >> 4) & 0xF
        out[:, 1::2] = half_bytes & 0xF
        return out

    codes = np.empty((BUF_H, BUF_W), dtype=np.uint8)
    codes[:, 0:600] = unpack(left_bytes)       # left half  = columns 0-599
    codes[:, 600:1200] = unpack(right_bytes)   # right half = columns 600-1199

    rgb = np.zeros((BUF_H, BUF_W, 3), dtype=np.uint8)
    for code, colour in CODE2RGB.items():
        rgb[codes == code] = colour
    return Image.fromarray(rgb, "RGB"), codes


def main():
    ap = argparse.ArgumentParser(description="Decode a Spectra 6 .bin to a PNG preview.")
    ap.add_argument("bin_path")
    ap.add_argument("--rotate", type=int, choices=[90, 180, 270], default=None,
                    help="also write a copy rotated this many degrees clockwise "
                         "(for previewing landscape-mounted frames)")
    args = ap.parse_args()

    portrait, codes = decode(args.bin_path)
    stem = os.path.splitext(args.bin_path)[0]
    portrait.save(stem + "_decoded.png")
    print("wrote", stem + "_decoded.png")

    if args.rotate:
        # PIL rotates counter-clockwise, so negate for clockwise.
        portrait.rotate(-args.rotate, expand=True).save(f"{stem}_rot{args.rotate}.png")
        print("wrote", f"{stem}_rot{args.rotate}.png")

    vals, counts = np.unique(codes, return_counts=True)
    print("colors:", {CODE_NAMES.get(int(v), hex(int(v))): int(c) for v, c in zip(vals, counts)})


if __name__ == "__main__":
    main()
