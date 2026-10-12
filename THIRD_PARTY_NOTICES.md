# Third-party notices

The original Auto Brightness source is MIT licensed. Dependency code is not included in the source ZIP. The standalone portable app and installer bundle the Python runtime and dependencies; their notices are preserved in the licenses directory. Libraries remain separate and replaceable. Source installations fetch dependencies from their publishers. Each dependency retains its own license:

- PySide6 Essentials and Shiboken6: Qt for Python, LGPL v3/GPL/commercial licensing. See [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html), [Qt source](https://code.qt.io/cgit/pyside/pyside-setup.git/) and the license files shipped in the installed packages. A distributed binary must preserve applicable notices and permit replacing/relinking LGPL libraries.
- OpenCV: Apache 2.0; opencv-python packaging includes additional third-party notices in its wheel.
- NumPy: BSD licensing and bundled notices.
- Pillow: HPND and bundled third-party notices.
- pystray: LGPL v3. The legacy Tk interface uses it; the Qt interface uses Qt's tray implementation.
- six: MIT.
- Python and Tcl/Tk: their respective licenses.
- PyInstaller: GPL v2 or later with its bootloader exception, permitting distribution of bundled applications under their own licenses.

The source project's MIT license does not override any dependency license. No Apple code, trademarks, images or proprietary rendering engine are bundled. The glass artwork is drawn by the project's own code.
