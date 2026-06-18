import socket
import json
import time
import uuid
import random
import os
import threading


def load_dotenv(path='.env'):
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())


load_dotenv()

HOST = os.getenv('MASTER_HOST', '127.0.0.1')
PORT = int(os.getenv('MASTER_PORT', '9000'))
MASTER_SERVER_UUID = os.getenv('MASTER_SERVER_UUID', os.getenv('SERVER_UUID', 'master_3'))

ORIGINAL_MASTER_IP   = HOST
ORIGINAL_MASTER_PORT = PORT
ORIGINAL_MASTER_ADDR = f"{ORIGINAL_MASTER_IP}:{ORIGINAL_MASTER_PORT}"

MASTER_IP   = ORIGINAL_MASTER_IP
MASTER_PORT = ORIGINAL_MASTER_PORT

WORKER_UUID = f"W-{str(uuid.uuid4())[:8].upper()}"

# Preenchido quando o worker está emprestado a outro master
SERVER_UUID_ORIGINAL: str | None = None

# Spec Sprint 2 / Sprint 3 item 7.3: worker aguarda resposta por no máximo 5s
RESPONSE_TIMEOUT = 5

HEARTBEAT_INTERVAL = 10
TASK_POLL_INTERVAL = 0.5

# Lock para proteger acesso às variáveis de estado de conexão
_state_lock = threading.Lock()


# ── Utilitários de socket ────────────────────────────────────────────────────

def conectar(host: str | None = None, port: int | None = None) -> socket.socket:
    """
    Abre conexão TCP com timeout de RESPONSE_TIMEOUT (5s) conforme spec.
    Aceita host/port opcionais para conectar a um master específico.
    """
    h = host if host is not None else MASTER_IP
    p = port if port is not None else MASTER_PORT
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Spec Sprint 2 e Sprint 3 item 7.3: timeout de 5s
    s.settimeout(RESPONSE_TIMEOUT)
    s.connect((h, p))
    return s


def enviar_json(sock: socket.socket, payload: dict):
    """Envia JSON terminado com \\n (delimitador de mensagem)."""
    sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))


def receber_json(sock: socket.socket, buf: list) -> dict:
    """
    Lê do socket até encontrar \\n e retorna o JSON parseado.
    Usa buffer acumulado para não perder bytes entre leituras.
    Respeita o timeout configurado no socket (RESPONSE_TIMEOUT = 5s).
    """
    while True:
        if "\n" in buf[0]:
            linha, buf[0] = buf[0].split("\n", 1)
            return json.loads(linha.strip())
        dados = sock.recv(4096).decode("utf-8")
        if not dados:
            raise ConnectionError("Conexão encerrada pelo master.")
        buf[0] += dados


# ── Heartbeat independente (Sprint 1) ───────────────────────────────────────

def ciclo_heartbeat():
    """
    Abre conexão separada para verificar se o master atual está ativo.
    Conexão de curta duração: connect → send HEARTBEAT → recv ALIVE → close.

    Payload enviado  : {"SERVER_UUID": "...", "TASK": "HEARTBEAT"}
    Payload esperado : {"SERVER_UUID": "...", "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}

    O timeout de 5s (RESPONSE_TIMEOUT) já está configurado em conectar().
    Se o master não responder dentro de 5s, status = OFFLINE.
    """
    with _state_lock:
        h, p = MASTER_IP, MASTER_PORT

    try:
        s = conectar(h, p)
        buf = [""]
        enviar_json(s, {
            "SERVER_UUID": SERVER_UUID_ORIGINAL or MASTER_SERVER_UUID,
            "TASK":        "HEARTBEAT",
            "WORKER_UUID": WORKER_UUID
        })
        res = receber_json(s, buf)
        s.close()
        response_val = str(res.get("RESPONSE") or res.get("response") or "UNKNOWN").upper()
        server_id    = res.get("SERVER_UUID") or res.get("server_uuid")
        print(f"[HEARTBEAT] Status: {response_val} (MASTER: {server_id})", flush=True)
    except socket.timeout:
        print(f"[HEARTBEAT] Status: OFFLINE - Timeout ({RESPONSE_TIMEOUT}s) ao aguardar resposta.", flush=True)
        _handle_master_offline()
    except Exception as e:
        print(f"[HEARTBEAT] Status: OFFLINE - {e}", flush=True)
        _handle_master_offline()


