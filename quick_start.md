# Docker

Развертывание брокеров и DummySystem в Docker.

## Быстрый старт (необходимо наличие docker и pipenv в системе)

```bash
cp docker/example.env docker/.env #(BROKER_TYPE=mqtt/kafka)
make docker-build
make docker-up
make docker-ps
```

## Архитектура

```
┌─────────────────────────────────────────────────────┐
│                 Docker Network: drones_net           │
│                                                      │
│  ┌─────────────┐  ┌─────────────┐                    │
│  │    Kafka    │  │  Mosquitto  │  (профиль kafka    │
│  │   :9092     │  │   :1883     │   или mqtt)        │
│  └─────────────┘  └─────────────┘                    │
│         │                  │                         │
│         └────────┬─────────┘                         │
│                  │                                   │
│  ┌───────────────┴───────────────┐                   │
│  │                               │                   │
│  │  dummy_system_a   dummy_system_b                  │
│  │      :9700             :9701                      │
│  │  (SystemBus: systems.dummy)                       │
│  └───────────────────────────────┘                   │
└─────────────────────────────────────────────────────┘
```

## Сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| kafka | 9092 | Брокер сообщений (профиль kafka) |
| mosquitto | 1883 | MQTT брокер (профиль mqtt) |
| dummy_system_a | 9700 | DummySystem (echo, process) |
| dummy_system_b | 9701 | DummySystem |

## Команды

```bash
make docker-build   # Собрать образы
make docker-up      # Запустить (BROKER_TYPE=kafka или mqtt)
make docker-down    # Остановить
make docker-logs    # Логи
make docker-ps      # Статус
make docker-clean   # Остановить + удалить образы
```

## Конфигурация (.env)

```bash
cp docker/example.env docker/.env
```

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| BROKER_TYPE | kafka или mqtt | kafka |
| KAFKA_PORT | Порт Kafka | 9092 |
| MQTT_PORT | Порт MQTT | 1883 |
| DUMMY_PORT_A | Health порт dummy_system_a | 9700 |
| DUMMY_PORT_B | Health порт dummy_system_b | 9701 |
| DUMMY_USER_A | SASL/MQTT пользователь dummy_system_a | dummy_a |
| DUMMY_PASSWORD_A | | |
| DUMMY_USER_B | SASL/MQTT пользователь dummy_system_b | dummy_b |
| DUMMY_PASSWORD_B | | |
| ADMIN_USER | Для тестов (BROKER_USER) | admin |
| ADMIN_PASSWORD | | |

## Аутентификация

- **Kafka:** SASL PLAIN, JAAS (ADMIN_USER, DUMMY_USER_A, DUMMY_USER_B)
- **MQTT:** allow_anonymous false, passwd + ACL (readwrite systems/#, replies/#, drones/#)

## Тесты

Интеграционные тесты ожидают запущенные контейнеры:

```bash
make tests #Все тесты

make unit-test #Интеграционные тесты

make e2e-test #Сквозные тесты

make integration-test #Интеграционные тесты
```

## Troubleshooting

**Контейнер не запускается:**
```bash
docker logs dummy_system_a
```

**Брокер недоступен:** убедитесь что Kafka или Mosquitto запущен (profile kafka/mqtt).

**Сервисы не видят друг друга:** внутри Docker используйте имена контейнеров (kafka, mosquitto), а не localhost.
