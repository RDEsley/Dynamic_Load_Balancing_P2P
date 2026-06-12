import socket
import threading
import json
import time
import os
import uuid
from collections import deque
from threading import Lock


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

HOST        = os.getenv('MASTER_HOST', '0.0.0.0')
PORT        = int(os.getenv('MASTER_PORT', '9000'))
SERVER_UUID = os.getenv('SERVER_UUID', f'MASTER_{PORT}')

# Vizinhos: "ip:porta,ip:porta"
NEIGHBORS = [item.strip() for item in os.getenv('NEIGHBORS', '').split(',') if item.strip()]

TASK_COUNT           = int(os.getenv('TASK_COUNT', '0'))
SATURATION_THRESHOLD = int(os.getenv('CAPACITY', '10'))
RELEASE_THRESHOLD    = int(os.getenv('RELEASE_THRESHOLD', '4'))

# ── Timeouts (spec: worker aguarda resposta por no máximo 5s) ─────────────────
# Conexões M2M (negociação entre masters): 5s conforme spec Sprint 3 item 7.4
M2M_TIMEOUT       = 5
# Sessão persistente worker↔master: usa recv loop com timeout menor para
# não bloquear indefinidamente; o worker já tem seu próprio timeout de 5s
# na conexão (settimeout no conectar()), então aqui usamos 30s como limite
# seguro para sessões estabelecidas sem atividade.
SESSION_TIMEOUT   = 30

# ── Locks ────────────────────────────────────────────────────────────────────
fila_lock  = Lock()
state_lock = Lock()
log_lock   = Lock()

# ── Fila de tarefas ──────────────────────────────────────────────────────────
fila_tarefas: deque = deque()

# ── Contadores de tarefas (Sprint 3 - Tarefa 07) ────────────────────────────
tasks_completed: int = 0
tasks_failed:    int = 0

# ── Registro de workers ──────────────────────────────────────────────────────
workers_conectados:          dict  = {}
workers_emprestados:         dict  = {}
meus_workers_emprestados:    dict  = {}
workers_para_liberar:        set   = set()
redirecionamentos_pendentes: int   = 0
fila_destinos_redirect:      deque = deque()
ultimo_request_help:         float = 0.0
REQUEST_HELP_COOLDOWN:       int   = 15


# ── Log ──────────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    with log_lock:
        print(f"[{ts}] {msg}", flush=True)


def log_estado_workers():
    """Sprint 3 Tarefa 07 — exibe contagem de workers a cada mudança de estado."""
    with state_lock:
        total     = len(workers_conectados)
        locais    = total - len(workers_emprestados)
        recebidos = len(workers_emprestados)
        enviados  = len(meus_workers_emprestados)
        ocupados  = sum(1 for w in workers_conectados.values() if w.get('busy'))
    log(f"[WORKERS] total={total} locais={locais} recebidos={recebidos} "
        f"enviados={enviados} ocupados={ocupados} ociosos={total - ocupados}")


def new_request_id() -> str:
    return str(uuid.uuid4())


# ── I/O de socket ────────────────────────────────────────────────────────────

def enviar_linha(conn: socket.socket, payload: dict):
    conn.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))


def ler_linha(conn: socket.socket, buffer_state: list) -> dict:
    """
    Lê do socket acumulando bytes no buffer até encontrar \\n.
    Respeita o timeout configurado no socket (SESSION_TIMEOUT para sessões
    persistentes, M2M_TIMEOUT para negociações entre masters).
    """
    buffer = buffer_state[0]
    while True:
        if "\n" in buffer:
            linha, resto = buffer.split("\n", 1)
            buffer_state[0] = resto
            return json.loads(linha.strip())
        dados = conn.recv(4096).decode("utf-8")
        if not dados:
            if buffer.strip():
                buffer_state[0] = ""
                return json.loads(buffer.strip())
            raise ConnectionError("Conexão fechada pelo host remoto.")
        buffer += dados


