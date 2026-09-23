# Career Quest — передача финального backend

Все файлы в этой папке коммитит Roman в ветку `roman`. Изменения `frontend/` коммитит фронтендер отдельно. Корневые `docker-compose.yml`, `.gitignore` и `README.md` передайте тимлиду.

## Режимы входа

- По умолчанию `AUTH_ENABLED=false`: явно обозначенное демо без пароля, доступное жюри. Это не защищённый режим.
- При `AUTH_ENABLED=true` API требует сессию. Сотрудник видит только свой профиль, баланс и заявки. HR имеет доступ к аналитике, загрузке профилей и решениям по наградам.
- В присланной обновлённой версии фронтенда форма входа уже подключена к API, режим выбирается через `GET /api/auth/me`. Старый исходный ZIP использовать не нужно.
- Это локальные учётные записи хакатонного приложения; корпоративный SSO не подключён.

Учётные записи создаёт тимлид через терминал (пароль вводится скрыто, минимум 12 символов). В Docker из корня репозитория:

```powershell
docker compose exec backend python manage_users.py --username hr@example.test --role hr
docker compose exec backend python manage_users.py --username employee@example.test --role employee --employee-id E0028
```

Или локально, используя тот же `REWARDS_DB_PATH`, что и сервер:

```powershell
python backend/manage_users.py --username hr@example.test --role hr
python backend/manage_users.py --username employee@example.test --role employee --employee-id E0028
```

После создания аккаунтов добавить `AUTH_ENABLED=true` в корневой `.env` и пересоздать backend: `docker compose up -d --build backend`. Для локального HTTP `AUTH_COOKIE_SECURE=false`; для HTTPS — `true`. `CORS_ORIGINS` должен содержать адрес фронтенда. Не публиковать `.env`, пароли и SQLite.

Сессия живёт 8 часов, хранится в HttpOnly cookie или может передаваться как Bearer token. Выход отзывает сессию. Пароли хранятся как salted PBKDF2 hashes; после 5 неверных попыток логин блокируется на 5 минут.

| API | Данные / результат |
| --- | --- |
| `GET /api/auth/me` | `{auth_enabled, authenticated, user}` |
| `POST /api/auth/login` | `{username,password}` → cookie + `{user,access_token,token_type,expires_in}` |
| `POST /api/auth/logout` | Завершение сессии |

`user` содержит `username`, `role` (`employee` / `hr`) и `employee_id` (для сотрудника). Фронтенд отправляет `credentials: 'include'` и загружает данные только после входа при включённой авторизации.

## Развитие, баллы и магазин

1. Выполнение: `POST /api/activities/{event_id}/complete`, тело `{employee_id}`. Сохранён и старый `/api/activities/complete` с `event_id` в теле.
2. Ответ содержит `points_awarded`, `points_balance`, `skill_updates`; `skill_id` — канонический `SK_...`.
3. 150 QP начисляются только при первом завершении добровольной активности с положительным приростом. Обязательные курсы, уже завершённые курсы из стартовой истории и нулевой прирост не дают QP. Стартовый баланс — 0; баллы за старые записи задним числом не начисляются.
4. Повтор того же курса не повышает навыки и не начисляет QP. Для повторяемого EV_036 новая сессия может повысить навык до потолка, но QP остаются одноразовыми. Навык выше потолка вводного курса не снижается.
5. Навыки, новые записи истории, пользовательские профили, кошелёк и аккаунты сохраняются в SQLite. Прогресс и баллы завершения фиксируются одной транзакцией.

| API | Назначение |
| --- | --- |
| `GET /api/rewards` | Каталог, цены, актуальные остатки ограниченных наград |
| `GET /api/employees/{id}/points` | Баланс, заработано и потрачено; возврат не считается новым заработком |
| `GET /api/employees/{id}/points/transactions` | Последние 100 операций кошелька |
| `POST /api/rewards/{reward_id}/redeem` + `{employee_id}` | Списание и заявка `Pending`; 409 при нехватке QP/остатка |
| `GET /api/employees/{id}/rewards/requests` | Личная история |
| `GET /api/hr/rewards/requests` | Все заявки; необязательный `status_filter` |
| `POST /api/hr/rewards/requests/{id}/decision` + `{decision:'Approved'}` или `Rejected` | Решение HR; отказ возвращает QP ровно один раз |
| `POST /api/hr/rewards/requests/{id}/fulfill` | Выдача одобренной награды, статус `Redeemed`; повтор безопасен |
| `GET /api/hr/rewards/analytics` | Реальные начисления, траты и заявки; открытия магазина/просмотры не выдумываются |

При выполнении активности и покупке фронтенд передаёт `Idempotency-Key`: UUID одной операции. При сетевом повторе сохраняется тот же UUID; новая намеренная операция получает новый UUID. Ключ нельзя повторно использовать для другой активности/награды. Для старых клиентов без ключа повторный заказ той же награды при существующей `Pending`-заявке возвращает её без нового списания.

Остатки каталога: 12 конференций и 24 худи взяты из макета. Заявки резервируют остатки, отказ освобождает их. Остальные награды не ограничены по количеству. Баллы начисляются по кнопке подтверждения завершения; внешняя LMS и автоматическая проверка ответов теста в датасете отсутствуют.

## Совместимость интерфейса

- `GET /api/health`, `/api/employees`, `/api/employees/{id}/profile` предоставляют данные в формате интерфейса.
- Рекомендации сохраняют исходный backend-контракт `event_id/title/target_skill/gain/max_level/score/rationale`; адаптер в `frontend/src/api.ts` преобразует его в карточки.
- `GET /api/hr/dashboard` формирует данные для HR-экрана; исходный `/api/hr/analytics` также доступен.
- Загрузка файла: multipart `file` на `/api/profiles/upload-file`; допустим профиль, массив профилей или `{profiles:[...]}`, максимум 1 MiB. Ответ `{profile_ids,loaded_count,validation_errors}`.
- Чат: `POST /api/chat` с `{employee_id,message}` → `{answer,source}`. Интеграция рекомендаций OpenAI и страховочный fallback сохранены.
- После выполнения, покупки, отказа или выдачи обновлять профиль/кошелёк/историю/каталог/HR-метрики. Это включено в обновлённый фронтенд.

## Данные и запуск

Локальная база по умолчанию: `backend/state/rewards.sqlite3`; путь можно задать `REWARDS_DB_PATH`. Служебные файлы исключены локальными `backend/.gitignore` и `backend/.dockerignore`, поэтому достаточно коммитить только `backend/`.

Тимлиду нужно применить изменение корневого Compose: `REWARDS_DB_PATH=/app/state/rewards.sqlite3`, том `rewards-state:/app/state` и корневое объявление `volumes: {rewards-state: {}}`. Не выполнять `docker compose down -v`, если нужно сохранить накопленный прогресс.

Сервер рассчитан на один процесс Uvicorn, как в Dockerfile. Несколько workers не поддерживают синхронное обновление кэша навыков между процессами.

```powershell
python -m pytest backend/tests -q
```

Тесты используют временные базы, отключают реальные запросы OpenAI и проверяют ограничения доступа, прогресс после восстановления, одноразовое начисление, конкурирующие покупки, возвраты, остатки и выдачу наград.
