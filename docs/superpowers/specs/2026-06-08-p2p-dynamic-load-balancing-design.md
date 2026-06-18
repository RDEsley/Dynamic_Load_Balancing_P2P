---
title: P2P Dynamic Load Balancing — Design
date: 2026-06-08
authors:
  - student: unknown
  - reviewer: copilot
---

# Resumo

Este documento descreve o design implementado para o projeto "P2P com Balanceamento de Carga Dinâmico" (Sprints 1–3) especificado em `document.md`.
Escopo: Sprints 1 (Heartbeat), 2 (Ciclo de Tarefas) e 3 (Negociação Master-to-Master e redirecionamento de Workers).

## Objetivos do design
- Implementar nós `Master` (`master.py`) e `Worker` (`worker.py`) comunicando via TCP com JSON delimitado por `\n`.
- Fornecer protocolo de negociação Master↔Master com `request_help` / `response_*` / `command_redirect` / `command_release`.
- Garantir interoperabilidade entre implementações distintas respeitando o esquema JSON e o framing — chaves e valores dos payloads todos em minúsculo.

**DoD (síntese)**: worker apresenta-se e faz heartbeat; master entrega tarefa ou responde `no_task`; status retornado e `ack` recebido; master saturado solicita ajuda com `request_help`, recebe `response_accepted` e workers são redirecionados e devolvidos corretamente.

---

## 1. Arquitetura (visão geral)

Dois arquivos Python independentes, sem dependências externas além da stdlib:

- `master.py` — servidor TCP. Aceita conexões de Workers e de peers Masters em paralelo usando `threading.Thread` por conexão. Mantém `fila_tarefas` (`collections.deque`), detecta saturação e negocia com peers via `_solicitar_ajuda`. Configurado por variáveis de ambiente ou arquivo `.env` (carregado manualmente sem `python-dotenv`).
- `worker.py` — cliente TCP. Loop principal de `ciclo_tarefa` (apresentação → tarefa → status → ack), com thread dedicada de `ciclo_heartbeat` rodando em paralelo a cada `HEARTBEAT_INTERVAL` segundos. Estado de conexão (master atual, endereço original, `SERVER_UUID_ORIGINAL`) protegido por `threading.Lock`.

Não há componente separado de `PeerManager` nem `TaskDispatcher` — toda a lógica reside diretamente em funções dentro de cada arquivo.

---

## 2. Componentes e interfaces

- `iniciar_master()` — ponto de entrada do master. Inicia as threads `gerador_de_tarefas` e `monitorar_carga` como daemon, depois entra em loop de `accept`, disparando uma `Thread` por conexão para `tratar_cliente`.

- `tratar_cliente(conn, addr)` — handler único para todas as conexões recebidas pelo master. Distingue mensagens M2M (possuem campo `"type"`) de mensagens de Worker (campos `"task"` ou `"worker"`). Aceita chaves em maiúsculo ou minúsculo para interoperabilidade. Timeout de sessão configurado em `SESSION_TIMEOUT = 30s`.

- `gerador_de_tarefas()` — thread daemon que insere uma tarefa `{"task": "query", "user": <nome>}` na `fila_tarefas` a cada segundo, até o limite opcional `TASK_COUNT`.

- `monitorar_carga()` — thread daemon que acorda a cada 5 segundos, compara `len(fila_tarefas)` com `SATURATION_THRESHOLD` e `RELEASE_THRESHOLD`, e aciona `_solicitar_ajuda` ou marca workers para devolução. Inclui cooldown de `REQUEST_HELP_COOLDOWN = 15s` entre pedidos consecutivos para evitar spam.

- `_solicitar_ajuda(carga_atual)` — percorre `NEIGHBORS` em ordem, abre conexão TCP com timeout `M2M_TIMEOUT = 5s`, envia `request_help` com UUID v4 único e aguarda `response_accepted` ou `response_rejected`. Para no primeiro vizinho que aceitar. Se nenhum responder em 5s, descarta e tenta o próximo (CT07).

- `_enviar_notify_worker_returned(worker_id, origem_addr)` — disparada em thread daemon após `command_release`, abre nova conexão TCP com o master de origem e envia `notify_worker_returned`.

- `ciclo_tarefa()` (worker) — abre conexão TCP com o master atual, envia apresentação, recebe tarefa ou redirecionamento, processa e reporta status. Cada ciclo abre e fecha sua própria conexão.

