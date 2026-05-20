# ⚡ Dynamic Load Balancing P2P

<div align="center">

**Sistema distribuído autônomo com balanceamento de carga horizontal via arquitetura P2P**

*Disciplina de Arquitetura de Sistemas Distribuídos — CEUB*

---

![Python](https://img.shields.io/badge/Python-3.7+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![AsyncIO](https://img.shields.io/badge/AsyncIO-Concorrência-00C7B7?style=for-the-badge&logo=python&logoColor=white)
![TCP](https://img.shields.io/badge/TCP-Sockets-FF6B35?style=for-the-badge&logo=cloudflare&logoColor=white)
![JSON](https://img.shields.io/badge/JSON-Protocolo-000000?style=for-the-badge&logo=json&logoColor=white)
![Threading](https://img.shields.io/badge/Threading-Paralelo-6C63FF?style=for-the-badge&logo=buffer&logoColor=white)
![MIT](https://img.shields.io/badge/Licença-MIT-22C55E?style=for-the-badge)

</div>

---

## 📋 Visão Geral

Este projeto implementa um sistema distribuído onde cada nó **Master** gerencia seu próprio conjunto de nós **Worker** (uma *Farm*). Os Masters mantêm uma fila FIFO de tarefas pendentes, distribuem essas tarefas aos Workers e recebem de volta o resultado do processamento com confirmação explícita de recebimento.

A comunicação entre Master e Worker segue um **protocolo JSON fixo**, pensado para interoperar entre máquinas diferentes sem depender de campos locais extras.

---

## 🛠️ Tecnologias Utilizadas

| Tecnologia | Uso no Projeto |
|:---:|:---|
| 🐍 **Python 3.7+** | Linguagem principal — sem dependências externas |
| ⚡ **AsyncIO** | Concorrência cooperativa de alta performance no Master/Worker |
| 🧵 **Threading** | Implementação alternativa com threads por conexão |
| 🔌 **TCP Sockets** | Canal de comunicação confiável entre nós |
| 📦 **JSON** | Protocolo de mensagens com delimitador `\n` |
| 🗄️ **deque (FIFO)** | Estrutura de fila de tarefas thread-safe no Master |

---

## 🎯 Objetivos do Projeto

| # | Objetivo | Descrição |
|:---:|:---:|:---|
| O1 | **Arquitetura P2P** | Criar um nó Master capaz de gerenciar (iniciar, parar, monitorar) um conjunto de Workers |
| O2 | **Simulação de Carga** | Desenvolver mecanismo para simular requisições com monitoramento de carga |
| O3 | **Monitoramento de Saturação** | O Master identifica quando requisições excedem um limiar (*threshold*) |
| O4 | **Protocolo Consensual M2M** | Masters saturados negociam ajuda com vizinhos via `REQUEST_HELP` / `RESPONSE_*` |
| O5 | **Redirecionamento Dinâmico** | Workers são redirecionados temporariamente com `COMMAND_REDIRECT` e devolvidos com `COMMAND_RELEASE` |
| O6 | **Autonomia e Interoperabilidade** | Operar com sistemas de outras equipes via protocolo JSON definido |

---

## 🏗️ Arquitetura

```
┌────────────────┐   task    ┌────────────────┐   result  ┌────────────────┐
│    Master      │ ────────► │     Worker     │ ────────► │    Master      │
│  (fila FIFO)   │           │  (processa)    │           │  (ACK / LOG)   │
└────────────────┘           └────────────────┘           └────────────────┘
```

### 🖥️ Nó Master
- Recebe Workers e outros Masters na mesma porta TCP (envelope `TYPE` vs. Sprint 2)
- Gerencia fila FIFO, saturação (`CAPACITY`) e histerese de devolução (60% da capacidade)
- Negocia empréstimo de Workers com Masters vizinhos (`NEIGHBOR_MASTERS` no `.env`)
- Confirma resultados com `STATUS = "ACK"` e libera Workers emprestados quando a carga normaliza

### ⚙️ Nó Worker
- Mantém conexão TCP persistente com o Master (Sprint 3)
- Solicita tarefas com `WORKER: ALIVE` (sem `SERVER_UUID` se local; com `SERVER_UUID` se emprestado)
- Processa `QUERY`, responde `OK`/`NOK` e aguarda `ACK`
- Trata `COMMAND_REDIRECT` e `COMMAND_RELEASE` do protocolo M2M

### 🔌 Protocolo de Comunicação
- Comunicação via **TCP** com mensagens JSON delimitadas por `\n`
- Valores de controle sempre em **CAIXA ALTA**
- Timeout de **5 segundos** no Worker ao aguardar resposta do Master
- Masters fazem parsing estrito apenas nos campos obrigatórios

---

## 📁 Estrutura do Projeto

```
Dynamic_Load_Balancing_P2P/
│
├── 📂 AsyncIO/
│   ├── master.py          # Master com asyncio (Sprint 2 + 3)
│   ├── worker.py          # Worker com conexão persistente (Sprint 2 + 3)
│   └── protocol.py        # Envelopes M2M e builders (Sprint 3)
│
├── 📂 tests/
│   ├── test_protocol.py
│   ├── test_master_m2m.py
│   └── test_worker_redirect.py
│
├── 📄 README.md
└── 📄 LICENSE
```

---

## ⚖️ Comparação das Implementações

| Característica | ⚡ AsyncIO | 🧵 Threads |
|:---|:---:|:---:|
| Modelo de concorrência | Cooperativo (event loop) | Preemptivo (OS threads) |
| Overhead por conexão | **Muito baixo** | Médio (stack por thread) |
| Complexidade do código | Média | Baixa |
| Escalabilidade | **Alta** (milhares de conexões) | Média (centenas) |
| Bloqueio de I/O | ✅ Não bloqueia | ❌ Bloqueia a thread |
| Indicado para | **Alta concorrência** | Simplicidade e prototipagem |

> 💡 **Recomendação:** use a versão AsyncIO para ambientes de produção e a versão Thread para aprendizado e prototipagem.

---

## 🚀 Como Executar

### Pré-requisitos

```
✅ Python 3.7+
✅ Sem dependências externas — apenas biblioteca padrão
```

### ⚙️ Configuração

Antes de rodar, edite as constantes de rede nos arquivos:

```python
HOST = ''             # IP do Master
PORT = 8000           # Porta TCP
SERVER_UUID = "Master_3"  # Identificador único do Master
```

---

### ⚡ Versão AsyncIO (recomendada)

> Ideal para alta concorrência com baixo overhead de recursos.

```bash
# Terminal 1 — Master
cd AsyncIO
python master.py

# Terminal 2 — Worker
cd AsyncIO
python worker.py
```

**Saída esperada:**

```log
# Master
Master Master_3 (AsyncIO) ativo em <HOST>:8000
[ASYNC] Conexão iniciada com ('10.62.217.31', 52341)
[TASK DISTRIBUIDA] Worker LOCAL - ('10.62.217.31', 52341) - USER: Michel
[ACK] Enviado para Worker_1

# Worker
Iniciando Worker (AsyncIO)...
[LOG] Enviando payload: {"WORKER": "ALIVE", "WORKER_UUID": "Worker_1"}
[LOG] Resposta do Master: {"TASK": "QUERY", "USER": "Michel"}
[TASK] Processando tarefa para USER=Michel
[LOG] ACK do Master: {"STATUS": "ACK", "WORKER_UUID": "Worker_1"}
```

---

### 🧵 Versão com Threads

> Mais simples e direta; cada conexão é tratada em uma thread separada.

```bash
# Terminal 1 — Master
cd Thread
python master.py

# Terminal 2 — Worker
cd Thread
python worker.py
```

---

## 🔌 Protocolo de Comunicação

> Toda comunicação é feita via **TCP** com payloads **JSON** delimitados por `\n`.

### 💓 Heartbeat — Worker → Master

```json
{ "WORKER": "ALIVE", "WORKER_UUID": "Worker_1" }
```

### 📤 Tarefa — Master → Worker

```json
{ "TASK": "QUERY", "USER": "Michel" }
```

### 🚫 Sem tarefa — Master → Worker

```json
{ "TASK": "NO_TASK" }
```

### 📥 Resultado — Worker → Master

```json
{ "STATUS": "OK", "TASK": "QUERY", "WORKER_UUID": "Worker_1" }
```

### ✅ ACK — Master → Worker

```json
{ "STATUS": "ACK", "WORKER_UUID": "Worker_1" }
```

> **⚠️ Importante:** todas as mensagens devem terminar com `\n` para delimitar o fim do payload no stream TCP.

---

## 🗂️ Sprints

<details>
<summary><strong>💓 Sprint 1 — Mecanismo de Heartbeat (TCP)</strong></summary>

O primeiro sprint implementa o mecanismo de Heartbeat entre Worker (cliente) e Master (servidor).

```
  Worker (Client)                           Master (Server)
       │                                          │
       │   ─────── loop a cada 30 segundos ─────  │
       │                                          │
       │  1. Conexão TCP + JSON (\n)              │
       │─────────────────────────────────────────►│
       │     {"WORKER":"ALIVE","WORKER_UUID":"…"} │
       │                                          │
       │  2. Resposta: tarefa ou NO_TASK          │
       │◄─────────────────────────────────────────│
       │                                          │
       │  3. Log: OK/NOK + aguarda ACK            │
       │◄─────────────────────────────────────────│
       │                                          │
```

**Definição de Pronto (DoD):**
- [x] O Worker consegue abrir uma conexão TCP com o Master
- [x] O Master recebe o JSON, realiza o *parsing* e identifica o comando de Heartbeat
- [x] O Worker recebe uma resposta do Master e imprime no log
- [x] A conexão é mantida ou reestabelecida corretamente sem travar os processos

</details>

<details>
<summary><strong>📦 Sprint 2 — Distribuição de Carga e Gestão de Fila</strong></summary>

O segundo sprint adiciona a fila de tarefas no Master e o ciclo completo de processamento do Worker.

```
  Master                                      Worker
    │                                           │
    │  1. Mantém fila FIFO                      │
    │                                           │
    │  2. Envia tarefa                          │
    │──────────────────────────────────────────►│
    │     {"TASK":"QUERY","USER":"…"}           │
    │                                           │
    │  3. Worker processa e responde            │
    │◄──────────────────────────────────────────│
    │     {"STATUS":"OK","TASK":"QUERY",…}      │
    │                                           │
    │  4. Master confirma                       │
    │──────────────────────────────────────────►│
    │     {"STATUS":"ACK","WORKER_UUID":"…"}    │
    │                                           │
```

**Comandos de fila disponíveis no CLI do Master:**

| Comando | Descrição |
|:---|:---|
| `add_task <user_name>` | Adiciona uma task na fila |
| `delete_task` | Remove a primeira task da fila |
| `clear` | Limpa toda a fila |
| `stop` | Desativa novas entradas de task |
| `list` | Mostra o conteúdo atual da fila |

**Definição de Pronto (DoD):**
- [x] Worker realiza o handshake de apresentação (enviando UUID)
- [x] Master distribui tarefa real da fila ou informa que não há tarefas
- [x] Worker processa a tarefa e o Master recebe status OK ou NOK
- [x] Worker recebe o ACK final, fechando o ciclo sem erros

</details>

<details>
<summary><strong>🤝 Sprint 3 — Protocolo Master-to-Master e Redirecionamento</strong></summary>

Quando a fila do Master A excede `CAPACITY` (padrão 100), o monitor de saturação envia `REQUEST_HELP` aos Masters vizinhos. O Master B avalia carga e Workers ociosos e responde com `RESPONSE_ACCEPTED` ou `RESPONSE_REJECTED` (mesmo `REQUEST_ID`). Após aceite, B envia `COMMAND_REDIRECT` aos Workers; eles registram-se no A com `REGISTER_TEMPORARY_WORKER` e passam a operar o ciclo da Sprint 2 com `SERVER_UUID` do Master de origem. Quando a carga normaliza (histerese: 3 amostras &lt; 60% da capacidade), A emite `COMMAND_RELEASE` e `NOTIFY_WORKER_RETURNED`.

**Envelope M2M (campos em CAIXA ALTA):**

```json
{
  "TYPE": "REQUEST_HELP",
  "REQUEST_ID": "UUID-V4",
  "PAYLOAD": { "MASTER_ID": "A", "CURRENT_LOAD": 150, "CAPACITY": 100, "WORKERS_NEEDED": 2 }
}
```

| TYPE | Direção | Finalidade |
|:---|:---|:---|
| `REQUEST_HELP` | Master A → B | Pedido de Workers emprestados |
| `RESPONSE_ACCEPTED` | B → A | Aceite + `WORKER_DETAILS` |
| `RESPONSE_REJECTED` | B → A | Recusa (`HIGH_LOAD`, `NO_WORKERS_AVAILABLE`, `REFUSED`) |
| `COMMAND_REDIRECT` | B → Worker | Ordena conexão ao Master saturado |
| `REGISTER_TEMPORARY_WORKER` | Worker → A | Registro como emprestado |
| `COMMAND_RELEASE` | A → Worker | Devolve ao Master original |
| `NOTIFY_WORKER_RETURNED` | A → B | Atualiza Farm do B |

**Exemplo `.env` (dois Masters na mesma rede):**

```env
# Master A (porta 8000, saturado)
HOST=0.0.0.0
PORT=8000
MASTER_ID=A
SERVER_UUID=Master_A
NEIGHBOR_MASTERS=B=192.168.0.10:8001
NUM_TASKS=120

# Master B (porta 8001, vizinho)
HOST=0.0.0.0
PORT=8001
MASTER_ID=B
SERVER_UUID=Master_B
NEIGHBOR_MASTERS=A=192.168.0.10:8000

# Worker do Master B
HOST=192.168.0.10
PORT=8001
WORKER_UUID=Worker_B1
ORIGINAL_MASTER_ID=B
```

**Demo rápida:**

```bash
# Terminal 1 — Master B
cd AsyncIO
python master.py

# Terminal 2 — Worker B1
cd AsyncIO
python worker.py

# Terminal 3 — Master A (fila grande via NUM_TASKS)
cd AsyncIO
python master.py
```

**Testes automatizados:**

```bash
python -m unittest discover -s tests -v
```

**Definição de Pronto (DoD):**
- [x] Master saturado envia `REQUEST_HELP` e correlaciona `REQUEST_ID` na resposta
- [x] Master vizinho aceita/recusa e redireciona Workers via `COMMAND_REDIRECT`
- [x] Worker emprestado registra-se e opera com `SERVER_UUID`
- [x] Devolução com `COMMAND_RELEASE` + `NOTIFY_WORKER_RETURNED` quando carga normaliza
- [x] Tipos desconhecidos são logados e ignorados sem derrubar o processo

</details>

---

<details>
<summary><strong>🤝 Sprint 03 — Master-to-Master Help (Empréstimo Temporário de Workers)</strong></summary>

Este sprint introduz um protocolo de cooperação entre Masters: quando um Master A está saturado ele pode solicitar temporariamente Workers de um Master vizinho B. A comunicação segue o envelope JSON newline-delimited e campos de controle em CAIXA ALTA.

Fluxo resumido:

- Master A envia a Master B:

```json
{"TYPE":"REQUEST_HELP","REQUEST_ID":"UUID","PAYLOAD":{"MASTER_ID":"A","CURRENT_LOAD":80,"CAPACITY":100,"WORKERS_NEEDED":2}}
```

- Master B responde no mesmo socket com `RESPONSE_ACCEPTED` ou `RESPONSE_REJECTED` preservando o `REQUEST_ID`:

Resposta aceita (normaliza detalhes de worker):

```json
{"TYPE":"RESPONSE_ACCEPTED","REQUEST_ID":"UUID","PAYLOAD":{"WORKERS_OFFERED":2,"WORKER_DETAILS":[{"ID":"B1","ADDRESS":"IP:PORT"}]}}
```

Resposta rejeitada:

```json
{"TYPE":"RESPONSE_REJECTED","REQUEST_ID":"UUID","PAYLOAD":{"REASON":"NO_WORKERS_AVAILABLE"}}
```

- Em caso de `RESPONSE_ACCEPTED`, o Master B envia `COMMAND_REDIRECT` aos Workers selecionados:

```json
{"TYPE":"COMMAND_REDIRECT","REQUEST_ID":"UUID","PAYLOAD":{"NEW_MASTER_ADDRESS":"IP_MASTER_A:PORT"}}
```

- O Worker conecta-se então a Master A e envia o registro temporário:

```json
{"TYPE":"REGISTER_TEMPORARY_WORKER","REQUEST_ID":"UUID","PAYLOAD":{"WORKER_ID":"B1","ORIGINAL_MASTER_ADDRESS":"IP_MASTER_B:PORT"}}
```

- Durante o período temporário o Worker opera normalmente (TASK/STATUS/ACK). Quando Master A normaliza, ele envia `COMMAND_RELEASE` ao Worker e `NOTIFY_WORKER_RETURNED` a Master B (ambos com `REQUEST_ID`):

```json
{"TYPE":"COMMAND_RELEASE","REQUEST_ID":"UUID","PAYLOAD":{"ORIGINAL_MASTER_ADDRESS":"IP_MASTER_B:PORT"}}

{"TYPE":"NOTIFY_WORKER_RETURNED","REQUEST_ID":"UUID","PAYLOAD":{"WORKER_ID":"B1"}}
```

Decisões importantes:

- Todos os envelopes usam `TYPE`/`REQUEST_ID`/`PAYLOAD` e valores de controle em maiúsculas.
- `RESPONSE_ACCEPTED` normaliza `WORKER_DETAILS` para objetos com `ID` e `ADDRESS`.
- Os `REQUEST_ID` devem ser preservados para correlação.
- Masters tentam 3 tentativas de `NOTIFY_WORKER_RETURNED` antes de logar falha final.

Definição de Pronto (DoD):

- [x] `REQUEST_HELP`/`RESPONSE_*` implementados com validação de payload
- [x] `COMMAND_REDIRECT` e `REGISTER_TEMPORARY_WORKER` suportados
- [x] Worker aceita redirect e registra-se temporariamente
- [x] `COMMAND_RELEASE` e `NOTIFY_WORKER_RETURNED` executam liberação e notificação
- [ ] Testes de integração end-to-end cobrindo todo o ciclo

</details>

## 🧩 Decisões de Design

<details>
<summary><strong>Por que JSON com delimitador <code>\n</code>?</strong></summary>

O TCP é um protocolo orientado a **stream** — não há garantia de que um `recv()` contenha exatamente uma mensagem. O uso de `\n` como delimitador garante que o receptor saiba exatamente onde uma mensagem termina e a próxima começa, evitando problemas de *framing*.

</details>

<details>
<summary><strong>Por que timeout de 5 segundos no Worker?</strong></summary>

Sem timeout, um Worker poderia travar indefinidamente aguardando resposta de um Master offline. O timeout de 5s garante que o Worker detecte falhas rapidamente e registre `OFFLINE` no log, seguindo para a próxima tentativa no ciclo de 30 segundos. O comportamento é consistente nas duas implementações (Thread e AsyncIO).

</details>

<details>
<summary><strong>Por que <code>daemon=True</code> nas threads do Master?</strong></summary>

Threads daemon são encerradas automaticamente quando o processo principal termina. Isso evita que o servidor fique "pendurado" aguardando threads filhas ao receber `Ctrl+C`.

</details>

---

## 📡 Interoperabilidade

O sistema foi projetado para operar com implementações de outras equipes. Para garantir compatibilidade:

1. O `WORKER_UUID` deve ser **único** por worker
2. O protocolo JSON com `\n` é **obrigatório** em ambos os lados
3. Os valores de controle devem estar em **CAIXA ALTA**: `ALIVE`, `QUERY`, `NO_TASK`, `OK`, `NOK`, `ACK`
4. Os Masters ignoram campos desconhecidos, mas **rejeitam** payloads sem os campos obrigatórios
5. O Worker aguarda no máximo **5 segundos** pela resposta do Master
6. A porta padrão é `8000`, mas pode ser configurada livremente

---

## 🧪 Cenários de Teste

| ID | Cenário | JSON Enviado pelo Worker | Resposta Esperada | Critério de Sucesso |
|:---:|:---|:---|:---|:---|
| CT01 | Worker local se apresenta | `{"WORKER":"ALIVE","WORKER_UUID":"W-123"}` | `{"TASK":"QUERY","USER":"Michel"}` | Master entrega tarefa da fila |
| CT02 | Worker emprestado se apresenta | `{...,"SERVER_UUID":"Master-B"}` | `{"TASK":"QUERY","USER":"Julia"}` | Master reconhece origem e atribui tarefa |
| CT03 | Fila vazia | `{"WORKER":"ALIVE","WORKER_UUID":"W-123"}` | `{"TASK":"NO_TASK"}` | Master responde corretamente |
| CT04 | Reporte de sucesso | `{"STATUS":"OK","TASK":"QUERY",...}` | `{"STATUS":"ACK"}` | Master libera o Worker com ACK |
| CT05 | Reporte de falha | `{"STATUS":"NOK","TASK":"QUERY",...}` | `{"STATUS":"ACK"}` | Master registra falha e confirma recebimento |

### Sprint 3 — Master-to-Master

| ID | Cenário | Critério de Sucesso |
|:---:|:---|:---|
| CT01 | Pedido aceito | `RESPONSE_ACCEPTED` + `COMMAND_REDIRECT` aos Workers |
| CT02 | Pedido recusado | `RESPONSE_REJECTED` com `HIGH_LOAD`, sem redirect |
| CT03 | Correlação | Cada resposta repete o `REQUEST_ID` da requisição |
| CT04 | Registro emprestado | `REGISTER_TEMPORARY_WORKER` + ALIVE com `SERVER_UUID` |
| CT05 | Tarefa em Worker emprestado | QUERY/ACK com log REMOTO |
| CT06 | Devolução | `COMMAND_RELEASE` + `NOTIFY_WORKER_RETURNED` + reconexão no B |
| CT07 | Timeout 5s | Solicitante tenta próximo vizinho ou aborta |
| CT08 | Queda do Master A | Worker emprestado reconecta ao B |
| CT09 | Tipo desconhecido | Log + processo continua |

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

Distribuído sob a licença **MIT**. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

---

<div align="center">

*CEUB — Arquitetura de Sistemas Distribuídos*

</div>
