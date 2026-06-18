# Dynamic Load Balancing P2P

<div align="center">

**Sistema distribuído autônomo com balanceamento de carga horizontal via arquitetura P2P**

*Disciplina de Arquitetura de Sistemas Distribuídos — CEUB*

---

![Python](https://img.shields.io/badge/Python-3.7+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Threading](https://img.shields.io/badge/Threading-Concorrência-6C63FF?style=for-the-badge)
![TCP](https://img.shields.io/badge/TCP-Sockets-FF6B35?style=for-the-badge&logo=cloudflare&logoColor=white)
![JSON](https://img.shields.io/badge/JSON-Protocolo-000000?style=for-the-badge&logo=json&logoColor=white)
![TLS](https://img.shields.io/badge/Supervisor-TLS%3A443-22C55E?style=for-the-badge)

</div>

---

## Visão Geral

Cada nó **Master** gerencia sua **Farm** de **Workers**, mantém uma fila FIFO de tarefas e negocia empréstimo de Workers com Masters vizinhos quando a carga excede um limiar. A comunicação P2P segue o protocolo JSON do plano de projeto (`plano_proj_SD-26_1.pdf` / `document.md`), com delimitador `\n` em stream TCP.

Na **Sprint 4**, o Master envia métricas ao supervisor da disciplina ([nuted-ia.dev](https://nuted-ia.dev/supervisor/dashboard/)) via **TLS na porta 443**, a cada **10 segundos**, sem aguardar resposta.

---

## Estrutura do Projeto

```
Dynamic_Load_Balancing_P2P/
├── master.py              # Master (Threads): fila, M2M, resiliência, reporter
├── worker.py              # Worker: heartbeat, tarefas, redirect/release
├── supervisor.py          # Cliente TLS → nuted-ia.dev (Sprint 4)
├── scripts/
│   └── test_supervisor.py # Envio único de métricas (teste seguro)
├── document.md            # Especificação das sprints (texto)
├── plano_proj_SD-26_1.pdf # Plano oficial do professor
├── .env.example           # Template de configuração
├── requirements.txt
└── README.md
```

---

## Tecnologias

| Tecnologia | Uso |
|:---|:---|
| Python 3.7+ | Linguagem principal |
| Threading | Uma thread por conexão no Master; heartbeat em thread separada no Worker |
| TCP + JSON (`\n`) | Protocolo P2P (Workers e Masters) |
| TLS/TCP (porta 443) | Envio de `performance_report` ao supervisor |
| `deque` + locks | Fila FIFO e estado compartilhado thread-safe |
| `psutil` (opcional) | Métricas reais de CPU/memória no relatório Sprint 4 |

---

## Pré-requisitos e Instalação

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edite o `.env` conforme o ambiente (lab, IP do master, vizinhos).

---

## Configuração (`.env`)

### Identidade do nó (obrigatório para o dashboard)

```env
SERVER_UUID=master_3
HOSTNAME=master_3_a_local
```

### Master P2P (rede do lab / máquinas do grupo)

```env
MASTER_HOST=0.0.0.0          # bind — escuta em todas as interfaces
MASTER_PORT=9000             # porta TCP do protocolo P2P (ajuste no lab se necessário)
CAPACITY=4                   # limiar de saturação (tarefas pendentes)
RELEASE_THRESHOLD=2          # histerese para devolver workers emprestados
TASK_COUNT=50                # tarefas simuladas (0 = infinito)
NEIGHBORS=outro_grupo=192.168.x.x:9000
```

### Worker (conectar ao master)

No terminal do worker ou em `.env` separado:

```env
MASTER_HOST=127.0.0.1        # IP do master (não use 0.0.0.0 aqui)
MASTER_PORT=9000
```

### Supervisor Sprint 4 (dashboard do professor)

```env
SUPERVISOR_ENABLED=true
SUPERVISOR_HOST=nuted-ia.dev
SUPERVISOR_PORT=443
SUPERVISOR_TLS=true
SUPERVISOR_SNI=nuted-ia.dev
SUPERVISOR_INTERVAL=10       # mínimo recomendado — não reduzir
PAYLOAD_VERSION=sprint4-monitor
```

> **Duas portas, dois propósitos:** `MASTER_PORT` (ex.: 9000) é o P2P entre Masters/Workers no lab. A porta **443** é só para enviar métricas ao `nuted-ia.dev`.

---

## Como Executar

### Terminal 1 — Master

```powershell
python master.py
```

Saída esperada:

```log
[SUPERVISOR] Reporter ativo -> nuted-ia.dev:443 (TLS=True, intervalo=10s, uuid=master_3)
=== MASTER 'master_3' (master_3_a_local) ON-LINE EM 0.0.0.0:9000 ===
[SUPERVISOR] Enviado performance_report (pending=1 running=0)
```

### Terminal 2 — Worker(s)

```powershell
$env:MASTER_HOST='127.0.0.1'
$env:MASTER_PORT='9000'
python worker.py
```

Abra vários terminais para simular mais Workers na Farm.

### Dois Masters no lab (Sprint 3)

Em máquinas ou IPs diferentes, cada equipe sobe um master. Para emprestar Workers entre grupos, configure `NEIGHBORS` com o **IP real** e a **porta P2P** do vizinho (não a 443 do supervisor).

**Master A (saturado — ex.: PC do grupo A):**

```env
MASTER_HOST=0.0.0.0
MASTER_PORT=9000
SERVER_UUID=master_3
HOSTNAME=master_3_a_local
CAPACITY=4
RELEASE_THRESHOLD=2
TASK_COUNT=50
NEIGHBORS=grupo_b=192.168.x.x:9000
```

**Master B (vizinho — ex.: PC do grupo B):**

```env
MASTER_HOST=0.0.0.0
MASTER_PORT=9000
SERVER_UUID=master_b
HOSTNAME=master_b.farm.local
CAPACITY=10
RELEASE_THRESHOLD=4
TASK_COUNT=0
NEIGHBORS=master_3=192.168.y.y:9000
```

**Workers do Master B** apontam para o IP do B:

```env
MASTER_HOST=192.168.x.x
MASTER_PORT=9000
```

Quando a fila do A passa de `CAPACITY`, o A envia `request_help`; o B aceita e redireciona Workers com `command_redirect`. Quando a fila normaliza (`RELEASE_THRESHOLD`), o A devolve com `command_release` e `notify_worker_returned`.

### Dashboard (Sprint 4)

Com o master rodando e `SUPERVISOR_ENABLED=true`:

**https://nuted-ia.dev/supervisor/dashboard/**

Procure o nó `master_3`. O painel atualiza a cada ~10s.

### Teste pontual do supervisor (sem loop)

Envia **um único** pacote — útil para validar conectividade sem flood:

```powershell
python scripts/test_supervisor.py --dry-run   # só mostra o JSON
python scripts/test_supervisor.py             # envia 1 vez
```

---

## Como Parar

| Situação | Ação |
|:---|:---|
| Terminal aberto | `Ctrl + C` no master e em cada worker |
| Fechou o terminal sem parar | Ver processos na porta 9000 e encerrar |

```powershell
netstat -ano | findstr :9000
Stop-Process -Id <PID> -Force
```

Ou matar todos os Python do projeto:

```powershell
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
  Where-Object { $_.CommandLine -match 'master\.py|worker\.py' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Para rodar localmente **sem** enviar ao nuted-ia: `SUPERVISOR_ENABLED=false` no `.env`.

---

## Arquitetura

```
┌─────────────┐  ALIVE/QUERY   ┌─────────────┐
│   Worker    │◄──────────────►│   Master    │
│  (cliente)  │  STATUS/ACK    │  (servidor) │
└─────────────┘                └──────┬──────┘
                                      │ request_help / response_*
                                      ▼
                               ┌─────────────┐
                               │ Master      │
                               │ vizinho     │
                               └─────────────┘

┌─────────────┐  performance_report (TLS)   ┌──────────────────┐
│   Master    │ ──────────────────────────► │ nuted-ia.dev:443 │
│  (reporter) │      a cada 10s, só SEND    │   (dashboard)    │
└─────────────┘                             └──────────────────┘
```

### Master (`master.py`)

- Escuta Workers e Masters na mesma porta TCP
- Fila FIFO, lista de **tarefas em execução** (`tarefas_em_execucao`)
- Se o Worker cai ou retorna NOK → tarefa volta para a fila
- Monitor de saturação → `request_help` aos vizinhos (`NEIGHBORS`)
- Thread em background envia métricas ao supervisor

### Worker (`worker.py`)

- Heartbeat a cada **10s** (thread dedicada)
- Ciclo de tarefas: `ALIVE` → `QUERY`/`NO_TASK` → `OK`/`NOK` → `ACK`
- Timeout de **5s** aguardando resposta do Master
- Trata `command_redirect`, `register_temporary_worker`, `command_release`
- Se o Master temporário cair → retorna ao master de origem (CT08)

---

## Protocolo P2P

Todas as mensagens são JSON terminadas com `\n`.

### Sprint 1 — Heartbeat (valores em CAIXA ALTA)

Worker → Master:

```json
{"SERVER_UUID": "master_3", "TASK": "HEARTBEAT"}
```

Master → Worker:

```json
{"SERVER_UUID": "master_3", "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}
```

### Sprint 2 — Tarefas (valores em CAIXA ALTA)

| Direção | Payload |
|:---|:---|
| Worker → Master | `{"WORKER":"ALIVE","WORKER_UUID":"W-XXXXXXXX"}` |
| Worker emprestado | `{"WORKER":"ALIVE","WORKER_UUID":"...","SERVER_UUID":"ip:porta_origem"}` |
| Master → Worker (com tarefa) | `{"TASK":"QUERY","USER":"Michel"}` |
| Master → Worker (fila vazia) | `{"TASK":"NO_TASK"}` |
| Worker → Master | `{"STATUS":"OK","TASK":"QUERY","WORKER_UUID":"..."}` |
| Master → Worker | `{"STATUS":"ACK","WORKER_UUID":"..."}` |

### Sprint 3 — Master-to-Master (`type` em **minúsculas**)

Envelope:

```json
{
  "type": "request_help",
  "request_id": "uuid-v4",
  "payload": { }
}
```

| type | Direção | Finalidade |
|:---|:---|:---|
| `request_help` | Master A → B | Pedido de workers |
| `response_accepted` | B → A | Aceite + `worker_details` |
| `response_rejected` | B → A | Recusa (`reason`: `high_load`, etc.) |
| `command_redirect` | B → Worker | Redireciona ao master saturado |
| `register_temporary_worker` | Worker → A | Registro como emprestado |
| `command_release` | A → Worker | Devolve ao master original |
| `notify_worker_returned` | A → B | Atualiza farm do B |

Timeout M2M no solicitante: **5 segundos** por vizinho.

### Sprint 4 — Supervisor (`performance_report`)

Enviado via TLS para `nuted-ia.dev:443`. Campos principais:

```json
{
  "server_uuid": "master_3",
  "hostname": "master_3_a_local",
  "role": "master",
  "task": "performance_report",
  "timestamp": "2026-06-08T12:34:56Z",
  "message_id": "uuid",
  "payload_version": "sprint4-monitor",
  "performance": {
    "system": { },
    "farm_state": {
      "workers": { "total_registered": 0, "workers_idle": 0, "workers_borrowed": 0, "workers_received": 0 },
      "tasks": { "tasks_pending": 0, "tasks_running": 0, "tasks_completed": 0, "tasks_failed": 0 }
    },
    "config_thresholds": { "max_task": 100, "release_task": 60 },
    "neighbors": []
  }
}
```

Regras do supervisor (plano Sprint 4):

- Apenas **SEND** — não usar `recv` após o envio
- Não usar HTTP nem paths (`/supervisor/...`) — só host + porta
- Intervalo de envio: **10 segundos**

---

## Sprints — Status

| Sprint | Escopo | Status |
|:---|:---|:---:|
| 1 | Heartbeat TCP Worker ↔ Master | Concluída |
| 2 | Fila, QUERY/NO_TASK, STATUS/ACK | Concluída |
| 3 | Negociação M2M, redirect, release | Concluída |
| 4 | Métricas TLS → nuted-ia.dev + dashboard | Concluída |

---

## Resiliência

- **Worker cai durante tarefa:** master recoloca a tarefa na fila (`[RESILIÊNCIA]`)
- **Worker retorna NOK:** tarefa volta para a fila
- **Master temporário offline:** worker retorna ao master de origem (CT08)
- **Tipo desconhecido:** logado e ignorado (CT09)
- **Histerese:** `RELEASE_THRESHOLD` < `CAPACITY` evita ping-pong de empréstimos

---

## Interoperabilidade no Lab

Para conectar com outras equipes na rede da faculdade:

1. Use o protocolo exatamente como no `document.md` / PDF do professor
2. Sprint 2: valores de controle em **CAIXA ALTA** (`ALIVE`, `QUERY`, `ACK`, …)
3. Sprint 3: campo `type` em **minúsculas** (`request_help`, `response_accepted`, …)
4. Configure `NEIGHBORS` com o IP:porta real do master vizinho
5. `WORKER_UUID` único por worker
6. Timeout do worker: **5s**; heartbeat: **10s**
7. Não altere `SUPERVISOR_INTERVAL` abaixo de 10s — risco de bloqueio no ambiente do professor

---

## Cenários de Teste

### Sprint 2

| ID | Cenário | Critério |
|:---:|:---|:---|
| CT01 | Worker local | Master entrega `QUERY` da fila |
| CT02 | Worker emprestado | `SERVER_UUID` presente; tarefa atribuída |
| CT03 | Fila vazia | Resposta `NO_TASK` |
| CT04 | Sucesso | `STATUS OK` → `ACK` |
| CT05 | Falha | `STATUS NOK` → `ACK` + tarefa recolocada na fila |

### Sprint 3

| ID | Cenário | Critério |
|:---:|:---|:---|
| CT01 | Ajuda aceita | `response_accepted` + `command_redirect` |
| CT02 | Ajuda recusada | `response_rejected`, sem redirect |
| CT03 | Correlação | Mesmo `request_id` na resposta |
| CT04 | Registro emprestado | `register_temporary_worker` + ALIVE com `SERVER_UUID` |
| CT05 | Tarefa emprestada | Ciclo QUERY/ACK completo |
| CT06 | Devolução | `command_release` + `notify_worker_returned` |
| CT07 | Timeout 5s | Tenta próximo vizinho |
| CT08 | Queda do master A | Worker reconecta ao B |
| CT09 | Tipo desconhecido | Log + processo continua |

---

## Equipe

<div align="center">

| | Nome | GitHub |
|:---:|:---|:---:|
| | Fernanda Kikuchi | [@FeMeNiKi](https://github.com/FeMeNiKi) |
| | Richard Esley | [@RDEsley](https://github.com/RDEsley) |
| | Matheus Brandão | [@AtsocD](https://github.com/AtsocD) |

</div>

---

## Objetivos do Projeto

| # | Objetivo |
|:---:|:---|
| O1 | Arquitetura P2P — Master gerencia Farm de Workers |
| O2 | Simulação de carga (`TASK_COUNT`, fila FIFO) |
| O3 | Monitoramento de saturação (`CAPACITY`) |
| O4 | Protocolo consensual Master-to-Master (`request_help`) |
| O5 | Redirecionamento dinâmico de Workers (`command_redirect`) |
| O6 | Interoperabilidade com outras equipes via protocolo JSON |

---

## Referências

- Repositório: [github.com/RDEsley/Dynamic_Load_Balancing_P2P](https://github.com/RDEsley/Dynamic_Load_Balancing_P2P)
- `plano_proj_SD-26_1.pdf` — plano oficial (inclui Sprint 4 e payload do supervisor)
- `document.md` — especificação detalhada das sprints
- Dashboard: https://nuted-ia.dev/supervisor/dashboard/

---

<div align="center">

*CEUB — Arquitetura de Sistemas Distribuídos — Prof. Michel Junio Ferreira Rosa*

</div>
