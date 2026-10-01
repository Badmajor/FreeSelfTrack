# FreeSelfTrack

**FreeSelfTrack** — бесплатный self-hosted трекер задач для команд и небольших организаций.

Проект позволяет развернуть собственный сервис управления задачами на своём сервере и хранить данные самостоятельно, без обязательной зависимости от облачного сервиса.

> **Статус проекта:** early development / MVP

## Оглавление

- [Возможности](#возможности)
- [Почему self-hosted](#почему-self-hosted)
- [Быстрый запуск](#быстрый-запуск)
- [1. Что потребуется](#1-что-потребуется)
- [2. Установка Docker](#2-установка-docker)
- [3. Скачать FreeSelfTrack](#3-скачать-freeselftrack)
- [4. Настройка конфигурации](#4-настройка-конфигурации)
- [Подключение SMTP](#подключение-smtp)
- [5. Запуск](#5-запуск)
- [6. Открыть приложение](#6-открыть-приложение)
- [7. Первый вход](#7-первый-вход)
- [Архитектура](#архитектура)
- [Данные](#данные)
- [Остановка](#остановка)
- [Полное удаление вместе с данными](#полное-удаление-вместе-с-данными)
- [Обновление](#обновление)
- [Просмотр логов](#просмотр-логов)
- [Проверка работоспособности](#проверка-работоспособности)
- [Использование собственного домена](#использование-собственного-домена)
- [Пример с Nginx](#пример-с-nginx)
- [Безопасность](#безопасность)
- [Резервное копирование](#резервное-копирование)
- [Изменение порта](#изменение-порта)
- [Локальный запуск для разработчиков](#локальный-запуск-для-разработчиков)
- [Технологии](#технологии)
- [Структура проекта](#структура-проекта)
- [API](#api)
- [Ограничения текущей версии](#ограничения-текущей-версии)
- [Устранение проблем](#устранение-проблем)
- [Удаление FreeSelfTrack](#удаление-freeselftrack)
- [Разработка](#разработка)
- [Лицензия](#лицензия)
- [Автор](#автор)
- [Обратная связь](#обратная-связь)

## Возможности

FreeSelfTrack предназначен для управления проектами, задачами и рабочими процессами команды.

Основные возможности:

* регистрация с подтверждением email через SMTP и авторизация пользователей;
* организации;
* участники организаций;
* проекты;
* участники проектов;
* собственные статусы для каждого проекта;
* Kanban-доски;
* изменение порядка статусов;
* задачи;
* исполнители;
* приоритеты;
* сроки выполнения;
* комментарии;
* упоминания пользователей;
* наблюдатели задач;
* уведомления;
* история изменений задач;
* вложения к комментариям;
* поиск и работа с задачами;
* восстановление удалённых организаций и проектов;
* фоновая обработка уведомлений о сроках.

### Kanban

Каждый проект может иметь собственный набор статусов.

Например:

```text
Backlog → To Do → In Progress → Review → Testing → Done
```

Статусы не являются глобальными: разные проекты могут использовать разные рабочие процессы.

---

# Почему self-hosted

FreeSelfTrack можно установить на собственный сервер.

Это позволяет:

* самостоятельно контролировать данные;
* не зависеть от SaaS-провайдера;
* использовать собственный домен;
* размещать систему во внутренней сети;
* самостоятельно выполнять резервное копирование;
* изменять исходный код под свои требования.

FreeSelfTrack не требует отдельной регистрации в стороннем облачном сервисе для работы самого приложения.

---

# Быстрый запуск

Самый простой способ запуска — Docker Compose.

Для обычного пользователя серверной системы не требуется устанавливать Python, Node.js, PostgreSQL или Redis отдельно.

Для запуска контейнеров нужен Docker с поддержкой Compose. Для регистрации новых пользователей также необходим доступный SMTP-сервер: собственный или сервер вашего почтового провайдера.

## 1. Что потребуется

Минимально:

* Linux-сервер;
* Docker;
* Docker Compose;
* доступ к серверу по SSH;
* открытый TCP-порт для веб-интерфейса;
* SMTP-сервер и параметры подключения для отправки писем подтверждения.

Для небольшой команды можно начать примерно с:

* 2 CPU;
* 2–4 GB RAM;
* 10+ GB свободного диска.

Фактические требования зависят от количества пользователей, задач и размера вложений.

---

# 2. Установка Docker

Если Docker ещё не установлен, установите Docker Engine и Docker Compose согласно официальной документации Docker.

Проверьте установку:

```bash
docker --version
docker compose version
```

Обе команды должны вернуть установленную версию.

---

# 3. Скачать FreeSelfTrack

Подключитесь к серверу по SSH.

Создайте каталог для приложения:

```bash
sudo mkdir -p /opt/freeselftrack
sudo chown "$USER":"$USER" /opt/freeselftrack
```

Перейдите в него:

```bash
cd /opt/freeselftrack
```

Склонируйте репозиторий:

```bash
git clone https://github.com/Badmajor/FreeSelfTrack.git .
```

Если Git не установлен:

```bash
sudo apt update
sudo apt install -y git
```

После этого:

```bash
git clone https://github.com/Badmajor/FreeSelfTrack.git .
```

---

# 4. Настройка конфигурации

В корне проекта находится файл `.env.example`.

Создайте рабочий `.env`:

```bash
cp .env.example .env
```

Откройте его:

```bash
nano .env
```

Минимально необходимо изменить пароли и секретный ключ, настроить SMTP и указать публичный адрес приложения в `PUBLIC_APP_URL`.

Пример:

```env
POSTGRES_DB=tracker
POSTGRES_USER=tracker
POSTGRES_PASSWORD=CHANGE_THIS_DATABASE_PASSWORD

POSTGRES_BIND_ADDRESS=127.0.0.1
POSTGRES_PORT=5431

TRACKER_DATABASE_URL=postgresql+asyncpg://tracker:CHANGE_THIS_DATABASE_PASSWORD@db:5432/tracker

AUTH_SECRET_KEY=CHANGE_THIS_TO_A_LONG_RANDOM_SECRET

DEADLINE_WORKER_INTERVAL_SECONDS=60

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=CHANGE_THIS_MINIO_PASSWORD

FRONTEND_BIND_ADDRESS=0.0.0.0
FRONTEND_PORT=5173

PUBLIC_APP_URL=http://localhost:5173
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=YOUR_SMTP_USERNAME
SMTP_PASSWORD=YOUR_SMTP_PASSWORD
SMTP_SENDER=noreply@example.com
```

## Подключение SMTP

Новые учётные записи создаются только после подтверждения email. Без работающего SMTP регистрацию завершить нельзя; ранее созданные пользователи могут входить как прежде. Почтовый сервер не входит в Compose: укажите свой сервер или параметры почтового провайдера.

| Переменная | Что указать |
| --- | --- |
| `PUBLIC_APP_URL` | Адрес frontend, доступный пользователям: например, `https://tasks.example.com` или `http://SERVER_IP:5173`. Он используется в ссылках подтверждения. `localhost` подходит только для локального запуска. |
| `SMTP_HOST` | Имя или адрес SMTP-сервера, доступного из контейнера. `localhost` внутри worker указывает на сам контейнер. |
| `SMTP_PORT` | Порт SMTP: обычно `587` для STARTTLS или `465` для TLS. |
| `SMTP_SECURITY` | `starttls` для STARTTLS или `tls` для TLS с начала соединения. `plain` предназначен только для изолированного локального тестового сервера. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Данные подключения, выданные почтовым провайдером; при необходимости используйте пароль приложения. Для сервера без авторизации оставьте оба значения пустыми. |
| `SMTP_SENDER` | Email отправителя, разрешённый вашим SMTP-сервером. |

Замените значения-примеры в `.env` на свои. Режимы `starttls` и `tls` проверяют сертификат сервера. Не публикуйте `.env` с почтовыми реквизитами.

Compose автоматически запускает `registration-mail-worker`, который отправляет письма из очереди PostgreSQL и повторяет попытки при сбоях. После изменения `.env` примените настройки командой `docker compose up -d`. Если ссылка не открывает ваш экземпляр приложения, проверьте `PUBLIC_APP_URL` и запросите новое письмо повторной регистрацией.

## Важно

Не используйте стандартные пароли из примеров на сервере, доступном из интернета.

Особенно важно изменить:

```env
POSTGRES_PASSWORD
AUTH_SECRET_KEY
MINIO_ROOT_PASSWORD
```

`AUTH_SECRET_KEY` должен быть длинным случайным значением.

Например, его можно сгенерировать:

```bash
openssl rand -hex 32
```

Результат можно использовать как:

```env
AUTH_SECRET_KEY=полученное_значение
```

---

# 5. Запуск

После настройки `.env` выполните:

```bash
docker compose up -d --build
```

Docker скачает необходимые базовые образы и соберёт контейнеры приложения.

Посмотреть состояние контейнеров:

```bash
docker compose ps
```

Все основные сервисы должны перейти в состояние `running` / `healthy`.

---

# 6. Открыть приложение

По умолчанию веб-интерфейс доступен на порту `5173`.

Если приложение запущено непосредственно на вашем компьютере:

```text
http://localhost:5173
```

Если приложение установлено на сервере:

```text
http://SERVER_IP:5173
```

Например:

```text
http://192.168.1.100:5173
```

или:

```text
http://203.0.113.10:5173
```

где `203.0.113.10` — IP-адрес вашего сервера.

---

# 7. Первый вход

Откройте FreeSelfTrack в браузере.

1. Заполните форму регистрации, указав доступный вам email и пароль длиной от 12 символов.
2. Откройте письмо подтверждения и перейдите по ссылке.
3. Введите пароль, выбранный при регистрации, и подтвердите email. Сам переход по ссылке учётную запись не создаёт.
4. Войдите с вашим email и паролем.

Ссылка действует один час по умолчанию и используется один раз. Если она истекла, отправьте форму регистрации повторно. Приложение показывает одинаковое сообщение для нового и уже зарегистрированного email; существующая учётная запись при этом не изменяется.

После подтверждения email и входа можно создать организацию:

```text
Организация
    ↓
Проект
    ↓
Статусы
    ↓
Задачи
```

Например:

```text
Моя компания

    Проект: Разработка сайта

        Backlog
        To Do
        In Progress
        Review
        Done

            TASK-1
            TASK-2
            TASK-3
```

---

# Архитектура

При стандартном запуске Docker Compose запускает несколько контейнеров.

```text
                         Интернет
                             │
                             ▼
                    ┌─────────────────┐
                    │    Frontend     │
                    │     nginx       │
                    │     :5173       │
                    └────────┬────────┘
                             │
                             │ /api/*
                             ▼
                    ┌─────────────────┐
                    │     Backend     │
                    │     FastAPI     │
                    │      :8000      │
                    └───────┬─┬───────┘
                            │ │
                ┌───────────┘ └───────────┐
                ▼                         ▼
        ┌──────────────┐          ┌──────────────┐
        │  PostgreSQL  │          │    Redis     │
        │     :5432    │          │     :6379    │
        └──────────────┘          └──────────────┘
```

Также в Compose присутствует MinIO для дальнейшего использования объектного хранилища.

## Сервисы

### Frontend

React-приложение, которое собирается в статические файлы и обслуживается nginx.

### Backend

API на FastAPI.

Backend отвечает за:

* пользователей;
* организации;
* проекты;
* задачи;
* статусы;
* комментарии;
* уведомления;
* историю изменений;
* авторизацию.

### PostgreSQL

Основная база данных приложения.

### Redis

Используется приложением для вспомогательных задач и фоновой работы.

### Deadline Worker

Отдельный контейнер, который периодически проверяет сроки задач и создаёт соответствующие уведомления.

### Registration Mail Worker

Контейнер `registration-mail-worker` отправляет письма подтверждения через настроенный SMTP-сервер. Очередь, срок действия заявок и состояние доставки хранятся в PostgreSQL. При временном сбое отправка повторяется до истечения срока заявки.

---

# Данные

Docker Compose использует именованные Docker volumes.

Основные данные хранятся в:

```text
postgres_data
redis_data
minio_data
```

Проверить volumes:

```bash
docker volume ls
```

Остановка контейнеров **не удаляет эти данные**:

```bash
docker compose down
```

После повторного запуска:

```bash
docker compose up -d
```

данные должны остаться.

---

# Остановка

Чтобы остановить приложение:

```bash
docker compose down
```

Это остановит и удалит контейнеры, но не удалит Docker volumes.

Для повторного запуска:

```bash
docker compose up -d
```

---

# Полное удаление вместе с данными

Если необходимо удалить приложение вместе с его данными:

```bash
docker compose down -v
```

> **Внимание:** команда `down -v` удалит volumes, содержащие данные PostgreSQL и других сервисов.

Не выполняйте эту команду, если хотите сохранить данные.

---

# Обновление

Чтобы обновить FreeSelfTrack до последней версии:

```bash
cd /opt/freeselftrack
```

Получите изменения:

```bash
git pull
```

Пересоберите контейнеры:

```bash
docker compose up -d --build
```

Проверить состояние:

```bash
docker compose ps
```

При запуске backend автоматически выполняет миграции базы данных:

```text
alembic upgrade head
```

Поэтому при обновлении версии приложения новые миграции применяются автоматически.

---

# Просмотр логов

Посмотреть логи всех сервисов:

```bash
docker compose logs
```

Следить за логами в реальном времени:

```bash
docker compose logs -f
```

Только backend:

```bash
docker compose logs -f backend
```

Только frontend:

```bash
docker compose logs -f frontend
```

Worker уведомлений о сроках:

```bash
docker compose logs -f deadline-worker
```

Worker отправки писем:

```bash
docker compose logs -f registration-mail-worker
```

Последние 100 строк backend:

```bash
docker compose logs --tail=100 backend
```

---

# Проверка работоспособности

Backend имеет health endpoint:

```text
/api/health
```

Внутренний health endpoint:

```text
/health
```

Проверить backend внутри контейнера:

```bash
docker compose exec backend \
  python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
```

Ожидаемый результат:

```text
{"status":"ok"}
```

Frontend также имеет endpoint:

```text
/health
```

Проверить его:

```bash
curl http://localhost:5173/health
```

Ожидаемый результат:

```text
ok
```

---

# Использование собственного домена

Для постоянного использования рекомендуется не публиковать приложение напрямую через порт `5173`, а поставить перед ним reverse proxy.

Например:

```text
https://tasks.example.com
            │
            ▼
       Reverse Proxy
            │
            ▼
    FreeSelfTrack :5173
```

В качестве reverse proxy можно использовать:

* Nginx;
* Caddy;
* Traefik.

Это позволит использовать:

* HTTPS;
* собственный домен;
* автоматическое получение TLS-сертификата;
* стандартный порт `443`.

---

# Пример с Nginx

Предположим, домен:

```text
tasks.example.com
```

FreeSelfTrack продолжает работать на:

```text
127.0.0.1:5173
```

Nginx принимает внешние подключения:

```text
https://tasks.example.com
```

и передаёт их FreeSelfTrack.

Пример конфигурации:

```nginx
server {
    listen 80;
    server_name tasks.example.com;

    location / {
        proxy_pass http://127.0.0.1:5173;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

После этого для HTTPS можно использовать Let's Encrypt и Certbot.

При переходе на домен обновите `PUBLIC_APP_URL` в `.env`, например на `https://tasks.example.com`, и выполните `docker compose up -d`, чтобы новые письма содержали правильные ссылки.

> Если вы не работали с Nginx, HTTPS или DNS раньше, сначала рекомендуется запустить FreeSelfTrack через `http://SERVER_IP:5173` и только после успешного запуска подключать домен.

---

# Безопасность

Если FreeSelfTrack доступен из интернета, рекомендуется:

1. использовать сильный пароль PostgreSQL;
2. использовать случайный `AUTH_SECRET_KEY`;
3. не публиковать PostgreSQL наружу;
4. не публиковать Redis наружу;
5. использовать HTTPS;
6. регулярно создавать резервные копии;
7. регулярно обновлять Docker images и сам FreeSelfTrack;
8. ограничить доступ к серверу через firewall.

PostgreSQL в стандартной конфигурации привязан к:

```text
127.0.0.1
```

поэтому он не должен быть доступен непосредственно из интернета.

Redis также не публикуется наружу.

---

# Резервное копирование

Основные данные FreeSelfTrack находятся в PostgreSQL.

Рекомендуется регулярно создавать резервную копию базы данных.

Узнать имя контейнера:

```bash
docker compose ps
```

Создать SQL-дамп:

```bash
docker compose exec -T db \
  pg_dump -U tracker tracker > freeselftrack-backup.sql
```

Для восстановления базы данных:

```bash
cat freeselftrack-backup.sql | \
  docker compose exec -T db \
  psql -U tracker tracker
```

> Перед восстановлением базы данных рекомендуется остановить backend и оба worker, чтобы приложение не изменяло данные во время восстановления.

Например:

```bash
docker compose stop backend deadline-worker registration-mail-worker
```

После восстановления:

```bash
docker compose start backend deadline-worker registration-mail-worker
```

---

# Изменение порта

По умолчанию frontend доступен на:

```text
5173
```

Если порт `5173` уже используется, измените:

```env
FRONTEND_PORT=8080
PUBLIC_APP_URL=http://SERVER_IP:8080
```

Если пользователи открывают приложение через HTTPS-домен, сохраните в `PUBLIC_APP_URL` этот публичный адрес.

После этого:

```bash
docker compose up -d
```

Приложение будет доступно на:

```text
http://SERVER_IP:8080
```

---

# Локальный запуск для разработчиков

Если вы хотите не просто установить FreeSelfTrack, а разрабатывать его, можно запускать frontend и backend отдельно.

## Backend

Требуется:

* Python 3.13+;
* PostgreSQL;
* Redis;
* SMTP-сервер или локальный тестовый приёмник писем для регистрации.

В каталоге backend используется `uv`.

После установки `uv`:

```bash
cd backend
uv sync
```

Запуск:

```bash
uv run uvicorn app.main:app --reload
```

Backend будет доступен на:

```text
http://localhost:8000
```

Документация FastAPI:

```text
http://localhost:8000/docs
```

### Отправка писем при локальной разработке

Для прямого запуска Python используйте переменные окружения с префиксом `TRACKER_`: `TRACKER_SMTP_HOST`, `TRACKER_SMTP_PORT`, `TRACKER_SMTP_SECURITY`, `TRACKER_SMTP_USERNAME`, `TRACKER_SMTP_PASSWORD`, `TRACKER_SMTP_SENDER` и `TRACKER_PUBLIC_APP_URL`. Их также можно задать в `backend/.env`; корневой `.env` используется Docker Compose.

В отдельном терминале из каталога `backend/` запустите:

```bash
uv run python -m app.workers.registration_mail
```

У API и worker должны совпадать `TRACKER_DATABASE_URL` и `TRACKER_AUTH_SECRET_KEY`. Для Vite по умолчанию укажите `TRACKER_PUBLIC_APP_URL=http://localhost:5173`.

## Frontend

Требуется Node.js.

Установка зависимостей:

```bash
cd frontend
npm ci
```

Запуск:

```bash
npm run dev
```

После этого Vite сообщит адрес локального frontend.

---

# Технологии

## Backend

* Python 3.13;
* FastAPI;
* SQLAlchemy;
* Alembic;
* PostgreSQL;
* Redis;
* Pydantic;
* JWT;
* Uvicorn.

## Frontend

* React;
* TypeScript;
* Vite;
* React Router;
* TanStack Query;
* nginx.

## Deployment

* Docker;
* Docker Compose.

---

# Структура проекта

Основные каталоги:

```text
FreeSelfTrack/
│
├── backend/
│   ├── app/
│   ├── alembic/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── package-lock.json
│
├── docker-compose.yml
├── .env.example
├── whitepaper.md
├── LICENSE
└── NOTICE
```

---

# API

Backend предоставляет REST API.

После запуска в режиме разработки документация FastAPI доступна по адресу:

```text
http://localhost:8000/docs
```

OpenAPI-схема:

```text
http://localhost:8000/openapi.json
```

При production-развёртывании backend по умолчанию не публикуется напрямую наружу: запросы к `/api/*` проходят через frontend nginx.

---

# Ограничения текущей версии

FreeSelfTrack находится в активной разработке.

Некоторые возможности могут быть реализованы частично или изменяться между версиями.

В частности, перед использованием в критически важной рабочей среде рекомендуется:

* протестировать резервное копирование и восстановление;
* настроить HTTPS;
* проверить ограничения доступа пользователей;
* настроить мониторинг;
* определить процедуру обновления;
* регулярно создавать резервные копии.

---

# Устранение проблем

## Не приходит письмо подтверждения

Проверьте worker и его логи:

```bash
docker compose ps registration-mail-worker
docker compose logs --tail=100 registration-mail-worker
```

Проверьте папку «Спам», доступность SMTP-сервера из контейнера, порт и режим шифрования, логин, пароль и разрешённый адрес отправителя. Событие `confirmation_delivery_retry` означает, что отправка будет повторена; `mail_database_unavailable` указывает на проблему доступа worker к PostgreSQL.

Ответ формы «Проверьте почту» означает, что заявка принята, а не что письмо уже доставлено. После исправления `.env` выполните `docker compose up -d`. Если часовой срок заявки истёк, повторите регистрацию; частые попытки могут временно ограничиваться. Если письмо пришло, но ссылка ведёт на неверный адрес, исправьте `PUBLIC_APP_URL`.

---

## Контейнеры не запускаются

Проверьте:

```bash
docker compose ps
```

Затем:

```bash
docker compose logs --tail=200
```

---

## Backend не запускается

Посмотрите логи:

```bash
docker compose logs --tail=200 backend
```

Часто причиной являются:

* неправильный пароль PostgreSQL;
* некорректный `TRACKER_DATABASE_URL`;
* повреждённый volume;
* ошибка миграции базы данных.

---

## Frontend не открывается

Проверьте:

```bash
docker compose ps
```

Затем:

```bash
docker compose logs --tail=200 frontend
```

Проверьте порт:

```bash
ss -lntp | grep 5173
```

Если сервер использует firewall, убедитесь, что необходимый порт разрешён.

---

## База данных не запускается

Проверьте:

```bash
docker compose logs --tail=200 db
```

Проверить состояние:

```bash
docker compose ps db
```

---

## Приложение перестало работать после обновления

Сначала посмотрите логи:

```bash
docker compose logs --tail=200 backend
```

Если проблема связана с миграциями, **не удаляйте PostgreSQL volume сразу**.

Удаление volume может привести к потере всех данных.

Сначала сохраните резервную копию базы данных.

---

# Удаление FreeSelfTrack

Чтобы удалить контейнеры:

```bash
docker compose down
```

Чтобы удалить контейнеры и данные:

```bash
docker compose down -v
```

Перед использованием второго варианта обязательно убедитесь, что резервная копия данных больше не нужна.

---

# Разработка

Если вы хотите принять участие в разработке FreeSelfTrack:

1. создайте fork репозитория;
2. создайте отдельную ветку;
3. внесите изменения;
4. добавьте тесты для нового функционала;
5. проверьте backend и frontend;
6. создайте Pull Request.

Исходный код проекта:

[GitHub — Badmajor/FreeSelfTrack](https://github.com/Badmajor/FreeSelfTrack?utm_source=chatgpt.com)

---

# Лицензия

FreeSelfTrack распространяется по **FreeSelfTrack Attribution License 1.0 (FSTAL-1.0)**.

Разрешается:

* использовать FreeSelfTrack;
* использовать его коммерчески;
* устанавливать его на собственный сервер;
* изменять исходный код;
* создавать производные проекты;
* распространять оригинальную или изменённую версию;
* предоставлять платный hosting;
* предоставлять услуги установки;
* предоставлять услуги поддержки и кастомизации.

При распространении FreeSelfTrack или производной версии необходимо сохранить указание на оригинальный проект:

> **FreeSelfTrack by Viktor Balonkin**
> https://github.com/Badmajor/FreeSelfTrack

Подробнее:

* [`LICENSE`](LICENSE)
* [`NOTICE`](NOTICE)

Сторонние библиотеки, фреймворки, Docker images и другие компоненты распространяются в соответствии с их собственными лицензиями.

---

# Автор

**Viktor Balonkin**

Original project:

[https://github.com/Badmajor/FreeSelfTrack](https://github.com/Badmajor/FreeSelfTrack?utm_source=chatgpt.com)

---

# Обратная связь

Если вы нашли ошибку или хотите предложить улучшение, создайте Issue в репозитории проекта.

[Issues — FreeSelfTrack](https://github.com/Badmajor/FreeSelfTrack/issues?utm_source=chatgpt.com)
