# ⚡ Dynamic Load Balancing P2P

<div align="center">

**Sistema distribuído autônomo com balanceamento de carga horizontal via arquitetura P2P**

*Disciplina de Arquitetura de Sistemas Distribuídos — CEUB*

---

![Python](https://img.shields.io/badge/Python-3.7+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![AsyncIO](https://img.shields.io/badge/AsyncIO-Concorrência-00C7B7?style=for-the-badge&logo=python&logoColor=white)
![TCP](https://img.shields.io/badge/TCP-Sockets-FF6B35?style=for-the-badge&logo=cloudflare&logoColor=white)
![JSON](https://img.shields.io/badge/JSON-Protocolo-000000?style=for-the-badge&logo=json&logoColor=white)
![MIT](https://img.shields.io/badge/Licença-MIT-22C55E?style=for-the-badge)

</div>

---

## 📋 Visão Geral

Este projeto implementa um sistema distribuído onde cada nó **Master** gerencia sua *Farm* de nós **Worker**. Os Masters mantêm uma fila FIFO de tarefas, distribuem trabalho aos Workers e recebem o resultado com confirmação explícita (`ACK`).

Quando um Master satura (`fila > CAPACITY`), ele negocia com Masters vizinhos o **empréstimo temporário** de Workers via protocolo Master-to-Master (M2M). Quando a carga normaliza (histerese em 60% da capacidade), os Workers emprestados são **devolvidos** ao Master de origem.

A implementação segue o plano de projeto **P2P com Balanceamento de Carga Dinâmico** (`plano_proj_SD-26_1.pdf`), com envelopes JSON em **CAIXA ALTA** e delimitador `\n` em stream TCP.

---

## 👋 Guia para iniciantes (como usar, em linguagem simples)

Se você não é da área de programação, leia esta seção primeiro. O restante do README é mais técnico.

### O que este projeto faz, em uma frase?

Imagine um **chefe (Master)** com uma **fila de pedidos** e alguns **funcionários (Workers)** que executam os pedidos. Quando o chefe fica com fila cheia demais, ele **pede emprestado** funcionários de um **chefe vizinho**. Quando a fila diminui, os funcionários **voltam** para o chefe de origem.

Isso é **balanceamento de carga**: distribuir trabalho sem deixar um único ponto sobrecarregado.

### Quem é quem?

| Papel | O que é | Analogia |
|:---|:---|:---|
| **Master** | Programa que recebe tarefas e manda para Workers | O chefe / gerente |
| **Worker** | Programa que processa uma tarefa e devolve o resultado | O funcionário |
| **Fila** | Lista de tarefas esperando | Pedidos na cozinha |
| **CAPACITY** | Limite de tarefas antes de considerar “lotado” | Capacidade máxima da fila (ex.: 100) |
| **Master A** | Master com muita fila (saturado) | Chefe sobrecarregado |
| **Master B** | Master vizinho com Workers livres | Chefe que pode emprestar gente |
| **Empréstimo** | Worker do B vai trabalhar temporariamente no A | Funcionário em missão em outra loja |
| **Devolução** | Worker volta para o B | Funcionário retorna para a loja original |

### O que você precisa ter instalado

1. **Python 3** — [python.org](https://www.python.org/downloads/) (na instalação, marque *“Add Python to PATH”*).
2. **Este projeto** — pasta clonada ou baixada do GitHub.
3. **Dois modos de teste:**
   - **Um só computador:** dá para testar quase tudo (abre 3 janelas de terminal).
   - **Dois computadores na mesma rede Wi‑Fi:** simula melhor o cenário “de outra equipe / outro PC”.

### Teste rápido no mesmo computador (recomendado para aprender)

Você vai abrir **3 janelas do PowerShell**. Em cada uma, vá até a pasta `scripts` do projeto.

**Forma mais fácil — usar os scripts prontos**

**Passo 1 — Gerar configuração (só na primeira vez)**

```powershell
cd "C:\caminho\para\Dynamic_Load_Balancing_P2P\scripts"
.\generate-env.ps1
```

Isso cria arquivos em `config/env/` com IP, portas e fila grande no Master A. Não precisa editar nada na primeira vez.

**Passo 2 — Terminal 1: Master B (vizinho)**

```powershell
cd scripts
.\run-master-b.ps1
```

Deixe aberto. Deve aparecer: `Master Master_B ativo em ...:8001`.

**Passo 3 — Terminal 2: Worker (funcionário do B)**

```powershell
cd scripts
.\run-worker-b.ps1
```

Deixe aberto. O Worker fica pedindo trabalho ao Master B.

**Passo 4 — Terminal 3: Master A (chefe lotado)**

```powershell
cd scripts
.\run-master-a.ps1
```

O Master A sobe com **120 tarefas** na fila (mais que `CAPACITY=100`) — isso simula saturação.

> **Ordem importa:** ligue sempre **B → Worker → A**. Se o A pedir ajuda antes do Worker estar conectado no B, o pedido pode ser recusado.

**Forma manual (se preferir editar o `.env` você mesmo)**

1. Copie `AsyncIO\.env.example` para `AsyncIO\.env`.
2. Para cada terminal, ajuste o `.env` antes de rodar `python master.py` ou `python worker.py`.
3. Regras: Master A na porta **8000** com `NUM_TASKS=120`; Master B na **8001** com `NUM_TASKS=0`; Worker apontando para B (`PORT=8001`, `ORIGINAL_MASTER_ID=B`).

**Passo 5 — O que deve acontecer (sem você fazer nada)**

1. Master A percebe que a fila está cheia.
2. Master A **pede ajuda** ao Master B (`REQUEST_HELP`).
3. Master B, se tiver Worker livre, **aceita** e manda o Worker ir para o A (`COMMAND_REDIRECT`).
4. O Worker passa a trabalhar para o A por um tempo.
5. Quando a fila do A **baixa** (regra de histerese: fica abaixo de ~60% da capacidade por um tempo), o A **devolve** o Worker ao B (`COMMAND_RELEASE` + aviso ao B).

**Passo 6 — Como saber se deu certo (olhe os textos na tela)**

| Mensagem no terminal | Significado simples |
|:---|:---|
| `[M2M] Saturação detectada` | Master A está lotado e vai pedir ajuda |
| `[M2M] EMIT REQUEST_HELP` | Pedido de empréstimo enviado ao vizinho |
| `[M2M] EMIT RESPONSE_ACCEPTED` | Vizinho aceitou emprestar Worker |
| `[M2M] EMIT COMMAND_REDIRECT` | Worker foi mandado para o outro Master |
| `[WORKER] Redirecionando` | Worker está mudando de “chefe” |
| `[TASK DISTRIBUIDA] Worker REMOTO` | Tarefa foi para um Worker emprestado |
| `[M2M] EMIT COMMAND_RELEASE` | Master A está devolvendo o Worker |
| `[EMPRESTIMO] Ciclo encerrado` | Devolução concluída com sucesso |
| `[HEARTBEAT] Master ativo` | Worker confirmou que o Master está vivo |

Se aparecer `[M2M] Rejeitando HELP: needed=1 available=0`, o Master B não tinha Worker **ocioso** conectado — confira se o Terminal 2 (Worker) está rodando **antes** do A pedir ajuda.

### Teste em dois computadores (mesma rede)

1. Descubra o IP de cada máquina: `ipconfig` (procure *IPv4*, ex.: `192.168.0.15`).
2. No PC do **Master B**, use `HOST=0.0.0.0` e `PORT=8001`.
3. No PC do **Master A**, em `NEIGHBOR_MASTERS`, coloque o IP real do B: `B=192.168.0.15:8001`.
4. No **Worker**, `MASTER_HOST` = IP do PC onde o Master B está rodando.
5. Libere as portas **8000** e **8001** no firewall do Windows, se necessário.

Ordem de ligar: **Master B → Worker → Master A** (mesma ordem do teste local).

Para **3 ou mais Masters** na mesma rede (A, B, C…), veja a seção [Vários Masters na mesma rede](#-vários-masters-na-mesma-rede-2-3-ou-mais-nós).

### Comandos úteis no Master (enquanto ele está rodando)

No terminal do Master, você pode digitar:

| Comando | O que faz |
|:---|:---|
| `add_task Maria` | Coloca mais um pedido na fila (cliente “Maria”) |
| `list` | Mostra quantos pedidos estão na fila |
| `delete_task` | Remove o primeiro pedido da fila |
| `clear` | Esvazia a fila |
| `stop` | Para de aceitar pedidos novos |

### Problemas comuns

| Problema | O que tentar |
|:---|:---|
| `python não é reconhecido` | Reinstale o Python marcando *Add to PATH*, ou use `py master.py` |
| Worker não conecta | Confira IP/porta no `.env`; Master já está rodando? |
| Master A não pede ajuda | `NUM_TASKS` precisa ser **maior** que `CAPACITY` (ex.: 120 e 100) |
| Vizinho não empresta Worker | Worker do B precisa estar rodando e **sem tarefa** naquele momento |
| Porta em uso | Feche outros Masters ou mude `PORT` no `.env` |
| Firewall bloqueia | Permita Python nas redes privadas |

### Glossário rápido

- **TCP / porta:** “Canal” e “número da porta” para dois programas conversarem na rede (como um telefone com ramal).
- **JSON:** Formato de mensagem `{"CAMPO": "valor"}` que os programas trocam.
- **Saturação:** Fila maior que o limite (`CAPACITY`).
- **Histerese:** Só devolve o Worker quando a fila **já baixou de verdade**, para não ficar emprestando e devolvendo toda hora.
- **ACK:** Confirmação do Master de que recebeu o resultado (“ok, anotado”).

### Quer validar automaticamente?

Na pasta do projeto:

```powershell
python -m unittest discover -s tests -v
```

Se aparecer `OK` no final, a lógica principal está passando nos testes.

---

## 🛠️ Tecnologias

| Tecnologia | Uso |
|:---:|:---|
| **Python 3.7+** | Sem dependências externas (stdlib) |
| **AsyncIO** | Concorrência no Master e Worker |
| **TCP Sockets** | Comunicação entre nós |
| **JSON + `\n`** | Framing de mensagens |
| **deque** | Fila FIFO thread-safe no Master |

---

## 🎯 Objetivos (O1–O6)

| # | Objetivo | Status |
|:---:|:---|:---:|
| O1 | Arquitetura P2P — Master gerencia Farm | ✅ |
| O2 | Simulação de carga (`NUM_TASKS`, CLI) | ✅ |
| O3 | Monitoramento de saturação | ✅ |
| O4 | Protocolo consensual M2M | ✅ |
| O5 | Redirecionamento dinâmico de Workers | ✅ |
| O6 | Interoperabilidade via protocolo JSON | ✅ |

---

## 🏗️ Arquitetura

```
┌──────── Master A (saturado) ────────┐     REQUEST_HELP      ┌──────── Master B (vizinho) ───┐
│  fila FIFO · CAPACITY · histerese   │ ───────────────────► │  avalia carga · workers ociosos │
└──────────────┬──────────────────────┘ ◄─────────────────── └──────────────┬────────────────┘
               │                    RESPONSE_* / pool M2M                     │
               │ COMMAND_RELEASE + NOTIFY_WORKER_RETURNED                       │ COMMAND_REDIRECT
               ▼                                                                ▼
        ┌──────────────┐                                                  ┌──────────────┐
        │ Worker B1    │ ◄──── REGISTER_TEMPORARY_WORKER + ALIVE ──────── │ Worker B1    │
        │ (emprestado) │                                                  │ (local)      │
        └──────────────┘                                                  └──────────────┘
```

### Master (`AsyncIO/master.py`)
- Servidor TCP único para Workers e Masters (envelope `TYPE` vs. Sprint 2)
- Fila FIFO, CLI de tarefas, monitor de saturação
- Pool de conexões M2M (reuso após `RESPONSE_ACCEPTED`)
- Devolução de Workers **somente** quando carga normaliza (3 amostras &lt; 60% de `CAPACITY`)

### Worker (`AsyncIO/worker.py`)
- Conexão TCP persistente
- Sprint 1: `HEARTBEAT` na entrada da sessão + loop periódico a cada `HEARTBEAT_INTERVAL` (10s) — envio fire-and-forget; resposta `ALIVE` é despachada pelo loop principal por tipo de mensagem para não causar race com `COMMAND_REDIRECT`/`COMMAND_RELEASE`
- Sprint 2: `ALIVE` → `QUERY`/`NO_TASK` → `OK`/`NOK` → `ACK`
- Sprint 3: `COMMAND_REDIRECT`, `REGISTER_TEMPORARY_WORKER`, `COMMAND_RELEASE`

---

## 📁 Estrutura do Projeto

```
Dynamic_Load_Balancing_P2P/
├── AsyncIO/                 # Implementação principal
│   ├── master.py
│   ├── worker.py
│   ├── protocol.py
│   └── .env.example
├── AsyncIO_A/               # Perfil Master A (saturado) — demo multi-PC
├── AsyncIO_B/               # Perfil Master B + Worker — demo multi-PC
├── tests/                   # 24 testes automatizados
├── scripts/                 # Scripts PowerShell (run-master-a/b, worker, detect-ip)
├── docs/                    # Specs e planos de implementação
├── plano_proj_SD-26_1.pdf
└── README.md
```

---

## 🚀 Como Executar

### Pré-requisitos

- Python 3.7+
- Nenhuma dependência pip (apenas biblioteca padrão)

### Configuração rápida

```bash
cd AsyncIO
copy .env.example .env    # Windows
# Edite HOST, PORT, MASTER_ID, NEIGHBOR_MASTERS, etc.
```

**Master B (vizinho):**

```env
HOST=0.0.0.0
PORT=8001
SERVER_UUID=Master_B
MASTER_ID=B
CAPACITY=100
NUM_TASKS=0
NEIGHBOR_MASTERS=A=IP_DO_MASTER_A:8000
```

**Master A (saturado):**

```env
HOST=0.0.0.0
PORT=8000
SERVER_UUID=Master_A
MASTER_ID=A
CAPACITY=100
NUM_TASKS=120
NEIGHBOR_MASTERS=B=IP_DO_MASTER_B:8001
```

**Worker (do Master B):**

```env
MASTER_HOST=IP_DO_MASTER_B
PORT=8001
WORKER_UUID=Worker_B1
ORIGINAL_MASTER_ID=B
MASTER_SERVER_UUID=Master_B
```

### Execução local

```bash
# Terminal 1 — Master B
cd AsyncIO
python master.py

# Terminal 2 — Worker
cd AsyncIO
python worker.py

# Terminal 3 — Master A (fila grande via NUM_TASKS)
cd AsyncIO
python master.py
```

### Scripts PowerShell (rede)

```powershell
.\scripts\detect-ip.ps1
.\scripts\generate-env.ps1
.\scripts\run-master-b.ps1
.\scripts\run-master-a.ps1
```

### Testes

```bash
python -m unittest discover -s tests -v
```

---

## 🌐 Vários Masters na mesma rede (2, 3 ou mais nós)

O projeto foi pensado como **P2P entre Masters**: cada Master é um “chefe” com sua Farm de Workers. Quando um Master **satura**, ele conversa com **Masters vizinhos** listados em `NEIGHBOR_MASTERS` e pode **emprestar** Workers deles.

> **Importante:** cada **Worker** conecta em **um único Master** por vez (o “dono”). O empréstimo só muda temporariamente para qual Master ele obedece — não há Worker ligado a dois Masters ao mesmo tempo.

### Como funciona na prática

| Papel | Conexão com vários Masters? |
|:---|:---|
| **Master saturado (ex.: A)** | Sim — pede ajuda aos vizinhos configurados |
| **Master vizinho (ex.: B, C)** | Sim — pode receber `REQUEST_HELP` de vários Masters |
| **Worker** | Não em paralelo — 1 Master ativo; redireciona se emprestado |

Quando a fila passa de `CAPACITY`, o Master percorre `NEIGHBOR_MASTERS` **em sequência** e para no **primeiro vizinho que aceitar** (`RESPONSE_ACCEPTED`). Se todos recusarem ou der timeout (5 s), o pedido falha até o próximo ciclo do monitor.

### Formato de `NEIGHBOR_MASTERS`

No `.env` de cada Master, use **vários vizinhos** separados por **vírgula**:

```env
NEIGHBOR_MASTERS=B=192.168.1.15:8001,C=192.168.1.16:8002
```

Cada item é `MASTER_ID=IP:PORTA`:

- `MASTER_ID` — identificador do vizinho (ex.: `B`, `C`). Deve bater com o `MASTER_ID` que o outro Master usa ao pedir ajuda.
- `IP:PORTA` — endereço TCP onde o outro Master **escuta** (`HOST`/`PORT` dele).

O Master **não precisa** listar a si mesmo — só quem pode emprestar Workers quando **ele** estiver saturado.

### Exemplo: 3 Masters (A, B e C) na mesma Wi‑Fi

Cenário didático:

- **Master A** — porta `8000`, fila grande (saturado), pede ajuda a B e C.
- **Master B** — porta `8001`, Workers locais, empresta para A se estiver ocioso.
- **Master C** — porta `8002`, Workers locais, empresta para A se B recusar.

```
                    REQUEST_HELP (se A saturar)
         ┌──────────────────────────────────────────┐
         │                                          │
    ┌────▼────┐                              ┌──────▼────┐
    │ Master A│                              │ Master B  │
    │ :8000   │                              │ :8001     │
    │ NUM_TASKS│                             │ Workers   │
    │ > CAPACITY                             └─────┬─────┘
    └────┬────┘                                    │
         │              REQUEST_HELP (se B recusar) │
         │         ┌─────────────────────────────────┘
         │         │
         │    ┌────▼────┐
         └────► Master C │
              │ :8002   │
              │ Workers │
              └─────────┘
```

#### Master A (saturado) — PC ou pasta `testes/AsyncIO_A`

```env
HOST=0.0.0.0
PORT=8000
SERVER_UUID=Master_A
MASTER_ID=A
CAPACITY=100
NUM_TASKS=120
NEIGHBOR_MASTERS=B=192.168.1.15:8001,C=192.168.1.16:8002
```

#### Master B (vizinho) — IP `192.168.1.15`

```env
HOST=0.0.0.0
PORT=8001
SERVER_UUID=Master_B
MASTER_ID=B
CAPACITY=100
NUM_TASKS=0
NEIGHBOR_MASTERS=A=192.168.1.14:8000,C=192.168.1.16:8002
```

> O B lista A e C para poder **devolver** notificações (`NOTIFY_WORKER_RETURNED`) e resolver endereços de origem — e para o caso de o B saturar no futuro.

#### Master C (vizinho) — IP `192.168.1.16`

```env
HOST=0.0.0.0
PORT=8002
SERVER_UUID=Master_C
MASTER_ID=C
CAPACITY=100
NUM_TASKS=0
NEIGHBOR_MASTERS=A=192.168.1.14:8000,B=192.168.1.15:8001
```

#### Workers (um por Master “dono”)

**Worker do B** (roda no PC do B ou aponta para o IP do B):

```env
MASTER_HOST=192.168.1.15
PORT=8001
WORKER_UUID=Worker_B1
ORIGINAL_MASTER_ID=B
MASTER_SERVER_UUID=Master_B
```

**Worker do C**:

```env
MASTER_HOST=192.168.1.16
PORT=8002
WORKER_UUID=Worker_C1
ORIGINAL_MASTER_ID=C
MASTER_SERVER_UUID=Master_C
```

Substitua os IPs pelos valores reais de cada máquina (`ipconfig` no Windows).

### Ordem recomendada para ligar

1. Masters **vizinhos** com Workers (B e C) — cada um com seu Worker já conectado.
2. Por último, o Master **saturado** (A), para não pedir ajuda antes dos Workers estarem ociosos nos vizinhos.

Ordem mínima com 2 nós: **B → Worker → A** (igual ao guia para iniciantes).

### Checklist rápido

| Item | Verificação |
|:---|:---|
| IPs corretos | `ipconfig` em cada PC; use IPv4 da mesma rede |
| Portas distintas | A=`8000`, B=`8001`, C=`8002` (ou outras, desde que únicas) |
| `MASTER_ID` único | Cada Master com letra/nome diferente (`A`, `B`, `C`) |
| Vizinhos no `.env` | Quem pede ajuda lista quem pode emprestar |
| Firewall | Liberar as portas TCP usadas em cada PC |
| Workers ociosos | Worker do vizinho rodando **antes** do A saturar |
| Saturação | `NUM_TASKS` (ou `add_task`) **maior** que `CAPACITY` no Master que pede ajuda |

### O que você deve ver nos logs (Master A saturado)

1. `[M2M] Saturação detectada`
2. `[M2M] EMIT REQUEST_HELP -> B` (tenta o primeiro vizinho da lista)
3. Se B aceitar: `RESPONSE_ACCEPTED` + `COMMAND_REDIRECT` no terminal do B
4. Se B recusar: tentativa seguinte para `C` na próxima rodada do monitor (ou após cooldown de 10 s)
5. `[WORKER] Redirecionando` no Worker emprestado
6. `[TASK DISTRIBUIDA] Worker REMOTO` no Master A

### Limitações atuais (saber antes da demonstração)

- **Pedidos em paralelo (CT03 do PDF):** hoje o código envia `REQUEST_HELP` **um vizinho por vez** e para no primeiro que aceitar; não dispara vários pedidos simultâneos a todos os vizinhos.
- **Um empréstimo por ciclo:** após um vizinho aceitar, o monitor aguarda o cooldown (`HELP_COOLDOWN_SECONDS`, 10 s) antes de pedir de novo.
- **Mais Workers:** para emprestar 2+ Workers, o vizinho precisa ter 2+ Workers **ociosos** conectados; o Master aceita empréstimo parcial (`min(disponíveis, pedidos)`).

### Teste local com 3 portas (um só PC)

Dá para simular 3 Masters abrindo **3 terminais** com `.env` diferentes (portas `8000`, `8001`, `8002`) e 2 terminais de Worker (B e C). Use `127.0.0.1` nos vizinhos:

```env
# Master A
NEIGHBOR_MASTERS=B=127.0.0.1:8001,C=127.0.0.1:8002

# Master B
NEIGHBOR_MASTERS=A=127.0.0.1:8000,C=127.0.0.1:8002

# Master C
NEIGHBOR_MASTERS=A=127.0.0.1:8000,B=127.0.0.1:8001
```

Copie `AsyncIO/.env.example` para três arquivos (ou use `scripts/generate-env.ps1` como base) e ajuste `PORT` / `NEIGHBOR_MASTERS` antes de cada `python master.py`.

---

## 🔌 Protocolo de Comunicação

Todas as mensagens são JSON terminadas com `\n`. Valores de controle em **CAIXA ALTA**.

### Sprint 1 — Heartbeat

**Worker → Master:**

```json
{ "SERVER_UUID": "Master_B", "TASK": "HEARTBEAT" }
```

**Master → Worker:**

```json
{ "SERVER_UUID": "Master_B", "TASK": "HEARTBEAT", "RESPONSE": "ALIVE" }
```

### Sprint 2 — Tarefas

| Direção | Payload |
|:---|:---|
| Worker → Master (local) | `{"WORKER":"ALIVE","WORKER_UUID":"W1"}` |
| Worker → Master (emprestado) | `{"WORKER":"ALIVE","WORKER_UUID":"W1","SERVER_UUID":"B"}` |
| Master → Worker (tarefa) | `{"TASK":"QUERY","USER":"Michel"}` |
| Master → Worker (vazio) | `{"TASK":"NO_TASK"}` |
| Worker → Master (resultado) | `{"STATUS":"OK","TASK":"QUERY","WORKER_UUID":"W1"}` |
| Master → Worker (confirmação) | `{"STATUS":"ACK"}` |

### Sprint 3 — Master-to-Master

Envelope padrão:

```json
{
  "TYPE": "REQUEST_HELP",
  "REQUEST_ID": "UUID-V4",
  "PAYLOAD": { "MASTER_ID": "A", "CURRENT_LOAD": 150, "CAPACITY": 100, "WORKERS_NEEDED": 2 }
}
```

| TYPE | Direção | Finalidade |
|:---|:---|:---|
| `REQUEST_HELP` | Master A → B | Pedido de Workers |
| `RESPONSE_ACCEPTED` | B → A | Aceite + `WORKER_DETAILS` |
| `RESPONSE_REJECTED` | B → A | Recusa (`HIGH_LOAD`, `NO_WORKERS_AVAILABLE`, `REFUSED`) |
| `COMMAND_REDIRECT` | B → Worker | Redireciona ao Master saturado |
| `REGISTER_TEMPORARY_WORKER` | Worker → A | Registro como emprestado |
| `COMMAND_RELEASE` | A → Worker | Devolve ao Master original |
| `NOTIFY_WORKER_RETURNED` | A → B | Atualiza Farm do B (via pool M2M) |

---

## 🗂️ Sprints e DoD

| Sprint | Entrega | DoD |
|:---|:---|:---:|
| **1** | Heartbeat TCP + JSON | ✅ |
| **2** | Fila FIFO, ALIVE, QUERY, ACK | ✅ |
| **3** | M2M, redirect, empréstimo, devolução com histerese | ✅ |

**Comportamentos-chave (Sprint 3):**
- Timeout de **5 s** no solicitante de `REQUEST_HELP`
- **Histerese:** liberação com 3 amostras consecutivas abaixo de 60% de `CAPACITY`
- **Pool M2M:** conexão mantida após `RESPONSE_ACCEPTED` para `NOTIFY_WORKER_RETURNED`
- Tipos desconhecidos: log + ignorar (processo continua)
- Recepção tolera `TYPE` ou `type` (emissão em maiúsculas)

---

## 🧪 Cenários de Teste (PDF)

### Sprint 2

| ID | Cenário | Critério |
|:---:|:---|:---|
| CT01 | Worker local | `QUERY` da fila |
| CT02 | Worker emprestado | `QUERY` + `SERVER_UUID` |
| CT03 | Fila vazia | `NO_TASK` |
| CT04–05 | OK / NOK | `ACK` |

### Sprint 3 (M2M)

| ID | Cenário | Critério |
|:---:|:---|:---|
| CT01 | Pedido aceito | `RESPONSE_ACCEPTED` + `COMMAND_REDIRECT` |
| CT02 | Pedido recusado | `RESPONSE_REJECTED`, sem redirect |
| CT03 | Correlação | Mesmo `REQUEST_ID` na resposta |
| CT04 | Registro emprestado | `REGISTER_TEMPORARY_WORKER` + ALIVE remoto |
| CT05 | Tarefa em emprestado | QUERY/ACK com log REMOTO |
| CT06 | Devolução | `COMMAND_RELEASE` + `NOTIFY` + reconexão no B |
| CT07 | Timeout 5 s | Próximo vizinho ou aborta |
| CT08 | Queda do Master A | Worker reconecta ao B |
| CT09 | Tipo desconhecido | Log + continua |

---

## 🧩 Decisões de Design

- **`\n` como delimitador:** evita problemas de framing em stream TCP.
- **Devolução por histerese:** evita ping-pong de empréstimo/devolução.
- **Pool M2M:** reduz handshakes TCP repetidos (recomendação do plano de projeto).
- **ACK mínimo:** `{"STATUS":"ACK"}` conforme especificação da Sprint 2.

---

## 📡 Interoperabilidade

1. `WORKER_UUID` único por Worker
2. JSON + `\n` obrigatório
3. Valores de controle em **CAIXA ALTA**
4. Campos desconhecidos ignorados; obrigatórios ausentes → log de erro
5. Timeout de **5 s** no Worker
6. Envelopes M2M: `TYPE`, `REQUEST_ID`, `PAYLOAD`

---

## 👥 Equipe

<div align="center">

| | Nome | GitHub |
|:---:|:---|:---:|
| 👩‍💻 | Fernanda Kikuchi | [@FeMeNiKi](https://github.com/FeMeNiKi) |
| 👨‍💻 | Richard Esley | [@RDEsley](https://github.com/RDEsley) |
| 👨‍💻 | Matheus Brandão | [@AtsocD](https://github.com/AtsocD) |

</div>

---

## 📄 Licença

Distribuído sob a licença **MIT**. Veja [LICENSE](LICENSE).

---

<div align="center">

*CEUB — Arquitetura de Sistemas Distribuídos*

</div>
