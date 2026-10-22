"use strict";

(function (global) {
  const view = {root:null, catalog:null, loading:false, busy:false, error:'', status:'', pending:null, invitation:null, pollTimer:null, controlDrafts:new Map(), projectSelections:new Map(), histories:new Map(), details:new Set(), selectedId:'', tab:'status', catalogPage:0};
  const copy = {
    eyebrow:'PROJECT HUB', title:'Подключения агентов', intro:'Пригласите агента из любого приложения. Подключение действует для этой установки Hub; агент выбирает проект и папку кода в своих запросах.',
    generate:'Пригласить агента', invitation:'Ссылка-приглашение', copy:'Скопировать ссылку', copied:'Скопировано', copyFallback:'Выделено: скопируйте вручную', expires:'Действует до {date}', connections:'Зарегистрированные подключения', empty:'Зарегистрированных подключений пока нет. Вы можете пригласить агента до добавления проектов.', loading:'Загрузка подключений…', refresh:'Обновить', revoke:'Отозвать доступ', revoked:'Доступ отозван', registered:'Зарегистрировано', clientInfo:'Приложение: {client}', retry:'Повторить последнее изменение', errorLoad:'Не удалось загрузить подключения.', errorMutation:'Не удалось изменить подключение.', confirmRevoke:'Отозвать доступ этого подключения? Действие нельзя отменить на сервере.', unknown:'Неизвестно', model:'Модель: {model}', modelUnknown:'Модель не сообщена', globalScope:'Все зарегистрированные проекты · выбор в каждом запросе', legacyScope:'Доступ ограничен проектом: {project}', recentRequest:'Недавний запрос к Hub', activityUnknown:'Текущая активность неизвестна', lastRequest:'Последний запрос: {date}', reportedIdentity:'Сведения об приложении, модели и чате сообщает сам клиент.', connectionDetails:'Сведения о подключении', externalId:'Идентификатор клиента: {externalId}', chat:'Чат: {chat}', session:'Сессия: {session}',
    invitationHelp:'Передайте ссылку только нужному агенту: она выдаёт доступ к зарегистрированным проектам этой установки. Агент сообщает своё приложение и подключает MCP через HTTP или использует API. Ссылка содержит секрет; не сохраняйте её в общих документах.', registrationHelp:'Регистрация показывает выданный доступ. Недавний запрос подтверждает обращение к Hub, но не выполнение агента или постоянное соединение. Данные о модели и чате могут быть неизвестны.', pending:'Исход предыдущего изменения неизвестен. Повторите тот же запрос вручную для подтверждения; новые изменения пока недоступны.', invalidAck:'Сервер не подтвердил результат изменения.'
  };
  const english = {eyebrow:'PROJECT HUB', title:'Agent connections', intro:'Invite an agent from any application. The connection belongs to this Hub installation; the agent selects its project and code folder on each request.', generate:'Invite an agent', invitation:'Invitation link', invitationHelp:'Share this link only with the intended agent: it grants access to registered projects in this installation. The agent reports its application and connects MCP over HTTP or uses the API. The link contains a secret; keep it out of shared documents.', copy:'Copy link', copied:'Link copied', copyFallback:'Link selected. Copy it manually.', expires:'Expires {date}', connections:'Registered connections', registrationHelp:'Registration records granted access. A recent request confirms an interaction with Hub, but does not prove agent execution or a persistent connection. Model and chat details may be unknown.', empty:'No registered connections yet. You can invite an agent before adding projects.', loading:'Loading connections…', refresh:'Refresh', revoke:'Revoke access', revoked:'Access revoked', registered:'Registered', clientInfo:'Application: {client}', pending:'The outcome of the previous change is unknown. Manually retry the same request to confirm it; new changes are unavailable until then.', retry:'Retry the last change', errorLoad:'Could not load connections.', errorMutation:'Could not change the connection.', invalidAck:'The server did not confirm the result of the change.', confirmRevoke:'Revoke access for this connection? This cannot be undone on the server.', unknown:'Unknown', model:'Model: {model}', modelUnknown:'Model not reported', globalScope:'All registered projects · selected on each request', legacyScope:'Access limited to project: {project}', recentRequest:'Recent Hub request', activityUnknown:'Current activity unknown', lastRequest:'Last request: {date}', reportedIdentity:'Application, model and chat details are reported by the client.', connectionDetails:'Connection details', externalId:'Client identifier: {externalId}', chat:'Chat: {chat}', session:'Session: {session}'};
  Object.assign(copy, {
    revoke:'Отключить', revoked:'Подключение отключено', reconnect:'Подключить снова', reconnectInvitation:'Приглашение для повторного подключения', reconnectHelp:'Эта ссылка восстанавливает то же подключение. История и прежние ссылки на чаты сохраняются. Передайте ссылку агенту в том же приложении.',
    confirmRevoke:'Отключить доступ этого агента к Hub? Его токен перестанет работать. История и ссылки на чаты сохранятся; доступ можно выдать снова через повторное подключение.',
    setupTitle:'Как подключить агента через MCP', setupClient:'Передайте приглашение агенту в выбранном приложении. Он сообщит своё приложение и доступные сведения о модели; проект заранее выбирать не нужно.', setupMcp:'Агент получает адрес Hub и закрытый токен доступа, затем настраивает MCP в приложении. Если приложение не поддерживает самостоятельную настройку, агент объясняет ручные действия.', setupRules:'Перед записью постоянных правил агент показывает полный текст, файл назначения и область: проект или всё приложение. Запись выполняется только после вашего явного согласия; ключи в правила не включаются.', setupTest:'Проверьте доступ к инструментам и работу в новом чате. Сообщать Hub о нативных чатах можно по желанию: это сохраняет ссылки, но не передаёт право управления приложением.', nativeChatsOptional:'Сведения о нативных чатах необязательны. Старые ссылки остаются в истории после отключения агента.', provider:'Поставщик модели: {provider}',
    capabilities:'Возможности клиента', capabilitiesHelp:'Профиль сообщает сам клиент. Проверка подтверждает только функции, для которых описан доступный интерфейс; недавний запрос к Hub не подтверждает остальные возможности.', noProfile:'Клиент ещё не сообщил профиль возможностей.', test:'Проверить возможности', tests:'Проверка возможностей', testsEmpty:'Проверка ещё не выполнялась.', testProgress:'Завершено {done} из {total}', testStarted:'Начало: {date}', testFinished:'Завершение: {date}', testDeadline:'Ожидание ответа до {date}', testOverdue:'Срок ожидания истёк; итоговый результат пока не получен.',
    stateDeclared:'Сообщено клиентом', stateVerified:'Проверено', stateUnavailable:'Недоступно', stateUnknown:'Неизвестно', stateFailed:'Ошибка проверки', stateRunning:'Проверяется…', stateTimeout:'Время ожидания истекло', statePending:'Ожидает проверки', stateCancelled:'Проверка отменена', configurationRequired:'Требуется настройка управления клиентом', openChat:'Открытие нативного чата', createChat:'Создание нативного чата', sendMessage:'Отправка в нативный чат', mcpTools:'Инструменты Hub через MCP', persistentRules:'Постоянные правила', nativeChatReporting:'Ссылки на нативные чаты',
    controlTitle:'Управление клиентом', controlHelp:'Настройте доступ, только если приложение предоставляет поддерживаемый интерфейс управления. Адрес, сообщённый агентом, — предварительное значение; он сохраняется только по вашей кнопке.', controlProtocol:'Протокол управления', controlEndpoint:'Адрес интерфейса клиента', controlKey:'Ключ управления клиентом', controlKeyHelp:'Получите ключ в самом приложении. Это отдельный доступ: токен Hub и API-ключ поставщика модели здесь не подходят. Сохранённый ключ не показывается. Пустое поле сохраняет текущий ключ при том же адресе и протоколе; при смене адреса укажите новый ключ.', controlSave:'Сохранить доступ к клиенту', controlSaved:'Доступ к клиенту сохранён', controlMcp:'MCP через HTTP', controlHttp:'HTTP JSON', controlConfigured:'Ключ управления сохранён', controlMissing:'Ключ управления не настроен', rulesReported:'Клиент сообщил сохранение правил', rulesManual:'Клиент сообщил ручную настройку правил', rulesDestination:'Файл назначения: {destination}', rulesProjectScope:'Область правил: проект', rulesApplicationScope:'Область правил: приложение',
    stateWaitingReply:'Ожидает ответа клиента', requestTimeout:'Ответ сервера не получен вовремя. Результат изменения может быть неизвестен.',
    stateDocumented:'Интерфейс описан', testImpact:'Проверка может создать отдельный тестовый чат и отправить в него проверочное сообщение.', openChatNotVerified:'Наличие ссылки не подтверждает, что окно приложения открылось. Открытие нативного чата остаётся непроверенным.', testDetailUnknown:'Пояснение к результату проверки недоступно.', controlNewKeyRequired:'Для нового адреса управления укажите новый ключ клиента.', profileTitle:'Профиль, сообщённый клиентом', profileHost:'Среда клиента: {host}', profileVersion:'Версия клиента: {version}', nativeChatTitle:'Нативный чат', mcp:'Доступ к инструментам Hub', callback:'Ответ из тестового чата', testResultTitle:'Проверка возможностей',
    resultUntested:'Эта возможность ещё не проверялась.', resultHubRequest:'Hub получил запрос с действующим токеном доступа.', resultSourceLink:'Ссылка на чат сообщена; открытие приложения не проверялось.', resultTimeout:'Ответ из тестового чата не получен вовремя. Возможность остаётся неподтверждённой.', resultTesting:'Проверяется выбранный интерфейс управления клиентом.', resultNoProfile:'Клиент ещё не сообщил поддерживаемый интерфейс управления.', resultConfigure:'Сохраните настройки управления клиентом перед проверкой. Если приложение требует ключ, используйте его собственный ключ.', resultEndpointMismatch:'Сохранённые настройки управления не совпадают с профилем клиента. Обновите профиль или настройки.', resultCreateUnavailable:'Настроенный интерфейс не предоставляет поддерживаемое действие создания чата.', resultAwaiting:'Клиент вернул идентификатор тестового чата; ожидается ответ на проверочный запрос.', resultCreated:'Интерфейс клиента вернул идентификатор нового чата.', resultOpeningUnknown:'Интерфейс вернул ссылку; открытие окна приложения не подтверждено.', resultNoSource:'Интерфейс не вернул пригодную ссылку на чат.', resultMessageAccepted:'Интерфейс клиента принял сообщение для тестового чата.', resultReply:'Получен ответ, соответствующий проверочному запросу из тестового чата.', resultProbeFailed:'Проверка не завершилась. Проверьте протокол, отдельный ключ клиента и заявленные действия.', resultCorrelated:'Полученный ответ соответствует проверочному запросу и тестовому чату.'
  });
  Object.assign(english, {
    revoke:'Disconnect', revoked:'Connection disconnected', reconnect:'Reconnect', reconnectInvitation:'Reconnection invitation', reconnectHelp:'This link restores the same connection. History and earlier chat links are preserved. Give it to the agent in the same application.',
    confirmRevoke:'Disconnect this agent from Hub? Its token will stop working. History and chat links are preserved; Reconnect can grant access again.',
    setupTitle:'Connect an agent through MCP', setupClient:'Give the invitation to an agent in your chosen application. It reports its application and available model details; no project selection is needed beforehand.', setupMcp:'The agent receives the Hub address and private access token, then configures MCP in the application. If the application cannot configure itself, the agent explains the manual steps.', setupRules:'Before writing persistent rules, the agent shows the full text, destination file and scope: a project or the whole application. It writes only after your explicit consent; credentials are excluded from the rules.', setupTest:'Check tool access and try a new chat. Native chat reporting to Hub is optional: it preserves links without granting application control.', nativeChatsOptional:'Native chat details are optional. Earlier links remain in history after disconnecting the agent.', provider:'Model provider: {provider}',
    capabilities:'Client capabilities', capabilitiesHelp:'The client reports its own profile. Testing confirms only functions with a documented, available interface; a recent Hub request does not confirm the other capabilities.', noProfile:'The client has not reported its capability profile.', test:'Test capabilities', tests:'Capability tests', testsEmpty:'No capability tests have run yet.', testProgress:'Completed {done} of {total}', testStarted:'Started: {date}', testFinished:'Finished: {date}', testDeadline:'Waiting for a response until {date}', testOverdue:'The deadline passed; a final result has not been received yet.',
    stateDeclared:'Reported by the client', stateVerified:'Verified', stateUnavailable:'Unavailable', stateUnknown:'Unknown', stateFailed:'Test failed', stateRunning:'Testing…', stateTimeout:'Timed out', statePending:'Waiting for a test', stateCancelled:'Test cancelled', configurationRequired:'Client-control configuration required', openChat:'Open a native chat', createChat:'Create a native chat', sendMessage:'Send to a native chat', mcpTools:'Hub tools through MCP', persistentRules:'Persistent rules', nativeChatReporting:'Native chat links',
    controlTitle:'Client control', controlHelp:'Configure access only when the application provides a supported control interface. An address reported by the agent is a preview; it is saved only when you click the button.', controlProtocol:'Control protocol', controlEndpoint:'Client interface address', controlKey:'Client-control key', controlKeyHelp:'Obtain this key from the application itself. This is separate access: the Hub token and model-provider API key cannot be used here. A saved key is never shown. Leave blank to keep the current key at the same address and protocol; enter a new key when changing the address.', controlSave:'Save client access', controlSaved:'Client access saved', controlMcp:'MCP over HTTP', controlHttp:'HTTP JSON', controlConfigured:'Client-control key saved', controlMissing:'Client-control key not configured', rulesReported:'The client reported saving the rules', rulesManual:'The client reported manual rule setup', rulesDestination:'Destination file: {destination}', rulesProjectScope:'Rule scope: project', rulesApplicationScope:'Rule scope: application',
    stateWaitingReply:'Waiting for a client response', requestTimeout:'The server did not respond in time. The outcome of the change may be unknown.',
    stateDocumented:'Interface documented', testImpact:'Testing may create a separate test chat and send it a diagnostic message.', openChatNotVerified:'A link does not confirm that the application window opened. Opening the native chat remains unverified.', testDetailUnknown:'Further details about the test result are unavailable.', controlNewKeyRequired:'Enter a new client key for the new control address.', profileTitle:'Client-reported profile', profileHost:'Client environment: {host}', profileVersion:'Client version: {version}', nativeChatTitle:'Native chat', mcp:'Access to Hub tools', callback:'Reply from the test chat', testResultTitle:'Capability check',
    resultUntested:'This capability has not been tested yet.', resultHubRequest:'Hub received a request with a valid access token.', resultSourceLink:'A chat link was reported; opening the application has not been tested.', resultTimeout:'The test chat did not reply before the deadline. The capability remains unconfirmed.', resultTesting:'Testing the selected client-control interface.', resultNoProfile:'The client has not reported a supported control interface.', resultConfigure:'Save client-control settings before testing. If the application requires a key, use its own key.', resultEndpointMismatch:'Saved control settings do not match the client profile. Update the profile or settings.', resultCreateUnavailable:'The configured interface has no supported chat-creation action.', resultAwaiting:'The client returned a test chat identifier; waiting for a reply to the diagnostic request.', resultCreated:'The client interface returned a new chat identifier.', resultOpeningUnknown:'The interface returned a link; opening the application window is unconfirmed.', resultNoSource:'The interface did not return a usable chat link.', resultMessageAccepted:'The client interface accepted a message for the test chat.', resultReply:'A reply matching the diagnostic request arrived from the test chat.', resultProbeFailed:'The test did not complete. Check the protocol, separate client key and declared actions.', resultCorrelated:'The reply matches the diagnostic request and test chat.'
  });
  Object.assign(copy, { applicationNotReported:'Приложение не сообщило название', untested:'Не проверено', probeUnavailable:'Для проверки сохраните настройки интерфейса управления, предоставленного приложением. Адрес и протокол должны соответствовать его профилю.', statusTab:'Доступ к Hub', controlTab:'Управление из Hub', incomingTitle:'Доступ агента к Hub', granted:'Доступ выдан', currentExecution:'Текущее выполнение не подтверждено', currentExecutionVerified:'Клиент сообщил о текущем выполнении', lastAuthenticated:'Последний запрос с действующим доступом', scopeProjects:'Доступ к {count} проектам', scopeOneProject:'Доступ к проекту: {project}', ruleReceipt:'Статус установки правил', ruleCurrent:'Сообщено: правила соответствуют текущей версии', ruleOutdated:'Сообщено: правила требуют обновления', ruleCurrentUnknown:'Актуальность правил не сообщена', openGlobalRules:'Открыть настройки правил', mcpSetupTitle:'Подключение инструментов Hub', mcpSetupHelp:'Это подключение даёт приложению доступ к инструментам Hub через MCP. Оно не настраивает управление чатами в приложении.', apiRequestsTitle:'Запросы Hub к модели', apiRequestsHelp:'Настройки модели и ключи API находятся отдельно. Доступ MCP не задаёт их.', outgoingTitle:'Управление приложением из Hub', outgoingHelp:'Для открытия чатов Hub нужен отдельный интерфейс управления приложения. Профиль приложения только объявляет возможности; сохранённый адрес ещё не подтверждает работу.', endpointDeclared:'Адрес, сообщённый приложением', endpointConfigured:'Адрес сохранён в Hub', endpointNotConfigured:'Адрес управления не настроен', endpointUnverified:'Сохранённый адрес ещё не проверен', endpointVerified:'Проверка управления подтверждена', noDeclaredControl:'Приложение не сообщило интерфейс управления', verifyControl:'Проверяйте управление только после настройки адреса и отдельного ключа.', diagnosticsIdentity:'Идентификация', diagnosticsActivity:'Активность', declaredCapabilities:'Возможности, заявленные приложением', verifiedTests:'Результаты проверок', rawProfile:'Исходный профиль приложения', appNotReported:'Приложение не сообщило', stateUntested:'Не проверено', stateUnknown:'Не сообщено', setupRules:'Статус записи правил показывается кратко. Полный текст правил находится в настройках приложения.' });
  Object.assign(english, { applicationNotReported:'Application did not report a name', untested:'Not tested', probeUnavailable:'Testing requires saved control settings matching the address and protocol reported by the application.', statusTab:'Hub access', controlTab:'Control from Hub', incomingTitle:'Agent access to Hub', granted:'Access granted', currentExecution:'Current execution is not confirmed', currentExecutionVerified:'The client reported a current execution', lastAuthenticated:'Last request with valid access', scopeProjects:'Access to {count} projects', scopeOneProject:'Access to project: {project}', ruleReceipt:'Rule installation status', ruleCurrent:'Reported: rules match the current version', ruleOutdated:'Reported: rules need an update', ruleCurrentUnknown:'Rule currentness was not reported', openGlobalRules:'Open rule settings', mcpSetupTitle:'Connect Hub tools', mcpSetupHelp:'This connection gives the application access to Hub tools through MCP. It does not configure chat control in the application.', apiRequestsTitle:'Hub model requests', apiRequestsHelp:'Model settings and API keys are managed separately. MCP access does not configure them.', outgoingTitle:'Control the application from Hub', outgoingHelp:'Hub needs a separate application control interface to open chats. The application profile only declares capabilities; a saved address does not confirm that control works.', endpointDeclared:'Address reported by the application', endpointConfigured:'Address saved in Hub', endpointNotConfigured:'Control address is not configured', endpointUnverified:'The saved address has not been verified', endpointVerified:'Control test confirmed', noDeclaredControl:'The application did not report a control interface', verifyControl:'Test control only after configuring its address and separate key.', diagnosticsIdentity:'Identity', diagnosticsActivity:'Activity', declaredCapabilities:'Capabilities reported by the application', verifiedTests:'Test results', rawProfile:'Raw application profile', appNotReported:'Not reported by the application', stateUntested:'Not tested', stateUnknown:'Not reported', setupRules:'Rule write status is shown briefly. The full rules are available in application settings.' });
  Object.assign(copy, {
    applications:'Приложения', applicationsIntro:'Клиенты, в которых ваши агенты работают с Hub.', connectApplication:'Подключить приложение',
    application:'Приложение', access:'Доступ к Hub', projectsColumn:'Проекты', action:'Действие', open:'Открыть', back:'Все приложения',
    statusTab:'Доступ к Hub', controlTab:'Управление из Hub', projectsTab:'Проекты', detailsTab:'Диагностика', missingConnection:'Подключение не найдено. Обновите каталог или вернитесь к списку приложений.',
    accessKinds:'Виды доступа', tokenHelp:'Токен Hub разрешает агенту обращаться к инструментам Hub. Он хранится в закрытых настройках приложения и здесь не показывается.',
    apiHelp:'API-ключ сервиса моделей нужен для прямых запросов из Hub. Он настраивается в подразделе «Запросы к моделям».',
    controlAccessHelp:'Управление чатами требует отдельного поддерживаемого интерфейса приложения. Приглашение MCP само по себе этот доступ не создаёт.',
    toolsConfirmed:'Доступ к инструментам подтверждён', toolsGranted:'Доступ выдан, запросы ещё не подтверждены', toolsHelp:'Агент может работать с данными Hub в разрешённых проектах. Недавний запрос не означает, что агент сейчас выполняет задачу.',
    controlNotSet:'Запуск чатов не настроен', controlNotSetHelp:'У Hub нет настроенного интерфейса управления этим приложением.', controlSet:'Управление клиентом настроено', controlVerified:'Ответ из тестового чата подтверждён', controlSetHelp:'Сохранённый адрес и результат проверки показаны в диагностике.',
    inspect:'Посмотреть', instructionsTitle:'Правила приложения', instructionsUnknown:'Статус записи правил не сообщён', instructionsHelp:'Краткий статус доступен в настройках правил приложения.',
    projectsTitle:'Проекты в этом приложении', projectsCount:'Учёт включён для {count} проектов.', openProjects:'Открыть проекты', stateHelp:'Статус относится к доступу и настройке; текущая работа агента определяется отдельно.',
    lastRequestColumn:'Последний запрос', previousPage:'Назад', nextPage:'Далее', profileJson:'Исходные технические данные', manageAccess:'Доступ приложения', noModel:'Модель выбирается в приложении',
    projectsUnavailable:'Сведения о проектах пока недоступны.', toModels:'Настроить запросы к моделям', sharedRules:'Правила работы', closeInvitation:'Скрыть приглашение', modelLabel:'Модель'
  });
  Object.assign(english, {
    applications:'Applications',applicationsIntro:'Clients where your agents work with Hub.',connectApplication:'Connect an application',application:'Application',access:'Hub access',projectsColumn:'Projects',action:'Action',open:'Open',back:'All applications',
    statusTab:'Hub access',controlTab:'Control from Hub',projectsTab:'Projects',detailsTab:'Diagnostics',missingConnection:'Connection not found. Refresh the catalog or return to the application list.',
    accessKinds:'Types of access',tokenHelp:'The Hub token allows the agent to use Hub tools. It is kept in private application settings and is never shown here.',apiHelp:'A model-service API key is used for direct requests from Hub. Configure it in Model requests.',controlAccessHelp:'Chat control requires a separate supported application interface. An MCP invitation does not create this access.',
    toolsConfirmed:'Tool access confirmed',toolsGranted:'Access granted; requests not yet confirmed',toolsHelp:'The agent can work with Hub data in permitted projects. A recent request does not mean that the agent is currently executing a task.',
    controlNotSet:'Chat launching is not configured',controlNotSetHelp:'Hub has no configured control interface for this application.',controlSet:'Client control configured',controlVerified:'Reply from the test chat confirmed',controlSetHelp:'The saved address and test results are available in Diagnostics.',inspect:'View',
    instructionsTitle:'Application rules',instructionsUnknown:'Rule write status was not reported',instructionsHelp:'A compact status is available in application rule settings.',projectsTitle:'Projects in this application',projectsCount:'Tracking enabled for {count} projects.',openProjects:'Open projects',stateHelp:'These statuses describe access and setup; current agent work is tracked separately.',
    lastRequestColumn:'Last request',previousPage:'Previous',nextPage:'Next',profileJson:'Technical client profile',manageAccess:'Application access',noModel:'The model is selected in the application',projectsUnavailable:'Project details are not yet available.',toModels:'Configure model requests',sharedRules:'Work rules',closeInvitation:'Hide invitation',modelLabel:'Model'
  });
  Object.assign(copy, {
    chatsTab:'Чаты приложения', bindingsTab:'Привязки проектов', boundProjects:'Привязано проектов: {count}', bindingsColumn:'Привязки',
    installationScope:'Эта установка Hub', accessScopeGlobal:'Область доступа: зарегистрированные проекты этой установки Hub.',
    incomingDirection:'Агент → Hub', outgoingDirection:'Hub → приложение', replyDirection:'Приложение → Hub', linkDirection:'Браузер → приложение',
    incomingTools:'Инструменты Hub', incomingExplanation:'Агент вызывает инструменты Hub через MCP. Успешный запрос подтверждает доступ в момент обращения.',
    incomingObserved:'Получен запрос с действующим доступом', incomingNotObserved:'Авторизованные запросы пока не наблюдались', incomingEvidence:'Этот факт не подтверждает загрузку всех инструментов, чтение правил новым чатом или текущую работу агента.',
    hubEndpoint:'Адрес MCP этой установки', modelRequestsSeparate:'Hub обращается к сервису модели напрямую и может выполнять запросы при закрытом Codex. Авторизация модели настраивается отдельно для всей установки Hub.',
    chatsIntro:'Открытие ссылки, создание чата и обмен сообщениями — отдельные функции. Здесь показаны доступные маршруты и результаты их проверки.', projectBindingChoice:'Проект для проверки', projectBindingRequired:'Выберите проект', adapterNotice:'Экспериментальный адаптер использует интерфейс текущего приложения Codex и только папки, разрешённые при его подключении. После закрытия или обновления приложения может потребоваться подключение снова.', visibilityConfirmed:'Присутствие чата в приложении и проекте подтверждено адаптером.',
    controlConnection:'Подключение управления чатами', controlSetup:'Настройки интерфейса управления', controlSaveOnly:'Сохранить настройки', savedWithoutProbe:'Настройки сохранены. Проверка запускается отдельно.',
    saveOnlyHelp:'Сохранение адреса и ключа не обращается к приложению и не создаёт чат.',
    controlSetupHelp:'Используйте адрес и протокол документированного интерфейса приложения или его адаптера. Ключ этого интерфейса хранится отдельно от доступа агента к Hub и авторизации сервиса моделей.',
    missingInterfaceHelp:'Приложение должно предоставить доступный Hub интерфейс управления. Одного названия инструмента, доступного агенту в чате, недостаточно.',
    protocolsHelp:'Поддерживаются MCP через HTTP и HTTP JSON. Выбор протокола не создаёт интерфейс в приложении.',
    featureInterfaceMissing:'Интерфейс управления не предоставлен', featureNotConfigured:'Нужно сохранить настройки', featureMismatch:'Настройки не совпадают с профилем', featureActionMissing:'Операция не описана для этого интерфейса', featureReady:'Готово к проверке', featureStale:'Настройка изменилась', featureNotReported:'Возможность не заявлена', featureLink:'Ссылка доступна', featureTemplate:'Заявлен шаблон ссылки', featureRevoked:'Доступ отозван',
    needCreate:'Для создания чата нужен интерфейс управления приложением.', needSend:'Для отправки из Hub нужны интерфейс управления и идентификатор чата.', needReply:'Подтверждение обмена проверяется после создания чата и отправки тестового сообщения.', featureCreate:'Создание чата', featureSend:'Отправка сообщения', featureReply:'Подтверждение обмена', featureOpen:'Открытие существующего чата',
    declaredOrigin:'Поддержка: заявлена приложением', testedOrigin:'Источник результата: проверка настроенного интерфейса', derivedOrigin:'Проверяется по ответу на тестовое сообщение',
    proofCreate:'Подтверждено: API вернул идентификатор нового чата.', proofSend:'Подтверждено: API принял сообщение для тестового чата.', proofReply:'Получен обратный запрос с совпавшими кодом проверки и идентификатором чата.', proofOpen:'Наличие ссылки подтверждено. Открытие окна приложения не проверено.',
    helpNotReported:'Приложение не описало эту функцию. Её поддержку нельзя определить по доступу к Hub.', helpActionMissing:'Для выбранного протокола нужно описание операции от приложения или адаптера.', helpReady:'Запустите отдельную проверку обмена, чтобы получить результат.', helpStale:'Предыдущий результат относится к другой версии настроек. Нужна новая проверка.', helpTemplate:'Шаблон адреса заявлен приложением. Для открытия нужен действительный чат.',
    exchangeTest:'Проверка обмена', exchangeAction:'Создать тестовый чат и проверить обмен', exchangeImpact:'Проверка создаст отдельный чат и отправит диагностическое сообщение. Приложение может выполнить запрос к модели. Результат проверки общий для приложения.', testChatProject:'Где создать тестовый чат',
    exchangeUnavailable:'Проверка обмена станет доступна после настройки совпадающего интерфейса с операцией создания чата.', dirtyProbe:'Сначала сохраните изменения настроек. Проверка использует сохранённый адрес.',
    attemptsTitle:'Журнал проверок управления чатами', attemptsSummary:'Успешно: {passed} · Нужно настроить: {configuration} · Ошибок: {failed} · Без ответа: {timeout} · Отменено: {cancelled} · В работе: {running}',
    noAttempts:'Проверки управления чатами ещё не запускались.', attemptTitle:'Попытка проверки обмена', historicalResult:'Результат для прежней настройки',
    diagnosticProfile:'Технический профиль приложения', diagnosticProfileHelp:'Сведения сообщает приложение. Они описывают его заявления и не подтверждают доступность управления из Hub.',
    linkHelp:'Ссылки на существующие чаты доступны в списке чатов и в результатах проверок.', openSetup:'Как настроить подключение',
    setupIncoming:'Для нового приложения создайте приглашение в каталоге. Для существующего подключения проверьте нативные настройки MCP в приложении, адрес этой установки и сохранённый токен. После подключения агент должен получить инструменты Hub и выполнить читающий запрос.',
    settingsNotice:'Подключения приложений и запросы к моделям действуют для всей установки Hub. Связи с отдельными проектами находятся в привязках.'
  });
  Object.assign(english, {
    chatsTab:'Application chats', bindingsTab:'Project bindings', boundProjects:'Bound projects: {count}', bindingsColumn:'Bindings',
    installationScope:'This Hub installation', accessScopeGlobal:'Access scope: registered projects in this Hub installation.',
    incomingDirection:'Agent → Hub', outgoingDirection:'Hub → application', replyDirection:'Application → Hub', linkDirection:'Browser → application',
    incomingTools:'Hub tools', incomingExplanation:'The agent calls Hub tools through MCP. A successful request confirms access at that moment.',
    incomingObserved:'A request with valid access was received', incomingNotObserved:'No authenticated requests observed yet', incomingEvidence:'This does not confirm discovery of every tool, rule loading in a new chat, or current agent execution.',
    hubEndpoint:'This installation’s MCP address', modelRequestsSeparate:'Hub contacts the model service directly and can make requests while Codex is closed. Model authorization is configured separately for this Hub installation.',
    chatsIntro:'Opening a link, creating a chat and exchanging messages are separate features. This page shows available routes and their test results.', projectBindingChoice:'Project for this test', projectBindingRequired:'Select a project', adapterNotice:'The experimental adapter uses the current Codex application interface and only folders allowed when it was connected. Reconnect may be required after the application closes or updates.', visibilityConfirmed:'Chat presence in the application and project was confirmed by the adapter.',
    controlConnection:'Chat control connection', controlSetup:'Control interface settings', controlSaveOnly:'Save settings', savedWithoutProbe:'Settings saved. Run a test separately.',
    saveOnlyHelp:'Saving the address and key does not contact the application or create a chat.',
    controlSetupHelp:'Use the address and protocol of a documented application interface or adapter. Its credential is separate from agent access to Hub and model-service authorization.',
    missingInterfaceHelp:'The application must provide a control interface reachable by Hub. A tool name available to an agent inside a chat is not enough.',
    protocolsHelp:'MCP over HTTP and HTTP JSON are supported. Selecting a protocol does not create an application interface.',
    featureInterfaceMissing:'Control interface not provided', featureNotConfigured:'Settings need to be saved', featureMismatch:'Settings differ from the profile', featureActionMissing:'Operation not described for this interface', featureReady:'Ready to test', featureStale:'Settings changed', featureNotReported:'Feature not reported', featureLink:'Source link available', featureTemplate:'Link template reported', featureRevoked:'Access revoked',
    needCreate:'Creating a chat requires an application control interface.', needSend:'Sending from Hub requires a control interface and a chat ID.', needReply:'Exchange confirmation is checked after creating a chat and sending a test message.', featureCreate:'Create a chat', featureSend:'Send a message', featureReply:'Confirm the exchange', featureOpen:'Open an existing chat',
    declaredOrigin:'Support: declared by the application', testedOrigin:'Result source: configured-interface test', derivedOrigin:'Checked through the test-message reply',
    proofCreate:'Confirmed: the API returned a new chat ID.', proofSend:'Confirmed: the API accepted a message for the test chat.', proofReply:'A callback matched the test code and expected chat ID.', proofOpen:'A source link is available. Opening the application window has not been tested.',
    helpNotReported:'The application has not described this feature. Hub access does not establish its support.', helpActionMissing:'The application or adapter must describe an operation for the selected protocol.', helpReady:'Run the separate exchange test to obtain a result.', helpStale:'The previous result belongs to different settings. Run a new test.', helpTemplate:'The application reported a link template. Opening it requires an actual chat.',
    exchangeTest:'Exchange test', exchangeAction:'Create a test chat and check the exchange', exchangeImpact:'The test creates a separate chat and sends a diagnostic message. The application may make a model request. The result applies to this application.', testChatProject:'Where to create the test chat',
    exchangeUnavailable:'Exchange testing requires a matching configured interface with a chat-creation operation.', dirtyProbe:'Save your changes first. Testing uses the saved address.',
    attemptsTitle:'Chat control test history', attemptsSummary:'Passed: {passed} · Setup required: {configuration} · Failed: {failed} · No reply: {timeout} · Cancelled: {cancelled} · Running: {running}',
    noAttempts:'No chat control tests have been started.', attemptTitle:'Exchange test attempt', historicalResult:'Result for previous settings', visibilityConfirmed:'Chat presence in the application and project was confirmed by the adapter.',
    diagnosticProfile:'Technical application profile', diagnosticProfileHelp:'The application reports these details. They describe its claims and do not establish control from Hub.',
    linkHelp:'Existing chat links are available in the chat list and test results.', openSetup:'How to configure access',
    setupIncoming:'For a new application, create an invitation in the catalog. For an existing connection, check its native MCP settings, this installation’s address and the stored token. The agent must then discover Hub tools and make a read request.',
    settingsNotice:'Application connections and model requests apply to the entire Hub installation. Project-specific links are managed under bindings.'
  });
  Object.assign(copy, {
    universalMcpHelp:'Подключение MCP относится к приложению и не зависит от выбранной модели. Приглашение регистрирует отдельное подключение и выдаёт его токен доступа. Для каждого нового подключения создайте новое приглашение.',
    codexControlSetup:'Адаптер Codex не подключён', codexControlHelp:'В чате Codex попросите подключить локальный адаптер к этой установке Hub и укажите разрешённые папки проектов. Настройка запустит адаптер, создаст ключ и сохранит адрес и протокол в Hub. Затем отдельно запустите проверку обмена.',
    codexKeyHelp:'Ключ создаётся адаптером Codex и сохраняется в Hub при подключении. Токен доступа к Hub и API-ключ модели здесь не подходят. Сохранённый ключ не показывается. Пустое поле сохраняет ключ при прежнем адресе и протоколе; при их смене нужен новый ключ адаптера.',
    codexControlSource:'Адрес, протокол и ключ записывает настройка локального адаптера Codex. Обычно вводить их вручную не требуется.',
    codexControlLifecycle:'Адаптер работает через текущий экземпляр Codex. После закрытия или обновления приложения может потребоваться повторное подключение.',
    unsupportedControlTitle:'Управление чатами не подключено', unsupportedControlHelp:'Для этого приложения в Hub пока нет готового адаптера управления чатами. Доступ агента к Hub по MCP работает независимо. Для управления чатами нужен отдельный совместимый интерфейс приложения.',
    externalControlHelp:'Используется внешний интерфейс, сообщённый приложением. Его адрес и отдельный ключ задаются ниже; работоспособность подтверждается проверкой обмена.',
    controlConfiguredReady:'Настройки сохранены · доступность проверяется отдельно',
    chatIntegrationHelp:'Управление чатами требует отдельного интерфейса приложения. В этой версии готовый локальный адаптер доступен для Codex. Другому приложению нужен собственный совместимый интерфейс или адаптер; приглашение MCP само по себе его не подключает.',
    historyHelp:'Каждая строка — отдельный запуск проверки обмена с приложением. На странице показано до 20 попыток. Сообщения из чатов в этот журнал не загружаются.',
    historyLoading:'Загрузка журнала…', historyLoadError:'Не удалось загрузить страницу журнала.', historyRetry:'Повторить загрузку',
    historyDate:'Начало', historyResult:'Результат', historyProject:'Проект тестового чата', historyDuration:'Длительность', historyDetails:'Подробнее', historyAttemptId:'Идентификатор попытки', historySeconds:'{value} с',
    historyPages:'Страницы журнала проверок', historyPrevious:'Назад', historyNext:'Далее', historyPage:'Страница {page} из {pages}', historyRange:'Показано {start}–{end} из {total}'
  });
  Object.assign(english, {
    universalMcpHelp:'The MCP connection belongs to the application and does not depend on its selected model. An invitation registers a separate connection and issues its access token. Create a new invitation for each new connection.',
    codexControlSetup:'Codex adapter is not connected', codexControlHelp:'In a Codex chat, ask to connect the local adapter to this Hub installation and specify the allowed project folders. Setup starts the adapter, generates its key and saves its address and protocol in Hub. Then run the exchange test separately.',
    codexKeyHelp:'The Codex adapter generates this key and saves it in Hub during setup. The Hub access token and model API key do not work here. The saved key is hidden. An empty field keeps the key for the same address and protocol; changing either requires a new adapter key.',
    codexControlSource:'Local Codex adapter setup saves the address, protocol and key. Manual entry is usually unnecessary.',
    codexControlLifecycle:'The adapter uses the current Codex instance. Reconnection may be required after the application closes or updates.',
    unsupportedControlTitle:'Chat control is not connected', unsupportedControlHelp:'Hub does not yet include a chat-control adapter for this application. Agent access to Hub through MCP works independently. Chat control requires a separate compatible application interface.',
    externalControlHelp:'This uses an external interface reported by the application. Set its address and separate key below; an exchange test confirms whether it works.',
    controlConfiguredReady:'Settings saved · availability requires a separate check',
    chatIntegrationHelp:'Chat control requires a separate application interface. This version includes a local adapter for Codex. Another application needs its own compatible interface or adapter; an MCP invitation alone does not connect it.',
    historyHelp:'Each row is one exchange test run. A page shows up to 20 attempts. Chat messages are not loaded into this history.',
    historyLoading:'Loading test history…', historyLoadError:'Could not load this history page.', historyRetry:'Retry loading',
    historyDate:'Started', historyResult:'Result', historyProject:'Test chat project', historyDuration:'Duration', historyDetails:'Details', historyAttemptId:'Attempt ID', historySeconds:'{value} s',
    historyPages:'Test history pages', historyPrevious:'Previous', historyNext:'Next', historyPage:'Page {page} of {pages}', historyRange:'Showing {start}–{end} of {total}'
  });
  const testErrorCopy = {
    hub_bindings_unavailable:['Не удалось получить привязки проектов. Проверьте доступность Project Hub и повторите проверку.','Project bindings could not be loaded. Check Project Hub availability and run the test again.'],
    hub_project_binding_missing:['Для проверки не выбрана привязка проекта. Выберите проект и повторите попытку.','No project binding was selected for this test. Choose a project and run it again.'],
    hub_project_binding_ambiguous:['Для проверки найдено несколько подходящих привязок проекта. Выберите нужную привязку.','Several project bindings matched this test. Choose the intended binding.'],
    hub_project_binding_changed:['Привязка проекта изменилась во время проверки. Обновите страницу и повторите попытку.','The project binding changed during the test. Refresh and run it again.'],
    native_project_missing:['В приложении не найден выбранный проект. Проверьте проект и повторите попытку.','The selected project was not found in the application. Check the project and run it again.'],
    native_project_ambiguous:['В приложении найдено несколько проектов с таким именем. Уточните проект и повторите попытку.','Several projects with that name were found in the application. Choose the intended project and run it again.'],
    native_catalog_unavailable:['Приложение временно не сообщило сведения о проектах; это не означает, что проект удалён. Повторите попытку или обновите Codex.','The application did not provide project metadata; this does not mean the project is missing. Retry or update Codex.'],
    native_chat_not_visible_in_project:['Тестовый чат не виден в выбранном проекте. Проверьте область проекта и повторите попытку.','The test chat is not visible in the selected project. Check the project scope and run it again.'],
    chat_not_owned:['Приложение не подтвердило владение тестовым чатом. Проверьте подключение и повторите попытку.','The application did not confirm ownership of the test chat. Check the connection and run it again.'],
    codex_host_unavailable:['Локальный адаптер Codex недоступен. Подключите его и повторите проверку.','The local Codex adapter is unavailable. Connect it and run the test again.'],
    codex_host_rejected:['Локальный адаптер Codex отклонил проверку. Проверьте его настройки и повторите попытку.','The local Codex adapter rejected the test. Check its settings and run it again.'],
    codex_outcome_unknown:['Результат проверки Codex неизвестен. Повторите тот же запрос вручную для подтверждения.','The Codex test outcome is unknown. Manually repeat the same request to confirm it.'],
    codex_protocol_changed:['Протокол адаптера Codex изменился. Обновите подключение и повторите проверку.','The Codex adapter protocol changed. Reconnect it and run the test again.'],
    prior_outcome_requires_reconciliation:['Предыдущий результат проверки не подтверждён. Повторите тот же запрос вручную.','The previous test outcome was not confirmed. Manually repeat the same request.'],
    control_auth_failed:['Приложение отклонило ключ управления. Проверьте ключ и повторите попытку.','The application rejected the control key. Check the key and run it again.'],
    control_endpoint_unavailable:['Интерфейс управления приложением недоступен. Проверьте адрес и повторите попытку.','The application control interface is unavailable. Check the address and run it again.'],
    control_timeout:['Приложение не ответило вовремя. Проверьте его работу и повторите попытку.','The application did not respond in time. Check it and run the test again.'],
    control_http_error:['Интерфейс управления приложением вернул ошибку. Проверьте его настройки и повторите попытку.','The application control interface returned an error. Check its settings and run it again.'],
    control_invalid_response:['Интерфейс управления приложением вернул неожиданный ответ. Проверьте совместимость и повторите попытку.','The application control interface returned an unexpected response. Check compatibility and run it again.']
  };
  const testErrorPhases = {connect:['подключении','connecting'],discover:['поиске проекта','discovering the project'],create:['создании чата','creating the chat'],send:['отправке сообщения','sending the message'],callback:['получении ответа','receiving the reply']};
  const testErrorCodes = new Set(Object.keys(testErrorCopy));
  function t(key, params = {}) {
    const fullKey = `connections.${key}`;
    try { const translated = global.HubI18n?.t?.(fullKey, params); if (translated && translated !== fullKey) return translated; } catch (_) { /* Local copy remains available. */ }
    const locale = global.HubI18n?.locale || global.document?.documentElement?.dataset?.hubLocale;
    const fallback = (locale === 'en' ? english : copy)[key] || key;
    return String(fallback).replace(/\{(\w+)\}/g, (_, name) => params[name] == null ? `{${name}}` : String(params[name]));
  }
  function esc(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
  function requestId() { return global.crypto?.randomUUID?.()?.replace(/-/g,'') || `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`.padEnd(32,'0').slice(0,32); }
  function connected(root = view.root) { return root && root.isConnected !== false; }
  async function api(url, options = {}) {
    const controller = typeof global.AbortController === 'function' ? new global.AbortController() : null;
    const timer = controller ? global.setTimeout(() => controller.abort(), 20000) : null;
    try {
      let response;
      try { response = await global.fetch(url, {cache:'no-store', ...options, ...(controller?{signal:controller.signal}:{}), headers:{...(options.body ? {'Content-Type':'application/json'} : {}), ...(options.headers || {})}}); }
      catch (cause) { const error = Error(controller?.signal.aborted ? t('requestTimeout') : (global.HubI18n?.error?.(cause) || cause?.message || t('unknown'))); error.uncertain = true; throw error; }
      let body; try { body = await response.json(); } catch (_) { /* A missing JSON body cannot confirm a change. */ }
      if (!response.ok) { const code=body?.code||body?.error;const error = Error(code === 'configuration_required' ? t('configurationRequired') : code === 'control_key_required' ? t('controlNewKeyRequired') : (global.HubI18n?.error?.(body?.message) || t('errorMutation'))); error.code = code; error.uncertain = response.status >= 500; throw error; }
      if (!body || typeof body !== 'object' || Array.isArray(body)) { const error = Error(t('invalidAck')); error.uncertain = true; throw error; }
      return body;
    } finally { if (timer != null) global.clearTimeout?.(timer); }
  }
  async function loadCatalog() {
    if (view.loading) return;
    view.loading = true; view.error = '';
    try { view.catalog = await api('/api/v1/connections'); }
    catch (error) { view.error = error.message || t('errorLoad'); }
    finally { view.loading = false; render(view.root, true); }
    if(view.selectedId&&view.tab==='diagnostics')await loadHistory(view.selectedId);
  }
  function historyState(id) {
    if(!view.histories.has(id))view.histories.set(id,{offset:0,limit:20,data:null,loading:false,error:''});
    return view.histories.get(id);
  }
  async function loadHistory(id, offset=null) {
    const state=historyState(id);
    if(state.loading)return;
    state.loading=true;state.error='';render(view.root,true);
    const requested=offset==null?state.offset:offset;state.requestedOffset=requested;
    try {
      const data=await api(`/api/v1/connection-tests?id=${encodeURIComponent(id)}&offset=${requested}&limit=${state.limit}`);
      if(data.connection!==id||!Array.isArray(data.tests)||data.tests.length>state.limit||!Number.isInteger(data.total)||data.total<0||!Number.isInteger(data.offset)||data.offset<0||data.limit!==state.limit)throw Error(t('invalidAck'));
      state.data=data;state.offset=data.offset;
    } catch(error) { state.error=error.message||t('historyLoadError'); }
    finally { state.loading=false;render(view.root,true); }
  }
  function bindings() { return Array.isArray(view.catalog?.bindings) ? view.catalog.bindings : []; }
  function blocked() { return view.busy || !!view.pending; }
  function stamp(value) { if (value==null || value==='') return ''; const date = typeof value === 'number' ? new Date(value*1000) : new Date(value); return Number.isFinite(date.getTime()) ? date.toLocaleString() : ''; }
  function stateLabel(state) {
    const keys = {declared:'stateDeclared','client-reported':'stateDeclared',client_reported:'stateDeclared',documented:'stateDocumented',verified:'stateVerified',passed:'stateVerified',unavailable:'stateUnavailable',unknown:'stateUntested',failed:'stateFailed',running:'stateRunning',timeout:'stateTimeout',timed_out:'stateTimeout',pending:'statePending',queued:'statePending',cancelled:'stateCancelled',awaiting_reply:'stateWaitingReply',configuration_required:'configurationRequired'};
    return t(Object.prototype.hasOwnProperty.call(keys,state)?keys[state]:'stateUntested');
  }
  function capabilityName(id) { const key=id==='mcp'?'mcpTools':id;return Object.prototype.hasOwnProperty.call(copy,key) ? t(key) : key; }
  function resultMessage(value) {
    if (testErrorCodes.has(value)) return testErrorDetail({code:value}).text;
    const code = {configuration_required:'configurationRequired',control_key_required:'controlNewKeyRequired',timeout:'stateTimeout',timed_out:'stateTimeout'};
    if (Object.prototype.hasOwnProperty.call(code,value)) return t(code[value]);
    const known = {'Capability has not been tested':'resultUntested','Hub received an authenticated tool request':'resultHubRequest','Source link available; opening in the native application has not been tested':'resultSourceLink','No correlated reply arrived before the deadline; capability remains unconfirmed':'resultTimeout','Testing the configured interface':'resultTesting','The client has not supplied its interface profile':'resultNoProfile','Confirm the control endpoint and its separate credential in settings before testing':'resultConfigure','The confirmed endpoint does not match the client profile':'resultEndpointMismatch','No supported chat-creation action is advertised by the configured interface':'resultCreateUnavailable','The API created a test conversation; waiting for its correlated reply':'resultAwaiting','Configured API returned a new conversation ID':'resultCreated','Source link returned; native application opening is not proven':'resultOpeningUnknown','The API returned no usable source link':'resultNoSource','Configured API accepted a message for the returned conversation ID':'resultMessageAccepted','A correlated reply arrived from the test conversation':'resultReply','The configured interface did not complete the probe; check its protocol, credential and declared actions':'resultProbeFailed','Probe nonce and returned conversation ID matched':'resultCorrelated','Connection or configuration changed during the probe':'helpStale'};
    if (Object.prototype.hasOwnProperty.call(known,value)) return t(known[value]);
    const source=String(value||''), locale=global.HubI18n?.locale||global.document?.documentElement?.dataset?.hubLocale;
    const translated=global.HubI18n?.error?.(source);
    if(translated&&translated!==source)return translated;
    if(locale!=='en'&&/[А-Яа-яЁё]/.test(source))return source;
    return t('testDetailUnknown');
  }
  function testErrorDetail(error) {
    if (!error || typeof error !== 'object' || !testErrorCodes.has(error.code)) return {text:global.HubI18n?.locale==='en'?'The exchange test could not be completed. Check the connection settings and run it again.':'Не удалось завершить проверку обмена. Проверьте настройки подключения и повторите попытку.', phase:'', status:null, unknown:false};
    const locale=global.HubI18n?.locale==='en'?1:0, phase=testErrorPhases[error.phase];
    let text=testErrorCopy[error.code][locale];
    if (phase) text += locale ? ` The failure occurred while ${phase[1]}.` : ` Сбой произошёл при ${phase[0]}.`;
    if (Number.isInteger(error.httpStatus) && error.httpStatus >= 100 && error.httpStatus <= 599) text += locale ? ` HTTP status: ${error.httpStatus}.` : ` Код HTTP: ${error.httpStatus}.`;
    return {text,phase:error.phase||'',status:error.httpStatus,unknown:error.outcomeUnknown===true};
  }
  function renderTestError(error) {
    const detail=testErrorDetail(error);
    return `<p class="connection-test-error" role="alert">${esc(detail.text)}${detail.unknown?` <span>${esc(global.HubI18n?.locale==='en'?'The chat or message may already exist. Inspect the journal and the application chat before starting another attempt.':'Чат или сообщение уже могли появиться. Проверьте журнал и чат в приложении перед новой попыткой.')}</span>`:''}</p>`;
  }
  function latestTest(row) {
    return (Array.isArray(row.tests)?row.tests:[]).filter(test=>test&&test.current!==false).sort((a,b)=>(Number(b.startedAt||0)-Number(a.startedAt||0)))[0];
  }
  function renderLatestTestOutcome(row) {
    const test=latestTest(row); if(!test) return '';
    const project=test.projectBinding?.project||test.projectBinding?.projectName;
    const context=project?`<small>${esc(t('projectBindingChoice'))}: ${esc(project)}</small>`:'';
    if(test.error) return renderTestError(test.error)+context;
    if(test.message) return `<p class="connection-test-error">${esc(resultMessage(test.message))}</p>`;
    return testTerminal(test)&&test.state!=='passed'&&test.state!=='verified' ? `<p class="connection-test-error">${esc(stateLabel(test.state))}</p>` : '';
  }
  function renderNativeChat(row) {
    const link = row.nativeChat && global.HubNativeChats?.link?.(row.nativeChat);
    return link ? `<div class="connection-native-chat"><strong>${esc(t('nativeChatTitle'))}</strong><p>${link}</p><p>${esc(t('openChatNotVerified'))}</p></div>` : '';
  }
  function testTerminal(test) { return ['passed','verified','failed','unavailable','unknown','timeout','timed_out','cancelled','configuration_required'].includes(test?.state); }
  function controlStatus(row) {
    if(row.controlStatus)return row.controlStatus;
    const configured=row.control, declared=row.profile?.control, create=row.profile?.capabilities?.createChat;
    const state=row.revoked?'revoked':!declared?'interface_missing':!configured?'not_configured':configured.endpoint!==declared.endpoint||configured.protocol!==declared.protocol?'configuration_mismatch':!(configured.protocol==='mcp-http'?create?.tool:create?.path)?'action_missing':'ready';
    return {state,canTest:state==='ready'};
  }
  function canProbeControl(row) { return controlStatus(row).canTest===true; }
  function featureStateLabel(state) {
    const keys={interface_missing:'featureInterfaceMissing',not_configured:'featureNotConfigured',configuration_mismatch:'featureMismatch',action_missing:'featureActionMissing',ready:'featureReady',stale:'featureStale',not_reported:'featureNotReported',source_available:'featureLink',link_template:'featureTemplate',revoked:'featureRevoked'};
    return keys[state]?t(keys[state]):stateLabel(state);
  }
  function feature(row,id) {
    if(row.features?.[id])return row.features[id];
    const declared=row.profile?.capabilities?.[id], evidence=row.capabilities?.[id]||{};
    const state=id==='openChat'?(row.nativeChat?.openUri?'source_available':declared?'link_template':'not_reported'):row.revoked?'revoked':!declared&&id!=='callback'?'not_reported':controlStatus(row).state==='ready'?evidence.state==='verified'?'verified':'ready':controlStatus(row).state;
    return {state,support:declared?'declared':'not_reported',verification:evidence};
  }
  function renderFeature(row,id) {
    const data=feature(row,id), state=data.state, names={openChat:'featureOpen',createChat:'featureCreate',sendMessage:'featureSend',callback:'featureReply'};
    const proof={openChat:'proofOpen',createChat:'proofCreate',sendMessage:'proofSend',callback:'proofReply'};
    const help={interface_missing:'missingInterfaceHelp',not_configured:'controlSetupHelp',configuration_mismatch:'resultEndpointMismatch',action_missing:'helpActionMissing',ready:'helpReady',stale:'helpStale',not_reported:'helpNotReported',link_template:'helpTemplate',revoked:'featureRevoked'};
    const direction=id==='openChat'?'linkDirection':id==='callback'?'replyDirection':'outgoingDirection';
    const evidence=data.verification||{};
    const origin=state==='verified'&&['createChat','sendMessage'].includes(id)?'testedOrigin':data.support==='declared'?'declaredOrigin':id==='callback'&&data.support==='derived'?'derivedOrigin':null;
    const detail=state==='interface_missing'?t({createChat:'needCreate',sendMessage:'needSend',callback:'needReply'}[id]||'missingInterfaceHelp'):state==='verified'||state==='source_available'?t(proof[id]):help[state]?t(help[state]):evidence.message?resultMessage(evidence.message):featureStateLabel(state);
    return `<section class="connection-section connection-feature" data-connection-feature="${id}"><div class="connection-section-head"><h3>${esc(t(names[id]))}</h3><span class="capability-state" data-capability-state="${esc(state)}">${esc(featureStateLabel(state))}</span></div><p class="connection-direction-label">${esc(t(direction))}</p><p>${esc(detail)}</p>${origin?`<p class="connection-evidence-origin">${esc(t(origin))}</p>`:''}${stamp(evidence.testedAt)?`<time>${esc(stamp(evidence.testedAt))}</time>`:''}${id==='openChat'?renderNativeChat(row):''}</section>`;
  }
  function testSummary(row, summary=null) {
    const tests=Array.isArray(row.tests)?row.tests:[];
    if(!tests.length&&!summary)return `<p>${esc(t('noAttempts'))}</p>`;
    const counts={passed:0,configuration:0,failed:0,timeout:0,cancelled:0,running:0};
    for(const test of tests){const state=test.state;counts[['passed','verified'].includes(state)?'passed':state==='configuration_required'?'configuration':['timeout','timed_out'].includes(state)?'timeout':state==='cancelled'?'cancelled':testTerminal(test)?'failed':'running']++;}
    return `<p class="connection-test-summary" role="status">${esc(t('attemptsSummary',summary||counts))}</p>`;
  }
  function renderTestHistory(row) {
    const state=historyState(row.id),data=state.data,tests=data?.tests||[],total=data?.total||0;
    const rows=tests.map(test=>{
      const project=test.projectBinding,known=(row.projectBindings||[]).find(binding=>binding.id===project?.bindingId);
      const projectName=known?.project_name||(view.catalog?.projects||[]).find(item=>item.id===project?.project)?.name||project?.project||'—';
      const seconds=Number.isFinite(test.startedAt)&&Number.isFinite(test.finishedAt)?Math.max(0,Math.round((test.finishedAt-test.startedAt)*10)/10):null;
      return `<tr data-connection-test-result="${esc(test.id)}"><td>${esc(stamp(test.startedAt)||'—')}</td><td><span class="capability-state" data-capability-state="${esc(test.state)}">${esc(stateLabel(test.state))}</span>${test.current===false?`<small>${esc(t('historicalResult'))}</small>`:''}</td><td>${esc(projectName)}</td><td>${seconds==null?'—':esc(t('historySeconds',{value:seconds}))}</td><td><details data-connection-details="probe:${esc(test.id)}"><summary>${esc(t('historyDetails'))}</summary><div class="connection-test-detail"><strong>${esc(t('attemptTitle'))}</strong>${test.message?`<p>${esc(resultMessage(test.message))}</p>`:''}${project?`<p>${esc(t('projectBindingChoice'))}: ${esc(projectName)}</p><code>${esc(project.scope?.root||project.scope?.nativeRef||'')}</code>`:''}${test.nativeVisibility?`<p>${esc(t('visibilityConfirmed'))}</p>`:''}${stamp(test.finishedAt)?`<p>${esc(t('testFinished',{date:stamp(test.finishedAt)}))}</p>`:''}${!testTerminal(test)&&stamp(test.deadline)?`<p>${esc(t('testDeadline',{date:stamp(test.deadline)}))}</p>`:''}<p>${esc(t('historyAttemptId'))}: <code>${esc(test.id)}</code></p>${renderNativeChat({nativeChat:test.nativeChat})}</div></details></td></tr>`;
    }).join('');
    const start=total?data.offset+1:0,end=Math.min(total,(data?.offset||0)+tests.length),page=Math.floor((data?.offset||0)/state.limit)+1,pages=Math.max(1,Math.ceil(total/state.limit));
    return `<section class="connection-section connection-test-history" aria-busy="${state.loading}"><h3>${esc(t('attemptsTitle'))}</h3><p>${esc(t('historyHelp'))}</p>${data?testSummary({tests},data.counts):''}${state.error?`<p role="alert">${esc(t('historyLoadError'))} <button type="button" data-connection-history-retry ${state.loading?'disabled':''}>${esc(t('historyRetry'))}</button></p>`:''}${state.loading&&!data?`<p role="status">${esc(t('historyLoading'))}</p>`:''}${rows?`<div class="connection-test-table-scroll"><table class="connection-test-table"><thead><tr>${['historyDate','historyResult','historyProject','historyDuration','historyDetails'].map(key=>`<th scope="col">${esc(t(key))}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`:data?`<p>${esc(t('noAttempts'))}</p>`:''}${data?`<nav class="connection-history-pages" aria-label="${esc(t('historyPages'))}"><span>${esc(t('historyRange',{start,end,total}))} · ${esc(t('historyPage',{page,pages}))}</span><div><button type="button" data-connection-history-page="previous" ${state.loading||data.offset===0?'disabled':''}>${esc(t('historyPrevious'))}</button><button type="button" data-connection-history-page="next" ${state.loading||end>=total?'disabled':''}>${esc(t('historyNext'))}</button></div></nav>`:''}</section>`;
  }
  // Keep structured failure details attached to the attempt that produced them.
  function renderTestHistory(row) {
    const state=historyState(row.id),data=state.data,tests=data?.tests||[],total=data?.total||0;
    const rows=tests.map(test=>{
      const project=test.projectBinding,known=(row.projectBindings||[]).find(binding=>binding.id===project?.bindingId);
      const projectName=known?.project_name||(view.catalog?.projects||[]).find(item=>item.id===project?.project)?.name||project?.project||'—';
      const seconds=Number.isFinite(test.startedAt)&&Number.isFinite(test.finishedAt)?Math.max(0,Math.round((test.finishedAt-test.startedAt)*10)/10):null;
      const reason=test.error?renderTestError(test.error):(test.message?'<p>'+esc(resultMessage(test.message))+'</p>':'');
      return '<tr data-connection-test-result="'+esc(test.id)+'"><td>'+esc(stamp(test.startedAt)||'—')+'</td><td><span class="capability-state" data-capability-state="'+esc(test.state)+'">'+esc(stateLabel(test.state))+'</span>'+(test.current===false?'<small>'+esc(t('historicalResult'))+'</small>':'')+'</td><td>'+esc(projectName)+'</td><td>'+(seconds==null?'—':esc(t('historySeconds',{value:seconds})))+'</td><td><details data-connection-details="probe:'+esc(test.id)+'"><summary>'+esc(t('historyDetails'))+'</summary><div class="connection-test-detail"><strong>'+esc(t('attemptTitle'))+'</strong>'+reason+(project?'<p>'+esc(t('projectBindingChoice'))+': '+esc(projectName)+'</p><code>'+esc(project.scope?.root||project.scope?.nativeRef||'')+'</code>':'')+(test.nativeVisibility?'<p>'+esc(t('visibilityConfirmed'))+'</p>':'')+(stamp(test.finishedAt)?'<p>'+esc(t('testFinished',{date:stamp(test.finishedAt)}))+'</p>':'')+(!testTerminal(test)&&stamp(test.deadline)?'<p>'+esc(t('testDeadline',{date:stamp(test.deadline)}))+'</p>':'')+'<p>'+esc(t('historyAttemptId'))+': <code>'+esc(test.id)+'</code></p>'+renderNativeChat({nativeChat:test.nativeChat})+'</div></details></td></tr>';
    }).join('');
    const start=total?data.offset+1:0,end=Math.min(total,(data?.offset||0)+tests.length),page=Math.floor((data?.offset||0)/state.limit)+1,pages=Math.max(1,Math.ceil(total/state.limit));
    return `<section class="connection-section connection-test-history" aria-busy="${state.loading}"><h3>${esc(t('attemptsTitle'))}</h3><p>${esc(t('historyHelp'))}</p>${data?testSummary({tests},data.counts):''}${state.error?`<p role="alert">${esc(t('historyLoadError'))} <button type="button" data-connection-history-retry ${state.loading?'disabled':''}>${esc(t('historyRetry'))}</button></p>`:''}${state.loading&&!data?`<p role="status">${esc(t('historyLoading'))}</p>`:''}${rows?`<div class="connection-test-table-scroll"><table class="connection-test-table"><thead><tr>${['historyDate','historyResult','historyProject','historyDuration','historyDetails'].map(key=>`<th scope="col">${esc(t(key))}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`:data?`<p>${esc(t('noAttempts'))}</p>`:''}${data?`<nav class="connection-history-pages" aria-label="${esc(t('historyPages'))}"><span>${esc(t('historyRange',{start,end,total}))} · ${esc(t('historyPage',{page,pages}))}</span><div><button type="button" data-connection-history-page="previous" ${state.loading||data.offset===0?'disabled':''}>${esc(t('historyPrevious'))}</button><button type="button" data-connection-history-page="next" ${state.loading||end>=total?'disabled':''}>${esc(t('historyNext'))}</button></div></nav>`:''}</section>`;
  }
  function readyProjectBindings(row) {
    return (row.projectBindings||[]).filter(binding => binding.status==='active' && !binding.pendingRelocation && binding.id);
  }
  function renderProjectBindingChoice(row) {
    const routed=row.profile?.capabilities?.createChat?.projectRouting===true, choices=readyProjectBindings(row);
    if (!routed && !choices.length) return '';
    const selected=view.projectSelections.get(row.id)||'';
    const options=choices.map(binding => `<option value="${esc(binding.id)}" ${selected===binding.id?'selected':''}>${esc((binding.project_name||binding.project||binding.id)+' · '+(binding.scope?.root||binding.scope?.nativeRef||''))}</option>`).join('');
    return `<label class="connection-project-choice">${esc(t('testChatProject'))}<select data-connection-project-binding="${esc(row.id)}" ${choices.length?'':'disabled'}>${routed?`<option value="" ${selected?'':'selected'}>${esc(t('projectBindingRequired'))}</option>`:''}${options}</select></label>`;
  }
  function renderExchangeTest(row) {
    const running=probeRunning(row,view.projectSelections.get(row.id)||'');
    const dirty=view.controlDrafts.get(row.id)?.dirty===true;
    const routed=row.profile?.capabilities?.createChat?.projectRouting===true, choices=readyProjectBindings(row), missingBinding=routed&&(!choices.length||!view.projectSelections.get(row.id));
    return `<section class="connection-section connection-exchange-test"><h3>${esc(t('exchangeTest'))}</h3>${canProbeControl(row)?`<p>${esc(t('exchangeImpact'))}</p>${renderProjectBindingChoice(row)}<p data-control-save-required ${dirty?'':'hidden'}>${esc(t('dirtyProbe'))}</p><button class="primary" type="button" data-connection-test="${esc(row.id)}" ${blocked()||row.revoked||running||dirty||missingBinding?'disabled':''}>${esc(t(running?'stateRunning':'exchangeAction'))}</button>`:`<p>${esc(t('exchangeUnavailable'))}</p>`}<a class="connection-history-link" href="#settings/agents/apps/${encodeURIComponent(row.id)}/diagnostics">${esc(t('attemptsTitle'))}</a></section>`;
  }
  function renderExchangeTest(row) {
    const running=probeRunning(row,view.projectSelections.get(row.id)||''),dirty=view.controlDrafts.get(row.id)?.dirty===true;
    const routed=row.profile?.capabilities?.createChat?.projectRouting===true,choices=readyProjectBindings(row),missingBinding=routed&&(!choices.length||!view.projectSelections.get(row.id));
    const controls=canProbeControl(row)?`<p>${esc(t('exchangeImpact'))}</p>${renderProjectBindingChoice(row)}<p data-control-save-required ${dirty?'':'hidden'}>${esc(t('dirtyProbe'))}</p><button class="primary" type="button" data-connection-test="${esc(row.id)}" ${blocked()||row.revoked||running||dirty||missingBinding?'disabled':''}>${esc(t(running?'stateRunning':'exchangeAction'))}</button>`:`<p>${esc(t('exchangeUnavailable'))}</p>`;
    return `<section class="connection-section connection-exchange-test"><h3>${esc(t('exchangeTest'))}</h3>${controls}${renderLatestTestOutcome(row)}<a class="connection-history-link" href="#settings/agents/apps/${encodeURIComponent(row.id)}/diagnostics">${esc(t('attemptsTitle'))}</a></section>`;
  }
  function probeRunning(row,bindingId) {
    const routed=row.profile?.capabilities?.createChat?.projectRouting===true;
    return (row.tests||[]).some(test=>test.current!==false&&!testTerminal(test)&&(!routed||test.projectBinding?.bindingId===bindingId));
  }
  function controlDraft(row) {
    const control = row.control || row.profile?.control;
    if (!view.controlDrafts.has(row.id)) view.controlDrafts.set(row.id, {protocol:control?.protocol||'mcp-http', endpoint:control?.endpoint||'', apiKey:'', dirty:false});
    const draft = view.controlDrafts.get(row.id);
    if (!draft.dirty && !view.busy && !view.pending) { draft.protocol=control?.protocol||'mcp-http';draft.endpoint=control?.endpoint||''; }
    return draft;
  }
  function renderControl(row) {
    const draft=controlDraft(row),disabled=blocked()||row.revoked,id=esc(row.id);
    const adapter=row.profile?.capabilities?.createChat?.tool==='codex-desktop-bridge.createChat';
    return `<div class="connection-control"><p id="connection-control-key-help-${id}" class="connection-control-key-help">${esc(t(adapter?'codexKeyHelp':'controlKeyHelp'))}</p>${row.control?`<p class="connection-control-status">${esc(t(row.control.hasCredential?'controlConfigured':'controlMissing'))}</p>`:''}<form data-connection-control-form="${id}"><label for="connection-control-protocol-${id}">${esc(t('controlProtocol'))}</label><select id="connection-control-protocol-${id}" name="protocol" ${disabled?'disabled':''}><option value="mcp-http" ${draft.protocol==='mcp-http'?'selected':''}>${esc(t('controlMcp'))}</option><option value="http-json" ${draft.protocol==='http-json'?'selected':''}>${esc(t('controlHttp'))}</option></select><label for="connection-control-endpoint-${id}">${esc(t('controlEndpoint'))}</label><input id="connection-control-endpoint-${id}" name="endpoint" type="url" value="${esc(draft.endpoint)}" ${disabled?'disabled':''}><label for="connection-control-key-${id}">${esc(t('controlKey'))}</label><input id="connection-control-key-${id}" name="apiKey" type="password" value="${esc(draft.apiKey)}" autocomplete="new-password" aria-describedby="connection-control-key-help-${id}" ${disabled?'disabled':''}><button type="submit" ${disabled?'disabled':''}>${esc(t('controlSaveOnly'))}</button><p class="connection-save-help">${esc(t('saveOnlyHelp'))}</p></form></div>`;
  }

  function renderRuleReport(row) {
    const rules = row.profile?.persistentInstructions;
    const status=rules?.status==='saved'?t('rulesReported'):rules?.status==='manual'?t('rulesManual'):t('instructionsUnknown');
    const current=!rules?.revision?t('ruleCurrentUnknown'):row.instructionsCurrent===true?t('ruleCurrent'):t('ruleOutdated');
    return `<section class="connection-section connection-rule-receipt"><h3>${esc(t('ruleReceipt'))}</h3><p>${esc(status)}</p><p>${esc(current)}</p><a href="#settings/agents/rules">${esc(t('openGlobalRules'))}</a></section>`;
  }
  function connectionName(row) {
    const client=String(row.client||'').trim().toLowerCase();
    if(client==='codex'||client.startsWith('openai-codex'))return 'Codex';
    if(client==='cursor'||client.startsWith('cursor-'))return 'Cursor';
    if(['claude-code','claude_code','claude code'].includes(client))return 'Claude Code';
    return row.metadata?.label || row.client || t('applicationNotReported');
  }
  function activeProjects(row) { return new Set((row.projectBindings||[]).filter(b=>b.status==='active').map(b=>b.project)).size; }
  function publicProfile(value) {
    if(Array.isArray(value))return value.map(publicProfile);
    if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([key])=>!/(api.?key|token|authorization|secret|credential)/i.test(key)).map(([key,item])=>[key,publicProfile(item)]));
    return value;
  }
  function renderHeader(label, {intro='', client=false, invite=false} = {}) {
    return `<div class="section-head connections-head"><div class="connection-heading"><div class="connection-title"><h2>${esc(label)}</h2>${client?`<span class="scope">${esc(t('installationScope'))}</span>`:''}</div>${intro?`<p>${esc(intro)}</p>`:''}</div><div class="settings-header-actions">${client?`<button type="button" data-connection-catalog>${esc(t('back'))}</button>`:''}<button type="button" data-connection-refresh ${view.loading?'disabled':''}>${esc(t('refresh'))}</button>${invite?`<form class="connections-invite" data-connection-form><button type="submit" class="primary" ${blocked()?'disabled':''}>${esc(t('connectApplication'))}</button></form>`:''}</div></div>${renderNotices()}`;
  }
  function renderCatalog() {
    const rows=bindings(),size=8;
    if(view.catalog==null)return renderHeader(t('applications'),{intro:t('applicationsIntro'),invite:true});
    view.catalogPage=Math.min(view.catalogPage,Math.max(0,Math.ceil(rows.length/size)-1));
    const list=rows.slice(view.catalogPage*size,(view.catalogPage+1)*size);
    return `${renderHeader(t('applications'),{intro:t('applicationsIntro'),invite:true})}<p class="connection-catalog-help">${esc(t('registrationHelp'))}</p>${rows.length?`<div class="connection-table-wrap"><table class="connection-catalog"><thead><tr><th>${esc(t('application'))}</th><th>${esc(t('access'))}</th><th>${esc(t('bindingsColumn'))}</th><th>${esc(t('lastRequestColumn'))}</th><th>${esc(t('action'))}</th></tr></thead><tbody>${list.map(row=>`<tr data-connection-id="${esc(row.id)}"><td><strong>${esc(connectionName(row))}</strong>${row.client&&row.client!==connectionName(row)?`<small>${esc(row.client)}</small>`:''}</td><td>${esc(row.revoked?t('revoked'):row.activity?.state==='recent-request'?t('recentRequest'):t('registered'))}</td><td>${row.scope==='global'?activeProjects(row):esc(row.project_name||row.project||'—')}</td><td>${esc(stamp(row.activity?.lastRequest)||'—')}</td><td><button type="button" data-connection-open="${esc(row.id)}">${esc(t('open'))}</button></td></tr>`).join('')}</tbody></table></div>${rows.length>size?`<div class="connection-pagination"><span>${view.catalogPage*size+1}–${Math.min(rows.length,(view.catalogPage+1)*size)} / ${rows.length}</span><button type="button" data-connection-page="previous" ${view.catalogPage?'':'disabled'}>${esc(t('previousPage'))}</button><button type="button" data-connection-page="next" ${(view.catalogPage+1)*size>=rows.length?'disabled':''}>${esc(t('nextPage'))}</button></div>`:''}`:`<p class="connections-empty">${esc(t('empty'))}</p>`}<details class="connection-setup" data-connection-details="setup"><summary>${esc(t('setupTitle'))}</summary><ol><li>${esc(t('setupClient'))}</li><li>${esc(t('setupMcp'))}</li><li>${esc(t('setupRules'))}</li><li>${esc(t('setupTest'))}</li></ol></details>`;
  }
  function canonicalTab(tab) { return ({status:'access',details:'diagnostics',access:'access',control:'control',projects:'projects',diagnostics:'diagnostics'})[tab]||'access'; }
  function renderClient(row) {
    const tab=canonicalTab(view.tab),label=connectionName(row),count=activeProjects(row);
    const scope=row.scope==='global'?t('accessScopeGlobal'):t('scopeOneProject',{project:row.project_name||row.project||t('applicationNotReported')});
    const last=row.activity?.lastRequest||row.features?.mcp?.verification?.testedAt||row.capabilities?.mcp?.testedAt;
    const observed=!!last&&!row.revoked;
    const identity=`<dl class="connection-identity"><dt>${esc(t('application'))}</dt><dd>${esc(label)}</dd><dt>${esc(t('modelLabel'))}</dt><dd>${esc(row.metadata?.model||t('noModel'))}</dd><dt>${esc(t('access'))}</dt><dd>${esc(scope)}</dd>${row.external_id?`<dt>${esc(t('externalId',{externalId:''}).split(':')[0])}</dt><dd>${esc(row.external_id)}</dd>`:''}</dl>`;
    const origin=global.location?.origin;
    const access=`<section class="connection-section connection-incoming"><div class="connection-section-head"><h3>${esc(t('incomingTools'))}</h3><span class="connection-direction-label">${esc(t('incomingDirection'))}</span></div><p>${esc(t('incomingExplanation'))}</p><p>${esc(t('universalMcpHelp'))}</p>${row.revoked?'':`<p>${esc(t('granted'))}</p>`}<strong class="capability-state" data-capability-state="${row.revoked?'revoked':observed?'verified':'ready'}">${esc(row.revoked?t('revoked'):observed?t('incomingObserved'):t('incomingNotObserved'))}</strong><p>${esc(scope)}</p><p>${esc(t('boundProjects',{count}))}</p>${origin?`<dl class="connection-identity"><dt>${esc(t('hubEndpoint'))}</dt><dd><code>${esc(origin+'/mcp')}</code></dd></dl>`:''}${last?`<p>${esc(t('lastRequest',{date:stamp(last)}))}</p>`:''}<p>${esc(t('incomingEvidence'))}</p><details><summary>${esc(t('openSetup'))}</summary><p>${esc(t('setupIncoming'))}</p><p>${esc(t('tokenHelp'))}</p><a href="#settings/agents/apps">${esc(t('back'))}</a></details></section>${renderRuleReport(row)}<section class="connection-section connection-access"><h3>${esc(t('manageAccess'))}</h3><p>${esc(t('tokenHelp'))}</p>${row.revoked?`<button type="button" data-connection-reconnect="${esc(row.id)}" ${blocked()?'disabled':''}>${esc(t('reconnect'))}</button>`:`<button type="button" data-connection-revoke="${esc(row.id)}" ${blocked()?'disabled':''}>${esc(t('revoke'))}</button>`}</section><p class="connection-model-reference">${esc(t('modelRequestsSeparate'))} <a href="#settings/agents/models">${esc(t('toModels'))}</a></p>`;
    const status=controlStatus(row),endpoint=row.profile?.control?.endpoint,configured=row.control?.endpoint;
    const provided=!!(endpoint||configured),codex=row.client==='codex'||row.profile?.host==='codex';
    const adapter=row.profile?.capabilities?.createChat?.tool==='codex-desktop-bridge.createChat';
    const route=provided?`<strong class="capability-state" data-capability-state="${esc(status.state)}">${esc(status.state==='ready'?t('controlConfiguredReady'):featureStateLabel(status.state))}</strong><p>${esc(t(adapter?'codexControlSource':'externalControlHelp'))}</p>${renderControl(row)}${endpoint&&configured&&endpoint!==configured?`<p>${esc(t('endpointDeclared'))}: <code>${esc(endpoint)}</code></p>`:''}${adapter?`<p class="connection-adapter-notice">${esc(t('codexControlLifecycle'))}</p>`:''}`:`<strong class="capability-state" data-capability-state="unavailable">${esc(t(codex?'codexControlSetup':'unsupportedControlTitle'))}</strong><p>${esc(t(codex?'codexControlHelp':'unsupportedControlHelp'))}</p>`;
    const openOnly=!provided&&(row.nativeChat?.openUri||row.profile?.capabilities?.openChat)?renderFeature(row,'openChat'):'';
    const control=`<p class="connection-page-intro">${esc(t('chatIntegrationHelp'))}</p><section class="connection-section connection-control-route"><div class="connection-section-head"><h3>${esc(t('controlConnection'))}</h3><span class="connection-direction-label">${esc(t('outgoingDirection'))}</span></div>${route}</section>${provided?`<div class="connection-feature-grid">${['openChat','createChat','sendMessage','callback'].map(id=>renderFeature(row,id)).join('')}</div>${renderExchangeTest(row)}`:openOnly}`;
    const rawProfile=row.profile?{...row.profile}:null;if(rawProfile)delete rawProfile.persistentInstructions;
    const diagnostics=`<section class="connection-section"><h3>${esc(t('diagnosticsIdentity'))}</h3><p>${esc(t('reportedIdentity'))}</p>${identity}${row.metadata?.chat?`<p>${esc(t('chat',{chat:row.metadata.chat}))}</p>`:''}${row.metadata?.session?`<p>${esc(t('session',{session:row.metadata.session}))}</p>`:''}${renderNativeChat(row)}</section>${provided||(row.tests||[]).length?renderTestHistory(row):''}<section class="connection-section"><h3>${esc(t('diagnosticProfile'))}</h3><p>${esc(t('diagnosticProfileHelp'))}</p><details data-connection-details="profile:${esc(row.id)}"><summary>${esc(t('rawProfile'))}</summary>${rawProfile?`<pre>${esc(JSON.stringify(publicProfile(rawProfile),null,2))}</pre>`:`<p>${esc(t('noProfile'))}</p>`}</details></section>`;
    const panel=tab==='projects'?(global.HubConnectionProjects?.render(row,view.catalog?.projects||[],blocked())||`<p>${esc(t('projectsUnavailable'))}</p>`):tab==='diagnostics'?diagnostics:tab==='control'?control:access;
    return `${renderHeader(label,{client:true})}<div class="connection-tabs" role="tablist" aria-label="${esc(label)}">${[['access','statusTab'],['control','chatsTab'],['projects','bindingsTab'],['diagnostics','detailsTab']].map(([id,key])=>`<button type="button" role="tab" id="connection-tab-${id}" aria-selected="${id===tab}" aria-controls="connection-client-panel" data-connection-tab="${id}">${esc(t(key))}</button>`).join('')}</div><div id="connection-client-panel" role="tabpanel" aria-labelledby="connection-tab-${tab}">${panel}</div>`;
  }
  function renderNotices() {
    return `${view.invitation?`<section class="connection-invitation"><label>${esc(t(view.invitation.reconnect?'reconnectInvitation':'invitation'))}<input readonly data-connection-url value="${esc(view.invitation.url)}"></label><p>${esc(t('invitationHelp'))}</p>${view.invitation.reconnect?`<p>${esc(t('reconnectHelp'))}</p>`:''}<p>${esc(t('expires',{date:stamp(view.invitation.expires)}))}</p><button type="button" data-connection-copy>${esc(t('copy'))}</button><button type="button" data-connection-dismiss-invite>${esc(t('closeInvitation'))}</button></section>`:''}<p class="connections-status" role="status">${esc(view.error||view.status||(view.loading||view.catalog==null?t('loading'):''))}${view.pending?` ${esc(t('pending'))} <button type="button" data-connection-retry ${view.busy?'disabled':''}>${esc(t('retry'))}</button>`:''}</p>`;
  }
  function renderContent() {
    const row=bindings().find(item=>item.id===view.selectedId);
    return view.selectedId?(row?renderClient(row):`${renderHeader(t('applications'),{client:true})}<p>${esc(view.loading?t('loading'):t('missingConnection'))}</p>`):renderCatalog();
  }
  function navigate(connectionId='',tab='status') {
    view.selectedId=connectionId;view.tab=connectionId?canonicalTab(tab):'access';
    if(global.location)global.location.hash='#settings/agents/apps'+(connectionId?'/'+encodeURIComponent(connectionId)+'/'+view.tab:'');
    render();
    if(connectionId&&view.tab==='diagnostics')void loadHistory(connectionId);
  }
  function render(root = view.root, background = false) {
    if (!connected(root)) return;
    if(root.__hubConnectionsRendered)root.querySelectorAll?.('[data-connection-details]').forEach(detail=>{if(detail.open)view.details.add(detail.dataset.connectionDetails);else view.details.delete(detail.dataset.connectionDetails);});
    const html = renderContent();
    if (global.HubLiveUI?.patch) global.HubLiveUI.patch(root, html, {preserveInputs:true}); else root.innerHTML = html;
    // The invitation is server output, not an editable form value. Live patching
    // preserves control values, so explicitly publish a newly acknowledged URL.
    const urlInput = root.querySelector('[data-connection-url]');
    if (urlInput && view.invitation && urlInput.value !== view.invitation.url) urlInput.value = view.invitation.url;
    root.querySelectorAll?.('[data-connection-details]').forEach(detail=>{detail.open=view.details.has(detail.dataset.connectionDetails);});
    root.querySelectorAll?.('[data-connection-control-form]').forEach(form=>{const draft=view.controlDrafts.get(form.dataset.connectionControlForm);if(!draft)return;for(const key of ['protocol','endpoint','apiKey']){const input=form.querySelector(`[name="${key}"]`);if(input&&input.value!==draft[key])input.value=draft[key];}});
    root.__hubConnectionsRendered = true;
    bind(root);
    global.HubConnectionProjects?.afterRender?.(root);
  }
  function capturePayload(root) {
    return {action:'invite', requestId:requestId()};
  }
  function validateAck(result, operation) {
    let valid;
    if (operation.kind === 'invite' || operation.kind === 'reconnect') valid = typeof result.id === 'string' && result.id.length > 0 && typeof result.url === 'string' && result.url.length > 0 && typeof result.expires === 'number' && Number.isFinite(result.expires) && result.expires > 0 && (operation.kind!=='reconnect'||result.reconnect===operation.payload.id);
    else if (operation.kind === 'configure-control') valid = result.id===operation.payload.id && result.saved===true;
    else if (operation.kind === 'test') valid = result.id===operation.payload.id && result.capabilities && typeof result.capabilities==='object' && !Array.isArray(result.capabilities) && Array.isArray(result.tests);
    else if (operation.kind === 'project-binding') {
      const requested=operation.payload.operation,binding=result.binding;
      valid=binding?.connection===operation.payload.id&&Number.isInteger(binding?.revision)&&typeof binding?.id==='string'
        &&(requested.bindingId?binding.id===requested.bindingId:binding.project===requested.project&&binding.scope?.root===requested.scope?.root);
    }
    else if (operation.kind === 'describe-profile') valid=result.id===operation.payload.id&&typeof result.profileRevision==='string';
    else if (operation.kind === 'launch') valid=result.requestId===operation.payload.request.requestId&&result.envelope?.connection===operation.payload.id;
    else valid = result.id === operation.payload.id && result.revoked === true;
    if (!valid) { const error = Error(t('invalidAck')); error.uncertain = true; throw error; }
  }
  async function mutate(payload, kind, retry = false) {
    if (view.busy || (view.pending && (!retry || payload !== view.pending.payload || kind !== view.pending.kind))) return;
    const operation = retry && view.pending ? view.pending : {payload:{...payload}, kind, body:JSON.stringify(payload)};
    view.busy = true; view.error = ''; view.status = kind==='test'?t('stateRunning'):''; render(view.root, true);
    try {
      const result = await api('/api/v1/connections', {method:'POST', body:operation.body});
      validateAck(result, operation); view.pending = null;
      if(kind==='project-binding')global.HubConnectionProjects?.ack(result);
      if (kind === 'invite' || kind === 'reconnect') view.invitation = {id:result.id, url:result.url, expires:result.expires, reconnect:result.reconnect};
      if (kind === 'configure-control') { const draft=view.controlDrafts.get(operation.payload.id);if(draft){draft.apiKey='';draft.dirty=false;}view.status=t('savedWithoutProbe'); }
      if (kind === 'test') { const row=bindings().find(item=>item.id===result.id);if(row)Object.assign(row,{capabilities:result.capabilities,tests:result.tests,profileRevision:result.profileRevision});view.status=''; }
      await loadCatalog();
    }
    catch (error) { view.error = error.message || t('errorMutation'); if (error.uncertain || retry) view.pending = operation; }
    finally { view.busy = false; render(view.root, true); }
  }
  async function onSubmit(root) { if (blocked()) return; try { await mutate(capturePayload(root), 'invite'); } catch (error) { view.error = error.message; render(root, true); } }
  async function revoke(id) { if (blocked() || !global.confirm?.(t('confirmRevoke'))) return; await mutate({action:'revoke', id}, 'revoke'); }
  async function reconnect(id) { if (blocked()) return; await mutate({action:'reconnect',id,requestId:requestId()},'reconnect'); }
  async function test(id) { const row=bindings().find(item=>item.id===id), routed=row?.profile?.capabilities?.createChat?.projectRouting===true, choice=view.root?.querySelector?.(`[data-connection-project-binding="${id}"]`), bindingId=choice?.value||'';if (blocked()||!row||row.revoked||!canProbeControl(row)||view.controlDrafts.get(id)?.dirty||(routed&&!bindingId)||probeRunning(row,bindingId)) return; await mutate({...{action:'test',id},...(bindingId?{bindingId}:{})},'test'); }
  async function configureControl(form) {
    if (blocked()) return;
    const id = form.dataset.connectionControlForm, row = bindings().find(item=>item.id===id);
    if (!row || row.revoked) return;
    const draft=controlDraft(row);for(const key of ['protocol','endpoint','apiKey'])draft[key]=form.querySelector(`[name="${key}"]`)?.value??draft[key];
    await mutate({action:'configure-control',id,protocol:draft.protocol,endpoint:draft.endpoint,apiKey:draft.apiKey,requestId:requestId()},'configure-control');
  }
  async function copyUrl(root) {
    const input = root.querySelector('[data-connection-url]'); if (!input) return;
    try {
      if (typeof global.navigator?.clipboard?.writeText !== 'function') throw Error('Clipboard unavailable');
      await global.navigator.clipboard.writeText(input.value); view.status = t('copied');
    } catch (_) { input.focus?.(); input.select?.(); view.status = t('copyFallback'); }
    view.error = ''; render(root, true);
  }
  function bind(root) {
    if (root.__hubConnectionsBound) return;
    root.__hubConnectionsBound = true;
    const updateControl = event=>{const form=event.target.closest?.('[data-connection-control-form]'),key=event.target.name;if(!form||!['protocol','endpoint','apiKey'].includes(key)||blocked())return;const row=bindings().find(item=>item.id===form.dataset.connectionControlForm);if(row&&!row.revoked){const draft=controlDraft(row);draft[key]=event.target.value;draft.dirty=true;const testButton=root.querySelector('[data-connection-test]');if(testButton)testButton.disabled=true;const saveHint=root.querySelector('[data-control-save-required]');if(saveHint)saveHint.hidden=false;}};
    root.addEventListener('input', updateControl);
    root.addEventListener('change', event=>{const select=event.target.closest?.('[data-connection-project-binding]');if(select){view.projectSelections.set(select.dataset.connectionProjectBinding,select.value||'');render(root,true);return;}updateControl(event);});
    root.addEventListener('submit', event => {
      if(event.target.matches?.('[data-connection-form]')){event.preventDefault();return onSubmit(root);}
      if(event.target.matches?.('[data-connection-control-form]')){event.preventDefault();return configureControl(event.target);}
    });
    root.addEventListener('click', event => {
      const target=event.target;
      const open=target.closest?.('[data-connection-open]');if(open)return navigate(open.dataset.connectionOpen,'access');
      if(target.closest?.('[data-connection-catalog]'))return navigate();
      const tab=target.closest?.('[data-connection-tab]');if(tab)return navigate(view.selectedId,tab.dataset.connectionTab);
      const historyPage=target.closest?.('[data-connection-history-page]');if(historyPage){const state=historyState(view.selectedId);return loadHistory(view.selectedId,Math.max(0,state.offset+(historyPage.dataset.connectionHistoryPage==='next'?state.limit:-state.limit)));}
      if(target.closest?.('[data-connection-history-retry]')){const state=historyState(view.selectedId);return loadHistory(view.selectedId,state.requestedOffset);}
      const page=target.closest?.('[data-connection-page]');if(page){view.catalogPage=Math.max(0,view.catalogPage+(page.dataset.connectionPage==='next'?1:-1));return render();}
      if(target.closest?.('[data-connection-dismiss-invite]')){view.invitation=null;return render();}
      const binding=target.closest?.('[data-binding-action]');
      if(binding&&!blocked())return global.HubConnectionProjects?.click(binding,bindings(),mutate,()=>render()).catch(error=>{view.error=error.message;render();});
      const revokeButton=target.closest?.('[data-connection-revoke]');if(revokeButton)return revoke(revokeButton.dataset.connectionRevoke);
      const reconnectButton=target.closest?.('[data-connection-reconnect]');if(reconnectButton)return reconnect(reconnectButton.dataset.connectionReconnect);
      const testButton=target.closest?.('[data-connection-test]');if(testButton)return test(testButton.dataset.connectionTest);
      if(target.closest?.('[data-connection-copy]'))return copyUrl(root);
      if(target.closest?.('[data-connection-refresh]'))return loadCatalog();
      if(target.closest?.('[data-connection-retry]')&&view.pending)return mutate(view.pending.payload,view.pending.kind,true);
    });
  }
  function schedulePoll(root) { if (view.pollTimer != null) return; view.pollTimer = setTimeout(async () => { view.pollTimer = null; if (!connected(view.root)) return; await loadCatalog(); schedulePoll(view.root); }, 5000); }
  function afterRender(root = global.document?.querySelector?.('#hub-connections-manager')) {
    if(!root)return;
    if(view.root!==root){view.root=root;bind(root);render(root);void loadCatalog();}
    // The application also patches this subtree during background updates.
    // Reopen the component's dialog and restore unsaved control fields even
    // when the root DOM node has been retained by that outer patch.
    root.querySelectorAll?.('[data-connection-control-form]').forEach(form=>{const draft=view.controlDrafts.get(form.dataset.connectionControlForm);if(!draft)return;for(const key of ['protocol','endpoint','apiKey']){const input=form.querySelector(`[name="${key}"]`);if(input)input.value=draft[key];}});
    global.HubConnectionProjects?.afterRender?.(root);
    schedulePoll(root);
  }
  global.addEventListener?.('hub-projects-changed', () => { void loadCatalog(); });
  global.HubI18n?.onChange?.(() => render(view.root, true));
  global.HubConnectionsUI = {page:(options={}) => {view.selectedId=options.connectionId||'';view.tab=canonicalTab(options.tab||'status');return `<section id="hub-connections-manager" class="connections-page">${renderContent()}</section>`;}, afterRender, busy:blocked};
})(typeof window !== 'undefined' ? window : globalThis);
