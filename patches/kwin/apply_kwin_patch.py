#!/usr/bin/env python3
"""
apply_kwin_patch.py - KWin DRM 10-bit FourCC Disable & 24-bit True Color Enforcer
Target: libkwin.so.6.x (KDE Plasma 6 KWin Wayland DRM Backend)
Hardware: Lenovo Tab M11 (TB311FU / poplar, MediaTek Helio G88 / MT8786 / MT6768)

Rationale:
  MediaTek MT6768 dispsys DRM kernel driver advertises 10-bit formats (XR30, AR30)
  in plane capabilities, but fails atomic commit and hardware rotation when 10-bit
  buffers are submitted. This causes black screens or failure to rotate the display.
  This script safely disables the 10-bit FourCC format codes in libkwin.so so KWin
  cleanly falls back to 24-bit True Color (XRGB8888 / ARGB8888), enabling full
  0°/90°/180°/270° Wayland rotation and HW acceleration.
"""

import sys
import os

TEN_BIT_FOURCCS = [
    b'XR30', b'XB30', b'RX30', b'BX30',
    b'AR30', b'AB30', b'RA30', b'BA30'
]

def patch_libkwin(input_path: str, output_path: str = None) -> bool:
    if output_path is None:
        output_path = input_path

    if not os.path.isfile(input_path):
        print(f"Error: Target file not found: {input_path}")
        return False

    with open(input_path, "rb") as f:
        data = bytearray(f.read())

    total_patched = 0
    for fourcc in TEN_BIT_FOURCCS:
        idx = 0
        while True:
            idx = data.find(fourcc, idx)
            if idx == -1:
                break
            # Null out the fourcc
            data[idx:idx + 4] = b'\x00\x00\x00\x00'
            total_patched += 1
            idx += 4

    print(f"Patched {total_patched} occurrences of 10-bit FourCC codes in {input_path}")

    with open(output_path, "wb") as f:
        f.write(data)

    print(f"Successfully saved patched library to: {output_path}")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apply_kwin_patch.py <path_to_libkwin.so.6> [output_path]")
        sys.exit(1)

    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else inp
    success = patch_libkwin(inp, out)
    sys.exit(0 if success else 1)
