# Balancer Lab App

Учебное stateless-веб-приложение для демонстрации reverse proxy, L4/L7-балансировки, DNS-балансировки, TLS/SSL-терминации и асинхронной обработки запросов.

Проект разработан так, чтобы одновременно запускать два и более идентичных backend-экземпляра и распределять запросы между ними через балансировщик.

## Что реализовано

- два идентичных backend-экземпляра `backend-1` и `backend-2`;
- идентификация backend-ноды в теле ответа и HTTP-заголовках;
- асинхронная обработка запросов;
- health-check endpoints;
- L7 HTTP/HTTPS-балансировка через Nginx;
- L4 TCP-балансировка через `nginx stream`;
- TLS/SSL termination только на Nginx;
- DNS round-robin через BIND9;
- отсутствие локальных пользовательских сессий;
- отсутствие локального пользовательского хранилища;
- возможность продолжить обслуживание запросов после отказа одной backend-ноды.

---

## Архитектура

В демонстрационном окружении использовались две Ubuntu Server VM в VMware:

```text
VM1: 192.168.52.136
VM2: 192.168.52.137
```

DNS-имя приложения:

```text
app.lab.test
```

Для него настроены две A-записи:

```text
app.lab.test -> 192.168.52.136
app.lab.test -> 192.168.52.137
```

Общая схема:

```text
                         app.lab.test
                              |
                       DNS round-robin
                         /          \
                        /            \
             192.168.52.136      192.168.52.137
                    |                  |
                  Nginx              Nginx
             TLS / L7 / L4      TLS / L7 / L4
                 /   \              /   \
                /     \            /     \
       backend-1   backend-2  backend-1  backend-2
```

На каждой VM backend запускается через Docker Compose:

```text
127.0.0.1:8001 -> backend-1
127.0.0.1:8002 -> backend-2
```

Nginx предоставляет:

```text
:80    -> HTTP, redirect на HTTPS
:443   -> HTTPS + L7 balancing
:9000  -> L4 TCP balancing
```

> IP-адреса выше относятся к демонстрационному окружению. При повторном развёртывании их нужно заменить на актуальные адреса виртуальных машин.

---

## Почему приложение stateless

В проекте отсутствуют:

- пользовательские сессии;
- SQLite и другие локальные БД;
- локальные файлы с пользовательским состоянием;
- данные, необходимые другой backend-ноде для обработки следующего запроса.

Поэтому запрос пользователя может попасть сначала на `backend-1`, а следующий — на `backend-2`, без нарушения логики приложения.

```text
                    Nginx
                      |
             +--------+--------+
             |                 |
         backend-1         backend-2
```

При остановке одного backend оставшийся экземпляр продолжает обслуживать запросы.

Если в будущем приложение будет расширено и появится бизнес-хранилище, оно должно быть вынесено во внешний отказоустойчивый сервис, например PostgreSQL/Redis, а не храниться локально внутри backend-контейнеров.

---

## Эндпоинты

### `GET /`

Веб-интерфейс для демонстрации текущей backend-ноды, health checks и распределения параллельных запросов.

### `GET /api/backend-info`

Возвращает сведения об экземпляре, обработавшем запрос:

```json
{
  "instance_id": "backend-1",
  "hostname": "91a02a527980",
  "pid": 1,
  "request_id": "b8320fec-437d-4361-8787-dbf3cd9c68f7",
  "started_at": "2026-09-19T10:52:16.698861+00:00",
  "uptime_seconds": 329.892,
  "server_time": "2026-09-19T10:57:46.591185+00:00"
}
```

Также добавляются заголовки:

```text
X-Backend-Node: backend-1
X-Backend-Hostname: 91a02a527980
X-Request-ID: ...
Cache-Control: no-store
```

`pid` может быть равен `1` на обеих нодах. Это нормально: каждый Docker-контейнер использует собственное PID namespace, а Uvicorn является главным процессом контейнера. Для однозначной идентификации используются `instance_id` и `hostname`.

### `GET /api/async-work?delay_ms=500`

Демонстрация неблокирующей асинхронной обработки.

```bash
curl -k "https://app.lab.test/api/async-work?delay_ms=1000"
```

### `GET /health/live`

Liveness endpoint.

### `GET /health/ready`

Readiness endpoint.

### `GET /docs`

Swagger/OpenAPI интерфейс FastAPI.

---

## Локальный запуск backend через Docker Compose

Требования:

- Docker Engine;
- Docker Compose plugin.

Запуск:

```bash
docker compose up --build
```

Или в фоне:

```bash
docker compose up -d --build
```

Проверка контейнеров:

```bash
docker ps
```

Прямые backend-адреса:

```text
http://localhost:8001
http://localhost:8002
```

Проверка:

```bash
curl http://localhost:8001/api/backend-info
curl http://localhost:8002/api/backend-info
```

