"""Enumerate DirectShow friendly names without opening a capture stream.

Uses the same device category/order as OpenCV CAP_DSHOW, with stable DevicePath
identities to detect device reordering. Native COM work lives in a child process.
"""

import ctypes as ct
import json
import os
import subprocess
import sys
import uuid


class GUID(ct.Structure):
    _fields_ = [
        ("data1", ct.c_uint32),
        ("data2", ct.c_uint16),
        ("data3", ct.c_uint16),
        ("data4", ct.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class VariantValue(ct.Union):
    _fields_ = [
        ("pointer", ct.c_void_p),
        ("padding", ct.c_uint64 * (2 if ct.sizeof(ct.c_void_p) == 8 else 1)),
    ]


class Variant(ct.Structure):
    _fields_ = [("type", ct.c_uint16), ("reserved", ct.c_uint16 * 3), ("value", VariantValue)]


def native_devices():
    if os.name != "nt":
        raise RuntimeError("Camera discovery requires Windows.")
    ole = ct.OleDLL("ole32")
    automation = ct.OleDLL("oleaut32")
    ole.CoInitializeEx.argtypes = [ct.c_void_p, ct.c_uint32]
    ole.CoInitializeEx.restype = ct.c_long
    ole.CoCreateInstance.argtypes = [
        ct.POINTER(GUID),
        ct.c_void_p,
        ct.c_uint32,
        ct.POINTER(GUID),
        ct.POINTER(ct.c_void_p),
    ]
    ole.CoCreateInstance.restype = ct.c_long
    automation.VariantClear.argtypes = [ct.POINTER(Variant)]
    ole.CoTaskMemFree.argtypes = [ct.c_void_p]
    ole.CoTaskMemFree.restype = None
    ole.CoInitializeEx(None, 2)

    def call(pointer, slot, arguments, *values):
        table = ct.cast(pointer, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
        method = ct.WINFUNCTYPE(ct.c_long, ct.c_void_p, *arguments)(table[slot])
        return method(pointer, *values)

    def release(pointer):
        if pointer:
            call(pointer, 2, [])

    def read(bag, key):
        variant = Variant()
        try:
            result = call(
                bag,
                3,
                [ct.c_wchar_p, ct.POINTER(Variant), ct.c_void_p],
                key,
                ct.byref(variant),
                None,
            )
            if result == 0 and variant.type == 8 and variant.value.pointer:
                return ct.wstring_at(variant.value.pointer)
            return ""
        finally:
            automation.VariantClear(ct.byref(variant))

    creator = ct.c_void_p()
    enumerator = ct.c_void_p()
    devices = []
    try:
        clsid = GUID.parse("62be5d10-60eb-11d0-bd3b-00a0c911ce86")
        iid = GUID.parse("29840822-5b84-11d0-bd3b-00a0c911ce86")
        category = GUID.parse("860bb310-5d01-11d0-bd3b-00a0c911ce86")
        property_bag = GUID.parse("55272a00-42cb-11ce-8135-00aa004bb851")
        ole.CoCreateInstance(ct.byref(clsid), None, 1, ct.byref(iid), ct.byref(creator))
        result = call(
            creator,
            3,
            [ct.POINTER(GUID), ct.POINTER(ct.c_void_p), ct.c_uint32],
            ct.byref(category),
            ct.byref(enumerator),
            0,
        )
        if result == 1:
            return []
        if result != 0:
            raise RuntimeError("Camera enumeration failed.")
        index = 0
        while True:
            moniker = ct.c_void_p()
            fetched = ct.c_ulong()
            result = call(
                enumerator,
                3,
                [ct.c_ulong, ct.POINTER(ct.c_void_p), ct.POINTER(ct.c_ulong)],
                1,
                ct.byref(moniker),
                ct.byref(fetched),
            )
            if result == 1:
                break
            if result != 0:
                raise RuntimeError("Camera enumeration failed.")
            bag = ct.c_void_p()
            try:
                result = call(
                    moniker,
                    9,
                    [ct.c_void_p, ct.c_void_p, ct.POINTER(GUID), ct.POINTER(ct.c_void_p)],
                    None,
                    None,
                    ct.byref(property_bag),
                    ct.byref(bag),
                )
                if result != 0:
                    raise RuntimeError("Could not read camera information.")
                name = read(bag, "FriendlyName") or read(bag, "Description")
                identity = read(bag, "DevicePath")
                if not identity:
                    display_name = ct.c_void_p()
                    try:
                        result = call(
                            moniker,
                            20,
                            [ct.c_void_p, ct.c_void_p, ct.POINTER(ct.c_void_p)],
                            None,
                            None,
                            ct.byref(display_name),
                        )
                        if result != 0 or not display_name:
                            raise RuntimeError("Could not identify this camera safely.")
                        identity = ct.wstring_at(display_name)
                    finally:
                        if display_name:
                            ole.CoTaskMemFree(display_name)
                devices.append(dict(index=index, name=name or f"Camera {index + 1}", id=identity))
            finally:
                release(bag)
                release(moniker)
            index += 1
        return devices
    finally:
        release(enumerator)
        release(creator)
        ole.CoUninitialize()


def list_devices():
    result = subprocess.run(
        [sys.executable]
        + ([] if getattr(sys, "frozen", False) else ["-m", "room_brightness"])
        + ["--list-cameras"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=12,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Camera discovery failed.")
    data = json.loads(result.stdout)
    if not isinstance(data, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get("index"), int)
        and item["index"] >= 0
        and isinstance(item.get("name"), str)
        and isinstance(item.get("id"), str)
        for item in data
    ):
        raise RuntimeError("Invalid camera list.")
    return data
