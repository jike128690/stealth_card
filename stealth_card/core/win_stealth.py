"""Windows 系统级隐蔽能力封装（对应开发计划文档 3.2）。

覆盖单实例互斥锁、防投屏/防截图隔离、双模态鼠标穿透、
键鼠闲置时间计算，以及前台窗口与光标位置探测。
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011
ERROR_ALREADY_EXISTS = 183


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


# 显式声明 64 位下的句柄签名，避免 ctypes 默认 int 截断 HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowDisplayAffinity.restype = wintypes.BOOL


class WinStealthController:
    _mutex_handle = None

    @classmethod
    def acquire_single_instance(cls, mutex_name="Global\\StealthCardHostMutex") -> bool:
        """确保全局仅运行一个 EXE 实例，防止热键冲突与重复悬浮窗"""
        cls._mutex_handle = kernel32.CreateMutexW(None, False, mutex_name)
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS

    @classmethod
    def release_single_instance(cls):
        """退出时释放互斥体句柄（进程结束系统亦会自动回收）"""
        if cls._mutex_handle:
            kernel32.CloseHandle(cls._mutex_handle)
            cls._mutex_handle = None

    @staticmethod
    def enable_anti_capture(hwnd: int, enable: bool = True) -> bool:
        """开启或关闭防投屏、防截图隔离。

        WDA_EXCLUDEFROMCAPTURE 需要 Windows 10 2004 及以上；旧系统上自动
        降级为 WDA_MONITOR（截图/投屏中呈现黑块，同样不泄露真实内容）。
        """
        if not enable:
            return bool(user32.SetWindowDisplayAffinity(wintypes.HWND(hwnd), WDA_NONE))
        if user32.SetWindowDisplayAffinity(wintypes.HWND(hwnd), WDA_EXCLUDEFROMCAPTURE):
            return True
        return bool(user32.SetWindowDisplayAffinity(wintypes.HWND(hwnd), WDA_MONITOR))

    @staticmethod
    def set_click_through(hwnd: int, penetrate: bool = True):
        """切换幽灵鼠标穿透态与位置调节锁定态"""
        style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        base_style = style | WS_EX_LAYERED | WS_EX_TOOLWINDOW
        if penetrate:
            new_style = base_style | WS_EX_TRANSPARENT
        else:
            new_style = base_style & ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, new_style)

    @staticmethod
    def get_idle_seconds() -> float:
        """获取系统距离上一次键鼠操作的闲置秒数"""
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = kernel32.GetTickCount() - lii.dwTime
            if millis < 0:  # GetTickCount 约 49.7 天回绕一次
                millis += 0x100000000
            return millis / 1000.0
        return 0.0

    @staticmethod
    def get_foreground_process_pid() -> int:
        """获取当前前台窗口所属进程 PID，无前台窗口时返回 0"""
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return 0
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    @staticmethod
    def get_cursor_pos():
        """获取当前光标屏幕坐标，失败返回 None"""
        point = POINT()
        if user32.GetCursorPos(ctypes.byref(point)):
            return point.x, point.y
        return None
