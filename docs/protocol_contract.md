# Protocolo Oficial - P2P Dynamic Load Balancing

## 1) Objetivo

Este documento define o contrato de interoperabilidade entre `Master` e `Worker`, e entre `Master` e `Master`.
As equipes devem interoperar **apenas por este protocolo**, sem dependência de implementação interna.

## 2) Transporte e framing

- Transporte: TCP.
- Formato de mensagem: JSON UTF-8.
- Delimitador obrigatório: `\n` ao final de cada mensagem.
- Cada conexão pode transportar múltiplas mensagens.

Exemplo de envio:

```text
{"SERVER_UUID":"Master_A","TASK":"HEARTBEAT"}\n
```

## 3) Campos base

Campos obrigatórios para todas as mensagens:

- `SERVER_UUID` (`string`): identificador único de quem envia a mensagem.
- `TASK` (`string`): tipo da operação.

Campos opcionais comuns:

- `PROTOCOL_VERSION` (`string`): versão do protocolo (padrão: `1.0`).
- `TIMESTAMP` (`string` ISO-8601): instante da geração da mensagem.
- `REQUEST_ID` (`string`): correlaciona request/response.

## 4) Mensagens oficiais

### 4.1 HEARTBEAT

Worker -> Master:

```json
{
  "SERVER_UUID": "Worker_1",
  "TASK": "HEARTBEAT"
}
```

Master -> Worker:

```json
{
  "SERVER_UUID": "Master_A",
  "TASK": "HEARTBEAT",
  "RESPONSE": "ALIVE"
}
```

### 4.2 LOAD_STATUS_REQUEST / LOAD_STATUS_RESPONSE (Master <-> Master)

Request:

```json
{
  "SERVER_UUID": "Master_A",
  "TASK": "LOAD_STATUS_REQUEST",
  "REQUEST_ID": "req-123"
}
```

Response:

```json
{
  "SERVER_UUID": "Master_B",
  "TASK": "LOAD_STATUS_RESPONSE",
  "REQUEST_ID": "req-123",
  "RESPONSE": "OK",
  "AVAILABLE_WORKERS": 3,
  "BORROWED_WORKERS": 1,
  "PENDING_REQUESTS": 2
}
```

### 4.3 BORROW_WORKER_REQUEST / BORROW_WORKER_RESPONSE (Master <-> Master)

Request:

```json
{
  "SERVER_UUID": "Master_A",
  "TASK": "BORROW_WORKER_REQUEST",
  "REQUEST_ID": "req-456",
  "COUNT": 1,
  "LEASE_SECONDS": 120
}
```

Response (aceito):

```json
{
  "SERVER_UUID": "Master_B",
  "TASK": "BORROW_WORKER_RESPONSE",
  "REQUEST_ID": "req-456",
  "RESPONSE": "ACCEPTED",
  "LEASE_ID": "lease-xyz",
  "COUNT": 1,
  "LEASE_SECONDS": 120
}
```

Response (negado):

```json
{
  "SERVER_UUID": "Master_B",
  "TASK": "BORROW_WORKER_RESPONSE",
  "REQUEST_ID": "req-456",
  "RESPONSE": "REJECTED",
  "ERROR_CODE": "INSUFFICIENT_WORKERS",
  "ERROR_MESSAGE": "No spare workers available"
}
```

### 4.4 RETURN_WORKER_REQUEST / RETURN_WORKER_RESPONSE (Master <-> Master)

Request:

```json
{
  "SERVER_UUID": "Master_A",
  "TASK": "RETURN_WORKER_REQUEST",
  "REQUEST_ID": "req-789",
  "LEASE_ID": "lease-xyz",
  "COUNT": 1
}
```

Response:

```json
{
  "SERVER_UUID": "Master_B",
  "TASK": "RETURN_WORKER_RESPONSE",
  "REQUEST_ID": "req-789",
  "RESPONSE": "OK",
  "LEASE_ID": "lease-xyz"
}
```

## 5) Erros padronizados

Formato de erro:

```json
{
  "SERVER_UUID": "Master_A",
  "TASK": "ERROR",
  "REQUEST_ID": "req-123",
  "RESPONSE": "ERROR",
  "ERROR_CODE": "INVALID_PAYLOAD",
  "ERROR_MESSAGE": "Missing TASK field"
}
```

`ERROR_CODE` recomendado:

- `INVALID_JSON`
- `INVALID_PAYLOAD`
- `UNKNOWN_TASK`
- `TIMEOUT`
- `INSUFFICIENT_WORKERS`
- `LEASE_NOT_FOUND`

## 6) Timeouts e retry

- Heartbeat do Worker: a cada 10 a 30 segundos.
- Timeout de leitura/escrita TCP: 3 a 5 segundos.
- Retry de reconexão Worker -> Master: exponencial simples (1s, 2s, 4s, ... até 10s).
- Retry Master -> Master: até 3 tentativas por operação crítica.

## 7) Regras de compatibilidade

- Campos desconhecidos devem ser ignorados (forward compatibility).
- `TASK` desconhecida deve gerar `ERROR` com `UNKNOWN_TASK`.
- Mudanças incompatíveis exigem incremento de major em `PROTOCOL_VERSION`.

## 8) Definição de pronto para interoperabilidade

- Mensagens serializadas com `\n`.
- Respeito aos campos obrigatórios.
- Tratamento consistente de erros padronizados.
- Suporte ao HEARTBEAT e pelo menos um ciclo completo de empréstimo/retorno (`BORROW` + `RETURN`).
