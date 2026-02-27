# Интеграция с внешним сервисом дронов

Документ фиксирует договорённости по обмену между `RobotSystem` (НУС) и внешним сервисом дронов.

Связанная диаграмма: `S1_DroneService_Interaction.puml`.

## 1. Роли и ответственность

- **НУС / RobotSystem** — инициирует команды управления миссией и обрабатывает ответы.
- **Внешний сервис дронов** — исполняет команды, возвращает результат и транслирует телеметрию.
- **TelemetrySystem** — принимает и нормализует телеметрию для хранения состояния.

## 2. Каналы обмена

- **Command channel (sync):** `request/response` для команд управления.
- **Telemetry channel (async):** поток телеметрии от внешнего сервиса в НУС.
- **Health channel (sync):** периодическая проверка доступности интеграции.

## 3. Команды НУС -> Внешний сервис дронов

### 3.1 `upload_mission`

Назначение: загрузка миссии на БВС.

**Request (пример):**
```json
{
  "message_id": "uuid",
  "timestamp": "2026-02-27T12:00:00Z",
  "mission_id": "m-123",
  "drone_id": "d-01",
  "route": {
    "wpl": "...",
    "waypoints": []
  }
}
```

**Response:** `accepted` | `rejected` (+ `reason`).

### 3.2 `arm`

Назначение: перевод БВС в состояние готовности к взлёту.

**Response:** `armed` | `failed` (+ `error_code`, `reason`).

### 3.3 `takeoff`

Назначение: команда на взлёт.

**Response:** `in_air` | `failed`.

### 3.4 `land`

Назначение: команда на посадку.

**Response:** `completed` | `failed`.

### 3.5 `return_to_base`

Назначение: возврат БВС на базу/в дронопорт.

**Response:** `completed` | `failed`.

### 3.6 `abort`

Назначение: аварийное прерывание миссии.

**Response:** `abort_ack` | `failed`.

## 4. События Внешний сервис дронов -> НУС

### 4.1 `telemetry.update`

Частота: ориентир `200-1000 мс` (настраиваемо).

**Payload (минимум):**
```json
{
  "timestamp": "2026-02-27T12:00:00Z",
  "drone_id": "d-01",
  "mission_id": "m-123",
  "position": { "lat": 0.0, "lon": 0.0, "alt": 0.0 },
  "battery": 82,
  "status": "in_air",
  "velocity": 12.4
}
```

### 4.2 Системные статусы

- `health.ok`
- `health.degraded`

## 5. Проверка доступности

### 5.1 `health.check`

- Инициатор: `RobotSystem`.
- Тип: `request/response`.
- Ответ: `health.ok` или `health.degraded`.

## 6. Ошибки и коды

Рекомендуется единый формат ошибки:

```json
{
  "error_code": "DRONE_TIMEOUT",
  "reason": "No response from drone service within timeout",
  "retryable": true
}
```

Минимальный набор кодов:
- `VALIDATION_ERROR`
- `DRONE_NOT_AVAILABLE`
- `MISSION_REJECTED`
- `COMMAND_TIMEOUT`
- `INTERNAL_ERROR`

## 7. Нефункциональные требования

- Доставка команд: минимум `at-least-once`.
- Идемпотентность по `message_id`.
- Корреляция запроса/ответа через `correlation_id`.
- Шифрование канала: TLS (для production желательно mTLS).
- Таймауты и retry policy должны быть согласованы отдельно.

## 8. Таблица для согласования

| Направление | Сообщение | Паттерн | Обязательный ответ |
|---|---|---|---|
| НУС -> Drone Service | `upload_mission` | request/response | `accepted` или `rejected` |
| НУС -> Drone Service | `arm` | request/response | `armed` или `failed` |
| НУС -> Drone Service | `takeoff` | request/response | `in_air` или `failed` |
| НУС -> Drone Service | `land` | request/response | `completed` или `failed` |
| НУС -> Drone Service | `return_to_base` | request/response | `completed` или `failed` |
| НУС -> Drone Service | `abort` | request/response | `abort_ack` или `failed` |
| Drone Service -> НУС | `telemetry.update` | async event stream | не требуется |
| НУС -> Drone Service | `health.check` | request/response | `health.ok` или `health.degraded` |
