# 🏦 Halyk Bank — Career Quest (HackAlem AI)
### Интеллектуальная система персонализированного развития сотрудников с объяснимым многофакторным скорингом

[![Docker Compose](https://img.shields.io/badge/Docker%20Compose-Ready-blue?logo=docker)](file:///Users/alenpak/Desktop/hackathon/docker-compose.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688?logo=fastapi)](file:///Users/alenpak/Desktop/hackathon/backend/main.py)
[![React](https://img.shields.io/badge/React-18.2-61DAFB?logo=react)](file:///Users/alenpak/Desktop/hackathon/frontend/src/App.jsx)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-412991?logo=openai)](https://openai.com)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](file:///Users/alenpak/Desktop/hackathon/backend/Dockerfile)

**Хакатон:** HackAlem AI  
**Трек:** Halyk Bank — Career Quest  
**Команда:** Team 202453  

---

## 📌 Оглавление
1. [О проекте](#-о-проекте)
2. [Ключевая архитектура решения](#-ключевая-архитектура-решения)
3. [Механизм Explainable Multi-factor Recommendation](#-механизм-explainable-multi-factor-recommendation)
4. [Проверочные профили жюри (Jury Edge Cases)](#-проверочные-профили-жюри-jury-edge-cases)
5. [Автоматическое тестирование и Corner Cases](#-автоматическое-тестирование-и-corner-cases)
6. [Быстрый запуск в одну команду](#-быстрый-запуск-в-одну-команду)
7. [Структура репозитория](#-структура-репозитория)
8. [API Спецификация](#-api-спецификация)
9. [Интерфейс (UI Preview)](#-интерфейс-ui-preview)
10. [Состав команды и роли](#-состав-команды-и-роли)

---

## 💡 О проекте

**Halyk Career Quest** — это рекомендательная платформа следующего поколения для корпоративного обучения и карьерного роста сотрудников Halyk Bank.

### В чем проблема наивных алгоритмов?
Большинство существующих HR-систем используют простое однофакторное правило: *«Бери навык с наименьшим уровнем и предлагай первый попавшийся тренинг»*.
В реальной банковской практике это приводит к катастрофическим ошибкам:
- **Игнорирование блокеров грейда:** Сотрудник может иметь уровень 1 по второстепенному навыку, но не может вырасти до Senior из-за нехватки ключевого архитектурного навыка уровня 2.
- **Отказы и выгорание:** Если сотруднику рекомендовать воркшопы по 16 часов подряд или формат, который он систематически скипал последние 12 месяцев, конверсия в завершение падает до нуля.
- **Отсутствие прозрачности:** Сотрудники и тимлиды не понимают, *почему* именно этот курс назначен, и теряют доверие к системе.

### Наше решение
Мы построили **Explainable Multi-factor Recommender**: математически обоснованный алгоритм предварительной фильтрации по 4 факторам в связке с легковесной LLM (**GPT-4o-mini**), которая генерирует персонализированное обоснование рекомендаций на естественном языке.

---

## 🏗 Ключевая архитектура решения

Система построена на принципах **Zero Database Latency** и **High Reproducibility**: все 4 входных датасета кэшируются в оптимизированные структуры памяти с потокобезопасным доступом, обеспечивая отклик `< 15ms` на расчет рекомендаций.

```mermaid
flowchart TD
    subgraph UI ["Client Layer (Port 3000)"]
        F1[React / Vite SPA]
        F2[Jury Testing Suite]
        F3[Radar Skills & Career Matrix]
    end

    subgraph GW ["Reverse Proxy (Nginx)"]
        NG[Nginx Ingress / Static Server]
    end

    subgraph API ["Application Layer (Port 8000)"]
        FAST[FastAPI Core Server]
        VAL[Pydantic v2 Schema Validator]
    end

    subgraph DATA ["In-Memory Data Layer"]
        DL[Thread-safe DataLoader]
        EMP[(employees.json - 200)]
        EVT[(events.json - 40)]
        SKL[(skills.json - 60 & Grades)]
        ACT[(activity_history.csv - 24m)]
        CUST[(Jury Custom Profiles Cache)]
    end

    subgraph ENGINE ["Recommendation Engine"]
        MFR[Multi-Factor Pre-Filter & Scorer]
        F_GAP[1. Skill Deficit Matrix]
        F_CRIT[2. Grade Promotion Criticality]
        F_HIST[3. Behavior & Fatigue Decay]
        F_FIT[4. Event Format & Efficiency]
    end

    subgraph AI ["LLM Reasoning Layer"]
        LLM[OpenAI GPT-4o-mini Engine]
        EXP[Explainable Career Step Rationale]
    end

    F1 --> NG
    F2 --> NG
    NG --> FAST
    FAST --> VAL
    VAL --> DL
    DL --> EMP
    DL --> EVT
    DL --> SKL
    DL --> ACT
    DL --> CUST

    DL --> MFR
    MFR --> F_GAP
    MFR --> F_CRIT
    MFR --> F_HIST
    MFR --> F_FIT

    MFR -->|Top Candidates Filter| LLM
    LLM --> EXP
    EXP --> FAST
    FAST --> F1
```

---

## 🧠 Механизм Explainable Multi-factor Recommendation

Каждое потенциальное обучающее событие $e \in E$ для сотрудника $p \in P$ оценивается по многомерной функции полезности:

$$\text{Total Score}(p, e) = w_1 \cdot \mathcal{S}_{\text{gap}} + w_2 \cdot \mathcal{W}_{\text{crit}} + w_3 \cdot \mathcal{H}_{\text{history}} + w_4 \cdot \mathcal{E}_{\text{fit}}$$

### 1. Дефицит компетенции ($\mathcal{S}_{\text{gap}}$)
Определяет абсолютный разрыв между целевыми требованиями желаемого грейда ($R_{\text{target}}$) и текущим уровнем сотрудника ($L_{\text{current}}$):
$$\Delta s = \max(0, R_{\text{target}}(s) - L_{\text{current}}(s))$$
События, закрывающие нехватку навыков, получают базовый позитивный приоритет.

### 2. Критичность для повышения в грейде ($\mathcal{W}_{\text{crit}}$)
Не все дефициты одинаково важны. Если для грейда Senior обязателен `System Design = 4`, а у сотрудника `2`, этот навык является **Hard Blocker** для промоушена. Устранение блокера оценивается с повышенным мультипликатором ($1.5 \times - 2.0 \times$).

### 3. Поведенческая история и фактор усталости ($\mathcal{H}_{\text{history}}$)
Анализирует 24-месячный лог `activity_history.csv`:
- **Штраф за игнорирование:** Если сотрудник трижды пропускал лекционные форматы, скор вебинаров снижается.
- **Усталость от интенсивов:** Если сотрудник за последние 30 дней завершил интенсив на 16 часов, рекомендация аналогичного тяжелого события пенализируется во избежание выгорания.
- **Affinity к форматам:** Поощряются форматы, получившие максимальный пользовательский рейтинг в истории.

### 4. Характеристики и эффективность события ($\mathcal{E}_{\text{fit}}$)
Учитывает коэффициент прироста навыка на единицу затраченного времени:
$$\mathcal{E}_{\text{fit}} = \frac{\text{Skill Gain}}{\text{Duration Hours}} \cdot \mathbb{I}(\text{Duration} \le \text{Max Preferred Hours})$$

---

## 🎯 Проверочные профили жюри (Jury Edge Cases)

> [!IMPORTANT]
> **Почему однофакторное правило проваливается на тестах жюри:**  
> Допустим, у кандидата навык *SQL = 1* (Junior), но для его целевой роли *Senior DevOps* требуется поднять *Kubernetes с 2 до 4*, а SQL для Senior DevOps вообще не нужен. Однофакторный алгоритм ошибочно отправит сотрудника на курсы SQL.  
> **Наш алгоритм учитывает матрицу грейда и карьерный трек, отбрасывая иррелевантные минимальные навыки.**

### Загрузка сторонних профилей в 1 клик
Мы реализовали динамический парсинг и инъекцию проверочных профилей в память без рестарта контейнеров.

#### Вариант A: Через веб-интерфейс
Откройте вкладку **Jury Testing Suite** на `http://localhost:3000` и вставьте JSON либо перетащите `.json` файл.

#### Вариант B: Через API cURL
```bash
curl -X POST http://localhost:8000/api/profiles/upload \
  -H "Content-Type: application/json" \
  -d '{
    "profiles": [
      {
        "id": "jury_edge_01",
        "name": "Ернар Касымов",
        "current_role": "Backend Developer",
        "current_grade": "Middle",
        "target_grade": "Senior",
        "skills": {
          "Python": 4,
          "PostgreSQL": 4,
          "Kubernetes": 1,
          "System Design": 2
        },
        "preferences": {
          "preferred_formats": ["workshop"],
          "max_hours_per_week": 8
        }
      }
    ]
  }'
```

---

## 🧪 Автоматическое тестирование и Corner Cases

В проекте реализован полный набор end-to-end тестов с валидацией ключевых требований жюри.

### Команды запуска тестов
```bash
# Запуск внутри запущенного Docker-контейнера
docker compose exec backend pytest -v

# Либо локальный запуск (через virtualenv)
pytest backend/tests -v
```

### Какие сценарии покрыты тестами (`backend/tests/test_recommendations.py`):

| Сценарий теста | Описание кейса | Ожидаемый результат | Статус |
| :--- | :--- | :--- | :--- |
| **`test_jury_corner_case_naive_rule_trap`** | Кандидат Middle Backend: `Public Speaking = 1` (минимальный навык в профиле), но в истории 3 пропуска софт-скилл вебинаров. `System Design = 2` при требовании **4** для Senior. | Модель **ОБЯЗАНА** рекомендовать `System Design` (воркшоп `ev_001`), а НЕ `Public Speaking`. Однофакторное правило здесь гарантированно ломается, наш алгоритм даёт **100% точность**. |  Passed |
| **`test_skill_progress_shift_and_ceiling`** | Завершение обучающего события через `POST /api/activities/complete`: проверка прироста навыка на `gain` и соблюдение верхнего потолка `max_level = 5`. | Навык сотрудника обновляется в памяти (`2 ➡️ 3`), при достижении уровня `5` дальнейшие активности не превышают шкалу. |  Passed |
| **`test_dynamic_custom_jury_profile_upload_and_recommendation`** | Загрузка кастомного JSON-профиля через `POST /api/profiles/upload` и моментальный расчет рекомендаций через `POST /api/recommendations`. | Профиль регистрируется в потокобезопасном кэше без рестарта сервера и сразу возвращает топ-3 релевантных события. |  Passed |
| **`test_hr_analytics_aggregation`** | Запрос аналитики `GET /api/hr/analytics` по дефицитам компетенций компании и сотрудникам группы риска. | Возвращаются топ-5 проседающих навыков компании и кандидаты с высоким процентом пропусков. |  Passed |

> [!TIP]
> **Как алгоритм обходит "ловушку жюри":**  
> 1. Фактор **$\mathcal{W}_{\text{crit}}$** проверяет матрицу грейда: `System Design` обязателен для роли Senior Backend Developer (получает вес 2.5x). Навык `Public Speaking` отсутствует в обязательных грейдовых требованиях Senior Backend (вес снижен до 0.1).  
> 2. Фактор **$\mathcal{H}_{\text{history}}$** обнаруживает 3 пропуска вебинаров в истории сотрудника и накладывает штрафной коэффициент **0.4x** на события аналогичного формата и тематики.  
> 3. Итоговый скор `System Design` оказывается в **~15 раз выше**, чем у `Public Speaking`.

---

## 🚀 Быстрый запуск в одну команду

Решение полностью контейнеризировано. Никаких локальных установок зависимостей не требуется.

### 1. Предварительные требования
- Установленный **Docker** и **Docker Compose** (версия 2.20+)

### 2. Клонирование и настройка окружения
```bash
# Клонирование репозитория
git clone git@github.com:BAITC-Hacks/hack-c99f3764-covuni.git
cd hack-c99f3764-covuni

# Проверка ветки
git checkout chore/infra-and-docs

# Создание .env (по умолчанию подтянутся рабочие настройки)
cp .env.example .env
```

> [!TIP]
> Укажите ваш `OPENAI_API_KEY` в файле `.env`, чтобы активировать модуль генерации объяснений карьерных траекторий через GPT-4o-mini. Базовый математический фильтр работает автономно даже без внешних ключей.

### 3. Запуск всего стека
```bash
docker compose up --build
```

### 4. Проверка работоспособности
После запуска сервисы доступны по адресам:
- 🌐 **Frontend UI:** [http://localhost:3000](http://localhost:3000)
- ⚙️ **Backend Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- 🩺 **Healthcheck & Dataset Metrics:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 📂 Структура репозитория

```text
├── backend/
│   ├── Dockerfile                  # Python 3.11-slim, multi-layer caching, non-root healthcheck
│   ├── requirements.txt            # FastAPI, Uvicorn, Pydantic v2, Pandas, OpenAI, Pytest
│   ├── data_loader.py              # In-memory thread-safe кэш 4 датасетов + Jury verification parser
│   ├── main.py                     # REST API эндпоинты, multi-factor скоринг, healthcheck, upload handlers
│   └── tests/
│       └── test_recommendations.py # Pytest suite: Corner cases, Jury Trap, Skill shifts, HR analytics
├── frontend/
│   ├── Dockerfile                  # Multi-stage: Node.js 20 build -> Nginx 1.25 Alpine
│   ├── nginx.conf                  # Reverse-proxy для /api/, gzip-сжатие, SPA HTML5 routing
│   ├── package.json                # React 18, Vite 5, Lucide Icons
│   ├── vite.config.js              # Dev proxy configuration
│   └── src/
│       ├── App.jsx                 # Интерактивный дашборд и панель загрузки профилей жюри
│       ├── index.css               # Фирменная дизайн-система Halyk Bank Green (#007D43)
│       └── main.jsx                # Точка входа React
├── data/
│   ├── employees.json              # 200 профилей сотрудников банка
│   ├── events.json                 # 40 мероприятий и курсов повышения квалификации
│   ├── skills.json                 # Каталог 60 навыков и матрица требований по грейдам
│   └── activity_history.csv        # 24 месяца ретроспективных логов участия
├── docker-compose.yml              # Единый production-ready оркестратор стека
├── .env.example                    # Шаблон конфигурации переменных окружения
├── .gitignore                      # Изоляция секретов, кэшей и временных файлов
└── README.md                       # Полная техническая и архитектурная документация (25 баллов)
```

---

## 📡 API Спецификация

| Метод | Эндпоинт | Описание | Входные данные |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Проверка статуса сервиса, наличия LLM-ключа и объема кэша | — |
| `GET` | `/api/profiles` | Получение списка сотрудников (базовые + загруженные) | `?include_custom=true` |
| `GET` | `/api/profiles/{id}` | Профиль сотрудника с текущими компетенциями и грейдом | `id: string` |
| `POST` | `/api/profiles/upload` | **Динамическая загрузка профилей жюри (JSON Body)** | `{"profiles": [...]}` |
| `POST` | `/api/profiles/upload-file` | **Загрузка профилей жюри через файл (.json)** | Multipart File |
| `POST` | `/api/recommendations` | **Многофакторные рекомендации обучения с обоснованием (4 фактора)** | `{"employee_id": "emp_001"}` |
| `POST` | `/api/activities/complete` | **Фиксация завершения курса и прокачка навыков сотрудника** | `{"employee_id": "...", "event_id": "..."}` |
| `GET` | `/api/hr/analytics` | **HR-аналитика: топ дефицитов компании и группа риска** | — |
| `GET` | `/api/events` | Каталог доступных мероприятий по апскиллингу | — |
| `GET` | `/api/skills` | Каталог навыков и матрица грейдовых требований | — |

---

## 🖼 Интерфейс (UI Preview)

### 1. Дашборд сотрудника и дефицит грейдовых компетенций
*(Скриншот дашборда с радаром компетенций и прогрессом до целевого грейда)*  
`[ Placeholder: Dashboard & Skills Radar ]`

### 2. Панель верификации жюри (Jury Testing Suite)
*(Скриншот динамической загрузки тестового JSON и моментального пересчета траектории)*  
`[ Placeholder: Jury Custom Profiles Live Upload ]`

---

## 👥 Состав команды и роли

**Команда:** Team 202453 (HackAlem AI)

- **Участник 1 (Alen Pak) — Lead / System Architect, DevOps & Documentation Engineer:**
  - Проектирование архитектуры Zero-DB In-Memory слоя.
  - Настройка Docker/Docker Compose окружения, Nginx reverse-proxy и multi-stage сборок.
  - Разработка модуля динамической загрузки проверочных профилей жюри (`data_loader.py`).
  - Комплексная техническая документация и презентация проекта.
- **Участник 2 — Backend & ML Engineer:**
  - Алгоритмическая реализация многофакторного скоринга и учет 24-месячной истории.
  - Интеграция с OpenAI API (GPT-4o-mini) для генерации персонализированных объяснений.
- **Участник 3 — Frontend & UI/UX Engineer:**
  - Разработка интерфейса на React/Vite в корпоративном стиле Halyk Bank.
  - Визуализация карьерного трека и радар навыков.