- `ciclo_heartbeat()` (worker) — conexão separada e de curta duração: envia `{"server_uuid": ..., "task": "heartbeat", "worker_uuid": ...}` e aguarda resposta com `"response": "alive"`. Em caso de timeout ou falha, chama `_handle_master_offline`.

- `montar_apresentacao()` (worker) — retorna `{"worker": "alive", "worker_uuid": ...}` para worker local, ou adiciona `"server_uuid": <endereço_original>` quando emprestado.

---

## 3. Fluxos de dados principais

1) **Heartbeat (Sprint 1)**
  - Worker → Master: `{ "server_uuid": "127.0.0.1:9000", "task": "heartbeat", "worker_uuid": "W-XXXXXXXX" }\n`
  - Master → Worker: `{ "server_uuid": "MASTER_9000", "task": "heartbeat", "response": "alive" }\n`
  - Thread `_thread_heartbeat` dorme `HEARTBEAT_INTERVAL = 10s` entre ciclos. Timeout de resposta: 5s (`RESPONSE_TIMEOUT`). Em falha, `_handle_master_offline` reverte o worker ao master original se estava emprestado.

2) **Ciclo de Tarefas (Sprint 2)**
  - Apresentação: Worker → Master: `{ "worker": "alive", "worker_uuid": "W-XXXXXXXX" }\n` (local) ou `{ "worker": "alive", "worker_uuid": "W-XXXXXXXX", "server_uuid": "127.0.0.1:9000" }\n` (emprestado).
  - Master com tarefa: `{ "task": "query", "user": "Gale" }\n`
  - Master sem tarefa: `{ "task": "no_task" }\n`
  - Worker reporta: `{ "status": "ok", "task": "query", "worker_uuid": "W-XXXXXXXX" }\n` (90% ok, 10% nok — `random.random() < 0.9`).
  - Master confirma: `{ "status": "ack", "worker_uuid": "W-XXXXXXXX" }\n`
  - Cada sessão de tarefa é de curta duração: a conexão é fechada e reaberta a cada ciclo. Poll interval: `TASK_POLL_INTERVAL = 0.5s`.

3) **Negociação Master↔Master e redirecionamento (Sprint 3)**
  - Saturação detectada quando `len(fila_tarefas) >= SATURATION_THRESHOLD`. `workers_needed = max(1, carga_atual - SATURATION_THRESHOLD + 2)`.
  - `request_help` inclui `request_id` (UUID v4), `master_id`, `current_load`, `capacity`, `workers_needed` e `master_port` (para o vizinho montar o endereço de retorno).
  - Vizinho aceita se `len(fila_tarefas) < SATURATION_THRESHOLD`; recusa com `reason: "high_load"` caso contrário.
  - Após `response_accepted`, master receptor enfileira N entradas em `fila_destinos_redirect` e incrementa `redirecionamentos_pendentes`. No próximo `WORKER ALIVE` de um worker local ocioso, envia `command_redirect`.
  - Worker ao receber `command_redirect`: atualiza `MASTER_IP/PORT`, define `SERVER_UUID_ORIGINAL = ORIGINAL_MASTER_ADDR` e chama `registrar_temporario`, que envia `register_temporary_worker` com `worker_id` e `original_master_address`.
  - Master receptor confirma com `{ "status": "ack", "worker_uuid": ... }\n`.
  - Devolução acionada quando `len(fila_tarefas) <= RELEASE_THRESHOLD`. Master envia `command_release` com `original_master_address` e dispara `_enviar_notify_worker_returned` em thread daemon. Worker limpa `SERVER_UUID_ORIGINAL` e retorna ao master original no próximo ciclo.

---

## 4. Mensagens, framing e validação

- Framing: terminador `\n` após cada objeto JSON. Ambos os lados acumulam bytes em buffer de string (`buf = [""]`) e processam ao encontrar `\n` — sem risco de mensagens fragmentadas em TCP.
- Todas as chaves e valores dos payloads são em minúsculo (`"task"`, `"heartbeat"`, `"alive"`, `"query"`, `"no_task"`, `"ok"`, `"nok"`, `"ack"`).
- Mensagens M2M seguem `{ "type": string, "request_id": uuid, "payload": { ... } }\n`.
- Interoperabilidade: o master aceita chaves tanto em minúsculo quanto em maiúsculo via `payload.get("campo") or payload.get("CAMPO")`. O worker faz o mesmo ao ler respostas. Isso cobre o objetivo O6 sem quebrar comunicação com equipes que usem outro case.
- Campos obrigatórios ausentes: log de erro + conexão fechada (sem derrubar o processo). Tipos `"type"` desconhecidos: log + `continue` (CT09).
- JSON inválido no master: `json.JSONDecodeError` capturado, log e `continue` — a conexão não é encerrada.

