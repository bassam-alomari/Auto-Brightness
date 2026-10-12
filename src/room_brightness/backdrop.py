"""Windows compositor blur with transparent tint; no desktop capture."""

import ctypes as ct
import os


class Margins(ct.Structure):
    _fields_ = [("left", ct.c_int), ("right", ct.c_int), ("top", ct.c_int), ("bottom", ct.c_int)]


def apply_backdrop(hwnd, enabled):
    if os.name != "nt":
        return False
    try:
        dwm = ct.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = [ct.c_void_p, ct.c_uint32, ct.c_void_p, ct.c_uint32]
        dwm.DwmSetWindowAttribute.restype = ct.c_long
        dwm.DwmExtendFrameIntoClientArea.argtypes = [ct.c_void_p, ct.POINTER(Margins)]
        dwm.DwmExtendFrameIntoClientArea.restype = ct.c_long
        backdrop = ct.c_int(1)
        result = dwm.DwmSetWindowAttribute(ct.c_void_p(hwnd), 38, ct.byref(backdrop), 4)
        margins = Margins(0, 0, 0, 0)
        extended = dwm.DwmExtendFrameIntoClientArea(ct.c_void_p(hwnd), ct.byref(margins))
        corners = ct.c_int(2 if enabled else 1)  # Clip native glass corners as well as Qt.
        dwm.DwmSetWindowAttribute(ct.c_void_p(hwnd), 33, ct.byref(corners), 4)
        border = ct.c_uint32(0xFFFFFFFE)  # DWMWA_COLOR_NONE
        dwm.DwmSetWindowAttribute(ct.c_void_p(hwnd), 34, ct.byref(border), 4)

        # Desktop Acrylic can supply an opaque system tint on layered Qt windows.
        # Request blur behind the transparent client without that system material.
        class Accent(ct.Structure):
            _fields_ = [
                ("state", ct.c_int),
                ("flags", ct.c_int),
                ("color", ct.c_uint32),
                ("animation", ct.c_int),
            ]

        class CompositionData(ct.Structure):
            _fields_ = [("attribute", ct.c_int), ("data", ct.c_void_p), ("size", ct.c_size_t)]

        user = ct.WinDLL("user32", use_last_error=True)
        setter = user.SetWindowCompositionAttribute
        setter.argtypes = [ct.c_void_p, ct.POINTER(CompositionData)]
        setter.restype = ct.c_int
        # Acrylic adds a stronger frosted compositor blur with a low-opacity tint.
        accent = Accent(4 if enabled else 0, 2 if enabled else 0, 0x181E140A if enabled else 0, 0)
        data = CompositionData(19, ct.cast(ct.pointer(accent), ct.c_void_p), ct.sizeof(accent))
        return bool(setter(ct.c_void_p(hwnd), ct.byref(data))) and result == 0 and extended == 0
    except (AttributeError, OSError):
        return False
