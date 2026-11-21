"""Windows memory counters for optional diagnostic markers; stdlib only.

Definitions: learn.microsoft.com/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex
and learn.microsoft.com/windows/win32/api/sysinfoapi/ns-sysinfoapi-memorystatusex
"""
import os
_reader=None

def snapshot():
    global _reader
    if os.name!='nt':return {'error':'Windows stage counters unavailable'}
    if _reader is None:
        import ctypes as c
        from ctypes import wintypes as w
        class Memory(c.Structure):
            _fields_=[('length',w.DWORD),('load',w.DWORD)]+[(n,c.c_ulonglong) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        class Process(c.Structure):
            _fields_=[('cb',w.DWORD),('faults',w.DWORD)]+[(n,c.c_size_t) for n in ('peak_rss','rss','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
        kernel=c.WinDLL('kernel32',use_last_error=True);psapi=c.WinDLL('psapi',use_last_error=True)
        kernel.GetCurrentProcess.restype=w.HANDLE
        kernel.GlobalMemoryStatusEx.argtypes=[c.POINTER(Memory)];kernel.GlobalMemoryStatusEx.restype=w.BOOL
        psapi.GetProcessMemoryInfo.argtypes=[w.HANDLE,c.POINTER(Process),w.DWORD];psapi.GetProcessMemoryInfo.restype=w.BOOL
        def read():
            memory=Memory();memory.length=c.sizeof(memory);process=Process();process.cb=c.sizeof(process)
            if not kernel.GlobalMemoryStatusEx(c.byref(memory)) or not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),c.byref(process),process.cb):
                return {'error':'Windows memory counter read failed','code':c.get_last_error()}
            return dict(available=memory.available,total=memory.total,rss=process.rss,private=process.private,native_peak_rss=process.peak_rss)
        _reader=read
    return _reader()
