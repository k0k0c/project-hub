"""Launch an ordinary application through the interactive Explorer desktop.

Uses Microsoft's Execute in Explorer pattern, without services, tasks, elevation,
parent-process spoofing or changes to Windows jobs. Called only for an explicitly
selected source runtime. Restricted/unknown caller tokens are never delegated.
"""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid


class DesktopLaunchError(OSError):
    pass


def physical_directory(path):
    """Name an existing shared temporary directory outside an MSIX overlay."""
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.CreateFileW(str(path), 0, 7, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise DesktopLaunchError('The source launch response directory could not be opened.')
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        count = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not 0 < count < len(buffer):
            raise DesktopLaunchError('The source launch response directory could not be resolved.')
        return Path(buffer.value)
    finally:
        kernel.CloseHandle(handle)


def run_controller(arguments, instance_home, *, timeout=660):
    """All source start/stop metadata must use Explorer's single AppData view."""
    from runtime_diagnostics import process_context
    if os.name != 'nt' or process_context().get('restrictedToken') is not False:
        raise DesktopLaunchError('Independent source launch requires an unrestricted Windows desktop.')
    with tempfile.TemporaryDirectory(prefix='hub-source-control-') as temporary:
        receipt = physical_directory(temporary) / 'result.json'
        executable = Path(sys.executable).with_name('pythonw.exe')
        if not executable.is_file():
            raise DesktopLaunchError('Independent source launch requires pythonw.exe.')
        launch([str(executable), '-B', str(Path(__file__).with_name('hub_launcher.py')),
            *arguments, '--desktop-entry', str(receipt), '--instance-home', str(instance_home)], Path(__file__).resolve().parent)
        deadline = time.monotonic() + timeout
        startup_deadline = time.monotonic() + min(timeout, 15)
        controller_pid = None
        dead_since = None
        while time.monotonic() < deadline:
            try:
                from hub_launcher import read_json
                row = read_json(receipt)
            except FileNotFoundError:
                if controller_pid is None:
                    try:
                        started = read_json(receipt.with_name('started.json'))
                    except FileNotFoundError:
                        if time.monotonic() >= startup_deadline:
                            raise DesktopLaunchError('The Windows source controller did not start. No completion response was received.')
                    else:
                        if not isinstance(started, dict) or type(started.get('pid')) is not int or started['pid'] <= 0:
                            raise DesktopLaunchError('Invalid source controller startup response.')
                        controller_pid = started['pid']
                if controller_pid is not None:
                    from runtime_diagnostics import _process_alive
                    if _process_alive(controller_pid) is False:
                        if dead_since is None:
                            dead_since = time.monotonic()
                        elif time.monotonic() - dead_since >= .5:
                            raise DesktopLaunchError('The Windows source controller exited before completing the operation. See Hub launcher diagnostics.')
                time.sleep(.1)
                continue
            if not isinstance(row, dict) or type(row.get('exitCode')) is not int or row['exitCode'] not in (0, 1) or \
                    (row.get('url') is not None and not isinstance(row['url'], str)):
                raise DesktopLaunchError('Invalid source launch completion response.')
            return row
        raise DesktopLaunchError('The source launch did not finish in time. The runtime was not forcibly stopped; inspect Hub diagnostics.')


def launch(command, directory, *, timeout=15):
    from runtime_diagnostics import process_context
    if os.name != 'nt' or process_context().get('restrictedToken') is not False:
        raise DesktopLaunchError('Independent source launch requires an unrestricted Windows desktop. Start Hub from the desktop shortcut.')
    helper = Path(__file__).resolve()
    # A source shortcut may itself use pythonw, whose standard streams are None.
    # The private helper needs real pipes; CREATE_NO_WINDOW keeps it invisible.
    interpreter = Path(sys.executable)
    if interpreter.name.lower() == 'pythonw.exe':
        interpreter = interpreter.with_name('python.exe')
    # COM RPC is isolated in a short-lived helper, so an unresponsive Explorer
    # cannot leave the calling launcher waiting indefinitely.
    try:
        result = subprocess.run([str(interpreter), '-B', str(helper), str(directory), *command],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as error:
        raise DesktopLaunchError('The Windows desktop did not respond to the source launch request.') from error
    if result.returncode:
        from runtime_diagnostics import record
        record('launcher.desktop_failed', exitCode=result.returncode,
               detail=result.stderr.decode('utf-8', errors='replace')[-1000:])
        raise DesktopLaunchError('The Windows desktop could not start Hub. Start it from the desktop shortcut; see launcher diagnostics.')
    try:
        result = json.loads(result.stdout)
        if type(result['desktopPid']) is not int or result['desktopPid'] <= 0:
            raise ValueError('Invalid desktop identity')
        return result
    except (ValueError, KeyError, TypeError) as error:
        raise DesktopLaunchError('The Windows desktop did not confirm the source launch identity.') from error


def desktop_identity():
    """Require the same Windows user and interactive desktop before delegation."""
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user = ctypes.WinDLL('user32', use_last_error=True)
    security = ctypes.WinDLL('advapi32', use_last_error=True)
    user.GetShellWindow.restype = w.HWND
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    security.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    security.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    security.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    pid = w.DWORD()
    window = user.GetShellWindow()
    if not window or not user.GetWindowThreadProcessId(window, ctypes.byref(pid)):
        raise DesktopLaunchError('The interactive Windows desktop is unavailable.')
    process = kernel.OpenProcess(0x1000, False, pid.value)
    if not process:
        raise DesktopLaunchError('The Windows desktop identity is inaccessible.')
    tokens = []
    try:
        identities = []
        for handle in (kernel.GetCurrentProcess(), process):
            token = w.HANDLE()
            if not security.OpenProcessToken(handle, 8, ctypes.byref(token)):
                raise DesktopLaunchError('The Windows desktop user could not be verified.')
            tokens.append(token)
            size = w.DWORD()
            security.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # TokenUser
            if not 0 < size.value <= 65536:
                raise DesktopLaunchError('The Windows desktop user identity is invalid.')
            buffer = ctypes.create_string_buffer(size.value)
            if not security.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
                raise DesktopLaunchError('The Windows desktop user could not be read.')
            identities.append(buffer)
        if not security.EqualSid(ctypes.c_void_p.from_buffer(identities[0]), ctypes.c_void_p.from_buffer(identities[1])):
            raise DesktopLaunchError('Hub and the Windows desktop must belong to the same user.')
    finally:
        for token in tokens:
            kernel.CloseHandle(token)
        kernel.CloseHandle(process)
    return {'desktopPid': pid.value}


def _execute(command, directory):
    """Get the desktop's automation object, not an in-process Shell.Application."""
    from ctypes import wintypes as w
    from runtime_diagnostics import process_context
    if process_context().get('restrictedToken') is not False:
        raise DesktopLaunchError('Restricted desktop delegation is not supported.')
    identity = desktop_identity()

    class Guid(ctypes.Structure):
        _fields_ = [('bytes', ctypes.c_ubyte * 16)]
        def __init__(self, value):
            super().__init__(); self.bytes[:] = uuid.UUID(value).bytes_le

    class Union(ctypes.Union):
        _fields_ = [('number', w.LONG), ('pointer', ctypes.c_void_p),
                    ('record', ctypes.c_void_p * 2)]

    class Variant(ctypes.Structure):
        _anonymous_ = ('value',)
        _fields_ = [('vt', w.WORD), ('reserved', w.WORD * 3), ('value', Union)]

    class Params(ctypes.Structure):
        _fields_ = [('args', ctypes.POINTER(Variant)), ('named', ctypes.c_void_p),
                    ('count', w.UINT), ('namedCount', w.UINT)]

    ole = ctypes.OleDLL('ole32'); automation = ctypes.WinDLL('oleaut32')
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, w.DWORD]
    ole.CoUninitialize.argtypes = []
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(Guid), ctypes.c_void_p, w.DWORD,
                                    ctypes.POINTER(Guid), ctypes.POINTER(ctypes.c_void_p)]
    automation.SysAllocString.argtypes = [w.LPCWSTR]
    automation.SysAllocString.restype = ctypes.c_void_p
    automation.VariantClear.argtypes = [ctypes.POINTER(Variant)]
    iid_dispatch = Guid('00020400-0000-0000-c000-000000000046')
    empty_iid = Guid('00000000-0000-0000-0000-000000000000')
    owned = []; variants = []

    def method(pointer, index, *types):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(w.HRESULT if hasattr(w, 'HRESULT') else ctypes.c_long,
                                 ctypes.c_void_p, *types)(table[index])

    def check(code):
        if code < 0:
            raise DesktopLaunchError(f'Windows desktop COM failed (0x{code & 0xffffffff:08x}).')

    def output(pointer):
        owned.append(pointer); return pointer

    def query(pointer, iid):
        result = ctypes.c_void_p()
        check(method(pointer, 0, ctypes.POINTER(Guid), ctypes.POINTER(ctypes.c_void_p))(
            pointer, ctypes.byref(iid), ctypes.byref(result)))
        return output(result)

    def value(item=None, *, byref=False):
        result = Variant()
        if byref:
            result.vt = 0x400c; result.pointer = ctypes.addressof(item)  # VT_VARIANT | VT_BYREF
        elif isinstance(item, int):
            result.vt = 3; result.number = item
        elif isinstance(item, str):
            result.vt = 8; result.pointer = automation.SysAllocString(item)
            if not result.pointer:
                raise MemoryError('Unable to allocate desktop launch argument.')
        variants.append(result)
        return result

    def invoke(pointer, name, args=(), flags=1):
        dispatch_id = w.LONG(); names = (w.LPCWSTR * 1)(name)
        check(method(pointer, 5, ctypes.POINTER(Guid), ctypes.POINTER(w.LPCWSTR), w.UINT,
                     w.DWORD, ctypes.POINTER(w.LONG))(
            pointer, ctypes.byref(empty_iid), names, 1, 0, ctypes.byref(dispatch_id)))
        reverse = (Variant * len(args))(*reversed(args))
        params = Params(reverse, None, len(args), 0); result = Variant(); variants.append(result)
        check(method(pointer, 6, w.LONG, ctypes.POINTER(Guid), w.DWORD, w.WORD,
                     ctypes.POINTER(Params), ctypes.POINTER(Variant), ctypes.c_void_p, ctypes.c_void_p)(
            pointer, dispatch_id, ctypes.byref(empty_iid), 0, flags,
            ctypes.byref(params), ctypes.byref(result), None, None))
        return result

    ole.CoInitializeEx(None, 2)  # STA; this helper has no other COM users.
    try:
        windows = ctypes.c_void_p()
        ole.CoCreateInstance(ctypes.byref(Guid('9ba05972-f6a8-11cf-a442-00a0c90a8f39')),
            None, 4, ctypes.byref(iid_dispatch), ctypes.byref(windows))
        output(windows)
        location = value(0); empty = value(); hwnd = w.LONG()
        window_arg = value(); window_arg.vt = 0x4003; window_arg.pointer = ctypes.addressof(hwnd)
        desktop = invoke(windows, 'FindWindowSW', [value(location, byref=True),
            value(empty, byref=True), value(8), window_arg, value(1)])
        if desktop.vt != 9 or not desktop.pointer:
            raise DesktopLaunchError('The interactive Explorer desktop is unavailable.')
        provider = query(desktop.pointer, Guid('6d5140c1-7436-11ce-8034-00aa006009fa'))
        browser = ctypes.c_void_p()
        check(method(provider, 3, ctypes.POINTER(Guid), ctypes.POINTER(Guid), ctypes.POINTER(ctypes.c_void_p))(
            provider, ctypes.byref(Guid('4c96be40-915c-11cf-99d3-00aa004ae837')),
            ctypes.byref(Guid('000214e2-0000-0000-c000-000000000046')), ctypes.byref(browser)))
        output(browser)
        view = ctypes.c_void_p()
        check(method(browser, 15, ctypes.POINTER(ctypes.c_void_p))(browser, ctypes.byref(view)))
        output(view)
        folder = ctypes.c_void_p()
        check(method(view, 15, w.UINT, ctypes.POINTER(Guid), ctypes.POINTER(ctypes.c_void_p))(
            view, 0, ctypes.byref(iid_dispatch), ctypes.byref(folder)))
        output(folder)
        shell = invoke(folder, 'Application', flags=2)
        if shell.vt != 9 or not shell.pointer:
            raise DesktopLaunchError('The Explorer application interface is unavailable.')
        invoke(shell.pointer, 'ShellExecute', [value(command[0]), value(subprocess.list2cmdline(command[1:])),
            value(str(directory)), value('open'), value(0)])
        return identity
    finally:
        for item in reversed(variants):
            automation.VariantClear(ctypes.byref(item))
        for pointer in reversed(owned):
            method(pointer, 2)(pointer)
        ole.CoUninitialize()


if __name__ == '__main__':
    try:
        print(json.dumps(_execute(sys.argv[2:], sys.argv[1])))
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
