# Spectra 6 `.bin` Image Converter

Convert ordinary images (JPG, PNG, HEIC, …) into the **`.bin` file format** used by the
**Spectra 6 13.3"** e-ink display (EL133UF1 controller, **1200 × 1600**, 6-color). The script
reuses a color-quantization metric tuned for the muted, real-world colors of Spectra 6
displays, so photos look more natural on the panel than a naive RGB conversion.

The output is a single packed binary file per image — exactly **960,000 bytes** — that you
copy onto the display following its loading procedure (see
[Loading onto the display](#loading-onto-the-display)).

---

## What it does

For each input image, the script:

1. **Auto-orients** the image from its EXIF rotation flag (so phone photos aren't sideways).
2. **Fits** the image into a fixed **1200 × 1600 portrait** frame. By default it *letterboxes*
   — scaling to fit entirely (no cropping) and padding the rest with a **black** border (see
   `--fit` for rotate/crop alternatives).
3. Applies light **brightness / contrast / saturation** enhancement plus edge-enhance,
   smoothing, and sharpening to compensate for the e-ink display's characteristics.
4. **Quantizes** the image to the 6 panel colors (black, white, yellow, red, blue, green)
   using a perceptual distance metric, with your choice of dithering.
5. **Packs** the result into the 4-bit indexed `.bin` format the panel expects and saves it
   as `<original-name>_1200x1600_s6.bin` (next to the input, or in `--output-dir`).

---

## Requirements

- **Python 3.8 or newer**
- **Pillow 9.1 or newer**, plus `numpy` and `tqdm`
- Optional: `pillow-heif` (only for `.heic` input)

> Pillow must be **9.1+** — the converter uses the `Image.Dither` enum introduced in that
> release. Older versions fail with `AttributeError: module 'PIL.Image' has no attribute
> 'Dither'`.
>
> `pillow-heif` is optional. Without it the script runs normally for JPG, PNG, etc. and simply
> disables `.heic` support.

## Installation

Download or clone the repository, then from the repository directory create a virtual
environment and install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

A virtual environment is recommended: recent macOS (Homebrew) and Debian/Ubuntu Python
installs block a global `pip install` with `error: externally-managed-environment`.

Run the commands in the rest of this README from the repository directory, or give the full
path to `convert_to_bin_spectra6.py`.

---

## Usage

### Convert a single image

```bash
python3 convert_to_bin_spectra6.py path/to/your/image.jpg
```

This writes `path/to/your/image_1200x1600_s6.bin`.

### Convert every image in a folder

```bash
python3 convert_to_bin_spectra6.py path/to/your/folder/
```

A `.bin` is created next to each source image. A progress bar shows overall status.

### Convert several files / folders at once

```bash
python3 convert_to_bin_spectra6.py photo1.jpg photo2.png ./album/
```

For the full list of options:

```bash
python3 convert_to_bin_spectra6.py --help
```

> **Existing output files are overwritten without warning.** Each `.bin` is named from the
> source image's base filename (`<name>_1200x1600_s6.bin`), so re-running over the same input
> replaces the previous file. With `--output-dir`, two source images that share a base
> filename (for example `trip1/IMG_0001.jpg` and `trip2/IMG_0001.jpg`) resolve to the same
> output name, and the second overwrites the first.

---

## Options

| Option         | Default     | Description                                                                 |
| -------------- | ----------- | --------------------------------------------------------------------------- |
| `--dither`     | `atkinson`  | Dithering algorithm. `atkinson` = best color, slower. `fs` = Floyd–Steinberg, much faster. |
| `--fit`        | `letterbox` | How to fit the image into the 1200 × 1600 frame. See below.                  |
| `--output-dir` | _(none)_    | Folder to write `.bin` files into. Default: next to each input image.       |
| `--brightness` | `1.1`       | Brightness multiplier (`1.0` = no change).                                  |
| `--contrast`   | `1.2`       | Contrast multiplier (`1.0` = no change).                                    |
| `--saturation` | `1.2`       | Color saturation multiplier (`1.0` = no change).                            |

Example with custom settings:

```bash
python3 convert_to_bin_spectra6.py --dither fs --contrast 1.4 --saturation 1.3 photo.jpg
```

Convert a whole album into a separate output folder:

```bash
python3 convert_to_bin_spectra6.py --output-dir ./bins ./album/
```

### How should I fit images? (`--fit`)

- **`letterbox`** (default) — scale to fit the whole image, padding with black bars. No
  cropping, nothing lost.
- **`rotate`** — turn landscape images 90° upright so they fill the portrait frame better,
  then letterbox the remainder. Best for mixed-orientation photo albums.
- **`crop`** — scale to fill the frame completely and crop the overflow. No black bars, but
  the edges of the image are trimmed.

### Which dithering should I use?

- **`atkinson`** (default) uses the color-tuned matching metric and generally gives the most
  pleasing, color-accurate result. It runs a per-pixel pass in Python, so expect roughly
  **20–30 seconds per image**.
- **`fs`** (Floyd–Steinberg) is near-instant and suited to fast iteration or converting many
  images in one batch, with slightly less color accuracy.

### Processing notes

- **Edge-enhance, smoothing, and sharpening are always applied** (on top of the
  brightness/contrast/saturation multipliers) to suit the e-ink panel. These three filters
  have no flags. Setting `--brightness 1.0 --contrast 1.0 --saturation 1.0` neutralizes the
  multipliers only — the filters still run.
- **Inputs smaller than 1200 × 1600 are scaled up** to fill the frame, so low-resolution
  images will look soft or blocky in the output.

---

## Supported input formats

`.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, `.webp`, `.gif` — plus `.heic` when `pillow-heif`
is installed.

Any aspect ratio is accepted; how it's fitted into the 1200 × 1600 frame depends on `--fit`
(see above). Image orientation is corrected automatically from EXIF metadata.

---

## Loading onto the display

> **TODO — pending hardware-specific details.** This section will cover how to copy the
> generated `.bin` onto the Spectra 6 13.3" display: the required folder and filename layout,
> any index or manifest file the panel expects, and how it selects which image to show. The
> tool produces a standalone `.bin` per image and does not yet rename files or write a manifest.

---

## Output format (technical details)

The `.bin` is the raw frame buffer for the Spectra 6 13.3" panel (EL133UF1 controller):

- **1200 × 1600** pixels, portrait.
- **6 colors**, each stored as a 4-bit device code:

  | Color  | Code  |
  | ------ | ----- |
  | Black  | `0x0` |
  | White  | `0x1` |
  | Yellow | `0x2` |
  | Red    | `0x3` |
  | Blue   | `0x5` |
  | Green  | `0x6` |

- **4-bit indexed, two pixels per byte** — the high nibble is the even column, the low nibble
  is the odd column.
- Each row is split into a **left half (columns 0–599)** and a **right half (columns
  600–1199)**. All left-half bytes for the whole image come first, then all right-half bytes.
- Total size is always exactly **960,000 bytes** (1600 rows × 300 bytes × 2 halves).

---

## Troubleshooting

- **`ModuleNotFoundError: No module named 'pillow_heif'` (or `numpy`, `tqdm`, `PIL`)**
  Run `pip install -r requirements.txt`. On some systems use `pip3` instead of `pip`.
- **`error: externally-managed-environment` when running `pip install`**
  Your system Python blocks global installs (PEP 668). Create and activate a virtual
  environment first — see [Installation](#installation).
- **`AttributeError: module 'PIL.Image' has no attribute 'Dither'`**
  Your Pillow is older than 9.1. Upgrade with `pip install -U "Pillow>=9.1"`.
- **`python: command not found`**
  Use `python3` (as shown in the examples).
- **HEIC files are skipped or error out**
  Make sure `pillow-heif` installed correctly: `pip install pillow-heif`.
- **Atkinson feels stuck**
  It isn't — it's just slow (a single image is ~20–30 s). Use `--dither fs` if you need speed.

---

## Credits

This converter builds on prior open-source work:

- **[PhotoPainter E-Ink Spectra 6 image converter](https://github.com/Toon-nooT/PhotoPainter-E-Ink-Spectra-6-image-converter)**
  by Toon-nooT — the resize/crop pipeline, the tuned RGB + luma color-distance metric, and the
  Atkinson dithering that this tool reuses.

## Issues & contributing

Bug reports and pull requests are welcome at
[github.com/Fraimic/fraimic_bin_converter](https://github.com/Fraimic/fraimic_bin_converter/issues).

## License

This project is open source under the **MIT License** — see [LICENSE](LICENSE).
