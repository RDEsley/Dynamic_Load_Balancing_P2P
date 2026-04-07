# 🔄 Dynamic Load Balancing P2P

> Sistema distribuído autônomo com balanceamento de carga horizontal via arquitetura P2P, desenvolvido para a disciplina de **Arquitetura de Sistemas Distribuídos** — CEUB.

---

## 📋 Visão Geral

Este projeto implementa um sistema distribuído onde cada nó **Master** gerencia seu próprio conjunto de nós **Worker** (uma *Farm*). Os Masters monitoram sua carga de trabalho e, ao atingir um limiar de saturação, negociam dinamicamente o empréstimo de Workers de um Master vizinho para lidar com o excesso de requisições.

A comunicação entre os Masters segue um **protocolo de consenso**, garantindo que a transferência de recursos seja coordenada e acordada entre as partes — sem qualquer conhecimento prévio da implementação interna umas das outras.

---

## 🎯 Objetivos do Projeto

| # | Objetivo | Descrição |
|---|----------|-----------|
| O1 | **Arquitetura P2P** | Criar um nó Master capaz de gerenciar (iniciar, parar, monitorar) um conjunto de Workers (Farm) |
| O2 | **Simulação de Carga** | Desenvolver um mecanismo para simular requisições chegando a um Master, com monitoramento de carga |
| O3 | **Monitoramento de Saturação** | O Master identifica quando o número de requisições excede um limiar (*threshold*) pré-definido |
| O4 | **Protocolo Consensual** | Protocolo robusto para que um Master saturado solicite ajuda e coordene redirecionamento de Workers |
| O5 | **Redirecionamento Dinâmico** | Um Master vizinho instrui Workers a se reportarem temporariamente ao Master saturado |
| O6 | **Autonomia e Interoperabilidade** | O sistema funciona em conjunto com o sistema de outra equipe, via protocolo definido |

---

## 🏗️ Arquitetura

O sistema é composto por três entidades principais:

```
┌─────────────────────────────────────────────────────────────┐
│                        REDE P2P                             │
│                                                             │
│   ┌──────────────┐   Protocolo    ┌──────────────┐          │
│   │   Master A   │◄──Consensual──►│   Master B   │          │
│   │  (saturado)  │                │  (vizinho)   │          │
│   └──────┬───────┘                └──────┬───────┘          │
│          │ gerencia                      │ gerencia          │
│    ┌─────▼──────┐                  ┌─────▼──────┐           │
│    │  Worker 1  │                  │  Worker 3  │           │
│    │  Worker 2  │◄── empréstimo ───│  Worker 4  │           │
│    └────────────┘                  └────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

### Nó Master
- Recebe requisições de clientes (simuladas)
- Mantém uma lista de Workers em sua Farm
- Distribui requisições entre seus Workers
- Monitora constantemente o número de requisições pendentes
- Inicia o **Protocolo de Conversa Consensual** quando `requisições > threshold`
- Gerencia Workers "emprestados" de outros Masters

### Nó Worker
- Processa requisições distribuídas pelo Master
- Envia **Heartbeats** periódicos para confirmar sua disponibilidade
- Pode ser redirecionado temporariamente para outro Master

### Protocolo de Comunicação
- Comunicação via **TCP** com mensagens JSON delimitadas por `\n`
- Suporte a interoperabilidade entre equipes diferentes via protocolo padronizado

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
      │  {"SERVER_UUID": "...", "TASK": "HEARTBEAT"}│
      │                                             │  2. Parsing e
      │                                             │◄─ Validação da Task
      │                                             │
      │         [Sucesso — Master Ativo]            │
      │                                             │
      │  3. Resposta JSON "ALIVE" (\n)              │
      │◄────────────────────────────────────────────│
      │                                             │
      │  4. Log: "Status: ALIVE"                    │
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
- [x] O Worker recebe a confirmação `"ALIVE"` e imprime no log
- [x] A conexão é mantida ou reestabelecida corretamente sem travar os processos

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
HOST = '10.62.217.31'   # IP do Master
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
Master Master_3 (AsyncIO) ativo em 10.62.217.31:8000
[ASYNC] Conexão iniciada com ('10.62.217.31', 52341)
[HEARTBEAT] Respondido para ('10.62.217.31', 52341)

# Worker
Iniciando Worker (AsyncIO)...
[LOG] Status: ALIVE
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
Master Master_3 ativo em 10.62.217.31:8000
[THREAD] Conexão ativa com ('10.62.217.31', 52341)
[HEARTBEAT] Respondido para ('10.62.217.31', 52341)

# Worker
Iniciando Worker...
[LOG] Status: ALIVE
```

---

## 🔌 Protocolo de Comunicação

Toda comunicação é feita via **TCP** com payloads **JSON** delimitados por `\n`.

### Heartbeat — Worker → Master

```json
{
  "SERVER_UUID": "Master_3",
  "TASK": "HEARTBEAT"
}
```

### Heartbeat — Master → Worker (resposta)

```json
{
  "SERVER_UUID": "Master_3",
  "TASK": "HEARTBEAT",
  "RESPONSE": "ALIVE"
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

### Por que `daemon=True` nas threads do Master?
Threads daemon são encerradas automaticamente quando o processo principal termina. Isso evita que o servidor fique "pendurado" aguardando threads filhas ao receber `Ctrl+C`.

---

## 📡 Interoperabilidade

O sistema foi projetado para operar com implementações de outras equipes. Para garantir compatibilidade:

1. O `SERVER_UUID` deve ser único e acordado entre as equipes
2. O protocolo JSON com `\n` é obrigatório em ambos os lados
3. Os campos `TASK` e `RESPONSE` devem seguir os valores definidos (`"HEARTBEAT"`, `"ALIVE"`)
4. A porta padrão é `8000`, mas pode ser configurada

---

## 📄 Licença

Distribuído sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

---

## 👥 Equipe

> Fernanda Kikuchi
> Richard Esley
> Matheus Brandão
