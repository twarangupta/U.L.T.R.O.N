"""Read text from the screen with the OCR that ships inside Windows (D37).

No Tesseract, no download: Windows.Media.Ocr is part of Windows 10 and 11 and
uses the language packs the user already has. Everything stays in memory, no
temporary picture is written.

    text = read_text(grab_screen())          # the whole screen
    text = read_text(grab_active_window())   # only the window in front
"""
from __future__ import annotations

import asyncio
import ctypes
import io
from ctypes import wintypes


class OcrUnavailable(RuntimeError):
    """Windows OCR cannot run here (no winrt packages, or no OCR language installed)."""


def grab_screen():
    """The whole screen as a PIL image."""
    import pyautogui
    return pyautogui.screenshot()


def grab_active_window():
    """The window in front as a PIL image; None if it cannot be found or has no size."""
    import pyautogui
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    rect = wintypes.RECT()
    if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    left, top = max(rect.left, 0), max(rect.top, 0)
    width, height = rect.right - left, rect.bottom - top
    if width < 20 or height < 20:
        return None
    return pyautogui.screenshot(region=(left, top, width, height))


async def _recognize(png_bytes: bytes) -> str:
    try:
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
    except ImportError as e:
        raise OcrUnavailable("The Windows OCR packages are not installed.") from e
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrUnavailable("Windows has no OCR language installed.")
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png_bytes)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    result = await engine.recognize_async(bitmap)
    return "\n".join(line.text for line in result.lines)


def read_text(image) -> str:
    """The text in a PIL image, one line per line. Raises OcrUnavailable."""
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return asyncio.run(_recognize(buffer.getvalue())).strip()
