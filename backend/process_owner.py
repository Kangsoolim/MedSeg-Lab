"""Windows kernel ownership: abrupt service death also stops its workers.

API/layout reference: Microsoft Learn Job Objects and
JOBOBJECT_EXTENDED_LIMIT_INFORMATION. No new native dependency is required.
"""
import sys

class WorkerOwner:
    def __init__(self):
        self.handle=None
        if sys.platform!='win32':return
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_=[('process_time',c.c_longlong),('job_time',c.c_longlong),('flags',w.DWORD),
                      ('min_working',c.c_size_t),('max_working',c.c_size_t),('active',w.DWORD),
                      ('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class IO(c.Structure):
            _fields_=[(name,c.c_ulonglong) for name in ['reads','writes','other','read_bytes','write_bytes','other_bytes']]
        class Extended(c.Structure):
            _fields_=[('basic',Basic),('io',IO),('process_memory',c.c_size_t),('job_memory',c.c_size_t),
                      ('peak_process',c.c_size_t),('peak_job',c.c_size_t)]
        self.api=c.WinDLL('kernel32',use_last_error=True)
        self.api.CreateJobObjectW.argtypes=[c.c_void_p,w.LPCWSTR];self.api.CreateJobObjectW.restype=w.HANDLE
        self.api.SetInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD];self.api.SetInformationJobObject.restype=w.BOOL
        self.api.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];self.api.AssignProcessToJobObject.restype=w.BOOL
        self.api.CloseHandle.argtypes=[w.HANDLE];self.api.CloseHandle.restype=w.BOOL
        self.handle=self.api.CreateJobObjectW(None,None)
        if not self.handle:raise c.WinError(c.get_last_error())
        info=Extended();info.basic.flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle,9,c.byref(info),c.sizeof(info)):
            error=c.WinError(c.get_last_error());self.close();raise error

    def assign(self,process):
        if self.handle:
            import ctypes as c
            if not self.api.AssignProcessToJobObject(self.handle,int(process._handle)):
                raise c.WinError(c.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle);self.handle=None