---

## 5. Erros, timeouts e resiliência

- **Worker → Master timeout**: `RESPONSE_TIMEOUT = 5s` configurado via `socket.settimeout` em `conectar()`. Se expirar em ciclo de tarefa, worker reverte ao master original caso esteja emprestado (CT08).
- **Master session timeout**: `SESSION_TIMEOUT = 30s` no socket da conexão aceita. Se worker ficar inativo, sessão é encerrada limpa.
- **M2M timeout**: `M2M_TIMEOUT = 5s` em conexões `_solicitar_ajuda` e `_enviar_notify_worker_returned`. Em timeout, `request_id` é descartado e tenta próximo vizinho (CT07).
- **Heartbeat offline**: `_handle_master_offline` reverte o worker ao master original apenas se `SERVER_UUID_ORIGINAL` estiver preenchido (worker emprestado). Worker local apenas loga.
- **Tarefa perdida em erro de sessão**: master reinsere a tarefa no início da `fila_tarefas` com `appendleft` se ocorrer exceção após dequeue.
- **Histerese**: `RELEASE_THRESHOLD < SATURATION_THRESHOLD` (padrão: 2 e 4 no `.env`) evita efeito ping-pong de empréstimo e devolução imediatos. Cooldown adicional de 15s entre `request_help` consecutivos.
- **Cleanup de sessão**: bloco `finally` em `tratar_cliente` remove o worker de `workers_conectados`, `workers_emprestados` e `workers_para_liberar` independente de como a conexão termina.

---

## 6. Configuração e execução

Configurado por variáveis de ambiente ou arquivo `.env` na raiz (carregado por `load_dotenv()` embutido no `master.py`):

```env
MASTER_HOST=127.0.0.1
MASTER_PORT=9000
SERVER_UUID=Master_A
NEIGHBORS=127.0.0.1:9001,127.0.0.1:9002
CAPACITY=4
RELEASE_THRESHOLD=2
TASK_COUNT=50
```

O `worker.py` lê apenas `MASTER_HOST` e `MASTER_PORT` via `os.getenv`. `WORKER_UUID` é gerado automaticamente na inicialização como `W-` seguido de 8 caracteres hex do UUID4.

Comandos para rodar:

```bash
# Terminal 1 — Master A
MASTER_PORT=9000 SERVER_UUID=Master_A NEIGHBORS=127.0.0.1:9001 python master.py

# Terminal 2 — Master B
MASTER_PORT=9001 SERVER_UUID=Master_B NEIGHBORS=127.0.0.1:9000 python master.py

# Terminais 3+ — Workers (conectam ao Master A por padrão)
MASTER_PORT=9000 python worker.py
```

Ou com o arquivo `.env` na raiz para o master, ajustando os valores conforme o nó.

---

## 7. Critérios de aceitação (DoD detalhado)

1. Worker abre conexão TCP com Master e apresenta-se com `{ "worker": "alive", "worker_uuid": "..." }`.
2. Master parseia e responde `{ "task": "query", "user": "..." }` ou `{ "task": "no_task" }` corretamente.
3. Worker executa tarefa simulada (`sleep` aleatório 0.5–1.5s) e envia `{ "status": "ok|nok", "task": "query", "worker_uuid": "..." }`; Master responde `{ "status": "ack", "worker_uuid": "..." }`.
4. Thread de heartbeat do Worker envia `{ "server_uuid": ..., "task": "heartbeat", "worker_uuid": ... }` a cada 10s e recebe `{ "response": "alive" }` em até 5s.
5. Saturação no Master (`len(fila) >= CAPACITY`) aciona `request_help` e completa negociação com `response_accepted` / `command_redirect`.
6. Worker redirecionado envia `register_temporary_worker` ao novo Master e passa a incluir `server_uuid` na apresentação.
7. Normalização da carga (`len(fila) <= RELEASE_THRESHOLD`) aciona `command_release` ao Worker e `notify_worker_returned` ao Master de origem; Worker reconecta ao master original sem `server_uuid`.
