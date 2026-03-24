# Dynamic Load Balancing P2P

> Projeto de Sistemas Distribuídos com arquitetura P2P entre Masters para balanceamento horizontal dinâmico.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-em%20desenvolvimento-yellow)

---

## Visão Geral

Cada **Master** controla sua própria farm de **Workers**. Quando a carga local ultrapassa um limite (`threshold`), o Master tenta emprestar Workers de um Master vizinho via protocolo Master-Master (P2P).

O objetivo principal é garantir **interoperabilidade entre equipes diferentes** usando apenas o contrato de protocolo definido em `docs/protocol_contract.md`.

```
┌─────────────┐      P2P       ┌─────────────┐
│  Master A   │◄──────────────►│  Master B   │
│             │                │             │
│ Worker 1    │                │ Worker 4    │
│ Worker 2    │                │ Worker 5    │
│ Worker 3    │                │ Worker 6    │
└─────────────┘                └─────────────┘
```

---

## Como Funciona

### 1. Heartbeat (Worker → Master)

O Worker mantém uma conexão TCP ativa com seu Master e envia sinais de vida periodicamente.

**Fluxo:**

```
Worker                          Master
  │                               │
  │── TCP Connect ───────────────►│
  │                               │
  │── {"SERVER_UUID":"Worker_1",  │
  │    "TASK":"HEARTBEAT"}\n ────►│
  │                               │
  │◄─ {"SERVER_UUID":"Master_A",  │
  │    "TASK":"HEARTBEAT",        │
  │    "RESPONSE":"ALIVE"}\n ─────│
  │                               │
```

**Comportamento em falha:** se o Master ficar indisponível, o Worker realiza reconexão automática com backoff exponencial.

| Log esperado | Descrição |
|---|---|
| `Status: ALIVE` | Heartbeat bem-sucedido |
| `Status: OFFLINE - Tentando Reconectar` | Master inacessível, aguardando reconexão |

---

### 2. Negociação P2P (Master ↔ Master)

Quando saturado (`pending_requests > saturation_threshold`), o Master inicia o protocolo de empréstimo:

```
Master A (saturado)             Master B (disponível)
  │                                    │
  │── LOAD_STATUS_REQUEST ────────────►│
  │◄─ LOAD_STATUS_RESPONSE ───────────│
  │                                    │
  │── BORROW_WORKER_REQUEST ──────────►│
  │                                    │
  │        ┌── se disponível ──────────┤
  │◄─ ACCEPTED (+ LEASE_ID) ──────────│
  │        │                           │
  │        └── se indisponível ────────┤
  │◄─ REJECTED (+ ERROR_CODE) ────────│
  │                                    │
  │  ... (carga normaliza) ...         │
  │                                    │
  │── RETURN_WORKER_REQUEST ──────────►│
  │◄─ RETURN_CONFIRMED ───────────────│
```

---

## Estrutura do Projeto

```
.
├── master/
│   ├── server.py          # Servidor TCP: handlers de HEARTBEAT e mensagens P2P
│   ├── p2p_client.py      # Cliente para chamadas Master-Master
│   └── load_balancer.py   # Orquestração de empréstimo/devolução por threshold
│
├── worker/
│   └── client.py          # Loop de heartbeat e reconexão automática
│
├── protocol/
│   ├── constants.py       # Tarefas, respostas e códigos de erro
│   ├── framing.py         # Leitura/escrita JSON line (\n)
│   └── messages.py        # Validação e builders de payload
│
├── docs/
│   ├── protocol_contract.md      # Contrato oficial do protocolo
│   └── p2p_negotiation_flow.md   # Fluxo detalhado de negociação
│
├── tests/
│   └── ...                # Testes de integração: heartbeat, reconexão, concorrência e P2P
│
├── run_master.py
└── run_worker.py
```

---

## Requisitos

- **Python 3.10+** (recomendado 3.11+)
- Sem dependências externas obrigatórias — utiliza apenas a biblioteca padrão

---

## Execução Rápida

### 1. Iniciar um Master

```bash
python run_master.py --uuid Master_A --host 127.0.0.1 --port 9000 --workers 3
```

### 2. Iniciar um Worker

```bash
python run_worker.py --uuid Worker_1 --master-host 127.0.0.1 --master-port 9000 --interval 10
```

### 3. Exemplo com múltiplos Masters (simulação P2P)

```bash
# Terminal 1 — Master A
python run_master.py --uuid Master_A --host 127.0.0.1 --port 9000 --workers 3

# Terminal 2 — Master B (peer do Master A)
python run_master.py --uuid Master_B --host 127.0.0.1 --port 9001 --workers 3 --peer 127.0.0.1:9000

# Terminal 3 — Workers conectando ao Master A
python run_worker.py --uuid Worker_1 --master-host 127.0.0.1 --master-port 9000
```

---

## Testes

```bash
python -m unittest discover -s tests -v
```

### Cobertura dos testes

| Cenário | Status |
|---|---|
| Worker conecta via TCP no Master | ✅ |
| Mensagens JSON com delimitador `\n` | ✅ |
| Master interpreta `TASK=HEARTBEAT` | ✅ |
| Worker recebe `RESPONSE=ALIVE` | ✅ |
| Reconexão automática em falha | ✅ |
| Atendimento concorrente de vários Workers | ✅ |
| Negociação P2P entre Masters | ✅ |

---

## Protocolo

O contrato completo do protocolo está documentado em [`docs/protocol_contract.md`](docs/protocol_contract.md).

### Mensagens principais

| Tarefa | Direção | Descrição |
|---|---|---|
| `HEARTBEAT` | Worker → Master | Sinal de vida periódico |
| `LOAD_STATUS_REQUEST` | Master → Master | Consulta carga do peer |
| `BORROW_WORKER_REQUEST` | Master → Master | Solicita empréstimo de Worker |
| `RETURN_WORKER_REQUEST` | Master → Master | Devolve Worker emprestado |

### Códigos de resposta

| Resposta | Descrição |
|---|---|
| `ALIVE` | Master ativo e responsivo |
| `ACCEPTED` | Empréstimo aprovado (inclui `LEASE_ID`) |
| `REJECTED` | Empréstimo negado (inclui `ERROR_CODE`) |

---

## Contribuindo

1. Mantenha a compatibilidade com o contrato de protocolo em `docs/protocol_contract.md`.
2. Adicione testes de integração para qualquer novo fluxo de mensagens.
3. Siga a estrutura de framing JSON com delimitador `\n` definida em `protocol/framing.py`.
