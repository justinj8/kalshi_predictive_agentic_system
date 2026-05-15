# Drop your hero asset here

The dashboard intro will auto-detect a file at one of these paths and play it
as the photoreal hero layer instead of the built 2.5D circuit. **No rebuild
needed — just save the file and reload the page.**

Filenames the intro looks for, in order of preference:

```
public/intro/hero.mp4
public/intro/hero.webm
public/intro/hero.jpg
public/intro/hero.jpeg
public/intro/hero.png
```

## What works well

The intro is tuned for **wide, naturalistic shots** like the F1-movie /
Fiorano test-day reference — overcast skies, drone-chase or wide tracking,
the car somewhere in frame.

When a hero asset is detected:

- The intro timeline lengthens (~8s vs ~6s) so the photo/video has room to
  breathe before the title slams in.
- The grade goes lighter (no heavy soft-light LUT wash) so your source
  colour shows through; only a subtle vignette + light film grain remain.
- The internal Ken-Burns is a slow push-in + drift right over 10s.
- The outer camera-rig push-in is mild (the photo has its own motion).
- The 2.5D Ferrari, particle smoke, and speed-blur sweep are disabled —
  they only make sense for the built scene.

## Recommended specs

| Type  | Resolution | Aspect | Notes |
| ----- | ---------- | ------ | ----- |
| Image | ≥ 1920×1080 | 16:9 | JPG ~80% quality is fine |
| Video | ≥ 1920×1080 | 16:9 | <= 10 MB, H.264 MP4 plays everywhere |

The intro is letterboxed, so anything important should be in the central
~78% horizontally and central ~76% vertically.

## Skipping the intro

Click anywhere, or press `Space` / `Esc` / `Enter`.

## Removing the hero

Delete the file (or move it elsewhere) and the intro falls back to the
built 2.5D Ferrari + circuit scene automatically.
