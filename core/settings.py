"""Настройки приложения (JSON-файл рядом с проектом).

Держим тут минимум, что влияет на работу движка:
  model_dir   — папка с int8-моделью GigaAM (v3_e2e_ctc.int8.onnx + vocab + config)
  engine      — имя движка (giga / whisper)
  clean      — включена ли очистка текста после распознавания
  output_dir  — куда класть готовые .txt
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.paths import data_dir, project_root, resource_dir

_DEFAULTS_FILE = data_dir() / "settings.json"

#: Разумные пути к модели GigaAM по умолчанию (проверяются по очереди).
_MODEL_CANDIDATES = [
    (resource_dir() / "models"),                                  # забандленная (frozen)
    (project_root() / "models"),                                  # своя папка
    Path(r"E:\Code\Python\writher-V.1.1.0\models"),               # реквизит из writher
    Path.home() / ".cache" / "huggingface"
    / "models--istupakov--gigaam-v3-onnx-int8",
]


@dataclass
class Settings:
    model_dir: str = ""
    output_dir: str = ""
    clean_enabled: bool = False
    engine: str = "gigaam"
    save_mp3: bool = False   # также сохранять MP3 после записи
    models_root: str = ""    # корень с папками моделей для выпадающего списка
    mic_gain: float = 1.0    # усиление микрофона при записи «+ система»
    system_gain: float = 1.0 # усиление системного звука при записи «+ микрофон»
    rec_limiter: bool = True # ограничение уровня при записи (защита от клиппинга)

    @classmethod
    def load(cls, path: Path = _DEFAULTS_FILE) -> "Settings":
        s = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            s = cls(**data)
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            pass
        # если models_root не задан — возьмём стандартный корень моделей
        if not s.models_root:
            s.models_root = _default_models_root()
        return s

    def save(self, path: Path = _DEFAULTS_FILE) -> None:
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def resolve_model_dir(self) -> Path:
        """Первый существующий кандидат. '' невалиден."""
        if self.model_dir and Path(self.model_dir).exists():
            return Path(self.model_dir)
        for cand in _MODEL_CANDIDATES:
            if Path(cand).exists():
                return Path(cand)
        return Path("")


def settings_dir() -> Path:
    return data_dir()


def _default_models_root() -> str:
    """Корень с папками-моделями для выпадающего списка.

    По умолчанию — `D:\\models\\voice` (локальное расположение моделей юзера).
    Можно переопределить в settings.json через `models_root`.
    """
    candidate = Path(r"D:\models\voice")
    return str(candidate) if candidate.is_dir() else ""