Остановка:

```bash
docker compose down
```

---

## L7-балансировка через Nginx

Пример upstream:

```nginx
upstream backend_servers {
    server 127.0.0.1:8001 max_fails=2 fail_timeout=10s;
    server 127.0.0.1:8002 max_fails=2 fail_timeout=10s;
}
```

HTTP перенаправляется на HTTPS:

```nginx
server {
    listen 80;
    server_name _;

    return 301 https://$host$request_uri;
}
```

HTTPS virtual host:

```nginx
server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/lab.crt;
    ssl_certificate_key /etc/nginx/ssl/lab.key;

    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://backend_servers;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Проверка:

```bash
for i in {1..6}; do
  curl -sk https://localhost/api/backend-info \
    | grep -o '"instance_id":"[^"]*"'
done
```

---

## TLS/SSL termination

TLS завершается исключительно на Nginx:

```text
Client
  |
  | HTTPS
  v
Nginx :443
  |
  | HTTP
  v
backend :8001 / :8002
```

Backend-контейнеры не содержат сертификатов и не запускают Uvicorn с TLS.

Проверка портов:

```bash
sudo ss -lntp | grep -E ':80 |:443 |:8001 |:8002 '
```

В демонстрационном окружении `80` и `443` принадлежат Nginx, а `8001` и `8002` опубликованы Docker.

Для лабораторной используется самоподписанный сертификат, поэтому браузер может показать предупреждение, а `curl` запускается с `-k`.

---

## L4 TCP-балансировка

Для демонстрации L4 используется модуль `nginx stream`.

```nginx
stream {
    upstream backend_tcp {
        server 127.0.0.1:8001 max_fails=2 fail_timeout=10s;
        server 127.0.0.1:8002 max_fails=2 fail_timeout=10s;
    }

    server {
        listen 9000;
        proxy_connect_timeout 3s;
        proxy_timeout 30s;
        proxy_pass backend_tcp;
    }
}
```

Проверка:

```bash
for i in {1..8}; do
  curl -s http://localhost:9000/api/backend-info \
    | grep -o '"instance_id":"[^"]*"'
done
```

При L4 Nginx работает с TCP-соединением и не принимает решение о маршрутизации на основании URI или HTTP-заголовков.

---

## DNS-балансировка

DNS-сервер — BIND9 на VM1 (`192.168.52.136`).

Зона:

```text
lab.test
```

DNS-записи:

```dns
ns  IN  A   192.168.52.136

app IN  A   192.168.52.136
app IN  A   192.168.52.137
```

Проверка:

```bash
dig @127.0.0.1 app.lab.test A +short
```

Ожидаемый ответ:

```text
192.168.52.136
192.168.52.137
```

С Windows:

```powershell
Resolve-DnsName app.lab.test -Server 192.168.52.136
```

После настройки DNS для интерфейса VMware приложение доступно:

```text
https://app.lab.test
```

DNS round-robin возвращает несколько A-записей. ОС или браузер может кэшировать выбранный адрес, поэтому смена IP не обязана происходить на каждый HTTP-запрос.

BIND9 в текущей конфигурации не является health-aware DNS failover: при полном выключении одной VM её A-запись автоматически не удаляется.

---

## Проверка отказа backend-ноды

Посмотреть контейнеры:

```bash
docker ps
```

Остановить первый backend:

```bash
docker stop balancer-lab-app-backend-1-1
```

Проверить:

```bash
for i in {1..6}; do
  curl -sk https://localhost/api/backend-info \
    | grep -o '"instance_id":"[^"]*"'
done
```

Запросы должны продолжить выполняться через `backend-2`.

Вернуть ноду:

```bash
docker start balancer-lab-app-backend-1-1
```

---

## Проверка асинхронных запросов

Откройте:

```text
https://app.lab.test
```

и нажмите **«30 параллельных запросов»**.

Страница одновременно отправит запросы на `/api/async-work` и покажет количество ответов от каждой backend-ноды.

---

## Health checks

```bash
curl -k https://app.lab.test/health/live
curl -k https://app.lab.test/health/ready
```


## Структура проекта

```text
balancer-lab-app/
├── app/
│   ├── main.py
│   └── static/
│       └── index.html
├── scripts/
│   └── demo_requests.py
├── .dockerignore
├── .gitignore
├── compose.yaml
├── Dockerfile
├── README.md
└── requirements.txt
```

## Итог

Проект демонстрирует:

- горизонтальное масштабирование backend;
- L7-балансировку;
- L4 TCP-балансировку;
- DNS round-robin;
- TLS termination на reverse proxy;
- асинхронную обработку;
- идентификацию backend-ноды;
- работу после отказа одного backend;
- stateless-архитектуру без локальных пользовательских сессий и данных.