def _handle_master_offline():
    """
    CT08: master temporário perdido → retorna ao master de origem.
    Chamado quando o heartbeat detecta que o master atual está inacessível.
    """
    global MASTER_IP, MASTER_PORT, SERVER_UUID_ORIGINAL
    with _state_lock:
        if SERVER_UUID_ORIGINAL:
            print(
                f"[CT08] Master temporário offline. "
                f"Retornando ao master de origem {ORIGINAL_MASTER_ADDR}...",
                flush=True
            )
            MASTER_IP            = ORIGINAL_MASTER_IP
            MASTER_PORT          = ORIGINAL_MASTER_PORT
            SERVER_UUID_ORIGINAL = None


# ── Thread de heartbeat ──────────────────────────────────────────────────────

def _thread_heartbeat():
    """
    Thread dedicada ao heartbeat, independente do ciclo de tarefas.
    Spec Sprint 1: worker repete verificação em intervalos regulares (ex: 10s).
    """
    while True:
        time.sleep(HEARTBEAT_INTERVAL)
        ciclo_heartbeat()


# ── Registro como worker temporário ─────────────────────────────────────────

def registrar_temporario(host: str, port: int):
    """
    Após command_redirect: conecta no novo master e envia register_temporary_worker.
    Spec Sprint 3 item 2.4: worker encerra conexão com master original,
    abre nova conexão com master de destino e envia register_temporary_worker.
    """
    try:
        s = conectar(host, port)
        buf = [""]
        enviar_json(s, {
            "type":       "register_temporary_worker",
            "request_id": str(uuid.uuid4()),
            "payload": {
                "worker_id":               WORKER_UUID,
                "original_master_address": ORIGINAL_MASTER_ADDR
            }
        })
        ack = receber_json(s, buf)
        s.close()
        status = str(ack.get("STATUS") or ack.get("status") or "?").upper()
        print(f"[P2P] Registrado no master temporário ({host}:{port}). ACK: {status}", flush=True)
    except socket.timeout:
        print(
            f"[ERRO P2P] Timeout ao registrar no master temporário ({host}:{port}). "
            f"Revertendo ao master original.",
            flush=True
        )
        # CT08: se o master temporário não responder ao registro, reverte
        global MASTER_IP, MASTER_PORT, SERVER_UUID_ORIGINAL
        with _state_lock:
            MASTER_IP            = ORIGINAL_MASTER_IP
            MASTER_PORT          = ORIGINAL_MASTER_PORT
            SERVER_UUID_ORIGINAL = None
    except Exception as e:
        print(f"[ERRO P2P] Falha ao registrar no master temporário: {e}", flush=True)


# ── Payload de apresentação ──────────────────────────────────────────────────

def montar_apresentacao() -> dict:
    """
    Local     : {"WORKER": "ALIVE", "WORKER_UUID": "..."}
    Emprestado: {"WORKER": "ALIVE", "WORKER_UUID": "...", "SERVER_UUID": "<origem>"}
    Spec Sprint 2 item 1 e Sprint 3 Tarefa 04: SERVER_UUID identifica o master de origem.
    """
    payload = {"WORKER": "ALIVE", "WORKER_UUID": WORKER_UUID}
    with _state_lock:
        orig = SERVER_UUID_ORIGINAL
    if orig:
        payload["SERVER_UUID"] = orig
    return payload


# ── Ciclo de tarefa ──────────────────────────────────────────────────────────

