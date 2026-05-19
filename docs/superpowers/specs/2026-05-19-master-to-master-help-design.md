# Sprint 03 Design - Master-to-Master Help Protocol

## 1. Context and Goal

This design extends the existing Sprint 01 and Sprint 02 protocols with Master-to-Master help requests when a Master is saturated.

Baseline assumptions from previous sprints:
- Worker <-> Master heartbeat is operational.
- Task cycle (presentation, distribution, status, ACK) is operational.
- `SERVER_UUID` support exists for borrowed/remote workers.
- JSON-over-TCP messages use `\n` as delimiter.

Goal:
- Allow `MASTER_A` (saturated) to request temporary worker help from `MASTER_B`.
- Keep protocol framing and behavior consistent with prior sprints.
- Preserve traceability for concurrent requests via `REQUEST_ID`.

## 2. Protocol Rules (Global)

- Transport: TCP socket.
- Message framing: each JSON message ends with `\n`.
- Required envelope for Master-to-Master and control messages:

```json
{
  "TYPE": "MESSAGE_TYPE",
  "REQUEST_ID": "REQUEST_ID_UNICO",
  "PAYLOAD": {
    "...": "..."
  }
}
```

- All control field names and enumerated control values are uppercase.
- Parsing tolerates unknown fields.
- Missing required fields must fail in a controlled way (log + ignore message), without process crash.

## 3. Message Contracts

### 3.1 Request help (Master A -> Master B)

```json
{
  "TYPE": "REQUEST_HELP",
  "REQUEST_ID": "REQUEST_ID_UNICO",
  "PAYLOAD": {
    "MASTER_ID": "A",
    "CURRENT_LOAD": 150,
    "CAPACITY": 100,
    "WORKERS_NEEDED": 2
  }
}
```

### 3.2 Accepted response (Master B -> Master A)

Response is sent in the same socket connection and same `REQUEST_ID`.

```json
{
  "TYPE": "RESPONSE_ACCEPTED",
  "REQUEST_ID": "REQUEST_ID_UNICO",
  "PAYLOAD": {
    "WORKERS_OFFERED": 2,
    "WORKER_DETAILS": [
      { "ID": "B1", "ADDRESS": "IP:PORT_WORKER_B1" },
      { "ID": "B2", "ADDRESS": "IP:PORT_WORKER_B2" }
    ]
  }
}
```

### 3.3 Rejected response (Master B -> Master A)

Response is sent in the same socket connection and same `REQUEST_ID`.

```json
{
  "TYPE": "RESPONSE_REJECTED",
  "REQUEST_ID": "REQUEST_ID_UNICO",
  "PAYLOAD": {
    "REASON": "HIGH_LOAD"
  }
}
```

Allowed `REASON` values:
- `HIGH_LOAD`
- `NO_WORKERS_AVAILABLE`
- `REFUSED`

### 3.4 Redirect command (Master B -> Worker B)

This starts a distinct flow and uses a new `REQUEST_ID`.

```json
{
  "TYPE": "COMMAND_REDIRECT",
  "REQUEST_ID": "REQUEST_ID_NOVO",
  "PAYLOAD": {
    "NEW_MASTER_ADDRESS": "IP_MASTER_A:PORT"
  }
}
```

### 3.5 Temporary registration (Worker B -> Master A)

After receiving `COMMAND_REDIRECT`, worker closes connection to `MASTER_B`, opens new socket to `MASTER_A`, and sends:

```json
{
  "TYPE": "REGISTER_TEMPORARY_WORKER",
  "REQUEST_ID": "REQUEST_ID_NOVO",
  "PAYLOAD": {
    "WORKER_ID": "B1",
    "ORIGINAL_MASTER_ADDRESS": "IP_MASTER_B:PORT"
  }
}
```

Master A responds normally through existing task protocol (`TASK=QUERY` or `TASK=NO_TASK`).

### 3.6 Release command (Master A -> Worker B)

When Master A normalizes load and no longer needs temporary workers:

```json
{
  "TYPE": "COMMAND_RELEASE",
  "REQUEST_ID": "REQUEST_ID_NOVO",
  "PAYLOAD": {
    "ORIGINAL_MASTER_ADDRESS": "IP_MASTER_B:PORT"
  }
}
```