# ── Gerador de tarefas ───────────────────────────────────────────────────────

def gerador_de_tarefas():
    usuarios = ["Gale", "ShadowHeart", "Varka", "Wriothesley", "Firefly"]
    contador = 0
    while True:
        time.sleep(1)
        if TASK_COUNT > 0 and contador >= TASK_COUNT:
            time.sleep(1)
            continue
        user = usuarios[contador % len(usuarios)]
        with fila_lock:
            fila_tarefas.append({"TASK": "QUERY", "USER": user})
        if contador % 5 == 0:
            with fila_lock:
                log(f"[FILA] {len(fila_tarefas)} tarefas pendentes.")
        contador += 1


# ── Monitor de carga (saturação + normalização) ──────────────────────────────

def monitorar_carga():
    while True:
        time.sleep(5)

        with fila_lock:
            carga_atual = len(fila_tarefas)

        with state_lock:
            pending_redirects = redirecionamentos_pendentes
            has_borrowed = any(
                wid in workers_conectados
                for wid in workers_emprestados
            )

        agora = time.time()
        with state_lock:
            tempo_desde_ultima = agora - ultimo_request_help

        pode_tentar = (
            pending_redirects == 0
            and not has_borrowed
            and tempo_desde_ultima >= REQUEST_HELP_COOLDOWN
        )

        if carga_atual >= SATURATION_THRESHOLD and pode_tentar:
            log(f"[CARGA] Saturação detectada ({carga_atual} tarefas). Enviando request_help...")
            _solicitar_ajuda(carga_atual)

        if carga_atual <= RELEASE_THRESHOLD and has_borrowed:
            log(f"[CARGA] Fila normalizada ({carga_atual} tarefas). Marcando workers para devolução...")
            with state_lock:
                for w_id in list(workers_emprestados.keys()):
                    workers_para_liberar.add(w_id)
            log(f"[DEVOLUÇÃO] Workers marcados: {list(workers_emprestados.keys())}")


# ── Protocolo M2M: solicitar ajuda ──────────────────────────────────────────

def _solicitar_ajuda(carga_atual: int):
    """
    Percorre NEIGHBORS tentando obter workers emprestados.
    CT03: request_id único por chamada.
    CT07: timeout de 5s por vizinho (M2M_TIMEOUT) — descarta e tenta próximo.
    """
    global redirecionamentos_pendentes, ultimo_request_help

    with state_lock:
        ultimo_request_help = time.time()

    if not NEIGHBORS:
        log('[M2M] Nenhum vizinho configurado em NEIGHBORS.')
        return

    req_id         = new_request_id()
    workers_needed = max(1, carga_atual - SATURATION_THRESHOLD + 2)
    meu_addr       = f"{HOST}:{PORT}"

    msg = {
        "type":       "request_help",
        "request_id": req_id,
        "payload": {
            "master_id":      SERVER_UUID,
            "current_load":   carga_atual,
            "capacity":       SATURATION_THRESHOLD,
            "workers_needed": workers_needed,
            "master_port":    PORT,
        }
    }

    for peer in NEIGHBORS:
        try:
            peer_host, peer_port_str = peer.split(':', 1)
            peer_port = int(peer_port_str)

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # CT07: timeout de exatamente 5s conforme spec Sprint 3 item 7.4
            s.settimeout(M2M_TIMEOUT)
            s.connect((peer_host, peer_port))
            enviar_linha(s, msg)
            log(f"[M2M] request_help enviado → {peer} (request_id={req_id})")

            buf = [""]
            res = ler_linha(s, buf)
            s.close()

            res_type = str(res.get("type") or res.get("TYPE") or "").lower()
            res_id   = res.get("request_id") or res.get("REQUEST_ID")

            # CT03: correlação de request_id
            if res_id != req_id:
                log(f"[M2M AVISO] request_id da resposta ({res_id}) != enviado ({req_id}). Ignorando.")
                continue

            if res_type == "response_accepted":
                p       = res.get("payload") or res.get("PAYLOAD") or {}
                offered = int(p.get("workers_offered") or p.get("WORKERS_OFFERED") or workers_needed)
                log(f"[M2M] response_accepted de {peer}. {offered} worker(s) a caminho. (request_id={req_id})")
                with state_lock:
                    redirecionamentos_pendentes += offered
                    for _ in range(offered):
                        fila_destinos_redirect.append(meu_addr)
                return

            elif res_type == "response_rejected":
                p      = res.get("payload") or res.get("PAYLOAD") or {}
                reason = p.get("reason") or p.get("REASON") or "desconhecido"
                log(f"[M2M] response_rejected de {peer}. Motivo: {reason}. Tentando próximo... (request_id={req_id})")

            else:
                # CT09: tipo desconhecido — loga e ignora
                log(f"[M2M] Tipo de resposta desconhecido de {peer}: '{res_type}'. Ignorado.")

        except socket.timeout:
            # CT07: timeout de 5s — descarta request_id e tenta próximo vizinho
            log(f"[M2M TIMEOUT] {peer} não respondeu em {M2M_TIMEOUT}s. "
                f"request_id={req_id} descartado. Tentando próximo...")
        except Exception as e:
            log(f"[M2M ERRO] Falha ao contactar {peer}: {e}")


