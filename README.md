# Dynamic Load Balancing P2P

Projeto de Sistemas Distribuidos com arquitetura P2P entre Masters para balanceamento horizontal dinamico.

## Visao geral

Cada `Master` controla sua propria farm de `Workers`.
Quando a carga local passa de um limite (`threshold`), o Master tenta emprestar Workers de um Master vizinho via protocolo Master-Master.

O objetivo principal e garantir interoperabilidade entre equipes diferentes usando apenas o contrato de protocolo.

## Como funciona

### 1) Heartbeat (Worker -> Master)

- O Worker abre conexao TCP com o Master.
- Envia JSON finalizado com `\n`:
  - `{"SERVER_UUID":"Worker_1","TASK":"HEARTBEAT"}`
- O Master faz parse por linha e responde:
  - `{"SERVER_UUID":"Master_A","TASK":"HEARTBEAT","RESPONSE":"ALIVE"}`
- Se o Master estiver indisponivel, o Worker faz reconexao automatica com backoff.

Logs esperados no Worker:
- `Status: ALIVE`
- `Status: OFFLINE - Tentando Reconectar`

### 2) Negociacao P2P (Master <-> Master)

Quando saturado (`pending_requests > saturation_threshold`), o Master:

1. Consulta peers (`LOAD_STATUS_REQUEST`).
2. Solicita emprestimo (`BORROW_WORKER_REQUEST`).
3. Recebe:
   - `ACCEPTED` com `LEASE_ID`, ou
   - `REJECTED` com `ERROR_CODE`.
4. Ao normalizar a carga, devolve os recursos (`RETURN_WORKER_REQUEST`).

## Estrutura do projeto

- `master/`
  - `server.py`: servidor TCP do Master, handlers HEARTBEAT e mensagens P2P.
  - `p2p_client.py`: cliente para chamadas Master-Master.
  - `load_balancer.py`: orquestracao de emprestimo/devolucao por threshold.
- `worker/`
  - `client.py`: loop de heartbeat e reconexao automatica.
- `protocol/`
  - `constants.py`: tarefas, respostas e codigos de erro.
  - `framing.py`: leitura/escrita JSON line (`\n`).
  - `messages.py`: validacao e builders de payload.
- `docs/`
  - `protocol_contract.md`: contrato oficial.
  - `p2p_negotiation_flow.md`: fluxo de negociacao.
- `tests/`
  - testes de integracao heartbeat, reconexao, concorrencia e P2P.

## Requisitos

- Python 3.10+ (recomendado 3.11+)
- Sem dependencias externas obrigatorias (usa biblioteca padrao)

## Execucao rapida

### 1. Iniciar Master

```bash
python run_master.py --uuid Master_A --host 127.0.0.1 --port 9000 --workers 3
```

### 2. Iniciar Worker

```bash
python run_worker.py --uuid Worker_1 --master-host 127.0.0.1 --master-port 9000 --interval 10
```

## Validacao da sprint HEARTBEAT

Criterios de pronto cobertos:
- Worker conecta via TCP no Master.
- Mensagens JSON com delimitador `\n`.
- Master interpreta `TASK=HEARTBEAT`.
- Worker recebe `RESPONSE=ALIVE`.
- Reconexao automatica em falha.
- Atendimento concorrente de varios Workers.

## Rodar testes

```bash
python -m unittest discover -s tests -v
```