def ciclo_tarefa():
    global MASTER_IP, MASTER_PORT, SERVER_UUID_ORIGINAL

    with _state_lock:
        h, p = MASTER_IP, MASTER_PORT

    try:
        s = conectar(h, p)
        buf = [""]
        enviar_json(s, montar_apresentacao())

        # Spec: aguarda resposta do master por no máximo RESPONSE_TIMEOUT (5s)
        resposta_master = receber_json(s, buf)

        msg_type  = resposta_master.get("type") or resposta_master.get("TYPE")
        task_raw  = resposta_master.get("TASK") or resposta_master.get("task") or ""
        task_type = str(task_raw).upper()

        # ── Mensagens com campo "type" (comandos M2M / redirecionamento) ─────
        if msg_type is not None:
            msg_type_lower = str(msg_type).lower()

            req_id  = resposta_master.get("request_id") or resposta_master.get("REQUEST_ID")
            payload = resposta_master.get("payload")    or resposta_master.get("PAYLOAD")

            # Spec Sprint 3 Nota 1: falha controlada se campos obrigatórios ausentes
            if req_id is None or payload is None:
                print(
                    f"[ERRO] Campo obrigatório ausente em mensagem type='{msg_type}'. "
                    f"Ignorando.",
                    flush=True
                )
                s.close()
                return

            # command_redirect ─────────────────────────────────────────────
            if msg_type_lower == "command_redirect":
                s.close()
                novo_endereco = payload.get("new_master_address") or payload.get("NEW_MASTER_ADDRESS")
                if not novo_endereco:
                    print("[ERRO P2P] command_redirect sem new_master_address. Ignorado.", flush=True)
                    return

                print(f"\n[P2P] command_redirect recebido! → {novo_endereco} (request_id={req_id})", flush=True)

                try:
                    novo_ip, novo_port_str = novo_endereco.split(":", 1)
                    novo_port = int(novo_port_str)
                except ValueError:
                    print(f"[ERRO P2P] Endereço inválido em command_redirect: '{novo_endereco}'.", flush=True)
                    return

                # Atualiza estado: worker agora aponta para o master temporário
                with _state_lock:
                    MASTER_IP            = novo_ip
                    MASTER_PORT          = novo_port
                    SERVER_UUID_ORIGINAL = ORIGINAL_MASTER_ADDR

                # Spec Sprint 3 item 2.4: após command_redirect, worker abre nova
                # conexão com master de destino e envia register_temporary_worker
                registrar_temporario(novo_ip, novo_port)
                return

            # command_release ──────────────────────────────────────────────
            if msg_type_lower == "command_release":
                s.close()
                release_addr = payload.get("original_master_address") or payload.get("ORIGINAL_MASTER_ADDRESS")
                print(
                    f"\n[P2P] command_release recebido! Retornando ao master original. "
                    f"(request_id={req_id})",
                    flush=True
                )

                # Determina endereço do master original
                if release_addr:
                    try:
                        ip_ret, port_ret = release_addr.split(":", 1)
                        ret_ip   = ip_ret
                        ret_port = int(port_ret)
                    except ValueError:
                        print(
                            f"[P2P AVISO] Endereço inválido ('{release_addr}'). "
                            f"Usando endereço original.",
                            flush=True
                        )
                        ret_ip   = ORIGINAL_MASTER_IP
                        ret_port = ORIGINAL_MASTER_PORT
                else:
                    ret_ip   = ORIGINAL_MASTER_IP
                    ret_port = ORIGINAL_MASTER_PORT

                with _state_lock:
                    MASTER_IP            = ret_ip
                    MASTER_PORT          = ret_port
                    SERVER_UUID_ORIGINAL = None

                print(f"[P2P] Reconectando ao master original em {ret_ip}:{ret_port}", flush=True)
                # Próximo ciclo_tarefa() já enviará ALIVE sem SERVER_UUID
                return

            # Tipo desconhecido: loga e ignora (CT09 / spec Nota 1)
            print(f"[PROTOCOLO] TYPE desconhecido: '{msg_type}'. Ignorado.", flush=True)
            s.close()
            return

        # ── Mensagens de tarefa (sem campo "type") ───────────────────────────

        # NO_TASK: nada a fazer, aguarda próximo ciclo
        if task_type == "NO_TASK":
            s.close()
            time.sleep(TASK_POLL_INTERVAL)
            return

        # QUERY: processar tarefa
        if task_type == "QUERY":
            user = resposta_master.get("USER") or resposta_master.get("user") or "?"
            # Simula processamento
            time.sleep(random.uniform(0.5, 1.5))
            status = "OK" if random.random() < 0.9 else "NOK"

            with _state_lock:
                orig = SERVER_UUID_ORIGINAL

            enviar_json(s, {
                "STATUS":      status,
                "TASK":        "QUERY",
                "WORKER_UUID": WORKER_UUID
            })

            # Spec Sprint 2: aguarda ACK do master (timeout 5s já no socket)
            ack = receber_json(s, buf)
            ack_status = str(ack.get("STATUS") or ack.get("status") or "?").upper()

            print(
                f"[TAREFA] '{user}' concluída. Status={status} | ACK={ack_status}"
                + (f" [emprestado de {orig}]" if orig else ""),
                flush=True
            )
            s.close()
            time.sleep(TASK_POLL_INTERVAL)
            return

        print(f"[PROTOCOLO] Mensagem não reconhecida do master: {resposta_master}. Ignorada.", flush=True)
        s.close()

    except socket.timeout:
        # Spec Sprint 2 / Sprint 3 item 7.3: timeout de 5s — conexão considerada perdida
        with _state_lock:
            h_cur, p_cur = MASTER_IP, MASTER_PORT
            orig = SERVER_UUID_ORIGINAL

        print(
            f"[TIMEOUT] Master ({h_cur}:{p_cur}) não respondeu em {RESPONSE_TIMEOUT}s.",
            flush=True
        )

        # CT08: master temporário não responde → reverte para master de origem
        if orig:
            print(
                f"[CT08] Master temporário perdido. "
                f"Retornando ao master de origem {ORIGINAL_MASTER_ADDR}...",
                flush=True
            )
            with _state_lock:
                MASTER_IP            = ORIGINAL_MASTER_IP
                MASTER_PORT          = ORIGINAL_MASTER_PORT
                SERVER_UUID_ORIGINAL = None

        time.sleep(TASK_POLL_INTERVAL)

    except (ConnectionRefusedError, OSError) as e:
        with _state_lock:
            h_cur, p_cur = MASTER_IP, MASTER_PORT
            orig = SERVER_UUID_ORIGINAL

        print(f"[ERRO] Falha ao conectar com master ({h_cur}:{p_cur}): {e}", flush=True)

        # CT08: master temporário caiu → retorna ao master de origem
        if orig:
            print(
                f"[CT08] Master temporário inacessível. "
                f"Retornando ao master de origem {ORIGINAL_MASTER_ADDR}...",
                flush=True
            )
            with _state_lock:
                MASTER_IP            = ORIGINAL_MASTER_IP
                MASTER_PORT          = ORIGINAL_MASTER_PORT
                SERVER_UUID_ORIGINAL = None

        time.sleep(TASK_POLL_INTERVAL)

    except Exception as e:
        print(f"[ERRO] Falha no ciclo de tarefa: {e}", flush=True)
        time.sleep(TASK_POLL_INTERVAL)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"=== WORKER {WORKER_UUID} INICIADO ===", flush=True)
    print(f"    Master inicial  : {MASTER_IP}:{MASTER_PORT}", flush=True)
    print(f"    Resposta timeout: {RESPONSE_TIMEOUT}s", flush=True)
    print(f"    Heartbeat a cada: {HEARTBEAT_INTERVAL}s", flush=True)
    print(f"    Poll a cada     : {TASK_POLL_INTERVAL}s", flush=True)

    # Sprint 1: thread dedicada ao heartbeat, independente do ciclo de tarefas
    hb_thread = threading.Thread(target=_thread_heartbeat, daemon=True, name="heartbeat")
    hb_thread.start()

    # Loop principal de tarefas
    while True:
        ciclo_tarefa()


if __name__ == "__main__":
    main()
