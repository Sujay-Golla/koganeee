"""DPI-aware OpenCV presentation and fixed-size recording, independent of sensors."""
from __future__ import annotations

import sys


def enable_dpi_awareness():
    """Call before window creation so Windows does not bitmap-scale the whole app."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def size_from_width(width):
    if not isinstance(width, int) or not 640 <= width <= 3840 or width % 16:
        raise ValueError("Dashboard/record width must be a multiple of 16 from 640 to 3840.")
    return width, width*9//16


def render_size(window=None, *, forced_width=0, record_size=None):
    """Fit 16:9 to the image area, keeping recording pixels when it is larger."""
    import cv2
    size = size_from_width(forced_width) if forced_width else (1280, 720)
    if window and not forced_width:
        try:
            _, _, w, h = cv2.getWindowImageRect(window)
            if w > 0 and h > 0:
                width = max(640, min(3840, int(min(w, h*16/9))//16*16))
                size = size_from_width(width)
        except cv2.error:
            pass  # Some HighGUI backends do not expose the image rectangle.
    if record_size and record_size[0] > size[0]:
        size = record_size
    return size


def recording_frame(image, size):
    import cv2
    if image.shape[1::-1] == size:
        return image
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)