### 3.7 Return notification (Master A -> Master B)

Sent in parallel to `COMMAND_RELEASE`, with a distinct `REQUEST_ID`.

```json
{
  "TYPE": "NOTIFY_WORKER_RETURNED",
  "REQUEST_ID": "REQUEST_ID_NOVO",
  "PAYLOAD": {
    "WORKER_ID": "B1"
  }
}
```

After receiving `COMMAND_RELEASE`, Worker B reconnects to original master with the standard presentation protocol (`ALIVE`).

## 4. Data Flow

### 4.1 Help flow
1. `MASTER_A` detects saturation.
2. `MASTER_A` opens TCP to `MASTER_B` and sends `REQUEST_HELP`.
3. `MASTER_B` evaluates its own load and worker availability.
4. `MASTER_B` responds via same socket:
   - `RESPONSE_ACCEPTED` with offered worker addresses, or
   - `RESPONSE_REJECTED` with reason.
5. If accepted, `MASTER_B` sends `COMMAND_REDIRECT` to offered workers.
6. Redirected worker reconnects to `MASTER_A` and sends `REGISTER_TEMPORARY_WORKER`.
7. `MASTER_A` continues normal task dispatch and ACK cycle.

### 4.2 Return flow
1. `MASTER_A` detects normalized load.
2. `MASTER_A` sends `COMMAND_RELEASE` to temporary worker.
3. In parallel, `MASTER_A` sends `NOTIFY_WORKER_RETURNED` to `MASTER_B`.
4. Worker reconnects to original master and resumes standard flow.

## 5. Decision Rules

`MASTER_B` returns `RESPONSE_REJECTED` when:
- `HIGH_LOAD`: local load is at/above local capacity threshold.
- `NO_WORKERS_AVAILABLE`: no free workers to offer.
- `REFUSED`: local policy denies sharing in that context.

`MASTER_B` returns `RESPONSE_ACCEPTED` when:
- local load is healthy,
- shareable workers are available,
- local policy permits sharing.

`MASTER_A` releases temporary workers when:
- load is normalized (below saturation threshold for 3 consecutive load checks).

## 6. Error Handling and Resilience

- Timeout waiting for response to `REQUEST_HELP`:
  - log with `REQUEST_ID`, peer socket, and timeout reason;
  - optionally try next known neighbor master.
- Invalid payload (missing required fields):
  - controlled failure, log and ignore message.
- Unknown fields:
  - tolerated and ignored.
- Redirect failure:
  - if worker cannot connect to new master, worker retries and then falls back to original master on next regular cycle.
- Notification failure (`NOTIFY_WORKER_RETURNED`):
  - retry a limited number of times (for example, 3), then log unresolved return notification.

## 7. Observability

Each controlled failure log should include, when available:
- `TYPE`
- `REQUEST_ID`
- source/destination socket (`IP:PORT`)
- validation/processing error reason

## 8. Compatibility Notes

- Existing Worker-Master task cycle remains valid.
- Existing `ALIVE` framing and `\n` delimiter remain unchanged.
- Existing systems that ignore unknown fields remain compatible.

## 9. Acceptance Criteria (Sprint 03)

1. Master A sends `REQUEST_HELP` and receives `RESPONSE_ACCEPTED` or `RESPONSE_REJECTED` via same socket.
2. Help response preserves same `REQUEST_ID` as request.
3. Rejected response includes one valid reason (`HIGH_LOAD`, `NO_WORKERS_AVAILABLE`, `REFUSED`).
4. On acceptance, Master B sends `COMMAND_REDIRECT` to offered workers.
5. Redirected worker connects to Master A and sends `REGISTER_TEMPORARY_WORKER`.
6. Master A responds normally through existing task protocol.
7. When normalized, Master A sends `COMMAND_RELEASE` and `NOTIFY_WORKER_RETURNED` in parallel.
8. Released worker reconnects to original master using standard `ALIVE` flow.
9. Parsing behavior is robust: unknown fields tolerated, missing required fields logged and handled without crashing.
