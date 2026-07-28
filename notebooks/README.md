# Notebooks

## `sam2_track.ipynb` — D6, owner: Pranav

The GPU upgrade path for tracking. Runs on Colab; the laptops have no usable GPU.

It must honour the **same `tracks.json` contract** as `blackbox/pipeline/track.py`
(see `blackbox/schemas.py`). Same fields, same units — floor metres, origin at a
corner of the 48 ft box — and the same rule about gaps: a non-wide frame is
present with `pos: null` and is never interpolated across.

Shape of it:

1. Upload the clip + `shots.json`.
2. Click-prompt both bots on the first wide frame of each segment.
3. SAM2-small propagation through the segment.
4. Mask centroids → homography → floor metres.
5. Download `tracks.json`.

Markdown cells carry the exact setup steps, because whoever runs this at 19:00
will not want to debug a Colab install.

**CSRT (D4) is the guaranteed path. This is the upgrade.** If SAM2 isn't working
by Gate 1, it doesn't ship and nothing is lost.
