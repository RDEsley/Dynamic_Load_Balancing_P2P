# 🔄 Dynamic Load Balancing P2P

> Sistema distribuído autônomo com balanceamento de carga horizontal via arquitetura P2P, desenvolvido para a disciplina de **Arquitetura de Sistemas Distribuídos** — CEUB.

---

## 📋 Visão Geral

Este projeto implementa um sistema distribuído onde cada nó **Master** gerencia seu próprio conjunto de nós **Worker** (uma *Farm*). Os Masters mantêm uma fila FIFO de tarefas pendentes, distribuem essas tarefas aos Workers e recebem de volta o resultado do processamento com confirmação explícita de recebimento.

A comunicação entre Master e Worker segue um **protocolo JSON fixo**, pensado para interoperar entre máquinas diferentes sem depender de campos locais extras.

---

## 🎯 Objetivos do Projeto

| # | Objetivo | Descrição |
|---|----------|-----------|
| O1 | **Arquitetura P2P** | Criar um nó Master capaz de gerenciar (iniciar, parar, monitorar) um conjunto de Workers (Farm) |
| O2 | **Simulação de Carga** | Desenvolver um mecanismo para simular requisições chegando a um Master, com monitoramento de carga |
| O3 | **Monitoramento de Saturação** | O Master identifica quando o número de requisições excede um limiar (*threshold*) pré-definido |
| O4 | **Fila de Tarefas** | Manter uma fila FIFO de tarefas pendentes no Master |
| O5 | **Entrega e Confirmação** | Enviar tarefa ao Worker, receber resultado e confirmar recebimento com ACK |
| O6 | **Autonomia e Interoperabilidade** | O sistema funciona em conjunto com o sistema de outra equipe, via protocolo definido |

---

## 🏗️ Arquitetura

O sistema é composto por três elementos conceituais principais:

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Master     │─────►│   Worker     │─────►│   Master     │
│ (fila FIFO)  │ task │ (processa)   │ res │ (ACK/LOG)    │
└──────────────┘      └──────────────┘      └──────────────┘
```

### Nó Master
- Recebe e gerencia tarefas em uma fila FIFO interna
- Distribui tarefas aos Workers por conexão TCP
- Ignora campos desconhecidos no JSON, mas exige os campos obrigatórios do protocolo
- Confirma o recebimento do resultado do Worker com `STATUS = "ACK"`

### Nó Worker
- Solicita tarefas ao Master por meio de heartbeat/alive signal
- Processa a tarefa simulando execução com espera aleatória ou cálculo
- Responde com `STATUS = "OK"` ou `STATUS = "NOK"`
- Aguarda o ACK do Master antes de considerar o ciclo concluído

### Protocolo de Comunicação
- Comunicação via **TCP** com mensagens JSON delimitadas por `\n`
- Valores de controle sempre em caixa alta
- Timeout de 5 segundos no Worker ao aguardar resposta do Master
- Os Masters fazem parsing estrito apenas nos campos obrigatórios e ignoram extensões futuras

---

## 💓 Sprint 1 — Mecanismo de Heartbeat (TCP)

O primeiro sprint implementa o mecanismo de Heartbeat entre Worker (cliente) e Master (servidor).

### Fluxo de Funcionamento

```
Worker (Client)                              Master (Server)
      │                                             │
      │  ──── loop a cada 30 segundos ────          │
      │                                             │
      │  1. Conexão TCP + envio de JSON (\n)        │
      │────────────────────────────────────────────►│
      │  {"WORKER": "ALIVE", "WORKER_UUID": "..."}│
      │                                             │  2. Parsing e
      │                                             │◄─ Validação do payload
      │                                             │
      │         [Sucesso — Master Ativo]            │
      │                                             │
      │  3. Resposta JSON com tarefa ou NO_TASK      │
      │◄────────────────────────────────────────────│
      │                                             │
      │  4. Log: tarefa recebida, OK/NOK e ACK       │
      │◄──┐                                         │
      │   │                                         │
      │                                             │
      │         [Falha de Conexão / Timeout]        │
      │                                             │
      │  4. Log: "Status: OFFLINE - Reconectando"   │
      │◄──┐                                         │
      │   │                                         │
      │  aguarda próximo ciclo                      │
