"""Read-only, physical-pixel window discovery. No client hooks or injection."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import re

u = C.WinDLL("user32", use_last_error=True)
k = C.WinDLL("kernel32", use_last_error=True)
CALLBACK = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
u.EnumWindows.argtypes = [CALLBACK, W.LPARAM]
u.GetForegroundWindow.restype = W.HWND
u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
u.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
u.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
u.IsWindowVisible.argtypes = [W.HWND]
u.IsIconic.argtypes = [W.HWND]
u.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
u.MonitorFromWindow.restype = W.HANDLE
u.GetMonitorInfoW.argtypes = [W.HANDLE, C.c_void_p]
k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k.OpenProcess.restype = W.HANDLE
k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
k.CloseHandle.argtypes = [W.HANDLE]


class MonitorInfo(C.Structure):
    _fields_ = [("size", W.DWORD), ("monitor", W.RECT), ("work", W.RECT), ("flags", W.DWORD)]


def enable_dpi():
    u.SetProcessDpiAwarenessContext.argtypes = [C.c_void_p]
    u.SetProcessDpiAwarenessContext(C.c_void_p(-4))


def windows(all_processes=False):
    found = []
    foreground = u.GetForegroundWindow()

    @CALLBACK
    def visit(hwnd, _):
        if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
            return True
        pid = W.DWORD()
        u.GetWindowThreadProcessId(hwnd, C.byref(pid))
        handle = k.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return True
        try:
            name, size = C.create_unicode_buffer(32768), W.DWORD(32768)
            if not k.QueryFullProcessImageNameW(handle, 0, name, C.byref(size)):
                return True
            if not all_processes and not re.fullmatch(r"godius(?:_local_combat_v\d+)?\.exe", Path(name.value).name.casefold()):
                return True
            rect, point = W.RECT(), W.POINT(0, 0)
            if not u.GetClientRect(hwnd, C.byref(rect)) or not u.ClientToScreen(hwnd, C.byref(point)):
                return True
            if rect.right <= 0 or rect.bottom <= 0:
                return True
            info = MonitorInfo()
            info.size = C.sizeof(info)
            if not u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, 2), C.byref(info)):
                return True
            found.append({"hwnd": int(hwnd), "pid": pid.value,
                "executable": name.value,
                "rect": (point.x, point.y, point.x + rect.right, point.y + rect.bottom),
                "monitor_height": info.monitor.bottom - info.monitor.top,
                "foreground": hwnd == foreground})
        finally:
            k.CloseHandle(handle)
        return True

    u.EnumWindows(visit, 0)
    return found


def target(selection=None):
    found=windows(all_processes=selection is not None)
    if selection is not None:
        return next((item for item in found if (item['hwnd'],item['pid'])==selection),None)
    return next((item for item in found if item['foreground']),found[0] if found else None)
