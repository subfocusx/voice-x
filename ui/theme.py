"""Тема оформления Voice-X: цветовая палитра и шрифты.

Один источник правды по цветам, чтобы UI-модули не дублировали hex-коды
и не «уезжали» от единого стиля. Только данные — никакой логики.
"""
from __future__ import annotations

import customtkinter as ctk

# ── палитра (все UI-модули берут цвета отсюда) ──────────────────────────────
COLORS = {
    "window_bg":     "#14141a",   # фон окна
    "surface":       "#1d1d24",   # карточки / панели
    "surface_2":     "#26262f",   # вложенные поверхности, инпуты
    "surface_hover": "#30303b",   # hover поверхностей
    "border":        "#3a3a45",   # рамки
    "accent":        "#5b6ee8",   # основной акцент (сине-фиолетовый)
    "accent_hover":  "#6f7ff2",   # акцент при наведении
    "accent_press":  "#4a5ad0",
    "success":       "#34c47a",   # успех / «Готово»
    "danger":        "#e0556a",   # ошибка / стоп
    "warning":       "#e0a94a",   # пауза / внимание
    "text":          "#ececf1",   # основной текст
    "text_dim":      "#9a9aa8",   # второстепенный текст
    "text_mute":     "#666672",   # приглушённый (плейсхолдеры)
}

#: синонимы для читаемости в коде
WINDOW_BG = COLORS["window_bg"]
SURFACE = COLORS["surface"]
SURFACE_2 = COLORS["surface_2"]
SURFACE_HOVER = COLORS["surface_hover"]
BORDER = COLORS["border"]
ACCENT = COLORS["accent"]
ACCENT_HOVER = COLORS["accent_hover"]
SUCCESS = COLORS["success"]
DANGER = COLORS["danger"]
WARNING = COLORS["warning"]
TEXT = COLORS["text"]
TEXT_DIM = COLORS["text_dim"]
TEXT_MUTE = COLORS["text_mute"]


# ── шрифты ───────────────────────────────────────────────────────────────────
_FAMILY = "Segoe UI"


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    """Удобная обёртка: не плодить CTkFont в каждом модуле."""
    return ctk.CTkFont(family=_FAMILY, size=size, weight=weight)