```

### Definição de Pronto (DoD)

A entrega do Sprint 1 é considerada concluída quando:

- [x] O Worker consegue abrir uma conexão TCP com o Master
- [x] O Master recebe o JSON, realiza o *parsing* e identifica o comando de Heartbeat
- [x] O Worker recebe uma resposta do Master e imprime no log
- [x] A conexão é mantida ou reestabelecida corretamente sem travar os processos

---

## 📦 Sprint 2 — Distribuição de Carga e Gestão de Fila

O segundo sprint adiciona a fila de tarefas no Master e o ciclo de processamento do Worker.

### Fluxo de Funcionamento

```
Master                                 Worker
  │                                       │
  │  1. Master mantém fila FIFO           │
  │  2. Envia tarefa                       │
  │──────────────────────────────────────►│
  │   {"TASK": "QUERY", "USER": "..."}  │
  │                                       │
  │  3. Worker simula processamento       │
  │     e responde com resultado          │
  │◄──────────────────────────────────────│
  │  {"STATUS": "OK", "TASK": "QUERY",  │
  │   "WORKER_UUID": "..."}              │
  │                                       │
  │  4. Master confirma recebimento       │
  │──────────────────────────────────────►│
  │  {"STATUS": "ACK", "WORKER_UUID": "..."}
```

### Payloads do Protocolo

**Master → Worker: tarefa disponível**
```json
{
  "TASK": "QUERY",
  "USER": "string"
}
```

**Master → Worker: sem tarefa disponível**
```json
{
  "TASK": "NO_TASK"
}
```

**Worker → Master: sucesso**
```json
{
  "STATUS": "OK",
  "TASK": "QUERY",
  "WORKER_UUID": "string"
}
```

**Worker → Master: falha**
```json
{
  "STATUS": "NOK",
  "TASK": "QUERY",
  "WORKER_UUID": "string"
}
```

**Master → Worker: ACK**
```json
{
  "STATUS": "ACK",
  "WORKER_UUID": "string"
}
```

### Comandos de Fila no Master

Os Masters possuem um CLI simples para teste manual da fila:

- `add_task <user_name>`: adiciona uma task na fila
- `delete_task`: remove a primeira task da fila
- `clear`: limpa toda a fila
- `stop`: desativa novas entradas de task
- `list`: mostra o conteúdo atual da fila

---

## 📁 Estrutura do Projeto

```
Dynamic_Load_Balancing_P2P/
│
├── AsyncIO/
│   ├── master.py          # Master com asyncio (não-bloqueante)
│   └── worker.py          # Worker com asyncio
│
├── Thread/
│   ├── master.py          # Master com threading
│   └── worker.py          # Worker com socket bloqueante
│
├── README.md
└── LICENSE
```

---

## 🚀 Como Executar

### Pré-requisitos

- Python **3.7+**
- Sem dependências externas — apenas biblioteca padrão do Python

### Configuração

Antes de rodar, edite as constantes de rede nos arquivos:

```python
HOST = ''   # IP do Master
PORT = 8000             # Porta TCP
SERVER_UUID = "Master_3"  # Identificador único do Master
```

---

### Versão com AsyncIO (recomendada)

Ideal para alta concorrência com baixo overhead de recursos.

**Terminal 1 — Master:**
```bash
cd AsyncIO
python master.py
```

**Terminal 2 — Worker:**
```bash
cd AsyncIO
python worker.py
```

**Saída esperada:**

```
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

### Versão com Threads

Mais simples e direta; cada conexão é tratada em uma thread separada.

**Terminal 1 — Master:**
```bash
cd Thread
python master.py
```

**Terminal 2 — Worker:**
```bash
cd Thread
python worker.py
```

**Saída esperada:**

