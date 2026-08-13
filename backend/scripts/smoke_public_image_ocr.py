#!/usr/bin/env python3
"""Public, disposable OCR journey using a generated non-personal test image."""

import base64
import binascii
import json
import os
import struct
import sys
import urllib.error
import urllib.request
import uuid
import zlib


FONT = {
    " ": ["00000"] * 7,
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "N": ["10001", "11001", "11001", "10101", "10011", "10011", "10001"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
}


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)


def build_test_png(text: str = "PINCO OCR 123", scale: int = 8) -> bytes:
    margin = 24
    glyph_width = 5 * scale
    spacing = scale
    width = margin * 2 + len(text) * glyph_width + (len(text) - 1) * spacing
    height = margin * 2 + 7 * scale
    pixels = [bytearray([255] * (width * 3)) for _ in range(height)]
    for index, character in enumerate(text):
        glyph = FONT[character]
        origin_x = margin + index * (glyph_width + spacing)
        for glyph_y, row in enumerate(glyph):
            for glyph_x, bit in enumerate(row):
                if bit != "1":
                    continue
                for dy in range(scale):
                    y = margin + glyph_y * scale + dy
                    for dx in range(scale):
                        x = origin_x + glyph_x * scale + dx
                        offset = x * 3
                        pixels[y][offset:offset + 3] = b"\x00\x00\x00"
    raw = b"".join(b"\x00" + bytes(row) for row in pixels)
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return signature + png_chunk(b"IHDR", header) + png_chunk(b"IDAT", zlib.compress(raw, 9)) + png_chunk(b"IEND", b"")


def request_json(url: str, method: str, payload: dict, token: str = "") -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Pinco-Session"] = token
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OCR endpoint returned HTTP {error.code}: {body[:500]}") from error


def main() -> None:
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PUBLIC_BASE_URL", "")).rstrip("/")
    if not base_url:
        raise SystemExit("Usage: smoke_public_image_ocr.py <base-url>")
    user_id = ""
    token = ""
    bootstrap = request_json(
        f"{base_url}/api/v1/miniapp/bootstrap",
        "POST",
        {"device_id": f"smoke-ocr-{uuid.uuid4().hex}", "platform": "http-smoke", "nickname": "OCR 自动验收"},
    )
    user_id = bootstrap["user"]["user_id"]
    token = bootstrap["session_token"]
    try:
        result = request_json(
            f"{base_url}/api/v1/image/upload",
            "POST",
            {
                "filename": "pinco-ocr-smoke.png",
                "type": "image",
                "user_id": user_id,
                "content": base64.b64encode(build_test_png()).decode("ascii"),
            },
            token,
        )
        normalized_text = "".join(str(result.get("extracted_text", "")).upper().split())
        if not result.get("analysis_available") or "PINCO" not in normalized_text:
            raise RuntimeError(f"OCR did not recognize the expected non-personal marker: {result}")
        if result.get("stored") is not False or result.get("content_retained") is not False:
            raise RuntimeError(f"OCR privacy boundary is not explicit: {result}")
        print(json.dumps({"ok": True, "recognized": "PINCO", "stored": False}, ensure_ascii=False))
    finally:
        if user_id and token:
            request_json(
                f"{base_url}/api/v1/account",
                "DELETE",
                {"user_id": user_id, "confirmation": "DELETE"},
                token,
            )


if __name__ == "__main__":
    main()
