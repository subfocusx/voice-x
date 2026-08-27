"""Нативный диалог «Открыть файл» (IFileOpenDialog) для Voice-X.

Проблема: tkinter на Windows иногда откатывается на КЛАССИЧЕСКИЙ
comdlg32-диалог ("Look in:", без адресной строки и поиска), когда
COM-апартамент главного потока изменён другими библиотеками (аудио SoundCard,
трей pystray, загрузка ONNX-модели). В классическом диалоге нельзя вставить
путь и нет строки поиска — неудобно.

IFileOpenDialog — современный диалог Explorer (адресная строка, хлебные
крошки, поиск, вставка пути) и НЕ зависит от состояния Tcl/Tk/comctl32:
он рисуется самой оболочкой Windows. Используем его напрямую через ctypes/COM.

Никаких внешних зависимостей; на любой внутренней ошибке функция сама
откатывается на обычный tkinter.filedialog (классический или современный —
как получится), чтобы приложение никогда не ломалось из-за диалога.
"""
from __future__ import annotations

import ctypes
from typing import Optional, Sequence, Tuple

# ── константы COM / оболочки ─────────────────────────────────────────────
CLSCTX_INPROC_SERVER = 0x1
COINIT_APARTMENTTHREADED = 0x2  # STA
SIGDN_FILESYSPATH = 0x80058000   # SIGDN_FILESYSPATH
S_OK = 0

# FOS_* (file open/save options)
FOS_FORCEFILESYSTEM = 0x00000040
FOS_PATHMUSTEXIST = 0x00000800
FOS_FILEMUSTEXIST = 0x00001000

# GUID
_CLSID_FileOpenDialog = "{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}"
_IID_IFileOpenDialog = "{D57C7288-D4AD-4768-BE02-9D969532D960}"

# индексы в vtable (IUnknown>IModalWindow>IFileDialog>IFileOpenDialog)
_V_SHOW = 3         # IModalWindow::Show(HWND)
_V_SETFILE_TYPES = 4  # IFileDialog::SetFileTypes(UINT, COMDLG_FILTERSPEC*)
_V_SETTITLE = 17    # IFileDialog::SetTitle(LPCWSTR)
_V_SETOPTIONS = 9   # IFileDialog::SetOptions(FOS)
_V_GETRESULT = 20   # IFileDialog::GetResult(IShellItem**)
# IShellItem (IUnknown>...>GetDisplayName)
_SI_GETDISPLAYNAME = 5


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, text: str) -> "GUID":
        import re

        m = re.fullmatch(
            r"\{?([0-9A-Fa-f]{8})-([0-9A-Fa-f]{4})-([0-9A-Fa-f]{4})-"
            r"([0-9A-Fa-f]{4})-([0-9A-Fa-f]{12})\}?",
            text,
        )
        if not m:
            raise ValueError(f"неверный GUID: {text!r}")
        g = cls()
        g.Data1 = int(m.group(1), 16)
        g.Data2 = int(m.group(2), 16)
        g.Data3 = int(m.group(3), 16)
        b = bytes.fromhex(m.group(4) + m.group(5))
        g.Data4 = (ctypes.c_ubyte * 8).from_buffer_copy(b)
        return g


class _ComPtr(ctypes.Structure):
    """Минимальная COM-обёртка: первый член — указатель на vtable."""

    _fields_ = [("lpVtbl", ctypes.POINTER(ctypes.c_void_p))]


class COMDLG_FILTERSPEC(ctypes.Structure):
    _fields_ = [
        ("pszName", ctypes.c_wchar_p),
        ("pszSpec", ctypes.c_wchar_p),
    ]


def _vtable_method(vtable, index, restype, argtypes):
    """Достать метод COM-интерфейса по индексу vtable как callable."""
    addr = vtable[index]
    proto = ctypes.WINFUNCTYPE(restype, *argtypes)
    return proto(addr)


def _release(com_ptr):
    """Release() IUnknown для указателя на обёртку COM-объекта."""
    try:
        vtable = com_ptr.contents.lpVtbl
        fn = _vtable_method(vtable, 2, ctypes.c_uint32, [ctypes.c_void_p])
        fn(com_ptr)
    except Exception:  # noqa: BLE001
        pass


def _top_hwnd(owner) -> Optional[int]:
    """Получить реальный HWND верхнего уровня Tk-виджета."""
    try:
        hid = owner.winfo_id()
        user32 = ctypes.windll.user32
        user32.GetParent.restype = ctypes.c_void_p
        user32.GetParent.argtypes = [ctypes.c_void_p]
        parent = user32.GetParent(hid)
        return parent if parent else hid
    except Exception:  # noqa: BLE001
        try:
            return owner.winfo_id()
        except Exception:  # noqa: BLE001
            return None


