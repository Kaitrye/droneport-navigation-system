# Интеграция с Дронопортом

Документ фиксирует контракт обмена между `RobotSystem` (НУС) и внешним сервисом Дронопорта.

Связанная диаграмма: `S2_DronePort_Interaction.puml`.

## 1. Цель интеграции

- Подготовка БВС к миссии (резервирование, preflight, зарядка).
- Поддержка запуска/посадки и приёма в штатном и аварийном режимах.
- Передача статусов инфраструктуры в НУС.

## 2. Роли

- **НУС / RobotSystem** — оркестрирует команды в сторону Дронопорта.
- **Дронопорт** — исполняет операции хранения/зарядки/выдачи/приёма БВС.
- **OrchestratorSystem** — принимает итоговые статусы готовности ресурсов.

## 3. Команды НУС -> Дронопорт

### 3.1 `reserve_slots`

Назначение: резервирование ячеек/ресурсов под окно миссии.

**Request (пример):**
```json
{
  "message_id": "uuid",
  "timestamp": "2026-02-27T12:00:00Z",
  "mission_id": "m-123",
  "drone_ids": ["d-01", "d-02"],
  "mission_window": {
    "start": "2026-02-27T12:10:00Z",
    "end": "2026-02-27T13:00:00Z"
  }
}
```

**Response:** `reserved` | `rejected` (+ `reason`).

### 3.2 `preflight_check`

Назначение: пред-полётная проверка БВС.

**Response:** `preflight.ok` | `preflight.failed` (+ список причин).

### 3.3 `charge_to_threshold`

Назначение: довести заряд до порога.

**Response:** `charge.completed` | `charge.timeout` | `failed`.

### 3.4 `release_for_takeoff`

Назначение: выдать БВС к взлёту/подтвердить готовность коридора.

**Response:** `release_ack` | `failed`.

### 3.5 `request_landing_slot`

Назначение: запрос слота на посадку/приём.

**Response:** `slot_assigned` | `denied`.

### 3.6 `dock`

Назначение: постановка БВС в док.

**Response:** `docked` | `failed`.

### 3.7 Пост-посадочная обработка (внутренняя логика Дронопорта)

После успешного `dock` Дронопорт самостоятельно:
- выполняет диагностику БВС;
- принимает решение о необходимости зарядки;
- при необходимости запускает зарядку без отдельной внешней команды.

Рекомендуемые статусные ответы/события в сторону НУС:
- `diagnostics.ok` | `diagnostics.failed`
- `charging.started` | `charging.not_required`

### 3.8 `emergency_receive`

Назначение: аварийный приём БВС.

**Response:** `emergency_ack` | `failed`.

### 3.9 `health.check`

Назначение: проверка доступности сервиса Дронопорта.

**Response:** `health.ok` | `health.degraded`.

## 4. Обратные события Дронопорта -> НУС (опционально)

Если Дронопорт поддерживает push-модель, рекомендованы события:
- `drone_port.slot.released`
- `drone_port.diagnostics.ok`
- `drone_port.diagnostics.failed`
- `drone_port.charge.completed`
- `drone_port.charge.failed`
- `drone_port.hardware.degraded`
- `drone_port.alert`

## 5. Ошибки

Единый формат:

```json
{
  "error_code": "PORT_RESOURCE_BUSY",
  "reason": "No available slot in mission window",
  "retryable": true
}
```

Минимальный набор кодов:
- `PORT_RESOURCE_BUSY`
- `PORT_PRECHECK_FAILED`
- `PORT_CHARGE_TIMEOUT`
- `PORT_DOCK_FAILED`
- `PORT_UNAVAILABLE`
- `INTERNAL_ERROR`

## 6. Нефункциональные требования

- Паттерн обмена командами: `request/response`.
- Доставка минимум `at-least-once`, идемпотентность по `message_id`.
- Корреляция запрос/ответ через `correlation_id`.
- Безопасность: TLS, для production желательно mTLS.
- Таймауты команд и retry policy согласуются отдельно (по SLA Дронопорта).

## 7. Таблица согласования

| Направление | Сообщение | Паттерн | Обязательный ответ |
|---|---|---|---|
| НУС -> Дронопорт | `reserve_slots` | request/response | `reserved` или `rejected` |
| НУС -> Дронопорт | `preflight_check` | request/response | `preflight.ok` или `preflight.failed` |
| НУС -> Дронопорт | `charge_to_threshold` | request/response | `charge.completed` или `charge.timeout` |
| НУС -> Дронопорт | `release_for_takeoff` | request/response | `release_ack` |
| НУС -> Дронопорт | `request_landing_slot` | request/response | `slot_assigned` или `denied` |
| НУС -> Дронопорт | `dock` | request/response | `docked` |
| Дронопорт -> НУС | `diagnostics.ok/failed` | status event | не требуется |
| Дронопорт -> НУС | `charging.started/not_required` | status event | не требуется |
| НУС -> Дронопорт | `emergency_receive` | request/response | `emergency_ack` |
| НУС -> Дронопорт | `health.check` | request/response | `health.ok` или `health.degraded` |
