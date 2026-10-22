"use strict";
// Interface messages only. Project content is rendered independently.
globalThis.HubLocaleCatalog = {
  "provider.chatgptPlanLink": {"ru":"Управлять доступом к моделям","en":"Manage model access"},
  "provider.chatgptAccountInUse": {"ru":"Чтобы удалить аккаунт из Hub, сначала удалите использующие его подключения.","en":"Delete connections using this account before removing it from Hub."},
  "provider.chatgptAuthorize": {"ru":"Открыть страницу авторизации","en":"Open authorization page"},
  "provider.chatgptSavedAccounts": {"ru":"Сохранённые аккаунты ChatGPT","en":"Saved ChatGPT accounts"},
  "provider.chatgptAccountsHelp": {"ru":"Сохранённый аккаунт не означает, что вход сейчас подтверждён: смотрите состояние авторизации. Удаление подключения убирает его настройки. «Выйти из аккаунта» очищает авторизацию Hub, а «Удалить аккаунт ChatGPT» удаляет сохранённую запись.","en":"A saved account does not mean sign-in is currently verified: check authorization status. ChatGPT sign-in is stored separately from connection settings. Sign out clears Hub authorization; Remove account from Hub removes the saved entry."},
  "provider.chatgptConnectionTitle": {"ru":"Подключение ChatGPT","en":"ChatGPT connection"},
  "provider.chatgptConnectionHelp": {"ru":"Подключение хранит выбранные аккаунт и модель. Состояние авторизации ниже показывает, может ли Hub использовать этот аккаунт сейчас.","en":"The connection stores the selected account and model. Authorization status below shows whether Hub can use this account now."},
  "provider.chatgptLoadingAccounts": {"ru":"Обновление состояния аккаунтов…","en":"Refreshing account status…"},
  "provider.chatgptAccount": {"ru":"Аккаунт ChatGPT","en":"ChatGPT account"},
  "provider.chatgptAuthorizationState": {"ru":"Состояние авторизации","en":"Authorization status"},
  "provider.chatgptModel": {"ru":"Модель ChatGPT","en":"ChatGPT model"},
  "provider.chatgptName": {"ru":"Название подключения","en":"Connection name"},
  "provider.chatgptNetwork": {"ru":"Сетевой режим","en":"Network policy"},
  "provider.chatgptDirect": {"ru":"Напрямую","en":"Direct"},
  "provider.chatgptSystem": {"ru":"Системный HTTP-прокси","en":"System HTTP proxy"},
  "provider.chatgptBrowserHelp": {"ru":"Ожидается вход в браузере. Если страница не открылась, используйте ссылку «Открыть страницу авторизации». При ошибке доступа проверьте, открывается ли auth.openai.com в вашем браузере. Сетевой режим относится к запросам Hub.","en":"Waiting for sign-in in your browser. If the page did not open, use Open authorization page. If access fails, check whether auth.openai.com opens in your browser. The network mode applies to Hub requests."},
  "provider.serviceSectionTitle": {"ru":"Вход через сервис","en":"Service sign-in"},
  "provider.serviceSectionIntro": {"ru":"Сейчас доступен ChatGPT. Войдите в аккаунт и разрешите Hub использовать доступные модели вашего плана.","en":"ChatGPT is currently supported. Sign in and allow Hub to use the models available through your plan."},
  "provider.chatgptNoToken": {"ru":"Токены доступа в интерфейсе не показываются.","en":"Access tokens are never shown here."},
  "provider.chatgptLogoutWarning": {"ru":"Выход выполнен, но удалённый отзыв токена не подтверждён. Проверьте настройки ChatGPT.","en":"You are signed out, but remote token revocation was not confirmed. Check ChatGPT settings."},
  "provider.chatgptForgetError": {"ru":"Не удалось удалить аккаунт. Обновите состояние и повторите действие.","en":"The account could not be removed. Refresh its status and try again."},
  "provider.check_not_checked": {"ru":"Нет подтверждённой проверки для текущих настроек","en":"No confirmed check for these settings"},
  "provider.authOAuth": {"ru":"Вход через ChatGPT","en":"ChatGPT sign-in"},
  "provider.authAPI": {"ru":"Доступ по API-ключу","en":"API key access"},
  "provider.probeOAuthFailed": {"ru":"Проверка остановилась при подготовке авторизации ChatGPT. Запрос к модели не отправлен.","en":"The check stopped while preparing ChatGPT authorization. No model request was sent."},
  "provider.chatgptCryptoHelp": {"ru":"Hub не смог загрузить компонент проверки подписи. Восстановите компоненты Hub, затем повторите проверку авторизации. Повторный вход не устраняет эту ошибку.","en":"Hub could not load its signature verification component. Repair Hub components, then verify authorization again. Signing in again does not fix this error."},
  "provider.probeOAuthPending": {"ru":"Hub сохранил полученный ответ авторизации в защищённом хранилище. Следующая новая проверка модели продолжит проверку авторизации без повторного обмена токенов. Пока проверка не завершена, запросы к модели не отправляются. «Обновить результат» только читает прежнюю квитанцию.","en":"Hub retained the received authorization response in protected storage. The next new model check resumes authorization verification without repeating the token exchange. No model requests are sent until verification succeeds. Refresh result only reads the earlier receipt."},
  "provider.probeOAuthIdentityInvalid": {"ru":"Ответ авторизации ChatGPT не прошёл проверку учётной записи. Откройте «Изменить» у этого подключения и войдите снова. Переподключение MCP или адаптера Codex не исправляет авторизацию модели.","en":"The ChatGPT authorization response failed account verification. Open Edit for this connection and sign in again. Reconnecting MCP or the Codex adapter does not repair model authorization."},
  "provider.probeOAuthRefreshUnknown": {"ru":"Ответ на обновление авторизации не получен. Откройте «Изменить» у этого подключения и войдите в ChatGPT снова. Hub не повторяет обновление автоматически.","en":"No response was received for the authorization refresh. Open Edit for this connection and sign in to ChatGPT again. Hub never repeats the refresh automatically."},
  "provider.probeParseHelp": {"ru":"Ответ сервиса получен, но Hub не смог прочитать поток ответа модели. Успешное выполнение запроса пока не подтверждено. Точная причина формата указана в безопасных сведениях о передаче.","en":"The service responded, but Hub could not read the model response stream. Successful completion is not confirmed. Safe transport details contain the exact format reason."},
  "provider.probeContentTypeFacts": {"ru":"Тип данных в заголовке: {type}. Признаки содержимого: {body}.","en":"Response media type: {type}. Body format hint: {body}."},
  "provider.probeFormatNotRecorded": {"ru":"В этой проверке фактический формат ответа не сохранялся. «Обновить результат» читает прежнюю запись и не отправляет новый запрос к модели.","en":"This check did not record the actual response format. Refresh result reads the existing receipt without sending another model request."},
  "provider.probeContentTypeHelp": {"ru":"Hub ожидал поток событий (text/event-stream), но тип данных в заголовке ответа отличается или не указан. Даже HTTP 200 не подтверждает успешное выполнение модели. По одному этому признаку нельзя определить источник ошибки.","en":"Hub expected an event stream (text/event-stream), but the response header declares a different media type or none at all. Even HTTP 200 does not confirm successful inference. This fact alone does not identify the source of the error."},
  "provider.probeTimeoutLimit": {"ru":"Лимит ожидания одной сетевой операции: {seconds} с.","en":"Network inactivity timeout: {seconds} s."},
  "provider.probeTimeoutUnknown": {"ru":"Результат выполнения запроса неизвестен. Hub не повторяет его автоматически. «Обновить результат» читает сохранённые сведения; новый запрос требует отдельного подтверждения.","en":"The request outcome is unknown. Hub never retries it automatically. Refresh result reads the saved details; a new request requires separate confirmation."},
  "provider.probeTLSRead": {"ru":"HTTP-ответ уже получен; ошибка возникла при его чтении.","en":"An HTTP response had already been received; the failure occurred while reading it."},
  "provider.probeTLSUnknown": {"ru":"По этим сведениям нельзя подтвердить, был ли запрос выполнен сервисом. Hub не повторяет его автоматически.","en":"These details do not confirm whether the service processed the request. Hub never retries it automatically."},
  "provider.probeSystemProxyPolicy": {"ru":"«Системный HTTP-прокси» — выбранный режим сети. Он использует прокси, только если тот настроен; сама надпись не подтверждает наличие прокси.","en":"System HTTP proxy is the selected network policy. It uses a proxy only when one is configured; the label alone does not confirm that a proxy exists."},
  "provider.keepKey": {"ru":"Оставьте поле пустым, чтобы сохранить ключ. При изменении протокола или адреса API укажите новый ключ.","en":"Leave blank to keep the saved key. Enter a new key when changing protocol or API endpoint."},
  "provider.networkMode": {"ru":"Сетевой режим","en":"Network policy"},
  "provider.networkModeHelp": {"ru":"Прямой режим подключается к сервису напрямую. Системный режим использует HTTP-прокси из настроек системы или окружения процесса Hub. Локальный Hub всегда работает напрямую.","en":"Direct connects to the service directly. System uses the HTTP proxy settings available to the Hub process from the operating system or environment. A local Hub always connects directly."},
  "provider.direct": {"ru":"Напрямую","en":"Direct"},
  "provider.system": {"ru":"Системный HTTP-прокси","en":"System HTTP proxy"},
  "provider.chatgptForgetTitle": {"ru":"Удалить аккаунт из Hub?","en":"Remove account from Hub?"},
  "provider.chatgptForgetHelp": {"ru":"Hub выйдет из аккаунта «{name}» и удалит сохранённые данные входа. Аккаунт в OpenAI и история запросов Hub сохранятся.","en":"Hub will sign out of “{name}” and remove its saved sign-in data. Your OpenAI account and Hub request history will remain."},
  "provider.probeDiagnostics": {"ru":"Безопасные сведения о передаче","en":"Safe transport details"},
  "provider.probeCopy": {"ru":"Копировать диагностические сведения","en":"Copy diagnostic details"},
  "provider.probeNoDiagnostics": {"ru":"Диагностические сведения отсутствуют","en":"No diagnostic details are available"},
  "provider.probeConfirm": {"ru":"Запустить проверку","en":"Start probe"},
  "provider.probeRunning": {"ru":"Проверка выполняется","en":"Probe running"},
  "provider.probeFailed": {"ru":"Проверка завершилась ошибкой","en":"Probe failed"},
  "provider.probeUnknown": {"ru":"Результат проверки неизвестен. Обновите его перед новой проверкой.","en":"The probe outcome is unknown. Refresh it before starting a new probe."},
  "provider.probeError": {"ru":"Код ошибки","en":"Error code"},
  "provider.modelServicesTitle": {"ru":"Модели для запросов Hub","en":"Models for Hub requests"},
  "provider.scope": {"ru":"Для всей установки","en":"Across the installation"},
  "provider.modelServicesIntro": {"ru":"Прямой вызов API для анализа архитектуры, кода и документов.","en":"Direct API calls to analyze architecture, code, and documents."},
  "provider.scopeHelp": {"ru":"Эти настройки нужны, когда Hub сам обращается к модели. Модель в подключённом приложении выбирается в том приложении.","en":"These settings apply when Hub calls a model directly. Choose the model inside a connected application in that application."},
  "provider.authHelp": {"ru":"Выберите один из двух способов доступа: подписка ChatGPT или API-ключ выбранного сервиса.","en":"Choose between ChatGPT subscription access and an API key for the selected service."},
  "provider.apiSectionTitle": {"ru":"Подключение по API-ключу","en":"API-key connections"},
  "provider.apiSectionIntro": {"ru":"Подключите произвольный API-сервис и сохраните его ключ в защищённом хранилище. Доступ и квоту API-аккаунта определяет поставщик.","en":"Add any supported API service and keep its key in protected storage. The provider determines access and quota for the API account."},
  "provider.modelServicesUsage": {"ru":"Выбирайте сервис в таблице для запросов Hub. Результат анализа выбранного контекста сохраняется в Hub. Подключение API не предоставляет доступ к существующим чатам и само по себе не включает выполнение задач.","en":"Choose a service in the table for Hub requests. Analysis of the selected context is saved in Hub. Connecting an API does not provide access to existing chats or enable task execution by itself."},
  "provider.endpointDefaultSaved": {"ru":"Стандартный адрес сервиса","en":"Default service endpoint"},
  "localFiles.choose": {"ru":"Выбрать папку…","en":"Choose folder…"},
  "localFiles.open": {"ru":"Открыть папку на компьютере сервера","en":"Open the folder on the server computer"},
  "localFiles.reveal": {"ru":"Показать в папке на компьютере сервера","en":"Show in a folder on the server computer"},
  "localFiles.copy": {"ru":"Скопировать путь","en":"Copy path"},
  "localFiles.copyShort": {"ru":"Копировать","en":"Copy"},
  "localFiles.copied": {"ru":"Путь скопирован.","en":"Path copied."},
  "localFiles.copyUnavailable": {"ru":"Копирование недоступно. Выделите путь и скопируйте его вручную.","en":"Copy is unavailable. Select the path and copy it manually."},
  "localFiles.invalidPath": {"ru":"Сервер не вернул путь к папке.","en":"The server did not return a folder path."},
  "localFiles.failed": {"ru":"Не удалось открыть папку. Вы можете скопировать путь.","en":"Could not open the folder. You can copy its path."},
  "operations.create": {"ru":"Создание резервной копии","en":"Create backup"},
  "operations.upload-start": {"ru":"Загрузка ZIP","en":"Upload ZIP"},
  "operations.upload-complete": {"ru":"Проверка ZIP","en":"Verify ZIP"},
  "operations.restore-copy": {"ru":"Подготовка ZIP к восстановлению","en":"Prepare ZIP restore"},
  "operations.import-folder": {"ru":"Подготовка папки к импорту","en":"Prepare folder import"},
  "operations.inspect-folder": {"ru":"Проверка папки","en":"Inspect folder"},
  "operations.inspect-copy": {"ru":"Проверка источника импорта","en":"Inspect import source"},
  "operations.apply-import": {"ru":"Применение импорта","en":"Apply import"},
  "operations.change-folders": {"ru":"Изменение папок хранилища","en":"Change storage folders"},
  "operations.upgrade-copy": {"ru":"Преобразование источника","en":"Convert source"},
  "operations.delete-copy": {"ru":"Удаление временной подготовки","en":"Delete temporary preparation"},
  "operations.delete-archive": {"ru":"Удаление архива","en":"Delete archive"},
  "operations.project-create": {"ru":"Создание проекта","en":"Create project"},
  "operations.project-update": {"ru":"Изменение проекта","en":"Update project"},
  "operations.requesting": {"ru":"Отправка запроса","en":"Sending request"},
  "operations.unknown": {"ru":"Состояние уточняется","en":"Checking status"},
  "operations.waiting": {"ru":"Ожидание другой операции","en":"Waiting for another operation"},
  "operations.preparing": {"ru":"Подготовка","en":"Preparing"},
  "operations.snapshot": {"ru":"Снимок текущих данных","en":"Current data snapshot"},
  "operations.copying": {"ru":"Копирование","en":"Copying"},
  "operations.compressing": {"ru":"Сжатие","en":"Compressing"},
  "operations.verifying": {"ru":"Проверка","en":"Verifying"},
  "operations.inspecting": {"ru":"Проверка источника","en":"Inspecting source"},
  "operations.upload": {"ru":"Передача файла","en":"Transferring file"},
  "operations.restoring": {"ru":"Подготовка восстановления","en":"Preparing restore"},
  "operations.migrating": {"ru":"Преобразование формата","en":"Converting format"},
  "operations.importing": {"ru":"Импорт проектов","en":"Importing projects"},
  "operations.publishing": {"ru":"Применение данных","en":"Applying data"},
  "operations.restarting": {"ru":"Проверка нового запуска","en":"Checking new launch"},
  "operations.rollback": {"ru":"Возврат прежнего состояния","en":"Restoring previous state"},
  "operations.comparing": {"ru":"Сравнение проектов","en":"Comparing projects"},
  "operations.waiting-for-restart": {"ru":"Ожидание перезапуска","en":"Waiting for restart"},
  "operations.stopping": {"ru":"Остановка сервера","en":"Stopping server"},
  "operations.starting": {"ru":"Запуск сервера","en":"Starting server"},
  "operations.ready": {"ru":"Готово","en":"Ready"},
  "operations.waiting-for-drain": {"ru":"Ожидание завершения текущих изменений","en":"Waiting for current changes"},
  "operations.deleting": {"ru":"Удаление","en":"Deleting"},
  "operations.complete": {"ru":"Завершено","en":"Completed"},
  "operations.queued": {"ru":"В очереди","en":"Queued"},
  "operations.running": {"ru":"Выполняется","en":"Running"},
  "operations.succeeded": {"ru":"Завершено","en":"Completed"},
  "operations.failed": {"ru":"Ошибка","en":"Failed"},
  "operations.interrupted": {"ru":"Прервано","en":"Interrupted"},
  "operations.operation": {"ru":"Операция","en":"Operation"},
  "operations.bytes": {"ru":"Б","en":"B"},
  "operations.seconds": {"ru":"с","en":"s"},
  "operations.project": {"ru":"Проект","en":"Project"},
  "operations.details": {"ru":"Подробнее","en":"Details"},
  "operations.loadingDetails": {"ru":"Сведения об операции загружаются…","en":"Loading operation details…"},
  "operations.waitingFor": {"ru":"Ожидается завершение операции","en":"Waiting for operation"},
  "operations.recovery": {"ru":"Состояние восстановления","en":"Recovery state"},
  "operations.previewResult": {"ru":"Открыть предварительный просмотр импорта","en":"Open import preview"},
  "operations.success": {"ru":"Операция завершена. Результат сохранён в истории.","en":"The operation completed. Its result is saved in history."},
  "operations.paused": {"ru":"Просмотр доступен. Изменения временно приостановлены.","en":"Viewing is available. Changes are temporarily paused."},
  "operations.reconnecting": {"ru":"Связь потеряна. Состояние операций уточняется; прежняя блокировка сохраняется до ответа сервера.","en":"Connection lost. Checking operation status; the previous write lock remains until the server responds."},
  "folderSettings.title": {"ru":"Хранилище и резервные копии","en":"Storage and backups"},
  "folderSettings.scope": {"ru":"Папки относятся ко всей установке Hub. Выбор папки заполняет поле; изменение применяется отдельным действием.","en":"These folders apply to the entire Hub installation. Choosing a folder fills the field; a separate action applies the change."},
  "folderSettings.installation": {"ru":"Вся установка","en":"Entire installation"},
  "folderSettings.data": {"ru":"Папка данных Hub","en":"Hub data folder"},
  "folderSettings.dataHelp": {"ru":"Все проекты, задачи, история, документы и вложения этой установки","en":"All projects, tasks, history, documents and attachments in this installation"},
  "folderSettings.backups": {"ru":"Папка резервных копий","en":"Backup folder"},
  "folderSettings.backupHelp": {"ru":"Архивы для восстановления. Они хранятся отдельно от рабочих данных","en":"Archives for recovery. They are stored separately from active data"},
  "folderSettings.serverComputer": {"ru":"Выбор и открытие папок выполняются на компьютере сервера Hub. При недоступном файловом менеджере вы можете скопировать путь.","en":"Folder selection and opening run on the Hub server computer. If its file manager is unavailable, you can copy the path."},
  "folderSettings.unavailable": {"ru":"Изменение папок недоступно в этом режиме запуска. Фактические пути показаны в сведениях о сервере.","en":"Folder changes are unavailable in this launch mode. Server details show the active paths."},
  "folderSettings.review": {"ru":"Проверьте изменение папок","en":"Review folder changes"},
  "folderSettings.moveHelp": {"ru":"Hub проверит назначение, скопирует согласованный снимок данных, сохранит прежнюю папку и проверит новый запуск. При ошибке прежние данные и настройки будут восстановлены. Непустое назначение не перезаписывается.","en":"Hub checks the destination, copies a consistent data snapshot, preserves the old folder and checks the new launch. Errors restore the previous data and settings. A nonempty destination is never overwritten."},
  "folderSettings.archivesRemain": {"ru":"Существующие архивы останутся в прежней папке. Следующие резервные копии сохранятся в выбранную папку; прежние архивы не удаляются.","en":"Existing archives remain in their previous folder. Future backups use the selected folder; earlier archives are not deleted."},
  "folderSettings.apply": {"ru":"Применить изменение папок","en":"Apply folder changes"},
  "folderSettings.cancel": {"ru":"Отменить","en":"Cancel"},
  "folderSettings.check": {"ru":"Проверить изменение папок","en":"Check folder changes"},
  "folderSettings.retry": {"ru":"Проверить и повторить тот же запрос","en":"Check and retry the same request"},
  "folderSettings.failed": {"ru":"Не удалось изменить папки.","en":"Could not change folders."},
  "folderSettings.invalid": {"ru":"Сервер не вернул настройки папок.","en":"The server did not return folder settings."},
  "folderSettings.confirm": {"ru":"Применить показанные папки? Прежняя папка данных и существующие архивы сохранятся.","en":"Apply the shown folders? The previous data folder and existing archives are preserved."},
  "folderSettings.invalidPreview": {"ru":"Сервер не подтвердил допустимость выбранных папок.","en":"The server did not confirm that the selected folders are valid."},
  "folderSettings.invalidAck": {"ru":"Сервер не подтвердил операцию. Повторите тот же запрос.","en":"The server did not confirm the operation. Retry the same request."},
  "folderSettings.saved": {"ru":"Папки применены. Прежние данные и архивы сохранены.","en":"Folder changes applied. Previous data and archives are preserved."},
  "backupAdmin.activeScope": {"ru":"Архив включает данные всех проектов. После проверки ZIP автоматически откроется предварительный просмотр; рабочие данные изменятся только после подтверждения.","en":"Archives include all projects. After verification, the import preview opens automatically; active data changes only after you confirm."},
  "backupAdmin.prepareRestore": {"ru":"Восстановить…","en":"Restore…"},
  "backupAdmin.sourcePrepared": {"ru":"ZIP подготовлен к импорту. Рабочие данные и исходный архив сохранены.","en":"ZIP prepared for import. Active data and the source archive are preserved."},
  "backupAdmin.openImportPreview": {"ru":"Выбрать проекты и режим восстановления","en":"Choose projects and restore mode"},
  "backupAdmin.restoreZip": {"ru":"Восстановить из ZIP","en":"Restore from ZIP"},
  "backupAdmin.importUploadHelp": {"ru":"Выберите ZIP-архив Project Hub. После загрузки и проверки автоматически откроется предварительный просмотр источника. Данные применятся только после подтверждения; исходный ZIP сохранится.","en":"Choose a Project Hub ZIP archive. After upload and verification, the source preview opens automatically. Data is applied only after confirmation; the source ZIP is preserved."},
  "backupAdmin.prepareConfirm": {"ru":"Подготовить ZIP к импорту? Рабочие данные изменятся только после выбора режима, проектов и явного подтверждения в предварительном просмотре.","en":"Prepare the ZIP for import? Active data changes only after you choose a mode and projects and explicitly confirm the preview."},
  "backupAdmin.unverified": {"ru":"Не проверен","en":"Not verified"},
  "projects.oldSchemaImportHelp": {"ru":"Управление отключено для прежнего формата данных. В разделе «Данные Hub» проверьте источник и импортируйте его в рабочую папку. Преобразование выполняется во временной копии; исходные данные сохранятся.","en":"Management is unavailable for this older format. Inspect and import the source into the active folder in Hub data. Conversion uses a temporary copy; source data is preserved."},
  "backupAdmin.deleting": {"ru":"Удаление", "en":"Deleting"},
  "backupAdmin.waiting": {"ru":"Ожидание другой операции", "en":"Waiting for another operation"},
  "backupAdmin.refresh": {"ru":"Обновить", "en":"Refresh"},
  "backupAdmin.title": {
    "ru": "Резервные копии",
    "en": "Backups"
  },
  "backupAdmin.scope": {
    "ru": "Архив включает данные всех проектов. Восстановление создаёт отдельную неактивную копию.",
    "en": "The archive includes every project. Restoration creates a separate inactive storage copy."
  },
  "backupAdmin.createButton": {
    "ru": "Создать копию",
    "en": "Create backup"
  },
  "backupAdmin.page": {
    "ru": "Страница",
    "en": "Page"
  },
  "backupAdmin.previous": {
    "ru": "Назад",
    "en": "Previous"
  },
  "backupAdmin.next": {
    "ru": "Далее",
    "en": "Next"
  },
  "backupAdmin.archive": {
    "ru": "Архив",
    "en": "Archive"
  },
  "backupAdmin.date": {
    "ru": "Дата",
    "en": "Date"
  },
  "backupAdmin.size": {
    "ru": "Размер",
    "en": "Size"
  },
  "backupAdmin.projects": {
    "ru": "Проекты",
    "en": "Projects"
  },
  "backupAdmin.verification": {
    "ru": "Проверка",
    "en": "Verification"
  },
  "backupAdmin.actions": {
    "ru": "Действия",
    "en": "Actions"
  },
  "backupAdmin.verified": {
    "ru": "Проверен",
    "en": "Verified"
  },
  "backupAdmin.details": {
    "ru": "Подробности",
    "en": "Details"
  },
  "backupAdmin.download": {
    "ru": "Скачать",
    "en": "Download"
  },
  "backupAdmin.restore": {
    "ru": "Восстановить…",
    "en": "Restore…"
  },
  "backupAdmin.delete": {
    "ru": "Удалить",
    "en": "Delete"
  },
  "backupAdmin.close": {
    "ru": "Закрыть",
    "en": "Close"
  },
  "backupAdmin.history": {
    "ru": "История операций",
    "en": "Operation history"
  },
  "backupAdmin.operation": {
    "ru": "Операция",
    "en": "Operation"
  },
  "backupAdmin.result": {
    "ru": "Результат",
    "en": "Result"
  },
  "backupAdmin.create": {
    "ru": "Создание архива",
    "en": "Create backup"
  },
  "backupAdmin.restore-copy": {
    "ru": "Восстановление копии",
    "en": "Restore copy"
  },
  "backupAdmin.import-folder": {
    "ru": "Импорт папки",
    "en": "Import folder"
  },
  "backupAdmin.upgrade-copy": {
    "ru": "Обновление формата",
    "en": "Upgrade storage format"
  },
  "backupAdmin.upload-complete": {
    "ru": "Проверка загрузки",
    "en": "Verify upload"
  },
  "backupAdmin.delete-archive": {
    "ru": "Удаление архива",
    "en": "Delete archive"
  },
  "backupAdmin.delete-copy": {
    "ru": "Удаление копии",
    "en": "Delete inactive storage"
  },
  "backupAdmin.succeeded": {
    "ru": "Завершено",
    "en": "Completed"
  },
  "backupAdmin.interrupted": {
    "ru": "Прервано",
    "en": "Interrupted"
  },
  "backupAdmin.failed": {
    "ru": "Ошибка",
    "en": "Failed"
  },
  "backupAdmin.sort": {
    "ru": "Сортировка",
    "en": "Sort by"
  },
  "backupAdmin.newest": {
    "ru": "Сначала новые",
    "en": "Newest first"
  },
  "backupAdmin.oldest": {
    "ru": "Сначала старые",
    "en": "Oldest first"
  },
  "backupAdmin.largest": {
    "ru": "По размеру",
    "en": "Largest first"
  },
  "backupAdmin.name": {
    "ru": "По названию",
    "en": "Name"
  },
  "backupAdmin.perPage": {
    "ru": "На странице",
    "en": "Rows per page"
  },
  "backupAdmin.loading": {
    "ru": "Загрузка…",
    "en": "Loading…"
  },
  "backupAdmin.empty": {
    "ru": "Резервных копий пока нет.",
    "en": "No backups yet."
  },
  "backupAdmin.upload": {
    "ru": "Загрузить архив",
    "en": "Upload backup"
  },
  "backupAdmin.uploadHelp": {
    "ru": "Выберите ZIP-архив Project Hub с этой или другой машины. Загрузка проверяет формат и содержимое. Затем можно восстановить данные в отдельную папку; подключение копии выполняется в разделе «Данные Hub».",
    "en": "Choose a Project Hub ZIP backup from this or another machine. Uploading verifies its format and contents. You can then restore it to a separate folder and activate the copy in Hub data."
  },
  "backupAdmin.file": {
    "ru": "Файл резервной копии",
    "en": "Backup file"
  },
  "backupAdmin.choose": {
    "ru": "Выбрать файл",
    "en": "Choose file"
  },
  "backupAdmin.noFile": {
    "ru": "Файл не выбран",
    "en": "No file selected"
  },
  "backupAdmin.verifyUpload": {
    "ru": "Загрузить и проверить",
    "en": "Upload and verify"
  },
  "backupAdmin.confirmDelete": {
    "ru": "Удалить этот архив? Активные данные и восстановленные копии сохранятся.",
    "en": "Delete this archive? Active data and restored copies are preserved."
  },
  "backupAdmin.pending": {
    "ru": "Повторите неподтверждённую операцию перед новым действием.",
    "en": "Retry the unconfirmed operation before starting another."
  },
  "backupAdmin.invalidAck": {
    "ru": "Сервер не подтвердил операцию. Повторите тот же запрос.",
    "en": "The server did not confirm the operation. Retry the same request."
  },
  "backupAdmin.retry": {
    "ru": "Повторить операцию",
    "en": "Retry operation"
  },
  "backupAdmin.restored": {
    "ru": "Создана отдельная неактивная копия.",
    "en": "A separate inactive storage copy was created."
  },
  "backupAdmin.openData": {
    "ru": "Открыть данные Hub",
    "en": "Open Hub data"
  },
  "storage.activeStorage": {
    "ru": "Активное хранилище",
    "en": "Active storage"
  },
  "storage.activeHelp": {
    "ru": "Все проекты этой установки используют одну папку данных. Импорт применяется в эту папку.",
    "en": "All projects in this installation use one data folder. Imports are applied to this folder."
  },
  "storage.attachStorage": {
    "ru": "Подключить прежние данные",
    "en": "Import existing data"
  },
  "storage.format": {
    "ru": "Формат хранилища",
    "en": "Storage format"
  },
  "storage.state": {
    "ru": "Состояние",
    "en": "Status"
  },
  "storage.projects": {
    "ru": "Проекты",
    "en": "Projects"
  },
  "storage.activeState": {
    "ru": "Активно",
    "en": "Active"
  },
  "storage.inactiveState": {
    "ru": "Неактивно",
    "en": "Inactive"
  },
  "storage.storageName": {
    "ru": "Хранилище",
    "en": "Storage"
  },
  "storage.date": {
    "ru": "Создано",
    "en": "Created"
  },
  "storage.source": {
    "ru": "Источник",
    "en": "Source"
  },
  "storage.actions": {
    "ru": "Действия",
    "en": "Actions"
  },
  "storage.folderImport": {
    "ru": "Папка данных",
    "en": "Data folder"
  },
  "storage.backupSource": {
    "ru": "Резервная копия",
    "en": "Backup"
  },
  "storage.copiesHelp": {
    "ru": "Здесь собраны импортированные и восстановленные копии. Просмотрите содержимое перед обновлением формата или подключением.",
    "en": "Imported and restored copies are listed here. Inspect the contents before upgrading their format or activating them."
  },
  "storage.noCopies": {
    "ru": "Подготовленных копий пока нет.",
    "en": "No prepared storage copies yet."
  },
  "storage.compatible": {
    "ru": "Готово к подключению",
    "en": "Ready to activate"
  },
  "storage.upgradeRequired": {
    "ru": "Нужно обновить формат",
    "en": "Format upgrade required"
  },
  "storage.deleteCopy": {
    "ru": "Удалить неактивную копию",
    "en": "Delete inactive copy"
  },
  "storage.deleteConfirm": {
    "ru": "Удалить эту неактивную копию? Архив и активные данные сохранятся.",
    "en": "Delete this inactive copy? The backup archive and active data are preserved."
  },
  "storage.close": {
    "ru": "Закрыть подробности",
    "en": "Close details"
  },
  "projects.projects": {"ru":"Проекты","en":"Projects"},
  "projects.data": {"ru":"Данные Hub","en":"Hub data"},
  "projects.backups": {"ru":"Резервные копии","en":"Backups"},
  "projects.adminIntro": {"ru":"Управляйте проектами, папками кода, данными и резервными копиями.","en":"Manage projects, code folders, Hub data and backups."},
  "projects.configure": {"ru":"Настроить","en":"Configure"},
  "projects.connectAgent": {"ru":"Подключить агента","en":"Connect an agent"},
  "projects.general": {"ru":"Общие","en":"General"},
  "projects.code": {"ru":"Папки кода","en":"Code folders"},
  "projects.agents": {"ru":"Агенты","en":"Agents"},
  "projects.projectSettings": {"ru":"Настройки проекта","en":"Project settings"},
  "projects.generalHelp": {"ru":"Название используется в Hub. Изменения сохраняют историю проекта.","en":"This name is used in Hub. Changes preserve the project history."},
  "projects.identifier": {"ru":"Идентификатор","en":"Identifier"},
  "projects.state": {"ru":"Состояние","en":"Status"},
  "projects.actions": {"ru":"Действия проекта","en":"Project actions"},
  "projects.close": {"ru":"Закрыть","en":"Close"},
  "projects.cancel": {"ru":"Отмена","en":"Cancel"},
  "projects.upgradeNeeded": {"ru":"Нужна совместимая копия данных","en":"A compatible storage copy is required"},
  "projects.oldSchemaHelp": {"ru":"Управление отключено для прежнего формата хранилища. В разделе «Данные Hub» создайте отдельную копию, обновите её формат и подключите через установленное приложение. Исходные данные сохранятся.","en":"Management is unavailable for this older storage format. In Hub data, create a separate copy, upgrade its format and activate it through the installed application. The original data is preserved."},
  "projects.confirmDelete": {"ru":"Удалить проект из активного списка? Его история сохранится, проект можно восстановить.","en":"Remove this project from the active list? Its history is preserved and the project can be recovered."},
  "workspaces.enabled": {"ru":"Подключена","en":"Enabled"},
  "workspaces.disabled": {"ru":"Отключена","en":"Disabled"},
  "app.observationPending": {
    "ru": "Наблюдение подготавливается",
    "en": "Observation is being prepared"
  },
  "app.observationEmpty": {
    "ru": "Наблюдения Hub пока не записаны",
    "en": "No Hub observations have been recorded"
  },
  "app.gitWorkspaceRequired": {
    "ru": "Подключите рабочую папку с кодом, чтобы использовать Git",
    "en": "Connect a code workspace to use Git"
  },
  "app.0ce20bfaf5c6": {
    "ru": "Проверить перенос",
    "en": "Preview transfer"
  },
  "app.6fca7296b32d": {
    "ru": "Подтвердить перенос",
    "en": "Confirm transfer"
  },
  "app.f6ca337ab735": {
    "ru": "«{v0}»: {v1} этапов, {v2} событий. История сохранится; ссылки на исходные файлы сохранят прежний проект.",
    "en": "«{v0}»: {v1} stages, {v2} events. History will be preserved; source file links will keep the original project."
  },
  "app.588f9296246f": {
    "ru": "Проверьте перенос в выбранный проект.",
    "en": "Verify the move to the selected project."
  },
  "app.beac0e65f6ef": {
    "ru": "<h2>Перенос задачи</h2><p>Задача сохранит план, историю и связи с чатами. Чаты и исходные файлы останутся на месте.</p><label>Целевой проект <select id=\"transfer-target\">{v0}</select></label><p id=\"transfer-details\" role=\"status\">{v1}</p><div><button class=\"icon-button\" id=\"transfer-submit\" title=\"Проверить перенос\" aria-label=\"Проверить перенос\" {v2}>{v3}</button> <button class=\"icon-button\" data-close title=\"Отмена\" aria-label=\"Отмена\">{v4}</button></div>",
    "en": "<h2>Task transfer</h2><p>The task will keep its plan, history, and chat links. Chats and source files will stay in place.</p><label>Target project <select id=\"transfer-target\">{v0}</select></label><p id=\"transfer-details\" role=\"status\">{v1}</p><div><button class=\"icon-button\" id=\"transfer-submit\" title=\"Preview transfer\" aria-label=\"Preview transfer\" {v2}>{v3}</button> <button class=\"icon-button\" data-close title=\"Cancel\" aria-label=\"Cancel\">{v4}</button></div>"
  },
  "app.a534013716e3": {
    "ru": "Других локальных проектов пока нет.",
    "en": "There are no other local projects yet."
  },
  "app.f2a39ce40b34": {
    "ru": "Выберите проект и проверьте перенос.",
    "en": "Choose a project and preview the transfer."
  },
  "app.124976c21333": {
    "ru": "<h2>Перенос задачи</h2><p>Загрузка проектов…</p><button class=\"icon-button\" data-close title=\"Закрыть\" aria-label=\"Закрыть\">{v0}</button>",
    "en": "<h2>Task transfer</h2><p>Loading projects…</p><button class=\"icon-button\" data-close title=\"Close\" aria-label=\"Close\">{v0}</button>"
  },
  "app.d230f0ae8043": {
    "ru": "Перенос задачи",
    "en": "Task transfer"
  },
  "app.51e140267931": {
    "ru": "Выбрать проект",
    "en": "Choose a project"
  },
  "app.b4e73f30261b": {
    "ru": "Подключённых проектов пока нет",
    "en": "There are no connected projects yet"
  },
  "app.3a2222fbb114": {
    "ru": " · сохранённая история",
    "en": " · saved history"
  },
  "app.d291fc05692e": {
    "ru": "Каталог Codex недоступен · сохранённый список",
    "en": "Codex catalog unavailable · saved list"
  },
  "app.4429fb918450": {
    "ru": "Проект не выбран",
    "en": "No project selected"
  },
  "app.60e51bb9d667": {
    "ru": "Сервер доступен",
    "en": "Server available"
  },
  "app.48d28a7c49a4": {
    "ru": "Каталог проектов недоступен",
    "en": "Project catalog unavailable"
  },
  "app.f79e3043429e": {
    "ru": "Не удалось обновить задачу",
    "en": "Could not update task"
  },
  "app.923dd22a6da8": {
    "ru": "ошибка журнала",
    "en": "log error"
  },
  "app.07d3f125d958": {
    "ru": "Push выполнен, но запись в историю не сохранена: ",
    "en": "Push completed, but the history record was not saved: "
  },
  "app.cd044157f115": {
    "ru": "Push не выполнен",
    "en": "Push was not completed"
  },
  "app.c69306bcbd49": {
    "ru": "Отправить текущую ветку в удалённый репозиторий?",
    "en": "Push the current branch to the remote repository?"
  },
  "app.5516fff043c1": {
    "ru": "Не удалось обновить проект: ",
    "en": "Could not refresh the project: "
  },
  "app.32dbbc1cc1fc": {
    "ru": "Проект загружен",
    "en": "Project loaded"
  },
  "app.f45edf006851": {
    "ru": "Проект",
    "en": "Project"
  },
  "app.c263b1efab35": {
    "ru": "Git-сводка не загрузилась: ",
    "en": "Git summary did not load: "
  },
  "app.1205ee9c3d92": {
    "ru": "Связь потеряна · переподключение",
    "en": "Connection lost · reconnecting"
  },
  "app.5b8e4f8d9441": {
    "ru": "Обновляется в реальном времени",
    "en": "Updating in real time"
  },
  "app.0430a7ea834a": {
    "ru": "Связь потеряна",
    "en": "Connection lost"
  },
  "app.105fe2f786c3": {
    "ru": "Подключено",
    "en": "Connected"
  },
  "app.8f014b0c85c8": {
    "ru": "Состояние связи относится к серверу портала. Последнее событие показывает публикацию агентом, а не подтверждает его непрерывную активность.",
    "en": "The connection state refers to the portal server. The last event shows agent publication, not continuous activity."
  },
  "app.3b669c4b247a": {
    "ru": "Последнее событие: {v0}{v1} · событий: {v2}",
    "en": "Latest event: {v0}{v1} · events: {v2}"
  },
  "app.b8dbb45818c4": {
    "ru": "ещё нет",
    "en": "not yet"
  },
  "app.59b9a2f87cfa": {
    "ru": " мин назад",
    "en": " min ago"
  },
  "app.fb6caad2dda8": {
    "ru": "<p role=\"status\">Загрузка раздела…</p>",
    "en": "<p role=\"status\">Loading section…</p>"
  },
  "app.2cce607ef7ae": {
    "ru": "<div class=\"page-head\"><div><h1>Проект не подключён</h1><p>Откройте раздел <a href=\"#projects\">«Проекты»</a>, чтобы добавить проект или перенести данные. Затем выберите проект в верхнем меню.</p></div></div>",
    "en": "<div class=\"page-head\"><div><h1>No project connected</h1><p>Open the section <a href=\"#projects\">«Projects»</a>, to add a project or move data. Then select a project from the top menu.</p></div></div>"
  },
  "app.bd3a5be11e2a": {
    "ru": "Обзор",
    "en": "Overview"
  },
  "app.06382c114a63": {
    "ru": "Проект / ",
    "en": "Project / "
  },
  "app.e0d097d35e6e": {
    "ru": "Хранилище / ",
    "en": "Storage / "
  },
  "app.d66afda7ef30": {
    "ru": "Не удалось загрузить архив: ",
    "en": "Could not load archive: "
  },
  "app.5d4294815184": {
    "ru": "<details class=\"diagnostic-archive\" data-key=\"diagnostic-archive\"><summary>Технический архив</summary><div id=\"diagnostic-archive-content\">",
    "en": "<details class=\"diagnostic-archive\" data-key=\"diagnostic-archive\"><summary>Technical archive</summary><div id=\"diagnostic-archive-content\">"
  },
  "app.0e4b39900135": {
    "ru": "</button></div><p class=\"caption\">Включая архивные чаты и завершенные работы. Связи берутся из сохраненной истории Hub.</p><div id=\"chats-history-content\">",
    "en": "</button></div><p class=\"caption\">Includes archived chats and completed work. Links come from the saved Hub history.</p><div id=\"chats-history-content\">"
  },
  "app.6b8fd6f46944": {
    "ru": "<section class=\"diagnostic-section\"><div class=\"section-head\"><h2>Вся история чатов</h2><button class=\"icon-button\" data-chats-retry title=\"Обновить историю чатов\" aria-label=\"Обновить историю чатов\">",
    "en": "<section class=\"diagnostic-section\"><div class=\"section-head\"><h2>Full chat history</h2><button class=\"icon-button\" data-chats-retry title=\"Refresh chat history\" aria-label=\"Refresh chat history\">"
  },
  "app.caf39202a46d": {
    "ru": "<p class=\"caption\">Список ограничен последними доступными записями; остальные чаты доступны в истории ниже.</p>",
    "en": "<p class=\"caption\">The list is limited to the latest available entries; other chats are available in the history below.</p>"
  },
  "app.b268df9a3e16": {
    "ru": "<button class=\"icon-button\" id=\"diagnostic-more\" title=\"Показать ещё\" aria-label=\"Показать ещё\">{v0}</button>",
    "en": "<button class=\"icon-button\" id=\"diagnostic-more\" title=\"Show more\" aria-label=\"Show more\">{v0}</button>"
  },
  "app.fdabea922bb4": {
    "ru": "Нет наблюдений о чатах.",
    "en": "No chat observations."
  },
  "app.f399a4d4ed88": {
    "ru": "Чаты не найдены.",
    "en": "No chats found."
  },
  "app.afbd635a939a": {
    "ru": "<p class=\"caption\">Последняя наблюдаемая активность; текущее выполнение не подтверждено.</p>",
    "en": "<p class=\"caption\">Most recently observed activity; current execution is not confirmed.</p>"
  },
  "app.17246338fcc4": {
    "ru": "<section class=\"diagnostic-section\"><div class=\"section-head\"><h2>Недавние чаты</h2><input id=\"diagnostic-search\" type=\"search\" aria-label=\"Поиск чатов\" placeholder=\"Поиск чатов\" value=\"",
    "en": "<section class=\"diagnostic-section\"><div class=\"section-head\"><h2>Recent chats</h2><input id=\"diagnostic-search\" type=\"search\" aria-label=\"Search chats\" placeholder=\"Search chats\" value=\""
  },
  "app.bc85cf0314d1": {
    "ru": "<div><span class=\"caption\">Данные получены</span><strong>",
    "en": "<div><span class=\"caption\">Data received</span><strong>"
  },
  "app.6f596994f824": {
    "ru": "Нет актуальных данных",
    "en": "No current data"
  },
  "app.d81568b864c8": {
    "ru": "Доступен",
    "en": "Available"
  },
  "app.5d591011174d": {
    "ru": "<div><span class=\"caption\">Каталог Codex</span><strong>",
    "en": "<div><span class=\"caption\">Codex catalog</span><strong>"
  },
  "app.0cf96d40d24c": {
    "ru": "Переподключение…",
    "en": "Reconnecting…"
  },
  "app.977e2e697b1a": {
    "ru": "<section class=\"diagnostic-health\"><div><span class=\"caption\">Связь с порталом</span><strong id=\"diagnostic-connection\">",
    "en": "<section class=\"diagnostic-health\"><div><span class=\"caption\">Portal connection</span><strong id=\"diagnostic-connection\">"
  },
  "app.c2630799a363": {
    "ru": "История обсуждений и работы по задачам проекта.",
    "en": "History of discussions and work on project tasks."
  },
  "app.b5121e526dd9": {
    "ru": "Чаты",
    "en": "Chats"
  },
  "app.e2bd047ec63a": {
    "ru": "Каталог Codex недоступен",
    "en": "Codex catalog unavailable"
  },
  "app.089609cd6038": {
    "ru": "Диагностические данные недоступны",
    "en": "Diagnostic data unavailable"
  },
  "app.35c51618fc23": {
    "ru": "<button class=\"icon-button\" data-archive-page=\"next\" title=\"Следующие\" aria-label=\"Следующие\">{v0}</button>",
    "en": "<button class=\"icon-button\" data-archive-page=\"next\" title=\"Next\" aria-label=\"Next\">{v0}</button>"
  },
  "app.499c191d5485": {
    "ru": "<button class=\"icon-button\" data-archive-page=\"previous\" title=\"Предыдущие\" aria-label=\"Предыдущие\">{v0}</button>",
    "en": "<button class=\"icon-button\" data-archive-page=\"previous\" title=\"Previous\" aria-label=\"Previous\">{v0}</button>"
  },
  "app.879f9de30b05": {
    "ru": "<p class=\"muted\">Записей нет.</p>",
    "en": "<p class=\"muted\">No records.</p>"
  },
  "app.f4c588f63d10": {
    "ru": "<p class=\"caption\">Исторические записи. Не являются текущими блокировками.</p>",
    "en": "<p class=\"caption\">Historical records. They are not current locks.</p>"
  },
  "app.32aa642b0ee5": {
    "ru": "Запись работы",
    "en": "Work record"
  },
  "app.542d994bd853": {
    "ru": "Попытка резервирования",
    "en": "Reservation attempt"
  },
  "app.0baf9497afd4": {
    "ru": "</p><button class=\"icon-button\" id=\"diagnostic-archive-retry\" title=\"Повторить\" aria-label=\"Повторить\">",
    "en": "</p><button class=\"icon-button\" id=\"diagnostic-archive-retry\" title=\"Retry\" aria-label=\"Retry\">"
  },
  "app.4a055a905b03": {
    "ru": "<p role=\"status\">Загрузка архива…</p>",
    "en": "<p role=\"status\">Loading archive…</p>"
  },
  "app.ca545f32f926": {
    "ru": "Не удалось загрузить чаты: ",
    "en": "Could not load chats: "
  },
  "app.45f803221317": {
    "ru": "</button></div><p class=\"caption\">Обсуждение, планирование и работа по сохраненным связям задачи. Участники сгруппированы по родительскому чату.</p><div id=\"chats-history-content\">",
    "en": "</button></div><p class=\"caption\">Discussion, planning and work based on saved task links. Participants are grouped by parent chat.</p><div id=\"chats-history-content\">"
  },
  "app.6b66cab9fbe4": {
    "ru": "<section class=\"diagnostic-section task-chats\"><div class=\"section-head\"><h2>Чаты задачи</h2><button class=\"icon-button\" data-chats-retry title=\"Обновить чаты\" aria-label=\"Обновить чаты\">",
    "en": "<section class=\"diagnostic-section task-chats\"><div class=\"section-head\"><h2>Task chats</h2><button class=\"icon-button\" data-chats-retry title=\"Refresh chats\" aria-label=\"Refresh chats\">"
  },
  "app.c47ae8612b44": {
    "ru": "<button class=\"icon-button\" data-chats-more title=\"Показать ещё чаты\" aria-label=\"Показать ещё чаты\" ",
    "en": "<button class=\"icon-button\" data-chats-more title=\"Show more chats\" aria-label=\"Show more chats\" "
  },
  "app.1cc60d66f193": {
    "ru": "</p><button class=\"icon-button\" data-chats-retry title=\"Повторить загрузку\" aria-label=\"Повторить загрузку\">",
    "en": "</p><button class=\"icon-button\" data-chats-retry title=\"Retry loading\" aria-label=\"Retry loading\">"
  },
  "app.262ccea54a08": {
    "ru": "<p role=\"status\">Загрузка чатов…</p>",
    "en": "<p role=\"status\">Loading chats…</p>"
  },
  "app.3716a2b2d4ad": {
    "ru": "Сохраненных связей с чатами пока нет. Обсуждения без записи работы или автора события не привязаны к задаче.",
    "en": "There are no saved chat links yet. Discussions without a work record or event author are not linked to a task."
  },
  "app.cf2b4f4de8fd": {
    "ru": "Каталог ограничен 5000 записями; более старые чаты без сохраненных связей Hub могут отсутствовать.",
    "en": "The catalog is limited to 5,000 records; older chats without saved Hub links may be missing."
  },
  "app.d7a3c3b07cea": {
    "ru": "Каталог Codex недоступен.",
    "en": "The Codex catalog is unavailable."
  },
  "app.4a33d2a34d01": {
    "ru": "Открыть в Codex",
    "en": "Open in Codex"
  },
  "app.97ec4c95cdbd": {
    "ru": "Открыть родительский чат",
    "en": "Open parent chat"
  },
  "app.7add60b3df59": {
    "ru": "<div class=\"chat-participants-label\">Агенты, работавшие в чате</div><div class=\"diagnostic-children\">",
    "en": "<div class=\"chat-participants-label\">Agents that worked in the chat</div><div class=\"diagnostic-children\">"
  },
  "app.3951a00db6d1": {
    "ru": "<p class=\"caption\">Последняя запись по задаче: ",
    "en": "<p class=\"caption\">Latest task entry: "
  },
  "app.ef4192cac8bc": {
    "ru": "Текущее выполнение не подтверждено.</p>",
    "en": "Current execution is not confirmed.</p>"
  },
  "app.49ade5ea8e40": {
    "ru": "Подагент работал внутри родительского чата. ",
    "en": "The subagent worked within the parent chat. "
  },
  "app.ef305dc5b654": {
    "ru": "Историческая запись. ",
    "en": "Historical record. "
  },
  "app.97db5772d6db": {
    "ru": "Родительский чат участника задачи. ",
    "en": "The parent chat of a task participant. "
  },
  "app.478d22d3183f": {
    "ru": "<span class=\"caption\">Связи с задачами не зарегистрированы.</span>",
    "en": "<span class=\"caption\">No task links registered.</span>"
  },
  "app.9c024f69a3c3": {
    "ru": "<span class=\"caption\">Задачи в этом чате</span>",
    "en": "<span class=\"caption\">Tasks in this chat</span>"
  },
  "app.db61e197a956": {
    "ru": "<small>Участники: ",
    "en": "<small>Participants: "
  },
  "app.449c9836a77d": {
    "ru": "<small>Подагент",
    "en": "<small>Subagent"
  },
  "app.bf5423fe8102": {
    "ru": "Рабочая папка",
    "en": "Working directory"
  },
  "app.bae15d9c380b": {
    "ru": "Псевдоним",
    "en": "Nickname"
  },
  "app.7cdfa59e6f79": {
    "ru": "Путь агента",
    "en": "Agent path"
  },
  "app.76848548e29c": {
    "ru": "Нет данных",
    "en": "No data"
  },
  "app.b7e50daf5ad8": {
    "ru": "Время наблюдения",
    "en": "Observation time"
  },
  "app.9e8b5b2cf2ed": {
    "ru": "Последнее состояние",
    "en": "Latest status"
  },
  "app.044a08ad2434": {
    "ru": "Каталог Codex и события Hub",
    "en": "Codex catalog and Hub events"
  },
  "app.56e46960c104": {
    "ru": "Источник",
    "en": "Source"
  },
  "app.299c345725ff": {
    "ru": "ID чата",
    "en": "ID chats"
  },
  "app.b2e8508d15f0": {
    "ru": "\"><summary>Технические данные</summary><dl>",
    "en": "\"><summary>Technical details</summary><dl>"
  },
  "app.d1c36b299130": {
    "ru": "Менее минуты назад",
    "en": "Less than a minute ago"
  },
  "app.df43550f208b": {
    "ru": "Нет наблюдений",
    "en": "No observations"
  },
  "app.fd3e2fd84c00": {
    "ru": "{v0}<section class=\"git-repository-head\"><div><span class=\"caption\">Репозиторий</span><strong>{v1}</strong></div><div><span class=\"caption\">Ветка</span><strong>{v2}</strong></div><div><span class=\"caption\">Состояние</span><strong class=\"{v3}\">{v4}</strong></div></section><section class=\"git-kpis\"><div><span>Затронуто задач</span><strong>{v5}</strong></div><div><span>Локальные файлы</span><strong>{v6}</strong></div><div><span>Commit-ов</span><strong>{v7}</strong></div><div><span>Синхронизация</span><strong>{v8}</strong><small>{v9}</small></div></section><section class=\"git-section\"><div class=\"section-head\"><h2>Изменения по задачам</h2><span class=\"caption\">Только сводка, без diff и полного списка файлов</span></div><div class=\"git-task-list\">{v10}</div>{v11}</section><section class=\"git-section\"><div class=\"section-head\"><h2>Последние commit</h2><span class=\"caption\">Привязка берётся из Project Hub trailers</span></div><div class=\"git-commit-list\">{v12}</div></section><section class=\"git-section\"><div class=\"section-head\"><h2>Последние push</h2></div><div class=\"git-commit-list\">{v13}</div></section>",
    "en": "{v0}<section class=\"git-repository-head\"><div><span class=\"caption\">Repository</span><strong>{v1}</strong></div><div><span class=\"caption\">Branch</span><strong>{v2}</strong></div><div><span class=\"caption\">Status</span><strong class=\"{v3}\">{v4}</strong></div></section><section class=\"git-kpis\"><div><span>Tasks affected</span><strong>{v5}</strong></div><div><span>Local files</span><strong>{v6}</strong></div><div><span>commits</span><strong>{v7}</strong></div><div><span>Synchronization</span><strong>{v8}</strong><small>{v9}</small></div></section><section class=\"git-section\"><div class=\"section-head\"><h2>Changes by task</h2><span class=\"caption\">Summary only, without a diff or full file list</span></div><div class=\"git-task-list\">{v10}</div>{v11}</section><section class=\"git-section\"><div class=\"section-head\"><h2>Recent commits</h2><span class=\"caption\">Links come from Project Hub trailers</span></div><div class=\"git-commit-list\">{v12}</div></section><section class=\"git-section\"><div class=\"section-head\"><h2>Recent pushes</h2></div><div class=\"git-commit-list\">{v13}</div></section>"
  },
  "app.b3e5d6cb14bf": {
    "ru": "Состояние репозитория в терминах задач и их изменений.",
    "en": "Repository status in terms of tasks and their changes."
  },
  "app.de5da87fcdc5": {
    "ru": "Контроль версий",
    "en": "Version control"
  },
  "app.62b4ba5080df": {
    "ru": "Чисто",
    "en": "Clean"
  },
  "app.b1364c306301": {
    "ru": "Есть изменения",
    "en": "Has changes"
  },
  "app.b720b25482d6": {
    "ru": "upstream не задан",
    "en": "upstream not set"
  },
  "app.a0c5c733407a": {
    "ru": "впереди / позади",
    "en": "ahead / behind"
  },
  "app.3dc796f8bc4d": {
    "ru": "<div class=\"empty\">Нет изменений, однозначно связанных с задачами.</div>",
    "en": "<div class=\"empty\">No changes unambiguously linked to tasks.</div>"
  },
  "app.8a93262b7e96": {
    "ru": "<div class=\"empty\">Push-события появятся после записи push в журнал Project Hub.</div>",
    "en": "<div class=\"empty\">Push-events will appear after the push is recorded in the Project Hub log.</div>"
  },
  "app.0302a26a55bd": {
    "ru": "Push записан в журнал",
    "en": "Push logged"
  },
  "app.1fb78a04ea9e": {
    "ru": "<div class=\"empty\">Commit-ов пока нет.</div>",
    "en": "<div class=\"empty\">No commits yet.</div>"
  },
  "app.4a7a419f9e98": {
    "ru": "<div class=\"git-unassigned-panel\"><strong>Без однозначной привязки</strong><span>{v0} локал. файлов · {v1} неоднозначных · {v2} commit</span></div>",
    "en": "<div class=\"git-unassigned-panel\"><strong>No unambiguous link</strong><span>{v0} local files · {v1} ambiguous · {v2} commit</span></div>"
  },
  "app.c5f5c695e20b": {
    "ru": "<a class=\"git-task-row\" href=\"{v0}\"><strong>{v1}</strong><span>{v2}</span><span>{v3} локал. · {v4} в commit</span><span>{v5} commit</span><span>{v6}</span></a>",
    "en": "<a class=\"git-task-row\" href=\"{v0}\"><strong>{v1}</strong><span>{v2}</span><span>{v3} local · {v4} in commit</span><span>{v5} commit</span><span>{v6}</span></a>"
  },
  "app.c7951fd569fc": {
    "ru": "Изменения",
    "en": "Changes"
  },
  "app.84fb6f4571ba": {
    "ru": "Смешанное",
    "en": "Mixed"
  },
  "app.ca5510a1d6eb": {
    "ru": "Есть commit",
    "en": "Has a commit"
  },
  "app.cc4b566d3740": {
    "ru": "Незакомичено",
    "en": "Uncommitted"
  },
  "app.ff1e06390a03": {
    "ru": "<button class=\"icon-button\" type=\"button\" data-git-push title=\"Отправить push…\" aria-label=\"Отправить push…\">{v0}</button>",
    "en": "<button class=\"icon-button\" type=\"button\" data-git-push title=\"Push…\" aria-label=\"Push…\">{v0}</button>"
  },
  "app.c3d002eb262e": {
    "ru": "<span>Remote не задан</span>",
    "en": "<span>Remote not set</span>"
  },
  "app.a932dbaeb95e": {
    "ru": "<a href=\"{v0}\" target=\"_blank\" rel=\"noopener\">Репозиторий</a> · <a href=\"{v1}\" target=\"_blank\" rel=\"noopener\">Ветка</a> · <a href=\"{v2}\" target=\"_blank\" rel=\"noopener\">Сравнить</a>",
    "en": "<a href=\"{v0}\" target=\"_blank\" rel=\"noopener\">Repository</a> · <a href=\"{v1}\" target=\"_blank\" rel=\"noopener\">Branch</a> · <a href=\"{v2}\" target=\"_blank\" rel=\"noopener\">Compare</a>"
  },
  "app.00b50534ae90": {
    "ru": "Репозиторий не найден",
    "en": "Repository not found"
  },
  "app.91582e6e3be6": {
    "ru": "Состояние контроля версий недоступно",
    "en": "Version control status unavailable"
  },
  "app.a2ee2c776fb8": {
    "ru": "Получение данных Git…",
    "en": "Retrieving Git data…"
  },
  "app.8f22932473df": {
    "ru": "Загрузка сводки репозитория…",
    "en": "Loading repository summary…"
  },
  "app.34ac78100648": {
    "ru": "Не удалось загрузить сводку",
    "en": "Could not load summary"
  },
  "app.66370ad36c08": {
    "ru": "<article class=\"git-commit-row\"><div>{v0}<strong>{v1}</strong></div><div class=\"git-commit-meta\">{v2}<span>{v3} файлов</span><time datetime=\"{v4}\">{v5}</time></div></article>",
    "en": "<article class=\"git-commit-row\"><div>{v0}<strong>{v1}</strong></div><div class=\"git-commit-meta\">{v2}<span>{v3} files</span><time datetime=\"{v4}\">{v5}</time></div></article>"
  },
  "app.933714518c05": {
    "ru": "Без сообщения",
    "en": "No message"
  },
  "app.2a3f3aa25255": {
    "ru": "<span class=\"git-unassigned\">Не привязан к задаче</span>",
    "en": "<span class=\"git-unassigned\">Not linked to a task</span>"
  },
  "app.8a49d0c13b78": {
    "ru": "Чат без названия",
    "en": "Untitled chat"
  },
  "app.8464cc3fafc9": {
    "ru": "{v0}<div class=\"panel\">{v1}</div><div class=\"notice\">В текущей версии агент публикует события и результаты через локальный CLI. Браузер показывает данные и не выполняет произвольные команды.</div><div class=\"section-head\"><h2>Как обновляется портал сейчас</h2></div><div class=\"panel flow\"><div class=\"flow-row\"><div class=\"flow-box\"><strong>Агент / запуск проверки</strong><small>Фактические действия и результаты</small></div><div class=\"flow-box\"><strong>Журнал проекта</strong><small>События, устойчивые ID и история</small></div><div class=\"flow-box\"><strong>Локальный сервер → браузер</strong><small>Живое обновление и повторное подключение</small></div></div></div>",
    "en": "{v0}<div class=\"panel\">{v1}</div><div class=\"notice\">In the current version, the agent publishes events and results through the local CLI. The browser displays data and does not run arbitrary commands.</div><div class=\"section-head\"><h2>How the portal updates now</h2></div><div class=\"panel flow\"><div class=\"flow-row\"><div class=\"flow-box\"><strong>Agent / check run</strong><small>Actual actions and results</small></div><div class=\"flow-box\"><strong>Project journal</strong><small>Events, stable IDs and history</small></div><div class=\"flow-box\"><strong>Local server → browser</strong><small>Live updates and reconnection</small></div></div></div>"
  },
  "app.234adb420762": {
    "ru": "Место для будущих интерактивных операций. Выполнение команд из браузера в этой версии не подключено.",
    "en": "A place for future interactive operations. Running commands from the browser is not connected in this version."
  },
  "app.9c41ac662be1": {
    "ru": "Действия проекта",
    "en": "Project actions"
  },
  "app.a4bba03c40fd": {
    "ru": "Управление",
    "en": "Management"
  },
  "app.80e122233d5a": {
    "ru": "<div class=\"action-preview\"><div><h3>{v0}</h3><p>{v1}</p></div><button class=\"icon-button\" disabled title=\"Позже\" aria-label=\"Позже\">{v2}</button></div>",
    "en": "<div class=\"action-preview\"><div><h3>{v0}</h3><p>{v1}</p></div><button class=\"icon-button\" disabled title=\"Later\" aria-label=\"Later\">{v2}</button></div>"
  },
  "app.e82189af28a3": {
    "ru": "Повторяемые операции проекта через общий реестр команд.",
    "en": "Repeatable project operations through the shared command registry."
  },
  "app.e5c674ba8ff7": {
    "ru": "Выполнить сценарий",
    "en": "Run a scenario"
  },
  "app.891223f260fb": {
    "ru": "Задание агенту с контекстом проекта, выбранной задачей и критериями результата.",
    "en": "An assignment for the agent with project context, the selected task and result criteria."
  },
  "app.e5cec66ced55": {
    "ru": "Поручить рутинную операцию",
    "en": "Assign a routine operation"
  },
  "app.838cced7716a": {
    "ru": "Конфигурация, параметры, состояние выполнения и журнал результата.",
    "en": "Configuration, parameters, execution status and result log."
  },
  "app.f0be314fc4e4": {
    "ru": "Запустить проверку",
    "en": "Run a check"
  },
  "app.49a07b4ad542": {
    "ru": "<div class=\"notice\">Не удалось загрузить интерфейс документации. Обновите страницу.</div>",
    "en": "<div class=\"notice\">Could not load the documentation interface. Refresh the page.</div>"
  },
  "app.07f3a94e18f6": {
    "ru": "<article class=\"future-item\"><h3>{v0}</h3><p>{v1}</p><small>{v2} · следующий этап</small></article>",
    "en": "<article class=\"future-item\"><h3>{v0}</h3><p>{v1}</p><small>{v2} · next stage</small></article>"
  },
  "app.de55e0ce203b": {
    "ru": "<div class=\"notice\">Не удалось загрузить интерфейс архитектуры. Обновите страницу.</div>",
    "en": "<div class=\"notice\">Could not load the architecture interface. Refresh the page.</div>"
  },
  "app.8b9f32ff1d0c": {
    "ru": "История не загрузилась: ",
    "en": "Could not load history: "
  },
  "app.9e7ac0d3c378": {
    "ru": "<div class=\"empty\">Нет событий выбранного типа на загруженной странице.</div>",
    "en": "<div class=\"empty\">No events of the selected type on the loaded page.</div>"
  },
  "app.cb52ad320244": {
    "ru": "<div class=\"history-loading\" role=\"status\" aria-live=\"polite\">{v0}<span>Загрузка истории разработки…</span></div>",
    "en": "<div class=\"history-loading\" role=\"status\" aria-live=\"polite\">{v0}<span>Loading development history…</span></div>"
  },
  "app.ee76f1e88f14": {
    "ru": "{v0}<div class=\"toolbar\"><select id=\"history-task\" aria-label=\"Задача\"><option value=\"\">Все задачи</option>{v1}</select><select id=\"history-kind\" aria-label=\"Тип события\"><option value=\"\">Все события</option><option value=\"task\" {v2}>Изменения задач</option><option value=\"check\" {v3}>Проверки</option><option value=\"decision\" {v4}>Решения</option><option value=\"finding\" {v5}>Наблюдения</option><option value=\"git\" {v6}>Git</option></select><span class=\"caption\">Всего событий в ленте: {v7}</span></div><div id=\"history-list\">{v8}</div><button class=\"icon-button\" id=\"history-more\" title=\"Более ранние события\" aria-label=\"Более ранние события\" {v9}>{v10}</button><div class=\"notice\">Более ранняя документация ещё не перенесена. Её импорт сохранит исходные даты, происхождение и отметку актуальности; он не будет выдавать старые записи за новые события.</div>",
    "en": "{v0}<div class=\"toolbar\"><select id=\"history-task\" aria-label=\"Task\"><option value=\"\">All tasks</option>{v1}</select><select id=\"history-kind\" aria-label=\"Event type\"><option value=\"\">All events</option><option value=\"task\" {v2}>Task changes</option><option value=\"check\" {v3}>Checks</option><option value=\"decision\" {v4}>Decisions</option><option value=\"finding\" {v5}>Observations</option><option value=\"git\" {v6}>Git</option></select><span class=\"caption\">Total events in feed: {v7}</span></div><div id=\"history-list\">{v8}</div><button class=\"icon-button\" id=\"history-more\" title=\"Earlier events\" aria-label=\"Earlier events\" {v9}>{v10}</button><div class=\"notice\">Earlier documentation has not been imported yet. Its import will preserve original dates, provenance, and freshness markers; it will not present old records as new events.</div>"
  },
  "app.8a7fe9bd38e0": {
    "ru": "События сохраняются между сессиями. Время ниже — время записи в журнал, с локальным часовым поясом браузера.",
    "en": "Events persist between sessions. Times below are journal entry times in the browser's local time zone."
  },
  "app.5143a08843c2": {
    "ru": "История разработки",
    "en": "Development history"
  },
  "app.4611f243b206": {
    "ru": "Журнал проекта",
    "en": "Project journal"
  },
  "app.ef21c3b741ba": {
    "ru": "<section class=\"panel stage-detail\"><div class=\"title-row\"><h2>{v0}</h2></div><div class=\"stage-detail-actions\">{v1}{v2}<button class=\"icon-button\" data-edit-stage=\"{v3}\" data-task-id=\"{v4}\" title=\"Редактировать этап\" aria-label=\"Редактировать этап\">{v5}</button><button class=\"icon-button\" data-stage-operation=\"transfer\" data-task-id=\"{v6}\" data-stage-id=\"{v7}\" title=\"Перенести этап\" aria-label=\"Перенести этап\">{v8}</button><button class=\"icon-button\" data-stage-operation=\"unlink\" data-task-id=\"{v9}\" data-stage-id=\"{v10}\" title=\"Отвязать этап\" aria-label=\"Отвязать этап\">{v11}</button><button class=\"icon-button\" data-stage-operation=\"delete\" data-task-id=\"{v12}\" data-stage-id=\"{v13}\" title=\"Удалить этап из текущего плана, сохранив историю\" aria-label=\"Удалить этап\">{v14}</button></div><p>{v15}</p>{v16}{v17}{v18}{v19}{v20}{v21}<div class=\"detail-section\"><h3>Реализовано</h3>{v22}</div><div class=\"detail-section\"><h3>До завершения</h3>{v23}</div><div class=\"detail-section\"><h3>Доказательства и исходники</h3>{v24}</div>{v25}</section>",
    "en": "<section class=\"panel stage-detail\"><div class=\"title-row\"><h2>{v0}</h2></div><div class=\"stage-detail-actions\">{v1}{v2}<button class=\"icon-button\" data-edit-stage=\"{v3}\" data-task-id=\"{v4}\" title=\"Edit stage\" aria-label=\"Edit stage\">{v5}</button><button class=\"icon-button\" data-stage-operation=\"transfer\" data-task-id=\"{v6}\" data-stage-id=\"{v7}\" title=\"Transfer stage\" aria-label=\"Transfer stage\">{v8}</button><button class=\"icon-button\" data-stage-operation=\"unlink\" data-task-id=\"{v9}\" data-stage-id=\"{v10}\" title=\"Unlink stage\" aria-label=\"Unlink stage\">{v11}</button><button class=\"icon-button\" data-stage-operation=\"delete\" data-task-id=\"{v12}\" data-stage-id=\"{v13}\" title=\"Remove the stage from the current plan, preserving history\" aria-label=\"Delete stage\">{v14}</button></div><p>{v15}</p>{v16}{v17}{v18}{v19}{v20}{v21}<div class=\"detail-section\"><h3>Implemented</h3>{v22}</div><div class=\"detail-section\"><h3>Remaining</h3>{v23}</div><div class=\"detail-section\"><h3>Evidence and source files</h3>{v24}</div>{v25}</section>"
  },
  "app.499d700a4876": {
    "ru": "<div class=\"detail-section\"><h3>Зависит от</h3>{v0}<p class=\"caption\">Зависимости показывают порядок завершения; независимые части могут внедряться раньше.</p></div>",
    "en": "<div class=\"detail-section\"><h3>Blocked by</h3>{v0}<p class=\"caption\">Dependencies show completion order; independent parts can be implemented earlier.</p></div>"
  },
  "app.5a02cab07ff0": {
    "ru": "<p class=\"caption\">Результаты будут добавлены по мере проверки.</p>",
    "en": "<p class=\"caption\">Results will be added as they are verified.</p>"
  },
  "app.4ac9f6556887": {
    "ru": "{v0}<div class=\"task-top-actions\"><a class=\"back\" href=\"#tasks\">← Все задачи</a>{v1}<div class=\"task-page-status\">{v2}</div><div class=\"task-page-actions\">{v3}{v4}</div></div><div class=\"task-heading\">{v5}</div><div class=\"task-compact-summary\" aria-label=\"Сводка задачи\"><div class=\"summary-line\"><span>{v6} / {v7} элементов завершено · {v8}%</span><span>Создана: {v9}</span><span>Обновление: {v10}</span>{v11}</div>{v12}</div>{v13}{v14}{v15}<div class=\"task-controls-row\">{v16}<button class=\"icon-button\" data-edit-task=\"{v17}\" title=\"Редактировать задачу\" aria-label=\"Редактировать задачу\">{v18}</button>{v19}</div>{v20}<div class=\"tabs\" role=\"tablist\" aria-label=\"Содержание задачи\">{v21}</div>\n{v22}\n {v23}\n{v24}\n{v25}\n{v26}\n {v27}",
    "en": "{v0}<div class=\"task-top-actions\"><a class=\"back\" href=\"#tasks\">← All tasks</a>{v1}<div class=\"task-page-status\">{v2}</div><div class=\"task-page-actions\">{v3}{v4}</div></div><div class=\"task-heading\">{v5}</div><div class=\"task-compact-summary\" aria-label=\"Task summary\"><div class=\"summary-line\"><span>{v6} / {v7} items completed · {v8}%</span><span>Created: {v9}</span><span>Update: {v10}</span>{v11}</div>{v12}</div>{v13}{v14}{v15}<div class=\"task-controls-row\">{v16}<button class=\"icon-button\" data-edit-task=\"{v17}\" title=\"Edit task\" aria-label=\"Edit task\">{v18}</button>{v19}</div>{v20}<div class=\"tabs\" role=\"tablist\" aria-label=\"Task contents\">{v21}</div>\n{v22}\n {v23}\n{v24}\n{v25}\n{v26}\n {v27}"
  },
  "app.0ffa7950dd60": {
    "ru": "<button class=\"icon-button\" data-transfer-task=\"{v0}\" title=\"Перенести задачу в проект\" aria-label=\"Перенести в проект…\">{v1}</button>",
    "en": "<button class=\"icon-button\" data-transfer-task=\"{v0}\" title=\"Transfer task to project\" aria-label=\"Move to project…\">{v1}</button>"
  },
  "app.bedc429e0f61": {
    "ru": "Задача / ",
    "en": "Task / "
  },
  "app.131ce75c0d14": {
    "ru": "<section class=\"panel child-task-list\"><h2>Дочерние задачи</h2>{v0}</section>",
    "en": "<section class=\"panel child-task-list\"><h2>Child tasks</h2>{v0}</section>"
  },
  "app.080c85caded8": {
    "ru": "История задачи",
    "en": "Task history"
  },
  "app.eaf501117cbe": {
    "ru": "Объём и приёмка",
    "en": "Scope and acceptance"
  },
  "app.d3482ce5cf86": {
    "ru": "План и зависимости",
    "en": "Plan and dependencies"
  },
  "app.fdf6e2780c02": {
    "ru": "<div class=\"section-head\"><h2>Этапы</h2><button class=\"icon-button\" data-edit-stage=\"\" data-task-id=\"{v0}\" title=\"Добавить этап\" aria-label=\"Добавить этап\">{v1}</button></div><div class=\"task-layout\"><div><div class=\"panel stage-list\" data-scroll-key=\"task-stage-list\">{v2}</div><p class=\"caption\" style=\"margin-top:12px\">Этапы имеют разный объём. Полоска этапов показывает их состояние, а не процент затраченного времени.</p></div>{v3}</div>{v4}{v5}",
    "en": "<div class=\"section-head\"><h2>Stages</h2><button class=\"icon-button\" data-edit-stage=\"\" data-task-id=\"{v0}\" title=\"Add stage\" aria-label=\"Add stage\">{v1}</button></div><div class=\"task-layout\"><div><div class=\"panel stage-list\" data-scroll-key=\"task-stage-list\">{v2}</div><p class=\"caption\" style=\"margin-top:12px\">Stages have different scopes. The stage bar shows their state, not the percentage of time spent.</p></div>{v3}</div>{v4}{v5}"
  },
  "app.10ce6a1e0485": {
    "ru": "<div class=\"empty\">Этапы ещё не добавлены</div>",
    "en": "<div class=\"empty\">No stages have been added yet</div>"
  },
  "app.65862e59e21a": {
    "ru": "<div class=\"two-columns\"><section class=\"panel stage-detail\"><h2>Входит в задачу</h2><div class=\"detail-section\">{v0}</div><div class=\"detail-section\"><h3>Критерии завершения</h3>{v1}</div></section><section><h2>Отдельные будущие этапы</h2><div class=\"detail-section\">{v2}</div><div class=\"notice\">Эти пункты сохранены в плане развития, но не входят в критерии завершения текущей задачи.</div></section></div>",
    "en": "<div class=\"two-columns\"><section class=\"panel stage-detail\"><h2>Part of task</h2><div class=\"detail-section\">{v0}</div><div class=\"detail-section\"><h3>Completion criteria</h3>{v1}</div></section><section><h2>Separate future stages</h2><div class=\"detail-section\">{v2}</div><div class=\"notice\">These items are saved in the development plan but are not part of the current task's completion criteria.</div></section></div>"
  },
  "app.b0ecb4a83f13": {
    "ru": "<div id=\"task-history\" class=\"timeline\">{v0}</div><a href=\"#history/{v1}\">Открыть полную историю этой задачи →</a>",
    "en": "<div id=\"task-history\" class=\"timeline\">{v0}</div><a href=\"#history/{v1}\">Open this task's full history →</a>"
  },
  "app.c00e3f714250": {
    "ru": "<div class=\"empty\">В недавней ленте нет событий этой задачи. Полная история доступна по ссылке ниже.</div>",
    "en": "<div class=\"empty\">There are no recent events for this task. Full history is available through the link below.</div>"
  },
  "app.aa3c6e6c7b23": {
    "ru": "<div class=\"task-actions\"><button class=\"icon-button\" data-task-close=\"{v0}\" data-close-mode=\"manual\" title=\"Закрыть задачу\" aria-label=\"Закрыть задачу\">{v1}</button>{v2}</div>",
    "en": "<div class=\"task-actions\"><button class=\"icon-button\" data-task-close=\"{v0}\" data-close-mode=\"manual\" title=\"Close task\" aria-label=\"Close task\">{v1}</button>{v2}</div>"
  },
  "app.570b05a5bffa": {
    "ru": "<button class=\"icon-button\" data-task-close=\"{v0}\" data-close-mode=\"auto\" title=\"Закрыть после проверки завершения\" aria-label=\"Закрыть автоматически\">{v1}</button>",
    "en": "<button class=\"icon-button\" data-task-close=\"{v0}\" data-close-mode=\"auto\" title=\"Close after verifying completion\" aria-label=\"Close automatically\">{v1}</button>"
  },
  "app.61c9cc4e8502": {
    "ru": "<div class=\"task-actions\"><button class=\"icon-button\" data-task-reopen=\"{v0}\" title=\"Переоткрыть задачу\" aria-label=\"Переоткрыть задачу\">{v1}</button></div>",
    "en": "<div class=\"task-actions\"><button class=\"icon-button\" data-task-reopen=\"{v0}\" title=\"Reopen task\" aria-label=\"Reopen task\">{v1}</button></div>"
  },
  "app.2d6faffbb6c5": {
    "ru": "<span class=\"task-priority descendant {v0}\" title=\"Максимальный приоритет незавершённых потомков\">Потомки: {v1}</span>",
    "en": "<span class=\"task-priority descendant {v0}\" title=\"Highest priority among unfinished descendants\">Descendants: {v1}</span>"
  },
  "app.7c23346f735c": {
    "ru": "<div class=\"task-edit-controls\"><label><span>Тип</span><select data-task-edit=\"type\" data-task-id=\"{v0}\"><option value=\"task\" {v1}>Task</option><option value=\"bug\" {v2}>Bug</option><option value=\"epic\" {v3}>Epic</option></select></label><label><span>Приоритет</span><select data-task-edit=\"priority\" data-task-id=\"{v4}\"><option value=\"\" {v5}>Не задан</option>{v6}</select></label>{v7}</div>",
    "en": "<div class=\"task-edit-controls\"><label><span>Type</span><select data-task-edit=\"type\" data-task-id=\"{v0}\"><option value=\"task\" {v1}>Task</option><option value=\"bug\" {v2}>Bug</option><option value=\"epic\" {v3}>Epic</option></select></label><label><span>Priority</span><select data-task-edit=\"priority\" data-task-id=\"{v4}\"><option value=\"\" {v5}>Not set</option>{v6}</select></label>{v7}</div>"
  },
  "app.a897fcf89ee4": {
    "ru": "<section class=\"panel\" role=\"status\"><h1>Загрузка задачи…</h1>{v0}</section>",
    "en": "<section class=\"panel\" role=\"status\"><h1>Loading task…</h1>{v0}</section>"
  },
  "app.9735f335cac3": {
    "ru": "<p>Получаем полное описание и этапы.</p>",
    "en": "<p>Retrieving the full description and stages.</p>"
  },
  "app.b27f5d7fdd22": {
    "ru": "<p role=\"alert\">Не удалось загрузить подробности: {v0}</p><button type=\"button\" class=\"icon-button\" data-task-detail-retry=\"{v1}\" title=\"Повторить загрузку подробностей задачи\" aria-label=\"Повторить загрузку подробностей задачи\">Повторить</button>",
    "en": "<p role=\"alert\">Could not load details: {v0}</p><button type=\"button\" class=\"icon-button\" data-task-detail-retry=\"{v1}\" title=\"Retry loading task details\" aria-label=\"Retry loading task details\">Retry</button>"
  },
  "app.7868efec7dc2": {
    "ru": "Ссылка может относиться к другому проекту.",
    "en": "The link may refer to another project."
  },
  "app.52aff16cc8d3": {
    "ru": "Задача не найдена",
    "en": "Task not found"
  },
  "app.03cc1c2d5ac2": {
    "ru": "Задачи",
    "en": "Tasks"
  },
  "app.ca6479685a1e": {
    "ru": "<div class=\"parent-picker\" data-parent-picker data-task-id=\"{v0}\"><span class=\"parent-picker-label\">Родитель</span><button type=\"button\" class=\"parent-picker-trigger\" data-parent-picker-trigger aria-haspopup=\"listbox\" aria-expanded=\"false\"><span>{v1}</span>{v2}</button><div class=\"parent-picker-popover\" hidden><input type=\"search\" class=\"parent-picker-search\" data-parent-search placeholder=\"Поиск по названию, ID, описанию…\" aria-label=\"Поиск родительской задачи\"><div class=\"parent-picker-options\" role=\"listbox\" aria-label=\"Родительская задача\">{v3}</div></div></div>",
    "en": "<div class=\"parent-picker\" data-parent-picker data-task-id=\"{v0}\"><span class=\"parent-picker-label\">Parent</span><button type=\"button\" class=\"parent-picker-trigger\" data-parent-picker-trigger aria-haspopup=\"listbox\" aria-expanded=\"false\"><span>{v1}</span>{v2}</button><div class=\"parent-picker-popover\" hidden><input type=\"search\" class=\"parent-picker-search\" data-parent-search placeholder=\"Search by title, ID, or description…\" aria-label=\"Search parent task\"><div class=\"parent-picker-options\" role=\"listbox\" aria-label=\"Parent task\">{v3}</div></div></div>"
  },
  "app.53b1f18878b8": {
    "ru": "<p class=\"parent-picker-empty\">Ничего не найдено</p>",
    "en": "<p class=\"parent-picker-empty\">Nothing found</p>"
  },
  "app.f877c25535e8": {
    "ru": "Статус не задан",
    "en": "No status set"
  },
  "app.48c8ac6482ec": {
    "ru": "<button type=\"button\" class=\"parent-picker-option {v0}\" role=\"option\" aria-selected=\"{v1}\" data-parent-option data-parent-value=\"\"><span class=\"parent-picker-option-title\">Проект</span><span class=\"parent-picker-option-meta\">Верхний уровень проекта</span></button>",
    "en": "<button type=\"button\" class=\"parent-picker-option {v0}\" role=\"option\" aria-selected=\"{v1}\" data-parent-option data-parent-value=\"\"><span class=\"parent-picker-option-title\">Project</span><span class=\"parent-picker-option-meta\">Top level of the project</span></button>"
  },
  "app.437b587555eb": {
    "ru": "<div class=\"empty\">Задачи не найдены. Измените запрос или фильтр.</div>",
    "en": "<div class=\"empty\">No tasks found. Change the query or filter.</div>"
  },
  "app.0a43343e62ab": {
    "ru": "<p class=\"caption\" role=\"status\">Найдено задач: {v0}. Поиск по ID, описанию, области, критериям и всем этапам плана. Все слова запроса; содержимое вложенных файлов не включено.</p>",
    "en": "<p class=\"caption\" role=\"status\">Tasks found: {v0}. Search by ID, description, scope, criteria and all plan stages. All query words must match; attached file contents are not included.</p>"
  },
  "app.5b23ad899154": {
    "ru": "Этап: ",
    "en": "Stage: "
  },
  "app.5c47a3132778": {
    "ru": "Отложено",
    "en": "Deferred"
  },
  "app.08c7c879bcb9": {
    "ru": "Критерии",
    "en": "Criteria"
  },
  "app.ac6b4059b527": {
    "ru": "Область",
    "en": "Scope"
  },
  "app.b3680f2cba5f": {
    "ru": "Описание",
    "en": "Description"
  },
  "app.0918b4ba9268": {
    "ru": "Название",
    "en": "Title"
  },
  "app.aa18e745349f": {
    "ru": "{v0}<div class=\"task-filter-bar\"><input id=\"task-search\" aria-label=\"Поиск задач\" placeholder=\"Найти задачу…\" value=\"{v1}\"><label>Статус<select id=\"task-status-filter\" aria-label=\"Фильтр по статусу\">{v2}</select></label><label>Тип<select id=\"task-type-filter\" aria-label=\"Фильтр по типу\">{v3}</select></label><label>Приоритет<select id=\"task-priority-filter\" aria-label=\"Фильтр по приоритету\">{v4}</select></label><label>Сортировка<select id=\"task-list-sort\" aria-label=\"Сортировка задач\">{v5}</select></label></div><div id=\"task-results\">{v6}</div>",
    "en": "{v0}<div class=\"task-filter-bar\"><input id=\"task-search\" aria-label=\"Task search\" placeholder=\"Find a task…\" value=\"{v1}\"><label>Status<select id=\"task-status-filter\" aria-label=\"Filter by status\">{v2}</select></label><label>Type<select id=\"task-type-filter\" aria-label=\"Filter by type\">{v3}</select></label><label>Priority<select id=\"task-priority-filter\" aria-label=\"Filter by priority\">{v4}</select></label><label>Sorting<select id=\"task-list-sort\" aria-label=\"Task sorting\">{v5}</select></label></div><div id=\"task-results\">{v6}</div>"
  },
  "app.86e701904b93": {
    "ru": "<div class=\"task-list-tools\"><button class=\"icon-button\" data-create-task title=\"Создать задачу\" aria-label=\"Создать задачу\">{v0}</button>{v1}<button class=\"icon-button\" data-settings-action=\"personal-reset\" title=\"Вернуть настройки проекта\" aria-label=\"Вернуть настройки проекта\">{v2}</button></div>",
    "en": "<div class=\"task-list-tools\"><button class=\"icon-button\" data-create-task title=\"Create task\" aria-label=\"Create task\">{v0}</button>{v1}<button class=\"icon-button\" data-settings-action=\"personal-reset\" title=\"Restore project settings\" aria-label=\"Restore project settings\">{v2}</button></div>"
  },
  "app.5484cf6c55b2": {
    "ru": "Задачи проекта",
    "en": "Project tasks"
  },
  "app.0578705e28be": {
    "ru": "Планирование",
    "en": "Planning"
  },
  "app.2a013601f9a8": {
    "ru": "Все статусы",
    "en": "All statuses"
  },
  "app.d367c360b8c5": {
    "ru": "Настройки проекта",
    "en": "Project settings"
  },
  "app.19161353d3bf": {
    "ru": "Все типы",
    "en": "All types"
  },
  "app.c1c552a44eb7": {
    "ru": "Все приоритеты",
    "en": "All priorities"
  },
  "app.ca87c2180268": {
    "ru": "По названию",
    "en": "By title"
  },
  "app.f2932d892ad9": {
    "ru": "Сначала незавершённые",
    "en": "Incomplete first"
  },
  "app.682ade53d14c": {
    "ru": "По статусу",
    "en": "By status"
  },
  "app.8741673244ca": {
    "ru": "По приоритету",
    "en": "By priority"
  },
  "app.28c18c8dfd24": {
    "ru": "Недавно обновлённые",
    "en": "Recently updated"
  },
  "app.461c83c1bd68": {
    "ru": "По дате создания · старые",
    "en": "Created date · oldest"
  },
  "app.10d04c1c3b04": {
    "ru": "По дате создания · новые",
    "en": "Created date · newest"
  },
  "app.46b79febee8c": {
    "ru": "{v0}\n <div class=\"overview-grid\"><section><div class=\"section-head\"><div><h2>Текущие задачи<span class=\"count\">{v1}</span></h2>{v2}<label class=\"sort-control\">Сортировка <select id=\"overview-task-sort\" aria-label=\"Сортировка задач\"><option value=\"created\" {v3}>По дате создания · новые</option><option value=\"created-oldest\" {v4}>По дате создания · старые</option><option value=\"priority\" {v5}>По приоритету</option><option value=\"updated\" {v6}>Недавно обновлённые</option><option value=\"status\" {v7}>По статусу</option><option value=\"progress\" {v8}>Сначала незавершённые</option><option value=\"title\" {v9}>По названию</option></select></label></div><a href=\"#tasks\">Все задачи →</a></div>{v10}<div class=\"notice\">Показан подтверждённый срез текущей работы. История портала накапливается с его запуска; более ранние документы будут импортированы отдельно.</div></section><div class=\"overview-sidebar\">\n <section class=\"panel plan-summary\"><div class=\"eyebrow\">Основная задача</div><h3>{v11}</h3>{v12}</section>\n {v13}\n <section><div class=\"section-head\"><h2>Последние события</h2><a href=\"#history\">Вся история →</a></div><div class=\"timeline\">{v14}</div></section></div></div>\n <div class=\"project-reserve\"><div><h3>Архитектура и код</h3><p>Системы, контракты, зависимости и связи классов.</p><a href=\"#architecture\">Структура будущего раздела →</a></div><div><h3>База знаний</h3><p>Руководства, справочник и исторические документы.</p><a href=\"#docs\">Структура документации →</a></div><div><h3>Действия проекта</h3><p>В будущем — запуски, команды и взаимодействие с агентом.</p><a href=\"#actions\">Предусмотренные расширения →</a></div></div>",
    "en": "{v0}\n <div class=\"overview-grid\"><section><div class=\"section-head\"><div><h2>Current tasks<span class=\"count\">{v1}</span></h2>{v2}<label class=\"sort-control\">Sorting <select id=\"overview-task-sort\" aria-label=\"Task sorting\"><option value=\"created\" {v3}>Created date · newest</option><option value=\"created-oldest\" {v4}>Created date · oldest</option><option value=\"priority\" {v5}>By priority</option><option value=\"updated\" {v6}>Recently updated</option><option value=\"status\" {v7}>By status</option><option value=\"progress\" {v8}>Incomplete first</option><option value=\"title\" {v9}>By title</option></select></label></div><a href=\"#tasks\">All tasks →</a></div>{v10}<div class=\"notice\">A confirmed snapshot of current work is shown. Portal history accumulates from the time it starts; earlier documents will be imported separately.</div></section><div class=\"overview-sidebar\">\n <section class=\"panel plan-summary\"><div class=\"eyebrow\">Primary task</div><h3>{v11}</h3>{v12}</section>\n {v13}\n <section><div class=\"section-head\"><h2>Recent events</h2><a href=\"#history\">Full history →</a></div><div class=\"timeline\">{v14}</div></section></div></div>\n <div class=\"project-reserve\"><div><h3>Architecture and code</h3><p>Systems, contracts, dependencies, and class relationships.</p><a href=\"#architecture\">Future section structure →</a></div><div><h3>Knowledge base</h3><p>Guides, reference material, and historical documents.</p><a href=\"#docs\">Documentation structure →</a></div><div><h3>Project actions</h3><p>Future support for runs, commands, and agent interaction.</p><a href=\"#actions\">Planned extensions →</a></div></div>"
  },
  "app.6c2c55068dc1": {
    "ru": "<span class=\"tag\">В работе: {v0}</span>",
    "en": "<span class=\"tag\">In progress: {v0}</span>"
  },
  "app.c0f072552cf6": {
    "ru": "Разработка, решения и знания о проекте — в одном месте.",
    "en": "Development, decisions and project knowledge in one place."
  },
  "app.2590606ceb11": {
    "ru": "Рабочее пространство",
    "en": "Workspace"
  },
  "app.eaab2ce5041f": {
    "ru": "<div class=\"empty\">Нет текущих задач для отображения</div>",
    "en": "<div class=\"empty\">No current tasks to display</div>"
  },
  "app.f6cf7d01e1ae": {
    "ru": "Основная задача не выбрана",
    "en": "No primary task selected"
  },
  "app.f883aa0850f0": {
    "ru": "<p class=\"caption\">Нет выбранной основной задачи.</p>",
    "en": "<p class=\"caption\">No primary task selected.</p>"
  },
  "app.ffa198e57505": {
    "ru": "<div class=\"empty\">История начинается с первого события</div>",
    "en": "<div class=\"empty\">History starts with the first event</div>"
  },
  "app.51365a4d6fe9": {
    "ru": "Единственная активная задача",
    "en": "The only active task"
  },
  "app.366564006f8e": {
    "ru": "Последняя обновлённая активная задача",
    "en": "Most recently updated active task"
  },
  "app.edde0234660c": {
    "ru": "Самая объёмная из активных задач",
    "en": "Largest active task"
  },
  "app.114112ae6abc": {
    "ru": "Выбрана явно",
    "en": "Explicitly selected"
  },
  "app.e271550457e6": {
    "ru": "<section class=\"panel now-panel\"><div class=\"label\"><i class=\"dot\"></i>ТЕКУЩАЯ РАБОТА{v0}</div>{v1}<div class=\"bottom\"><a href=\"#coordination\">Чаты и агенты →</a><span class=\"activity-note\">По состоянию подключённых чатов</span></div></section>",
    "en": "<section class=\"panel now-panel\"><div class=\"label\"><i class=\"dot\"></i>CURRENT WORK{v0}</div>{v1}<div class=\"bottom\"><a href=\"#coordination\">Chats and agents →</a><span class=\"activity-note\">Based on connected chat status</span></div></section>"
  },
  "app.c74fc1c0104d": {
    "ru": "<span class=\"activity-note\">Задач: {v0} · чатов: {v1}</span>",
    "en": "<span class=\"activity-note\">Tasks: {v0} · chats: {v1}</span>"
  },
  "app.2403bb98af36": {
    "ru": "<p class=\"caption\">Нет подтверждённой активной работы чатов.</p>",
    "en": "<p class=\"caption\">No confirmed active work in chats.</p>"
  },
  "app.b3690325224c": {
    "ru": "<span class=\"current-work-stage\">Работа по задаче</span>",
    "en": "<span class=\"current-work-stage\">Work on the task</span>"
  },
  "app.e56a412d1285": {
    "ru": "Проверка",
    "en": "Verifying"
  },
  "app.7a1b4177b276": {
    "ru": "Реализация",
    "en": "Implementation"
  },
  "app.04c325ed529c": {
    "ru": "Исследование",
    "en": "Exploration"
  },
  "app.cbc7a8f88a5e": {"ru":"<div class=\"task-estimate {v0}\"><div class=\"estimate-metrics\"><div><span class=\"estimate-label\">Готовность</span>{v1}</div><div><span class=\"estimate-label\">Осталось времени агента</span>{v2}</div></div>{v3}<div class=\"estimate-freshness {v4}\">{v5}{v6}{v7}</div>{v8}</div>","en":"<div class=\"task-estimate {v0}\"><div class=\"estimate-metrics\"><div><span class=\"estimate-label\">Completion</span>{v1}</div><div><span class=\"estimate-label\">Agent time remaining</span>{v2}</div></div>{v3}<div class=\"estimate-freshness {v4}\">{v5}{v6}{v7}</div>{v8}</div>"},
  "app.7f3ad0d70ecc": {
    "ru": "<span class=\"caption\">Оценка не задана</span>",
    "en": "<span class=\"caption\">No estimate set</span>"
  },
  "app.00e976f55b2f": {
    "ru": "<strong class=\"estimate-hours\">{v0}–{v1} ч</strong>",
    "en": "<strong class=\"estimate-hours\">{v0}–{v1} h</strong>"
  },
  "app.b552faeabe19": {
    "ru": "<div class=\"range-bar\" aria-label=\"Готовность: {v0}–{v1} процентов\"><div class=\"minimum\" style=\"width:{v2}%\"></div><div class=\"uncertain\" style=\"left:{v3}%;width:{v4}%\"></div></div>",
    "en": "<div class=\"range-bar\" aria-label=\"Completion: {v0}–{v1} percent\"><div class=\"minimum\" style=\"width:{v2}%\"></div><div class=\"uncertain\" style=\"left:{v3}%;width:{v4}%\"></div></div>"
  },
  "app.9eb3d9887d5b": {
    "ru": "Время —",
    "en": "Time —"
  },
  "app.2b90608b8714": {
    "ru": "<strong>{v0}–{v1} ч</strong> осталось",
    "en": "<strong>{v0}–{v1} h</strong> remaining"
  },
  "app.d6fc97062e95": {
    "ru": "Готовность —",
    "en": "Completion —"
  },
  "app.bafef38a3b64": {
    "ru": "не оценено",
    "en": "not estimated"
  },
  "app.602df55a0af1": {
    "ru": " часов",
    "en": " hours"
  },
  "app.f6263781b038": {
    "ru": "; осталось времени агента: ",
    "en": "; agent time remaining: "
  },
  "app.769f4277e4c8": {
    "ru": "не оценена",
    "en": "not assessed"
  },
  "app.85f3a836ee37": {
    "ru": "Готовность: ",
    "en": "Completion: "
  },
  "app.01559bfe41c1": {
    "ru": "Дата оценки неизвестна",
    "en": "Assessment date unknown"
  },
  "app.3e996c89b008": {
    "ru": "Оценка обновлена",
    "en": "Estimate updated"
  },
  "app.bffe6fd0018b": {
    "ru": "Оценка требует пересмотра",
    "en": "Estimate needs review"
  },
  "app.4cd44f4b1b09": {
    "ru": "Оценка не задана",
    "en": "No estimate set"
  },
  "app.0e21dc5dcf76": {
    "ru": "После периода работы",
    "en": "After a period of work"
  },
  "app.c1cda6c9dfbc": {
    "ru": "После изменения этапа",
    "en": "After a stage change"
  },
  "app.00e1cf7a6801": {
    "ru": "статус push неизвестен",
    "en": "push status unknown"
  },
  "app.a5560a64af44": {
    "ru": "локальный · не отправлен",
    "en": "local · not pushed"
  },
  "app.1ccc694277d6": {
    "ru": "отправлен",
    "en": "pushed"
  },
  "app.911177018aa6": {
    "ru": "<code title=\"Commit ещё не отправлен в upstream\">{v0}</code>",
    "en": "<code title=\"The commit has not been pushed to upstream\">{v0}</code>"
  },
  "app.df9579c56e2f": {
    "ru": "Не удалось выбрать основную задачу",
    "en": "Could not select the primary task"
  },
  "app.3895902b27df": {
    "ru": "Не удалось закрыть задачу",
    "en": "Could not close task"
  },
  "app.fecc63060e30": {
    "ru": "Закрыть задачу с возможными незавершёнными дочерними задачами?",
    "en": "Close the task with potentially unfinished child tasks?"
  },
  "app.f31562287bf9": {
    "ru": "Не удалось переоткрыть задачу",
    "en": "Could not reopen task"
  },
  "app.dbb0fe6eb358": {
    "ru": "Не удалось изменить родительскую задачу",
    "en": "Could not change parent task"
  },
  "app.e4f836fc9377": {
    "ru": "Не удалось скопировать. Разрешите доступ к буферу обмена в браузере и повторите.",
    "en": "Could not copy. Allow clipboard access in the browser and try again."
  },
  "app.d2d08c715ee6": {
    "ru": "Скопировано",
    "en": "Copied"
  },
  "app.f775d86e1ac7": {
    "ru": "<div class=\"copy-controls\">{v0}<div class=\"copy-menu\"><button class=\"icon-button copy-trigger\" type=\"button\" data-copy-default=\"{v1}\" aria-haspopup=\"menu\" aria-expanded=\"false\" aria-label=\"Скопировать данные\" title=\"Скопировать данные\">{v2}</button><div class=\"copy-menu-options\" role=\"menu\"><button type=\"button\" data-copy=\"{v3}\" role=\"menuitem\">Для чата</button><button type=\"button\" data-copy=\"{v4}\" role=\"menuitem\">Ссылку</button><button type=\"button\" data-copy=\"{v5}\" role=\"menuitem\">ID</button></div></div></div>",
    "en": "<div class=\"copy-controls\">{v0}<div class=\"copy-menu\"><button class=\"icon-button copy-trigger\" type=\"button\" data-copy-default=\"{v1}\" aria-haspopup=\"menu\" aria-expanded=\"false\" aria-label=\"Copy data\" title=\"Copy data\">{v2}</button><div class=\"copy-menu-options\" role=\"menu\"><button type=\"button\" data-copy=\"{v3}\" role=\"menuitem\">For chat</button><button type=\"button\" data-copy=\"{v4}\" role=\"menuitem\">Link</button><button type=\"button\" data-copy=\"{v5}\" role=\"menuitem\">ID</button></div></div></div>"
  },
  "app.7f40a27567e9": {
    "ru": "Сделать основной задачей",
    "en": "Make primary task"
  },
  "app.271f8d3a3d4e": {
    "ru": "Основная задача",
    "en": "Primary task"
  },
  "app.8c88e727623c": {
    "ru": "<article class=\"task-card panel{v0}\">{v1}<div class=\"task-card-titlebar\"><div class=\"task-card-heading\"><a href=\"{v2}\"><h3>{v3}</h3></a></div><div class=\"task-card-badges\"><div class=\"task-inline-meta\"><span class=\"task-type\">{v4}</span>{v5}{v6}{v7}</div>{v8}</div><div class=\"task-card-actions\">{v9}</div></div><div class=\"task-card-body\"><p>{v10}</p>{v11}<div class=\"task-card-progress-row\"><div class=\"task-meta task-progress-metric\"><span>{v12} из {v13} элементов завершено · {v14}%</span><span class=\"card-dates\"><time title=\"Создана: {v15}\" datetime=\"{v16}\">Созд. {v17}</time><time title=\"Изменена: {v18}\" datetime=\"{v19}\">Изм. {v20}</time></span></div>{v21}</div></div></article>",
    "en": "<article class=\"task-card panel{v0}\">{v1}<div class=\"task-card-titlebar\"><div class=\"task-card-heading\"><a href=\"{v2}\"><h3>{v3}</h3></a></div><div class=\"task-card-badges\"><div class=\"task-inline-meta\"><span class=\"task-type\">{v4}</span>{v5}{v6}{v7}</div>{v8}</div><div class=\"task-card-actions\">{v9}</div></div><div class=\"task-card-body\"><p>{v10}</p>{v11}<div class=\"task-card-progress-row\"><div class=\"task-meta task-progress-metric\"><span>{v12} of {v13} items completed · {v14}%</span><span class=\"card-dates\"><time title=\"Created: {v15}\" datetime=\"{v16}\">Created {v17}</time><time title=\"Updated: {v18}\" datetime=\"{v19}\">Updated {v20}</time></span></div>{v21}</div></div></article>"
  },
  "app.8309546a5f0d": {
    "ru": "<span class=\"task-type\">{v0} дочерн.</span>",
    "en": "<span class=\"task-type\">{v0} children</span>"
  },
  "app.71062d4f854f": {
    "ru": "Развернуть дочерние задачи",
    "en": "Expand child tasks"
  },
  "app.dfaa7a9e8d3a": {
    "ru": "Свернуть дочерние задачи",
    "en": "Collapse child tasks"
  },
  "app.bb4b0f5b3375": {
    "ru": "<div class=\"stage-strip\" aria-label=\"{v0} из {v1} этапов завершено\">{v2}</div>",
    "en": "<div class=\"stage-strip\" aria-label=\"{v0} of {v1} stages completed\">{v2}</div>"
  },
  "app.83ff1b2cdd88": {
    "ru": "Не удалось повторить commit",
    "en": "Could not retry commit"
  },
  "app.74c071688440": {
    "ru": "Не удалось согласовать коммиты",
    "en": "Could not reconcile commits"
  },
  "app.ee7c2271562d": {
    "ru": "Проект изменён. Закройте окно и откройте его в нужном проекте.",
    "en": "The project changed. Close the window and reopen it in the desired project."
  },
  "app.8083fe90255f": {
    "ru": "Укажите причину согласования (от 1 до 1200 символов).",
    "en": "Enter the reason for reconciliation (1 to 1200 characters)."
  },
  "app.5d08d0030495": {
    "ru": "Укажите от 1 до 20 полных SHA: 40 или 64 шестнадцатеричных символа каждый.",
    "en": "Enter 1 to 20 full SHAs: 40 or 64 hexadecimal characters each."
  },
  "app.28f3a4d7214b": {
    "ru": "<form novalidate><header><h2>Согласовать существующие коммиты</h2><button type=\"button\" class=\"icon-button\" data-close title=\"Отмена\" aria-label=\"Отмена\">{v0}</button></header><div class=\"editor-fields\"><label class=\"edit-field\"><span>Полные SHA (1–20), от старого к новому, через пробел или новую строку</span><textarea name=\"commits\" rows=\"4\" required spellcheck=\"false\" aria-describedby=\"checkpoint-reconcile-error\"></textarea></label><label class=\"edit-field\"><span>Причина согласования</span><textarea name=\"reason\" rows=\"3\" required maxlength=\"1200\" aria-describedby=\"checkpoint-reconcile-error\"></textarea></label></div><p class=\"editor-error\" id=\"checkpoint-reconcile-error\" role=\"alert\"></p><footer><button type=\"submit\" class=\"icon-button\" title=\"Проверить и согласовать\" aria-label=\"Проверить и согласовать\">{v1}</button></footer></form>",
    "en": "<form novalidate><header><h2>Reconcile existing commits</h2><button type=\"button\" class=\"icon-button\" data-close title=\"Cancel\" aria-label=\"Cancel\">{v0}</button></header><div class=\"editor-fields\"><label class=\"edit-field\"><span>Full SHAs (1–20), from oldest to newest, separated by spaces or new lines</span><textarea name=\"commits\" rows=\"4\" required spellcheck=\"false\" aria-describedby=\"checkpoint-reconcile-error\"></textarea></label><label class=\"edit-field\"><span>Reason for reconciliation</span><textarea name=\"reason\" rows=\"3\" required maxlength=\"1200\" aria-describedby=\"checkpoint-reconcile-error\"></textarea></label></div><p class=\"editor-error\" id=\"checkpoint-reconcile-error\" role=\"alert\"></p><footer><button type=\"submit\" class=\"icon-button\" title=\"Verify and reconcile\" aria-label=\"Verify and reconcile\">{v1}</button></footer></form>"
  },
  "app.046f5286fcb5": {
    "ru": "Согласовать существующие коммиты",
    "en": "Reconcile existing commits"
  },
  "app.8baa6da45ae2": {
    "ru": "Проект изменился. Откройте сверку заново.",
    "en": "The project changed. Reopen reconciliation."
  },
  "app.00e950b20155": {
    "ru": "Не удалось прочитать принадлежность изменений",
    "en": "Could not read change attribution"
  },
  "app.70a54009db3d": {
    "ru": "<p>Записей: {v0} · changesets: {v1} · файлов: {v2}</p><p>Git HEAD: <code>{v3}</code></p><p>Кандидат: <code>{v4}</code></p><p>{v5}</p><div data-steps></div><button type=\"button\" data-more hidden>Показать ещё</button>",
    "en": "<p>Entries: {v0} · changesets: {v1} · files: {v2}</p><p>Git HEAD: <code>{v3}</code></p><p>Candidate: <code>{v4}</code></p><p>{v5}</p><div data-steps></div><button type=\"button\" data-more hidden>Show more</button>"
  },
  "app.6f70cfcf70c1": {
    "ru": "Кандидат подготовлен. Создайте commit с обычными hooks через Git, затем проверьте его SHA.",
    "en": "The candidate is ready. Create a commit with the usual Git hooks, then verify its SHA."
  },
  "app.c666e017c034": {
    "ru": "Содержимое commit и ancestry проверены. Зачёт сохранит исходные ID и историю.",
    "en": "Commit contents and ancestry were verified. Adoption will preserve the original IDs and history."
  },
  "app.ec84dd769ede": {
    "ru": "Выберите 1–20 записей, укажите основание и полный SHA при сверке commit.",
    "en": "Choose 1–20 records, provide the basis, and the full SHA when reviewing a commit."
  },
  "app.9276cf1aaaa6": {
    "ru": "<article><h3>{v0}</h3><p>{v1}</p><p>До: <code>{v2}</code> {v3}</p><p>После: <code>{v4}</code> {v5}</p><ul>{v6}</ul></article>",
    "en": "<article><h3>{v0}</h3><p>{v1}</p><p>Before: <code>{v2}</code> {v3}</p><p>After: <code>{v4}</code> {v5}</p><ul>{v6}</ul></article>"
  },
  "app.535119bf3cc5": {
    "ru": "Скачать",
    "en": "Download"
  },
  "app.622966d01aab": {
    "ru": " · текстовых правок: {v0}",
    "en": " · text changes: {v0}"
  },
  "app.473ea5a05435": {
    "ru": "Результат работы",
    "en": "Work result"
  },
  "app.fe3f7b8341dd": {
    "ru": "Исходная версия",
    "en": "Original version"
  },
  "app.a3920e8b6bb3": {
    "ru": "Файл отсутствует",
    "en": "File missing"
  },
  "app.977c4eb0e763": {
    "ru": "{v0} · {v1} байт · {v2}",
    "en": "{v0} · {v1} bytes · {v2}"
  },
  "app.3c91fdcbed40": {
    "ru": "Независимые текстовые правки",
    "en": "Independent text changes"
  },
  "app.2b931a8e72a1": {
    "ru": "Полная цепочка байтов",
    "en": "Complete byte chain"
  },
  "app.689e8ab88b93": {
    "ru": "Не удалось прочитать покрытие",
    "en": "Could not read coverage"
  },
  "app.1fedd22c3995": {
    "ru": "<form novalidate><header><h2>Сверка общего Git commit</h2><button type=\"button\" class=\"icon-button\" data-close aria-label=\"Отмена\" title=\"Отмена\">{v0}</button></header><div class=\"editor-fields\"><fieldset><legend>Связанные задачи и этапы (до 20)</legend>{v1}</fieldset><label class=\"edit-field\"><span>Полный SHA существующего commit (необязательно для подготовки кандидата)</span><input name=\"commit\" spellcheck=\"false\" maxlength=\"64\"></label><label class=\"edit-field\"><span>Основание принадлежности выбранных изменений</span><textarea name=\"reason\" rows=\"3\" maxlength=\"1200\" required></textarea></label><div data-review aria-live=\"polite\"></div></div><p class=\"editor-error\" role=\"alert\"></p><footer><button type=\"submit\">Предварительный просмотр</button><button type=\"button\" data-adopt disabled>Зачесть проверенное покрытие</button></footer></form>",
    "en": "<form novalidate><header><h2>Review shared Git commit</h2><button type=\"button\" class=\"icon-button\" data-close aria-label=\"Cancel\" title=\"Cancel\">{v0}</button></header><div class=\"editor-fields\"><fieldset><legend>Related tasks and stages (up to 20)</legend>{v1}</fieldset><label class=\"edit-field\"><span>Full SHA of an existing commit (optional when preparing a candidate)</span><input name=\"commit\" spellcheck=\"false\" maxlength=\"64\"></label><label class=\"edit-field\"><span>Basis for ownership of the selected changes</span><textarea name=\"reason\" rows=\"3\" maxlength=\"1200\" required></textarea></label><div data-review aria-live=\"polite\"></div></div><p class=\"editor-error\" role=\"alert\"></p><footer><button type=\"submit\">Preview</button><button type=\"button\" data-adopt disabled>Adopt verified coverage</button></footer></form>"
  },
  "app.c6ebf13052e8": {
    "ru": "Сверка общего Git commit",
    "en": "Review shared Git commit"
  },
  "app.202d8b0ba9dd": {
    "ru": "<button class=\"icon-button\" data-checkpoint-retry=\"{v0}\" data-checkpoint-stage=\"{v1}\" title=\"Повторить checkpoint\" aria-label=\"Повторить checkpoint\" {v2}>{v3}</button><button class=\"icon-button\" data-checkpoint-reconcile=\"{v4}\" data-checkpoint-stage=\"{v5}\" title=\"Согласовать существующие коммиты\" aria-label=\"Согласовать существующие коммиты\" {v6}>{v7}</button>",
    "en": "<button class=\"icon-button\" data-checkpoint-retry=\"{v0}\" data-checkpoint-stage=\"{v1}\" title=\"Retry checkpoint\" aria-label=\"Retry checkpoint\" {v2}>{v3}</button><button class=\"icon-button\" data-checkpoint-reconcile=\"{v4}\" data-checkpoint-stage=\"{v5}\" title=\"Reconcile existing commits\" aria-label=\"Reconcile existing commits\" {v6}>{v7}</button>"
  },
  "app.c9718a7f757e": {
    "ru": "Commit создан; требуется сверка покрытия",
    "en": "Commit created; coverage reconciliation required"
  },
  "app.4da313bdaf1b": {
    "ru": "Автоматические коммиты выключены",
    "en": "Automatic commits are disabled"
  },
  "app.2fbe37c6b688": {
    "ru": "Изменений для commit нет",
    "en": "There are no changes for a commit"
  },
  "app.62491cf7472e": {
    "ru": "Не удалось создать commit",
    "en": "Could not create commit"
  },
  "app.b8c18e728cfe": {
    "ru": "Commit ожидает выполнения",
    "en": "Commit awaiting execution"
  },
  "app.192b0a33be70": {
    "ru": "<div class=\"checkpoint-status\" role=\"status\"><span>{v0}</span><span class=\"checkpoint-reason\" title=\"{v1}\">{v2}</span><button class=\"icon-button\" data-checkpoint-retry=\"{v3}\" data-checkpoint-stage=\"{v4}\" title=\"Повторить публикацию метаданных\" aria-label=\"Повторить публикацию метаданных\" {v5}>{v6}</button></div>",
    "en": "<div class=\"checkpoint-status\" role=\"status\"><span>{v0}</span><span class=\"checkpoint-reason\" title=\"{v1}\">{v2}</span><button class=\"icon-button\" data-checkpoint-retry=\"{v3}\" data-checkpoint-stage=\"{v4}\" title=\"Retry metadata publication\" aria-label=\"Retry metadata publication\" {v5}>{v6}</button></div>"
  },
  "app.4dbbff2ba232": {
    "ru": "Результат Git ожидает публикации",
    "en": "Git result awaiting publication"
  },
  "app.dab03b62d573": {
    "ru": "Commit сохранён; метаданные ожидают публикации",
    "en": "Commit saved; metadata awaiting publication"
  },
  "app.aa2800795b9a": {
    "ru": "<button class=\"icon-button\" data-checkpoint-batch=\"{v0}\" data-checkpoint-stage=\"{v1}\" title=\"Просмотреть общий commit и связанные задачи\" aria-label=\"Сверить общий commit\">{v2}</button>",
    "en": "<button class=\"icon-button\" data-checkpoint-batch=\"{v0}\" data-checkpoint-stage=\"{v1}\" title=\"View shared commit and linked tasks\" aria-label=\"Reconcile shared commit\">{v2}</button>"
  },
  "app.4800516916e2": {
    "ru": "Ожидает проверки",
    "en": "Awaiting review"
  },
  "app.ce1001c5e410": {
    "ru": "Старая запись не содержит исходных байтов. Нужна отдельная сверка истории.",
    "en": "The legacy record has no original bytes. A separate history review is needed."
  },
  "app.fcb285883594": {
    "ru": "Завершите выбранные задачи и этапы перед сверкой.",
    "en": "Complete the selected tasks and stages before the review."
  },
  "app.61ad098f5abc": {
    "ru": "Дождитесь завершения текущей операции checkpoint.",
    "en": "Wait for the current checkpoint operation to finish."
  },
  "app.45af8687813d": {
    "ru": "Checkpoint уже имеет другое подтверждённое покрытие.",
    "en": "The checkpoint already has different confirmed coverage."
  },
  "app.7257774214bb": {
    "ru": "Проект изменился. Повторите предварительный просмотр.",
    "en": "The project changed. Run the preview again."
  },
  "app.ed0f7dfb04dd": {
    "ru": "Кандидат изменился. Повторите предварительный просмотр.",
    "en": "The candidate changed. Run the preview again."
  },
  "app.4c13d77e2a92": {
    "ru": "Родитель commit отличается от просмотренного кандидата.",
    "en": "The commit parent differs from the reviewed candidate."
  },
  "app.3b1798c79ea9": {
    "ru": "Изменения конфликтуют. Нужен явно разрешённый результат.",
    "en": "The changes conflict. An explicitly approved result is required."
  },
  "app.bbd6ca978695": {
    "ru": "Для исходных байтов не хватает подтверждённых изменений. Добавьте связанную работу или выполните отдельную сверку.",
    "en": "Confirmed changes for the original bytes are missing. Add related work or perform a separate review."
  },
  "app.fac7576116ea": {
    "ru": "Git использует преобразование содержимого. Нужен проверенный adapter.",
    "en": "Git uses content transformation. A verified adapter is required."
  },
  "app.cffac49d11c4": {
    "ru": "Заявленные изменения уже вошли в commit. Согласуйте подтверждённое покрытие.",
    "en": "The claimed changes are already in a commit. Reconcile the confirmed coverage."
  },
  "app.dc154b7add3e": {
    "ru": "HEAD изменился. Проверьте исходную границу и существующие коммиты.",
    "en": "HEAD changed. Check the original boundary and existing commits."
  },
  "app.02fa734016d0": {
    "ru": "В индексе уже есть staged изменения. Нужна ручная сверка.",
    "en": "The index already contains staged changes. A manual review is needed."
  },
  "app.a95f5932b1f3": {
    "ru": "Нет подтверждённой области изменений для автоматического commit.",
    "en": "There is no confirmed change scope for an automatic commit."
  },
  "app.ecdf0424ff95": {
    "ru": "Связанная работа ещё выполняется.",
    "en": "Related work is still running."
  },
  "app.70ac4d55a2cf": {
    "ru": "Файлы изменились во время чтения. Повторите проверку.",
    "en": "Files changed while reading. Run the check again."
  },
  "app.3f016922e801": {
    "ru": "HEAD или индекс изменился во время подготовки. Проверьте кандидат.",
    "en": "HEAD or the index changed during preparation. Check the candidate."
  },
  "app.94e03836b504": {
    "ru": "Результат сохранён; требуется повторить публикацию в Hub.",
    "en": "The result was saved; publication to Hub must be retried."
  },
  "app.4548f997188c": {
    "ru": "Операционная система отказала в доступе.",
    "en": "The operating system denied access."
  },
  "app.14749befde27": {
    "ru": "Старые и новые границы требуют отдельной сверки.",
    "en": "Old and new boundaries require a separate review."
  },
  "app.81c0105d30fa": {
    "ru": "Не хватает сохранённой границы содержимого для проверки.",
    "en": "The saved content boundary needed for verification is missing."
  },
  "app.beaf13a8004e": {
    "ru": "Исходные байты не прошли проверку целостности.",
    "en": "The original bytes failed the integrity check."
  },
  "app.9867b0726852": {
    "ru": "Сохранённые байты не прошли проверку целостности.",
    "en": "The saved bytes failed the integrity check."
  },
  "app.88d0bb2dfa56": {
    "ru": "Commit не подтверждает сохранённый результат работы.",
    "en": "The commit does not confirm the saved work result."
  },
  "app.fc6d5ee4c2d1": {
    "ru": "Содержимое кандидата отличается от завершённой работы. Commit остановлен.",
    "en": "The candidate content differs from the completed work. The commit was stopped."
  },
  "app.5186375d369d": {
    "ru": "Файлы изменились после завершения работы. Проверьте новый результат.",
    "en": "Files changed after work completed. Check the new result."
  },
  "app.bedd87cba2a8": {
    "ru": "Исходные байты отличаются от родителя commit. Нужна сверка содержимого.",
    "en": "The original bytes differ from the commit parent. The content must be reviewed."
  },
  "app.92e354422366": {
    "ru": "В исходных файлах уже были изменения. Нужна сверка их принадлежности.",
    "en": "The source files already had changes. Their ownership must be reviewed."
  },
  "app.dabc5839d2bc": {
    "ru": "Commit не создан",
    "en": "Commit was not created"
  },
  "app.a6d5837b3fd7": {
    "ru": "Git недоступен",
    "en": "Git unavailable"
  },
  "app.7281412dfc9c": {
    "ru": "{v0} файлов",
    "en": "{v0} files"
  },
  "app.5e4282c196d5": {
    "ru": "Локальный commit · статус push неизвестен",
    "en": "Local commit · push status unknown"
  },
  "app.06377ff3551e": {
    "ru": "Локальный commit · не отправлен",
    "en": "Local commit · not pushed"
  },
  "app.4b5140e1977e": {
    "ru": "Commit отправлен",
    "en": "Commit pushed"
  },
  "app.aa4211d27ae7": {
    "ru": "Нет открытых пунктов в этом этапе.",
    "en": "There are no open items in this stage."
  },
  "app.192d7b945ed0": {
    "ru": "Завершённых пунктов пока нет.",
    "en": "No items are completed yet."
  },
  "app.a2fd6a85723b": {
    "ru": "Недостаточно данных подключённых агентов для определения активности.",
    "en": "There is not enough data from connected agents to determine activity."
  },
  "app.a5ed711eb426": {
    "ru": "Нет активного исполнителя. Статус плана не изменён.",
    "en": "No active worker. The plan status was not changed."
  },
  "app.29069a39d68a": {
    "ru": "Активных чатов: {v0}. По последним событиям подключённых агентов.",
    "en": "Active chats: {v0}. Based on recent events from connected agents."
  },
  "app.05ece6ebda35": {
    "ru": "Агент ожидает",
    "en": "Agent is waiting"
  },
  "app.8dd65a3e6de6": {
    "ru": "Агент: нет данных",
    "en": "Agent: no data"
  },
  "app.44ee3fe42edd": {
    "ru": "Агент не работает",
    "en": "Agent is idle"
  },
  "app.36adf77adf8b": {
    "ru": "Агент работает",
    "en": "Agent is working"
  },
  "app.5e9ea2105d84": {
    "ru": " Необходимое действие: ",
    "en": " Required action: "
  },
  "app.51bad52ca4c2": {
    "ru": "<div class=\"notice blocker-detail\"><strong>{v0}</strong><p>Причина: {v1}</p><p>Необходимое действие: {v2}</p></div>",
    "en": "<div class=\"notice blocker-detail\"><strong>{v0}</strong><p>Reason: {v1}</p><p>Required action: {v2}</p></div>"
  },
  "app.a699469b575a": {
    "ru": "Уточнить причину и необходимое действие в записи задачи.",
    "en": "Clarify the reason and required action in the task record."
  },
  "app.60917697d591": {
    "ru": "Причина не указана.",
    "en": "No reason specified."
  },
  "app.067c4b855cc3": {
    "ru": "Проблема учёта",
    "en": "Bookkeeping issue"
  },
  "app.2ae8bedad7c9": {
    "ru": "Нужен ответ пользователя",
    "en": "User response needed"
  },
  "app.61d077d3515c": {
    "ru": "Техническое препятствие",
    "en": "Technical blocker"
  },
  "app.295bd5ba2d79": {
    "ru": "позже",
    "en": "later"
  },
  "app.cad123465b9e": {
    "ru": "Действия",
    "en": "Actions"
  },
  "app.b123be6f8236": {
    "ru": "Документация",
    "en": "Documentation"
  },
  "app.1898e1901dcd": {
    "ru": "Архитектура и код",
    "en": "Architecture and code"
  },
  "app.5029f02d0a94": {
    "ru": "Проекты",
    "en": "Projects"
  },
  "app.985b5e0f2ccf": {
    "ru": "Настройки",
    "en": "Settings"
  },
  "app.bb1b79b14c91": {
    "ru": "Проверки",
    "en": "Checks"
  },
  "app.7641ad9bafb2": {
    "ru": "Обзор проекта",
    "en": "Project overview"
  },
  "app.1d80e1757a7a": {
    "ru": "Запись",
    "en": "Note"
  },
  "app.199d6db958cd": {
    "ru": "Решение",
    "en": "Decision"
  },
  "app.574d43b44984": {
    "ru": "Наблюдение",
    "en": "Finding"
  },
  "app.adc4ed716c1a": {
    "ru": "Результат проверки исправлен",
    "en": "Check result corrected"
  },
  "app.09a8377bf26f": {
    "ru": "Результат проверки неизвестен",
    "en": "Check outcome unknown"
  },
  "app.aef23a5d2d28": {
    "ru": "Проверка прервана",
    "en": "Check interrupted"
  },
  "app.1cbcef8251cf": {
    "ru": "Проверка не прошла",
    "en": "Check failed"
  },
  "app.7a780b2ed19f": {
    "ru": "Проверка пройдена",
    "en": "Check passed"
  },
  "app.69faab6e6901": {
    "ru": "Проверка запущена",
    "en": "Check started"
  },
  "app.768257912b25": {
    "ru": "Шаг завершён",
    "en": "Work step completed"
  },
  "app.fd408eab202b": {
    "ru": "Работа начата",
    "en": "Work started"
  },
  "app.d9a99eebd8cb": {
    "ru": "Этап восстановлен",
    "en": "Stage restored"
  },
  "app.068026c33a92": {
    "ru": "Этап перенесён в задачу",
    "en": "Stage transferred into task"
  },
  "app.e12d195ff80e": {
    "ru": "Этап перенесён из задачи",
    "en": "Stage transferred out of task"
  },
  "app.cf4f5f8f1ec5": {
    "ru": "Этап перенесён",
    "en": "Stage transferred"
  },
  "app.6b48c0310af5": {
    "ru": "Этап отвязан",
    "en": "Stage unlinked"
  },
  "app.d4ec24da0fc5": {
    "ru": "Этап удалён из плана",
    "en": "Stage removed from plan"
  },
  "app.46b65269f9fa": {
    "ru": "Этап добавлен",
    "en": "Stage added"
  },
  "app.50a759ac4169": {
    "ru": "Этап обновлён",
    "en": "Stage updated"
  },
  "app.6e0b5dcf13c5": {
    "ru": "Связь задач удалена",
    "en": "Task link removed"
  },
  "app.9ae1d1f1c567": {
    "ru": "Задачи связаны",
    "en": "Tasks linked"
  },
  "app.1344d008de05": {
    "ru": "Изменён родитель задачи",
    "en": "Task parent changed"
  },
  "app.f72238b65172": {
    "ru": "Изменён приоритет задачи",
    "en": "Task priority changed"
  },
  "app.9f1fe6d24245": {
    "ru": "Изменён тип задачи",
    "en": "Task type changed"
  },
  "app.5e6ee4b48ff8": {
    "ru": "Изменён статус задачи",
    "en": "Task status changed"
  },
  "app.a2a4bf6e680e": {
    "ru": "Задача переоткрыта",
    "en": "Task reopened"
  },
  "app.taskClosed": {
    "ru": "Задача закрыта",
    "en": "Task closed"
  },
  "app.e97acacf9acf": {
    "ru": "Задача обновлена",
    "en": "Task updated"
  },
  "app.756c6c64e23e": {
    "ru": "Новая задача",
    "en": "Task created"
  },
  "app.32bb1c680f95": {
    "ru": "Сессия закрыта",
    "en": "Session closed"
  },
  "app.f7b2f77928af": {
    "ru": "Прерван",
    "en": "Interrupted"
  },
  "app.f4dff7d22ed4": {
    "ru": "Ответ завершён",
    "en": "Response complete"
  },
  "app.89c9e3a11aee": {
    "ru": "Ожидает",
    "en": "Waiting"
  },
  "app.bf22dfeeba8b": {
    "ru": "Ошибка",
    "en": "Failed"
  },
  "app.8cf46ff28cc1": {
    "ru": "Результат неизвестен",
    "en": "Outcome unknown"
  },
  "app.599ca07b8dd2": {
    "ru": "Выполняется",
    "en": "Running"
  },
  "app.be625a64f643": {
    "ru": "Пройдено",
    "en": "Passed"
  },
  "app.23a2a9bfcf74": {
    "ru": "Отменено",
    "en": "Cancelled"
  },
  "app.b459ff8f254e": {
    "ru": "Завершено",
    "en": "Completed"
  },
  "app.5db21586e6b5": {
    "ru": "Есть препятствие",
    "en": "Blocked"
  },
  "app.b22a2454bd69": {
    "ru": "В очереди",
    "en": "Queued"
  },
  "app.59a28f1b11df": {
    "ru": "В работе",
    "en": "In progress"
  },
  "app.4692f1b33927": {
    "ru": "Предстоит",
    "en": "Planned"
  },
  "architecture-map.044237bb788d": {
    "ru": "ELK: геометрия маршрута выходит за границы модели · ",
    "en": "ELK: route geometry exceeds the model bounds · "
  },
  "architecture-map.9784a23a2a03": {
    "ru": "ELK: не построен маршрут ",
    "en": "ELK: no route was built for "
  },
  "architecture-map.6e68361171c6": {
    "ru": "ELK не загружен",
    "en": "ELK did not load"
  },
  "architecture-map.e05bf0b073b1": {
    "ru": "<nav class=\"k-file-tree\" aria-label=\"Дерево исходников\">{v0}</nav>",
    "en": "<nav class=\"k-file-tree\" aria-label=\"Source tree\">{v0}</nav>"
  },
  "architecture-map.9da4e12912ef": {
    "ru": "<p class=\"k-empty\">Исходников в этом представлении нет.</p>",
    "en": "<p class=\"k-empty\">There is no source in this view.</p>"
  },
  "architecture-map.f9ec1711a797": {
    "ru": "<details data-k-file-folder=\"@non-files\"><summary>Компоненты и внешние типы</summary><div>{v0}</div></details>",
    "en": "<details data-k-file-folder=\"@non-files\"><summary>Components and external types</summary><div>{v0}</div></details>"
  },
  "architecture-map.646b8c230681": {
    "ru": "<button type=\"button\" class=\"k-file-more\" data-k-file-more=\"{v0}\" data-k-file-offset=\"{v1}\">Показать ещё ({v2})</button>",
    "en": "<button type=\"button\" class=\"k-file-more\" data-k-file-more=\"{v0}\" data-k-file-offset=\"{v1}\">Show more ({v2})</button>"
  },
  "architecture-map.8c4077fe995d": {
    "ru": "<small class=\"k-file-lazy\" data-k-file-lazy=\"{v0}\">Откройте папку для загрузки содержимого</small>",
    "en": "<small class=\"k-file-lazy\" data-k-file-lazy=\"{v0}\">Open the folder to load its contents</small>"
  },
  "architecture-map.b3a84f87fd83": {
    "ru": "компонент",
    "en": "component"
  },
  "architecture-map.9841fec2a184": {
    "ru": "внешний тип",
    "en": "external type"
  },
  "architecture-map.03d139991c66": {
    "ru": "интерфейс",
    "en": "interface"
  },
  "architecture-map.51cdccb8236d": {
    "ru": "класс",
    "en": "class"
  },
  "architecture-map.b00acac941e6": {
    "ru": "<nav class=\"k-architecture-tree\" aria-label=\"Дерево архитектуры\"><button class=\"k-tree-row\" data-k-tree-mode=\"overview\" data-k-tree-id=\"\">{v0}<span>Обзор проекта</span></button><h3>Подсистемы</h3>{v1}<h3>Точки входа</h3>{v2}<h3>Сценарии</h3>{v3}</nav>",
    "en": "<nav class=\"k-architecture-tree\" aria-label=\"Architecture tree\"><button class=\"k-tree-row\" data-k-tree-mode=\"overview\" data-k-tree-id=\"\">{v0}<span>Project overview</span></button><h3>Subsystems</h3>{v1}<h3>Entry points</h3>{v2}<h3>Scenarios</h3>{v3}</nav>"
  },
  "architecture-map.d3b6e144bd94": {
    "ru": "<p class=\"k-empty\">Компоненты пока не заданы.</p>",
    "en": "<p class=\"k-empty\">No components have been defined yet.</p>"
  },
  "architecture-map.df1338e4ab59": {
    "ru": "<small>Сканер не обнаружил точки входа.</small>",
    "en": "<small>The scanner found no entry points.</small>"
  },
  "architecture-map.1085e74899e5": {
    "ru": "<small>Сценариев пока нет.</small>",
    "en": "<small>There are no scenarios yet.</small>"
  },
  "architecture-map.cdf15ee8b7c8": {
    "ru": "Карта изменилась во время раскрытия. Повторите действие в текущем представлении.",
    "en": "The map changed while expanding. Repeat the action in the current view."
  },
  "architecture-map.4844531fbfed": {
    "ru": "Знания обновились. Обновите карту.",
    "en": "The knowledge changed. Refresh the map."
  },
  "architecture-map.6505c4b50881": {
    "ru": "Неполная страница связей: обновите карту.",
    "en": "The connection page is incomplete: refresh the map."
  },
  "architecture-map.5063fb21091b": {
    "ru": "Знания обновились во время раскрытия. Обновите карту.",
    "en": "The knowledge changed while expanding. Refresh the map."
  },
  "architecture-map.a90984e26197": {
    "ru": "Внешние типы",
    "en": "External types"
  },
  "architecture-map.9088ca9c0de9": {
    "ru": "Файлы",
    "en": "Files"
  },
  "architecture-map.8a89b9398cca": {
    "ru": "Интерфейсы",
    "en": "Interfaces"
  },
  "architecture-map.a860280b008e": {
    "ru": "Классы",
    "en": "Classes"
  },
  "architecture-map.9af957b361ca": {
    "ru": "Зависимости",
    "en": "Dependencies"
  },
  "architecture-map.2167fe553fee": {
    "ru": "Наследование",
    "en": "Inheritance"
  },
  "architecture-map.79e484b1f467": {
    "ru": "Все связи",
    "en": "All connections"
  },
  "architecture-map.816655bd716f": {
    "ru": "Структура",
    "en": "Structure"
  },
  "backup-status.d979148ac994": {
    "ru": "Изменения временно приостановлены до завершения снимка резервной копии.",
    "en": "Changes are temporarily paused until the backup snapshot is complete."
  },
  "backup-status.c76f945ec469": {
    "ru": "Выполняется операция резервного копирования: просмотр доступен, изменения временно приостановлены.",
    "en": "A backup operation is in progress: viewing is available, and changes are temporarily paused."
  },
  "backup-status.5410e6bc8748": {
    "ru": "Выполняется снимок резервной копии: просмотр доступен, изменения временно приостановлены.",
    "en": "A backup snapshot is in progress: viewing is available, and changes are temporarily paused."
  },
  "backups.247092300960": {
    "ru": "Создана отдельная неактивная копия ({v0} проектов): {v1}. Текущие данные не изменены.",
    "en": "A separate inactive copy was created ({v0} projects): {v1}. Current data was not changed."
  },
  "backups.3b6637a1159a": {
    "ru": "путь не указан",
    "en": "path not provided"
  },
  "backups.b90f3c9aaa87": {
    "ru": "Восстановление копии…",
    "en": "Restoring copy…"
  },
  "backups.7afce05be3dc": {
    "ru": "Будет создана отдельная неактивная копия. Текущие данные останутся без изменений. Продолжить?",
    "en": "A separate inactive copy will be created. Current data will remain unchanged. Continue?"
  },
  "backups.e90cecc2e2ac": {
    "ru": "Копия загружена и проверена.",
    "en": "Backup uploaded and verified."
  },
  "backups.e1db9d47f0fc": {
    "ru": "Загрузка копии…",
    "en": "Uploading backup…"
  },
  "backups.f3cdac14ba62": {
    "ru": "Создание копии…",
    "en": "Creating backup…"
  },
  "backups.9981620cf186": {
    "ru": "Сервер вернул некорректную позицию загрузки",
    "en": "The server returned an invalid upload offset"
  },
  "backups.bc926c10eea6": {
    "ru": "Операция завершилась с ошибкой",
    "en": "The operation failed"
  },
  "backups.ac6138440bed": {
    "ru": "Операция прервана",
    "en": "The operation was interrupted"
  },
  "backups.5445f25984ee": {
    "ru": "Загруженная копия",
    "en": "Uploaded backup"
  },
  "backups.c6a17769cc39": {
    "ru": "{v0}<section id=\"backups-page\" class=\"backups-page\" aria-label=\"Резервные копии всех проектов\"><div class=\"backup-panel-head\"><div><h2>Резервные копии</h2><p class=\"caption\">Копия включает данные всех проектов. Восстановление создаёт отдельную неактивную копию, текущие данные остаются без изменений.</p></div><button class=\"icon-button\" type=\"button\" data-backup-create title=\"Создать резервную копию\" aria-label=\"Создать резервную копию\">{v1}<span>Создать копию</span></button></div><p class=\"backup-status\" role=\"status\" data-backup-status></p>{v2}<div class=\"backup-upload\"><h3>Загрузить копию</h3><p class=\"caption\">Выберите ZIP-файл резервной копии для проверки содержимого.</p><div class=\"backup-upload-row\"><input type=\"file\" accept=\".zip,application/zip\" data-backup-file aria-label=\"Файл резервной копии\"><button class=\"icon-button\" type=\"button\" data-backup-upload {v3} title=\"Загрузить и проверить копию\" aria-label=\"Загрузить и проверить копию\">{v4}<span>Загрузить и проверить</span></button></div><progress data-backup-progress max=\"100\" value=\"0\" hidden></progress><div data-backup-preview>{v5}</div></div><div class=\"backup-list\"><div class=\"section-head\"><h3>Доступные копии</h3><span class=\"caption\">{v6}</span></div>{v7}</div>{v8}</section>",
    "en": "{v0}<section id=\"backups-page\" class=\"backups-page\" aria-label=\"Backups for all projects\"><div class=\"backup-panel-head\"><div><h2>Backups</h2><p class=\"caption\">The backup includes data from all projects. Restoration creates a separate inactive copy; current data remains unchanged.</p></div><button class=\"icon-button\" type=\"button\" data-backup-create title=\"Create backup\" aria-label=\"Create backup\">{v1}<span>Create backup</span></button></div><p class=\"backup-status\" role=\"status\" data-backup-status></p>{v2}<div class=\"backup-upload\"><h3>Upload backup</h3><p class=\"caption\">Choose a backup ZIP file to verify its contents.</p><div class=\"backup-upload-row\"><input type=\"file\" accept=\".zip,application/zip\" data-backup-file aria-label=\"Backup file\"><button class=\"icon-button\" type=\"button\" data-backup-upload {v3} title=\"Upload and verify backup\" aria-label=\"Upload and verify backup\">{v4}<span>Upload and verify</span></button></div><progress data-backup-progress max=\"100\" value=\"0\" hidden></progress><div data-backup-preview>{v5}</div></div><div class=\"backup-list\"><div class=\"section-head\"><h3>Available backups</h3><span class=\"caption\">{v6}</span></div>{v7}</div>{v8}</section>"
  },
  "backups.dff64f412875": {
    "ru": "<div class=\"page-head\"><div><div class=\"eyebrow\">Данные</div><h1>Проекты</h1><p>Резервные копии всех проектов и восстановление отдельной неактивной копии.</p></div></div>",
    "en": "<div class=\"page-head\"><div><div class=\"eyebrow\">Data</div><h1>Projects</h1><p>Backups for all projects and restoration to a separate inactive copy.</p></div></div>"
  },
  "backups.593c960d8bc4": {
    "ru": "<div class=\"backup-jobs\" aria-label=\"Операции с копиями\">{v0}</div>",
    "en": "<div class=\"backup-jobs\" aria-label=\"Backup operations\">{v0}</div>"
  },
  "backups.cb606efd1476": {
    "ru": "<p class=\"caption\">Резервных копий пока нет.</p>",
    "en": "<p class=\"caption\">There are no backups yet.</p>"
  },
  "backups.a003f2048ead": {
    "ru": "<p class=\"caption\">Загрузка списка…</p>",
    "en": "<p class=\"caption\">Loading list…</p>"
  },
  "backups.d062babb88b7": {
    "ru": "<div class=\"backup-restore-copies\"><div class=\"section-head\"><h3>Восстановленные копии</h3><span class=\"caption\">{v0}</span></div>{v1}</div>",
    "en": "<div class=\"backup-restore-copies\"><div class=\"section-head\"><h3>Restored copies</h3><span class=\"caption\">{v0}</span></div>{v1}</div>"
  },
  "backups.4421af9c6cb4": {
    "ru": "<p class=\"backup-restore-copy\" role=\"status\">Создана отдельная неактивная копия: <code>{v0}</code> · {v1} проектов. Текущие данные не изменены.</p>",
    "en": "<p class=\"backup-restore-copy\" role=\"status\">A separate inactive copy was created: <code>{v0}</code> · {v1} projects. Current data was not changed.</p>"
  },
  "backups.be6bb3dae69f": {
    "ru": "<article class=\"backup-card\"><div class=\"backup-card-heading\"><div><h3>{v0}</h3><p class=\"caption\">Создана {v1} · {v2}</p></div><code title=\"SHA-256\">{v3}</code></div><p>{v4}</p><div class=\"backup-actions\"><a class=\"icon-button\" href=\"/api/v1/backups/download?id={v5}\" download title=\"Скачать резервную копию\" aria-label=\"Скачать резервную копию\">{v6}<span>Скачать</span></a><button class=\"icon-button\" type=\"button\" data-backup-restore=\"{v7}\" title=\"Восстановить в отдельную папку\" aria-label=\"Восстановить в отдельную папку\">{v8}<span>Восстановить копию</span></button></div></article>",
    "en": "<article class=\"backup-card\"><div class=\"backup-card-heading\"><div><h3>{v0}</h3><p class=\"caption\">Created {v1} · {v2}</p></div><code title=\"SHA-256\">{v3}</code></div><p>{v4}</p><div class=\"backup-actions\"><a class=\"icon-button\" href=\"/api/v1/backups/download?id={v5}\" download title=\"Download backup\" aria-label=\"Download backup\">{v6}<span>Download</span></a><button class=\"icon-button\" type=\"button\" data-backup-restore=\"{v7}\" title=\"Restore to a separate folder\" aria-label=\"Restore to a separate folder\">{v8}<span>Restore copy</span></button></div></article>"
  },
  "backups.9eb508eda2fc": {
    "ru": "Резервная копия",
    "en": "Backup"
  },
  "backups.01ad30c08fcf": {
    "ru": "Все проекты на момент создания копии",
    "en": "All projects at the time of backup"
  },
  "backups.45ed0b6bc3a2": {
    "ru": "Проекты: {v0}",
    "en": "Projects: {v0}"
  },
  "backups.f45edf006851": {
    "ru": "Проект",
    "en": "Project"
  },
  "backups.aaca6cc1758d": {
    "ru": "<section class=\"backup-preview\" aria-label=\"Предварительный просмотр резервной копии\"><div class=\"section-head\"><h3>Предварительный просмотр</h3><span class=\"caption\">{v0}</span></div><p>{v1} файлов · {v2} · создана {v3}</p>{v4}</section>",
    "en": "<section class=\"backup-preview\" aria-label=\"Backup preview\"><div class=\"section-head\"><h3>Preview</h3><span class=\"caption\">{v0}</span></div><p>{v1} files · {v2} · created {v3}</p>{v4}</section>"
  },
  "backups.fc4d428a1b96": {
    "ru": "<p class=\"caption\">Проекты в архиве не указаны.</p>",
    "en": "<p class=\"caption\">No projects are listed in the archive.</p>"
  },
  "backups.7c0cc70f040a": {
    "ru": "<li><strong>{v0}</strong><span>{v1} задач · {v2} событий журнала</span></li>",
    "en": "<li><strong>{v0}</strong><span>{v1} tasks · {v2} journal events</span></li>"
  },
  "backups.1d8b8e7f21aa": {
    "ru": "Формат неизвестен",
    "en": "Unknown format"
  },
  "backups.06e1f1d51266": {
    "ru": "Формат {v0}",
    "en": "Format {v0}"
  },
  "backups.b3ce53956234": {
    "ru": "Прервано",
    "en": "Interrupted"
  },
  "backups.bf22dfeeba8b": {
    "ru": "Ошибка",
    "en": "Failed"
  },
  "backups.b459ff8f254e": {
    "ru": "Завершено",
    "en": "Completed"
  },
  "backups.ef95ffda901b": {
    "ru": " · {v0} с",
    "en": " · {v0} s"
  },
  "backups.822d93cab5c7": {
    "ru": "Операция",
    "en": "Operation"
  },
  "backups.ffc7bd0bca35": {
    "ru": " · {v0} из {v1}",
    "en": " · {v0} of {v1}"
  },
  "backups.844267b67b7e": {
    "ru": "Восстановление",
    "en": "Restoring"
  },
  "backups.e56a412d1285": {
    "ru": "Проверка",
    "en": "Verifying"
  },
  "backups.9d075c6c6973": {
    "ru": "Сжатие",
    "en": "Compressing"
  },
  "backups.fd2517f93c21": {
    "ru": "Снимок данных",
    "en": "Data snapshot"
  },
  "backups.5ea5c68f20d4": {
    "ru": "Подготовка",
    "en": "Preparing"
  },
  "backups.2d55ddef0ce5": {
    "ru": "Неизвестная ошибка",
    "en": "Unknown error"
  },
  "backups.242cbce2575c": {
    "ru": "{v0} МБ",
    "en": "{v0} MB"
  },
  "backups.23efda167fd1": {
    "ru": "{v0} КБ",
    "en": "{v0} KB"
  },
  "backups.56b6020f0d29": {
    "ru": "{v0} Б",
    "en": "{v0} B"
  },
  "backups.8684ae415a8d": {
    "ru": "Не удалось выполнить операцию с резервной копией",
    "en": "The backup operation could not be completed"
  },
  "checks.a7f9938c7e3e": {
    "ru": "{v0}<section class=\"checks-page\" aria-label=\"История проверок\"><div class=\"checks-toolbar\">{v1}{v2}{v3}<button class=\"icon-button\" type=\"button\" data-checks-refresh title=\"Обновить историю проверок\" aria-label=\"Обновить историю проверок\" {v4}>{v5}</button></div><p class=\"checks-count\" role=\"status\">{v6}Загружено {v7} из {v8} · По фильтрам: {v9}</p>{v10}<div class=\"checks-runs\" aria-busy=\"{v11}\">{v12}</div></section><section class=\"checks-baseline\"><div class=\"section-head\"><h2>Подтверждённый начальный срез</h2><span class=\"caption\">До запуска журнала</span></div>{v13}</section>",
    "en": "{v0}<section class=\"checks-page\" aria-label=\"Check history\"><div class=\"checks-toolbar\">{v1}{v2}{v3}<button class=\"icon-button\" type=\"button\" data-checks-refresh title=\"Refresh check history\" aria-label=\"Refresh check history\" {v4}>{v5}</button></div><p class=\"checks-count\" role=\"status\">{v6}Loaded {v7} of {v8} · Matching filters: {v9}</p>{v10}<div class=\"checks-runs\" aria-busy=\"{v11}\">{v12}</div></section><section class=\"checks-baseline\"><div class=\"section-head\"><h2>Confirmed baseline snapshot</h2><span class=\"caption\">Before the run log</span></div>{v13}</section>"
  },
  "checks.bb1b79b14c91": {
    "ru": "Проверки",
    "en": "Checks"
  },
  "checks.43c696001243": {
    "ru": "Качество",
    "en": "Quality"
  },
  "checks.359497aff53e": {
    "ru": "Профиль",
    "en": "Profile"
  },
  "checks.225077c6d479": {
    "ru": "Статус",
    "en": "Status"
  },
  "checks.b9ce27191d40": {
    "ru": "Задача",
    "en": "Task"
  },
  "checks.7d7e6c8ac615": {
    "ru": "Загрузка… · ",
    "en": "Loading… · "
  },
  "checks.e716a9b6a00a": {
    "ru": "<p role=\"alert\" class=\"checks-error\">{v0}. Показана доступная часть истории.</p>",
    "en": "<p role=\"alert\" class=\"checks-error\">{v0}. The available history is shown.</p>"
  },
  "checks.9bd8481f4216": {
    "ru": "Запусков по выбранным условиям нет.",
    "en": "No runs match the selected filters."
  },
  "checks.8ce7a2e82e67": {
    "ru": "Загрузка запусков…",
    "en": "Loading runs…"
  },
  "checks.12948425bb26": {
    "ru": "<p class=\"caption\">Начальный срез не зарегистрирован.</p>",
    "en": "<p class=\"caption\">No baseline snapshot has been registered.</p>"
  },
  "checks.b8232ffae9b1": {
    "ru": "<label for=\"checks-{v0}\">{v1}<select id=\"checks-{v2}\" data-checks-filter=\"{v3}\"><option value=\"\">Все</option>{v4}</select></label>",
    "en": "<label for=\"checks-{v0}\">{v1}<select id=\"checks-{v2}\" data-checks-filter=\"{v3}\"><option value=\"\">All</option>{v4}</select></label>"
  },
  "checks.47ea8d60f8ce": {
    "ru": "<details class=\"checks-run\" data-key=\"{v0}\"><summary><span class=\"checks-expand\">{v1}</span>{v2}<span class=\"checks-run-heading\"><strong>{v3}</strong>{v4}</span><span class=\"checks-time checks-profile\"><small>Профиль</small><span>{v5}</span></span><span class=\"checks-time\"><small>Начало</small>{v6}</span><span class=\"checks-time\"><small>Завершение</small>{v7}</span><span class=\"checks-time\"><small>Длительность</small>{v8}</span></summary><div class=\"checks-detail\">{v9}<dl>{v10}{v11}</dl>{v12}</div></details>",
    "en": "<details class=\"checks-run\" data-key=\"{v0}\"><summary><span class=\"checks-expand\">{v1}</span>{v2}<span class=\"checks-run-heading\"><strong>{v3}</strong>{v4}</span><span class=\"checks-time checks-profile\"><small>Profile</small><span>{v5}</span></span><span class=\"checks-time\"><small>Started</small>{v6}</span><span class=\"checks-time\"><small>Finished</small>{v7}</span><span class=\"checks-time\"><small>Duration</small>{v8}</span></summary><div class=\"checks-detail\">{v9}<dl>{v10}{v11}</dl>{v12}</div></details>"
  },
  "checks.e56a412d1285": {
    "ru": "Проверка",
    "en": "Verifying"
  },
  "checks.dcc30b47bd1e": {
    "ru": "Проект недоступен",
    "en": "Project unavailable"
  },
  "checks.da69491c9290": {
    "ru": "Проект запуска",
    "en": "Launch project"
  },
  "checks.d36a133fd3fa": {
    "ru": "Проект-владелец",
    "en": "Owner project"
  },
  "checks.ff6cb3b265db": {
    "ru": "Исходный проект",
    "en": "Origin project"
  },
  "checks.1b3ef3ff3360": {
    "ru": "Предыдущая запись",
    "en": "Previous record"
  },
  "checks.6f1924c288de": {
    "ru": "Причина исправления",
    "en": "Correction reason"
  },
  "checks.5960fc2fec3e": {
    "ru": "Код выхода",
    "en": "Exit code"
  },
  "checks.58fed910e73e": {
    "ru": "Ревизия",
    "en": "Revision"
  },
  "checks.a2cb4dde2ce6": {
    "ru": "Область проверки",
    "en": "Check scope"
  },
  "checks.64e9e8a8b277": {
    "ru": "Команда (argv)",
    "en": "Command (argv)"
  },
  "checks.29de0472de7c": {
    "ru": "Профиль / версия",
    "en": "Profile / version"
  },
  "checks.d5e8c111c915": {
    "ru": "Зарегистрированный запуск",
    "en": "Registered run"
  },
  "checks.5fa57ef4ba8c": {
    "ru": "Историческая запись",
    "en": "Historical record"
  },
  "checks.be8ee1152065": {
    "ru": "Начальный срез",
    "en": "Baseline snapshot"
  },
  "checks.1d80e1757a7a": {
    "ru": "Запись",
    "en": "Note"
  },
  "checks.66842329abcf": {
    "ru": "ID запуска",
    "en": "Run ID"
  },
  "checks.a8c7a7d05c94": {
    "ru": "<span class=\"caption\">Без задачи</span>",
    "en": "<span class=\"caption\">No task</span>"
  },
  "checks.bc272e0cea15": {
    "ru": "{v0} мин {v1} с",
    "en": "{v0} min {v1} s"
  },
  "checks.120d7a6383b4": {
    "ru": "{v0} с",
    "en": "{v0} s"
  },
  "checks.a8d1a8317560": {
    "ru": "История изменилась во время загрузки. Обновите список",
    "en": "History changed while loading. Refresh the list"
  },
  "checks.bfe951d9051a": {
    "ru": "Некорректная страница истории проверок",
    "en": "Invalid check history page"
  },
  "checks.4e16d382b4fe": {
    "ru": "Не удалось загрузить историю проверок",
    "en": "Could not load check history"
  },
  "checks.8cf46ff28cc1": {
    "ru": "Результат неизвестен",
    "en": "Outcome unknown"
  },
  "checks.f7b2f77928af": {
    "ru": "Прерван",
    "en": "Interrupted"
  },
  "checks.bf22dfeeba8b": {
    "ru": "Ошибка",
    "en": "Failed"
  },
  "checks.be625a64f643": {
    "ru": "Пройдено",
    "en": "Passed"
  },
  "checks.599ca07b8dd2": {
    "ru": "Выполняется",
    "en": "Running"
  },
  "documentation.bb38f42f08a3": {
    "ru": "<label>Раздел документации<select data-k-field=\"audience\">{v0}</select></label><label>Папка<input data-k-field=\"section\" value=\"{v1}\" placeholder=\"Например: Разработка / Сборка\"></label><label>Формат<select data-k-field=\"type\">{v2}</select></label><label>Состояние<select data-k-field=\"status\">{v3}</select></label>",
    "en": "<label>Documentation section<select data-k-field=\"audience\">{v0}</select></label><label>Folder<input data-k-field=\"section\" value=\"{v1}\" placeholder=\"For example: Development / Build\"></label><label>Format<select data-k-field=\"type\">{v2}</select></label><label>Status<select data-k-field=\"status\">{v3}</select></label>"
  },
  "documentation.3c54b5e783ef": {
    "ru": "Архив",
    "en": "Archive"
  },
  "documentation.6dcf44c7f692": {
    "ru": "Историческая",
    "en": "Historical"
  },
  "documentation.a5088f0fe34c": {
    "ru": "Актуальная",
    "en": "Current"
  },
  "documentation.65fd24f1cb37": {
    "ru": "Черновик",
    "en": "Draft"
  },
  "documentation.1cd33df9055d": {
    "ru": "Объяснение",
    "en": "Explanation"
  },
  "documentation.0a2f5a04fddd": {
    "ru": "Справочник",
    "en": "Reference"
  },
  "documentation.b6dc320f8c16": {
    "ru": "Инструкция",
    "en": "How-to"
  },
  "documentation.deefab96a5ba": {
    "ru": "Учебный материал",
    "en": "Tutorial"
  },
  "documentation.728fb7f05b1f": {
    "ru": "<div class=\"d-space-layout{v0}\" style=\"--d-tree-width:{v1}px\">{v2}{v3}<main class=\"d-document{v4}\"><nav class=\"d-page-breadcrumb\" aria-label=\"Расположение страницы\">{v5}<span>{v6}{v7}</span></nav>{v8}</main></div>",
    "en": "<div class=\"d-space-layout{v0}\" style=\"--d-tree-width:{v1}px\">{v2}{v3}<main class=\"d-document{v4}\"><nav class=\"d-page-breadcrumb\" aria-label=\"Page location\">{v5}<span>{v6}{v7}</span></nav>{v8}</main></div>"
  },
  "documentation.d344c2fa72de": {
    "ru": "<div class=\"d-tree-splitter\" role=\"separator\" tabindex=\"0\" aria-orientation=\"vertical\" aria-label=\"Ширина содержания\" aria-valuemin=\"180\" aria-valuemax=\"720\" aria-valuenow=\"{v0}\"></div>",
    "en": "<div class=\"d-tree-splitter\" role=\"separator\" tabindex=\"0\" aria-orientation=\"vertical\" aria-label=\"Contents width\" aria-valuemin=\"180\" aria-valuemax=\"720\" aria-valuenow=\"{v0}\"></div>"
  },
  "documentation.10abcc119778": {
    "ru": "<article class=\"k-inspector d-space-overview\"><h2>{v0}</h2><p>{v1}</p><p>{v2}</p><button data-k-action=\"new-doc\">Создать страницу</button></article>",
    "en": "<article class=\"k-inspector d-space-overview\"><h2>{v0}</h2><p>{v1}</p><p>{v2}</p><button data-k-action=\"new-doc\">Create page</button></article>"
  },
  "documentation.0bdd6f589e66": {
    "ru": "Выберите страницу в дереве слева.",
    "en": "Select a page in the tree on the left."
  },
  "documentation.0724bc2b537a": {
    "ru": "<section class=\"d-search-results\" aria-label=\"Результаты поиска\">{v0}{v1}</section>",
    "en": "<section class=\"d-search-results\" aria-label=\"Search results\">{v0}{v1}</section>"
  },
  "documentation.1d08f51a14cd": {
    "ru": "<p>Ничего не найдено.</p>",
    "en": "<p>Nothing found.</p>"
  },
  "documentation.44dfbcf5bf47": {
    "ru": "Общие материалы",
    "en": "General materials"
  },
  "documentation.5c068ebab74e": {
    "ru": "<button data-k-action=\"more\">Показать ещё</button>",
    "en": "<button data-k-action=\"more\">Show more</button>"
  },
  "documentation.71a2340f1e8a": {
    "ru": "Пока пусто",
    "en": "Empty for now"
  },
  "documentation.14f5c2357859": {
    "ru": "Статьи и справочные материалы этого раздела.",
    "en": "Articles and reference materials for this section."
  },
  "documentation.cae672528b90": {
    "ru": "<aside class=\"d-tree\" aria-label=\"Дерево документации\"><div class=\"d-tree-heading\"><span>Содержание</span><span>{v0}</span></div>{v1}{v2}<button class=\"d-tree-add\" data-k-action=\"new-doc\">{v3}<span>Создать страницу</span></button></aside>",
    "en": "<aside class=\"d-tree\" aria-label=\"Documentation tree\"><div class=\"d-tree-heading\"><span>Contents</span><span>{v0}</span></div>{v1}{v2}<button class=\"d-tree-add\" data-k-action=\"new-doc\">{v3}<span>Create page</span></button></aside>"
  },
  "documentation.9f6ceee42652": {
    "ru": "<p>В этом разделе пока нет страниц.</p></div>",
    "en": "<p>There are no pages in this section yet.</p></div>"
  },
  "documentation.084be15d17d3": {
    "ru": "<button data-k-action=\"more\">Показать ещё результаты поиска</button>",
    "en": "<button data-k-action=\"more\">Show more search results</button>"
  },
  "documentation.947a1802ee02": {
    "ru": "Исторический материал",
    "en": "Historical material"
  },
  "documentation.820010d672b1": {
    "ru": "<div class=\"d-toolbar\"><nav class=\"d-breadcrumb\" aria-label=\"Навигация документации\"><button data-d-home>{v0}<span>Документация</span></button>{v1}</nav><label class=\"d-search\">{v2}<span class=\"k-sr-only\">Поиск страниц</span><input type=\"search\" data-k-filter=\"query\" value=\"{v3}\" placeholder=\"Найти страницу\"></label>{v4}</div>",
    "en": "<div class=\"d-toolbar\"><nav class=\"d-breadcrumb\" aria-label=\"Documentation navigation\"><button data-d-home>{v0}<span>Documentation</span></button>{v1}</nav><label class=\"d-search\">{v2}<span class=\"k-sr-only\">Search pages</span><input type=\"search\" data-k-filter=\"query\" value=\"{v3}\" placeholder=\"Find a page\"></label>{v4}</div>"
  },
  "documentation.9c260c534671": {
    "ru": "Скрыть содержание",
    "en": "Hide contents"
  },
  "documentation.c4251841204f": {
    "ru": "Показать содержание",
    "en": "Show contents"
  },
  "documentation.1fcb33f2ea02": {
    "ru": "Сервер не подтвердил следующую страницу документации.",
    "en": "The server did not confirm the next documentation page."
  },
  "documentation.25fc2dbdfc0e": {
    "ru": "Документация обновилась во время загрузки дерева. Обновите раздел.",
    "en": "Documentation changed while loading the tree. Refresh the section."
  },
  "documentation.e58aaa8fe15c": {
    "ru": "<header class=\"k-heading d-heading\"><div><small>БАЗА ЗНАНИЙ ПРОЕКТА</small><h1>Документация</h1><p>Материалы проекта, собранные по разделам и папкам.</p></div><div class=\"k-actions\">{v0}<button class=\"d-primary-action\" data-k-action=\"new-doc\">{v1}<span>Создать страницу</span></button><button class=\"d-tool-trigger\" data-k-action=\"tools\">{v2}<span>Инструменты</span></button></div></header>",
    "en": "<header class=\"k-heading d-heading\"><div><small>PROJECT KNOWLEDGE BASE</small><h1>Documentation</h1><p>Project materials organized by sections and folders.</p></div><div class=\"k-actions\">{v0}<button class=\"d-primary-action\" data-k-action=\"new-doc\">{v1}<span>Create page</span></button><button class=\"d-tool-trigger\" data-k-action=\"tools\">{v2}<span>Tools</span></button></div></header>"
  },
  "documentation.75a3e50649e6": {
    "ru": "<button data-k-action=\"return-architecture\">Вернуться к архитектуре</button>",
    "en": "<button data-k-action=\"return-architecture\">Return to architecture</button>"
  },
  "documentation.e3ed53c75f0a": {
    "ru": "страниц",
    "en": "pages"
  },
  "documentation.91fc35f12d86": {
    "ru": "страницы",
    "en": "pages"
  },
  "documentation.2db15581e092": {
    "ru": "страница",
    "en": "page"
  },
  "documentation.cb392104b887": {
    "ru": "Интеграции, собственные компоненты и публичные контракты.",
    "en": "Integrations, custom components, and public contracts."
  },
  "documentation.a2441abc4213": {
    "ru": "Расширения и API",
    "en": "Extensions and APIs"
  },
  "documentation.7f4c1e45323c": {
    "ru": "Форматы, приёмы и примеры для авторов шаблонов.",
    "en": "Formats, techniques, and examples for template authors."
  },
  "documentation.a9d2a180afe2": {
    "ru": "Создание шаблонов",
    "en": "Template authoring"
  },
  "documentation.a9fc98b0ca15": {
    "ru": "Устройство проекта, сборка, архитектурные решения и сопровождение.",
    "en": "Project structure, builds, architecture decisions, and maintenance."
  },
  "documentation.ea439cac732e": {
    "ru": "Разработка приложения",
    "en": "Application development"
  },
  "documentation.034b492e4ba1": {
    "ru": "Работа с приложением, интерфейсом и основными возможностями.",
    "en": "Using the application, interface, and main features."
  },
  "documentation.06655b56cf0b": {
    "ru": "Руководство пользователя",
    "en": "User guide"
  },
  "html-documents.616860f14b91": {
    "ru": "<article class=\"d-html-document\">{v0}{v1}{v2}{v3}<div class=\"d-html-toolbar\"><div class=\"d-html-meta\" aria-label=\"Сведения о документе\">{v4}</div><a class=\"d-html-open\" href=\"{v5}\" target=\"_blank\" rel=\"noopener noreferrer\">Открыть отдельно</a></div><iframe class=\"d-html-frame\" src=\"{v6}\" title=\"{v7}\" sandbox=\"allow-scripts\"></iframe>{v8}</article>",
    "en": "<article class=\"d-html-document\">{v0}{v1}{v2}{v3}<div class=\"d-html-toolbar\"><div class=\"d-html-meta\" aria-label=\"Document information\">{v4}</div><a class=\"d-html-open\" href=\"{v5}\" target=\"_blank\" rel=\"noopener noreferrer\">Open separately</a></div><iframe class=\"d-html-frame\" src=\"{v6}\" title=\"{v7}\" sandbox=\"allow-scripts\"></iframe>{v8}</article>"
  },
  "html-documents.6a695f6f0d7e": {
    "ru": "Не найдены ресурсы",
    "en": "Resources not found"
  },
  "html-documents.05352527f978": {
    "ru": "Не найдены ссылки",
    "en": "Links not found"
  },
  "html-documents.b0b264ca9314": {
    "ru": "Внешние ресурсы не выполняются в изолированном просмотре",
    "en": "External resources do not run in the isolated viewer"
  },
  "html-documents.71c53cb63469": {
    "ru": "HTML-документ",
    "en": "HTML-document"
  },
  "html-documents.8d1c5ffcc2fc": {
    "ru": "<p class=\"d-html-warning\" role=\"alert\">У HTML-документа отсутствует исходный файл.</p>",
    "en": "<p class=\"d-html-warning\" role=\"alert\">The HTML document has no source file.</p>"
  },
  "html-documents.a231f4299c1b": {
    "ru": " title=\"Основание даты: {v0}\"",
    "en": " title=\"Date basis: {v0}\""
  },
  "html-documents.ef422ab46b3c": {
    "ru": "Архивный материал",
    "en": "Archived material"
  },
  "html-documents.f5b5eef91751": {
    "ru": "Актуальный материал",
    "en": "Current material"
  },
  "html-documents.65fd24f1cb37": {
    "ru": "Черновик",
    "en": "Draft"
  },
  "html-documents.947a1802ee02": {
    "ru": "Исторический материал",
    "en": "Historical material"
  },
  "images.6ed906faa964": {
    "ru": "Сервер не вернул ссылку на файл",
    "en": "The server did not return a file link"
  },
  "images.9985b0ad9602": {
    "ru": "Не удалось прочитать файл",
    "en": "Could not read the file"
  },
  "images.db491ef5033f": {
    "ru": "Загрузка…",
    "en": "Loading…"
  },
  "images.e526f22f58a1": {
    "ru": "Размер файла превышает 20 МиБ",
    "en": "The file size exceeds 20 MiB"
  },
  "images.644afc727de8": {
    "ru": "<span></span><small role=\"status\"></small><button type=\"button\" class=\"icon-button\" title=\"Удалить\" aria-label=\"Удалить\">{v0}</button>",
    "en": "<span></span><small role=\"status\"></small><button type=\"button\" class=\"icon-button\" title=\"Remove\" aria-label=\"Remove\">{v0}</button>"
  },
  "images.1a84729fe0eb": {
    "ru": "<summary>Изображения задачи ({v0})</summary><div class=\"image-gallery\">{v1}</div>",
    "en": "<summary>Task images ({v0})</summary><div class=\"image-gallery\">{v1}</div>"
  },
  "images.6580c1c7c01c": {
    "ru": "<button class=\"image-tile\" type=\"button\" data-reuse=\"{v0}\" title=\"Добавить: {v1}\"><img alt=\"\" loading=\"lazy\" src=\"{v2}\"><span class=\"image-failure\" hidden>Предпросмотр недоступен</span><span>{v3}</span></button>",
    "en": "<button class=\"image-tile\" type=\"button\" data-reuse=\"{v0}\" title=\"Add: {v1}\"><img alt=\"\" loading=\"lazy\" src=\"{v2}\"><span class=\"image-failure\" hidden>Preview unavailable</span><span>{v3}</span></button>"
  },
  "images.b59d4dceb7a9": {
    "ru": "<button class=\"image-tile editor-image-preview\" type=\"button\" data-image-path=\"{v0}\" aria-label=\"Открыть изображение: {v1}\"><img alt=\"\" src=\"{v2}\"><span class=\"image-failure\" hidden>Предпросмотр недоступен</span></button>",
    "en": "<button class=\"image-tile editor-image-preview\" type=\"button\" data-image-path=\"{v0}\" aria-label=\"Open image: {v1}\"><img alt=\"\" src=\"{v2}\"><span class=\"image-failure\" hidden>Preview unavailable</span></button>"
  },
  "images.da2da5c8e24d": {
    "ru": "<label class=\"edit-field\"><span>Добавить файлы</span><input type=\"file\" multiple aria-label=\"Добавить файлы\"></label><div class=\"image-upload-list\"></div>",
    "en": "<label class=\"edit-field\"><span>Add files</span><input type=\"file\" multiple aria-label=\"Add files\"></label><div class=\"image-upload-list\"></div>"
  },
  "images.ec9799f58d28": {
    "ru": "Предпросмотр этого формата недоступен. Скачайте оригинал.",
    "en": "Preview is unavailable for this format. Download the original."
  },
  "images.f9aa8240d753": {
    "ru": "Источник недоступен. Можно проверить другую версию.",
    "en": "The source is unavailable. You can check another version."
  },
  "images.c0368b861259": {
    "ru": "Не удалось проверить источник",
    "en": "Could not check the source"
  },
  "images.148de878a9dc": {
    "ru": "Не удалось открыть изображение. Скачайте оригинал.",
    "en": "Could not open the image. Download the original."
  },
  "images.a784c7e776fe": {
    "ru": "Масштаб 1:1 предпросмотра",
    "en": "Preview 1:1 scale"
  },
  "images.078683788cb3": {
    "ru": "Вписать в окно",
    "en": "Fit to window"
  },
  "images.52dc053311e4": {
    "ru": "<header><strong></strong><select aria-label=\"Версия источника\"><option value=\"current\">Текущий файл</option><option value=\"archive\">Архив</option></select><button type=\"button\" class=\"icon-button\" data-zoom aria-label=\"Масштаб 1:1 предпросмотра\" title=\"Масштаб 1:1 предпросмотра\" aria-pressed=\"false\">{v0}</button><a class=\"icon-button\" data-download download title=\"Скачать оригинал\" aria-label=\"Скачать оригинал\">{v1}</a><button type=\"button\" class=\"icon-button\" data-close title=\"Закрыть\" aria-label=\"Закрыть\">{v2}</button></header><p class=\"image-status\" role=\"status\"></p><div class=\"image-viewer\"><button type=\"button\" class=\"icon-button image-nav\" data-image-prev aria-label=\"Предыдущее изображение\" title=\"Предыдущее изображение\" disabled>{v3}</button><div class=\"image-viewport\" tabindex=\"0\" aria-label=\"Изображение\"></div><button type=\"button\" class=\"icon-button image-nav\" data-image-next aria-label=\"Следующее изображение\" title=\"Следующее изображение\" disabled>{v4}</button></div><details><summary>Источник</summary><pre data-provenance></pre></details>",
    "en": "<header><strong></strong><select aria-label=\"Source version\"><option value=\"current\">Current file</option><option value=\"archive\">Archive</option></select><button type=\"button\" class=\"icon-button\" data-zoom aria-label=\"Preview 1:1 scale\" title=\"Preview 1:1 scale\" aria-pressed=\"false\">{v0}</button><a class=\"icon-button\" data-download download title=\"Download original\" aria-label=\"Download original\">{v1}</a><button type=\"button\" class=\"icon-button\" data-close title=\"Close\" aria-label=\"Close\">{v2}</button></header><p class=\"image-status\" role=\"status\"></p><div class=\"image-viewer\"><button type=\"button\" class=\"icon-button image-nav\" data-image-prev aria-label=\"Previous image\" title=\"Previous image\" disabled>{v3}</button><div class=\"image-viewport\" tabindex=\"0\" aria-label=\"Image\"></div><button type=\"button\" class=\"icon-button image-nav\" data-image-next aria-label=\"Next image\" title=\"Next image\" disabled>{v4}</button></div><details><summary>Source</summary><pre data-provenance></pre></details>"
  },
  "images.ea39db0332cf": {
    "ru": "<button type=\"button\" class=\"image-tile\" data-image-path=\"{v0}\" title=\"{v1}\"><img src=\"{v2}\" alt=\"\" loading=\"lazy\"><span class=\"image-failure\" hidden>Предпросмотр недоступен</span><span>{v3}</span></button>",
    "en": "<button type=\"button\" class=\"image-tile\" data-image-path=\"{v0}\" title=\"{v1}\"><img src=\"{v2}\" alt=\"\" loading=\"lazy\"><span class=\"image-failure\" hidden>Preview unavailable</span><span>{v3}</span></button>"
  },
  "images.f242456b2273": {
    "ru": "Файл",
    "en": "File"
  },
  "images.e7e104355790": {
    "ru": "Лог",
    "en": "Log"
  },
  "images.3091aca226ef": {
    "ru": "Текст",
    "en": "Text"
  },
  "knowledge-research.4222c6f20dbd": {
    "ru": "Запрос не принят",
    "en": "Request not accepted"
  },
  "knowledge-research.3822e2ed03db": {
    "ru": "{v0} · область исследования",
    "en": "{v0} · exploration scope"
  },
  "knowledge-research.295be651384d": {
    "ru": "Элемент закреплён на холсте",
    "en": "Element pinned to canvas"
  },
  "knowledge-research.2d91108371e1": {
    "ru": "Закрепление снято",
    "en": "Unpinned"
  },
  "knowledge-research.5d32ef453063": {
    "ru": "Раздели участников на понятные категории с иерархией. Сохрани отдельную карту с группировкой и суммарными связями, не меняя глобальное владение элементами.",
    "en": "Organize the participants into clear categories with a hierarchy. Save a separate map with grouping and aggregated relationships, without changing global ownership of elements."
  },
  "knowledge-research.07bb4dc27387": {
    "ru": "Текущая карта",
    "en": "Current map"
  },
  "knowledge-research.0d564ca8d70f": {
    "ru": "Результат: {v0} · {v1}",
    "en": "Result: {v0} · {v1}"
  },
  "knowledge-research.04c325ed529c": {
    "ru": "Исследование",
    "en": "Exploration"
  },
  "knowledge-research.27db1bcdd585": {
    "ru": "Результат отсутствует на текущей карте",
    "en": "The result is missing from the current map"
  },
  "knowledge-research.728202ab1b25": {
    "ru": "Предложи и сохрани понятную иерархию подсистем для выбранной директории. Исследуй внешние связи при необходимости; не ограничивай анализ границами папки.",
    "en": "Propose and save a clear subsystem hierarchy for the selected directory. Explore external relationships as needed; do not limit the analysis to the folder boundaries."
  },
  "knowledge-research.6ec748dce3e3": {
    "ru": "Создай карту архитектуры выбранной директории: её состав, назначение и важные связи с остальным проектом. Сохрани карту с доказательствами из исходников.",
    "en": "Create an architecture map of the selected directory: its contents, purpose and important relationships with the rest of the project. Save the map with evidence from source code."
  },
  "knowledge-research.3828a0f1791f": {
    "ru": "<strong>Текущая карта</strong>{v0}{v1}{v2}{v3}<div class=\"r-label\">Отдельные результаты исследований</div>{v4}",
    "en": "<strong>Current map</strong>{v0}{v1}{v2}{v3}<div class=\"r-label\">Separate exploration results</div>{v4}"
  },
  "knowledge-research.d19310d6efe8": {
    "ru": "Структурировать всю текущую карту",
    "en": "Structure the entire current map"
  },
  "knowledge-research.719040d9cfa8": {
    "ru": "Свернуть группы",
    "en": "Collapse groups"
  },
  "knowledge-research.4ecdb94e431b": {
    "ru": "Раскрыть все группы",
    "en": "Expand all groups"
  },
  "knowledge-research.9afb4629f7d5": {
    "ru": "Сохранить карту",
    "en": "Save map"
  },
  "knowledge-research.f6511b70b268": {
    "ru": "<small>Пока нет добавленных исследований</small>",
    "en": "<small>No explorations added yet</small>"
  },
  "knowledge-research.8a218c0dcb3c": {
    "ru": "<div class=\"r-label\">Сопоставить</div>{v0}{v1}{v2}{v3}{v4}",
    "en": "<div class=\"r-label\">Compare</div>{v0}{v1}{v2}{v3}{v4}"
  },
  "knowledge-research.37b23ddaad9d": {
    "ru": "Назначить A",
    "en": "Set as A"
  },
  "knowledge-research.8cb8e1d9ae04": {
    "ru": "Назначить B",
    "en": "Set as B"
  },
  "knowledge-research.29c06b4d41bd": {
    "ru": "Закрепить на холсте",
    "en": "Pin to canvas"
  },
  "knowledge-research.20ea9fc48ebb": {
    "ru": "Снять закрепление",
    "en": "Unpin"
  },
  "knowledge-research.2b0f347601cd": {
    "ru": "Структурировать всю подсистему",
    "en": "Structure the entire subsystem"
  },
  "knowledge-research.01565f7ba7f7": {
    "ru": "Создать подсистемы из директории",
    "en": "Create subsystems from a directory"
  },
  "knowledge-research.0126c81184c7": {
    "ru": "Создать карту директории",
    "en": "Create a directory map"
  },
  "knowledge-research.461f299982f4": {
    "ru": "<small>Проверяем возможности…</small>",
    "en": "<small>Checking capabilities…</small>"
  },
  "knowledge-research.efc7382cb1db": {
    "ru": "Открыть отдельно на холсте",
    "en": "Open separately on the canvas"
  },
  "knowledge-research.655809bfceee": {
    "ru": "Показать шаги сценария",
    "en": "Show scenario steps"
  },
  "knowledge-research.5e981f88c4d1": {
    "ru": "Свернуть раскрытую ветку",
    "en": "Collapse the expanded branch"
  },
  "knowledge-research.51792def2af7": {
    "ru": "Свернуть продолжение сценария",
    "en": "Collapse the rest of the scenario"
  },
  "knowledge-research.0a825b112958": {
    "ru": "<div class=\"r-label\">На холсте</div>",
    "en": "<div class=\"r-label\">On the canvas</div>"
  },
  "knowledge-research.eadbf5066229": {
    "ru": "<div class=\"r-label\">Дерево</div>{v0}{v1}<div class=\"r-label\">Исследование</div>",
    "en": "<div class=\"r-label\">Tree</div>{v0}{v1}<div class=\"r-label\">Exploration</div>"
  },
  "knowledge-research.83408dd78830": {
    "ru": "Свернуть потомков",
    "en": "Collapse descendants"
  },
  "knowledge-research.a2f201bfd2d8": {
    "ru": "Развернуть всех потомков",
    "en": "Expand all descendants"
  },
  "knowledge-research.428ed33b6ea1": {
    "ru": "Свернуть всё",
    "en": "Collapse all"
  },
  "knowledge-research.8f99fcd144e0": {
    "ru": "Исследование прервано",
    "en": "Exploration interrupted"
  },
  "knowledge-research.bea575963371": {
    "ru": "Этот результат не содержит применимого графа. ",
    "en": "This result does not contain a usable graph. "
  },
  "knowledge-research.1726a3800daf": {
    "ru": "Исходники изменились во время анализа. Повторите исследование.",
    "en": "Source files changed during analysis. Repeat the exploration."
  },
  "knowledge-research.428c47fe4036": {
    "ru": "Неверная страница результата",
    "en": "Invalid result page"
  },
  "knowledge-research.e1b16143ac2e": {
    "ru": "<h2>Сохранить исследовательскую карту</h2><form data-r-save-form><label>Название<input name=\"title\" maxlength=\"300\" required></label><button type=\"submit\" class=\"r-primary\">Сохранить карту</button></form>",
    "en": "<h2>Save exploration map</h2><form data-r-save-form><label>Title<input name=\"title\" maxlength=\"300\" required></label><button type=\"submit\" class=\"r-primary\">Save map</button></form>"
  },
  "knowledge-research.a9f50900ce61": {
    "ru": "<h2>Языковые провайдеры</h2>{v0}<p>Настройка: <code>{v1}</code></p><p>Для Java используйте помощник knowledge_language.py. Другие языки подключаются конфигурацией готового LSP-сервера. Доступность операций определяется возможностями сервера и типом элемента.</p>",
    "en": "<h2>Language providers</h2>{v0}<p>Setting: <code>{v1}</code></p><p>For Java, use the knowledge_language.py helper. Other languages can be connected by configuring an existing LSP server. Available operations depend on the server's capabilities and the element type.</p>"
  },
  "knowledge-research.ef92bb7c5369": {
    "ru": "<p>Серверы пока не подключены.</p>",
    "en": "<p>No servers connected yet.</p>"
  },
  "knowledge-research.8bf6f1e2e70b": {
    "ru": "Стандартно",
    "en": "Standard"
  },
  "knowledge-research.6b3122c6dc52": {
    "ru": "Подробно",
    "en": "Detailed"
  },
  "knowledge-research.6a6d484b2190": {
    "ru": "Кратко",
    "en": "Brief"
  },
  "knowledge-research.a023a456aa06": {
    "ru": "Выбранный объект и необходимые связи из исходников.",
    "en": "The selected object and necessary relationships from source code."
  },
  "knowledge-research.ca46ed8e4358": {
    "ru": "Вся подсистема: собственные элементы, дочерние подсистемы и необходимые внешние связи. Область не ограничена текущим холстом.",
    "en": "The entire subsystem: its own elements, child subsystems and necessary external relationships. The scope is not limited to the current canvas."
  },
  "knowledge-research.bfd922f2a6ea": {
    "ru": "{v0} · {v1} элементов · {v2} связей. Перед запуском сохранится снимок области; агент создаст отдельную карту с категориями.",
    "en": "{v0} · {v1} elements · {v2} relationships. A snapshot of the scope will be saved before starting; the agent will create a separate map with categories."
  },
  "knowledge-research.1a33284e0d8d": {
    "ru": "Вся текущая карта",
    "en": "Entire current map"
  },
  "knowledge-research.474f35a04e2b": {
    "ru": "Только выбранный результат исследования",
    "en": "Only the selected exploration result"
  },
  "knowledge-research.3d5dad864efc": {
    "ru": "<h2>Исследуйте постепенно</h2><p>Начните с подсистемы, исходника или сохранённой карты. Открытие в навигаторе заменяет область холста.</p><p>В меню узла раскройте состав, собственные элементы или исследуйте связи. Действие запускается сразу и раскрывает один шаг до следующего видимого символа. Продолжайте с найденного символа; его связи автоматически не раскрываются. Представление выберите в настройках Project Hub → «Архитектура и код». Если файлы скрыты, переходы через них показаны как цепочки. Статус появляется на холсте сразу; результат добавляется автоматически с компоновкой. Сохранённые связи читаются из каталога. Структуру методов и вызовы исследуйте через языковой сервер.</p><p>Назначьте A и B в меню двух узлов, чтобы найти путь. Свернуть ветку убирает только результаты её раскрытия, сохраняя общие и закреплённые элементы.</p><p>Alt+Enter — весь доступный холст; Escape — вернуться. F — вписать выбор.</p>",
    "en": "<h2>Explore gradually</h2><p>Start with a subsystem, source file or saved map. Opening an item in the navigator replaces the canvas scope.</p><p>Use the node menu to expand its contents or own elements, or explore its relationships. The action starts immediately and expands one step to the next visible symbol. Continue from the symbol you find; its relationships are not expanded automatically. Choose the view in Project Hub settings → “Architecture and code”. If files are hidden, paths through them appear as chains. Status appears on the canvas immediately; the result is added and laid out automatically. Saved relationships are read from the catalog. Explore method structure and calls through the language server.</p><p>Set A and B in the menus of two nodes to find a path. Collapsing a branch removes only the results of expanding that branch, preserving shared and pinned elements.</p><p>Alt+Enter — the entire available canvas; Escape to return. F to fit the selection.</p>"
  },
  "knowledge-research.1329f067e159": {
    "ru": "<h2>Журнал исследований</h2><p class=\"r-hint\">Запуски по всему проекту. Работающие запросы агента — первыми, затем новые сверху. По 20 записей на страницу в каждом разделе. Автоматические загрузки разделов скрыты.</p>{v0}<h3>Агент</h3>{v1}{v2}<h3>Анализатор</h3>{v3}{v4}{v5}",
    "en": "<h2>Research journal</h2><p class=\"r-hint\">Runs across the entire project. Active agent requests appear first, followed by the newest entries. Each section has 20 entries per page. Automatic section loads are hidden.</p>{v0}<h3>Agent</h3>{v1}{v2}<h3>Analyzer</h3>{v3}{v4}{v5}"
  },
  "knowledge-research.de228d428306": {
    "ru": "<p role=\"status\">Загружаем журнал…</p>",
    "en": "<p role=\"status\">Loading journal…</p>"
  },
  "knowledge-research.254cf5d72f78": {
    "ru": "<p>Запросов агенту пока нет.</p>",
    "en": "<p>There are no agent requests yet.</p>"
  },
  "knowledge-research.fbda3d738a6f": {
    "ru": "<p>Нет исследований.</p>",
    "en": "<p>No research yet.</p>"
  },
  "knowledge-research.603e460bf59c": {
    "ru": "Обновить",
    "en": "Refresh"
  },
  "knowledge-research.12c84293072b": {
    "ru": "Ранее",
    "en": "Earlier"
  },
  "knowledge-research.6140d7258082": {
    "ru": "Новее",
    "en": "Newer"
  },
  "knowledge-research.18178e882774": {
    "ru": "<article class=\"r-job r-job-agent\"><span class=\"r-job-source\">{v0}Агент AI</span><strong>{v1}</strong><span>{v2}</span><small>{v3}</small><span>{v4}</span>{v5}{v6}{v7}</article>",
    "en": "<article class=\"r-job r-job-agent\"><span class=\"r-job-source\">{v0}AI agent</span><strong>{v1}</strong><span>{v2}</span><small>{v3}</small><span>{v4}</span>{v5}{v6}{v7}</article>"
  },
  "knowledge-research.acf4d2beedb2": {
    "ru": "Запрос агенту",
    "en": "Agent request"
  },
  "knowledge-research.ed9decf31558": {
    "ru": "<a href=\"codex://threads/{v0}\" target=\"_blank\" rel=\"noreferrer\">Открыть чат агента</a>",
    "en": "<a href=\"codex://threads/{v0}\" target=\"_blank\" rel=\"noreferrer\">Open agent chat</a>"
  },
  "knowledge-research.364f38915e47": {
    "ru": "Элемент",
    "en": "Element"
  },
  "knowledge-research.aae1f96172eb": {
    "ru": "class=\"r-icon\" aria-label=\"Закрыть\"",
    "en": "class=\"r-icon\" aria-label=\"Close\""
  },
  "knowledge-research.a7a4033657e8": {
    "ru": "Закрыть",
    "en": "Close"
  },
  "knowledge-research.b6715a1a9dbd": {
    "ru": "<article class=\"r-job r-job-analyzer\"><span class=\"r-job-source\">{v0}Анализатор</span><strong>{v1}</strong><span>{v2}</span><small>{v3} · {v4}</small><span>{v5}{v6}{v7}</span>{v8}{v9}<div>{v10}</div></article>",
    "en": "<article class=\"r-job r-job-analyzer\"><span class=\"r-job-source\">{v0}Analyzer</span><strong>{v1}</strong><span>{v2}</span><small>{v3} · {v4}</small><span>{v5}{v6}{v7}</span>{v8}{v9}<div>{v10}</div></article>"
  },
  "knowledge-research.424c6c965459": {
    "ru": "Сохранённые факты",
    "en": "Saved facts"
  },
  "knowledge-research.dd77f0a008a8": {
    "ru": "Частичный результат",
    "en": "Partial result"
  },
  "knowledge-research.7475a46fb013": {
    "ru": " · из кэша",
    "en": " · from cache"
  },
  "knowledge-research.6a2ebd568d3a": {
    "ru": " · {v0} элементов · {v1} связей",
    "en": " · {v0} elements · {v1} relationships"
  },
  "knowledge-research.7c47f7292ba4": {
    "ru": "Отменить",
    "en": "Cancel"
  },
  "knowledge-research.1bad5a2c8bcd": {
    "ru": "Посмотреть результат",
    "en": "View result"
  },
  "knowledge-research.2843fd0f0896": {
    "ru": " · открыть журнал исследований",
    "en": " · open exploration log"
  },
  "knowledge-research.4ffca1543786": {
    "ru": "Агент · {v0}{v1} · {v2}{v3}{v4}",
    "en": "Agent · {v0}{v1} · {v2}{v3}{v4}"
  },
  "knowledge-research.5d8079c0a0a3": {
    "ru": " · добавлено {v0}",
    "en": " · added {v0}"
  },
  "knowledge-research.7c0c2176c4d6": {
    "ru": "Что вызывает",
    "en": "Callees"
  },
  "knowledge-research.6c7d4b945c9a": {
    "ru": "Кто вызывает",
    "en": "Callers"
  },
  "knowledge-research.c617b89fd870": {
    "ru": "Ссылки на символ",
    "en": "References to symbol"
  },
  "knowledge-research.d2b67e827f0d": {
    "ru": "Перейти к определению",
    "en": "Go to definition"
  },
  "knowledge-research.0b1e7b7ccd85": {
    "ru": "Структура исходника",
    "en": "Source structure"
  },
  "knowledge-research.471958b93be1": {
    "ru": "Связь A → B",
    "en": "Relationship A → B"
  },
  "knowledge-research.20ee9d0bf71c": {
    "ru": "Наследники и реализации",
    "en": "Derived types and implementations"
  },
  "knowledge-research.159ed72dcb07": {
    "ru": "Базовые типы",
    "en": "Base types"
  },
  "knowledge-research.57712f63ff5d": {
    "ru": "Кто использует элемент",
    "en": "What uses this element"
  },
  "knowledge-research.9d258667d512": {
    "ru": "Что использует элемент",
    "en": "What this element uses"
  },
  "knowledge-research.d7c52cffe62a": {
    "ru": "Определения внутри",
    "en": "Definitions within"
  },
  "knowledge-research.195eefeb2b71": {
    "ru": "Собственные элементы",
    "en": "Own elements"
  },
  "knowledge-research.375fb7239895": {
    "ru": "Подсистемы следующего уровня",
    "en": "Subsystems at the next level"
  },
  "knowledge-research.07aa0a7e5648": {
    "ru": "<section class=\"r-pair\"><h3>Связь двух объектов</h3><div><b>A</b> {v0}</div><div><b>B</b> {v1}</div><div class=\"r-inline\">{v2}{v3}{v4}</div></section>",
    "en": "<section class=\"r-pair\"><h3>Relationship between two objects</h3><div><b>A</b> {v0}</div><div><b>B</b> {v1}</div><div class=\"r-inline\">{v2}{v3}{v4}</div></section>"
  },
  "knowledge-research.8a6dc054ffe7": {
    "ru": "Выберите в меню узла",
    "en": "Choose from the node menu"
  },
  "knowledge-research.0d16aab0591f": {
    "ru": "Поменять",
    "en": "Swap"
  },
  "knowledge-research.8965271d3c97": {
    "ru": "Очистить",
    "en": "Clear"
  },
  "knowledge-research.c41b3b3a848f": {
    "ru": "Найти путь",
    "en": "Find path"
  },
  "knowledge-research.40c071dcb4cb": {
    "ru": "<section class=\"r-inspector-actions\"><h3>На холсте</h3>{v0}{v1}{v2}<h3>Исследовать</h3>{v3}{v4}<h3>Помощь агента</h3>{v5}{v6}</section>{v7}<section class=\"r-evidence-card\"><h3>Основание карты</h3><p>{v8}</p><small>Статические связи не гарантируют полный путь выполнения. Сценарии содержат только сохранённые участки.</small></section>",
    "en": "<section class=\"r-inspector-actions\"><h3>On the canvas</h3>{v0}{v1}{v2}<h3>Explore</h3>{v3}{v4}<h3>Agent help</h3>{v5}{v6}</section>{v7}<section class=\"r-evidence-card\"><h3>Map basis</h3><p>{v8}</p><small>Static relationships do not guarantee a complete execution path. Scenarios contain only saved segments.</small></section>"
  },
  "knowledge-research.cbaef226242b": {
    "ru": "<p class=\"k-empty\">Проверяем доступные действия…</p>",
    "en": "<p class=\"k-empty\">Checking available actions…</p>"
  },
  "knowledge-research.131ca6ac802c": {
    "ru": "<small>Глубокий анализ: настройте языковой сервер в инструментах.</small>",
    "en": "<small>Deep analysis: configure a language server in Tools.</small>"
  },
  "knowledge-research.6bc29babed0c": {
    "ru": "Сохранённые факты и авторская структура",
    "en": "Saved facts and authored structure"
  },
  "knowledge-research.eeae2d911c84": {
    "ru": "<section class=\"r-inspector-actions\"><h3>Категория текущей карты</h3><p>Группировка отображения. Исходные участники и связи сохраняются.</p>{v0}</section>",
    "en": "<section class=\"r-inspector-actions\"><h3>Current map category</h3><p>Display grouping. Original participants and relationships are preserved.</p>{v0}</section>"
  },
  "knowledge-research.ab5169be4871": {
    "ru": "Сгруппировать результат: {v0} · {v1}",
    "en": "Group the result: {v0} · {v1}"
  },
  "knowledge-research.99abcf53559a": {
    "ru": "Свернуть содержимое группы",
    "en": "Collapse group contents"
  },
  "knowledge-research.a5a0e1951383": {
    "ru": "Раскрыть содержимое группы",
    "en": "Expand group contents"
  },
  "knowledge-research.353cf589e95b": {
    "ru": "Автоматически",
    "en": "Automatic"
  },
  "knowledge-research.61da6b5d923c": {
    "ru": "<section class=\"k-graph-panel r-panel\"><div class=\"r-graph-toolbar\"><div class=\"r-tool-group\"><button data-k-action=\"graph-back\" title=\"Назад\" aria-label=\"Назад\"{v0}>{v1}</button><button data-k-action=\"graph-forward\" title=\"Вперёд\" aria-label=\"Вперёд\"{v2}>{v3}</button><button data-k-action=\"zoom-out\" aria-label=\"Уменьшить\">−</button><button data-k-action=\"zoom-in\" aria-label=\"Увеличить\">+</button></div><div class=\"r-tool-group\"><button data-k-action=\"fit\" title=\"Вписать всё\">{v4}<span>Вписать</span></button><button data-k-action=\"focus\" title=\"Фокус · F\">{v5}<span>Фокус</span></button><button data-k-action=\"auto-layout\" title=\"Одна компоновка с сохранением фокуса\">{v6}<span>Компоновка</span></button></div><div class=\"r-tool-group r-toolbar-end\"><button data-k-action=\"toggle-list\" title=\"Навигатор\" aria-label=\"Навигатор\" aria-expanded=\"{v7}\">{v8}</button>{v9}{v10}<button data-k-action=\"toggle-inspector\" title=\"Обзор выбранного\" aria-label=\"Обзор выбранного\" aria-expanded=\"{v11}\">{v12}</button>{v13}</div></div><div class=\"r-canvas-caption\"><span>{v14} элементов · {v15} связей</span><button class=\"r-research-status\" data-r-research-status data-r-agent-status data-r-action=\"jobs\" aria-live=\"polite\"{v16} title=\"Открыть журнал исследований\">{v17}</button><span>ПКМ по узлу — исследовать · F — фокус</span></div><p data-k-canvas-selection role=\"status\" hidden></p><div class=\"k-node-actions r-node-actions\" data-k-node-actions hidden>{v18}</div><div class=\"k-graph\" data-k-cy role=\"group\" aria-label=\"Карта кода проекта\"><div class=\"k-group-labels\" data-k-group-labels aria-hidden=\"true\"></div></div></section>",
    "en": "<section class=\"k-graph-panel r-panel\"><div class=\"r-graph-toolbar\"><div class=\"r-tool-group\"><button data-k-action=\"graph-back\" title=\"Back\" aria-label=\"Back\"{v0}>{v1}</button><button data-k-action=\"graph-forward\" title=\"Forward\" aria-label=\"Forward\"{v2}>{v3}</button><button data-k-action=\"zoom-out\" aria-label=\"Zoom out\">−</button><button data-k-action=\"zoom-in\" aria-label=\"Zoom in\">+</button></div><div class=\"r-tool-group\"><button data-k-action=\"fit\" title=\"Fit all\">{v4}<span>Fit</span></button><button data-k-action=\"focus\" title=\"Focus · F\">{v5}<span>Focus</span></button><button data-k-action=\"auto-layout\" title=\"One layout pass preserving focus\">{v6}<span>Layout</span></button></div><div class=\"r-tool-group r-toolbar-end\"><button data-k-action=\"toggle-list\" title=\"Navigator\" aria-label=\"Navigator\" aria-expanded=\"{v7}\">{v8}</button>{v9}{v10}<button data-k-action=\"toggle-inspector\" title=\"Overview of selection\" aria-label=\"Overview of selection\" aria-expanded=\"{v11}\">{v12}</button>{v13}</div></div><div class=\"r-canvas-caption\"><span>{v14} elements · {v15} relationships</span><button class=\"r-research-status\" data-r-research-status data-r-agent-status data-r-action=\"jobs\" aria-live=\"polite\"{v16} title=\"Open exploration log\">{v17}</button><span>Right-click a node to explore · F to focus</span></div><p data-k-canvas-selection role=\"status\" hidden></p><div class=\"k-node-actions r-node-actions\" data-k-node-actions hidden>{v18}</div><div class=\"k-graph\" data-k-cy role=\"group\" aria-label=\"Project code map\"><div class=\"k-group-labels\" data-k-group-labels aria-hidden=\"true\"></div></div></section>"
  },
  "knowledge-research.2751c9100018": {
    "ru": "Карта",
    "en": "Map"
  },
  "knowledge-research.fc4bf3b38152": {
    "ru": "class=\"r-icon\" aria-label=\"Развернуть холст\"",
    "en": "class=\"r-icon\" aria-label=\"Expand canvas\""
  },
  "knowledge-research.66e805f82137": {
    "ru": "Развернуть холст · Alt+Enter",
    "en": "Expand canvas · Alt+Enter"
  },
  "knowledge-research.bc40872e777a": {
    "ru": "aria-label=\"Действия выбранного узла\" aria-haspopup=\"menu\"",
    "en": "aria-label=\"Actions for the selected node\" aria-haspopup=\"menu\""
  },
  "knowledge-research.cad123465b9e": {
    "ru": "Действия",
    "en": "Actions"
  },
  "knowledge-research.d8f2327d230b": {
    "ru": "<aside class=\"k-catalog r-panel{v0}\" data-k-browser-mode=\"{v1}\"><header class=\"k-catalog-head\"><h2>Навигатор</h2><button data-k-action=\"follow-selection\" aria-pressed=\"{v2}\" title=\"Следить за выбранным элементом\" aria-label=\"Следить за выбранным элементом\">{v3}</button><button data-k-action=\"toggle-list\" aria-label=\"Свернуть навигатор\">{v4}</button></header><div class=\"r-tabs\" role=\"tablist\" aria-label=\"Навигация\">{v5}</div>{v6}<div class=\"r-search-row\"><label class=\"k-navigator-search r-search\">{v7}<input type=\"search\" data-k-filter=\"query\" value=\"{v8}\" placeholder=\"Название или путь\" aria-label=\"Найти в навигаторе\"></label><div class=\"r-tree-controls\">{v9}{v10}</div></div><small data-k-follow-status></small><div class=\"r-tree{v11}\">{v12}</div></aside>",
    "en": "<aside class=\"k-catalog r-panel{v0}\" data-k-browser-mode=\"{v1}\"><header class=\"k-catalog-head\"><h2>Navigator</h2><button data-k-action=\"follow-selection\" aria-pressed=\"{v2}\" title=\"Follow the selected element\" aria-label=\"Follow the selected element\">{v3}</button><button data-k-action=\"toggle-list\" aria-label=\"Collapse navigator\">{v4}</button></header><div class=\"r-tabs\" role=\"tablist\" aria-label=\"Navigation\">{v5}</div>{v6}<div class=\"r-search-row\"><label class=\"k-navigator-search r-search\">{v7}<input type=\"search\" data-k-filter=\"query\" value=\"{v8}\" placeholder=\"Name or path\" aria-label=\"Find in navigator\"></label><div class=\"r-tree-controls\">{v9}{v10}</div></div><small data-k-follow-status></small><div class=\"r-tree{v11}\">{v12}</div></aside>"
  },
  "knowledge-research.ee7e9d92da0e": {
    "ru": "Карты",
    "en": "Maps"
  },
  "knowledge-research.550ed2eaf608": {
    "ru": "Исходники",
    "en": "Sources"
  },
  "knowledge-research.9fe78c578dee": {
    "ru": "Архитектура",
    "en": "Architecture"
  },
  "knowledge-research.eb74b36053d2": {
    "ru": "<div class=\"r-label\">Элементы текущего холста</div>",
    "en": "<div class=\"r-label\">Elements on the current canvas</div>"
  },
  "knowledge-research.d7e119200116": {
    "ru": "class=\"r-icon\" aria-label=\"Свернуть всё дерево\"",
    "en": "class=\"r-icon\" aria-label=\"Collapse the entire tree\""
  },
  "knowledge-research.dc3eb5481c02": {
    "ru": "class=\"r-icon\" aria-label=\"Развернуть всё дерево\"",
    "en": "class=\"r-icon\" aria-label=\"Expand the entire tree\""
  },
  "knowledge-research.a998df6f5789": {
    "ru": "Развернуть всё",
    "en": "Expand all"
  },
  "knowledge-research.25d6b2af633b": {
    "ru": "<button class=\"k-tree-row r-nav-row\" data-r-open=\"\">{v0}<span>Обзор проекта</span></button><h3 class=\"r-label\">Подсистемы</h3>{v1}<h3 class=\"r-label\">Точки входа</h3>{v2}{v3}",
    "en": "<button class=\"k-tree-row r-nav-row\" data-r-open=\"\">{v0}<span>Project overview</span></button><h3 class=\"r-label\">Subsystems</h3>{v1}<h3 class=\"r-label\">Entry points</h3>{v2}{v3}"
  },
  "knowledge-research.9ae5e9c0b49f": {
    "ru": "Показать ещё · {v0} из {v1}",
    "en": "Show more · {v0} of {v1}"
  },
  "knowledge-research.e6f3cdafdb81": {
    "ru": "<p class=\"k-empty\" role=\"status\">Загружаем исходники…</p>",
    "en": "<p class=\"k-empty\" role=\"status\">Loading source code…</p>"
  },
  "knowledge-research.2fafe6f8453b": {
    "ru": "<p class=\"k-empty\">Сохранённых карт пока нет.</p>",
    "en": "<p class=\"k-empty\">No saved maps yet.</p>"
  },
  "knowledge-research.3568d5213115": {
    "ru": "Показать ещё подсистемы",
    "en": "Show more subsystems"
  },
  "knowledge-research.a075d9a805bb": {
    "ru": "<small>Раскройте подсистему</small>",
    "en": "<small>Expand the subsystem</small>"
  },
  "knowledge-research.784ad23b0b7b": {
    "ru": "<div class=\"r-service\"><div class=\"r-scope\">{v0}<strong>{v1}</strong><span>Версия {v2}</span></div><div class=\"r-service-actions\">{v3}{v4}{v5}<button data-k-action=\"refresh\" class=\"r-icon\" title=\"Перечитать данные\" aria-label=\"Перечитать данные\">{v6}</button><button data-k-action=\"scan\" class=\"r-icon\" title=\"Сканировать исходники\" aria-label=\"Сканировать исходники\"{v7}>{v8}</button><button data-k-action=\"diagnostics\" class=\"{v9}\" title=\"Состояние анализа\">{v10}<span>{v11}</span></button><button data-k-action=\"tools\" class=\"r-icon\" title=\"Инструменты\" aria-label=\"Инструменты\">{v12}</button></div></div>",
    "en": "<div class=\"r-service\"><div class=\"r-scope\">{v0}<strong>{v1}</strong><span>Version {v2}</span></div><div class=\"r-service-actions\">{v3}{v4}{v5}<button data-k-action=\"refresh\" class=\"r-icon\" title=\"Reload data\" aria-label=\"Reload data\">{v6}</button><button data-k-action=\"scan\" class=\"r-icon\" title=\"Scan sources\" aria-label=\"Scan sources\"{v7}>{v8}</button><button data-k-action=\"diagnostics\" class=\"{v9}\" title=\"Analysis status\">{v10}<span>{v11}</span></button><button data-k-action=\"tools\" class=\"r-icon\" title=\"Tools\" aria-label=\"Tools\">{v12}</button></div></div>"
  },
  "knowledge-research.7641ad9bafb2": {
    "ru": "Обзор проекта",
    "en": "Project overview"
  },
  "knowledge-research.8cdf6d474a2c": {
    "ru": "Элементы холста",
    "en": "Canvas elements"
  },
  "knowledge-research.5101a840d7a8": {
    "ru": "Исследования{v0}",
    "en": "Research{v0}"
  },
  "knowledge-research.c6db861f4828": {
    "ru": " · выполняются",
    "en": " · running"
  },
  "knowledge-research.4d9b952ce11a": {
    "ru": "Как пользоваться",
    "en": "How to use"
  },
  "knowledge-research.d7327abdc0fe": {
    "ru": "Анализ",
    "en": "Analysis"
  },
  "knowledge-research.6e3bf0065f31": {
    "ru": "Есть ограничения",
    "en": "Limitations exist"
  },
  "knowledge-research.8ff72bacb2e2": {
    "ru": "Сканирование…",
    "en": "Scanning…"
  },
  "knowledge-research.cde5a287889a": {
    "ru": "Структурировать карту",
    "en": "Structure the map"
  },
  "knowledge-research.537693697192": {
    "ru": "Свой запрос",
    "en": "Custom request"
  },
  "knowledge-research.d24987aec8c6": {
    "ru": "Объяснить связь",
    "en": "Explain a relationship"
  },
  "knowledge-research.942891d378c2": {
    "ru": "Описать сценарий",
    "en": "Describe a scenario"
  },
  "knowledge-research.4a192b8a2907": {
    "ru": "Предложить структуру подсистемы",
    "en": "Suggest a subsystem structure"
  },
  "knowledge-research.7016b14f38f6": {
    "ru": "Описать выбранный элемент",
    "en": "Describe the selected element"
  },
  "knowledge-research.4377319f6a00": {
    "ru": "Семантический анализ исходников",
    "en": "Semantic source analysis"
  },
  "knowledge-research.2d05f93e0776": {
    "ru": "Сохранённые статические связи",
    "en": "Stored static relationships"
  },
  "knowledge-research.88eced302fe1": {
    "ru": "Путь не найден",
    "en": "Path not found"
  },
  "knowledge-research.654faea50f57": {
    "ru": "Ошибка анализа",
    "en": "Analysis error"
  },
  "knowledge-research.4f35e860be9b": {
    "ru": "Операция не поддерживается",
    "en": "Operation not supported"
  },
  "knowledge-research.96df26e3fb17": {
    "ru": "Исходники изменились",
    "en": "Sources changed"
  },
  "knowledge-research.70646e10e5f1": {
    "ru": "Связей не найдено",
    "en": "No relationships found"
  },
  "knowledge-research.ef05d57959cf": {
    "ru": "Готово",
    "en": "Ready"
  },
  "knowledge-research.b3ce53956234": {
    "ru": "Прервано",
    "en": "Interrupted"
  },
  "knowledge-research.23a2a9bfcf74": {
    "ru": "Отменено",
    "en": "Cancelled"
  },
  "knowledge-research.bf22dfeeba8b": {
    "ru": "Ошибка",
    "en": "Failed"
  },
  "knowledge-research.bb7b6faa137c": {
    "ru": "Анализируется",
    "en": "Analyzing"
  },
  "knowledge-research.b22a2454bd69": {
    "ru": "В очереди",
    "en": "Queued"
  },
  "knowledge-research.b572dc513d84": {
    "ru": "Получаем результат",
    "en": "Retrieving result"
  },
  "knowledge-research.a207dbeaf97a": {
    "ru": "Запускается",
    "en": "Starting"
  },
  "knowledge-research.cf3bfd9f3a83": {
    "ru": "Исход требует проверки",
    "en": "Outcome needs review"
  },
  "knowledge-research.2ae8bedad7c9": {
    "ru": "Нужен ответ пользователя",
    "en": "User response needed"
  },
  "knowledge-research.b459ff8f254e": {
    "ru": "Завершено",
    "en": "Completed"
  },
  "knowledge-research.93b7fc7708db": {
    "ru": "Размышляет",
    "en": "Thinking"
  },
  "knowledge-research.599ca07b8dd2": {
    "ru": "Выполняется",
    "en": "Running"
  },
  "knowledge-research.b68a04c1feaa": {
    "ru": "Формирует ответ",
    "en": "Writing a response"
  },
  "knowledge-research.0605d178d4a7": {
    "ru": "Использует инструменты",
    "en": "Using tools"
  },
  "knowledge-research.0232a305412b": {
    "ru": "Работает",
    "en": "Working"
  },
  "knowledge-research.20f6bbebb946": {
    "ru": "Инициализация",
    "en": "Initializing"
  },
  "knowledge-research.88af1cc2a8a2": {
    "ru": "Принят",
    "en": "Accepted"
  },
  "knowledge-research.5ea5c68f20d4": {
    "ru": "Подготовка",
    "en": "Preparing"
  },
  "knowledge-workspace.ba286d542451": {
    "ru": "Изменить ширину панели сведений",
    "en": "Resize the information panel"
  },
  "knowledge-workspace.4340f3a1422d": {
    "ru": "Изменить ширину списка элементов",
    "en": "Resize the item list"
  },
  "knowledge.b251953efac8": {
    "ru": " участников",
    "en": " participants"
  },
  "knowledge.74be9ffaf6e4": {
    "ru": " совпадений · ",
    "en": " matches · "
  },
  "knowledge.f5ea1454f52a": {
    "ru": "Запрошен переносимый ZIP со статьями и вложениями.",
    "en": "A portable ZIP containing articles and attachments has been requested."
  },
  "knowledge.4508afe8b724": {
    "ru": "Запрошен ZIP только из ранее согласованных публичных статей. Внутренние связи и зависимости требуют отдельной проверки сервером.",
    "en": "A ZIP containing only previously approved public articles has been requested. Internal relationships and dependencies require a separate server check."
  },
  "knowledge.e5daf1f62bd8": {
    "ru": "Запрошена резервная копия с историей и вложениями.",
    "en": "A backup with history and attachments was requested."
  },
  "knowledge.ef9743554af1": {
    "ru": "ожидает запуска",
    "en": "waiting to start"
  },
  "knowledge.bd280ebe5bda": {
    "ru": "выполняется",
    "en": "running"
  },
  "knowledge.fd540b659be9": {
    "ru": "Сканирование: ",
    "en": "Scan: "
  },
  "knowledge.58d124f88027": {
    "ru": "Запрашиваем сканирование…",
    "en": "Requesting scan…"
  },
  "knowledge.a7d7b46ca86e": {
    "ru": "Сканирование уже запущено",
    "en": "A scan is already running"
  },
  "knowledge.0fefa6110ff2": {
    "ru": "Восстановлена новая версия ",
    "en": "Restored as a new version "
  },
  "knowledge.0a4ff224e19a": {
    "ru": "Восстановление заменит несохранённый черновик. Продолжить?",
    "en": "Restoring will replace the unsaved draft. Continue?"
  },
  "knowledge.5c38acb40bab": {
    "ru": "Загрузить сохранённую версию и отменить изменения этого черновика?",
    "en": "Load the saved version and discard changes to this draft?"
  },
  "knowledge.6b3110d5a472": {
    "ru": "Новый сценарий",
    "en": "New scenario"
  },
  "knowledge.15c048a3c028": {
    "ru": "Новая статья",
    "en": "New article"
  },
  "knowledge.bc6976f996ab": {
    "ru": "Сохранена версия ",
    "en": "Saved version "
  },
  "knowledge.bce74bf988d4": {
    "ru": "Импорт статей",
    "en": "Import articles"
  },
  "knowledge.9271ccf19216": {
    "ru": "Настройки знаний",
    "en": "Knowledge settings"
  },
  "knowledge.d04f6d2cd09a": {
    "ru": "Получаем данные…",
    "en": "Retrieving data…"
  },
  "knowledge.4e41077fa07f": {
    "ru": "Открываем раздел · ",
    "en": "Opening section · "
  },
  "knowledge.88946f395190": {
    "ru": "<p class=\"k-warning\">Список и контекст получены из разных версий. Обновите перед редактированием.</p>",
    "en": "<p class=\"k-warning\">The list and context come from different versions. Refresh before editing.</p>"
  },
  "knowledge.c9bf2e79c3ef": {
    "ru": "<div class=\"k-status\" role=\"status\">Версия знаний: {v0}{v1}{v2}</div>",
    "en": "<div class=\"k-status\" role=\"status\">Knowledge version: {v0}{v1}{v2}</div>"
  },
  "knowledge.aae8a7b9edfb": {
    "ru": " · Загрузка…",
    "en": " · Loading…"
  },
  "knowledge.d34b06e43b75": {
    "ru": " · Сохранение…",
    "en": " · Saving…"
  },
  "knowledge.e0f7cfbbb6eb": {
    "ru": "<article class=\"k-empty\"><h2>Выберите статью</h2><p>Создайте документ или подготовьте импорт существующего Markdown.</p></article>",
    "en": "<article class=\"k-empty\"><h2>Choose an article</h2><p>Create a document or prepare an import of existing Markdown.</p></article>"
  },
  "knowledge.a36142871b6f": {
    "ru": "<p>Возможности адаптеров пока не получены. Запустите сканирование.</p>",
    "en": "<p>Adapter capabilities have not been retrieved yet. Run a scan.</p>"
  },
  "knowledge.aeeb48c2d323": {
    "ru": "<p><strong>{v0}:</strong> {v1}{v2}{v3}. Методы и динамические вызовы не анализируются.</p>",
    "en": "<p><strong>{v0}:</strong> {v1}{v2}{v3}. Methods and dynamic calls are not analyzed.</p>"
  },
  "knowledge.dab0b47de1d8": {
    "ru": "инвентаризация файлов; подробные связи типов не извлекаются",
    "en": "file inventory; detailed type relationships are not extracted"
  },
  "knowledge.2d42bdaac217": {
    "ru": "файлы, классы и объявленные связи типов",
    "en": "files, classes and declared type relationships"
  },
  "knowledge.f7c42e060eb5": {
    "ru": " и точки входа",
    "en": " and entry points"
  },
  "knowledge.586a82dbf5c4": {
    "ru": " при доступном локальном JDK; фактическое покрытие показывает последнее сканирование",
    "en": " when a local JDK is available; the latest scan shows actual coverage"
  },
  "knowledge.ff17c05a6302": {
    "ru": "Другие языки",
    "en": "Other languages"
  },
  "knowledge.cecac946bcac": {
    "ru": "<div class=\"k-job{v0}\" role=\"status\"><strong>Сканирование: {v1}</strong>{v2}{v3}{v4}{v5}{v6}</div>",
    "en": "<div class=\"k-job{v0}\" role=\"status\"><strong>Scan: {v1}</strong>{v2}{v3}{v4}{v5}{v6}</div>"
  },
  "knowledge.e57bedc663c1": {
    "ru": "<small>Завершено: {v0}</small>",
    "en": "<small>Completed: {v0}</small>"
  },
  "knowledge.711307095bed": {
    "ru": "<p>Исходники или политика изменились во время сканирования; повторите обновление.</p>",
    "en": "<p>Sources or policy changed during the scan; run the update again.</p>"
  },
  "knowledge.fadbaebe858b": {
    "ru": "<details><summary>Ограничения / диагностика ({v0})</summary>{v1}</details>",
    "en": "<details><summary>Limitations / diagnostics ({v0})</summary>{v1}</details>"
  },
  "knowledge.857dc0885665": {
    "ru": "файлов без изменений",
    "en": "unchanged files"
  },
  "knowledge.9f0347ed213d": {
    "ru": "файлов разобрано",
    "en": "files parsed"
  },
  "knowledge.69b406975445": {
    "ru": "типов",
    "en": "types"
  },
  "knowledge.7e1ad316f1c8": {
    "ru": "файлов",
    "en": "files"
  },
  "knowledge.2f41c01eefa1": {
    "ru": "исходники изменились",
    "en": "source files changed"
  },
  "knowledge.a13c37d406f5": {
    "ru": "прервано",
    "en": "interrupted"
  },
  "knowledge.44d4090ae9e4": {
    "ru": "ошибка",
    "en": "error"
  },
  "knowledge.de2280e6a5a0": {
    "ru": "завершено с ограничениями",
    "en": "completed with limitations"
  },
  "knowledge.5f9b6607de24": {
    "ru": "завершено",
    "en": "completed"
  },
  "knowledge.e3b9f87518c5": {
    "ru": "<section class=\"k-auxiliary\"><h2>Импорт Markdown / HTML / текста</h2><label>Относительные пути (по одному в строке)<textarea data-k-paths rows=\"4\">{v0}</textarea></label><button data-k-action=\"import-preview\"{v1}>Подготовить предпросмотр</button><button data-k-action=\"close-panel\">Закрыть</button>\n      {v2}</section>",
    "en": "<section class=\"k-auxiliary\"><h2>Import Markdown / HTML / text</h2><label>Relative paths (one per line)<textarea data-k-paths rows=\"4\">{v0}</textarea></label><button data-k-action=\"import-preview\"{v1}>Prepare preview</button><button data-k-action=\"close-panel\">Close</button>\n      {v2}</section>"
  },
  "knowledge.8f568f9af4e0": {
    "ru": "<p>Предпросмотр {v0} · версия {v1}. Новые статьи будут добавлены. Обновления существующих статей требуют выбора.</p>{v2}<button data-k-action=\"import-apply\"{v3}>Применить проверенный импорт</button>",
    "en": "<p>Preview {v0} · version {v1}. New articles will be added. Updates to existing articles require a choice.</p>{v2}<button data-k-action=\"import-apply\"{v3}>Apply verified import</button>"
  },
  "knowledge.79475f6362fd": {
    "ru": "<p>{v0}</p><p>Сохранено файлов: {v1}. Просмотр доступен после импорта.</p>{v2}",
    "en": "<p>{v0}</p><p>Saved files: {v1}. Viewing is available after import.</p>{v2}"
  },
  "knowledge.e3991bad15d9": {
    "ru": "<p>Внешние ресурсы заблокированы в изолированном просмотре.</p>",
    "en": "<p>External resources are blocked in the isolated view.</p>"
  },
  "knowledge.4f0548d13284": {
    "ru": "Статья",
    "en": "Article"
  },
  "knowledge.be9e952a96bf": {
    "ru": "HTML-комплект",
    "en": "HTML-bundle"
  },
  "knowledge.28d1d87dba87": {
    "ru": "<label class=\"k-check\"><input type=\"checkbox\" data-k-import-select=\"{v0}\"{v1}>Применить проверенное обновление</label><pre>{v2}</pre>",
    "en": "<label class=\"k-check\"><input type=\"checkbox\" data-k-import-select=\"{v0}\"{v1}>Apply the verified update</label><pre>{v2}</pre>"
  },
  "knowledge.543cdba16383": {
    "ru": "<header class=\"k-inspector-head\"><h2>Настройки знаний</h2><button data-k-action=\"close-panel\">{v0}Закрыть</button></header><p>Правила анализа и структура разделов этого проекта. Изменения правил применяются при следующем сканировании.</p><dl class=\"k-policy-summary\"><dt>Компоненты</dt><dd>{v1}</dd><dt>Точки входа</dt><dd>{v2}</dd><dt>Разделы документации</dt><dd>{v3}</dd></dl><details><summary>{v4}Редактировать правила анализа</summary><p>Компоненты задают смысловые блоки и пути исходников. Точки входа задают начало обзора. Исключённые каталоги не сканируются.</p><label>Конфигурация проекта<textarea data-k-policy rows=\"12\" spellcheck=\"false\">{v5}</textarea></label><button data-k-action=\"save-policy\"{v6}>{v7}Сохранить настройки</button></details>",
    "en": "<header class=\"k-inspector-head\"><h2>Knowledge settings</h2><button data-k-action=\"close-panel\">{v0}Close</button></header><p>Analysis rules and section structure for this project. Rule changes apply on the next scan.</p><dl class=\"k-policy-summary\"><dt>Components</dt><dd>{v1}</dd><dt>Entry points</dt><dd>{v2}</dd><dt>Documentation sections</dt><dd>{v3}</dd></dl><details><summary>{v4}Edit analysis rules</summary><p>Components define logical blocks and source paths. Entry points define where the overview starts. Excluded directories are not scanned.</p><label>Project configuration<textarea data-k-policy rows=\"12\" spellcheck=\"false\">{v5}</textarea></label><button data-k-action=\"save-policy\"{v6}>{v7}Save settings</button></details>"
  },
  "knowledge.9d9561c0bf9f": {
    "ru": "Пока не заданы",
    "en": "Not set yet"
  },
  "knowledge.4e90074f740b": {
    "ru": "Инструменты",
    "en": "Tools"
  },
  "knowledge.b3e305d6ff4a": {
    "ru": "<header class=\"k-inspector-head\"><h2>Инструменты {v0}</h2><button data-k-action=\"close-panel\" aria-label=\"Закрыть\" title=\"Закрыть\">{v1}</button></header><div class=\"k-tool-grid\">{v2}{v3}</div>",
    "en": "<header class=\"k-inspector-head\"><h2>Tools {v0}</h2><button data-k-action=\"close-panel\" aria-label=\"Close\" title=\"Close\">{v1}</button></header><div class=\"k-tool-grid\">{v2}{v3}</div>"
  },
  "knowledge.cfbb85a2a060": {
    "ru": "документации",
    "en": "of the documentation"
  },
  "knowledge.74c31d8580c2": {
    "ru": "архитектуры",
    "en": "of the architecture"
  },
  "knowledge.9e51ec957ada": {
    "ru": "<button data-r-action=\"providers\">{v0}<strong>Языковые провайдеры</strong><small>Подключённые языки и настройка сервера</small></button>",
    "en": "<button data-r-action=\"providers\">{v0}<strong>Language providers</strong><small>Connected languages and server setup</small></button>"
  },
  "knowledge.0c0cb4d8201a": {
    "ru": "Полная копия базы знаний",
    "en": "Full copy of the knowledge base"
  },
  "knowledge.9eb508eda2fc": {
    "ru": "Резервная копия",
    "en": "Backup"
  },
  "knowledge.0a2e2121f639": {
    "ru": "Только согласованные публичные статьи",
    "en": "Only approved public articles"
  },
  "knowledge.b00a2d5a1f74": {
    "ru": "Публичный ZIP",
    "en": "Public ZIP"
  },
  "knowledge.9149d8d7ee7d": {
    "ru": "Документация и архитектурные факты",
    "en": "Documentation and architectural facts"
  },
  "knowledge.1f67cc552aef": {
    "ru": "Экспорт ZIP",
    "en": "ZIP export"
  },
  "knowledge.932059352b8e": {
    "ru": "Компоненты, точки входа и правила анализа",
    "en": "Components, entry points, and analysis rules"
  },
  "knowledge.3115c8dce126": {
    "ru": "Предпросмотр Markdown и текста",
    "en": "Preview Markdown and text"
  },
  "knowledge.ad317ef5316b": {
    "ru": "Импортировать статьи",
    "en": "Import articles"
  },
  "knowledge.0981c73c8915": {
    "ru": "Добавить статью в выбранный раздел",
    "en": "Add an article to the selected section"
  },
  "knowledge.9d5fecb3d309": {
    "ru": "Создать страницу",
    "en": "Create page"
  },
  "knowledge.6a7450a24a0a": {
    "ru": "Сохранить смысловую последовательность",
    "en": "Save a meaningful sequence"
  },
  "knowledge.ee7885b161a7": {
    "ru": "Обновить факты локального анализа",
    "en": "Update local analysis facts"
  },
  "knowledge.8fbe51c7cdda": {
    "ru": "Сканировать исходники",
    "en": "Scan sources"
  },
  "knowledge.bfdf0e3a0585": {
    "ru": "Состояние анализа",
    "en": "Analysis status"
  },
  "knowledge.423fbd33023a": {
    "ru": "<header class=\"k-inspector-head\"><h2>Состояние анализа</h2><button data-k-action=\"close-panel\" aria-label=\"Закрыть\">{v0}Закрыть</button></header><div class=\"k-status\">Версия знаний: {v1}{v2}</div>{v3}{v4}<h3>Покрытие сканера</h3>{v5}",
    "en": "<header class=\"k-inspector-head\"><h2>Analysis status</h2><button data-k-action=\"close-panel\" aria-label=\"Close\">{v0}Close</button></header><div class=\"k-status\">Knowledge version: {v1}{v2}</div>{v3}{v4}<h3>Scanner coverage</h3>{v5}"
  },
  "knowledge.a3e01ea25a8a": {
    "ru": "<p>Загрузка…</p>",
    "en": "<p>Loading…</p>"
  },
  "knowledge.b373a5d81881": {
    "ru": "Изменить роль в проекте",
    "en": "Change the project role"
  },
  "knowledge.ae309a1ed58e": {
    "ru": "<header class=\"k-inspector-head\"><h2>Роль в проекте</h2><button data-k-action=\"close-panel\" aria-label=\"Закрыть\">{v0}Закрыть</button></header><label>Описание<textarea id=\"k-description\" data-k-field=\"description\" maxlength=\"12000\" rows=\"7\" placeholder=\"Коротко опишите назначение элемента\">{v1}</textarea></label><div class=\"k-actions\"><button class=\"k-primary\" data-k-action=\"save-description\"{v2}>{v3}Сохранить{v4}</button><button data-k-action=\"close-panel\">Отмена</button></div>",
    "en": "<header class=\"k-inspector-head\"><h2>Role in project</h2><button data-k-action=\"close-panel\" aria-label=\"Close\">{v0}Close</button></header><label>Description<textarea id=\"k-description\" data-k-field=\"description\" maxlength=\"12000\" rows=\"7\" placeholder=\"Briefly describe the element's purpose\">{v1}</textarea></label><div class=\"k-actions\"><button class=\"k-primary\" data-k-action=\"save-description\"{v2}>{v3}Save{v4}</button><button data-k-action=\"close-panel\">Cancel</button></div>"
  },
  "knowledge.ea6fb5a1eb23": {
    "ru": "<article class=\"k-inspector k-multi-selection\"><header class=\"k-selection-header\"><h2>Выбрано {v0} элементов</h2><button data-k-action=\"toggle-inspector\" aria-label=\"Закрыть панель сведений\">{v1}</button></header>\n      <div class=\"k-actions\"><button data-k-action=\"focus\">{v2}Вписать выбор</button><button data-k-action=\"clear-selection\">Снять выбор</button></div>\n      <section class=\"k-inspector-section\"><h3>Состав выбора</h3><p>{v3} узлов · {v4} групп по типам</p>{v5}<p>{v6} подсистем · {v7} точек входа · {v8} узлов с исходником</p></section>\n      {v9}\n      <section class=\"k-inspector-section\"><h3>Связи внутри выбора · {v10}</h3>{v11}{v12}</section>\n      <section class=\"k-inspector-section\"><h3>Связи с остальной картой</h3><details><summary>Входящие · {v13}</summary>{v14}</details><details><summary>Исходящие · {v15}</summary>{v16}</details></section>\n      <p class=\"k-selection-note\">Группы включают загруженное содержимое; каждый узел и связь учитываются один раз. Статистика относится к текущей карте. Узлы и группы размещаются автоматически; кнопка «Компоновка» обновляет их расположение. Правая кнопка мыши перемещает камеру.</p></article>",
    "en": "<article class=\"k-inspector k-multi-selection\"><header class=\"k-selection-header\"><h2> {v0} items</h2><button data-k-action=\"toggle-inspector\" aria-label=\"Close the details panel\">{v1}</button></header>\n      <div class=\"k-actions\"><button data-k-action=\"focus\">{v2}Fit selection</button><button data-k-action=\"clear-selection\">Clear selection</button></div>\n      <section class=\"k-inspector-section\"><h3>Selection contents</h3><p>{v3} nodes · {v4} groups by type</p>{v5}<p>{v6} subsystems · {v7} entry points · {v8} nodes with source code</p></section>\n      {v9}\n      <section class=\"k-inspector-section\"><h3>Relationships within selection · {v10}</h3>{v11}{v12}</section>\n      <section class=\"k-inspector-section\"><h3>Relationships with the rest of the map</h3><details><summary>Incoming · {v13}</summary>{v14}</details><details><summary>Outgoing · {v15}</summary>{v16}</details></section>\n      <p class=\"k-selection-note\">Groups include loaded content; each node and relationship is counted once. Statistics apply to the current map. Nodes and groups are placed automatically; Layout updates their positions. The right mouse button moves the camera.</p></article>"
  },
  "knowledge.752103b7f5e6": {
    "ru": "<section class=\"k-inspector-section\"><h3>Выбранные связи · {v0}</h3>{v1}</section>",
    "en": "<section class=\"k-inspector-section\"><h3>Selected relationships · {v0}</h3>{v1}</section>"
  },
  "knowledge.ec3824dc268e": {
    "ru": "<p>В агрегированных рёбрах: {v0} статических отношений исходников.</p>",
    "en": "<p>In aggregated edges: {v0} static source code relationships.</p>"
  },
  "knowledge.d13620cdf7c1": {
    "ru": "<dt>Нет</dt><dd>0</dd>",
    "en": "<dt>None</dt><dd>0</dd>"
  },
  "knowledge.ee42062e1734": {
    "ru": "<header class=\"k-selection-header\"><h2>Сведения</h2><button data-k-action=\"toggle-inspector\" aria-label=\"Закрыть панель сведений\">{v0}</button></header><div class=\"k-empty\">Выберите узел или связь, чтобы увидеть роль, исходник и связанные статьи.</div>",
    "en": "<header class=\"k-selection-header\"><h2>Details</h2><button data-k-action=\"toggle-inspector\" aria-label=\"Close the details panel\">{v0}</button></header><div class=\"k-empty\">Choose a node or relationship to see its role, source, and related articles.</div>"
  },
  "knowledge.af968b8e9faf": {
    "ru": "<article class=\"k-inspector\"><header class=\"k-selection-header\"><h2>{v0}</h2><button data-k-action=\"toggle-inspector\" aria-label=\"Закрыть панель сведений\" title=\"Закрыть панель сведений\">{v1}</button></header><div class=\"k-item-meta\"><span data-k-type=\"{v2}\">{v3}</span><span>{v4}</span>{v5}</div>\n      {v6}\n      {v7}\n      {v8}{v9}{v10}\n      {v11}\n      {v12}\n      {v13}\n      {v14}\n      {v15}\n      {v16}\n      {v17}{v18}\n      {v19}{v20}{v21}</article>",
    "en": "<article class=\"k-inspector\"><header class=\"k-selection-header\"><h2>{v0}</h2><button data-k-action=\"toggle-inspector\" aria-label=\"Close the details panel\" title=\"Close the details panel\">{v1}</button></header><div class=\"k-item-meta\"><span data-k-type=\"{v2}\">{v3}</span><span>{v4}</span>{v5}</div>\n      {v6}\n      {v7}\n      {v8}{v9}{v10}\n      {v11}\n      {v12}\n      {v13}\n      {v14}\n      {v15}\n      {v16}\n      {v17}{v18}\n      {v19}{v20}{v21}</article>"
  },
  "knowledge.a5e51710d3c8": {
    "ru": "Сценарий",
    "en": "Scenario"
  },
  "knowledge.f83d147689b5": {
    "ru": "Авторская модель",
    "en": "Authored model"
  },
  "knowledge.a97550017e68": {
    "ru": "Группировка",
    "en": "Grouping"
  },
  "knowledge.4649615d4cdd": {
    "ru": "Из исходников",
    "en": "From source code"
  },
  "knowledge.00ddbc8b35e1": {
    "ru": "<span>Точка входа</span>",
    "en": "<span>Entry point</span>"
  },
  "knowledge.626cda060f0c": {
    "ru": "Компонент",
    "en": "Component"
  },
  "knowledge.7920665774c5": {
    "ru": "<details class=\"k-evidence\"><summary>Версия файла</summary><p class=\"k-source\">{v0}</p></details>",
    "en": "<details class=\"k-evidence\"><summary>File version</summary><p class=\"k-source\">{v0}</p></details>"
  },
  "knowledge.0b5267f774e0": {
    "ru": "Исходник",
    "en": "Source"
  },
  "knowledge.d25ea8172e59": {
    "ru": "<p class=\"k-warning\">Источник отсутствует в последнем сканировании.</p>",
    "en": "<p class=\"k-warning\">The source is missing from the latest scan.</p>"
  },
  "knowledge.a11835c117d5": {
    "ru": "<p class=\"k-warning\">Исходники изменились. Обновите анализ.</p>",
    "en": "<p class=\"k-warning\">Source files changed. Refresh the analysis.</p>"
  },
  "knowledge.60d3cb70767b": {
    "ru": "<p class=\"k-warning\">Внешняя или неоднозначная зависимость.</p>",
    "en": "<p class=\"k-warning\">External or ambiguous dependency.</p>"
  },
  "knowledge.49107b030f7e": {
    "ru": "<p class=\"k-warning\">Есть несохранённые изменения{v0}.</p>",
    "en": "<p class=\"k-warning\">There are unsaved changes{v0}.</p>"
  },
  "knowledge.0a9c723d632a": {
    "ru": " · версия знаний изменилась",
    "en": " · the knowledge version changed"
  },
  "knowledge.3d7716c98a08": {
    "ru": "<div class=\"k-actions\"><button data-k-action=\"edit-role-description\" data-k-role-id=\"{v0}\">{v1}Изменить</button>{v2}<button data-k-action=\"history\" data-k-role-id=\"{v3}\">{v4}История</button></div>",
    "en": "<div class=\"k-actions\"><button data-k-action=\"edit-role-description\" data-k-role-id=\"{v0}\">{v1}Change</button>{v2}<button data-k-action=\"history\" data-k-role-id=\"{v3}\">{v4}History</button></div>"
  },
  "knowledge.807ec017e240": {
    "ru": "<button data-k-action=\"save\" data-k-role-id=\"{v0}\"{v1}>{v2}Сохранить *</button>",
    "en": "<button data-k-action=\"save\" data-k-role-id=\"{v0}\"{v1}>{v2}Save *</button>"
  },
  "knowledge.c6826c783794": {
    "ru": "Показать ещё",
    "en": "Show more"
  },
  "knowledge.36c25d9ffcfd": {
    "ru": "Свернуть",
    "en": "Collapse"
  },
  "knowledge.f8e60bc2a232": {
    "ru": "Роль в проекте",
    "en": "Role in project"
  },
  "knowledge.4f875695055b": {
    "ru": "Описание пока не добавлено.",
    "en": "No description added yet."
  },
  "knowledge.5014a1bdc8f3": {
    "ru": "<p class=\"k-empty\">Исходные строки не указаны.</p>",
    "en": "<p class=\"k-empty\">No source lines specified.</p>"
  },
  "knowledge.f74456ae7d60": {
    "ru": "Доказательства",
    "en": "Evidence"
  },
  "knowledge.bc0c40581492": {
    "ru": "Направление",
    "en": "Direction"
  },
  "knowledge.0c99d07cf18f": {
    "ru": "<label>Название<input data-k-field=\"title\" value=\"{v0}\"></label><label>Тип представления<input data-k-field=\"viewType\" value=\"{v1}\"></label><label>Узлы (ID)<textarea data-k-field=\"nodeIds\" rows=\"2\">{v2}</textarea></label><label>Порядок связей (ID)<textarea data-k-field=\"orderedEdges\" rows=\"2\">{v3}</textarea></label><ol class=\"k-flow\">{v4}</ol>",
    "en": "<label>Title<input data-k-field=\"title\" value=\"{v0}\"></label><label>View type<input data-k-field=\"viewType\" value=\"{v1}\"></label><label>Nodes (IDs)<textarea data-k-field=\"nodeIds\" rows=\"2\">{v2}</textarea></label><label>Relationship order (IDs)<textarea data-k-field=\"orderedEdges\" rows=\"2\">{v3}</textarea></label><ol class=\"k-flow\">{v4}</ol>"
  },
  "knowledge.fed3ab900107": {
    "ru": "<nav class=\"k-links\" aria-label=\"Связанные документы\">{v0}</nav>",
    "en": "<nav class=\"k-links\" aria-label=\"Related documents\">{v0}</nav>"
  },
  "knowledge.aceb6c1af609": {
    "ru": "<p class=\"k-empty\">Связанных статей пока нет.</p>",
    "en": "<p class=\"k-empty\">No related articles yet.</p>"
  },
  "knowledge.b123be6f8236": {
    "ru": "Документация",
    "en": "Documentation"
  },
  "knowledge.56fe4b0b5653": {
    "ru": "Исходящие связи",
    "en": "Outgoing relationships"
  },
  "knowledge.2391e3a2188b": {
    "ru": "Входящие связи",
    "en": "Incoming relationships"
  },
  "knowledge.f113dbe6c689": {
    "ru": "<details class=\"k-inspector-section\"><summary>Состав подсистемы на текущей карте · {v0} узлов</summary><p>{v1} внутренних связей · {v2} входящих · {v3} исходящих</p></details>",
    "en": "<details class=\"k-inspector-section\"><summary>Subsystem contents on the current map · {v0} nodes</summary><p>{v1} internal relationships · {v2} incoming · {v3} outgoing</p></details>"
  },
  "knowledge.9714ca3171b8": {
    "ru": "<pre>{v0}</pre><button data-k-action=\"restore\">Восстановить как новую версию</button>",
    "en": "<pre>{v0}</pre><button data-k-action=\"restore\">Restore as a new version</button>"
  },
  "knowledge.553f67d234e4": {
    "ru": "Историческая версия ",
    "en": "Historical version "
  },
  "knowledge.99c15c690078": {
    "ru": "<div class=\"k-relation-row\"><button data-k-select=\"{v0}\" title=\"Открыть описание связи\"><span class=\"k-relation-kind\" data-k-edge=\"{v1}\">{v2}</span>{v3}</button><a data-k-select=\"{v4}\" href=\"{v5}\">{v6}</a>{v7}</div>",
    "en": "<div class=\"k-relation-row\"><button data-k-select=\"{v0}\" title=\"Open the relationship description\"><span class=\"k-relation-kind\" data-k-edge=\"{v1}\">{v2}</span>{v3}</button><a data-k-select=\"{v4}\" href=\"{v5}\">{v6}</a>{v7}</div>"
  },
  "knowledge.72369a5ce90f": {
    "ru": "<details class=\"k-evidence\"><summary>Исходные строки</summary>{v0}</details>",
    "en": "<details class=\"k-evidence\"><summary>Source lines</summary>{v0}</details>"
  },
  "knowledge.fa67bcc61ea0": {
    "ru": "<section class=\"k-graph-panel\">{v0}<div class=\"k-actions k-graph-tools\"><div class=\"k-tool-group\" role=\"group\" aria-label=\"Навигация\"><button data-k-action=\"graph-back\" aria-label=\"Назад по графу\" title=\"Назад\"{v1}>{v2}</button><button data-k-action=\"graph-forward\" aria-label=\"Вперёд по графу\" title=\"Вперёд\"{v3}>{v4}</button><button data-k-action=\"zoom-out\" aria-label=\"Уменьшить\">−</button><button data-k-action=\"zoom-in\" aria-label=\"Увеличить\">+</button></div><div class=\"k-tool-group\" role=\"group\" aria-label=\"Управление картой\"><button data-k-action=\"fit\" aria-label=\"Вписать все отображаемые узлы\">{v5}Вписать всё</button><button data-k-action=\"focus\" title=\"F — вписать выбранные узлы; без выбора — всё\">{v6}Фокус</button><button data-k-action=\"open-canvas\">{v7}Открыть выбранное</button><button data-k-action=\"auto-layout\">{v8}Автокомпоновка</button></div><button data-k-action=\"toggle-inspector\" aria-label=\"Панель сведений\" aria-expanded=\"{v9}\">{v10}Сведения</button><details class=\"k-graph-info\"><summary>{v11}Вид</summary><div class=\"k-info-content k-view-options\"><p>Размещение: ELK · ортогональное</p><p>Связи: ортогональные со скруглением. Вложенные связи и петли — фиксированная компактная кривая.</p><label>Группировка<select data-k-group-by aria-label=\"Группировка\"><option value=\"components\"{v12}>Компоненты</option><option value=\"types\"{v13}>Компоненты и типы</option><option value=\"none\"{v14}>Без рамок</option></select></label><small data-k-layout-active>Активная компоновка: {v15}</small></div></details>{v16}{v17}<details class=\"k-graph-info k-participants-menu\" data-k-participants-menu><summary>На схеме ({v18})</summary><div class=\"k-info-content k-participants-tree\" data-k-participants data-k-browser-mode=\"graph\"><label class=\"k-navigator-search\">Найти на схеме<input data-k-find-on-map value=\"{v19}\" placeholder=\"Название или путь\"></label><small data-k-find-count>{v20} совпадений · {v21} участников</small><small data-k-follow-status></small><div data-k-participant-rows>{v22}</div></div></details>{v23}<span class=\"k-graph-count\">Загружено {v24} · показано {v25} узлов{v26} · {v27} связей</span></div><p data-k-canvas-selection role=\"status\" hidden></p><div class=\"k-node-actions\" data-k-node-actions hidden>{v28}<button data-k-action=\"focus\" aria-label=\"Фокус на выбранном узле\" title=\"Фокус на выбранном узле · F\">{v29}</button><button data-k-action=\"open-canvas\" aria-label=\"Открыть выбранный узел\" title=\"Открыть выбранный узел\">{v30}</button><button data-k-action=\"more-branch\" aria-label=\"Показать ещё связи\" title=\"Загрузить следующую часть ветви\" hidden>Ещё</button><button data-k-action=\"collapse-branch\" aria-label=\"Свернуть ветку\" title=\"Свернуть ветку\">{v31}</button></div>\n      {v32}\n      {v33}\n      </section>",
    "en": "<section class=\"k-graph-panel\">{v0}<div class=\"k-actions k-graph-tools\"><div class=\"k-tool-group\" role=\"group\" aria-label=\"Navigation\"><button data-k-action=\"graph-back\" aria-label=\"Back through the graph\" title=\"Back\"{v1}>{v2}</button><button data-k-action=\"graph-forward\" aria-label=\"Forward through the graph\" title=\"Forward\"{v3}>{v4}</button><button data-k-action=\"zoom-out\" aria-label=\"Zoom out\">−</button><button data-k-action=\"zoom-in\" aria-label=\"Zoom in\">+</button></div><div class=\"k-tool-group\" role=\"group\" aria-label=\"Map controls\"><button data-k-action=\"fit\" aria-label=\"Fit all displayed nodes\">{v5}Fit all</button><button data-k-action=\"focus\" title=\"F — fit selected nodes; fit all if none are selected\">{v6}Focus</button><button data-k-action=\"open-canvas\">{v7}Open selection</button><button data-k-action=\"auto-layout\">{v8}Auto layout</button></div><button data-k-action=\"toggle-inspector\" aria-label=\"Details panel\" aria-expanded=\"{v9}\">{v10}Details</button><details class=\"k-graph-info\"><summary>{v11}View</summary><div class=\"k-info-content k-view-options\"><p>Layout: ELK · orthogonal</p><p>Relationships: orthogonal with rounded corners. Nested relationships and loops use a fixed compact curve.</p><label>Grouping<select data-k-group-by aria-label=\"Grouping\"><option value=\"components\"{v12}>Components</option><option value=\"types\"{v13}>Components and types</option><option value=\"none\"{v14}>No borders</option></select></label><small data-k-layout-active>Active layout: {v15}</small></div></details>{v16}{v17}<details class=\"k-graph-info k-participants-menu\" data-k-participants-menu><summary>On the diagram ({v18})</summary><div class=\"k-info-content k-participants-tree\" data-k-participants data-k-browser-mode=\"graph\"><label class=\"k-navigator-search\">Find on the diagram<input data-k-find-on-map value=\"{v19}\" placeholder=\"Name or path\"></label><small data-k-find-count>{v20} matches · {v21} participants</small><small data-k-follow-status></small><div data-k-participant-rows>{v22}</div></div></details>{v23}<span class=\"k-graph-count\">Loaded {v24} · shown {v25} nodes{v26} · {v27} relationships</span></div><p data-k-canvas-selection role=\"status\" hidden></p><div class=\"k-node-actions\" data-k-node-actions hidden>{v28}<button data-k-action=\"focus\" aria-label=\"Focus on the selected node\" title=\"Focus on the selected node · F\">{v29}</button><button data-k-action=\"open-canvas\" aria-label=\"Open the selected node\" title=\"Open the selected node\">{v30}</button><button data-k-action=\"more-branch\" aria-label=\"Show more relationships\" title=\"Load the next part of the branch\" hidden>More</button><button data-k-action=\"collapse-branch\" aria-label=\"Collapse branch\" title=\"Collapse branch\">{v31}</button></div>\n      {v32}\n      {v33}\n      </section>"
  },
  "knowledge.301b1e213147": {
    "ru": "Направленная",
    "en": "Directed"
  },
  "knowledge.17859e5e0a99": {
    "ru": "Сетка · нет связей",
    "en": "Grid · no relationships"
  },
  "knowledge.a9a5abbd358c": {
    "ru": "ELK · направленная",
    "en": "ELK · directed"
  },
  "knowledge.16f1d7d50ee2": {
    "ru": "fCoSE · вложенная",
    "en": "fCoSE · nested"
  },
  "knowledge.8570951c0e20": {
    "ru": "Силовая",
    "en": "Force-directed"
  },
  "knowledge.002864e2866d": {
    "ru": "<button data-k-action=\"more-code\">Ещё код</button><span class=\"k-warning\">Показана часть кода</span>",
    "en": "<button data-k-action=\"more-code\">More code</button><span class=\"k-warning\">Part of the code is shown</span>"
  },
  "knowledge.d9d36a4e0f95": {
    "ru": " рамок",
    "en": " borders"
  },
  "knowledge.49230ba6f344": {
    "ru": "<button data-k-action=\"expand-direct\" data-k-branch-mode=\"{v0}\" aria-label=\"Раскрыть: {v1}\" title=\"{v2}\" disabled>{v3}</button>",
    "en": "<button data-k-action=\"expand-direct\" data-k-branch-mode=\"{v0}\" aria-label=\"Expand: {v1}\" title=\"{v2}\" disabled>{v3}</button>"
  },
  "knowledge.816655bd716f": {
    "ru": "Структура",
    "en": "Structure"
  },
  "knowledge.db92aca77ded": {
    "ru": "<div class=\"k-graph\" data-k-cy role=\"group\" aria-label=\"Граф архитектуры. Для выбора клавиатурой используйте список На схеме.\"><div class=\"k-group-labels\" data-k-group-labels aria-hidden=\"true\"></div></div>",
    "en": "<div class=\"k-graph\" data-k-cy role=\"group\" aria-label=\"Architecture graph. To select items with the keyboard, use the On the diagram list.\"><div class=\"k-group-labels\" data-k-group-labels aria-hidden=\"true\"></div></div>"
  },
  "knowledge.27f2e5537850": {
    "ru": "<details class=\"k-graph-info\"><summary>Легенда</summary><div class=\"k-info-content\"><div class=\"k-graph-legend\" aria-label=\"Легенда графа\">{v0}<span>Цвет карточки — тип объекта. У интерфейса пунктирная рамка, у внешнего типа — точечная. Выбор отмечен золотой рамкой.</span><span>Стрелка — направление связи; сплошная — факт из кода, пунктирная — авторская связь.</span></div><div class=\"k-graph-legend\"><span data-k-edge=\"inheritance\">Наследование / реализация</span><span data-k-edge=\"dependency\">Использование / зависимость</span><span data-k-edge=\"imports\">Импорт</span><span data-k-edge=\"contains\">Содержит</span><span data-k-edge=\"action\">Авторская связь / действие</span><span>Подписи связи показаны при выборе или наведении.</span></div></div></details>\n      <details class=\"k-graph-info k-graph-relations\"><summary>Связи ({v1})</summary><div class=\"k-info-content\">{v2}{v3}</div></details>",
    "en": "<details class=\"k-graph-info\"><summary>Legend</summary><div class=\"k-info-content\"><div class=\"k-graph-legend\" aria-label=\"Graph legend\">{v0}<span>Card color indicates object type. Interfaces have dashed borders; external types have dotted borders. Selection is marked with a gold border.</span><span>Arrows indicate relationship direction; solid lines indicate facts from code, and dashed lines indicate authored relationships.</span></div><div class=\"k-graph-legend\"><span data-k-edge=\"inheritance\">Inheritance / implementation</span><span data-k-edge=\"dependency\">Usage / dependency</span><span data-k-edge=\"imports\">Import</span><span data-k-edge=\"contains\">Contains</span><span data-k-edge=\"action\">Authored relationship / action</span><span>Relationship labels appear on selection or hover.</span></div></div></details>\n      <details class=\"k-graph-info k-graph-relations\"><summary>Relations ({v1})</summary><div class=\"k-info-content\">{v2}{v3}</div></details>"
  },
  "knowledge.6b958a8a9791": {
    "ru": "<p class=\"k-warning\">Связи получены не полностью. Обновите данные или уточните выбранный элемент.</p>",
    "en": "<p class=\"k-warning\">Relationships were not fully retrieved. Refresh the data or refine the selected item.</p>"
  },
  "knowledge.09f88cd01006": {
    "ru": "<p>Связей в этом представлении нет.</p>",
    "en": "<p>There are no relationships in this view.</p>"
  },
  "knowledge.c18afab9e18b": {
    "ru": "Подготавливаем выбранный раздел…",
    "en": "Preparing the selected section…"
  },
  "knowledge.9caf0bf93bd8": {
    "ru": "Не удалось открыть раздел. Перечитайте данные.",
    "en": "Could not open the section. Reload the data."
  },
  "knowledge.6a4da0ccebfc": {
    "ru": "<details class=\"k-graph-info\" data-k-filters-menu><summary>Фильтры{v0}</summary><div class=\"k-info-content k-view-options\">{v1}</div></details>",
    "en": "<details class=\"k-graph-info\" data-k-filters-menu><summary>Filters{v0}</summary><div class=\"k-info-content k-view-options\">{v1}</div></details>"
  },
  "knowledge.602dc9c88c0e": {
    "ru": "{v0}<fieldset><legend>Связи текущей карты</legend>{v1}</fieldset><label>Направление{v2}<select data-k-edge-direction data-k-edge-anchor=\"{v3}\">{v4}</select></label><button data-k-action=\"reset-filters\">Сбросить фильтры</button>",
    "en": "{v0}<fieldset><legend>Relationships on the current map</legend>{v1}</fieldset><label>Direction{v2}<select data-k-edge-direction data-k-edge-anchor=\"{v3}\">{v4}</select></label><button data-k-action=\"reset-filters\">Reset filters</button>"
  },
  "knowledge.4e94a7dab9af": {
    "ru": "<fieldset><legend>Типы участников текущей карты</legend>{v0}</fieldset>",
    "en": "<fieldset><legend>Participant types on the current map</legend>{v0}</fieldset>"
  },
  "knowledge.920c27c1a0d4": {
    "ru": " · выберите участника на схеме",
    "en": " · select a participant on the diagram"
  },
  "knowledge.be9b64fcd3b4": {
    "ru": " относительно ",
    "en": " relative to "
  },
  "knowledge.8b2983ada1b3": {
    "ru": "Исходящие",
    "en": "Outgoing"
  },
  "knowledge.5a198abc4c76": {
    "ru": "Входящие",
    "en": "Incoming"
  },
  "knowledge.215816bf4210": {
    "ru": "Все",
    "en": "All"
  },
  "knowledge.da28bc8d8b81": {
    "ru": "<section class=\"k-matrix-panel\"><p>Строка — источник, столбец — зависимость. Число — статические связи из синтаксиса, не количество вызовов. Выберите ячейку для локального графа.</p>{v0}<div class=\"k-matrix-scroll\"><table><caption>Связи текущей выборки</caption><thead><tr><th scope=\"col\">Источник ↓ / зависимость →</th>{v1}</tr></thead><tbody>{v2}</tbody></table></div>{v3}</section>",
    "en": "<section class=\"k-matrix-panel\"><p>Rows represent sources, columns represent dependencies. Numbers represent static relationships from syntax, not call counts. Select a cell to open a local graph.</p>{v0}<div class=\"k-matrix-scroll\"><table><caption>Relationships in the current selection</caption><thead><tr><th scope=\"col\">Source ↓ / dependency →</th>{v1}</tr></thead><tbody>{v2}</tbody></table></div>{v3}</section>"
  },
  "knowledge.9abed7b54a44": {
    "ru": "<p class=\"k-warning\">Матрица неполная: достигнут предел связей или версии данных различаются. ? — отсутствие связи не подтверждено.</p>",
    "en": "<p class=\"k-warning\">The matrix is incomplete: the relationship limit was reached or data versions differ. ? means that the absence of a relationship has not been confirmed.</p>"
  },
  "knowledge.747f78e5a0be": {
    "ru": "есть",
    "en": "present"
  },
  "knowledge.762c7823d566": {
    "ru": " статических связей",
    "en": " static relationships"
  },
  "knowledge.90c8cf35ae10": {
    "ru": "число не указано",
    "en": "no count specified"
  },
  "knowledge.059cdac0d09f": {
    "ru": " зависит от ",
    "en": " depends on "
  },
  "knowledge.04b22be55b12": {
    "ru": "<p>На этом уровне дочерних компонентов нет. Выберите уровень выше или локальные связи.</p>",
    "en": "<p>There are no child components at this level. Select the parent level or local relationships.</p>"
  },
  "knowledge.5e9803acc9ba": {
    "ru": "<nav class=\"k-component-scope\"><button data-k-action=\"component-root\">Корневые компоненты</button>{v0}<span>{v1}</span></nav>",
    "en": "<nav class=\"k-component-scope\"><button data-k-action=\"component-root\">Root components</button>{v0}<span>{v1}</span></nav>"
  },
  "knowledge.570d9d15a675": {
    "ru": "<button data-k-select=\"{v0}\">На уровень выше</button><strong>{v1}</strong>",
    "en": "<button data-k-select=\"{v0}\">One level up</button><strong>{v1}</strong>"
  },
  "knowledge.3f60c862ebc1": {
    "ru": "Прямые дочерние компоненты: ",
    "en": "Direct child components: "
  },
  "knowledge.53d64437fb81": {
    "ru": "Состав подсистемы · типы из исходников.",
    "en": "Subsystem contents · types from source code."
  },
  "knowledge.4a7433f8440e": {
    "ru": "Граф недоступен: Cytoscape.js не загружен. Используйте доступный список элементов.",
    "en": "Graph unavailable: Cytoscape.js has not loaded. Use the available item list."
  },
  "knowledge.da614ce8c1e0": {
    "ru": "ELK недоступен: выполнено резервное размещение. ",
    "en": "ELK unavailable: fallback layout applied. "
  },
  "knowledge.21b98c7366e8": {
    "ru": "Направленная · резерв",
    "en": "Directed · fallback"
  },
  "knowledge.aa0cba195e50": {
    "ru": "Сетка · резерв",
    "en": "Grid · fallback"
  },
  "knowledge.6ca68f51df2c": {
    "ru": "fCoSE · резерв",
    "en": "fCoSE · fallback"
  },
  "knowledge.0ddc55cb308d": {
    "ru": "Силовая · резерв",
    "en": "Force-directed · fallback"
  },
  "knowledge.cc3c43686b46": {
    "ru": "Активная компоновка: ",
    "en": "Active layout: "
  },
  "knowledge.5a6b3316471d": {
    "ru": " · проверка доступности",
    "en": " · availability check"
  },
  "knowledge.429a75ba54f0": {
    "ru": " · нет доступных элементов",
    "en": " · no available items"
  },
  "knowledge.53f0369a4be0": {
    "ru": " · раскрыть в текущей карте",
    "en": " · expand on the current map"
  },
  "knowledge.a6d95dc59740": {
    "ru": "Связь выбрана",
    "en": "Relationship selected"
  },
  "knowledge.e10f9577fbb7": {
    "ru": "Выбрано: {v0} · участников: {v1} · внутренних связей: {v2}",
    "en": "Selected: {v0} · participants: {v1} · internal relationships: {v2}"
  },
  "knowledge.c21b646d2d82": {
    "ru": "происхождение не указано",
    "en": "origin not specified"
  },
  "knowledge.c4e344b6fb32": {
    "ru": " · вход",
    "en": " · entry"
  },
  "knowledge.66093b0d8d76": {
    "ru": " внутри",
    "en": " inside"
  },
  "knowledge.41f780fdee89": {
    "ru": "Категория",
    "en": "Category"
  },
  "knowledge.907677552b02": {
    "ru": "Исходники обновились во время загрузки дерева. Обновите раздел.",
    "en": "Source files changed while the tree was loading. Refresh the section."
  },
  "knowledge.c63642bdab51": {
    "ru": "вызывает",
    "en": "calls"
  },
  "knowledge.db207c22cbe2": {
    "ru": "читает",
    "en": "reads"
  },
  "knowledge.dd2284e8a057": {
    "ru": "инициализирует",
    "en": "initializes"
  },
  "knowledge.626701c599c3": {
    "ru": "запускает",
    "en": "starts"
  },
  "knowledge.076e6114c122": {
    "ru": "цепочка через файлы",
    "en": "chain through files"
  },
  "knowledge.1e6a94ec5b45": {
    "ru": "зависит",
    "en": "depends"
  },
  "knowledge.63e6e06421c4": {
    "ru": "содержит",
    "en": "contains"
  },
  "knowledge.6f8b2ff0c656": {
    "ru": "импортирует",
    "en": "imports"
  },
  "knowledge.59b57383b7a6": {
    "ru": "использует",
    "en": "uses"
  },
  "knowledge.07eff7a5fe5a": {
    "ru": "наследует",
    "en": "inherits"
  },
  "knowledge.b01b27086c3f": {
    "ru": "реализует",
    "en": "implements"
  },
  "knowledge.5e0d0bcd16a7": {
    "ru": "Пространство имён",
    "en": "Namespace"
  },
  "knowledge.730c934a0cfd": {
    "ru": "Модуль",
    "en": "Module"
  },
  "knowledge.bbfa955ec6bd": {
    "ru": "Символ",
    "en": "Symbol"
  },
  "knowledge.c89453017f3e": {
    "ru": "Переменная",
    "en": "Variable"
  },
  "knowledge.80a7359dec79": {
    "ru": "Свойство",
    "en": "Property"
  },
  "knowledge.f1707b7e1d2b": {
    "ru": "Поле",
    "en": "Field"
  },
  "knowledge.859538119171": {
    "ru": "Функция",
    "en": "Function"
  },
  "knowledge.5fcca1576ab8": {
    "ru": "Метод",
    "en": "Method"
  },
  "knowledge.acba5467afc6": {
    "ru": "Внешний тип",
    "en": "External type"
  },
  "knowledge.59dbfe54b48f": {
    "ru": "Файл / модуль",
    "en": "File / module"
  },
  "knowledge.517c6d91fcdb": {
    "ru": "Интерфейс",
    "en": "Interface"
  },
  "knowledge.1711aecef486": {
    "ru": "Класс",
    "en": "Class"
  },
  "knowledge.cde256fd0d5f": {
    "ru": "Выбранный элемент отсутствует в текущем списке исходников.",
    "en": "The selected item is missing from the current source list."
  },
  "knowledge.c574eab0ea66": {
    "ru": "Выбранная подсистема отсутствует в дереве архитектуры.",
    "en": "The selected subsystem is missing from the architecture tree."
  },
  "knowledge.c938986dac19": {
    "ru": "<div class=\"k-scope-controls\"><strong>{v0}</strong><div role=\"group\" aria-label=\"Содержимое выбранного раздела\">{v1}</div>{v2}</div>",
    "en": "<div class=\"k-scope-controls\"><strong>{v0}</strong><div role=\"group\" aria-label=\"Contents of the selected section\">{v1}</div>{v2}</div>"
  },
  "knowledge.7641ad9bafb2": {
    "ru": "Обзор проекта",
    "en": "Project overview"
  },
  "knowledge.7840c9a54c7b": {
    "ru": "Связи",
    "en": "Relations"
  },
  "knowledge.2167fe553fee": {
    "ru": "Наследование",
    "en": "Inheritance"
  },
  "knowledge.55dd51a0372b": {
    "ru": "<span>Авторский сценарий · только сохранённые участники и связи</span>",
    "en": "<span>Authored scenario · saved participants and relationships only</span>"
  },
  "knowledge.1b3a63b288a4": {
    "ru": "Код",
    "en": "Code"
  },
  "knowledge.77091052e9ae": {
    "ru": "Подсистемы",
    "en": "Subsystems"
  },
  "knowledge.be8cdd9f4c82": {
    "ru": "<label><input type=\"checkbox\" data-k-include-subsystems{v0}>Включить код подсистем</label>",
    "en": "<label><input type=\"checkbox\" data-k-include-subsystems{v0}>Include subsystem code</label>"
  },
  "knowledge.2d13aa62f660": {
    "ru": "<div role=\"group\" aria-label=\"Отображение тех же фактов\">{v0}</div>",
    "en": "<div role=\"group\" aria-label=\"Display of the same facts\">{v0}</div>"
  },
  "knowledge.fd5f99d60d33": {
    "ru": "Матрица",
    "en": "Matrix"
  },
  "knowledge.2751c9100018": {
    "ru": "Карта",
    "en": "Map"
  },
  "knowledge.300e04b815b8": {
    "ru": "Подсистемы проекта",
    "en": "Project subsystems"
  },
  "knowledge.81397fca9c28": {
    "ru": "Зависимости: ",
    "en": "Dependencies: "
  },
  "knowledge.2a9e8f177200": {
    "ru": "Версия знаний: ",
    "en": "Knowledge version: "
  },
  "knowledge.3f35bec5c245": {
    "ru": "<section class=\"k-diff\"><h4>Изменённый фрагмент: версия {v0} → сохранённая текущая статья</h4>\n      <p>{v1}Общие начало и конец опущены. Несохранённый черновик исключён из сравнения.</p>\n      {v2}\n      {v3}</section>",
    "en": "<section class=\"k-diff\"><h4>Changed fragment: version {v0} → current saved article</h4>\n      <p>{v1}The identical beginning and ending have been omitted. The unsaved draft is excluded from the comparison.</p>\n      {v2}\n      {v3}</section>"
  },
  "knowledge.fe7436fc4c35": {
    "ru": "Сравниваются пути, хеши и размеры файлов комплекта HTML. ",
    "en": "Paths, hashes and sizes of files in the HTML bundle are compared. "
  },
  "knowledge.ef5d6a7314f0": {
    "ru": "<p>Строк в прежнем фрагменте: {v0}; в текущем: {v1}.</p><div class=\"k-diff-columns\"><section><h5>Прежняя версия</h5><pre>{v2}</pre></section><section><h5>Текущая сохранённая</h5><pre>{v3}</pre></section></div>",
    "en": "<p>Lines in the previous fragment: {v0}; in the current version: {v1}.</p><div class=\"k-diff-columns\"><section><h5>Previous version</h5><pre>{v2}</pre></section><section><h5>Current saved version</h5><pre>{v3}</pre></section></div>"
  },
  "knowledge.327245a6954f": {
    "ru": "<span>Удалённых строк нет.</span>",
    "en": "<span>No deleted lines.</span>"
  },
  "knowledge.a1ba7ce4d3e9": {
    "ru": "<span>Добавленных строк нет.</span>",
    "en": "<span>No added lines.</span>"
  },
  "knowledge.0f8b9405fb4c": {
    "ru": "Изменений текста нет.",
    "en": "No text changes."
  },
  "knowledge.b38e5d504a3a": {
    "ru": "Изменений комплекта HTML нет.",
    "en": "No changes to the HTML bundle."
  },
  "knowledge.2177df655ea8": {
    "ru": "<p class=\"k-warning\">Сравнение ограничено 200 строками каждой версии и 500 символами строки.{v0}{v1}</p>",
    "en": "<p class=\"k-warning\">The comparison is limited to 200 lines per version and 500 characters per line.{v0}{v1}</p>"
  },
  "knowledge.643a931a8530": {
    "ru": " Не показано строк: ",
    "en": " Lines not shown: "
  },
  "knowledge.0daa819a26c8": {
    "ru": " Длинные строки сокращены.",
    "en": " Long lines have been truncated."
  },
  "knowledge.3190d4ec9899": {
    "ru": "<article class=\"k-inspector{v0}\"><div class=\"k-inspector-head\"><h2>{v1}</h2><button data-k-action=\"history\">История</button>\n      <button data-k-action=\"edit\">{v2}</button></div>\n      {v3}\n      {v4}\n      {v5}\n      {v6}\n      <nav class=\"k-links\" data-k-doc-links=\"{v7}\" aria-label=\"Связанная архитектура\"{v8}>{v9}</nav>\n      {v10}{v11}</article>",
    "en": "<article class=\"k-inspector{v0}\"><div class=\"k-inspector-head\"><h2>{v1}</h2><button data-k-action=\"history\">History</button>\n      <button data-k-action=\"edit\">{v2}</button></div>\n      {v3}\n      {v4}\n      {v5}\n      {v6}\n      <nav class=\"k-links\" data-k-doc-links=\"{v7}\" aria-label=\"Related architecture\"{v8}>{v9}</nav>\n      {v10}{v11}</article>"
  },
  "knowledge.59792556fd06": {
    "ru": "Редактировать",
    "en": "Edit"
  },
  "knowledge.b39f2a07ba06": {
    "ru": "Читать",
    "en": "Read"
  },
  "knowledge.6670eeccd58b": {
    "ru": "<p class=\"k-warning\">Несохранённый черновик · основан на версии {v0}{v1}</p>",
    "en": "<p class=\"k-warning\">Unsaved draft · based on version {v0}{v1}</p>"
  },
  "knowledge.e749fd121ab4": {
    "ru": " · знания проекта обновились; требуется сверка",
    "en": " · project knowledge has changed; reconciliation required"
  },
  "knowledge.f29d21c0e8f4": {
    "ru": "<div class=\"k-editor\"><label>Заголовок<input data-k-field=\"title\" value=\"{v0}\"></label><div class=\"k-editor-meta\">\n      {v1}</div>\n      <label>Связанные элементы архитектуры (ID через запятую)<input data-k-field=\"entityRefs\" value=\"{v2}\"></label>\n      {v3}\n      <div class=\"k-actions\"><button data-k-action=\"save\"{v4}>Сохранить новую версию</button><button data-k-action=\"preview\">{v5} предпросмотр</button><button data-k-action=\"discard\">Загрузить сохранённую версию</button></div></div>",
    "en": "<div class=\"k-editor\"><label>Title<input data-k-field=\"title\" value=\"{v0}\"></label><div class=\"k-editor-meta\">\n      {v1}</div>\n      <label>Related architectural items (comma-separated IDs)<input data-k-field=\"entityRefs\" value=\"{v2}\"></label>\n      {v3}\n      <div class=\"k-actions\"><button data-k-action=\"save\"{v4}>Save a new version</button><button data-k-action=\"preview\">{v5} preview</button><button data-k-action=\"discard\">Load the saved version</button></div></div>"
  },
  "knowledge.c665b809de48": {
    "ru": "<label>Аудитория<input data-k-field=\"audience\" list=\"k-audiences\" value=\"{v0}\"><datalist id=\"k-audiences\">{v1}</datalist></label>\n      <label>Раздел<input data-k-field=\"section\" value=\"{v2}\"></label>\n      <label>Тип статьи<select data-k-field=\"type\">{v3}</select></label>\n      <label>Статус<select data-k-field=\"status\">{v4}</select></label>",
    "en": "<label>Audience<input data-k-field=\"audience\" list=\"k-audiences\" value=\"{v0}\"><datalist id=\"k-audiences\">{v1}</datalist></label>\n      <label>Section<input data-k-field=\"section\" value=\"{v2}\"></label>\n      <label>Article type<select data-k-field=\"type\">{v3}</select></label>\n      <label>Status<select data-k-field=\"status\">{v4}</select></label>"
  },
  "knowledge.a68feb74138f": {
    "ru": "Не классифицирована",
    "en": "Unclassified"
  },
  "knowledge.ef0141cc3a49": {
    "ru": "<p>HTML и зависимости обновляются через импорт исходника с проверкой изменений. Здесь редактируются название, раздел и статус.</p>",
    "en": "<p>HTML and dependencies are updated by importing the source with change verification. The name, section and status are edited here.</p>"
  },
  "knowledge.1e5bec3aab1c": {
    "ru": "Показать",
    "en": "Show"
  },
  "knowledge.0a2a4b837761": {
    "ru": "Скрыть",
    "en": "Hide"
  },
  "knowledge.51864059642a": {
    "ru": "<section class=\"k-historical\"><h3>Просмотр версии {v0}</h3>{v1}<div class=\"k-actions\"><button data-k-action=\"compare\"{v2}>{v3}</button><button data-k-action=\"restore\">Восстановить как новую версию</button></div>{v4}</section>",
    "en": "<section class=\"k-historical\"><h3>View version {v0}</h3>{v1}<div class=\"k-actions\"><button data-k-action=\"compare\"{v2}>{v3}</button><button data-k-action=\"restore\">Restore as a new version</button></div>{v4}</section>"
  },
  "knowledge.c0bd2cf14b30": {
    "ru": "Сравнить с текущей",
    "en": "Compare with current"
  },
  "knowledge.3506391e9a3d": {
    "ru": "Загрузка текущей статьи…",
    "en": "Loading the current article…"
  },
  "knowledge.00451de0e1c6": {
    "ru": "<section class=\"k-debt\" aria-label=\"Незавершённое согласование знаний\">{v0}\n      {v1}</section>",
    "en": "<section class=\"k-debt\" aria-label=\"Incomplete knowledge reconciliation\">{v0}\n      {v1}</section>"
  },
  "knowledge.baf50f7afde0": {
    "ru": "<p class=\"k-warning\" role=\"status\">Публикация в журнал задачи ожидает доставки: {v0}. Сохранённые знания доступны; подтверждение связи с задачей ещё не доставлено.</p>",
    "en": "<p class=\"k-warning\" role=\"status\">Publication to the task log is awaiting delivery: {v0}. Saved knowledge is available; confirmation of the task link has not yet been delivered.</p>"
  },
  "knowledge.53883d4251fd": {
    "ru": "<p class=\"k-warning\">Требуется сверка знаний: <a href=\"{v0}\">{v1}{v2}</a> · {v3}</p>",
    "en": "<p class=\"k-warning\">Knowledge reconciliation required: <a href=\"{v0}\">{v1}{v2}</a> · {v3}</p>"
  },
  "knowledge.bffdeff3432b": {
    "ru": "Причина не указана",
    "en": "No reason specified"
  },
  "knowledge.c3f30b16faf5": {
    "ru": " · и ещё ",
    "en": " · and more "
  },
  "knowledge.57db5f2d9642": {
    "ru": "Неполные ссылки на исходники",
    "en": "Incomplete source references"
  },
  "knowledge.3839403cd19a": {
    "ru": "Не найдены изображения",
    "en": "No images found"
  },
  "knowledge.26f492f8ca0c": {
    "ru": "<small class=\"k-code-basis\">Основание: {v0}{v1}{v2}</small>",
    "en": "<small class=\"k-code-basis\">Basis: {v0}{v1}{v2}</small>"
  },
  "knowledge.3a3a46f973da": {
    "ru": "Версия исходного кода неизвестна",
    "en": "Source code version unknown"
  },
  "knowledge.e8bff9ea4928": {
    "ru": "<br>Fingerprint неизвестен",
    "en": "<br>Fingerprint unknown"
  },
  "knowledge.bcdad090ec18": {
    "ru": "<br>Git HEAD неизвестен",
    "en": "<br>Git HEAD unknown"
  },
  "knowledge.5aea9d7ced44": {
    "ru": "неизвестен",
    "en": "unknown"
  },
  "knowledge.1add7a6d5db1": {
    "ru": "корень ",
    "en": "root "
  },
  "knowledge.8e999ca1c071": {
    "ru": "Последнее успешное сканирование; текущий код может отличаться",
    "en": "Last successful scan; the current code may differ"
  },
  "knowledge.d251b7ad835a": {
    "ru": "Локальное сканирование исходников",
    "en": "Local source code scan"
  },
  "knowledge.94736024ec51": {
    "ru": "<section class=\"k-history\"><h3>История изменений</h3>{v0}\n      {v1}</section>",
    "en": "<section class=\"k-history\"><h3>Change history</h3>{v0}\n      {v1}</section>"
  },
  "knowledge.25f6d93e8d3c": {
    "ru": "<p>В этой странице истории изменений элемента нет.</p>",
    "en": "<p>This page of the change history does not contain the item.</p>"
  },
  "knowledge.dbbc3ea46098": {
    "ru": "<div><button data-k-revision=\"{v0}\" data-k-role-id=\"{v1}\">Версия {v2}</button><span>{v3} · {v4}\n      {v5}{v6}</span></div>",
    "en": "<div><button data-k-revision=\"{v0}\" data-k-role-id=\"{v1}\">Version {v2}</button><span>{v3} · {v4}\n      {v5}{v6}</span></div>"
  },
  "knowledge.be1848bcacd3": {
    "ru": "<small>Задача не привязана</small>",
    "en": "<small>No task linked</small>"
  },
  "knowledge.9cbeea5e736c": {
    "ru": "<a href=\"{v0}\">Задача {v1}{v2}</a>",
    "en": "<a href=\"{v0}\">Task {v1}{v2}</a>"
  },
  "knowledge.48c6b08159e4": {
    "ru": "<button data-k-action=\"history-more\" data-k-role-id=\"{v0}\">Следующая страница истории</button>",
    "en": "<button data-k-action=\"history-more\" data-k-role-id=\"{v0}\">Next history page</button>"
  },
  "knowledge.ca522d14614c": {
    "ru": "<p>Показано максимум 200 элементов. Уточните поиск.</p>",
    "en": "<p>Up to 200 items are shown. Refine your search.</p>"
  },
  "knowledge.5c068ebab74e": {
    "ru": "<button data-k-action=\"more\">Показать ещё</button>",
    "en": "<button data-k-action=\"more\">Show more</button>"
  },
  "knowledge.e65877f5393d": {
    "ru": "Ничего не найдено. Измените поиск или фильтры.",
    "en": "Nothing found. Change the search or filters."
  },
  "knowledge.e869f114154d": {
    "ru": "На текущей схеме элементов нет. Откройте весь каталог или измените представление.",
    "en": "There are no items on the current diagram. Open the entire catalog or change the view."
  },
  "knowledge.2b4beceac80f": {
    "ru": "Точка входа",
    "en": "Entry point"
  },
  "knowledge.7dc34e0efdfc": {
    "ru": " результатов",
    "en": " results"
  },
  "knowledge.e029cc4b39ce": {
    "ru": " из ",
    "en": " of "
  },
  "knowledge.978b2791fbea": {
    "ru": "Показано ",
    "en": "Shown "
  },
  "knowledge.af3de774e2fe": {
    "ru": " элементов на схеме",
    "en": " items in the diagram"
  },
  "knowledge.9d59fec28e78": {
    "ru": "<label>Список<select data-k-filter=\"listMode\"><option value=\"graph\"{v0}>На схеме</option><option value=\"catalog\"{v1}>Весь каталог</option></select></label><p>{v2}</p>",
    "en": "<label>List<select data-k-filter=\"listMode\"><option value=\"graph\"{v0}>On the diagram</option><option value=\"catalog\"{v1}>Entire catalog</option></select></label><p>{v2}</p>"
  },
  "knowledge.331ed8173c2c": {
    "ru": "Все элементы архитектурной базы; поиск по проекту",
    "en": "All architectural knowledge base items; search across the project"
  },
  "knowledge.4bc69b378182": {
    "ru": "Элементы текущего представления",
    "en": "Items in the current view"
  },
  "knowledge.8a9ef47f4ae1": {
    "ru": "Свернуть список",
    "en": "Collapse list"
  },
  "knowledge.c7c7a551079f": {
    "ru": "Развернуть список",
    "en": "Expand list"
  },
  "knowledge.371783c09a6a": {
    "ru": "Элементы модели",
    "en": "Model items"
  },
  "knowledge.279e6b2bd1dc": {
    "ru": "Статьи",
    "en": "Articles"
  },
  "knowledge.1e8f1ab7f1a6": {
    "ru": "Классы / типы",
    "en": "Classes / types"
  },
  "knowledge.e04215953573": {
    "ru": "Внешние зависимости",
    "en": "External dependencies"
  },
  "knowledge.823384848ecc": {
    "ru": "Файлы / модули",
    "en": "Files / modules"
  },
  "knowledge.8a89b9398cca": {
    "ru": "Интерфейсы",
    "en": "Interfaces"
  },
  "knowledge.8d6e25aa7b88": {
    "ru": "Точки входа",
    "en": "Entry points"
  },
  "knowledge.1e8466ebebaf": {
    "ru": "Компоненты",
    "en": "Components"
  },
  "knowledge.817f8931e5f0": {
    "ru": "<aside class=\"k-catalog{v0}\" data-k-browser-mode=\"{v1}\" aria-label=\"Навигатор архитектуры\"><header class=\"k-catalog-head\"><h2>Навигатор</h2><button data-k-action=\"follow-selection\" aria-pressed=\"{v2}\" title=\"Следить за выбором на схеме\" aria-label=\"Следить за выбором на схеме\">{v3}</button><button data-k-action=\"toggle-list\" aria-expanded=\"{v4}\" aria-label=\"{v5}\" title=\"{v6}\">{v7}</button></header><div class=\"k-navigator-actions\"><button data-k-action=\"refresh\">Перечитать данные</button><button data-k-action=\"scan\"{v8}>Сканировать исходники</button><button data-k-action=\"diagnostics\" aria-label=\"Состояние анализа\">{v9}</button><button data-k-action=\"tools\" aria-label=\"Инструменты\">{v10}</button></div><div class=\"k-analysis-status\" data-k-analysis-status role=\"status\">{v11}</div><label class=\"k-navigator-search\">{v12}<input type=\"search\" data-k-filter=\"query\" value=\"{v13}\" placeholder=\"Название или путь\"></label>{v14}<small data-k-follow-status></small><div class=\"k-browser-tabs\" role=\"group\" aria-label=\"Содержимое навигатора\">{v15}</div>{v16}{v17}</aside>",
    "en": "<aside class=\"k-catalog{v0}\" data-k-browser-mode=\"{v1}\" aria-label=\"Architecture navigator\"><header class=\"k-catalog-head\"><h2>Navigator</h2><button data-k-action=\"follow-selection\" aria-pressed=\"{v2}\" title=\"Follow selection on the diagram\" aria-label=\"Follow selection on the diagram\">{v3}</button><button data-k-action=\"toggle-list\" aria-expanded=\"{v4}\" aria-label=\"{v5}\" title=\"{v6}\">{v7}</button></header><div class=\"k-navigator-actions\"><button data-k-action=\"refresh\">Reload data</button><button data-k-action=\"scan\"{v8}>Scan sources</button><button data-k-action=\"diagnostics\" aria-label=\"Analysis status\">{v9}</button><button data-k-action=\"tools\" aria-label=\"Tools\">{v10}</button></div><div class=\"k-analysis-status\" data-k-analysis-status role=\"status\">{v11}</div><label class=\"k-navigator-search\">{v12}<input type=\"search\" data-k-filter=\"query\" value=\"{v13}\" placeholder=\"Name or path\"></label>{v14}<small data-k-follow-status></small><div class=\"k-browser-tabs\" role=\"group\" aria-label=\"Navigator contents\">{v15}</div>{v16}{v17}</aside>"
  },
  "knowledge.16592fbe4452": {
    "ru": "Свернуть навигатор",
    "en": "Collapse navigator"
  },
  "knowledge.e342569d2132": {
    "ru": "Развернуть навигатор",
    "en": "Expand navigator"
  },
  "knowledge.ca285db3dd75": {
    "ru": "Состояние",
    "en": "Status"
  },
  "knowledge.57319ddc7170": {
    "ru": "Поиск исходников",
    "en": "Search source code"
  },
  "knowledge.b99e520d31ad": {
    "ru": "Поиск структуры",
    "en": "Search structure"
  },
  "knowledge.37f0b3f35e34": {
    "ru": "<label>Область поиска<select data-k-discovery-scope><option value=\"project\"{v0}>В проекте</option><option value=\"subsystem\"{v1}{v2}>Собственный код подсистемы</option></select></label>",
    "en": "<label>Search scope<select data-k-discovery-scope><option value=\"project\"{v0}>In the project</option><option value=\"subsystem\"{v1}{v2}>Subsystem's own code</option></select></label>"
  },
  "knowledge.550ed2eaf608": {
    "ru": "Исходники",
    "en": "Sources"
  },
  "knowledge.ffe2244ab9fb": {
    "ru": " · весь проект",
    "en": " · the entire project"
  },
  "knowledge.f1a36a3637b0": {
    "ru": " · результаты поиска",
    "en": " · search results"
  },
  "knowledge.ec508b15b9bd": {
    "ru": " элементов",
    "en": " items"
  },
  "knowledge.c71a57df05f3": {
    "ru": "Загрузка дерева…",
    "en": "Loading tree…"
  },
  "knowledge.caeb528f480b": {
    "ru": " элементов текущей схемы",
    "en": " items in the current diagram"
  },
  "knowledge.6eaac5b9d719": {
    "ru": "Изображение документа",
    "en": "Document image"
  },
  "knowledge.3fc61fe31ce8": {
    "ru": "[Изображение: ",
    "en": "[Image: "
  },
  "knowledge.276a86fcfe31": {
    "ru": "<div class=\"k-filters\"><label>Поиск<input data-k-filter=\"query\" type=\"search\" value=\"{v0}\" placeholder=\"Название, текст, идентификатор\"></label><label>Аудитория<select data-k-filter=\"audience\">{v1}</select></label><label>Раздел<select data-k-filter=\"section\">{v2}</select></label><label>Тип статьи<select data-k-filter=\"type\">{v3}</select></label></div>",
    "en": "<div class=\"k-filters\"><label>Search<input data-k-filter=\"query\" type=\"search\" value=\"{v0}\" placeholder=\"Name, text, identifier\"></label><label>Audience<select data-k-filter=\"audience\">{v1}</select></label><label>Section<select data-k-filter=\"section\">{v2}</select></label><label>Article type<select data-k-filter=\"type\">{v3}</select></label></div>"
  },
  "knowledge.d6e3403bd0aa": {
    "ru": "Все аудитории",
    "en": "All audiences"
  },
  "knowledge.0ff4708ef6e1": {
    "ru": "Все разделы",
    "en": "All sections"
  },
  "knowledge.19161353d3bf": {
    "ru": "Все типы",
    "en": "All types"
  },
  "knowledge.8085a5fb0275": {
    "ru": "Название не указано",
    "en": "No name specified"
  },
  "knowledge.417f2145edf5": {
    "ru": "название загружается",
    "en": "loading name"
  },
  "knowledge.046741ca6cc6": {
    "ru": "название не удалось загрузить",
    "en": "could not load name"
  },
  "knowledge.3a0c21e12958": {
    "ru": "элемент недоступен",
    "en": "item unavailable"
  },
  "knowledge.3a75c55e3d45": {
    "ru": " · источник отсутствует",
    "en": " · source missing"
  },
  "knowledge.74398e178599": {
    "ru": "<strong>Архитектура <small>({v0})</small></strong>{v1}\n      {v2}",
    "en": "<strong>Architecture <small>({v0})</small></strong>{v1}\n      {v2}"
  },
  "knowledge.14873adeacfd": {
    "ru": "<div class=\"d-link-controls\"><span role=\"status\">{v0} из {v1}{v2}</span>{v3}{v4}</div>",
    "en": "<div class=\"d-link-controls\"><span role=\"status\">{v0} of {v1}{v2}</span>{v3}{v4}</div>"
  },
  "knowledge.49fe8defe86d": {
    "ru": " · Загружаются названия…",
    "en": " · Loading names…"
  },
  "knowledge.29beefeb2b7e": {
    "ru": "Показать все",
    "en": "Show all"
  },
  "knowledge.46d6bd5a21e3": {
    "ru": "<button data-k-action=\"doc-links-retry\"{v0}>Повторить загрузку названий</button>",
    "en": "<button data-k-action=\"doc-links-retry\"{v0}>Retry loading names</button>"
  },
  "knowledge.50159167929f": {
    "ru": "Список изменился между страницами. Обновите его перед продолжением.",
    "en": "The list changed between pages. Refresh it before continuing."
  },
  "knowledge.81b79f68e5ba": {
    "ru": "Данные перечитаны · версия ",
    "en": "Data reloaded · version "
  },
  "knowledge.2ea741451018": {
    "ru": "Данные перечитаны · без изменений",
    "en": "Data reloaded · no changes"
  },
  "knowledge.55196a79d6de": {
    "ru": "Знания изменились во время загрузки. Перечитайте данные.",
    "en": "Knowledge changed while loading. Reload the data."
  },
  "knowledge.8022d3c480b2": {
    "ru": "Знания изменились во время загрузки кода. Перечитайте данные.",
    "en": "Knowledge changed while code was loading. Reload the data."
  },
  "knowledge.3dbb7364509e": {
    "ru": "Знания изменились во время загрузки.",
    "en": "Knowledge changed while loading."
  },
  "knowledge.8335d13aa801": {
    "ru": "Перечитываем данные…",
    "en": "Reloading data…"
  },
  "knowledge.704d20d7e887": {
    "ru": "Каталог изменился во время загрузки. Перечитайте данные.",
    "en": "The catalog changed while loading. Reload the data."
  },
  "knowledge.5b80bfbe7398": {
    "ru": ". Черновик сохранён. Сверьте историю и текущую версию перед повторным сохранением.",
    "en": ". Draft saved. Check the history and current version before saving again."
  },
  "knowledge.fce0fa9e02e8": {
    "ru": "Ошибка загрузки знаний",
    "en": "Error loading knowledge"
  },
  "knowledge.4cf0a635e9c1": {
    "ru": "Представление проекта изменилось",
    "en": "The project view changed"
  },
  "knowledge.af449a23b672": {
    "ru": "<section class=\"knowledge-root\" data-k-project=\"{v0}\" data-k-mode=\"{v1}\"{v2}>\n      {v3}\n      <div data-k-body><p role=\"status\">Загрузка знаний…</p></div></section>",
    "en": "<section class=\"knowledge-root\" data-k-project=\"{v0}\" data-k-mode=\"{v1}\"{v2}>\n      {v3}\n      <div data-k-body><p role=\"status\">Loading knowledge…</p></div></section>"
  },
  "knowledge.45304fd2fb18": {
    "ru": "<header class=\"k-heading\"><div>{v0}</div>\n      <div class=\"k-actions\">{v1}<button data-k-action=\"refresh\">Обновить</button>{v2}<button data-k-action=\"policy\">Настройки</button>\n      {v3}\n      <button data-k-action=\"export\">Экспорт ZIP</button><button data-k-action=\"export-public\" title=\"Только ранее согласованные публичные, самостоятельные статьи\">Публичный ZIP</button><button data-k-action=\"backup\">Резервная копия</button>{v4}</div></header>",
    "en": "<header class=\"k-heading\"><div>{v0}</div>\n      <div class=\"k-actions\">{v1}<button data-k-action=\"refresh\">Refresh</button>{v2}<button data-k-action=\"policy\">Settings</button>\n      {v3}\n      <button data-k-action=\"export\">ZIP export</button><button data-k-action=\"export-public\" title=\"Only previously approved public, standalone articles\">Public ZIP</button><button data-k-action=\"backup\">Backup</button>{v4}</div></header>"
  },
  "knowledge.167db73910d5": {
    "ru": "<small>БАЗА ЗНАНИЙ ПРОЕКТА</small><h1>Документация</h1><p>Статьи для пользователей и разработчиков, связанные с моделью проекта.</p>",
    "en": "<small>PROJECT KNOWLEDGE BASE</small><h1>Documentation</h1><p>Articles for users and developers, linked to the project model.</p>"
  },
  "knowledge.0d9ff4991685": {
    "ru": "<h1 class=\"k-sr-only\">Архитектура</h1>",
    "en": "<h1 class=\"k-sr-only\">Architecture</h1>"
  },
  "knowledge.75a3e50649e6": {
    "ru": "<button data-k-action=\"return-architecture\">Вернуться к архитектуре</button>",
    "en": "<button data-k-action=\"return-architecture\">Return to architecture</button>"
  },
  "knowledge.d2e91eaa411a": {
    "ru": "<details class=\"k-tools\"><summary>Инструменты</summary><div class=\"k-actions\">",
    "en": "<details class=\"k-tools\"><summary>Tools</summary><div class=\"k-actions\">"
  },
  "knowledge.743dbd652f40": {
    "ru": "<button data-k-action=\"scan\">Сканировать</button><button data-k-action=\"new-view\">Новый сценарий</button>",
    "en": "<button data-k-action=\"scan\">Scan</button><button data-k-action=\"new-view\">New scenario</button>"
  },
  "knowledge.64d06d2da38b": {
    "ru": "<button data-k-action=\"new-doc\">Новая статья</button><button data-k-action=\"import\">Импорт</button>",
    "en": "<button data-k-action=\"new-doc\">New article</button><button data-k-action=\"import\">Import</button>"
  },
  "projects.57b13a4ae07c": {
    "ru": "Сервер не вернул проект",
    "en": "The server did not return a project"
  },
  "projects.f0cf5da54e37": {
    "ru": "Некорректный каталог проектов",
    "en": "Invalid project catalog"
  },
  "projects.abc1ae6ffc4a": {
    "ru": "Повторите действие.",
    "en": "Repeat the action."
  },
  "projects.5ffce33f9766": {
    "ru": "Путь к папке должен быть абсолютным.",
    "en": "The folder path must be absolute."
  },
  "projects.49bfd3c3a0e3": {
    "ru": "Проект изменён другим клиентом. Нажмите «Обновить», сравните значения и повторите сохранение.",
    "en": "The project changed in another client. Refresh, compare the values, and save again."
  },
  "projects.f2cca80a5b4b": {
    "ru": "Повторить последнее изменение",
    "en": "Repeat last change"
  },
  "projects.e548e8f4d639": {
    "ru": "Предыдущее изменение не подтверждено. Повторите его перед новым действием.",
    "en": "The previous change has not been confirmed. Repeat it before starting another action."
  },
  "projects.0c92833cda5f": {
    "ru": "Введите название проекта.",
    "en": "Enter a project name."
  },
  "projects.6be220f7d990": {
    "ru": "Проект создан.",
    "en": "Project created."
  },
  "projects.4dd96a79b884": {
    "ru": "Изменения сохранены.",
    "en": "Changes saved."
  },
  "projects.200d4d17ae3e": {
    "ru": "Папка кода не указана",
    "en": "No code folder specified"
  },
  "projects.a87a4b39c304": {
    "ru": "Активен",
    "en": "Active"
  },
  "projects.34886925697b": {
    "ru": "В архиве",
    "en": "Archived"
  },
  "projects.0bfb4a497412": {
    "ru": "Удалённые проекты",
    "en": "Deleted projects"
  },
  "projects.76f55a988f8a": {
    "ru": "Восстановить",
    "en": "Recover"
  },
  "projects.be99b1361201": {
    "ru": "Удалить",
    "en": "Remove"
  },
  "projects.d314390d1ef9": {
    "ru": "Вернуть из архива",
    "en": "Unarchive"
  },
  "projects.1137508af8ff": {
    "ru": "Архивировать",
    "en": "Archive"
  },
  "projects.e4e6c1fa1cfc": {
    "ru": "Открыть проект",
    "en": "Open project"
  },
  "projects.194306e20807": {
    "ru": "Переименовать",
    "en": "Rename"
  },
  "projects.3dfbbddd5a77": {
    "ru": "Управление отключено для этой версии каталога. Перенесите данные совместимым архивом, затем обновите каталог.",
    "en": "Management is disabled for this catalog version. Transfer the data with a compatible archive, then refresh the catalog."
  },
  "projects.9b0f38818a0a": {
    "ru": "Не удалось загрузить проекты",
    "en": "Projects could not be loaded"
  },
  "projects.4767b9a38d5e": {
    "ru": "Загрузка проектов…",
    "en": "Loading projects…"
  },
  "projects.741d221b924c": {
    "ru": "Проектов пока нет.",
    "en": "There are no projects yet."
  },
  "projects.603e460bf59c": {
    "ru": "Обновить",
    "en": "Refresh"
  },
  "projects.49ed84ac6492": {
    "ru": "Создать проект",
    "en": "Create project"
  },
  "projects.802588148bf9": {
    "ru": "Укажите абсолютный путь, если проект связан с локальной рабочей папкой.",
    "en": "Enter an absolute path when the project is linked to a local working folder."
  },
  "projects.e4c87de262c0": {
    "ru": "Папка кода (необязательно)",
    "en": "Code folder (optional)"
  },
  "projects.720a7014d17b": {
    "ru": "Название проекта",
    "en": "Project name"
  },
  "projects.a84d90bc78b3": {
    "ru": "Добавить проект",
    "en": "Add project"
  },
  "projects.4c171d1a6b7d": {
    "ru": "Управляйте проектами Hub и при необходимости связывайте их с папкой исходного кода.",
    "en": "Manage Hub projects and, when needed, link them to a source-code folder."
  },
  "projects.5029f02d0a94": {
    "ru": "Проекты",
    "en": "Projects"
  },
  "settings.683eb10b73f7": {
    "ru": ". Настройки проекта не изменены.",
    "en": ". Project settings unchanged."
  },
  "settings.cf4c63120878": {
    "ru": "Пример запроса: ",
    "en": "Example request: "
  },
  "settings.c265cda8462e": {
    "ru": "Не удалось загрузить настройки",
    "en": "Could not load settings"
  },
  "settings.d691c834f8d2": {
    "ru": "Выделено: скопируйте вручную",
    "en": "Selected: copy manually"
  },
  "settings.d2d08c715ee6": {
    "ru": "Скопировано",
    "en": "Copied"
  },
  "settings.382dd64dc0b2": {
    "ru": "Есть несохранённые изменения",
    "en": "There are unsaved changes"
  },
  "settings.8e866a91877b": {
    "ru": "Не более 24000 символов в блоке.",
    "en": "No more than 24,000 characters per block."
  },
  "settings.1f8e3dc905e9": {
    "ru": "Сохранено в пользовательской инструкции прежнего подключения Codex через плагин. Изменения действуют после чтения файла project-hub-user агентом.",
    "en": "Saved to the user instruction for the legacy Codex plugin connection. Changes take effect after the agent reads the project-hub-user file."
  },
  "settings.e6470d30d3be": {
    "ru": "Сервер не подтвердил версию инструкций",
    "en": "The server did not confirm the instruction version"
  },
  "settings.3ad4aed694e1": {
    "ru": "Не удалось сохранить инструкции",
    "en": "Could not save instructions"
  },
  "settings.fab6d9413525": {
    "ru": "Инструкции изменены другим участником. Черновик сохранён. Отмените черновик, чтобы загрузить актуальные инструкции перед редактированием.",
    "en": "The instructions were changed by someone else. Your draft was saved. Cancel the draft to load the current instructions before editing."
  },
  "settings.bd97450c8556": {
    "ru": "Сохранение…",
    "en": "Saving…"
  },
  "settings.faa316985fe5": {
    "ru": "Заменить ваши инструкции начальным шаблоном из установленной версии плагина?",
    "en": "Replace your instructions with the initial template from the installed plugin version?"
  },
  "settings.11120c1b9cce": {
    "ru": "Заменить ваши инструкции начальным шаблоном из установленной версии плагина? Черновик будет отменён.",
    "en": "Replace your instructions with the initial template from the installed plugin version? The draft will be cancelled."
  },
  "settings.d89c25d80ffd": {
    "ru": "<div class=\"hub-instructions\" data-instructions-project=\"{v0}\"><p class=\"intro\">Справка о работе Project Hub и настройка ваших инструкций для агента. Начните с правил работы; подробное устройство и технические возможности описаны в следующих темах.</p>\n    <div class=\"reader\"><nav class=\"toc\" aria-label=\"Оглавление инструкций\"><strong>Содержание</strong>{v1}</nav><div class=\"reader-body\"><div class=\"reader-top\"><div><div class=\"eyebrow\">ИНСТРУКЦИИ И ВОЗМОЖНОСТИ HUB</div><h2>{v2}</h2></div></div><section id=\"hub-instruction-topic\" tabindex=\"-1\"><p class=\"hub-topic-intro\">{v3}</p>{v4}</section>{v5}<p id=\"hub-instructions-status\" class=\"meta\" role=\"status\">{v6}</p>{v7}</div></div></div>",
    "en": "<div class=\"hub-instructions\" data-instructions-project=\"{v0}\"><p class=\"intro\">Help for using Project Hub and configuring your agent instructions. Start with working rules; later topics describe the architecture and technical capabilities.</p>\n    <div class=\"reader\"><nav class=\"toc\" aria-label=\"Instruction contents\"><strong>Contents</strong>{v1}</nav><div class=\"reader-body\"><div class=\"reader-top\"><div><div class=\"eyebrow\">HUB INSTRUCTIONS AND CAPABILITIES</div><h2>{v2}</h2></div></div><section id=\"hub-instruction-topic\" tabindex=\"-1\"><p class=\"hub-topic-intro\">{v3}</p>{v4}</section>{v5}<p id=\"hub-instructions-status\" class=\"meta\" role=\"status\">{v6}</p>{v7}</div></div></div>"
  },
  "settings.3af931e3e4f4": {
    "ru": " · черновик",
    "en": " · draft"
  },
  "settings.ac34ddab99bb": {
    "ru": "Сохранить мои инструкции",
    "en": "Save my instructions"
  },
  "settings.4c8faff3287b": {
    "ru": "Отменить черновик",
    "en": "Cancel draft"
  },
  "settings.575848637526": {
    "ru": "<details data-key=\"instruction-technical\"><summary>Подключение файла к Codex</summary><p>{v0}</p><p>Редактор меняет только файл project-hub-user/SKILL.md. Инструкции отдельных проектов и встроенные правила плагина редактируются отдельно.</p><p class=\"meta\">Файл: {v1}</p></details>",
    "en": "<details data-key=\"instruction-technical\"><summary>Connecting the file to Codex</summary><p>{v0}</p><p>The editor changes only the project-hub-user/SKILL.md file. Instructions for individual projects and the plugin's built-in rules are edited separately.</p><p class=\"meta\">File: {v1}</p></details>"
  },
  "settings.e41c30f724a8": {
    "ru": "<p class=\"history\">Вы ещё не сохраняли изменения инструкций через Hub. После первого сохранения или восстановления здесь появится запись.</p>",
    "en": "<p class=\"history\">You have not saved instruction changes through Hub yet. An entry will appear here after your first save or restore.</p>"
  },
  "settings.69b3ce38020a": {
    "ru": "<p><time datetime=\"{v0}\">{v1}</time> · {v2}</p><p>Изменены ваши инструкции</p>",
    "en": "<p><time datetime=\"{v0}\">{v1}</time> · {v2}</p><p>Your instructions changed</p>"
  },
  "settings.033a80284b24": {
    "ru": "Автор не указан",
    "en": "Author not provided"
  },
  "settings.2a5c42af7c00": {
    "ru": "Пользователь",
    "en": "User"
  },
  "settings.732063f16e43": {
    "ru": "Дата не указана",
    "en": "Date not provided"
  },
  "settings.3c81415ee551": {
    "ru": "{v0}<h3>Восстановление настройки в Codex</h3><p>Если обработчики отсутствуют, можно скопировать конфигурацию ниже. Добавление и подтверждение доверия выполняются в Codex.</p>{v1}{v2}",
    "en": "{v0}<h3>Restoring the setting in Codex</h3><p>If no handlers are configured, you can copy the configuration below. Add it and confirm trust in Codex.</p>{v1}{v2}"
  },
  "settings.ecee8e4ae2fa": {
    "ru": "{v0}<h3>Инструменты по назначению</h3><p>Выберите группу, чтобы узнать доступные действия. Точные имена и исходные контракты пригодятся при настройке MCP.</p>{v1}",
    "en": "{v0}<h3>Tools by purpose</h3><p>Select a group to see the available actions. Exact names and original contracts are useful when configuring MCP.</p>{v1}"
  },
  "settings.86b7a4e32dfc": {
    "ru": "<details open data-key=\"instruction-reading\"><summary>Прочитать встроенную инструкцию</summary>{v0}</details>",
    "en": "<details open data-key=\"instruction-reading\"><summary>Read the built-in instruction</summary>{v0}</details>"
  },
  "settings.78600c53dcf8": {
    "ru": "Это последние изменения ваших инструкций: сохранение нового текста и восстановление начального шаблона. История общая для этого файла, а не для выбранного проекта. Обновления плагина и изменения задач сюда не входят.",
    "en": "These are the latest changes to your instructions: saving new text and restoring the initial template. This history belongs to the file, rather than the selected project. It does not include plugin updates or task changes."
  },
  "settings.2008c948b424": {
    "ru": "Project Hub можно дополнять инструкциями, обработчиками событий и другими MCP-подключениями. Здесь показаны доступные способы и их границы. Настройка расширения выполняется отдельно в Codex.",
    "en": "Project Hub can be extended with instructions, event handlers and other MCP connections. Available methods and their limits are shown here. Extensions are configured separately in Codex."
  },
  "settings.56c7b74b54cc": {
    "ru": "Обработчики событий (hooks) запускаются средствами Codex при начале чата, новом запросе или редактировании. Они помогают Hub наблюдать за работой и напоминать об учёте задач. Инструменты MCP работают отдельно от них.",
    "en": "Codex runs event handlers (hooks) when a chat starts, a new request arrives or editing occurs. They help Hub observe work and remind the agent to track tasks. MCP tools operate separately."
  },
  "settings.1ff884604d12": {
    "ru": "Скрипты — программы внутри плагина. Они соединяют Codex с локальным сервисом, передают события и записывают результаты проверок. Обычно запускать их вручную не нужно; этот список помогает понять их назначение и разобраться с настройкой.",
    "en": "Scripts are programs inside the plugin. They connect Codex to the local service, send events and record check results. You usually do not need to run them manually; this list helps explain their purpose and troubleshoot configuration."
  },
  "settings.1ecfa1a43146": {
    "ru": "Здесь описано, что агент может делать через Hub. Skill — файл с инструкциями для агента. MCP — подключение, через которое агент вызывает инструменты Hub: читает память проекта, ведёт задачи и сохраняет результаты.",
    "en": "This section describes what the agent can do through Hub. A skill is a file containing instructions for the agent. MCP is a connection through which the agent calls Hub tools: it reads project memory, manages tasks and saves results."
  },
  "settings.8747014bc0b7": {
    "ru": "Этот раздел объясняет устройство Project Hub: как Codex обращается к сервису, где сохраняются данные и почему задачи, инструкции и разрешения имеют разные источники. Ниже — подробности для тех, кто хочет понять техническую сторону.",
    "en": "This section explains how Project Hub works: how Codex connects to the service, where data is saved and why tasks, instructions and permissions have different sources. Technical details are provided below for those who want to learn more."
  },
  "settings.a8716e2b0e5b": {
    "ru": "Здесь можно дополнить встроенные правила своими предпочтениями: например, как подробно писать отчёты и как выбирать проверки. Ваш текст хранится отдельно от плагина и сохраняется при его обновлении.",
    "en": "Add your own preferences to the built-in rules here: for example, how detailed reports should be and how to choose checks. Your text is stored separately from the plugin and preserved during updates."
  },
  "settings.bf2df2bdfff9": {
    "ru": "Это правила, по которым агент ведёт задачи, сохраняет решения и сообщает о результатах в Project Hub. Они поставляются вместе с плагином Codex, который вы устанавливаете на компьютер. Здесь их можно прочитать, но нельзя изменить: обновлённые правила приходят с новой версией плагина.",
    "en": "These rules guide how the agent manages tasks, saves decisions and reports results in Project Hub. They come with the Codex plugin you install on your computer. You can read them here but cannot edit them: updated rules arrive with a new plugin version."
  },
  "settings.fd8e97b92520": {
    "ru": "Файл пользовательской инструкции прежнего плагина Codex ещё не создан. Для этого подключения нажмите «Создать мои инструкции из шаблона», затем отредактируйте его.",
    "en": "The user instruction file for the legacy Codex plugin has not been created yet. For this connection, click “Create my instructions from the template”, then edit it."
  },
  "settings.1475e8bd0463": {
    "ru": "Пока показан шаблон прежнего плагина Codex. Для его редактора сначала настройте расположение пользовательской инструкции. Для независимого подключения сохраняйте правило в приложении агента.",
    "en": "The legacy Codex plugin template is shown for now. Configure the user instruction location before using its editor. For an independent connection, save the rule in the agent application."
  },
  "settings.9a3d8460d4e8": {
    "ru": "Codex пока не находит пользовательскую инструкцию прежнего подключения через плагин. Настройте её расположение для этого подключения. Независимое подключение использует постоянное правило в приложении агента.",
    "en": "Codex cannot find the user instruction for the legacy plugin connection yet. Configure its location for that connection. The independent connection uses a permanent rule in the agent application."
  },
  "settings.db62a639115e": {
    "ru": "Codex может найти файл как локальную инструкцию (skill). Изменения применяются, когда агент прочитает project-hub-user; сохранение не обновляет уже работающий чат и не гарантирует чтение каждым новым чатом.",
    "en": "Codex can find the file as a local instruction file (skill). Changes take effect when the agent reads project-hub-user; saving does not update a chat already running or guarantee that every new chat will read it."
  },
  "settings.a89b61029eae": {
    "ru": "Эти инструкции хранятся локально. К каким чатам они применяются, зависит от расположения файла в Codex.",
    "en": "These instructions are stored locally. Which chats they apply to depends on the file's location in Codex."
  },
  "settings.49db66ea11d2": {
    "ru": "Эти инструкции не принадлежат отдельному проекту. Они относятся к вашей работе с Hub во всех проектах, добавленных в Project Hub.",
    "en": "These instructions do not belong to an individual project. They apply to your work with Hub across all projects added to Project Hub."
  },
  "settings.a9592df53cd1": {
    "ru": "Предложение для будущих версий",
    "en": "Proposal for future versions"
  },
  "settings.8bcf365638c3": {
    "ru": "Доступно сейчас",
    "en": "Available now"
  },
  "settings.caaa12293dba": {
    "ru": "<article class=\"hub-instruction-card hub-hook-optional\"><h3>Дополнительное ожидание уведомлений</h3><p>{v0}</p><p>Добавьте обработчик к существующим настройкам событий вручную, не заменяя всю конфигурацию. Портал не включает его автоматически. Обработчик не возобновляет бездействующий чат; эта справка не проверяет разрешение на запуск и фактическое срабатывание в Codex.</p><details><summary>Конфигурация дополнительного обработчика (JSON)</summary><label>Фрагмент для добавления<textarea class=\"hub-hook-command\" readonly rows=\"10\">{v1}</textarea><button type=\"button\" data-hub-copy-command data-hub-copy-optional-hooks>Скопировать JSON обработчика</button></label></details></article>",
    "en": "<article class=\"hub-instruction-card hub-hook-optional\"><h3>Additional notification wait</h3><p>{v0}</p><p>Manually add the handler to your existing event settings without replacing the entire configuration. The portal does not enable it automatically. The handler does not resume an idle chat; this help does not verify permission to run it or whether it actually runs in Codex.</p><details><summary>Additional handler configuration (JSON)</summary><label>Snippet to add<textarea class=\"hub-hook-command\" readonly rows=\"10\">{v1}</textarea><button type=\"button\" data-hub-copy-command data-hub-copy-optional-hooks>Copy handler JSON</button></label></details></article>"
  },
  "settings.9daf41cd2710": {
    "ru": "<details class=\"hub-hook-recovery\"><summary>JSON для восстановления hooks</summary><p>Импорт JSON и подтверждение доверия к hooks выполняет пользователь в Codex. Портал не изменяет существующие или чужие hooks. Копирование не подтверждает доставку или срабатывание.</p><label>Конфигурация с путями этой установки<textarea class=\"hub-hook-command\" readonly rows=\"10\">{v0}</textarea><button type=\"button\" data-hub-copy-command data-hub-copy-hooks>Скопировать JSON hooks</button></label></details>",
    "en": "<details class=\"hub-hook-recovery\"><summary>JSON to restore hooks</summary><p>You import JSON and confirm trust in hooks in Codex. The portal does not change existing hooks or hooks owned by others. Copying does not confirm delivery or execution.</p><label>Configuration with this installation's paths<textarea class=\"hub-hook-command\" readonly rows=\"10\">{v0}</textarea><button type=\"button\" data-hub-copy-command data-hub-copy-hooks>Copy hooks JSON</button></label></details>"
  },
  "settings.8e85d7823619": {
    "ru": "<h3>{v0}</h3>{v1}<details><summary>Настройка обработчика · {v2}</summary><p>Обработчик включён в плагин. Эта справка не проверяет, разрешён ли его запуск в Codex и сработал ли он в вашем чате.</p><p class=\"caption\">Назначение: {v3} · Ограничение времени: {v4} с · Фильтр инструментов: {v5}</p>{v6}</details>",
    "en": "<h3>{v0}</h3>{v1}<details><summary>Handler configuration · {v2}</summary><p>The handler is included in the plugin. This help does not verify whether Codex permits it to run or whether it ran in your chat.</p><p class=\"caption\">Purpose: {v3} · Time limit: {v4} s · Tool filter: {v5}</p>{v6}</details>"
  },
  "settings.f3370066eb26": {
    "ru": "Все подходящие события",
    "en": "All matching events"
  },
  "settings.ff0335cacf78": {
    "ru": "<label>{v0}<textarea class=\"hub-hook-command\" readonly rows=\"3\">{v1}</textarea><button type=\"button\" data-hub-copy-command>{v2}: копировать</button></label>",
    "en": "<label>{v0}<textarea class=\"hub-hook-command\" readonly rows=\"3\">{v1}</textarea><button type=\"button\" data-hub-copy-command>{v2}: copy</button></label>"
  },
  "settings.e9b0d8467738": {
    "ru": "Команда Windows",
    "en": "Windows command"
  },
  "settings.8b372c12c268": {
    "ru": "Команда",
    "en": "Command"
  },
  "settings.fac655680a19": {
    "ru": "Закрытие сессии",
    "en": "Session end"
  },
  "settings.e78898a57f66": {
    "ru": "Прерывание работы",
    "en": "Work interruption"
  },
  "settings.1c5ce8dc1111": {
    "ru": "Окончание ответа",
    "en": "Response end"
  },
  "settings.0489ec79f603": {
    "ru": "Перед редактированием файла",
    "en": "Before editing a file"
  },
  "settings.46e8c9653b32": {
    "ru": "Новый запрос пользователя",
    "en": "New user request"
  },
  "settings.6fce73381227": {
    "ru": "Начало чата",
    "en": "Chat start"
  },
  "settings.21ae8fa35c65": {
    "ru": "<h3><code>{v0}</code></h3>{v1}<p class=\"caption\">Среда: {v2}</p>{v3}",
    "en": "<h3><code>{v0}</code></h3>{v1}<p class=\"caption\">Environment: {v2}</p>{v3}"
  },
  "settings.f9ee30d64af8": {
    "ru": "<details><summary>Параметры</summary>{v0}</details>",
    "en": "<details><summary>Parameters</summary>{v0}</details>"
  },
  "settings.62c12739878b": {
    "ru": "<h3>{v0}</h3><p>{v1}</p><p class=\"caption\">Имя MCP: <code>{v2}</code></p><details><summary>Технический контракт для агента · оригинал</summary>{v3}</details>",
    "en": "<h3>{v0}</h3><p>{v1}</p><p class=\"caption\">MCP name: <code>{v2}</code></p><details><summary>Technical contract for the agent · original</summary>{v3}</details>"
  },
  "settings.8b28511c0138": {
    "ru": "Дополнительный инструмент этой версии плагина. Его контракт приведён ниже.",
    "en": "An additional tool in this plugin version. Its contract is shown below."
  },
  "settings.f44ac1fa3391": {
    "ru": "Другие инструменты",
    "en": "Other tools"
  },
  "settings.21f031d04f0c": {
    "ru": "<h3 id=\"{v0}\">{v1} <a class=\"hub-block-link\" href=\"#settings/instructions/{v2}/{v3}\" aria-label=\"Ссылка на блок {v4}\">#</a></h3>{v5}\n      {v6}\n      {v7}\n      {v8}\n      <details data-key=\"instruction-source-{v9}\"><summary>Где хранится файл инструкции</summary><p>{v10}</p></details>",
    "en": "<h3 id=\"{v0}\">{v1} <a class=\"hub-block-link\" href=\"#settings/instructions/{v2}/{v3}\" aria-label=\"Link to block {v4}\">#</a></h3>{v5}\n      {v6}\n      {v7}\n      {v8}\n      <details data-key=\"instruction-source-{v9}\"><summary>Where the instruction file is stored</summary><p>{v10}</p></details>"
  },
  "settings.3d5467394606": {
    "ru": "Полный текст встроенной инструкции",
    "en": "Full built-in instruction text"
  },
  "settings.0eb2ff1d7dbf": {
    "ru": "Ваши правила для агента",
    "en": "Your rules for the agent"
  },
  "settings.60b183be6472": {
    "ru": "<p class=\"hub-instruction-notice\">В новой версии плагина изменился начальный шаблон. Ваши инструкции сохранены. Восстановление заменит их новым шаблоном.</p>",
    "en": "<p class=\"hub-instruction-notice\">The initial template changed in the new plugin version. Your instructions were preserved. Restoring will replace them with the new template.</p>"
  },
  "settings.7f241919fadb": {
    "ru": "<div class=\"hub-agent-instruction\" role=\"region\" aria-label=\"Текст инструкции для агента\"><div class=\"hub-agent-instruction-label\">Текст инструкции для агента</div><p class=\"hub-agent-instruction-help\">Этот текст обращён к агенту и задаёт правила его работы.</p>{v0}</div>{v1}",
    "en": "<div class=\"hub-agent-instruction\" role=\"region\" aria-label=\"Instruction text for the agent\"><div class=\"hub-agent-instruction-label\">Instruction text for the agent</div><p class=\"hub-agent-instruction-help\">This text is addressed to the agent and defines how it works.</p>{v0}</div>{v1}"
  },
  "settings.c40f8f14593d": {
    "ru": "Редактировать мои инструкции",
    "en": "Edit my instructions"
  },
  "settings.6756a6827773": {
    "ru": "<label>Локальная инструкция<textarea id=\"hub-personal-editor\" data-hub-instruction-block=\"{v0}\" maxlength=\"24000\" rows=\"18\" {v1}>{v2}</textarea></label><p class=\"caption\">До 24000 символов. Черновик сохраняется при переходе между темами.</p>{v3}",
    "en": "<label>Local instruction<textarea id=\"hub-personal-editor\" data-hub-instruction-block=\"{v0}\" maxlength=\"24000\" rows=\"18\" {v1}>{v2}</textarea></label><p class=\"caption\">Up to 24,000 characters. The draft is saved when you switch topics.</p>{v3}"
  },
  "settings.56b44d4aec51": {
    "ru": "Вернуться к чтению",
    "en": "Return to reading"
  },
  "settings.7b8fa76ce23c": {
    "ru": "Создать мои инструкции из шаблона",
    "en": "Create my instructions from the template"
  },
  "settings.13ab90ea8a41": {
    "ru": "Восстановить начальные инструкции",
    "en": "Restore initial instructions"
  },
  "settings.6127558540b1": {
    "ru": "<details data-key=\"instruction-default-{v0}\"><summary>Начальный шаблон для восстановления</summary><p>Этот текст поставляется с установленной версией плагина. Кнопка восстановления заменит им ваши инструкции.</p>{v1}</details>",
    "en": "<details data-key=\"instruction-default-{v0}\"><summary>Initial template for restoration</summary><p>This text is provided with the installed plugin version. The restore button will replace your instructions with it.</p>{v1}</details>"
  },
  "settings.7da5d5b236a8": {
    "ru": "<p class=\"caption\">В этой версии плагина записей пока нет.</p>",
    "en": "<p class=\"caption\">This plugin version has no entries yet.</p>"
  },
  "settings.66f7961fe72c": {
    "ru": "Загрузка инструкций…",
    "en": "Loading instructions…"
  },
  "settings.603e460bf59c": {
    "ru": "Обновить",
    "en": "Refresh"
  },
  "settings.9fd9b362a777": {
    "ru": "Готовит предварительный разбор старых записей перед изменением их структуры; просмотр не меняет задачи.",
    "en": "Prepares a preliminary review of old records before changing their structure; viewing it does not change tasks."
  },
  "settings.7417fe797284": {
    "ru": "Посмотреть предложение по старым задачам",
    "en": "View the proposal for old tasks"
  },
  "settings.985b5e0f2ccf": {
    "ru": "Настройки",
    "en": "Settings"
  },
  "settings.62ba96d60a5e": {
    "ru": "Работает с настройками задач, просмотра, архитектуры и Git. Изменения выполняются по запросу пользователя.",
    "en": "Works with task, viewing, architecture and Git settings. Changes are made at your request."
  },
  "settings.8b02e5780b9b": {
    "ru": "Прочитать или изменить настройки проекта",
    "en": "Read or change project settings"
  },
  "settings.76d2705ac5ab": {
    "ru": "Помогает проверить вклад нескольких работ в общий коммит и связать его с их результатами. Просмотр и согласование через API сами не создают коммит.",
    "en": "Helps verify contributions from several work efforts to a shared commit and link it to their results. Viewing and reconciliation through the API do not create a commit themselves."
  },
  "settings.6ee5541e8e9a": {
    "ru": "Согласовать общий коммит",
    "en": "Reconcile a shared commit"
  },
  "settings.4f3fecc2e553": {
    "ru": "Проверки и Git",
    "en": "Checks and Git"
  },
  "settings.de50ce48095d": {
    "ru": "Читает состояние сохранения результата в Git и помогает повторить незавершённую публикацию без потери исходных сведений.",
    "en": "Reads the status of saving results in Git and helps retry an incomplete publication without losing the original information."
  },
  "settings.1aef4ef5a1e2": {
    "ru": "Проверить контрольную точку",
    "en": "Verify a checkpoint"
  },
  "settings.22ceccb464e9": {
    "ru": "Показывает, какая проверка выполнялась и чем завершилась. Набор проверок определяется правилами проекта.",
    "en": "Shows which check ran and its outcome. Project rules determine the set of checks."
  },
  "settings.dee1e9cbda79": {
    "ru": "Записать запуск и итог проверки",
    "en": "Record a check run and its outcome"
  },
  "settings.d4d7b8873998": {
    "ru": "Регистрирует документы и другие файлы, сохраняет их версии и прикрепляет к задаче.",
    "en": "Registers documents and other files, saves their versions and attaches them to a task."
  },
  "settings.75e19526737d": {
    "ru": "Сохранить файл результата",
    "en": "Save result file"
  },
  "settings.9f2b7f773977": {
    "ru": "Документы и материалы",
    "en": "Documents and materials"
  },
  "settings.249be5ebe83d": {
    "ru": "Добавляет иллюстрацию или снимок экрана к задаче либо этапу, чтобы результат можно было проверить.",
    "en": "Adds an illustration or screenshot to a task or stage so the result can be verified."
  },
  "settings.a9923d24c38c": {
    "ru": "Прикрепить изображение",
    "en": "Attach an image"
  },
  "settings.dd51eec1c806": {
    "ru": "Ищет и сохраняет статьи, описания компонентов и связи. Анализ исходников показывает доступные статические факты; смысл и порядок работы объясняет агент с опорой на доказательства.",
    "en": "Finds and saves articles, component descriptions and relationships. Source analysis shows available static facts; the agent explains meaning and workflow based on evidence."
  },
  "settings.57b16e9ea6e5": {
    "ru": "Вести документацию и архитектуру",
    "en": "Maintain documentation and architecture"
  },
  "settings.2b535b660547": {
    "ru": "Публикует обоснованные предложения по актуальности, готовности и оценке задач. Пользователь выбирает, какие предложения применить.",
    "en": "Publishes evidence-based proposals about task relevance, completion and estimates. You choose which proposals to apply."
  },
  "settings.57a1092aa6cf": {
    "ru": "Предложить пересмотр задач",
    "en": "Propose a task review"
  },
  "settings.b0327e91e211": {
    "ru": "Задачи и этапы",
    "en": "Tasks and stages"
  },
  "settings.d0e8c88fe175": {
    "ru": "Записывает выводы, проверки и подтверждающие материалы в выбранный этап. Завершение работы и закрытие всей задачи — отдельные действия.",
    "en": "Records findings, checks and supporting materials in the selected stage. Finishing work and closing the entire task are separate actions."
  },
  "settings.e8856cb6b0cb": {
    "ru": "Сохранить результат работы",
    "en": "Save work result"
  },
  "settings.5a90877991e8": {
    "ru": "Связывает работу агента с задачей и этапом, указывает затрагиваемые файлы. Hub сообщает о возможных пересечениях с другими работами.",
    "en": "Links the agent's work to a task and stage, and specifies affected files. Hub reports possible overlaps with other work."
  },
  "settings.17361531e10f": {
    "ru": "Зарегистрировать начало работы",
    "en": "Register the start of work"
  },
  "settings.ca1ff376088e": {
    "ru": "Читает и обновляет этапы, оставшиеся требования, оценки и принятые решения.",
    "en": "Reads and updates stages, remaining requirements, estimates and accepted decisions."
  },
  "settings.d2904d49a032": {
    "ru": "Вести план и решения",
    "en": "Maintain the plan and decisions"
  },
  "settings.7270fc0ad914": {
    "ru": "Завершает задачу после проверки критериев готовности. Окончание ответа агента само по себе задачу не закрывает.",
    "en": "Closes a task after verifying its completion criteria. Finishing an agent response does not by itself close the task."
  },
  "settings.5f15cc9fd262": {
    "ru": "Закрыть выполненную задачу",
    "en": "Close a completed task"
  },
  "settings.501568838b62": {
    "ru": "Записывает зависимости, связанные задачи и дубли. Помогает понять, что блокирует продолжение.",
    "en": "Records dependencies, related tasks and duplicates. Helps identify what blocks further progress."
  },
  "settings.1087c6787019": {
    "ru": "Связать задачи",
    "en": "Link tasks"
  },
  "settings.a16539c066ac": {
    "ru": "Обновляет согласованные сведения о задаче и ссылки на материалы, сохраняя историю изменений.",
    "en": "Updates agreed task information and material links, preserving change history."
  },
  "settings.792d77df43de": {
    "ru": "Уточнить карточку задачи",
    "en": "Update task details"
  },
  "settings.1b0b17b09c32": {
    "ru": "Записывает цель, область работы и критерии готовности. План с этапами добавляется отдельно.",
    "en": "Records the goal, work scope and completion criteria. A plan with stages is added separately."
  },
  "settings.c759b93d6794": {
    "ru": "Создать задачу",
    "en": "Create task"
  },
  "settings.c2b857c37cf8": {
    "ru": "Коротко ожидает обновление Hub, когда продолжение зависит от внешнего события. Не запускает модель и не завершает задачу.",
    "en": "Briefly waits for a Hub update when progress depends on an external event. Does not run a model or complete a task."
  },
  "settings.0fb7dd4e5900": {
    "ru": "Подождать изменения состояния",
    "en": "Wait for a status change"
  },
  "settings.1b6f19b18874": {
    "ru": "Контекст и память",
    "en": "Context and memory"
  },
  "settings.94314ad074c1": {
    "ru": "Показывает уведомления о других работах над той же задачей, зависимостями или файлами. Это повод согласовать действия; уведомление не доказывает, что другой чат сейчас выполняется.",
    "en": "Shows notifications about other work on the same task, dependencies or files. This is a reason to coordinate actions; a notification does not prove that another chat is currently running."
  },
  "settings.cd0033d62fed": {
    "ru": "Узнать о связанной параллельной работе",
    "en": "Learn about related parallel work"
  },
  "settings.01308b446882": {
    "ru": "Ищет записанные задачи, решения и подтверждающие материалы. Позволяет использовать накопленную память проекта.",
    "en": "Finds recorded tasks, decisions and supporting materials. Lets you use accumulated project memory."
  },
  "settings.1e5c53555ca3": {
    "ru": "Найти прошлые решения и результаты",
    "en": "Find previous decisions and results"
  },
  "settings.d2aa1396bc9e": {
    "ru": "Помогает агенту определить проект и свой чат, увидеть активную работу и продолжить её с правильного места.",
    "en": "Helps the agent identify the project and its own chat, see active work and resume from the right point."
  },
  "settings.c00786a1e7d0": {
    "ru": "Узнать состояние проекта и текущей работы",
    "en": "Check project and current work status"
  },
  "settings.9d444769c920": {
    "ru": "История изменений",
    "en": "Change history"
  },
  "settings.ba1b8e9001a2": {
    "ru": "Расширения",
    "en": "Extensions"
  },
  "settings.e81c0b681b79": {
    "ru": "Обработчики событий (hooks)",
    "en": "Event handlers (hooks)"
  },
  "settings.c5c4b74842ed": {
    "ru": "Скрипты",
    "en": "Scripts"
  },
  "settings.cbe4edc37a8b": {
    "ru": "Возможности агента и MCP",
    "en": "Agent and MCP capabilities"
  },
  "settings.ba20d82574c7": {
    "ru": "Архитектура Hub",
    "en": "Architecture Hub"
  },
  "settings.2a02b8618db0": {
    "ru": "Ваши инструкции",
    "en": "Your instructions"
  },
  "settings.b785b445b5f9": {
    "ru": "Правила работы",
    "en": "Working rules"
  },
  "settings.51d84a54f6ca": {
    "ru": "<details><summary>Технические данные файла инструкции</summary><p>Имя и описание, по которым Codex находит эту инструкцию (skill).</p><pre>{v0}</pre></details>",
    "en": "<details><summary>Technical details of the instruction file</summary><p>The name and description Codex uses to find this instruction file (skill).</p><pre>{v0}</pre></details>"
  },
  "settings.d28910a6f3ed": {
    "ru": "Инструкции обновились. Черновик сохранён; отмените его перед редактированием актуальной версии.",
    "en": "The instructions were updated. Your draft was saved; cancel it before editing the current version."
  },
  "settings.533466a205ce": {
    "ru": "Неполный реестр инструкций",
    "en": "Incomplete instruction registry"
  },
  "settings.78c949187e3f": {
    "ru": "Не удалось загрузить инструкции",
    "en": "Could not load instructions"
  },
  "settings.515308926562": {"ru":"<nav class=\"tabs settings-tabs\" aria-label=\"Разделы настроек\"><a href=\"#settings\" {v0}>Общие</a><a href=\"#settings/agents\" {v3}>Агенты и подключения</a><a href=\"#settings/architecture\" {v1}>Архитектура и код</a></nav>","en":"<nav class=\"tabs settings-tabs\" aria-label=\"Settings sections\"><a href=\"#settings\" {v0}>General</a><a href=\"#settings/agents\" {v3}>Agents and connections</a><a href=\"#settings/architecture\" {v1}>Architecture and code</a></nav>"},
  "settings.2fe8f2fd7243": {
    "ru": "Сохранено",
    "en": "Saved"
  },
  "settings.9b88b36adc35": {
    "ru": "Сервер не вернул подтверждённую версию настроек",
    "en": "The server did not return a confirmed settings version"
  },
  "settings.6e7ee8b60e28": {
    "ru": "Не удалось сохранить настройки",
    "en": "Could not save settings"
  },
  "settings.212f81ce441d": {
    "ru": "Настройки изменены другим участником. Черновик сохранён. Отмените изменения, чтобы загрузить актуальную версию.",
    "en": "The settings changed elsewhere. Your draft was saved. Cancel the changes to load the current version."
  },
  "settings.e9e52973f0b7": {
    "ru": "Сбросить настройки раздела? Несохранённые изменения остальных разделов останутся.",
    "en": "Reset this section's settings? Unsaved changes in other sections will remain."
  },
  "settings.959c18b08365": {
    "ru": "Не удалось загрузить каталог моделей",
    "en": "Could not load the model catalog"
  },
  "settings.b042756eefcb": {
    "ru": "<div class=\"settings-page settings-design\" data-settings-project=\"{v0}\">{v1}<fieldset class=\"settings-project-fields\" {v2}>\n<section class=\"card\"><div class=\"section-head\"><h2>Работа агента</h2><span class=\"scope\">Проект · новые запросы</span></div>\n<div class=\"field\"><div><label for=\"setting-architecture-model\">Модель по умолчанию</label><p>Для новых исследовательских чатов этого проекта. Текущий основной чат сохраняет свою модель.</p></div><select id=\"setting-architecture-model\" data-setting=\"architecture.model\"><option value=\"\" {v3}>Codex по умолчанию</option>{v4}{v5}</select></div>\n<div class=\"field\"><div><label for=\"setting-architecture-descriptionDetail\">Подробность описания</label><p>Кратко — 2–4 предложения. Стандартно — несколько абзацев. Подробно — структурированный разбор с опорой на исходники.</p></div><div>{v6}<p>Можно изменить в момент запроса.</p></div></div>\n<div class=\"field\"><div><label for=\"setting-architecture-agentSummaries\">Публичные сводки агента</label><p>Короткие сообщения только при существенном изменении: этап, результат, ограничение или нужное действие.</p></div><label class=\"check\"><input type=\"checkbox\" id=\"setting-architecture-agentSummaries\" data-setting=\"architecture.agentSummaries\" {v7}><span>Показывать сводки</span></label></div>\n<button type=\"button\" data-settings-request=\"open\">{v8}Пример запроса описания</button>{v9}</section>\n<section class=\"card\"><div class=\"section-head\"><h2>Исследование связей</h2><span class=\"scope\">Проект · новые исследования</span></div>\n<p>Исследование запускается сразу и раскрывает один шаг от выбранного элемента. Чтобы продолжить, выберите найденный символ и повторите действие. Новые узлы автоматически не исследуются.</p>\n<div class=\"field\"><div><label for=\"setting-architecture-representation\">Представление результата</label><p>Символы доступны в обоих представлениях. Если файлы скрыты, исследование проходит через них до следующего символа; такая цепочка явно отмечается на карте.</p></div>{v10}</div></section>\n<section class=\"information\"><h3>Источник анализа выбирается автоматически</h3><p>Hub учитывает свежий кэш, тип символа и возможности языкового сервера. Если данных недостаточно, результат показывает ограничения покрытия.</p>\n<details><summary>Последний анализ и ограничения</summary><p>Состояние результата и ограничения покрытия показаны в разделе «Архитектура и код». Ошибки индекса не означают отсутствие связей.</p><p><a href=\"#architecture\">Открыть архитектуру и журнал исследований</a></p></details></section>\n</fieldset>{v11}<details data-key=\"settings-reset-architecture\"><summary>Восстановить значения из комплекта</summary>{v12}</details><dialog id=\"settings-request-dialog\" aria-labelledby=\"settings-request-title\"><header><h2 id=\"settings-request-title\">Описать выбранный элемент</h2><button type=\"button\" data-settings-request=\"close\" aria-label=\"Закрыть пример запроса\">{v13}</button></header><p class=\"muted\">Пример · подсистема «База знаний»</p><label for=\"settings-request-detail\">Подробность этого запроса</label><select id=\"settings-request-detail\">{v14}</select><p class=\"meta\">Выбор действует только для этого примера; запрос к агенту не запускается.</p><div class=\"actions\"><button class=\"primary\" type=\"button\" data-settings-request=\"apply\">Проверить выбор</button></div><p class=\"meta\" id=\"settings-request-status\" role=\"status\"></p></dialog></div>",
    "en": "<div class=\"settings-page settings-design\" data-settings-project=\"{v0}\">{v1}<fieldset class=\"settings-project-fields\" {v2}>\n<section class=\"card\"><div class=\"section-head\"><h2>Agent work</h2><span class=\"scope\">Project · new requests</span></div>\n<div class=\"field\"><div><label for=\"setting-architecture-model\">Default model</label><p>For new exploration chats in this project. The current primary chat keeps its model.</p></div><select id=\"setting-architecture-model\" data-setting=\"architecture.model\"><option value=\"\" {v3}>Codex by default</option>{v4}{v5}</select></div>\n<div class=\"field\"><div><label for=\"setting-architecture-descriptionDetail\">Description detail</label><p>Brief: 2–4 sentences. Standard: a few paragraphs. Detailed: a structured analysis based on source code.</p></div><div>{v6}<p>Can be changed when making a request.</p></div></div>\n<div class=\"field\"><div><label for=\"setting-architecture-agentSummaries\">Public agent summaries</label><p>Brief messages only when something significant changes: a stage, result, limitation or required action.</p></div><label class=\"check\"><input type=\"checkbox\" id=\"setting-architecture-agentSummaries\" data-setting=\"architecture.agentSummaries\" {v7}><span>Show summaries</span></label></div>\n<button type=\"button\" data-settings-request=\"open\">{v8}Description request example</button>{v9}</section>\n<section class=\"card\"><div class=\"section-head\"><h2>Relationship research</h2><span class=\"scope\">Project · new explorations</span></div>\n<p>Exploration starts immediately and expands one step from the selected element. To continue, select the symbol you find and repeat the action. New nodes are not explored automatically.</p>\n<div class=\"field\"><div><label for=\"setting-architecture-representation\">Result presentation</label><p>Symbols are available in both views. If files are hidden, exploration passes through them to the next symbol; this chain is explicitly marked on the map.</p></div>{v10}</div></section>\n<section class=\"information\"><h3>The analysis source is selected automatically</h3><p>Hub uses the latest cache, symbol type and language server capabilities. If data is insufficient, the result shows coverage limitations.</p>\n<details><summary>Latest analysis and limitations</summary><p>Result status and coverage limitations are shown in “Architecture and code”. Index errors do not mean that relationships are absent.</p><p><a href=\"#architecture\">Open architecture and exploration log</a></p></details></section>\n</fieldset>{v11}<details data-key=\"settings-reset-architecture\"><summary>Restore bundled values</summary>{v12}</details><dialog id=\"settings-request-dialog\" aria-labelledby=\"settings-request-title\"><header><h2 id=\"settings-request-title\">Describe the selected element</h2><button type=\"button\" data-settings-request=\"close\" aria-label=\"Close request example\">{v13}</button></header><p class=\"muted\">Example · “Knowledge base” subsystem</p><label for=\"settings-request-detail\">Request detail</label><select id=\"settings-request-detail\">{v14}</select><p class=\"meta\">This choice applies only to this example; it does not start an agent request.</p><div class=\"actions\"><button class=\"primary\" type=\"button\" data-settings-request=\"apply\">Check selection</button></div><p class=\"meta\" id=\"settings-request-status\" role=\"status\"></p></dialog></div>"
  },
  "settings.6b3122c6dc52": {
    "ru": "Подробно",
    "en": "Detailed"
  },
  "settings.8bf6f1e2e70b": {
    "ru": "Стандартно",
    "en": "Standard"
  },
  "settings.6a6d484b2190": {
    "ru": "Кратко",
    "en": "Brief"
  },
  "settings.5b2f735bd7df": {
    "ru": "Загрузка каталога моделей…",
    "en": "Loading model catalog…"
  },
  "settings.c8f6bee07ee8": {
    "ru": "Символы и файлы",
    "en": "Symbols and files"
  },
  "settings.5de9f88969b6": {
    "ru": "Символы, без файлов",
    "en": "Symbols without files"
  },
  "settings.336a0f606373": {
    "ru": "Сбросить раздел",
    "en": "Reset section"
  },
  "settings.75d0296b77b4": {
    "ru": "<option value=\"{v0}\" selected>{v1} · недоступна</option>",
    "en": "<option value=\"{v0}\" selected>{v1} · unavailable</option>"
  },
  "settings.ffee6084558f": {
    "ru": "<div class=\"settings-page settings-design\" data-settings-project=\"{v0}\">{v1}{v2}\n<section class=\"card\"><div class=\"section-head\"><div><h2>Ваш интерфейс</h2><p class=\"muted\">Вид Hub на этом устройстве</p></div><span class=\"scope\">Лично · этот браузер</span></div>\n<div class=\"field\"><div><label for=\"setting-menu-mode\">Основное меню</label><p id=\"menu-help\">При узком окне меню всегда показывает иконки. На широком экране можно оставить этот же вид.</p></div><div><select id=\"setting-menu-mode\" aria-describedby=\"menu-help menu-preference-status\"><option value=\"auto\" {v3}>Автоматически</option><option value=\"compact\" {v4}>Только иконки</option></select><p id=\"menu-preference-status\" role=\"status\">{v5}</p></div></div>\n<p>Чтобы вернуть подписи на широком экране, выберите «Автоматически».</p></section>\n<fieldset class=\"settings-project-fields\" {v6}>\n<section class=\"card\"><div class=\"section-head\"><h2>Контрольные точки Git</h2><span class=\"scope\">Проект · Project Hub</span></div>\n<div class=\"field\"><div><label for=\"setting-git-autoCommit\">Автоматические коммиты</label><p id=\"git-help\">Сохранять проверенные изменения при завершении работы. Настройка действует для агентов этого проекта.</p></div><label class=\"check\"><input id=\"setting-git-autoCommit\" data-setting=\"git.autoCommit\" type=\"checkbox\" {v7} aria-describedby=\"git-help\"><span>Создавать коммиты</span></label></div>\n<div class=\"field\"><div><label for=\"setting-git-commitOn\">Когда создавать коммит</label><p>Выберите момент сохранения завершённого результата.</p></div><select id=\"setting-git-commitOn\" data-setting=\"git.commitOn\" {v8}>{v9}</select></div>\n<details><summary>Что входит в контрольную точку</summary><p>Только проверенные изменения в области работы. Публикация в удалённый репозиторий требует отдельного действия.</p></details></section>\n<div class=\"two\"><section class=\"card\"><div class=\"section-head\"><h2>Список задач</h2><span class=\"scope\">Проект</span></div>\n<div class=\"field\"><label for=\"setting-tasks-sort\">Сортировка по умолчанию</label><p>Применяется, пока вы не выбрали личный порядок в списке.</p><select id=\"setting-tasks-sort\" data-setting=\"tasks.sort\">{v10}</select></div>\n<label class=\"check\"><input id=\"setting-tasks-showCompleted\" data-setting=\"tasks.showCompleted\" type=\"checkbox\" {v11}><span>Показывать завершённые и отменённые<small>Общий стартовый вид списка задач.</small></span></label>\n<details><summary>Столбцы списка</summary><div class=\"checks\">{v12}</div></details>\n<details><summary>Ваши настройки списка</summary><p>Личный выбор в таблице имеет приоритет над значениями проекта.</p><button type=\"button\" data-settings-action=\"personal-reset\">Вернуть настройки проекта для списка и обзора</button></details></section>\n<section class=\"card\"><div class=\"section-head\"><h2>Обзор проекта</h2><span class=\"scope\">Проект</span></div><p>Блок «Текущие задачи» на главной странице.</p>\n<div class=\"field\"><label for=\"setting-tasks-overviewSort\">Сортировка по умолчанию</label><p>Порядок незавершённых задач на обзоре.</p><select id=\"setting-tasks-overviewSort\" data-setting=\"tasks.overviewSort\">{v13}</select></div>\n<label class=\"check\"><input id=\"setting-tasks-showUpcomingOnOverview\" data-setting=\"tasks.showUpcomingOnOverview\" type=\"checkbox\" {v14}><span>Показывать предстоящие задачи<small>Запланированные задачи и очередь.</small></span></label><br><label class=\"check\"><input id=\"setting-tasks-showEpicsOnOverview\" data-setting=\"tasks.showEpicsOnOverview\" type=\"checkbox\" {v15}><span>Показывать эпики<small>Крупные направления рядом с обычными задачами.</small></span></label></section></div>\n<section class=\"card\" style=\"margin-top:16px\"><div class=\"section-head\"><h2>Просмотр документов</h2><span class=\"scope\">Значения проекта</span></div>\n<div class=\"field\"><div><label for=\"setting-viewer-wrapLines\">Перенос строк</label><p>Длинные строки подстраиваются под ширину просмотрщика.</p></div><label class=\"check\"><input id=\"setting-viewer-wrapLines\" data-setting=\"viewer.wrapLines\" type=\"checkbox\" {v16}><span>Переносить строки</span></label></div>\n<div class=\"field\"><div><label for=\"setting-viewer-showSourceDetails\">Сведения об источнике</label><p>Показывать происхождение документа при открытии.</p></div><label class=\"check\"><input id=\"setting-viewer-showSourceDetails\" data-setting=\"viewer.showSourceDetails\" type=\"checkbox\" {v17}><span>Показывать сведения</span></label></div></section>\n</fieldset>{v18}<div><details data-key=\"settings-history\"><summary>Последние изменения проекта</summary>{v19}</details><details data-key=\"settings-reset\"><summary>Восстановить значения из комплекта</summary>{v20}</details></fieldset> </div>",
    "en": "<div class=\"settings-page settings-design\" data-settings-project=\"{v0}\">{v1}{v2}\n<section class=\"card\"><div class=\"section-head\"><div><h2>Your interface</h2><p class=\"muted\">Hub appearance on this device</p></div><span class=\"scope\">Personal · this browser</span></div>\n<div class=\"field\"><div><label for=\"setting-menu-mode\">Main menu</label><p id=\"menu-help\">In a narrow window, the menu always shows icons. On a wide screen, you can keep the same view.</p></div><div><select id=\"setting-menu-mode\" aria-describedby=\"menu-help menu-preference-status\"><option value=\"auto\" {v3}>Automatic</option><option value=\"compact\" {v4}>Icons only</option></select><p id=\"menu-preference-status\" role=\"status\">{v5}</p></div></div>\n<p>To restore labels on a wide screen, choose “Automatic”.</p></section>\n<fieldset class=\"settings-project-fields\" {v6}>\n<section class=\"card\"><div class=\"section-head\"><h2>Git checkpoints</h2><span class=\"scope\">Project · Project Hub</span></div>\n<div class=\"field\"><div><label for=\"setting-git-autoCommit\">Automatic commits</label><p id=\"git-help\">Save verified changes when work is completed. This setting applies to agents in this project.</p></div><label class=\"check\"><input id=\"setting-git-autoCommit\" data-setting=\"git.autoCommit\" type=\"checkbox\" {v7} aria-describedby=\"git-help\"><span>Create commits</span></label></div>\n<div class=\"field\"><div><label for=\"setting-git-commitOn\">When to create a commit</label><p>Choose when to save a completed result.</p></div><select id=\"setting-git-commitOn\" data-setting=\"git.commitOn\" {v8}>{v9}</select></div>\n<details><summary>What a checkpoint includes</summary><p>Only verified changes in the work scope. Publishing to a remote repository requires a separate action.</p></details></section>\n<div class=\"two\"><section class=\"card\"><div class=\"section-head\"><h2>Task list</h2><span class=\"scope\">Project</span></div>\n<div class=\"field\"><label for=\"setting-tasks-sort\">Default sorting</label><p>Used until you choose a personal order in the list.</p><select id=\"setting-tasks-sort\" data-setting=\"tasks.sort\">{v10}</select></div>\n<label class=\"check\"><input id=\"setting-tasks-showCompleted\" data-setting=\"tasks.showCompleted\" type=\"checkbox\" {v11}><span>Show completed and cancelled<small>The shared initial view of the task list.</small></span></label>\n<details><summary>List columns</summary><div class=\"checks\">{v12}</div></details>\n<details><summary>Your list settings</summary><p>Your personal table choices take priority over project values.</p><button type=\"button\" data-settings-action=\"personal-reset\">Restore project settings for the list and overview</button></details></section>\n<section class=\"card\"><div class=\"section-head\"><h2>Project overview</h2><span class=\"scope\">Project</span></div><p>The “Current tasks” block on the home page.</p>\n<div class=\"field\"><label for=\"setting-tasks-overviewSort\">Default sorting</label><p>Order of incomplete tasks on the overview.</p><select id=\"setting-tasks-overviewSort\" data-setting=\"tasks.overviewSort\">{v13}</select></div>\n<label class=\"check\"><input id=\"setting-tasks-showUpcomingOnOverview\" data-setting=\"tasks.showUpcomingOnOverview\" type=\"checkbox\" {v14}><span>Show upcoming tasks<small>Scheduled tasks and the queue.</small></span></label><br><label class=\"check\"><input id=\"setting-tasks-showEpicsOnOverview\" data-setting=\"tasks.showEpicsOnOverview\" type=\"checkbox\" {v15}><span>Show epics<small>Major initiatives alongside regular tasks.</small></span></label></section></div>\n<section class=\"card\" style=\"margin-top:16px\"><div class=\"section-head\"><h2>Document viewer</h2><span class=\"scope\">Project values</span></div>\n<div class=\"field\"><div><label for=\"setting-viewer-wrapLines\">Wrap lines</label><p>Long lines adapt to the viewer's width.</p></div><label class=\"check\"><input id=\"setting-viewer-wrapLines\" data-setting=\"viewer.wrapLines\" type=\"checkbox\" {v16}><span>Wrap lines</span></label></div>\n<div class=\"field\"><div><label for=\"setting-viewer-showSourceDetails\">Source details</label><p>Show the document's origin when opening it.</p></div><label class=\"check\"><input id=\"setting-viewer-showSourceDetails\" data-setting=\"viewer.showSourceDetails\" type=\"checkbox\" {v17}><span>Show details</span></label></div></section>\n</fieldset>{v18}<div><details data-key=\"settings-history\"><summary>Recent project changes</summary>{v19}</details><details data-key=\"settings-reset\"><summary>Restore bundled values</summary>{v20}</details></fieldset> </div>"
  },
  "settings.504edf34b123": {
    "ru": "<p class=\"history\">Изменений пока нет.</p>",
    "en": "<p class=\"history\">There are no changes yet.</p>"
  },
  "settings.0427f52ddb36": {
    "ru": "Сбросить просмотр документов",
    "en": "Reset document viewer"
  },
  "settings.f37fd0df5592": {
    "ru": "Сбросить задачи",
    "en": "Reset tasks"
  },
  "settings.171ad2031275": {
    "ru": "Сбросить Git",
    "en": "Reset Git"
  },
  "settings.9f018a1d67a2": {
    "ru": "При завершении задачи",
    "en": "When the task is completed"
  },
  "settings.1edc55352500": {
    "ru": "При завершении этапа",
    "en": "When the stage is completed"
  },
  "settings.59ea9ad3a2d7": {
    "ru": "При завершении этапа и задачи",
    "en": "When the stage and task are completed"
  },
  "settings.ca87c2180268": {
    "ru": "По названию",
    "en": "By title"
  },
  "settings.f2932d892ad9": {
    "ru": "Сначала незавершённые",
    "en": "Incomplete first"
  },
  "settings.682ade53d14c": {
    "ru": "По статусу",
    "en": "By status"
  },
  "settings.8741673244ca": {
    "ru": "По приоритету",
    "en": "By priority"
  },
  "settings.28c18c8dfd24": {
    "ru": "Недавно обновлённые",
    "en": "Recently updated"
  },
  "settings.461c83c1bd68": {
    "ru": "По дате создания · старые",
    "en": "Created date · oldest"
  },
  "settings.10d04c1c3b04": {
    "ru": "По дате создания · новые",
    "en": "Created date · newest"
  },
  "settings.f9b7aff3a66f": {
    "ru": "<div class=\"settings-page settings-design\">{v0}{v1}<p>Для настройки проекта добавьте его в разделе «Проекты».</p></div>",
    "en": "<div class=\"settings-page settings-design\">{v0}{v1}<p>To configure a project, add it in Projects.</p></div>"
  },
  "settings.a74dbbb4f108": {
    "ru": "<section class=\"card\"><div class=\"section-head\"><div><h2>Язык Project Hub</h2><p class=\"muted\">Общий язык интерфейса этой установки. Тексты задач, документов и других данных не переводятся.</p></div><span class=\"scope\">Интерфейс Hub</span></div><div class=\"field\"><label for=\"hub-interface-language\">Язык интерфейса</label><select id=\"hub-interface-language\" {v0}><option value=\"ru\" {v1}>Русский</option><option value=\"en\" {v2}>Английский</option></select><p role=\"status\">{v3}</p></div></section>",
    "en": "<section class=\"card\"><div class=\"section-head\"><div><h2>Project Hub language</h2><p class=\"muted\">The interface language for this installation. Task, document and other stored content is not translated.</p></div><span class=\"scope\">Hub interface</span></div><div class=\"field\"><label for=\"hub-interface-language\">Interface language</label><select id=\"hub-interface-language\" {v0}><option value=\"ru\" {v1}>Russian</option><option value=\"en\" {v2}>English</option></select><p role=\"status\">{v3}</p></div></section>"
  },
  "settings.f84257068b68": {
    "ru": "<div class=\"eyebrow\">PROJECT HUB</div><h1>Настройки</h1><p class=\"intro\">Параметры проекта, ваш интерфейс и правила работы с Hub.</p>{v0}",
    "en": "<div class=\"eyebrow\">PROJECT HUB</div><h1>Settings</h1><p class=\"intro\">Project settings, your interface, and Hub working rules.</p>{v0}"
  },
  "settings.d367c360b8c5": {
    "ru": "Настройки проекта",
    "en": "Project settings"
  },
  "settings.1898e1901dcd": {
    "ru": "Архитектура и код",
    "en": "Architecture and code"
  },
  "settings.891b41a9523b": {
    "ru": "Просмотр документов",
    "en": "Document viewer"
  },
  "settings.03cc1c2d5ac2": {
    "ru": "Задачи",
    "en": "Tasks"
  },
  "settings.86338d9df854": {
    "ru": "<div class=\"actions settings-actions\"><span class=\"status\" role=\"status\" id=\"settings-status\">{v0}</span><button type=\"button\" data-settings-action=\"cancel\" {v1}>Отменить</button><button class=\"primary\" type=\"button\" data-settings-action=\"save\" {v2}>Сохранить настройки проекта</button></div>",
    "en": "<div class=\"actions settings-actions\"><span class=\"status\" role=\"status\" id=\"settings-status\">{v0}</span><button type=\"button\" data-settings-action=\"cancel\" {v1}>Cancel</button><button class=\"primary\" type=\"button\" data-settings-action=\"save\" {v2}>Save project settings</button></div>"
  },
  "settings.65867175d00e": {
    "ru": "Проектные настройки без изменений",
    "en": "Project settings are unchanged"
  },
  "settings.3f2236e45f36": {
    "ru": "Есть несохранённые изменения проекта",
    "en": "There are unsaved project changes"
  },
  "task-editor.5da81c850483": {
    "ru": "Этапов в группе: {v0}. ",
    "en": "Stages in group: {v0}. "
  },
  "task-editor.ee0d0cb307c3": {
    "ru": "<form><header><h2>{v0}</h2><button class=\"icon-button\" type=\"button\" data-operation-close title=\"Закрыть\" aria-label=\"Закрыть\">{v1}</button></header><div class=\"editor-fields\"><strong>{v2}</strong><p class=\"caption\">{v3}</p>{v4}{v5}</div><p class=\"editor-error\" role=\"alert\" hidden></p><footer><button class=\"icon-button\" type=\"button\" data-operation-close title=\"Отмена\" aria-label=\"Отмена\">{v6}</button><button class=\"icon-button\" type=\"submit\" title=\"{v7}\" aria-label=\"{v8}\">{v9}</button></footer></form>",
    "en": "<form><header><h2>{v0}</h2><button class=\"icon-button\" type=\"button\" data-operation-close title=\"Close\" aria-label=\"Close\">{v1}</button></header><div class=\"editor-fields\"><strong>{v2}</strong><p class=\"caption\">{v3}</p>{v4}{v5}</div><p class=\"editor-error\" role=\"alert\" hidden></p><footer><button class=\"icon-button\" type=\"button\" data-operation-close title=\"Cancel\" aria-label=\"Cancel\">{v6}</button><button class=\"icon-button\" type=\"submit\" title=\"{v7}\" aria-label=\"{v8}\">{v9}</button></footer></form>"
  },
  "task-editor.0423c010b948": {
    "ru": "Этап будет исключён из текущего плана. История и доказательства сохранятся; этап можно восстановить.",
    "en": "The stage will be removed from the current plan. History and evidence will be preserved; the stage can be restored."
  },
  "task-editor.d9c9b8aa6dcf": {
    "ru": "Этап вернётся в текущий план.",
    "en": "The stage will return to the current plan."
  },
  "task-editor.51a532fee76c": {
    "ru": "<label class=\"editor-check\"><input type=\"checkbox\" name=\"includeDependencies\">Перенести всю связанную группу зависимостей</label>",
    "en": "<label class=\"editor-check\"><input type=\"checkbox\" name=\"includeDependencies\">Transfer the entire related dependency group</label>"
  },
  "task-editor.3d5e38a2e21b": {
    "ru": "Целевая задача",
    "en": "Target task"
  },
  "task-editor.442e7ad54796": {
    "ru": "Причина",
    "en": "Reason"
  },
  "task-editor.082b457a5d09": {
    "ru": "Восстановить этап",
    "en": "Restore stage"
  },
  "task-editor.d9dc2e9ec238": {
    "ru": "Удалить этап",
    "en": "Delete stage"
  },
  "task-editor.28eb49abfd00": {
    "ru": "Отвязать этап",
    "en": "Unlink stage"
  },
  "task-editor.af445a2529bf": {
    "ru": "Перенести этап",
    "en": "Transfer stage"
  },
  "task-editor.d0bac5ddfa12": {
    "ru": "<details class=\"task-sources\" data-key=\"archived-{v0}\"><summary>Удалённые и отвязанные этапы ({v1})</summary>{v2}</details>",
    "en": "<details class=\"task-sources\" data-key=\"archived-{v0}\"><summary>Removed and unlinked stages ({v1})</summary>{v2}</details>"
  },
  "task-editor.e5aa7d194937": {
    "ru": "<div class=\"section-head\"><span>{v0}</span><button class=\"icon-button\" data-stage-operation=\"restore\" data-task-id=\"{v1}\" data-stage-id=\"{v2}\" title=\"Восстановить этап\" aria-label=\"Восстановить этап\">{v3}</button></div>",
    "en": "<div class=\"section-head\"><span>{v0}</span><button class=\"icon-button\" data-stage-operation=\"restore\" data-task-id=\"{v1}\" data-stage-id=\"{v2}\" title=\"Restore stage\" aria-label=\"Restore stage\">{v3}</button></div>"
  },
  "task-editor.d8f00c9cbb5f": {
    "ru": "Загрузить актуальные данные и заменить несохранённый черновик?",
    "en": "Load current data and replace the unsaved draft?"
  },
  "task-editor.84a0629361d5": {
    "ru": "<form><header><h2>{v0}</h2><button class=\"icon-button\" type=\"button\" data-editor-close title=\"Закрыть\" aria-label=\"Закрыть\">{v1}</button></header><div class=\"editor-fields\">{v2}{v3}<div class=\"editor-grid\">{v4}{v5}</div>\n  {v6}\n  <fieldset data-sources><legend>{v7}</legend><div data-source-rows>{v8}</div><button class=\"icon-button\" type=\"button\" data-add-source title=\"Добавить источник\" aria-label=\"Добавить источник\">{v9}</button></fieldset>\n  {v10}</div><p class=\"editor-error\" role=\"alert\" hidden></p><footer><button class=\"icon-button\" type=\"button\" data-editor-reload title=\"Загрузить актуальные данные\" aria-label=\"Загрузить актуальное\">{v11}</button><button class=\"icon-button\" type=\"button\" data-editor-close title=\"Отмена\" aria-label=\"Отмена\">{v12}</button><button class=\"icon-button\" type=\"submit\" title=\"Сохранить\" aria-label=\"Сохранить\">{v13}</button></footer></form>",
    "en": "<form><header><h2>{v0}</h2><button class=\"icon-button\" type=\"button\" data-editor-close title=\"Close\" aria-label=\"Close\">{v1}</button></header><div class=\"editor-fields\">{v2}{v3}<div class=\"editor-grid\">{v4}{v5}</div>\n  {v6}\n  <fieldset data-sources><legend>{v7}</legend><div data-source-rows>{v8}</div><button class=\"icon-button\" type=\"button\" data-add-source title=\"Add source\" aria-label=\"Add source\">{v9}</button></fieldset>\n  {v10}</div><p class=\"editor-error\" role=\"alert\" hidden></p><footer><button class=\"icon-button\" type=\"button\" data-editor-reload title=\"Load current data\" aria-label=\"Load current version\">{v11}</button><button class=\"icon-button\" type=\"button\" data-editor-close title=\"Cancel\" aria-label=\"Cancel\">{v12}</button><button class=\"icon-button\" type=\"submit\" title=\"Save\" aria-label=\"Save\">{v13}</button></footer></form>"
  },
  "task-editor.0918b4ba9268": {
    "ru": "Название",
    "en": "Title"
  },
  "task-editor.b3680f2cba5f": {
    "ru": "Описание",
    "en": "Description"
  },
  "task-editor.225077c6d479": {
    "ru": "Статус",
    "en": "Status"
  },
  "task-editor.54f9272ea6c7": {
    "ru": "Вес",
    "en": "Weight"
  },
  "task-editor.f45edf006851": {
    "ru": "Проект",
    "en": "Project"
  },
  "task-editor.757b4e4eafa9": {
    "ru": "Родитель",
    "en": "Parent"
  },
  "task-editor.a402b3d034fb": {
    "ru": "Не задан",
    "en": "Not set"
  },
  "task-editor.0e5ac36d3f46": {
    "ru": "Приоритет",
    "en": "Priority"
  },
  "task-editor.d4a6795c199f": {
    "ru": "Тип",
    "en": "Type"
  },
  "task-editor.5c47a3132778": {
    "ru": "Отложено",
    "en": "Deferred"
  },
  "task-editor.f2e1315d11b6": {
    "ru": "Критерии приёмки",
    "en": "Acceptance criteria"
  },
  "task-editor.808c04fe8a46": {
    "ru": "Объём",
    "en": "Scope"
  },
  "task-editor.dfb54a72a0bd": {
    "ru": "<fieldset><legend>Зависимости</legend>{v0}</fieldset>",
    "en": "<fieldset><legend>Dependencies</legend>{v0}</fieldset>"
  },
  "task-editor.a70b093aeac4": {
    "ru": "До завершения",
    "en": "Remaining"
  },
  "task-editor.e078c61c3e49": {
    "ru": "Реализовано",
    "en": "Implemented"
  },
  "task-editor.7dc4dce82a5d": {
    "ru": "Источники задачи",
    "en": "Task sources"
  },
  "task-editor.64be6f12a479": {
    "ru": "Доказательства этапа",
    "en": "Stage evidence"
  },
  "task-editor.8c40e748bc44": {
    "ru": "<fieldset><legend>Связи</legend><datalist id=\"editor-task-ids\">{v0}</datalist><div data-link-rows>{v1}</div><button class=\"icon-button\" type=\"button\" data-add-link title=\"Добавить связь\" aria-label=\"Добавить связь\">{v2}</button></fieldset><fieldset><legend>Оценка</legend><div class=\"editor-grid\">{v3}{v4}{v5}{v6}</div>{v7}{v8}</fieldset>",
    "en": "<fieldset><legend>Relations</legend><datalist id=\"editor-task-ids\">{v0}</datalist><div data-link-rows>{v1}</div><button class=\"icon-button\" type=\"button\" data-add-link title=\"Add relationship\" aria-label=\"Add relationship\">{v2}</button></fieldset><fieldset><legend>Estimate</legend><div class=\"editor-grid\">{v3}{v4}{v5}{v6}</div>{v7}{v8}</fieldset>"
  },
  "task-editor.191e582cc7b3": {
    "ru": "Готовность от, %",
    "en": "Readiness from, %"
  },
  "task-editor.16b15ae023c0": {
    "ru": "Готовность до, %",
    "en": "Readiness to, %"
  },
  "task-editor.659b1867b759": {
    "ru": "Осталось от, ч",
    "en": "Hours remaining from"
  },
  "task-editor.4cbb84f93d9a": {
    "ru": "Осталось до, ч",
    "en": "Hours remaining to"
  },
  "task-editor.5fdfd02a080e": {
    "ru": "Уверенность",
    "en": "Confidence"
  },
  "task-editor.e39bc7fb376c": {
    "ru": "Обоснование",
    "en": "Rationale"
  },
  "task-editor.c759b93d6794": {
    "ru": "Создать задачу",
    "en": "Create task"
  },
  "task-editor.7910256282a4": {
    "ru": "Редактировать задачу",
    "en": "Edit task"
  },
  "task-editor.a5422c3ac740": {
    "ru": "Добавить этап",
    "en": "Add stage"
  },
  "task-editor.49bdb952ae6a": {
    "ru": "Редактировать этап",
    "en": "Edit stage"
  },
  "task-editor.0491c5c90e80": {
    "ru": "Изменяемые поля уже обновлены другим участником. Черновик сохранён в форме; сверьте его с актуальными данными.",
    "en": "The fields being edited were updated by someone else. Your draft is kept in the form; compare it with the current data."
  },
  "task-editor.9225d5afe8c2": {
    "ru": "Не удалось сохранить изменения",
    "en": "Could not save changes"
  },
  "task-editor.dc60222a34e1": {
    "ru": "<div class=\"editor-link-row\" data-link-row><select aria-label=\"Тип связи\" data-link-type>{v0}</select><input aria-label=\"ID связанной задачи\" data-link-target required value=\"{v1}\" list=\"editor-task-ids\"><input aria-label=\"Проект связанной задачи\" data-link-project value=\"{v2}\" placeholder=\"Текущий проект\"><button class=\"icon-button\" type=\"button\" data-remove-row title=\"Удалить связь\" aria-label=\"Удалить связь\">{v3}</button></div>",
    "en": "<div class=\"editor-link-row\" data-link-row><select aria-label=\"Relation type\" data-link-type>{v0}</select><input aria-label=\"Related task ID\" data-link-target required value=\"{v1}\" list=\"editor-task-ids\"><input aria-label=\"Related task project\" data-link-project value=\"{v2}\" placeholder=\"Current project\"><button class=\"icon-button\" type=\"button\" data-remove-row title=\"Remove relationship\" aria-label=\"Remove relationship\">{v3}</button></div>"
  },
  "task-editor.37a583fd779e": {
    "ru": "<section class=\"task-relations\"><h2>Связи задач</h2><div class=\"relation-list\">{v0}</div></section>",
    "en": "<section class=\"task-relations\"><h2>Task relations</h2><div class=\"relation-list\">{v0}</div></section>"
  },
  "task-editor.c1a85153671e": {
    "ru": "<div class=\"detail-section\"><h3>Переносы этапа</h3>{v0}{v1}</div>",
    "en": "<div class=\"detail-section\"><h3>Stage transfers</h3>{v0}{v1}</div>"
  },
  "task-editor.5cf85684a13a": {
    "ru": "<details><summary>Предыдущие события ({v0})</summary>{v1}</details>",
    "en": "<details><summary>Previous events ({v0})</summary>{v1}</details>"
  },
  "task-editor.21841f48f3b2": {
    "ru": "Этап исключён из плана: {v0}. Он доступен в архиве этапов ниже.",
    "en": "Stage removed from the plan: {v0}. It is available in the stage archive below."
  },
  "task-editor.bd1f919d87e4": {
    "ru": "Этап перенесён: <a href=\"{v0}\">{v1}</a>",
    "en": "Stage transferred: <a href=\"{v0}\">{v1}</a>"
  },
  "task-editor.b4832aa2f471": {
    "ru": "<section class=\"task-sources\" aria-label=\"Источники всей задачи\"><div class=\"section-head\"><h2>Источники задачи</h2><button class=\"icon-button\" data-edit-task=\"{v0}\" title=\"Редактировать источники задачи\" aria-label=\"Редактировать источники задачи\">{v1}</button></div>{v2}</section>",
    "en": "<section class=\"task-sources\" aria-label=\"Sources for the whole task\"><div class=\"section-head\"><h2>Task sources</h2><button class=\"icon-button\" data-edit-task=\"{v0}\" title=\"Edit task sources\" aria-label=\"Edit task sources\">{v1}</button></div>{v2}</section>"
  },
  "task-editor.08e7807a3694": {
    "ru": "<p class=\"caption\">Нет прикреплённых источников.</p>",
    "en": "<p class=\"caption\">No sources are attached.</p>"
  },
  "task-editor.1538ca66cb3e": {
    "ru": "Дублируется задачей",
    "en": "Duplicated by task"
  },
  "task-editor.ab91970691f9": {
    "ru": "Дублирует",
    "en": "Duplicates"
  },
  "task-editor.844c7f4197a7": {
    "ru": "Зависит от",
    "en": "Blocked by"
  },
  "task-editor.806bc5f8787d": {
    "ru": "Блокирует",
    "en": "Blocks"
  },
  "task-editor.73c25b59c4b3": {
    "ru": "Связана с",
    "en": "Related to"
  },
  "task-editor.2a7b89b16a0d": {
    "ru": "<div class=\"editor-source-row\" data-source-row data-original=\"{v0}\"><input aria-label=\"Название источника\" data-source-label value=\"{v1}\"><input aria-label=\"Путь источника\" data-source-path required value=\"{v2}\"><button class=\"icon-button\" type=\"button\" data-remove-row title=\"Удалить источник\" aria-label=\"Удалить источник\">{v3}</button></div>",
    "en": "<div class=\"editor-source-row\" data-source-row data-original=\"{v0}\"><input aria-label=\"Source name\" data-source-label value=\"{v1}\"><input aria-label=\"Source path\" data-source-path required value=\"{v2}\"><button class=\"icon-button\" type=\"button\" data-remove-row title=\"Remove source\" aria-label=\"Remove source\">{v3}</button></div>"
  },
  "task-table.77c8465f46ff": {
    "ru": "<div class=\"task-table-scroll\" data-task-table-scroll data-scroll-key=\"task-table\" tabindex=\"0\" role=\"region\" aria-label=\"Таблица задач\"><table class=\"task-table\"><thead><tr>{v0}</tr></thead><tbody>{v1}</tbody></table></div>",
    "en": "<div class=\"task-table-scroll\" data-task-table-scroll data-scroll-key=\"task-table\" tabindex=\"0\" role=\"region\" aria-label=\"Task table\"><table class=\"task-table\"><thead><tr>{v0}</tr></thead><tbody>{v1}</tbody></table></div>"
  },
  "task-table.2d6faffbb6c5": {
    "ru": "<span class=\"task-priority descendant {v0}\" title=\"Максимальный приоритет незавершённых потомков\">Потомки: {v1}</span>",
    "en": "<span class=\"task-priority descendant {v0}\" title=\"Highest priority among unfinished descendants\">Descendants: {v1}</span>"
  },
  "task-table.71062d4f854f": {
    "ru": "Развернуть дочерние задачи",
    "en": "Expand child tasks"
  },
  "task-table.dfaa7a9e8d3a": {
    "ru": "Свернуть дочерние задачи",
    "en": "Collapse child tasks"
  },
  "task-table.b23ba1d01017": {
    "ru": " · {v0} обязательств, {v1} групп",
    "en": " · {v0} obligations, {v1} groups"
  },
  "task-table.6a0cc3e0a931": {
    "ru": "<details class=\"task-column-menu\" data-task-column-menu {v0}><summary class=\"icon-button\" aria-label=\"Столбцы таблицы\" title=\"Столбцы таблицы\">{v1}</summary><fieldset class=\"task-column-options\"><legend>Столбцы таблицы</legend>{v2}</fieldset></details>",
    "en": "<details class=\"task-column-menu\" data-task-column-menu {v0}><summary class=\"icon-button\" aria-label=\"Table columns\" title=\"Table columns\">{v1}</summary><fieldset class=\"task-column-options\"><legend>Table columns</legend>{v2}</fieldset></details>"
  },
  "task-table.cad123465b9e": {
    "ru": "Действия",
    "en": "Actions"
  },
  "task-table.3c56cb41be6f": {
    "ru": "Обновлена",
    "en": "Updated"
  },
  "task-table.0a39fbc65169": {
    "ru": "Создана",
    "en": "Created"
  },
  "task-table.890c6b81731d": {
    "ru": "Оценка / осталось",
    "en": "Estimate / remaining"
  },
  "task-table.610d4c2115f6": {
    "ru": "План",
    "en": "Plan"
  },
  "task-table.9a9f0a0c10e3": {
    "ru": "Статус / агент",
    "en": "Status / agent"
  },
  "task-table.4db42ea0e429": {
    "ru": "Дочерние",
    "en": "Children"
  },
  "task-table.0e5ac36d3f46": {
    "ru": "Приоритет",
    "en": "Priority"
  },
  "task-table.d4a6795c199f": {
    "ru": "Тип",
    "en": "Type"
  },
  "task-table.b3680f2cba5f": {
    "ru": "Описание",
    "en": "Description"
  },
  "task-table.b9ce27191d40": {
    "ru": "Задача",
    "en": "Task"
  },
  "ui-state.7b66a8d552a0": {
    "ru": "Выбор меню действует до закрытия страницы: хранилище браузера недоступно.",
    "en": "The menu choice lasts until the page is closed: browser storage is unavailable."
  },
  "ui-state.bde59ece1110": {
    "ru": "Сейчас: полное меню. Выбор сохранён.",
    "en": "Current view: full menu. Your choice was saved."
  },
  "ui-state.eb75c10712a5": {
    "ru": "Сейчас: только иконки. Выбор сохранён.",
    "en": "Current view: icons only. Your choice was saved."
  },
  "ui-state.b1d1fc1eb78f": {
    "ru": "Сейчас: иконки из-за ширины окна. Ваш выбор сохранён.",
    "en": "Current view: icons because the window is narrow. Your choice was saved."
  },
  "viewer.4a2100cda048": {
    "ru": "Поиск по всему документу",
    "en": "Search the entire document"
  },
  "viewer.45a466a3dfac": {
    "ru": "Поиск по логу; «Далее» продолжает сканирование",
    "en": "Search the log; “Next” continues scanning"
  },
  "viewer.5765af8408a4": {
    "ru": "Не удалось открыть: ",
    "en": "Could not open: "
  },
  "viewer.44f7045db1ff": {
    "ru": "Файл превышает лимит встроенного просмотра (4 МБ). Откройте его в редакторе проекта.",
    "en": "The file exceeds the built-in viewer limit (4 MB). Open it in the project editor."
  },
  "viewer.43262aa7a4eb": {
    "ru": "Не удалось проверить источник.",
    "en": "Could not check the source."
  },
  "viewer.5084779772c5": {
    "ru": "{v0} совпадений{v1}",
    "en": "{v0} matches{v1}"
  },
  "viewer.45dd15b006e0": {
    "ru": " на странице",
    "en": " on the page"
  },
  "viewer.a64bbaf6eac4": {
    "ru": " · показаны первые 1 000 совпадений; уточните запрос",
    "en": " · the first 1,000 matches are shown; refine the query"
  },
  "viewer.ac4099041126": {
    "ru": "Страница {v0} · {v1} строк · просмотрено до {v2}% файла{v3}{v4}",
    "en": "Page {v0} · {v1} lines · viewed through {v2}% of the file{v3}{v4}"
  },
  "viewer.c6ccb12e93d2": {
    "ru": " · совпадений в этом фрагменте нет",
    "en": " · no matches in this section"
  },
  "viewer.1f59f34f93ed": {
    "ru": " · длинные строки разбиты на фрагменты",
    "en": " · long lines are split into fragments"
  },
  "viewer.7eb8ace9b2c2": {
    "ru": " строк на странице",
    "en": " lines on page"
  },
  "viewer.b3ccc59590ee": {
    "ru": "Лог · ",
    "en": "Log · "
  },
  "viewer.a39c29b5ee8f": {
    "ru": " · подсветка синтаксиса отключена для большого файла (более 200 000 символов)",
    "en": " · syntax highlighting is disabled for a large file (over 200,000 characters)"
  },
  "viewer.6ed48a8b7992": {
    "ru": " символов · поиск по всему документу",
    "en": " characters · search the entire document"
  },
  "viewer.6c82309d10a9": {
    "ru": " Выберите «Архив», чтобы открыть сохранённую копию.",
    "en": " Choose “Archive” to open the saved copy."
  },
  "viewer.72493200f71b": {
    "ru": "Архив недоступен.",
    "en": "The archive is unavailable."
  },
  "viewer.85d6f365a958": {
    "ru": "Текущий файл недоступен.",
    "en": "The current file is unavailable."
  },
  "viewer.ec9799f58d28": {
    "ru": "Предпросмотр этого формата недоступен. Скачайте оригинал.",
    "en": "Preview is unavailable for this format. Download the original."
  },
  "viewer.3c54b5e783ef": {
    "ru": "Архив",
    "en": "Archive"
  },
  "viewer.73bd5dbb84f5": {
    "ru": "Текущий файл",
    "en": "Current file"
  },
  "viewer.4701c6618f9a": {
    "ru": "Проверка источника…",
    "en": "Checking source…"
  },
  "viewer.db491ef5033f": {
    "ru": "Загрузка…",
    "en": "Loading…"
  },
  "viewer.7a5ce21fed83": {
    "ru": "Следующее совпадение",
    "en": "Next match"
  },
  "viewer.bff46c40e8c2": {
    "ru": "Предыдущее совпадение",
    "en": "Previous match"
  },
  "viewer.290773056a2d": {
    "ru": "Исходный текст",
    "en": "Raw text"
  },
  "viewer.71ad39a4e9fd": {
    "ru": "Скачать оригинал",
    "en": "Download original"
  },
  "viewer.b7292c143b9f": {
    "ru": "Изменён файл: ",
    "en": "Changed file: "
  },
  "viewer.06629efecaad": {
    "ru": "Версия: ",
    "en": "Version: "
  },
  "viewer.eed27cb94cd7": {
    "ru": "Файл: ",
    "en": "File: "
  },
  "viewer.00d10c9b1342": {
    "ru": "Корень проекта: ",
    "en": "Project root: "
  },
  "viewer.03fb8ea87dd6": {
    "ru": "Путь: ",
    "en": "Path: "
  },
  "viewer.f250ed099246": {
    "ru": "не указан",
    "en": "not set"
  },
  "viewer.e180df6170c8": {
    "ru": "Исходный проект: ",
    "en": "Origin project: "
  },
  "viewer.08f9276429ab": {
    "ru": " — недоступен",
    "en": " — unavailable"
  },
  "viewer.26880b14605e": {
    "ru": "Сохранённая версия",
    "en": "Saved version"
  },
  "viewer.3494826f9512": {
    "ru": " строк",
    "en": " lines"
  },
  "viewer.3091aca226ef": {
    "ru": "Текст",
    "en": "Text"
  },
  "viewer.e31df58dc58a": {
    "ru": "<header><div><small>РЕЗУЛЬТАТ ПРОВЕРКИ / ДОКУМЕНТ</small><h2 id=\"artifact-name\"></h2></div><button class=\"icon-button\" id=\"artifact-close\" aria-label=\"Закрыть просмотр\" title=\"Закрыть просмотр\">{v0}</button></header>\n    <div class=\"artifact-controls\"><input id=\"artifact-search\" type=\"search\" placeholder=\"Поиск по файлу\" aria-label=\"Поиск по файлу\"><select id=\"artifact-level\" aria-label=\"Уровень лога\"><option value=\"\">Все уровни</option><option>ERROR</option><option>WARN</option><option>INFO</option><option>DEBUG</option><option>TRACE</option></select><button class=\"icon-button\" id=\"artifact-find\" title=\"Найти\" aria-label=\"Найти\">{v1}</button><button class=\"icon-button\" id=\"artifact-refresh\" title=\"Обновить\" aria-label=\"Обновить\">{v2}</button><label><input id=\"artifact-wrap\" type=\"checkbox\" checked> Перенос строк</label><a id=\"artifact-raw\" target=\"_blank\" rel=\"noopener\">Исходный текст</a></div>\n    <div class=\"artifact-source\"><div class=\"artifact-source-row\"><label>Версия <select id=\"artifact-source-mode\"><option value=\"current\">Текущий файл</option><option value=\"archive\">Архив</option></select></label><button class=\"icon-button\" id=\"artifact-source-toggle\" type=\"button\" aria-expanded=\"false\" aria-controls=\"artifact-provenance\" aria-label=\"Сведения об источнике\" title=\"Сведения об источнике\">{v3}</button><span id=\"artifact-metadata\"></span><span id=\"artifact-status\" role=\"status\"></span></div><p id=\"artifact-provenance\" hidden></p></div>\n    <div class=\"artifact-main\"><nav id=\"artifact-toc\" aria-label=\"Оглавление\"></nav><div id=\"artifact-body\" tabindex=\"0\"></div></div><footer><button class=\"icon-button\" id=\"artifact-prev\" title=\"Предыдущая страница\" aria-label=\"Предыдущая страница\">{v4}</button><button class=\"icon-button\" id=\"artifact-next\" title=\"Следующая страница\" aria-label=\"Следующая страница\">{v5}</button></footer>",
    "en": "<header><div><small>CHECK RESULT / DOCUMENT</small><h2 id=\"artifact-name\"></h2></div><button class=\"icon-button\" id=\"artifact-close\" aria-label=\"Close viewer\" title=\"Close viewer\">{v0}</button></header>\n    <div class=\"artifact-controls\"><input id=\"artifact-search\" type=\"search\" placeholder=\"Search file\" aria-label=\"Search file\"><select id=\"artifact-level\" aria-label=\"Log level\"><option value=\"\">All levels</option><option>ERROR</option><option>WARN</option><option>INFO</option><option>DEBUG</option><option>TRACE</option></select><button class=\"icon-button\" id=\"artifact-find\" title=\"Find\" aria-label=\"Find\">{v1}</button><button class=\"icon-button\" id=\"artifact-refresh\" title=\"Refresh\" aria-label=\"Refresh\">{v2}</button><label><input id=\"artifact-wrap\" type=\"checkbox\" checked> Wrap lines</label><a id=\"artifact-raw\" target=\"_blank\" rel=\"noopener\">Raw text</a></div>\n    <div class=\"artifact-source\"><div class=\"artifact-source-row\"><label>Version <select id=\"artifact-source-mode\"><option value=\"current\">Current file</option><option value=\"archive\">Archive</option></select></label><button class=\"icon-button\" id=\"artifact-source-toggle\" type=\"button\" aria-expanded=\"false\" aria-controls=\"artifact-provenance\" aria-label=\"Source details\" title=\"Source details\">{v3}</button><span id=\"artifact-metadata\"></span><span id=\"artifact-status\" role=\"status\"></span></div><p id=\"artifact-provenance\" hidden></p></div>\n    <div class=\"artifact-main\"><nav id=\"artifact-toc\" aria-label=\"Table of contents\"></nav><div id=\"artifact-body\" tabindex=\"0\"></div></div><footer><button class=\"icon-button\" id=\"artifact-prev\" title=\"Previous page\" aria-label=\"Previous page\">{v4}</button><button class=\"icon-button\" id=\"artifact-next\" title=\"Next page\" aria-label=\"Next page\">{v5}</button></footer>"
  },
  "viewer.e05b680c08a7": {
    "ru": "Просмотр результата",
    "en": "Result viewer"
  },
  "shell.skip": {
    "ru": "Перейти к содержимому",
    "en": "Skip to content"
  },
  "shell.chooseProject": {
    "ru": "Выбрать проект",
    "en": "Choose a project"
  },
  "shell.projects": {
    "ru": "Проекты",
    "en": "Projects"
  },
  "shell.workspace": {
    "ru": "РАБОЧЕЕ ПРОСТРАНСТВО",
    "en": "WORKSPACE"
  },
  "shell.sections": {
    "ru": "Разделы проекта",
    "en": "Project sections"
  },
  "shell.local": {
    "ru": "Локальный портал",
    "en": "Local portal"
  },
  "shell.history": {
    "ru": "История остаётся с проектом",
    "en": "History stays with the project"
  },
  "shell.breadcrumb": {
    "ru": "Проект / Обзор",
    "en": "Project / Overview"
  },
  "shell.connecting": {
    "ru": "Подключение…",
    "en": "Connecting…"
  },
  "shell.loading": {
    "ru": "Загрузка проекта…",
    "en": "Loading project…"
  },
  "shell.footer": {
    "ru": "Project Hub · Единый центр проекта",
    "en": "Project Hub · Your project hub"
  },
  "shell.waiting": {
    "ru": "Ожидание данных",
    "en": "Waiting for data"
  },
  "i18n.saved": {
    "ru": "Язык интерфейса сохранён.",
    "en": "Interface language saved."
  },
  "i18n.loadError": {
    "ru": "Не удалось получить настройки языка.",
    "en": "Could not load language preferences."
  },
  "i18n.saveError": {
    "ru": "Не удалось подтвердить сохранение языка. Повторите выбор.",
    "en": "Could not confirm the language change. Select it again to retry."
  },
  "i18n.conflict": {
    "ru": "Язык изменён другим пользователем. Обновите настройки и повторите выбор.",
    "en": "The language was changed by another user. Refresh preferences and select it again."
  },
  "i18n.unknownError": {
    "ru": "Не удалось выполнить действие. Проверьте сведения об операции и повторите попытку.",
    "en": "Could not complete the action. Check the operation details and try again."
  },
  "i18n.networkError": {
    "ru": "Нет ответа сервера. Проверьте подключение и повторите действие.",
    "en": "The server did not respond. Check the connection and try again."
  },
  "connections.eyebrow": {"ru":"PROJECT HUB","en":"PROJECT HUB"},
  "connections.title": {"ru":"Подключения агентов","en":"Agent connections"},
  "connections.intro": {"ru":"Пригласите агента из любого приложения. Подключение действует для этой установки Hub; агент выбирает проект и папку кода в своих запросах.","en":"Invite an agent from any application. The connection belongs to this Hub installation; the agent selects its project and code folder on each request."},
  "connections.existing": {
    "ru": "Существующий проект",
    "en": "Existing project"
  },
  "connections.newProject": {
    "ru": "Новый проект агента",
    "en": "New agent project"
  },
  "connections.choose": {
    "ru": "Выберите проект",
    "en": "Choose a project"
  },
  "connections.generate": {"ru":"Пригласить агента","en":"Invite an agent"},
  "connections.invitation": {"ru":"Ссылка-приглашение","en":"Invitation link"},
  "connections.copy": {"ru":"Скопировать ссылку","en":"Copy link"},
  "connections.copied": {"ru":"Скопировано","en":"Link copied"},
  "connections.copyFallback": {"ru":"Выделено: скопируйте вручную","en":"Link selected. Copy it manually."},
  "connections.expires": {"ru":"Действует до {date}","en":"Expires {date}"},
  "connections.connections": {"ru":"Зарегистрированные подключения","en":"Registered connections"},
  "connections.empty": {"ru":"Зарегистрированных подключений пока нет. Вы можете пригласить агента до добавления проектов.","en":"No registered connections yet. You can invite an agent before adding projects."},
  "connections.loading": {"ru":"Загрузка подключений…","en":"Loading connections…"},
  "connections.refresh": {"ru":"Обновить","en":"Refresh"},
  "connections.revoke": {"ru":"Отключить","en":"Disconnect"},
  "connections.revoked": {"ru":"Подключение отключено","en":"Connection disconnected"},
  "connections.registered": {"ru":"Зарегистрировано","en":"Registered"},
  "connections.clientInfo": {"ru":"Приложение: {client}","en":"Application: {client}"},
  "connections.pending": {"ru":"Исход предыдущего изменения неизвестен. Повторите тот же запрос вручную для подтверждения; новые изменения пока недоступны.","en":"The outcome of the previous change is unknown. Manually retry the same request to confirm it; new changes are unavailable until then."},
  "connections.retry": {"ru":"Повторить последнее изменение","en":"Retry the last change"},
  "connections.errorLoad": {"ru":"Не удалось загрузить подключения.","en":"Could not load connections."},
  "connections.errorProjects": {
    "ru": "Не удалось загрузить проекты.",
    "en": "Could not load projects."
  },
  "connections.errorMutation": {"ru":"Не удалось изменить подключение.","en":"Could not change the connection."},
  "connections.confirmRevoke": {"ru":"Отключить доступ этого агента к Hub? Его токен перестанет работать. История и ссылки на чаты сохранятся; доступ можно выдать снова через повторное подключение.","en":"Disconnect this agent from Hub? Its token will stop working. History and chat links are preserved; Reconnect can grant access again."},
  "connections.noProject": {
    "ru": "Проект не указан",
    "en": "No project specified"
  },
  "connections.noDate": {
    "ru": "Срок не указан",
    "en": "No expiry specified"
  },
  "connections.unknown": {"ru":"Неизвестно","en":"Unknown"},
  "connections.newHelp": {
    "ru": "При подключении агент выберет название проекта и при необходимости укажет папки исходников и рабочее пространство.",
    "en": "When connecting, the agent chooses the project name and can specify source folders and a workspace."
  },
  "connections.invitationHelp": {"ru":"Передайте ссылку только нужному агенту: она выдаёт доступ к зарегистрированным проектам этой установки. Агент сообщает своё приложение и подключает MCP через HTTP или использует API. Ссылка содержит секрет; не сохраняйте её в общих документах.","en":"Share this link only with the intended agent: it grants access to registered projects in this installation. The agent reports its application and connects MCP over HTTP or uses the API. The link contains a secret; keep it out of shared documents."},
  "connections.registrationHelp": {"ru":"Регистрация показывает выданный доступ. Недавний запрос подтверждает обращение к Hub, но не выполнение агента или постоянное соединение. Данные о модели и чате могут быть неизвестны.","en":"Registration records granted access. A recent request confirms an interaction with Hub, but does not prove agent execution or a persistent connection. Model and chat details may be unknown."},
  "connections.invalidProject": {
    "ru": "Выберите существующий проект или новый проект агента.",
    "en": "Choose an existing project or a new agent project."
  },
  "connections.invalidAck": {"ru":"Сервер не подтвердил результат изменения.","en":"The server did not confirm the result of the change."},
  "storage.title": {
    "ru": "Данные Hub",
    "en": "Hub data"
  },
  "storage.intro": {
    "ru": "Подключите прежнюю папку данных или восстановленную резервную копию. Импорт сохраняет исходные данные и создаёт отдельную копию.",
    "en": "Connect an existing data folder or a restored backup. Import preserves the original and creates a separate copy."
  },
  "storage.active": {
    "ru": "Рабочее хранилище",
    "en": "Active storage"
  },
  "storage.folder": {
    "ru": "Папка данных на сервере",
    "en": "Data folder on this server"
  },
  "storage.inspect": {
    "ru": "Проверить содержимое",
    "en": "Inspect contents"
  },
  "storage.refresh": {
    "ru": "Обновить",
    "en": "Refresh"
  },
  "storage.preview": {
    "ru": "Предварительный просмотр импорта",
    "en": "Import preview"
  },
  "storage.tasks": {
    "ru": "задач",
    "en": "tasks"
  },
  "storage.wholeHome": {
    "ru": "Подключается всё хранилище с найденными проектами. Проекты с совпадающими именами автоматически не объединяются.",
    "en": "The whole storage and its projects are connected. Projects with matching names are not automatically merged."
  },
  "storage.upgrade": {
    "ru": "Обновить формат копии",
    "en": "Upgrade copied format"
  },
  "storage.activate": {
    "ru": "Использовать эту копию",
    "en": "Use this copy"
  },
  "storage.import": {
    "ru": "Импортировать копию",
    "en": "Import a copy"
  },
  "storage.copies": {
    "ru": "Подготовленные копии",
    "en": "Prepared copies"
  },
  "storage.launcherRequired": {
    "ru": "Для переключения хранилища запустите Hub через ярлык установленного приложения. Просмотр и импорт доступны также при запуске из исходников.",
    "en": "To switch storage, start Hub using its installed application shortcut. Viewing and import are also available when running from source."
  },
  "storage.operation": {
    "ru": "Переключение хранилища",
    "en": "Storage activation"
  },
  "storage.retry": {
    "ru": "Повторить тот же запрос",
    "en": "Retry the same request"
  },
  "storage.pending": {
    "ru": "Результат предыдущего запроса не подтверждён. Повторите его перед новым изменением.",
    "en": "The previous request is not confirmed. Retry it before making another change."
  },
  "storage.working": {
    "ru": "Выполняется операция…",
    "en": "Working…"
  },
  "storage.switching": {
    "ru": "Сервер переключает хранилище. Соединение восстановится автоматически.",
    "en": "The server is switching storage. The connection will recover automatically."
  },
  "storage.importing": {
    "ru": "Копия импортируется в фоне. Она появится в списке после проверки.",
    "en": "The copy is being imported in the background. It will appear in the list after verification."
  },
  "storage.ready": {
    "ru": "Проверка завершена.",
    "en": "Inspection complete."
  },
  "storage.failed": {
    "ru": "Операция не выполнена.",
    "en": "Operation failed."
  },
  "storage.queued": {
    "ru": "Ожидает выполнения",
    "en": "Queued"
  },
  "storage.running": {
    "ru": "Выполняется",
    "en": "Running"
  },
  "storage.succeeded": {
    "ru": "Завершено",
    "en": "Completed"
  },
  "storage.interrupted": {
    "ru": "Прервано; проверьте обе папки данных.",
    "en": "Interrupted; inspect both data folders."
  },
  "storage.rollback": {
    "ru": "Прежнее хранилище восстановлено",
    "en": "Previous storage restored"
  },
  "storage.upgradeConfirm": {
    "ru": "Обновить формат этой неактивной копии? Исходная папка и рабочее хранилище сохраняются.",
    "en": "Upgrade this inactive copy? The original folder and active storage are preserved."
  },
  "subsystems.manage": {"ru":"Управление подсистемами","en":"Manage subsystems"},
  "subsystems.projectOverview": {"ru":"Обзор проекта","en":"Project overview"},
  "subsystems.projectActions": {"ru":"Действия с проектом","en":"Project actions"},
  "subsystems.subsystemActions": {"ru":"Действия с подсистемой","en":"Subsystem actions"},
  "subsystems.editSubsystem": {"ru":"Редактировать подсистему","en":"Edit subsystem"},
  "subsystems.createChild": {"ru":"Добавить дочернюю подсистему","en":"Add child subsystem"},
  "subsystems.editHelp": {"ru":"Измените название, описание и границы подсистемы. Её идентификатор и история сохранятся.","en":"Edit the subsystem's name, description and boundaries. Its identifier and history are preserved."},
  "subsystems.createHelp": {"ru":"Укажите название и назначение новой подсистемы. При необходимости выберите родителя и относительные пути к её коду.","en":"Name the new subsystem and describe its purpose. Optionally select a parent and relative paths to its code."},
  "subsystems.close": {"ru":"Закрыть","en":"Close"},
  "subsystems.confirmRemove": {"ru":"Удалить подсистему","en":"Remove subsystem"},
  "subsystems.confirmAnalysis": {"ru":"Запустить анализ","en":"Start analysis"},
  "subsystems.intro": {"ru":"Начните с обзора проекта и основных подсистем, затем уточняйте их состав. Редактирование сохраняет идентификаторы и историю.","en":"Start with the project overview and main subsystems, then refine their composition. Edits preserve identifiers and history."},
  "subsystems.overview": {"ru":"Описать обзор проекта","en":"Describe project overview"},
  "subsystems.firstLevel": {"ru":"Описать основные подсистемы","en":"Describe main subsystems"},
  "subsystems.create": {"ru":"Добавить подсистему","en":"Add subsystem"},
  "subsystems.edit": {"ru":"Редактировать","en":"Edit"},
  "subsystems.analyze": {"ru":"Обновить описание агентом","en":"Update description with an agent"},
  "subsystems.remove": {"ru":"Удалить пустую подсистему","en":"Remove empty subsystem"},
  "subsystems.title": {"ru":"Название","en":"Name"},
  "subsystems.parent": {"ru":"Родительская подсистема","en":"Parent subsystem"},
  "subsystems.topLevel": {"ru":"Первый уровень","en":"Top level"},
  "subsystems.paths": {"ru":"Границы кода","en":"Code boundaries"},
  "subsystems.pathsHelp": {"ru":"По одному относительному префиксу пути на строку. Изменение границ вступит в силу для фактов кода после сканирования.","en":"One relative path prefix per line. Code facts reflect changed boundaries after scanning."},
  "subsystems.description": {"ru":"Краткое описание","en":"Short description"},
  "subsystems.save": {"ru":"Сохранить","en":"Save"},
  "subsystems.cancel": {"ru":"Отмена","en":"Cancel"},
  "subsystems.retry": {"ru":"Повторить сохранение","en":"Retry save"},
  "subsystems.working": {"ru":"Выполняется…","en":"Working…"},
  "subsystems.saved": {"ru":"Подсистема сохранена","en":"Subsystem saved"},
  "subsystems.failed": {"ru":"Не удалось выполнить действие. Обновите данные и проверьте результат.","en":"Action failed. Refresh the data and check the result."},
  "subsystems.changeReason": {"ru":"Изменение подсистемы через интерфейс","en":"Subsystem edited through the interface"},
  "subsystems.started": {"ru":"Запрос агенту отправлен. Результат появится в истории исследований.","en":"Agent request submitted. The result will appear in research history."},
  "subsystems.analysisConfirm": {"ru":"Запустить анализ агентом? Результат будет сохранён в проекте.","en":"Start agent analysis? The result will be saved in this project."},
  "subsystems.removeConfirm": {"ru":"Удалить пустую подсистему из структуры? История сохранится. Подсистему с дочерними элементами или связями сначала нужно переразметить.","en":"Remove this empty subsystem from the structure? History is preserved. Reassign children and references before removing a subsystem that contains them."},
  "storage.activateConfirm": {
    "ru": "Переключить весь Hub на эту копию? Прежнее хранилище сохраняется в своей папке. Дождитесь завершения резервирования и других операций.",
    "en": "Switch the whole Hub to this copy? The previous storage is preserved in its folder. Wait for backups and other operations to finish."
  },
  "workspaces.title": {"ru": "Рабочие папки кода", "en": "Code workspaces"},
  "workspaces.intro": {"ru": "Подключите папки кода на сервере для чтения исходников, Git и языкового анализа. Задачи и документы доступны без рабочей папки.", "en": "Connect code folders on the server for source reading, Git and language analysis. Tasks and documents work without a code workspace."},
  "workspaces.sourceAvailable": {"ru": "Исходники доступны", "en": "Source available"},
  "workspaces.sourceUnavailable": {"ru": "Исходники недоступны", "en": "Source unavailable"},
  "workspaces.gitDetected": {"ru": "Репозиторий Git найден", "en": "Git repository detected"},
  "workspaces.gitUnavailable": {"ru": "Git недоступен", "en": "Git unavailable"},
  "workspaces.lspNotChecked": {"ru": "Доступность языкового сервера проверяется при анализе", "en": "Language server availability is checked during analysis"},
  "workspaces.lspUnavailable": {"ru": "Языковой анализ недоступен", "en": "Language analysis unavailable"},
  "workspaces.folder": {"ru": "Папка кода на сервере", "en": "Code folder on the server"},
  "workspaces.relocate": {"ru": "Изменить расположение", "en": "Change location"},
  "workspaces.disable": {"ru": "Отключить", "en": "Disable"},
  "workspaces.enable": {"ru": "Включить", "en": "Enable"},
  "workspaces.refresh": {"ru": "Обновить сведения", "en": "Refresh details"},
  "workspaces.readOnly": {"ru": "Редактирование рабочих папок станет доступно после обновления формата хранилища.", "en": "Workspace editing becomes available after upgrading the storage format."},
  "workspaces.retry": {"ru": "Повторить сохранение", "en": "Retry save"},
  "workspaces.empty": {"ru": "Рабочие папки не подключены.", "en": "No code workspaces connected."},
  "workspaces.add": {"ru": "Подключить папку", "en": "Connect folder"},
  "workspaces.invalidAck": {"ru": "Ответ сервера не подтверждает действие. Проверьте результат или повторите тот же запрос.", "en": "The server response does not confirm the operation. Check the result or retry the same request."},
  "workspaces.failed": {"ru": "Не удалось выполнить действие. Проверьте подключение и повторите запрос.", "en": "Operation failed. Check the connection and retry."},
  "workspaces.working": {"ru": "Сохраняется…", "en": "Saving…"},
  "workspaces.saved": {"ru": "Рабочая папка сохранена", "en": "Workspace saved"},
  "provider.title": {"ru":"Поставщики моделей","en":"Model providers"},
  "provider.intro": {"ru":"Настройте сервисы моделей для анализа из Hub. Эти настройки общие для установки и независимы от подключения агента через MCP.","en":"Configure model services for analysis from Hub. These settings apply across the installation and are independent of the agent MCP connection."},
  "provider.loading": {"ru":"Загрузка провайдеров…","en":"Loading providers…"},
  "provider.refresh": {"ru":"Обновить","en":"Refresh"},
  "provider.save": {"ru":"Сохранить провайдера","en":"Save provider"},
  "provider.select": {"ru":"Использовать для запросов Hub","en":"Use for Hub requests"},
  "provider.retry": {"ru":"Повторить последнее изменение","en":"Retry the last change"},
  "provider.pending": {"ru":"Результат изменения неизвестен. Повторите тот же запрос вручную.","en":"The outcome of the change is unknown. Manually retry the same request."},
  "provider.name": {"ru":"Название","en":"Name"},
  "provider.provider": {"ru":"Протокол API","en":"API protocol"},
  "provider.model": {"ru":"Точный идентификатор модели","en":"Exact model identifier"},
  "provider.endpoint": {"ru":"Конечная точка API","en":"API endpoint"},
  "provider.apiKey": {"ru":"API-ключ поставщика","en":"Provider API key"},
  "provider.apiKeyHelp": {"ru":"Укажите ключ из кабинета поставщика. Он не создаётся при приглашении агента и не совпадает с токеном Hub. Он также не заменяет отдельный ключ управления клиентом. Ключ хранится в защищённом хранилище установки и очищается после сохранения; сохранённый ключ здесь не показывается.","en":"Enter a key from the provider account. Inviting an agent does not create it, and it is separate from the Hub token. It also does not replace a separate client-control key. The key is stored in the installation vault and cleared after saving; a saved key is never shown here."},
  "provider.responses": {"ru":"OpenAI Responses","en":"OpenAI Responses"},
  "provider.anthropic": {"ru":"Anthropic","en":"Anthropic"},
  "provider.gemini": {"ru":"Google Gemini","en":"Google Gemini"},
  "provider.chat": {"ru":"Совместимый Chat Completions","en":"Compatible Chat Completions"},
  "provider.saved": {"ru":"Провайдер сохранён","en":"Provider saved"},
  "provider.selected": {"ru":"Выбран для запросов Hub","en":"Selected for Hub requests"},
  "provider.invalidAck": {"ru":"Сервер не подтвердил изменение.","en":"The server did not confirm the change."},
  "provider.loadError": {"ru":"Не удалось загрузить провайдеров.","en":"Could not load providers."},
  "provider.mutationError": {"ru":"Не удалось изменить провайдера.","en":"Could not change provider."},
  "provider.unavailable": {"ru":"Провайдеры недоступны.","en":"Providers are unavailable."},
  "provider.analyze": {"ru":"Анализировать","en":"Analyze"},
  "provider.apiScope": {"ru":"Анализ через API. Результат сохраняется в Hub; выполнение кода и продолжение чатов недоступны.","en":"API analysis. Results are saved in Hub; code execution and chat continuation are unavailable."},
  "provider.hubResult": {"ru":"Результат в Hub","en":"Result in Hub"},
  "provider.openResult": {"ru":"Открыть результат","en":"Open result"},
  "provider.chatgptError": {"ru":"Не удалось выполнить действие ChatGPT. Повторите попытку или проверьте подключение.","en":"Could not complete the ChatGPT action. Try again or check the connection."},
  "provider.proposalApplied": {"ru": "Основные подсистемы сохранены. Чтобы обновить принадлежность кода, выполните сканирование исходников.", "en": "First-level subsystems were saved. Scan the source files to update code ownership."},
  "provider.proposalInvalid": {"ru": "Результат анализа сохранён. Предложение подсистем не прошло проверку; существующая структура сохранена.", "en": "The analysis result was saved. The subsystem proposal could not be validated; the existing structure was preserved."},
  "provider.proposalConflict": {"ru": "Результат анализа сохранён. Структура проекта изменилась во время анализа; проверьте предложение перед применением.", "en": "The analysis result was saved. Project structure changed during analysis; review the proposal before applying it."},
  "subsystems.confirmation": {"ru": "Подтверждение действия", "en": "Confirm action"},
  "subsystems.confirmAnalysis": {"ru": "Начать анализ", "en": "Start analysis"},
  "subsystems.confirmRemove": {"ru": "Удалить подсистему", "en": "Remove subsystem"},
  "settings.nativeWorkflow": {
    "ru": "<section class=\"card\" id=\"hub-native-workflow\"><h2>Постоянные правила для агента</h2><p>В разделе <a href=\"#settings/agents\">«Агенты и подключения»</a> создайте универсальное приглашение и передайте ссылку агенту. Он получит правила работы с Hub и инструкции подключения.</p><p>Сохраните правила как постоянную инструкцию в приложении агента. Затем откройте новый чат и проверьте, что агент читает правило, выбирает зарегистрированный проект, видит его через hub_context и записывает задачу и этап.</p><p>Храните доступ приватно, отдельно от исходников и текста правил. Независимое подключение MCP не требует плагина Codex, skills или обработчиков событий. Разрешения и подтверждения доверия задаёт приложение агента.</p></section>",
    "en": "<section class=\"card\" id=\"hub-native-workflow\"><h2>Permanent rules for your agent</h2><p>In <a href=\"#settings/agents\">Agents and connections</a>, create a universal invitation and share its link with the agent. It receives the Hub workflow and connection instructions.</p><p>Save the workflow as a permanent instruction in the agent application. Then open a new conversation and verify that the agent reads the rule, selects a registered project, sees it through hub_context, and records a task and stage.</p><p>Keep credentials private, separate from source files and rule text. The independent MCP connection requires no Codex plugin, skills or event hooks. The agent application controls permissions and trust prompts.</p></section>"
  },
  "settings.legacyCodexTitle": {
    "ru": "Прежнее подключение Codex через плагин",
    "en": "Legacy Codex plugin connection"
  },
  "settings.legacyCodexHelp": {
    "ru": "Этот необязательный раздел относится к прежнему плагину Codex: его пользовательской инструкции, скриптам и обработчикам событий. Редактор меняет только файл этого подключения; постоянные правила независимого подключения редактируются в приложении агента.",
    "en": "This optional section is for the legacy Codex plugin: its user instruction, scripts and event hooks. The editor changes only that connection's file; edit permanent rules for the independent connection in the agent application."
  },
  "connections.model": {"ru":"Модель: {model}","en":"Model: {model}"},
  "connections.modelUnknown": {"ru":"Модель не сообщена","en":"Model not reported"},
  "connections.globalScope": {"ru":"Все зарегистрированные проекты · выбор в каждом запросе","en":"All registered projects · selected on each request"},
  "connections.legacyScope": {"ru":"Доступ ограничен проектом: {project}","en":"Access limited to project: {project}"},
  "connections.recentRequest": {"ru":"Недавний запрос к Hub","en":"Recent Hub request"},
  "connections.activityUnknown": {"ru":"Текущая активность неизвестна","en":"Current activity unknown"},
  "connections.lastRequest": {"ru":"Последний запрос: {date}","en":"Last request: {date}"},
  "connections.reportedIdentity": {"ru":"Сведения об приложении, модели и чате сообщает сам клиент.","en":"Application, model and chat details are reported by the client."},
  "connections.connectionDetails": {"ru":"Сведения о подключении","en":"Connection details"},
  "connections.externalId": {"ru":"Идентификатор клиента: {externalId}","en":"Client identifier: {externalId}"},
  "connections.chat": {"ru":"Чат: {chat}","en":"Chat: {chat}"},
  "connections.session": {"ru":"Сессия: {session}","en":"Session: {session}"},
  "provider.nameHelp": {"ru":"Понятное имя, чтобы отличать подключение от других.","en":"A clear name for distinguishing this connection."},
  "provider.providerHelp": {"ru":"Формат запросов, который принимает этот сервис.","en":"The request format accepted by this service."},
  "provider.modelHelp": {"ru":"Укажите точный идентификатор модели из кабинета выбранного поставщика.","en":"Enter the exact model identifier from the selected provider account."},
  "provider.endpointHelp": {"ru":"Для совместимого Chat Completions можно указать свой URL; для Responses, Anthropic и Gemini используется адрес выбранного протокола.","en":"You may provide a custom URL for compatible Chat Completions; Responses, Anthropic, and Gemini use the selected protocol address."},
  "provider.endpointDefault": {"ru":"Оставьте поле пустым, чтобы использовать адрес протокола.","en":"Leave blank to use the protocol address."},
  "provider.configuredTitle": {"ru":"Сохранённые подключения","en":"Saved connections"},
  "provider.hubExecutor": {"ru":"Исполнитель запросов Hub","en":"Hub request executor"},
  "provider.noneTitle": {"ru":"Без исполнителя","en":"No executor"},
  "provider.noneHelp": {"ru":"Запросы Hub к провайдеру отключены.","en":"Hub requests to a provider are disabled."},
  "provider.notSelected": {"ru":"Не выбран","en":"Not selected"},
  "actions.placeholder": {"ru":"Будущие действия проекта появятся в этом разделе.","en":"Future project actions will appear in this section."},
  "research.historyError": {"ru":"Не удалось прочитать историю запросов.","en":"Could not read request history."},
  "research.historyInvalid": {"ru":"Неверный ответ истории запросов.","en":"Invalid request history response."},
  "research.history": {"ru":"История запросов","en":"Request history"},
  "research.refreshHistory": {"ru":"Обновить историю","en":"Refresh history"},
  "research.projectActivity": {"ru":"{active} чатов работают · {waiting} ожидают · {unknown} без данных","en":"{active} chats working · {waiting} waiting · {unknown} unknown"},
  "research.observedActivity": {"ru":"По последним событиям подключённых агентов.","en":"Based on recent events from connected agents."},
  "research.provider": {"ru":"Провайдер исследования","en":"Research provider"},
  "research.selectProvider": {"ru":"Выберите провайдера","en":"Select a provider"},
  "research.configureProvider": {"ru":"Подключите провайдера в настройках агентов и подключений.","en":"Connect a provider in Agents and connections settings."},
  "research.requestError": {"ru":"Не удалось отправить исследование.","en":"Could not send the research request."},
  "research.toolResultLimit": {"ru":"Анализ не завершился: объём данных, возвращённых инструментами, превысил допустимый лимит.","en":"Analysis did not complete: tool results exceeded the allowed size limit."},
  "research.readBudgetLimit": {"ru":"Анализ достиг лимита чтений или шагов и не вернул итоговый ответ. Результат не сохранён.","en":"Analysis reached its read or turn limit without returning a final answer. No result was saved."},
  "research.providerTimeout": {"ru":"Проблема соединения с сервисом модели.","en":"There is a problem connecting to the model service."},
  "research.networkFailure": {"ru":"Проблема соединения с сервисом модели.","en":"There is a problem connecting to the model service."},
  "research.noModel": {"ru":"Не выбрана модель.","en":"No model is selected."},
  "research.chooseModel": {"ru":"Выбрать модель","en":"Choose a model"},
  "research.connectionRequired": {"ru":"Для анализа требуется доступ к модели.","en":"Model access is required for analysis."},
  "research.configureConnection": {"ru":"Настроить подключение","en":"Set up connection"},
  "research.failureUnknown": {"ru":"Не удалось завершить анализ.","en":"The analysis could not be completed."},
  "research.requested": {"ru":"Запрос сохранён","en":"Request saved"},
  "research.accepted": {"ru":"Запрос принят","en":"Request accepted"},
  "research.running": {"ru":"Выполняется","en":"Running"},
  "research.completed": {"ru":"Завершено","en":"Completed"},
  "research.failed": {"ru":"Ошибка","en":"Failed"},
  "research.interrupted": {"ru":"Прервано","en":"Interrupted"},
  "research.cancelled": {"ru":"Отменено","en":"Cancelled"},
  "research.needsAttention": {"ru":"Требует проверки","en":"Needs review"},
  "research.outcomeUnknown": {"ru":"Результат неизвестен","en":"Outcome unknown"},
  "research.documentationTitle": {"ru":"Исследование документации","en":"Documentation research"},
  "research.architectureTitle": {"ru":"Исследование архитектуры и кода","en":"Architecture and code research"},
  "research.documentationScope": {"ru":"Исследуйте материалы и исходники проекта. Результат сохраняется отдельным документом с источниками и ограничениями.","en":"Research the project materials and sources. The result is saved as a separate document with sources and limitations."},
  "research.architectureScope": {"ru":"Результаты сохраняются в знаниях проекта с источниками и ограничениями.","en":"Results are saved in project knowledge with sources and limitations."},
  "research.projectDocuments": {"ru":"Документация проекта","en":"Project documentation"},
  "research.purpose": {"ru":"Цель исследования","en":"Research purpose"},
  "research.question": {"ru":"Что нужно выяснить","en":"What do you want to learn"},
  "research.detail": {"ru":"Подробность ответа","en":"Answer detail"},
  "research.projectDetail": {"ru":"Объём описания","en":"Description length"},
  "research.subsystemLimitLabel": {"ru":"Детальность структуры","en":"Structure detail"},
  "research.subsystemLimit5": {"ru":"Крупные подсистемы — до 5","en":"Major subsystems — up to 5"},
  "research.subsystemLimit8": {"ru":"Основные части — до 8","en":"Main parts — up to 8"},
  "research.subsystemLimit10": {"ru":"Подробная карта — до 10","en":"Detailed map — up to 10"},
  "research.projectFocus": {"ru":"На что обратить внимание (необязательно)","en":"What to focus on (optional)"},
  "provider.chatgptModelDetails": {"ru":"Безопасные сведения обновления моделей","en":"Safe model refresh details"},
  "provider.probeCompleted": {"ru":"Проверка завершена успешно","en":"Probe completed successfully"},
  "provider.probeCompletedHelp": {"ru":"Соединение с сервисом установлено. Ответ на тестовый запрос к выбранной модели получен и прочитан Hub.","en":"Connected to the service. Hub received and read the response to a test request to the selected model."},
  "research.subsystemLimitHelp": {"ru":"Верхняя граница числа подсистем первого уровня, а не обязательное количество. Вложенные подсистемы можно уточнить позже.","en":"The maximum number of first-level subsystems, not a required count. You can refine nested subsystems later."},
  "research.brief": {"ru":"Кратко","en":"Brief"},
  "research.standard": {"ru":"Стандартно","en":"Standard"},
  "research.detailed": {"ru":"Подробно","en":"Detailed"},
  "research.start": {"ru":"Начать исследование","en":"Start research"},
  "research.close": {"ru":"Закрыть","en":"Close"},
  "research.refresh": {"ru":"Обновить статус","en":"Refresh status"},
  "research.cancel": {"ru":"Отменить исследование","en":"Cancel research"},
  "research.verifyOutcome": {"ru":"Обновите статус перед новым запросом.","en":"Refresh the status before a new request."},
  "research.selectedResult": {"ru":"Выбранный результат исследования","en":"Selected research result"},
  "research.currentMap": {"ru":"Вся текущая карта","en":"The entire current map"},
  "research.subsystemScope": {"ru":"Подсистема, её состав и необходимые связи с остальным проектом.","en":"The subsystem, its contents, and relevant relationships with the rest of the project."},
  "research.objectScope": {"ru":"Выбранный объект и необходимые связи из исходников.","en":"The selected object and relevant relationships from source files."},
  "research.documentation-draft": {"ru":"Подготовить материал","en":"Draft documentation"},
  "research.documentation-refresh": {"ru":"Предложить обновление","en":"Propose an update"},
  "research.documentation-review": {"ru":"Проверить документацию","en":"Review documentation"},
  "projects.agentConnections": {"ru":"Агенты и подключения","en":"Agents and connections"},
  "research.invalidRequest": {"ru":"Выберите допустимую область исследования.","en":"Select a supported research scope."},
  "research.selectedObject": {"ru":"Выбранный объект","en":"Selected object"},
  "research.linkedChat": {"ru":"Связанный чат","en":"Linked chat"},
  "research.providerResearch": {"ru":"Исследование провайдера","en":"Provider research"},
  "research.custom": {"ru":"Исследование","en":"Research"},
  "research.mapScope": {"ru":"{scope} · {nodes} элементов · {relations} связей","en":"{scope} · {nodes} elements · {relations} relationships"},
  "research.projectScope": {"ru":"Обзор проекта и его основные подсистемы.","en":"The project overview and its main subsystems."},
  "research.projectOverviewHelp": {"ru":"Текст появится в разделе «Обзор проекта» на странице «Архитектура и код». Предыдущие версии останутся в истории.","en":"The text will appear in Project overview under Architecture and code. Earlier versions remain in history."},
  "research.projectSubsystemsHelp": {"ru":"Подсистемы первого уровня появятся в навигаторе и на карте. Существующие подсистемы сохранятся; вложенные уровни можно уточнить позже.","en":"First-level subsystems will appear in the navigator and map. Existing subsystems are kept; you can refine nested levels later."},
  "connections.reconnect": {"ru":"Подключить снова","en":"Reconnect"},
  "connections.reconnectInvitation": {"ru":"Приглашение для повторного подключения","en":"Reconnection invitation"},
  "connections.reconnectHelp": {"ru":"Эта ссылка восстанавливает то же подключение. История и прежние ссылки на чаты сохраняются. Передайте ссылку агенту в том же приложении.","en":"This link restores the same connection. History and earlier chat links are preserved. Give it to the agent in the same application."},
  "connections.setupTitle": {"ru":"Как подключить агента через MCP","en":"Connect an agent through MCP"},
  "connections.setupClient": {"ru":"Передайте приглашение агенту в выбранном приложении. Он сообщит своё приложение и доступные сведения о модели; проект заранее выбирать не нужно.","en":"Give the invitation to an agent in your chosen application. It reports its application and available model details; no project selection is needed beforehand."},
  "connections.setupMcp": {"ru":"Агент получает адрес Hub и закрытый токен доступа, затем настраивает MCP в приложении. Если приложение не поддерживает самостоятельную настройку, агент объясняет ручные действия.","en":"The agent receives the Hub address and private access token, then configures MCP in the application. If the application cannot configure itself, the agent explains the manual steps."},
  "connections.setupRules": {"ru":"Перед записью постоянных правил агент показывает полный текст, файл назначения и область: проект или всё приложение. Запись выполняется только после вашего явного согласия; ключи в правила не включаются.","en":"Before writing persistent rules, the agent shows the full text, destination file and scope: a project or the whole application. It writes only after your explicit consent; credentials are excluded from the rules."},
  "connections.setupTest": {"ru":"Проверьте доступ к инструментам и работу в новом чате. Сообщать Hub о нативных чатах можно по желанию: это сохраняет ссылки, но не передаёт право управления приложением.","en":"Check tool access and try a new chat. Native chat reporting to Hub is optional: it preserves links without granting application control."},
  "connections.nativeChatsOptional": {"ru":"Сведения о нативных чатах необязательны. Старые ссылки остаются в истории после отключения агента.","en":"Native chat details are optional. Earlier links remain in history after disconnecting the agent."},
  "connections.provider": {"ru":"Поставщик модели: {provider}","en":"Model provider: {provider}"},
  "connections.capabilities": {"ru":"Возможности клиента","en":"Client capabilities"},
  "connections.capabilitiesHelp": {"ru":"Профиль сообщает сам клиент. Проверка подтверждает только функции, для которых описан доступный интерфейс; недавний запрос к Hub не подтверждает остальные возможности.","en":"The client reports its own profile. Testing confirms only functions with a documented, available interface; a recent Hub request does not confirm the other capabilities."},
  "connections.noProfile": {"ru":"Клиент ещё не сообщил профиль возможностей.","en":"The client has not reported its capability profile."},
  "connections.test": {"ru":"Проверить возможности","en":"Test capabilities"},
  "connections.tests": {"ru":"Проверка возможностей","en":"Capability tests"},
  "connections.testsEmpty": {"ru":"Проверка ещё не выполнялась.","en":"No capability tests have run yet."},
  "connections.testProgress": {"ru":"Завершено {done} из {total}","en":"Completed {done} of {total}"},
  "connections.testStarted": {"ru":"Начало: {date}","en":"Started: {date}"},
  "connections.testFinished": {"ru":"Завершение: {date}","en":"Finished: {date}"},
  "connections.testDeadline": {"ru":"Ожидание ответа до {date}","en":"Waiting for a response until {date}"},
  "connections.testOverdue": {"ru":"Срок ожидания истёк; итоговый результат пока не получен.","en":"The deadline passed; a final result has not been received yet."},
  "connections.stateDeclared": {"ru":"Сообщено клиентом","en":"Reported by the client"},
  "connections.stateVerified": {"ru":"Проверено","en":"Verified"},
  "connections.stateUnavailable": {"ru":"Недоступно","en":"Unavailable"},
  "connections.stateUnknown": {"ru":"Неизвестно","en":"Unknown"},
  "connections.stateFailed": {"ru":"Ошибка проверки","en":"Test failed"},
  "connections.stateRunning": {"ru":"Проверяется…","en":"Testing…"},
  "connections.stateTimeout": {"ru":"Время ожидания истекло","en":"Timed out"},
  "connections.statePending": {"ru":"Ожидает проверки","en":"Waiting for a test"},
  "connections.stateCancelled": {"ru":"Проверка отменена","en":"Test cancelled"},
  "connections.configurationRequired": {"ru":"Требуется настройка управления клиентом","en":"Client-control configuration required"},
  "connections.openChat": {"ru":"Открытие нативного чата","en":"Open a native chat"},
  "connections.createChat": {"ru":"Создание нативного чата","en":"Create a native chat"},
  "connections.sendMessage": {"ru":"Отправка в нативный чат","en":"Send to a native chat"},
  "connections.mcpTools": {"ru":"Инструменты Hub через MCP","en":"Hub tools through MCP"},
  "connections.persistentRules": {"ru":"Постоянные правила","en":"Persistent rules"},
  "connections.nativeChatReporting": {"ru":"Ссылки на нативные чаты","en":"Native chat links"},
  "connections.controlTitle": {"ru":"Управление клиентом","en":"Client control"},
  "connections.controlHelp": {"ru":"Настройте доступ, только если приложение предоставляет поддерживаемый интерфейс управления. Адрес, сообщённый агентом, — предварительное значение; он сохраняется только по вашей кнопке.","en":"Configure access only when the application provides a supported control interface. An address reported by the agent is a preview; it is saved only when you click the button."},
  "connections.controlProtocol": {"ru":"Протокол управления","en":"Control protocol"},
  "connections.controlEndpoint": {"ru":"Адрес интерфейса клиента","en":"Client interface address"},
  "connections.controlKey": {"ru":"Ключ управления клиентом","en":"Client-control key"},
  "connections.controlKeyHelp": {"ru":"Получите ключ в самом приложении. Это отдельный доступ: токен Hub и API-ключ поставщика модели здесь не подходят. Сохранённый ключ не показывается. Пустое поле сохраняет текущий ключ при том же адресе и протоколе; при смене адреса укажите новый ключ.","en":"Obtain this key from the application itself. This is separate access: the Hub token and model-provider API key cannot be used here. A saved key is never shown. Leave blank to keep the current key at the same address and protocol; enter a new key when changing the address."},
  "connections.controlSave": {"ru":"Сохранить доступ к клиенту","en":"Save client access"},
  "connections.controlSaved": {"ru":"Доступ к клиенту сохранён","en":"Client access saved"},
  "connections.controlMcp": {"ru":"MCP через HTTP","en":"MCP over HTTP"},
  "connections.controlHttp": {"ru":"HTTP JSON","en":"HTTP JSON"},
  "connections.controlConfigured": {"ru":"Ключ управления сохранён","en":"Client-control key saved"},
  "connections.controlMissing": {"ru":"Ключ управления не настроен","en":"Client-control key not configured"},
  "connections.rulesReported": {"ru":"Клиент сообщил сохранение правил","en":"The client reported saving the rules"},
  "connections.rulesManual": {"ru":"Клиент сообщил ручную настройку правил","en":"The client reported manual rule setup"},
  "connections.rulesDestination": {"ru":"Файл назначения: {destination}","en":"Destination file: {destination}"},
  "connections.rulesProjectScope": {"ru":"Область правил: проект","en":"Rule scope: project"},
  "connections.rulesApplicationScope": {"ru":"Область правил: приложение","en":"Rule scope: application"},
  "connections.stateWaitingReply": {"ru":"Ожидает ответа клиента","en":"Waiting for a client response"},
  "connections.requestTimeout": {"ru":"Ответ сервера не получен вовремя. Результат изменения может быть неизвестен.","en":"The server did not respond in time. The outcome of the change may be unknown."},
  "provider.apiScopeHelp": {"ru":"Запросы из архитектуры, кода и документации анализируют переданный контекст и сохраняют результат в Hub. Для работы с нативными чатами нужен отдельный поддерживаемый интерфейс клиента.","en":"Requests from architecture, code and documentation analyze the supplied context and save the result in Hub. Native chat access requires a separate supported client interface."},
  "connections.stateDocumented": {"ru":"Интерфейс описан","en":"Interface documented"},
  "connections.testImpact": {"ru":"Проверка может создать отдельный тестовый чат и отправить в него проверочное сообщение.","en":"Testing may create a separate test chat and send it a diagnostic message."},
  "connections.openChatNotVerified": {"ru":"Наличие ссылки не подтверждает, что окно приложения открылось. Открытие нативного чата остаётся непроверенным.","en":"A link does not confirm that the application window opened. Opening the native chat remains unverified."},
  "connections.testDetailUnknown": {"ru":"Пояснение к результату проверки недоступно.","en":"Further details about the test result are unavailable."},
  "connections.controlNewKeyRequired": {"ru":"Для нового адреса управления укажите новый ключ клиента.","en":"Enter a new client key for the new control address."},
  "connections.profileTitle": {"ru":"Профиль, сообщённый клиентом","en":"Client-reported profile"},
  "connections.profileHost": {"ru":"Среда клиента: {host}","en":"Client environment: {host}"},
  "connections.profileVersion": {"ru":"Версия клиента: {version}","en":"Client version: {version}"},
  "connections.nativeChatTitle": {"ru":"Нативный чат","en":"Native chat"},
  "connections.mcp": {"ru":"Доступ к инструментам Hub","en":"Access to Hub tools"},
  "connections.callback": {"ru":"Ответ из тестового чата","en":"Reply from the test chat"},
  "connections.testResultTitle": {"ru":"Проверка возможностей","en":"Capability check"},
  "connections.resultUntested": {"ru":"Эта возможность ещё не проверялась.","en":"This capability has not been tested yet."},
  "connections.resultHubRequest": {"ru":"Hub получил запрос с действующим токеном доступа.","en":"Hub received a request with a valid access token."},
  "connections.resultSourceLink": {"ru":"Ссылка на чат сообщена; открытие приложения не проверялось.","en":"A chat link was reported; opening the application has not been tested."},
  "connections.resultTimeout": {"ru":"Ответ из тестового чата не получен вовремя. Возможность остаётся неподтверждённой.","en":"The test chat did not reply before the deadline. The capability remains unconfirmed."},
  "connections.resultTesting": {"ru":"Проверяется выбранный интерфейс управления клиентом.","en":"Testing the selected client-control interface."},
  "connections.resultNoProfile": {"ru":"Клиент ещё не сообщил поддерживаемый интерфейс управления.","en":"The client has not reported a supported control interface."},
  "connections.resultConfigure": {"ru":"Сохраните настройки управления клиентом перед проверкой. Если приложение требует ключ, используйте его собственный ключ.","en":"Save client-control settings before testing. If the application requires a key, use its own key."},
  "connections.resultEndpointMismatch": {"ru":"Сохранённые настройки управления не совпадают с профилем клиента. Обновите профиль или настройки.","en":"Saved control settings do not match the client profile. Update the profile or settings."},
  "connections.resultCreateUnavailable": {"ru":"Настроенный интерфейс не предоставляет поддерживаемое действие создания чата.","en":"The configured interface has no supported chat-creation action."},
  "connections.resultAwaiting": {"ru":"Клиент вернул идентификатор тестового чата; ожидается ответ на проверочный запрос.","en":"The client returned a test chat identifier; waiting for a reply to the diagnostic request."},
  "connections.resultCreated": {"ru":"Интерфейс клиента вернул идентификатор нового чата.","en":"The client interface returned a new chat identifier."},
  "connections.resultOpeningUnknown": {"ru":"Интерфейс вернул ссылку; открытие окна приложения не подтверждено.","en":"The interface returned a link; opening the application window is unconfirmed."},
  "connections.resultNoSource": {"ru":"Интерфейс не вернул пригодную ссылку на чат.","en":"The interface did not return a usable chat link."},
  "connections.resultMessageAccepted": {"ru":"Интерфейс клиента принял сообщение для тестового чата.","en":"The client interface accepted a message for the test chat."},
  "connections.resultReply": {"ru":"Получен ответ, соответствующий проверочному запросу из тестового чата.","en":"A reply matching the diagnostic request arrived from the test chat."},
  "connections.resultProbeFailed": {"ru":"Проверка не завершилась. Проверьте протокол, отдельный ключ клиента и заявленные действия.","en":"The test did not complete. Check the protocol, separate client key and declared actions."},
  "connections.resultCorrelated": {"ru":"Полученный ответ соответствует проверочному запросу и тестовому чату.","en":"The reply matches the diagnostic request and test chat."}
};