def askopenfilename(
    title: str = "",
    filetypes: Optional[Sequence[Tuple[str, str]]] = None,
    parent=None,
) -> Optional[str]:
    """Современный диалог «Открыть файл».

    Возвращает выбранный путь или ``""`` при отмене. При любой внутренней
    ошибке откатывается на ``tkinter.filedialog.askopenfilename``.
    """
    # Откат — чтобы диалог никогда не ломал приложение.
    def _fallback():
        from tkinter import filedialog

        try:
            return filedialog.askopenfilename(
                title=title,
                filetypes=list(filetypes or []),
                parent=parent,
            )
        except Exception:  # noqa: BLE001
            return ""

    try:
        # WinDLL (не OleDLL): OleDLL сам бросает OSError на отрицательном
        # HRESULT, а нам нужно перехватить RPC_E_CHANGED_MODE и продолжить.
        ole32 = ctypes.WinDLL("ole32")
        CoInitializeEx = ole32.CoInitializeEx
        CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        CoInitializeEx.restype = ctypes.c_long
        hr_init = CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        # S_OK(0)/S_FALSE(1) — ок; RPC_E_CHANGED_MODE(-2147417850) — поток уже
        # инициализирован (например MTA из SoundCard/comtypes). IFileOpenDialog
        # работает и из MTA, поэтому продолжаем. Любая другая ошибка — откат.
        if hr_init not in (S_OK, 1, -2147417850):
            return _fallback()

        CoCreateInstance = ole32.CoCreateInstance
        CoCreateInstance.argtypes = [
            ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_uint32,
            ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
        ]
        CoCreateInstance.restype = ctypes.c_long

        CoTaskMemFree = ole32.CoTaskMemFree
        CoTaskMemFree.argtypes = [ctypes.c_void_p]
        CoTaskMemFree.restype = None

        clsid = GUID.from_string(_CLSID_FileOpenDialog)
        iid = GUID.from_string(_IID_IFileOpenDialog)

        raw = ctypes.c_void_p()
        hr = CoCreateInstance(
            ctypes.byref(clsid), None, CLSCTX_INPROC_SERVER,
            ctypes.byref(iid), ctypes.byref(raw),
        )
        if hr < S_OK:
            return _fallback()

        dlg = ctypes.cast(raw, ctypes.POINTER(_ComPtr))
        vtable = dlg.contents.lpVtbl

        if title:
            _vtable_method(vtable, _V_SETTITLE, ctypes.c_long,
                           [ctypes.c_void_p, ctypes.c_wchar_p])(dlg, title)

        if filetypes:
            specs = (COMDLG_FILTERSPEC * len(filetypes))()
            for i, (name, spec) in enumerate(filetypes):
                specs[i].pszName = name
                specs[i].pszSpec = spec
            _vtable_method(
                vtable, _V_SETFILE_TYPES, ctypes.c_long,
                [ctypes.c_void_p, ctypes.c_uint32,
                 ctypes.POINTER(COMDLG_FILTERSPEC)],
            )(dlg, len(filetypes), specs)

        options = FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST | FOS_FILEMUSTEXIST
        _vtable_method(vtable, _V_SETOPTIONS, ctypes.c_long,
                       [ctypes.c_void_p, ctypes.c_uint32])(dlg, options)

        owner = _top_hwnd(parent) if parent is not None else 0
        hr = _vtable_method(vtable, _V_SHOW, ctypes.c_long,
                            [ctypes.c_void_p, ctypes.c_void_p])(dlg, owner)
        if hr < S_OK:
            return ""

        item = ctypes.c_void_p()
        hr = _vtable_method(vtable, _V_GETRESULT, ctypes.c_long,
                            [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)])(
            dlg, ctypes.byref(item))
        if hr < S_OK:
            return ""

        try:
            shell = ctypes.cast(item, ctypes.POINTER(_ComPtr))
            svtable = shell.contents.lpVtbl
            pname = ctypes.c_void_p()
            hr = _vtable_method(
                svtable, _SI_GETDISPLAYNAME, ctypes.c_long,
                [ctypes.c_void_p, ctypes.c_int32,
                 ctypes.POINTER(ctypes.c_void_p)],
            )(shell, SIGDN_FILESYSPATH, ctypes.byref(pname))
            if hr < S_OK:
                return ""
            result = ctypes.wstring_at(pname.value)
            CoTaskMemFree(pname.value)
            return result
        finally:
            _release(item)

    except Exception as exc:  # noqa: BLE001
        print(f"[voice-x] нативный диалог недоступен, tkinter-fallback ({exc!r})",
              flush=True)
        return _fallback()
    finally:
        try:
            _release(raw)
        except Exception:  # noqa: BLE001
            pass
