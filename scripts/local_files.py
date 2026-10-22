"""Local desktop folder selection and reveal, without shell commands."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import threading


class LocalFileError(ValueError):
    pass


def local_path(value):
    if not isinstance(value, (str, Path)) or not str(value) or '\x00' in str(value):
        raise LocalFileError('Выберите полный путь к папке')
    path = Path(value)
    if not path.is_absolute():
        raise LocalFileError('Требуется полный путь к папке на компьютере сервера')
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise LocalFileError('Пути через ссылки или перенаправления не поддерживаются')
    return path.resolve()


def _windows_choose(initial):
    import ctypes
    from ctypes import wintypes
    ole = ctypes.OleDLL('ole32')
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, ctypes.c_uint, wintypes.LPARAM, wintypes.LPARAM)
    class BrowseInfo(ctypes.Structure):
        _fields_ = [('hwndOwner', wintypes.HWND), ('pidlRoot', ctypes.c_void_p),
                    ('pszDisplayName', wintypes.LPWSTR), ('lpszTitle', wintypes.LPCWSTR),
                    ('ulFlags', ctypes.c_uint), ('lpfn', callback_type),
                    ('lParam', wintypes.LPARAM), ('iImage', ctypes.c_int)]
    shell.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BrowseInfo)]
    shell.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
    shell.SHGetPathFromIDListW.restype = wintypes.BOOL
    user = ctypes.WinDLL('user32')
    user.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    user.SendMessageW.restype = wintypes.LPARAM
    start = ctypes.create_unicode_buffer(initial or '')
    @callback_type
    def callback(hwnd, message, _param, _data):
        if message == 1 and initial:  # BFFM_INITIALIZED / BFFM_SETSELECTIONW
            user.SendMessageW(hwnd, 0x467, 1, ctypes.cast(start, ctypes.c_void_p).value)
        return 0
    result = ole.CoInitializeEx(None, 2)  # STA, on this request's own thread.
    if result < 0:
        raise LocalFileError('Не удалось открыть системный выбор папки')
    item = None
    try:
        display = ctypes.create_unicode_buffer(32768)
        info = BrowseInfo(None, None, ctypes.cast(display, wintypes.LPWSTR), 'Project Hub — выберите папку', 0x41, callback, 0, 0)
        item = shell.SHBrowseForFolderW(ctypes.byref(info))
        if not item:
            return None
        path = ctypes.create_unicode_buffer(32768)
        if not shell.SHGetPathFromIDListW(item, path):
            raise LocalFileError('Выберите локальную папку файловой системы')
        return path.value
    finally:
        if item:
            ole.CoTaskMemFree(item)
        ole.CoUninitialize()


def _run(argv):
    return subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)


def choose_folder(initial=None):
    if initial:
        initial = str(local_path(initial))
    if os.name == 'nt':
        path = _windows_choose(initial)
    elif sys.platform == 'darwin':
        script = 'on run argv\nset chosen to choose folder with prompt "Project Hub — choose folder"\nreturn POSIX path of chosen\nend run'
        result = _run(['/usr/bin/osascript', '-e', script])
        if result.returncode:
            if '(-128)' in result.stderr:
                return None
            raise LocalFileError('Не удалось открыть системный выбор папки')
        path = result.stdout.strip()
    else:
        if shutil.which('zenity'):
            argv = ['zenity', '--file-selection', '--directory', '--title=Project Hub']
            if initial:
                argv += ['--filename=' + initial.rstrip('/') + '/']
        elif shutil.which('kdialog'):
            argv = ['kdialog', '--getexistingdirectory', initial or str(Path.home()), '--title', 'Project Hub']
        else:
            raise LocalFileError('Системный выбор папки недоступен. Введите полный путь вручную')
        result = _run(argv)
        if result.returncode == 1:
            return None
        if result.returncode:
            raise LocalFileError('Не удалось открыть системный выбор папки')
        path = result.stdout.strip()
    if not path:
        return None
    selected = local_path(path)
    if not selected.is_dir():
        raise LocalFileError('Выбранная папка недоступна')
    return str(selected)


def open_folder(path, *, reveal=False):
    path = local_path(path)
    if not path.exists():
        raise LocalFileError('Папка или файл больше не существует')
    if not path.is_dir() and not reveal:
        raise LocalFileError('Файлы можно только показать в папке')
    if os.name == 'nt':
        if path.is_dir():
            os.startfile(str(path), 'explore')
        else:
            # /select is an Explorer argument, never a shell expression.
            subprocess.Popen(['explorer.exe', '/select,', str(path)], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    elif sys.platform == 'darwin':
        result = _run(['/usr/bin/open', *(['-R'] if reveal else []), str(path)])
        if result.returncode:
            raise LocalFileError('Не удалось открыть Finder')
    else:
        opener = shutil.which('xdg-open')
        if not opener:
            raise LocalFileError('Файловый менеджер недоступен')
        result = _run([opener, str(path.parent if path.is_file() else path)])
        if result.returncode:
            raise LocalFileError('Не удалось открыть файловый менеджер')
    return {'opened': True}


_chosen = set()
_chosen_lock = threading.Lock()


def remember_source(path):
    """Called after trusted folder/archive verification, not directly by HTTP."""
    checked = str(local_path(path))
    with _chosen_lock:
        _chosen.add(checked)


def execute(registry, body, *, application_home):
    if not isinstance(body, dict) or set(body) - {'action', 'kind', 'path', 'project', 'reveal'}:
        raise LocalFileError('Неизвестное действие с папкой')
    action, kind = body.get('action'), body.get('kind')
    if action == 'choose-folder' and kind in ('data', 'backups', 'import', 'workspace'):
        path = choose_folder(body.get('path'))
        if path:
            with _chosen_lock:
                _chosen.add(path)
                if len(_chosen) > 100:
                    _chosen.clear(); _chosen.add(path)
        return {'path': path, 'cancelled': path is None}
    if action != 'open-folder' or type(body.get('reveal', False)) is not bool:
        raise LocalFileError('Неизвестное действие с папкой')
    from storage_operations import backup_directory
    defaults = {'data': registry.home, 'backups': backup_directory(registry), 'program': Path(application_home)}
    if kind in defaults:
        root = local_path(defaults[kind])
        path = local_path(body.get('path') or root)
        if path != root and root not in path.parents:
            raise LocalFileError('Этот путь не относится к выбранной папке Hub')
    elif kind == 'workspace':
        project = next((item for item in registry.list(include_deleted=False)['projects'] if item['id'] == body.get('project')), None)
        if project is None:
            raise LocalFileError('Выберите зарегистрированный проект')
        roots = [local_path(root) for root in project.get('roots', [])]
        from project_workspaces import Workspaces
        roots += [local_path(item['descriptor']['root']) for item in Workspaces(registry).catalog(project['id'])['items']
                  if item['kind'] == 'local']
        path = local_path(body.get('path'))
        if not any(path == root or root in path.parents for root in roots):
            raise LocalFileError('Путь не входит в папки кода выбранного проекта')
    elif kind == 'import-source':
        path = local_path(body.get('path'))
        with _chosen_lock:
            registered = str(path) in _chosen
        if not registered and path == registry.home:
            registered = True
        if not registered:
            from backup_api import Backups
            from hub_import import copied_home
            import re
            backups = Backups(registry)
            for metadata in backups.home.glob('*.json'):
                if not re.fullmatch('[0-9a-f]{32}', metadata.stem):
                    continue
                row = backups._read(metadata.stem)
                if row.get('sourcePath') and path == local_path(row['sourcePath']):
                    registered = True
                elif row.get('restore', {}).get('path') == str(path):
                    copied_home(backups, row['id'])
                    registered = True
        if not registered:
            raise LocalFileError('Сначала выберите или проверьте эту папку для импорта')
    else:
        raise LocalFileError('Неизвестный тип папки')
    return open_folder(path, reveal=body.get('reveal', False))
