#!/usr/bin/env python3
#encoding: utf-8

"""
Convert images to the Spectra 6 .bin format (Spectra 6 13.3" panel, EL133UF1
controller, 1200x1600, 6-color).

Reuses a tuned 6-color quantization / Atkinson dithering metric, but instead of
saving a BMP it tracks the per-pixel palette index and packs the 4-bit indexed
.bin the panel expects (two pixels per byte, left/right half split, 960,000
bytes total).
"""

import sys
import os
import os.path
import numpy as np
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import argparse
from tqdm import tqdm

# HEIC support is optional: only enabled if pillow-heif is installed. JPEG/PNG/etc
# work without it.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False

# Target panel geometry (Spectra 6 13.3" / EL133UF1)
TARGET_WIDTH = 1200
TARGET_HEIGHT = 1600
EXPECTED_BIN_SIZE = (TARGET_WIDTH // 2) * TARGET_HEIGHT  # 960,000 bytes

# Supported input formats (.heic only when pillow-heif is available)
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.gif']
if HEIC_SUPPORTED:
    IMAGE_EXTENSIONS.append('.heic')

# Define the 6-color palette (black, white, yellow, red, blue, green).
# Order matters: index i maps to COLOR_CODES[i].
PALETTE_COLORS = [
    (0, 0, 0),       # Black
    (255, 255, 255), # White
    (255, 255, 0),   # Yellow
    (255, 0, 0),     # Red
    (0, 0, 255),     # Blue
    (0, 255, 0)      # Green
]

# 4-bit device codes for the EL133UF1 panel. Note 0x4 is intentionally skipped.
#                       Black White Yellow Red  Blue Green
COLOR_CODES = np.array([0x0,  0x1,  0x2,   0x3, 0x5, 0x6], dtype=np.uint8)

# Precompute palette as NumPy arrays for faster access
PALETTE_ARRAY = np.array(PALETTE_COLORS, dtype=np.float32)
# blue and green prints darker, lower its luma value so the distance metric favors it over white, also at luma1
PALETTE_LUMA_ARRAY = np.array([r*250 + g*350 + b*400 for (r, g, b) in PALETTE_COLORS], dtype=np.float32) / (255.0 * 1000)


# Find the closest palette color using floating-point arithmetic (exact RGBL method)
def closest_palette_color(rgb):
    r1, g1, b1 = rgb
    # Calculate luma for the input pixel
    luma1 = (r1 * 250 + g1 * 350 + b1 * 400) / (255.0 * 1000)

    # Calculate differences using precomputed arrays
    diffR = r1 - PALETTE_ARRAY[:, 0]
    diffG = g1 - PALETTE_ARRAY[:, 1]
    diffB = b1 - PALETTE_ARRAY[:, 2]

    # Calculate RGB component of distance
    # boost blue, reduce green a bit and red a little more to compensate for human eye sensitivity and e-ink display characteristics (trial and error)
    rgb_dist = (diffR*diffR*0.250 + diffG*diffG*0.350 + diffB*diffB*0.400) * 0.75 / (255.0*255.0)

    # Calculate luma differences
    luma_diff = luma1 - PALETTE_LUMA_ARRAY
    luma_dist = luma_diff * luma_diff

    # Total distance
    total_dist = 1.5*rgb_dist + 0.60*luma_dist  # hue errors are more important, increased the rgb_dist factor.

    # Find minimum distance index
    return np.argmin(total_dist)


# Atkinson dithering returning a per-pixel palette-index array (not RGB).
# Uses the tuned closest_palette_color metric for each decision.
def quantize_atkinson_indexed(image):
    img_array = np.array(image.convert('RGB'))
    height, width, _ = img_array.shape
    # Use float array for error diffusion to avoid integer truncation issues
    working_img = img_array.astype(np.float32)
    indices = np.zeros((height, width), dtype=np.uint8)

    for y in range(height):
        for x in range(width):
            old_pixel = working_img[y, x].copy()
            # Use exact color comparison instead of lookup table for better accuracy
            idx = closest_palette_color(tuple(np.clip(old_pixel, 0, 255).astype(int)))
            new_pixel = np.array(PALETTE_COLORS[idx], dtype=np.float32)
            working_img[y, x] = new_pixel
            indices[y, x] = idx

            # Calculate error
            error = old_pixel - new_pixel

            # Atkinson error distribution - only to not-yet-processed pixels (right and down)
            # Weights: Right: 1/8, Bottom-left: 1/8, Bottom: 1/4, Bottom-right: 1/8
            # Total distributed: 5/8, which is standard for Atkinson
            if x + 1 < width:
                working_img[y, x + 1] += error * (1/8)
            if y + 1 < height:
                if x - 1 >= 0:
                    working_img[y + 1, x - 1] += error * (1/8)
                working_img[y + 1, x] += error * (1/4)
                if x + 1 < width:
                    working_img[y + 1, x + 1] += error * (1/8)

    return indices


# Floyd-Steinberg via Pillow returning a per-pixel palette-index array.
# Fast, but uses Pillow's plain Euclidean matching rather than the tuned metric.
def quantize_floydsteinberg_indexed(image):
    pal_image = Image.new("P", (1, 1))
    flat_palette = [c for color in PALETTE_COLORS for c in color]
    # Pad to a full 256-entry palette; only the first 6 entries are used.
    pal_image.putpalette(flat_palette + [0, 0, 0] * (256 - len(PALETTE_COLORS)))

    idx_img = image.convert('RGB').quantize(dither=Image.Dither.FLOYDSTEINBERG, palette=pal_image)
    return np.array(idx_img, dtype=np.uint8)


# Fit an (already EXIF-corrected, RGB) image into the fixed 1200x1600 portrait frame.
def fit_to_frame(image, fit):
    img = image
    width, height = img.size

    # 'rotate': turn landscape images upright so they better fill the portrait
    # frame, then letterbox as usual.
    if fit == 'rotate' and width > height:
        img = img.rotate(90, expand=True)
        width, height = img.size

    if fit == 'crop':
        # Scale to fill, then center-crop the overflow (no borders, edges lost).
        scale_ratio = max(TARGET_WIDTH / width, TARGET_HEIGHT / height)
        resized_width = max(1, int(round(width * scale_ratio)))
        resized_height = max(1, int(round(height * scale_ratio)))
        resized = img.resize((resized_width, resized_height), Image.LANCZOS)
        left = (resized_width - TARGET_WIDTH) // 2
        top = (resized_height - TARGET_HEIGHT) // 2
        return resized.crop((left, top, left + TARGET_WIDTH, top + TARGET_HEIGHT))

    # 'letterbox' (and 'rotate' after reorientation): scale to fit entirely inside
    # the frame and pad the remainder with a black border (no cropping).
    scale_ratio = min(TARGET_WIDTH / width, TARGET_HEIGHT / height)
    resized_width = max(1, int(round(width * scale_ratio)))
    resized_height = max(1, int(round(height * scale_ratio)))
    resized = img.resize((resized_width, resized_height), Image.LANCZOS)
    framed = Image.new('RGB', (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0))
    left = (TARGET_WIDTH - resized_width) // 2
    top = (TARGET_HEIGHT - resized_height) // 2
    framed.paste(resized, (left, top))
    return framed


# Pack the per-pixel index array into the EL133UF1 .bin format.
def generate_binary_file(color_indices, output_path):
    """
    EL133UF1 binary format:
    - 1200x1600 pixels
    - 4-bit indexed color, two pixels per byte (high nibble = even col, low = odd col)
    - Split into left half (cols 0-599) then right half (cols 600-1199)
    - Total size: 960,000 bytes
    """
    height, width = color_indices.shape
    if width != TARGET_WIDTH or height != TARGET_HEIGHT:
        raise ValueError(f"Image must be exactly {TARGET_WIDTH}x{TARGET_HEIGHT}, got {width}x{height}")

    # Map palette indices to 4-bit device codes (vectorized)
    color_code_array = COLOR_CODES[color_indices]

    # Process left half (columns 0-599)
    left_half = color_code_array[:, 0:600]
    left_packed = (left_half[:, 0::2] << 4) | left_half[:, 1::2]

    # Process right half (columns 600-1199)
    right_half = color_code_array[:, 600:1200]
    right_packed = (right_half[:, 0::2] << 4) | right_half[:, 1::2]

    # Flatten and concatenate (all left bytes, then all right bytes)
    binary_data = np.concatenate([
        left_packed.flatten(),
        right_packed.flatten()
    ]).astype(np.uint8)

    if len(binary_data) != EXPECTED_BIN_SIZE:
        raise ValueError(f"Binary file must be exactly {EXPECTED_BIN_SIZE} bytes, got {len(binary_data)}")

    with open(output_path, 'wb') as f:
        f.write(binary_data.tobytes())


# Convert a single image file to a .bin. Returns True on success, False on failure.
def process_image(image_file, args):
    try:
        # Read input image and apply EXIF orientation so phone photos aren't sideways.
        input_image = ImageOps.exif_transpose(Image.open(image_file)).convert('RGB')

        # Fit into the fixed 1200x1600 portrait frame per the chosen mode.
        framed_image = fit_to_frame(input_image, args.fit)

        # Apply enhancements (brightness, contrast, saturation)
        enhanced_image = ImageEnhance.Brightness(framed_image).enhance(args.brightness)
        enhanced_image = ImageEnhance.Contrast(enhanced_image).enhance(args.contrast)
        enhanced_image = ImageEnhance.Color(enhanced_image).enhance(args.saturation)

        # Add edge enhancement
        enhanced_image = enhanced_image.filter(ImageFilter.EDGE_ENHANCE)
        # Add noise reduction
        enhanced_image = enhanced_image.filter(ImageFilter.SMOOTH)
        # Add sharpening for better detail visibility
        enhanced_image = enhanced_image.filter(ImageFilter.SHARPEN)

        # Quantize to per-pixel palette indices
        if args.dither == 'atkinson':
            color_indices = quantize_atkinson_indexed(enhanced_image)
        else:
            color_indices = quantize_floydsteinberg_indexed(enhanced_image)

        # Determine output path (next to input, or in --output-dir if given)
        out_name = os.path.splitext(os.path.basename(image_file))[0] + '_1200x1600_s6.bin'
        if args.output_dir:
            output_filename = os.path.join(args.output_dir, out_name)
        else:
            output_filename = os.path.join(os.path.dirname(image_file), out_name)

        generate_binary_file(color_indices, output_filename)

        print(f'Successfully converted {image_file} to {output_filename}')
        return True
    except Exception as e:
        print(f'Error processing {image_file}: {e}')
        return False


def parse_args():
    parser = argparse.ArgumentParser(description='Convert images to Spectra 6 .bin (1200x1600, Spectra 6 13.3" / EL133UF1).')
    parser.add_argument('input_paths', nargs='+', type=str, help='Input image file(s) or directory')
    parser.add_argument('--dither', choices=['atkinson', 'fs'], default='atkinson',
                        help='Dithering algorithm: atkinson (tuned metric, slow) or fs (Floyd-Steinberg, fast)')
    parser.add_argument('--fit', choices=['letterbox', 'rotate', 'crop'], default='letterbox',
                        help='How to fit images into the 1200x1600 frame: letterbox (black bars, no crop), '
                             'rotate (turn landscape upright then letterbox), or crop (fill and crop edges)')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Directory to write .bin files into (default: next to each input image)')
    parser.add_argument('--brightness', type=float, default=1.1, help='Brightness factor (1.0 = no change)')
    parser.add_argument('--contrast', type=float, default=1.2, help='Contrast factor (1.0 = no change)')
    parser.add_argument('--saturation', type=float, default=1.2, help='Color saturation factor (1.0 = no change)')
    return parser.parse_args()


# Collect image files from the given file/dir paths.
def collect_image_files(input_paths):
    all_image_files = []
    for input_path in input_paths:
        if not os.path.exists(input_path):
            print(f'Error: path {input_path} does not exist')
            continue

        if os.path.isfile(input_path):
            all_image_files.append(input_path)
        elif os.path.isdir(input_path):
            found_any = False
            for file in os.listdir(input_path):
                file_path = os.path.join(input_path, file)
                if (os.path.isfile(file_path) and
                        any(file.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)):
                    all_image_files.append(file_path)
                    found_any = True
            if not found_any:
                print(f'Warning: no image files found in directory {input_path}')
        else:
            print(f'Error: {input_path} is not a valid file or directory')
    return all_image_files


def main():
    args = parse_args()

    if not HEIC_SUPPORTED:
        print("Note: pillow-heif not installed; .heic input is disabled (install it to enable).")
    if args.dither == 'atkinson':
        print("Using Atkinson dithering (tuned color metric). Note: --dither fs is much faster but less color-accurate.")
    else:
        print("Using Floyd-Steinberg dithering (fast).")

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)

    all_image_files = collect_image_files(args.input_paths)
    if not all_image_files:
        print('Error: no valid image files to process')
        sys.exit(1)

    print(f'Found {len(all_image_files)} image files to process')
    failures = 0
    for image_file in tqdm(all_image_files, desc="Processing images", unit="file"):
        if not process_image(image_file, args):
            failures += 1

    if failures:
        print(f'{failures} of {len(all_image_files)} file(s) failed to convert')
        sys.exit(1)


if __name__ == '__main__':
    main()