# ── Protocolo M2M: notificar devolução ──────────────────────────────────────

def _enviar_notify_worker_returned(worker_id: str, origem_addr: str):
    """notify_worker_returned (Master A → Master B) — Sprint 3 spec 2.5b"""
    try:
        ip, port_str = origem_addr.split(":", 1)
        port = int(port_str)
    except ValueError:
        log(f"[M2M ERRO] Endereço inválido para notify_worker_returned: {origem_addr}")
        return

    req_id = new_request_id()
    msg = {
        "type":       "notify_worker_returned",
        "request_id": req_id,
        "payload":    {"worker_id": worker_id}
    }
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(M2M_TIMEOUT)
        s.connect((ip, port))
        enviar_linha(s, msg)
        s.close()
        log(f"[M2M] notify_worker_returned → {ip}:{port} worker='{worker_id}' (request_id={req_id})")
    except Exception as e:
        log(f"[M2M ERRO] Falha ao enviar notify_worker_returned: {e}")


# ── Handler de conexão (sessão persistente) ──────────────────────────────────

def tratar_cliente(conn: socket.socket, addr):
    """
    Trata uma conexão persistente. Pode vir de:
      - Worker próprio ou emprestado  (campo WORKER ou TASK=HEARTBEAT)
      - Master vizinho                (campo 'type', protocolo M2M Sprint 3)

    Timeout de sessão: SESSION_TIMEOUT (30s) para detectar workers inativos.
    Aceita chaves em MAIÚSCULO ou minúsculo para interoperabilidade (O6).
    """
    global redirecionamentos_pendentes, tasks_completed, tasks_failed

    worker_uuid_sessao = None
    buffer_state       = [""]

    try:
        # Timeout de sessão: detecta inatividade em conexões estabelecidas.
        # Diferente do timeout de 5s do worker (que é no connect()), este
        # controla quanto tempo o master aguarda nova mensagem do worker.
        conn.settimeout(SESSION_TIMEOUT)

        while True:
            try:
                payload = ler_linha(conn, buffer_state)
            except socket.timeout:
                # Worker ficou silencioso por SESSION_TIMEOUT — encerra sessão limpa
                log(f"[SESSÃO TIMEOUT] Worker '{worker_uuid_sessao}' inativo por {SESSION_TIMEOUT}s. Encerrando.")
                break
            except (ConnectionError, OSError):
                break
            except json.JSONDecodeError:
                log(f"[PARSE ERRO] JSON inválido de {addr}. Ignorando.")
                continue

            # ── Mensagens M2M (possuem campo "type") ─────────────────────────
            msg_type_raw = payload.get("type") or payload.get("TYPE")
            if msg_type_raw is not None:
                msg_type = str(msg_type_raw).lower()

                # ── request_help ─────────────────────────────────────────────
                if msg_type == "request_help":
                    req_id          = payload.get("request_id") or payload.get("REQUEST_ID")
                    peer_p          = payload.get("payload") or payload.get("PAYLOAD") or {}
                    workers_pedidos = int(peer_p.get("workers_needed") or peer_p.get("WORKERS_NEEDED") or 1)

                    peer_ip          = addr[0]
                    peer_port_recv   = int(peer_p.get("master_port") or peer_p.get("MASTER_PORT") or PORT)
                    solicitante_addr = f"{peer_ip}:{peer_port_recv}"

                    with fila_lock:
                        minha_carga = len(fila_tarefas)

                    if minha_carga < SATURATION_THRESHOLD:
                        with state_lock:
                            redirecionamentos_pendentes += workers_pedidos
                            for _ in range(workers_pedidos):
                                fila_destinos_redirect.append(solicitante_addr)

                            ociosos = [
                                wid for wid, info in workers_conectados.items()
                                if not info.get('busy')
                                and wid not in meus_workers_emprestados
                                and wid not in workers_emprestados
                            ]

                        detalhes = [
                            {"id": wid, "address": f"{addr[0]}:{addr[1]}"}
                            for wid in ociosos[:workers_pedidos]
                        ]

                        resposta = {
                            "type":       "response_accepted",
                            "request_id": req_id,
                            "payload": {
                                "workers_offered": workers_pedidos,
                                "worker_details":  detalhes,
                            }
                        }
                        log(f"[M2M] request_help ACEITO. {workers_pedidos} worker(s) → {solicitante_addr}. (request_id={req_id})")
                    else:
                        resposta = {
                            "type":       "response_rejected",
                            "request_id": req_id,
                            "payload":    {"reason": "high_load"}
                        }
                        log(f"[M2M] request_help RECUSADO (carga={minha_carga}). (request_id={req_id})")

                    enviar_linha(conn, resposta)
                    # Conexão M2M é de curta duração (request/response) — encerra após responder
                    break

                # ── notify_worker_returned ───────────────────────────────────
                if msg_type == "notify_worker_returned":
                    req_id = payload.get("request_id") or payload.get("REQUEST_ID")
                    p      = payload.get("payload") or payload.get("PAYLOAD") or {}
                    w_id   = p.get("worker_id") or p.get("WORKER_ID") or "UNK"
                    with state_lock:
                        meus_workers_emprestados.pop(w_id, None)
                    log(f"[M2M] notify_worker_returned. Worker '{w_id}' devolvido. (request_id={req_id})")
                    log_estado_workers()
                    break

                # ── register_temporary_worker ────────────────────────────────
                if msg_type == "register_temporary_worker":
                    req_id = payload.get("request_id") or payload.get("REQUEST_ID")
                    p      = payload.get("payload") or payload.get("PAYLOAD") or {}

                    w_id        = p.get("worker_id") or p.get("WORKER_ID")
                    origem_addr = p.get("original_master_address") or p.get("ORIGINAL_MASTER_ADDRESS")

                    # Sprint 3 Nota 1: falha controlada se campos obrigatórios ausentes
                    if not w_id:
                        log(f"[ERRO] register_temporary_worker sem worker_id. Ignorando. (request_id={req_id})")
                        continue
                    if not origem_addr:
                        log(f"[ERRO] register_temporary_worker sem original_master_address. Ignorando. (request_id={req_id})")
                        continue

                    with state_lock:
                        workers_emprestados[w_id] = origem_addr
                        workers_conectados[w_id]  = {'busy': False, 'conn': conn, 'addr': addr}
                    worker_uuid_sessao = w_id

                    enviar_linha(conn, {"STATUS": "ACK", "WORKER_UUID": w_id})
                    log(f"[P2P] Worker emprestado '{w_id}' registrado. Origem: {origem_addr} (request_id={req_id})")
                    log(f"[CICLO-VIDA] Worker '{w_id}': emprestado de {origem_addr} → agora ativo aqui.")
                    log_estado_workers()
                    continue

                # ── CT09: tipo desconhecido — loga e ignora ──────────────────
                log(f"[M2M] TYPE desconhecido: '{msg_type_raw}'. Ignorado.")
                continue

            # ── Mensagens de Worker ──────────────────────────────────────────

            task_raw = payload.get("TASK") or payload.get("task") or ""
            task_val = str(task_raw).upper()

            # Sprint 1: HEARTBEAT
            if task_val == "HEARTBEAT":
                worker_uuid_hb = payload.get("WORKER_UUID") or payload.get("worker_uuid")
                enviar_linha(conn, {
                    "SERVER_UUID": SERVER_UUID,
                    "TASK":        "HEARTBEAT",
                    "RESPONSE":    "ALIVE"
                })
                log(f"[HEARTBEAT] Respondido para Worker '{worker_uuid_hb}'.")
                # Heartbeat usa conexão de curta duração (connect → send → recv → close)
                break

            # Sprint 2: WORKER ALIVE — apresentação / pedido de tarefa
            worker_raw = payload.get("WORKER") or payload.get("worker") or ""
            if str(worker_raw).upper() == "ALIVE":
                worker_uuid      = payload.get("WORKER_UUID") or payload.get("worker_uuid") or "DESCONHECIDO"
                server_uuid_orig = payload.get("SERVER_UUID") or payload.get("server_uuid")
                worker_uuid_sessao = worker_uuid

                with state_lock:
                    if worker_uuid not in workers_conectados:
                        workers_conectados[worker_uuid] = {'busy': False, 'conn': conn, 'addr': addr}

                # Worker local retornando de empréstimo (sem SERVER_UUID)
                if not server_uuid_orig:
                    with state_lock:
                        if worker_uuid in meus_workers_emprestados:
                            addr_temp = meus_workers_emprestados.pop(worker_uuid)
                            log(f"[P2P] Worker '{worker_uuid}' retornou de {addr_temp}.")
                            log_estado_workers()
                        workers_emprestados.pop(worker_uuid, None)

                # Sprint 3: verificar se há redirecionamento pendente
                redirect_now     = False
                destino_redirect = ""
                with state_lock:
                    if not server_uuid_orig and redirecionamentos_pendentes > 0 and fila_destinos_redirect:
                        redirecionamentos_pendentes -= 1
                        destino_redirect = fila_destinos_redirect.popleft()
                        redirect_now     = True

                if redirect_now:
                    req_id = new_request_id()
                    enviar_linha(conn, {
                        "type":       "command_redirect",
                        "request_id": req_id,
                        "payload":    {"new_master_address": destino_redirect}
                    })
                    with state_lock:
                        meus_workers_emprestados[worker_uuid] = destino_redirect
                    log(f"[P2P] command_redirect → Worker '{worker_uuid}' para {destino_redirect} (request_id={req_id})")
                    log(f"[CICLO-VIDA] Worker '{worker_uuid}': enviado para {destino_redirect}.")
                    log_estado_workers()
                    break

                # Sprint 3: verificar se worker emprestado deve ser devolvido
                release_now = False
                if server_uuid_orig:
                    with state_lock:
                        if worker_uuid in workers_para_liberar:
                            workers_para_liberar.discard(worker_uuid)
                            workers_emprestados.pop(worker_uuid, None)
                            workers_conectados.pop(worker_uuid, None)
                            release_now = True

                if release_now:
                    req_id = new_request_id()
                    enviar_linha(conn, {
                        "type":       "command_release",
                        "request_id": req_id,
                        "payload":    {"original_master_address": server_uuid_orig}
                    })
                    log(f"[DEVOLUÇÃO] command_release → Worker '{worker_uuid}' volta para {server_uuid_orig} (request_id={req_id})")
                    log(f"[CICLO-VIDA] Worker '{worker_uuid}': devolvido para {server_uuid_orig}.")
                    log_estado_workers()
                    threading.Thread(
                        target=_enviar_notify_worker_returned,
                        args=(worker_uuid, server_uuid_orig),
                        daemon=True
                    ).start()
                    break

                # Sprint 2: distribuir tarefa ou informar fila vazia
                with fila_lock:
                    tarefa = fila_tarefas.popleft() if fila_tarefas else None

                if tarefa:
                    with state_lock:
                        if worker_uuid in workers_conectados:
                            workers_conectados[worker_uuid]['busy'] = True

                    enviar_linha(conn, tarefa)
                    try:
                        resultado  = ler_linha(conn, buffer_state)
                        status_val = str(resultado.get("STATUS") or resultado.get("status") or "?").upper()

                        if status_val not in ("OK", "NOK"):
                            log(f"[AVISO] STATUS inválido '{status_val}' de '{worker_uuid}'. Aceito mesmo assim.")

                        with state_lock:
                            if status_val == "OK":
                                tasks_completed += 1
                            else:
                                tasks_failed += 1
                            if worker_uuid in workers_conectados:
                                workers_conectados[worker_uuid]['busy'] = False

                        log(f"[TAREFA] Worker '{worker_uuid}' concluiu. STATUS={status_val}"
                            + (f" [EMPRESTADO de {server_uuid_orig}]" if server_uuid_orig else " [LOCAL]")
                            + f" | concluídas={tasks_completed} falhas={tasks_failed}")

                        enviar_linha(conn, {"STATUS": "ACK", "WORKER_UUID": worker_uuid})
                    except Exception as e:
                        log(f"[ERRO SESSÃO] Falha ao processar tarefa do worker '{worker_uuid}': {e}")
                        with fila_lock:
                            fila_tarefas.appendleft(tarefa)
                        with state_lock:
                            if worker_uuid in workers_conectados:
                                workers_conectados[worker_uuid]['busy'] = False
                        break
                else:
                    enviar_linha(conn, {"TASK": "NO_TASK"})

                # Sessão de tarefa é de curta duração (apresentação → tarefa → status → ack)
                # Worker fecha e reabre conexão a cada ciclo
                break

            log(f"[PROTOCOLO] Mensagem não reconhecida de {addr}: {payload}. Ignorada.")

    except Exception as e:
        log(f"[CONEXÃO FECHADA] Sessão encerrada ({addr}): {e}")
    finally:
        if worker_uuid_sessao:
            with state_lock:
                workers_conectados.pop(worker_uuid_sessao, None)
                workers_emprestados.pop(worker_uuid_sessao, None)
                workers_para_liberar.discard(worker_uuid_sessao)
        conn.close()


# ── Inicialização ────────────────────────────────────────────────────────────

def iniciar_master():
    threading.Thread(target=gerador_de_tarefas, daemon=True).start()
    threading.Thread(target=monitorar_carga,    daemon=True).start()
    log(f"[INIT] Threads de carga e gerador iniciadas.")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(100)
    log(f"=== MASTER '{SERVER_UUID}' ON-LINE EM {HOST}:{PORT} ===")
    log(f"    Saturation threshold : {SATURATION_THRESHOLD} tarefas")
    log(f"    Release threshold    : {RELEASE_THRESHOLD} tarefas")
    log(f"    Session timeout      : {SESSION_TIMEOUT}s")
    log(f"    M2M timeout          : {M2M_TIMEOUT}s")
    log(f"    Vizinhos configurados: {NEIGHBORS or 'nenhum'}")

    while True:
        try:
            conn, addr = s.accept()
            threading.Thread(target=tratar_cliente, args=(conn, addr), daemon=True).start()
        except KeyboardInterrupt:
            log("Master encerrado pelo usuário.")
            break
        except Exception as e:
            log(f"[ERRO ACEITAR CONEXÃO] {e}")


if __name__ == '__main__':
    iniciar_master()