```
# Master
Master Master_3 ativo em <HOST>:8000
[THREAD] Conexão ativa com ('10.62.217.31', 52341)
[TASK DISTRIBUIDA] Worker LOCAL - ('10.62.217.31', 52341) - USER: Michel
[ACK] Enviado para Worker_1

# Worker
Iniciando Worker...
[LOG] Enviando payload: {"WORKER": "ALIVE", "WORKER_UUID": "Worker_1"}
[LOG] Resposta do Master: {"TASK": "QUERY", "USER": "Michel"}
[TASK] Executando tarefa para: Michel
[LOG] ACK do Master: {"STATUS": "ACK", "WORKER_UUID": "Worker_1"}
```

---

## 🔌 Protocolo de Comunicação

Toda comunicação é feita via **TCP** com payloads **JSON** delimitados por `\n`.

### Heartbeat — Worker → Master

```json
{
  "WORKER": "ALIVE",
  "WORKER_UUID": "Worker_1"
}
```

Se o Worker estiver em outra máquina, o campo `SERVER_UUID` também pode ser enviado.

### Tarefa — Master → Worker

```json
{
  "TASK": "QUERY",
  "USER": "Michel"
}
```

### Sem tarefa — Master → Worker

```json
{
  "TASK": "NO_TASK"
}
```

### Resultado — Worker → Master

```json
{
  "STATUS": "OK",
  "TASK": "QUERY",
  "WORKER_UUID": "Worker_1"
}
```

### ACK — Master → Worker

```json
{
  "STATUS": "ACK",
  "WORKER_UUID": "Worker_1"
}
```

> **Importante:** Todas as mensagens devem terminar com `\n` para delimitar o fim do payload.

---

## ⚙️ Comparação das Implementações

| Característica | AsyncIO | Threads |
|---|---|---|
| Modelo de concorrência | Cooperativo (event loop) | Preemptivo (OS threads) |
| Overhead por conexão | Muito baixo | Médio (stack por thread) |
| Complexidade do código | Média | Baixa |
| Escalabilidade | Alta (milhares de conexões) | Média (centenas de conexões) |
| Bloqueio de I/O | Não bloqueia | Bloqueia a thread |
| Indicado para | Alta concorrência | Simplicidade e prototipagem |

---

## 🧩 Decisões de Design

### Por que JSON com delimitador `\n`?
O TCP é um protocolo orientado a **stream** — não há garantia de que um `recv()` contenha exatamente uma mensagem. O uso de `\n` como delimitador garante que o receptor saiba exatamente onde uma mensagem termina e a próxima começa, evitando problemas de *framing*.

### Por que timeout de 5 segundos no Worker (Thread)?
Sem timeout, um Worker poderia travar indefinidamente aguardando resposta de um Master offline. O timeout de 5s garante que o Worker detecte falhas rapidamente e registre `OFFLINE` no log, seguindo para a próxima tentativa no ciclo de 30 segundos.

### Por que timeout de 5 segundos no Worker (AsyncIO)?
O comportamento precisa ser consistente nas duas implementações. No AsyncIO, o `await` da resposta também é limitado a 5 segundos para evitar bloqueio indefinido antes da próxima tentativa.

### Por que `daemon=True` nas threads do Master?
Threads daemon são encerradas automaticamente quando o processo principal termina. Isso evita que o servidor fique "pendurado" aguardando threads filhas ao receber `Ctrl+C`.

---

## 📡 Interoperabilidade

O sistema foi projetado para operar com implementações de outras equipes. Para garantir compatibilidade:

1. O `WORKER_UUID` deve ser único por worker
2. O protocolo JSON com `\n` é obrigatório em ambos os lados
3. Os valores de controle devem ser tratados em caixa alta: `ALIVE`, `QUERY`, `NO_TASK`, `OK`, `NOK`, `ACK`
4. Os Masters ignoram campos desconhecidos, mas rejeitam payloads sem os campos obrigatórios
5. O Worker aguarda no máximo 5 segundos pela resposta do Master
6. A porta padrão é `8000`, mas pode ser configurada

---

## 📄 Licença

Distribuído sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

---

## 👥 Equipe

> [Fernanda Kikuchi](https://github.com/FeMeNiKi) <br>
> [Richard Esley](https://github.com/RDEsley) <br>
> [Matheus Brandão](https://github.com/AtsocD)
