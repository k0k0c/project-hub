"""Inventory and editor for one owned native Codex user skill. No model delivery."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

PACKAGE = Path(__file__).resolve().parents[1]
NAME = 'project-hub-user'
KIND = 'project-hub-user-skill-v1'
MAX_BODY = 24000
MAX_FILE = 128000
HEADER = ('---\nname: project-hub-user\ndescription: User preferences for task bookkeeping, '
          'coordination and results when working with the Project Hub plugin.\n---\n\n')


class InstructionsError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.status = status
        self.body = {'error': code, 'message': message}


def default_body():
    return (PACKAGE / 'assets/default-user-instructions.md').read_text(encoding='utf-8')


def digest(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()


def _atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _lock(home):
    # A file lock serializes independent installer/editor processes, not agent work.
    home.mkdir(parents=True, exist_ok=True)
    with (home / 'edit.lock').open('a+b') as output:
        if output.tell() == 0:
            output.write(b'0')
            output.flush()
        deadline = time.monotonic() + 5
        while True:
            try:
                output.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(output.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(output, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise InstructionsError('instructions_busy', 'Instruction editor is busy', 409)
                time.sleep(.02)
        try:
            yield
        finally:
            output.seek(0)
            if os.name == 'nt':
                msvcrt.locking(output.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(output, fcntl.LOCK_UN)


def _json(path, missing=None):
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return missing
    if len(raw) > MAX_FILE:
        raise InstructionsError('invalid_instructions', 'Instructions metadata exceeds size limit', 500)
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise InstructionsError('invalid_instructions', 'Invalid instruction metadata', 500) from error


class Instructions:
    def __init__(self, data_home):
        self.home = Path(data_home).resolve() / 'instructions'
        self.config = self.home / 'location.json'

    def location(self):
        config = _json(self.config, {})
        if not isinstance(config, dict) or (config and config.get('kind') != KIND):
            raise InstructionsError('invalid_instructions', 'Unknown instruction location configuration', 500)
        # Unconfigured development/test servers never inspect the real user profile.
        root = Path(config.get('root', str(self.home / NAME))).absolute()
        if root.name != NAME or root.resolve() != root:
            raise InstructionsError('invalid_instructions', 'Only the owned instruction skill directory is supported', 500)
        return root

    def _owned(self, root, create=False):
        marker = root / '.project-hub-owned.json'
        if root.resolve() != root or marker.is_symlink() or (root / 'SKILL.md').is_symlink():
            raise InstructionsError('instruction_ownership', 'Instruction paths must belong to the owned skill', 409)
        value = _json(marker)
        if value is None:
            if root.exists() and any(root.iterdir()):
                raise InstructionsError('instruction_ownership', 'Refusing to adopt an existing unowned skill directory', 409)
            if create:
                _atomic(marker, json.dumps({'kind': KIND, 'defaultDigest': digest(default_body())}).encode())
        elif not isinstance(value, dict) or value.get('kind') != KIND:
            raise InstructionsError('instruction_ownership', 'Skill belongs to another owner', 409)
        return value

    def initialize(self, root=None, package_root=None):
        """Installer/plugin-owned opt-in initialization; ordinary portal GET never writes."""
        with _lock(self.home):
            existing = _json(self.config)
            selected = Path(root).absolute() if root is not None else self.location()
            if selected.name != NAME or selected.resolve() != selected:
                raise InstructionsError('invalid_instructions', 'Use a separate project-hub-user skill directory')
            if existing and self.location() != selected:
                raise InstructionsError('instruction_ownership', 'Existing skill location is preserved; migrate explicitly', 409)
            self._owned(selected, create=True)
            path = selected / 'SKILL.md'
            if not path.exists():
                _atomic(path, (HEADER + default_body()).encode('utf-8'))
            if not existing:
                config = {'kind': KIND, 'root': str(selected)}
                if package_root is not None:
                    config['packageRoot'] = str(Path(package_root).absolute())
                _atomic(self.config, json.dumps(config).encode())
        return self.read()

    def read(self):
        root = self.location()
        marker = self._owned(root)
        path = root / 'SKILL.md'
        try:
            with path.open('rb') as source:
                raw = source.read(MAX_FILE + 1)
        except FileNotFoundError:
            raw = None
        if raw is not None:
            if marker is None or len(raw) > MAX_FILE:
                raise InstructionsError('invalid_instructions', 'Invalid owned skill file', 500)
            try:
                text = raw.decode('utf-8-sig').replace('\r\n','\n')
            except UnicodeError as error:
                raise InstructionsError('invalid_instructions', 'Skill must be UTF-8', 500) from error
            if not text.startswith(HEADER):
                raise InstructionsError('invalid_instructions', 'Restore the owned skill metadata before editing', 409)
            body = text[len(HEADER):]
            if len(body) > MAX_BODY:
                raise InstructionsError('invalid_instructions', 'Skill body exceeds size limit', 500)
        else:
            body = default_body()
        history = _json(self.home / 'history.json', [])
        if not isinstance(history, list) or len(history) > 20:
            raise InstructionsError('invalid_instructions', 'Invalid instruction history', 500)
        return dict(revision=digest(raw) if raw is not None else 'missing-v1', initialized=raw is not None,
                    body=body, path=str(path), history=history,
                    restoreAllowed=self.config.is_file(),
                    defaultChanged=bool(marker and marker.get('defaultDigest') != digest(default_body())),
                    nativeDiscovery=root.parent.name == 'skills' and root.parent.parent.name == '.agents')

    def update(self, expected, patch=None, reset=None, actor='local-user'):
        if not self.config.is_file():
            raise InstructionsError('instructions_unconfigured', 'Initialize the user skill through the installer before editing', 409)
        if (patch is None) == (reset is None):
            raise InstructionsError('invalid_instructions', 'Use patch OR reset')
        if reset is not None and reset not in ('userInstructions', 'all'):
            raise InstructionsError('invalid_instructions', 'Unknown instruction block')
        if patch is not None and (not isinstance(patch, dict) or set(patch) != {'userInstructions'}):
            raise InstructionsError('invalid_instructions', 'Only userInstructions is editable')
        body = default_body() if reset is not None else patch['userInstructions']
        if not isinstance(body, str) or not body.strip() or len(body) > MAX_BODY or '\x00' in body:
            raise InstructionsError('invalid_instructions', 'Instruction body must contain 1–24000 text characters')
        with _lock(self.home):
            current = self.read()
            if expected != current['revision']:
                raise InstructionsError('instructions_conflict', 'Instructions changed; reload before saving', 409)
            root = self.location()
            self._owned(root, create=reset is not None)
            if not current['initialized'] and reset is None:
                raise InstructionsError('instructions_uninitialized', 'Initialize the owned skill before editing', 409)
            payload = (HEADER + body).encode('utf-8')
            if current['initialized'] and body == current['body']:
                return current
            entry = dict(at=datetime.now(timezone.utc).isoformat(), actor=actor,
                         blocks=['userInstructions'], before=current['revision'], after=digest(payload))
            # History precedes the atomic file replacement; it records requested edits,
            # and exact file digest remains the concurrency authority after a crash.
            _atomic(self.home / 'history.json', json.dumps((current['history'] + [entry])[-20:]).encode())
            _atomic(root / 'SKILL.md', payload)
            if reset is not None:
                _atomic(root / '.project-hub-owned.json', json.dumps({'kind': KIND, 'defaultDigest': digest(default_body())}).encode())
        return self.read()


def catalog(data_home):
    instructions = Instructions(data_home)
    state = instructions.read()
    location = _json(instructions.config, {})
    package = Path(location.get('packageRoot', str(PACKAGE)))
    user_root=Path.home()/'.agents/skills'/NAME
    scope=('codex-user' if Path(state['path']).parent==user_root.absolute() else
           'native-local' if state['nativeDiscovery'] else 'unconfigured')
    if not (package / 'plugin.json').is_file():
        raise InstructionsError('package_unavailable', 'Repair the missing Project Hub package before restoring hooks', 409)
    from hub_plugin import TOOLS
    manifest = _json(package / 'plugin.json', {})
    core = package / 'skills/project-hub/SKILL.md'
    hooks = _json(package / 'hooks/hooks.json', {}).get('hooks', {})
    descriptions = {
        'SessionStart': 'При начале сессии проверяет, есть ли работа в Hub, и напоминает зарегистрировать её.',
        'UserPromptSubmit': 'Отмечает новый пользовательский запрос и проверяет состояние работы; сам задачи не создаёт и не закрывает.',
        'PreToolUse': 'Перед явным редактированием предупреждает, если работа ещё не зарегистрирована в Hub.',
        'Stop': 'Отмечает остановку текущего хода; это не означает завершение задачи.',
        'Interrupt': 'Отмечает, что текущий ход был прерван.',
        'SessionEnd': 'Отмечает окончание сессии; незавершённая работа остаётся открытой для продолжения.',
    }
    hook_rows = []
    recovery = {}
    import shlex
    import sys
    import subprocess
    entry = str(package / 'scripts/client_entry.py')
    windows = "& '" + sys.executable.replace("'", "''") + "' '" + entry.replace("'", "''") + "' hook"
    for event, groups in hooks.items():
        for group in groups:
            for handler in group.get('hooks', []):
                # Recovery outside the plugin uses actual paths, not PLUGIN_ROOT.
                import shlex
                import sys
                import subprocess
                entry = str(package / 'scripts/client_entry.py')
                argv = [sys.executable, entry, 'hook']
                command = subprocess.list2cmdline(argv) if os.name == 'nt' else shlex.join(argv)
                windows = "& '" + sys.executable.replace("'", "''") + "' '" + entry.replace("'", "''") + "' hook"
                hook_rows.append(dict(event=event, description=descriptions.get(event, event),
                    requiredFor='Только для наблюдений и напоминаний; инструменты MCP и инструкции работают и без этого обработчика',
                    command=command, commandWindows=windows, timeout=handler.get('timeout', 10),
                    matcher=group.get('matcher', ''), state='declared', observed=None))
                restored=dict(hooks=[dict(type='command',command=command,commandWindows=windows,
                                         timeout=handler.get('timeout',10))])
                if group.get('matcher'):
                    restored['matcher']=group['matcher']
                recovery.setdefault(event,[]).append(restored)
    script_purposes = {
        'client_entry.py': 'Единая точка запуска инструментов MCP, обработчиков событий и публикации проверок; читает connection.json.',
        'hub_plugin.py': 'Описывает доступные инструменты MCP и направляет каждый вызов в нужную часть Hub; также запускает наблюдения за жизненным циклом.',
        'hub_http.py': 'Передаёт вызовы плагина локальному сервису по HTTP. Проверяет адрес подключения и размер ответа; сам сервер не запускает.',
        'hub_core.py': 'Учитывает чаты и зарегистрированную работу, записывает наблюдения и историю. Помогает обнаружить пересечения при редактировании одних файлов.',
        'hub_memory.py': 'Работает с задачами и планами и читает разрешённые источники проекта.',
        'hub_check.py': 'Запускает уже существующую проверку проекта и публикует её фактический результат вместе с журналом.',
        'hub_instructions.py': 'Показывает каталог и редактирует только локальные пользовательские инструкции Codex.',
        'hub_notices.py': 'Находит связанную параллельную работу: ту же задачу, зависимости или общие файлы. Сохраняет уведомления, которые агент может прочитать через MCP.',
        'hub_watch.py': 'По желанию коротко ждёт новое уведомление через асинхронный обработчик события; модель при этом не вызывается.',
        'git_integration.py': 'Создаёт проверяемые снимки Git и контрольные точки по настройкам проекта; разрешения Codex не обходит.',
        'project_settings.py': 'Хранит настройки проекта Hub, номера изменений, историю и операции сброса.',
        'git_changesets.py': 'Сохраняет состав и содержимое изменений работы, чтобы позднее проверить, что именно попало в коммит.',
        'hub_git_batch.py': 'Проверяет общий снимок изменений нескольких работ и помогает сохранить согласованный общий коммит штатными средствами Git.',
        'work_scope.py': 'Сопоставляет заявленные файлы работы с папками проекта. Это помогает учитывать несколько рабочих копий и обнаруживать пересечения.',
    }
    scripts = [dict(name=p.name, description=script_purposes.get(p.name, 'Внутренний модуль плагина.'),
                    runtime='Python', settings=(['PROJECT_HUB_URL · локальный адрес подключения'] if p.name in ('client_entry.py', 'hub_http.py') else
                        ['Существующая команда, профиль, ограничение времени и путь логов проекта'] if p.name == 'hub_check.py' else []))
               for p in sorted((package / 'scripts').glob('*.py'))]
    return dict(schemaVersion=1, package=dict(name=manifest.get('name', 'project-hub'), version=manifest.get('version')),
        revision=state['revision'], digest=state['revision'], initialized=state['initialized'],
        path=state['path'], scope=scope,
        history=state['history'], nativeDiscovery=state['nativeDiscovery'], restoreAllowed=state['restoreAllowed'],
        rules=[dict(id='core', title='Встроенные инструкции агента', kind='mandatory', default=core.read_text(encoding='utf-8'),
                    effective=core.read_text(encoding='utf-8'), source=str(core), editable=False),
               dict(id='userInstructions', title='Пользовательские инструкции Project Hub', kind='editable',
                    default=default_body(), effective=state['body'], source=state['path'], editable=True,
                    defaultChanged=state['defaultChanged'], maxLength=MAX_BODY)],
        architecture=[dict(id='boundary', title='Кто за что отвечает', description='Codex ведёт чат: выполняет шаги, запускает инструменты, управляет разрешениями и решает, когда продолжить. Плагин Project Hub предоставляет MCP-инструменты и передаёт их локальному сервису. Сервис хранит задачи, память, наблюдения и результаты в локальном хранилище, а веб-интерфейс показывает это состояние и позволяет отправлять команды. По вашей команде Hub может передать задачу или выбранный этап на выполнение в Codex. Саму работу выполняет Codex со своими разрешениями; Hub не может выдать себе дополнительные права.'),
            dict(id='request', title='Как проходит запрос агента', description='1. Агент читает инструкцию и выбирает инструмент MCP.\n2. Плагин передаёт имя инструмента, параметры, идентификатор чата и рабочую папку локальному HTTP-сервису.\n3. Сервис определяет проект, проверяет запрос и читает либо сохраняет данные.\n4. Ответ возвращается в Codex; агент оценивает результат и выбирает следующий шаг.\n\nВеб-интерфейс обращается к тому же сервису. Поэтому задача, созданная агентом, видна пользователю, а изменённый пользователем план доступен агенту при следующем чтении. Из Hub можно запустить выполнение задачи или выбранного этапа: вы открываете действие, выбираете область и режим, затем явно нажимаете «Начать» или «Продолжить». Hub передаёт контекст в Codex и показывает состояние запуска. Само появление задачи в плане не запускает её автоматически.'),
            dict(id='storage', title='Где сохраняются данные', description='Программы самого Project Hub — сервер, веб-интерфейс и плагин Codex — хранятся отдельно от пользовательских данных Hub. Исходники проектов, которые вы добавили в Hub, остаются в папках этих проектов. Каталог проектов хранит связь проекта с его папками. Задачи, этапы, решения и события сохраняются в локальном хранилище с историей; сведения о чатах и работе учитываются отдельно. Документация, архитектурные описания и версии файлов результатов сохраняются как связанные материалы.\n\nНомер версии данных нужен сервису, чтобы не затереть чужую правку при одновременном сохранении. Это не версия плагина и не коммит Git. Проверенный коммит, результат задачи и версия документа — разные подтверждения.'),
            dict(id='ownership', title='Как разделены инструкции', description='Встроенный project-hub/SKILL.md поставляется с плагином и описывает порядок работы агента. Ваши предпочтения хранятся отдельно в project-hub-user/SKILL.md. Именно этот файл меняет редактор «Ваши инструкции». AGENTS.md и другие инструкции отдельных проектов здесь не редактируются.\n\nCodex обнаруживает и читает инструкции своим механизмом. Сохранение файла не заставляет уже работающий чат перечитать его. Вызовы MCP не подменяют загрузку инструкций.'),
            dict(id='lifecycle', title='Как связаны задача, этап и работа чата', description='Задача описывает цель и критерии готовности. Этап — часть плана с конкретным результатом. Работа чата связывает действия агента с этапом и затрагиваемыми файлами. Создание задачи ещё не означает начало выполнения; отчёт о работе ещё не означает, что вся задача завершена.\n\nОбработчики событий отмечают наблюдаемую активность Codex. Остановка ответа или закрытие сессии не закрывают задачу. Предупреждение о параллельной правке помогает согласовать действия, но не выдаёт разрешения на запись и не является блокировкой файла.'),
            dict(id='distribution', title='Что происходит при обновлении и сбое', description='Для локальной установки предусмотрен ZIP-архив с программами Project Hub: сервером, веб-интерфейсом, сканером исходников, плагином Codex и установщиком. Python-код запускается из файлов; отдельного скомпилированного приложения этот способ поставки не создаёт. Архив содержит выбранные файлы для работы Hub, а не весь репозиторий разработки, историю Git или исходники ваших проектов. При установке создаются отдельные папки для программ Hub и его данных.\n\nВерсия плагина содержит встроенную инструкцию и начальный шаблон пользовательских правил. Обновление заменяет программы; личный текст и данные задач сохраняются отдельно. Восстановление шаблона — явное действие пользователя, которое заменяет только его инструкции.\n\nЕсли сервис недоступен, агент может продолжать разрешённую работу в проекте, но должен сообщить о несохранённых в Hub результатах. Плагин не создаёт запасную базу и не расширяет разрешения Codex. Ошибка доставки события не доказывает, что работа завершена или не выполнялась.')],
        skills=[dict(id='project-hub', title='project-hub · встроенные правила', description='Описывает, как Codex пользуется инструментами Hub: как определить пользователя и работу, вести этапы, прикладывать подтверждения и закрывать задачу.'),
                dict(id=NAME, title=NAME + ' · локальные предпочтения', description='Хранит редактируемые предпочтения пользователя. Codex находит этот skill среди локальных инструкций и читает его, когда применяет настройки.')],
        tools=[dict(name=t['name'], description=t['description'], group='MCP') for t in TOOLS], scripts=scripts,
        hooks=hook_rows,hookRecovery=dict(hooks=recovery),
        optionalHookRecovery=dict(description='По желанию: одно асинхронное ожидание длительностью до 45 секунд на пользовательский ход. Codex сам доставляет найденные факты в следующую безопасную точку; завершение обработчика не пробуждает бездействующий чат.',
            hooks={'UserPromptSubmit':[dict(hooks=[dict(type='command',
                command=(subprocess.list2cmdline([sys.executable,entry,'notice-hook']) if os.name=='nt'
                         else shlex.join([sys.executable,entry,'notice-hook'])),
                commandWindows=windows.removesuffix(' hook')+' notice-hook',timeout=50,**{'async':True})])]}),
        extensions=[dict(id='native-skills', title='Локальные skills', description='Пользовательские skills Codex с отдельными именами; их редактирование не меняет код Hub.', status='supported'),
                    dict(id='native-hooks', title='Пользовательские обработчики (hooks)', description='Настраиваются средствами Codex и вызывают существующий обработчик. Наличие шаблона само по себе не даёт доверия и не запускает его.', status='supported'),
                    dict(id='companion-mcp', title='Дополнительный MCP', description='Отдельное MCP-подключение использует открытые инструменты Hub; разрешения и отправка сообщений по-прежнему находятся под контролем Codex.', status='supported')],
        delivery=dict(description=('Codex читает локальный skill штатным механизмом. Вызов $project-hub-user применяет его явно; '
            if state['nativeDiscovery'] else 'Установщик должен подключить собственный skill к каталогу .agents/skills Codex. ') +
            'Сохранение не обновляет инструкции уже начатого чата. Hub не передаёт эти правила в ответах MCP.'))
