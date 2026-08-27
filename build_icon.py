"""Сгенерировать иконку Voice-X (микрофон) в voice-x.ico.

Иконка используется и для ярлыка/.exe (PyInstaller), и для системного трея.
Запуск: <venv>\\python.exe build_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

#: акцентный цвет из ui/theme.py (совпадает с фоном кнопок)
ACCENT = (91, 110, 232, 255)
WHITE = (255, 255, 255, 255)


def _icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # фон — скруглённый квадрат акцентного цвета
    d.rounded_rectangle([2, 2, size - 2, size - 2], radius=size // 5, fill=ACCENT)

    cx = size // 2
    w = max(2, size // 5)
    top = size // 4
    bot = size // 2 + size // 12
    # корпус микрофона
    d.rounded_rectangle([cx - w, top, cx + w, bot], radius=w // 2, fill=WHITE)
    # ножка
    d.line([cx, bot, cx, bot + size // 6], fill=WHITE, width=max(2, size // 14))
    # дуга подставки
    d.arc([cx - w, top, cx + w, bot + size // 12], start=0, end=180,
          fill=WHITE, width=max(2, size // 14))
    return img


def main() -> None:
    out = Path(__file__).resolve().parent / "voice-x.ico"
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    master = _icon(256)
    master.save(out, format="ICO", sizes=sizes)
    print(f"OK {out} ({out.stat().st_size} bytes, {len(sizes)} sizes)")


if __name__ == "__main__":
    main()
