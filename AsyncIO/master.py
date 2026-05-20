import asyncio
import json
import math
import os
import time
from collections import deque

from protocol import (
    build_command_redirect,
    build_command_release,
    build_notify_worker_returned,
    build_request_help,
    build_response_accepted,
    build_response_rejected,
    encode_line,
    get_message_type,
    is_m2m_envelope,
    new_request_id,
    validate_envelope,
    validate_payload,
)

HOST = ""
PORT = 8000
SERVER_UUID = "Master_3"
MASTER_ID = "A"
CAPACITY = 100
RELEASE_THRESHOLD = int(CAPACITY * 0.6)
NUM_TASKS = 0
MASTER_LISTEN_ADDRESS = ""
SATURATION_CHECK_INTERVAL = 5
HELP_COOLDOWN_SECONDS = 10

task_queue = deque()
queue_lock = asyncio.Lock()
workers_lock = asyncio.Lock()
accepting_tasks = True
connected_workers: dict = {}
temporary_workers: dict = {}
load_samples: deque = deque(maxlen=10)
neighbor_masters: dict = {}
help_in_flight = False
last_help_attempt = 0.0


def validar_payload(payload, campos_obrigatorios):
    if not isinstance(payload, dict):
        return False
    return all(campo in payload for campo in campos_obrigatorios)


def peer_to_address(peername) -> str:
    if not peername:
        return ""
    host, port = peername[0], peername[1]
    return f"{host}:{port}"


def is_normalized(samples: list[int], threshold: int) -> bool:
    if len(samples) < 3:
        return False
    return all(sample < threshold for sample in samples[-3:])


def count_workers():
    local = borrowed_in = borrowed_out = 0
    for _wid, meta in connected_workers.items():
        if meta.get("temporary"):
            borrowed_in += 1
        else:
            local += 1
    return local, borrowed_in, len(temporary_workers)


def log_worker_counts(event: str):
    local, borrowed_in, pending_return = count_workers()
    print(
        f"[FARM] {event} | locais={local} emprestados_recebidos={borrowed_in} "
        f"retornos_pendentes={pending_return} fila={len(task_queue)}"
    )


async def async_decide_help_response(req_payload: dict) -> dict:
    async with queue_lock:
        current_load = len(task_queue)
    if current_load >= CAPACITY:
        return {
            "ACCEPTED": False,
            "REASON": "HIGH_LOAD",
            "WORKER_DETAILS": [],
            "NEW_MASTER_ADDRESS": None,
        }

    requester_master_id = req_payload.get("MASTER_ID")
    new_master_address = neighbor_masters.get(requester_master_id)
    if not new_master_address:
        return {
            "ACCEPTED": False,
            "REASON": "REFUSED",
            "WORKER_DETAILS": [],
            "NEW_MASTER_ADDRESS": None,
        }

    try:
        needed = int(req_payload.get("WORKERS_NEEDED", 0))
    except (TypeError, ValueError):
        return {
            "ACCEPTED": False,
            "REASON": "REFUSED",
            "WORKER_DETAILS": [],
            "NEW_MASTER_ADDRESS": None,
        }

    available = []
    async with workers_lock:
        for worker_id, metadata in connected_workers.items():
            if (
                not metadata.get("temporary")
                and metadata.get("address")
                and not metadata.get("busy")
                and metadata.get("writer")
            ):
                available.append({"ID": worker_id, "ADDRESS": metadata["address"]})

    if needed <= 0 or len(available) < needed:
        return {
            "ACCEPTED": False,
            "REASON": "NO_WORKERS_AVAILABLE",
            "WORKER_DETAILS": [],
            "NEW_MASTER_ADDRESS": None,
        }

    return {
        "ACCEPTED": True,
        "REASON": None,
        "WORKER_DETAILS": available[:needed],
        "NEW_MASTER_ADDRESS": new_master_address,
    }


def read_num_tasks_from_env(path: str):
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "NUM_TASKS":
                    return int(v.strip())
    except (ValueError, OSError):
        return None
    return None


def read_master_config():
    global HOST, PORT, SERVER_UUID, MASTER_ID, CAPACITY, RELEASE_THRESHOLD
    global NUM_TASKS, MASTER_LISTEN_ADDRESS

    paths = [
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
    ]
    for env_path in paths:
        if not os.path.exists(env_path):
            continue
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key == "HOST":
                        HOST = value
                    elif key == "PORT":
                        PORT = int(value)
                    elif key == "SERVER_UUID":
                        SERVER_UUID = value
                    elif key == "MASTER_ID":
                        MASTER_ID = value
                    elif key == "CAPACITY":
                        CAPACITY = int(value)
                        RELEASE_THRESHOLD = int(CAPACITY * 0.6)
                    elif key == "NEIGHBOR_MASTERS":
                        for item in value.split(","):
                            if "=" in item:
                                m_id, address = item.split("=", 1)
                                if m_id.strip() and address.strip():
                                    neighbor_masters[m_id.strip()] = address.strip()
                    elif key == "NUM_TASKS":
                        try:
                            NUM_TASKS = int(value)
                        except ValueError:
                            NUM_TASKS = 0
                    elif key == "MASTER_LISTEN_ADDRESS":
                        MASTER_LISTEN_ADDRESS = value
        except OSError:
            pass

    if not MASTER_LISTEN_ADDRESS:
        bind_host = HOST if HOST else "127.0.0.1"
        MASTER_LISTEN_ADDRESS = f"{bind_host}:{PORT}"


def input_task_cli(loop):
    global accepting_tasks
    while True:
        try:
            user_input = input(
                "[MASTER CLI] Digite 'add_task <user_name>', 'delete_task', 'clear', 'stop' ou 'list': "
            )
            if user_input.startswith("add_task "):
                if not accepting_tasks:
                    print("[FILA] Entrada de tasks desativada.")
                    continue
                user_name = user_input.replace("add_task ", "", 1).strip()
                if user_name:
                    asyncio.run_coroutine_threadsafe(enqueue_task(user_name), loop)
                else:
                    print("[ERRO] Digite: add_task <user_name>")
            elif user_input == "delete_task":
                asyncio.run_coroutine_threadsafe(delete_task(), loop)
            elif user_input == "clear":
                asyncio.run_coroutine_threadsafe(clear_tasks(), loop)
            elif user_input == "stop":
                accepting_tasks = False
                print("[FILA] Entrada de novas tasks desativada.")
            elif user_input == "list":
                asyncio.run_coroutine_threadsafe(list_tasks(), loop)
            else:
                print("[ERRO] Comando inválido.")
        except Exception as e:
            print(f"[ERRO CLI] {e}")


async def register_worker_connection(
    worker_id: str,
    reader,
    writer,
    addr,
    *,
    temporary: bool = False,
    original_master_address: str | None = None,
):
    address = peer_to_address(addr)
    async with workers_lock:
        connected_workers[worker_id] = {
            "reader": reader,
            "writer": writer,
            "address": address,
            "temporary": temporary,
            "busy": False,
            "peer": addr,
        }
        if temporary and original_master_address:
            temporary_workers[worker_id] = original_master_address
    log_worker_counts(f"Worker {worker_id} registrado")


async def unregister_worker(worker_id: str):
    async with workers_lock:
        connected_workers.pop(worker_id, None)
        temporary_workers.pop(worker_id, None)
    log_worker_counts(f"Worker {worker_id} desconectado")


async def send_redirect_commands(worker_details: list[dict], new_master_address: str):
    for detail in worker_details:
        worker_id = detail.get("ID")
        async with workers_lock:
            metadata = connected_workers.get(worker_id, {})
            worker_writer = metadata.get("writer")
        if not worker_writer:
            print(f"[M2M] Worker {worker_id} sem conexão ativa para redirect")
            continue
        command = build_command_redirect(new_request_id(), new_master_address)
        ts = time.strftime("%H:%M:%S")
        print(f"[M2M] {ts} EMIT COMMAND_REDIRECT worker={worker_id} -> {new_master_address}")
        try:
            worker_writer.write(encode_line(command))
            await worker_writer.drain()
            async with workers_lock:
                if worker_id in connected_workers:
                    connected_workers[worker_id]["redirected"] = True
        except Exception as e:
            print(f"[ERRO] Falha ao redirecionar worker {worker_id}: {e}")


async def notify_worker_returned_to_master(worker_id: str, original_master_address: str):
    for attempt in range(1, 4):
        try:
            host, port_str = original_master_address.rsplit(":", 1)
            _reader, writer = await asyncio.open_connection(host, int(port_str))
            notify = build_notify_worker_returned(new_request_id(), worker_id)
            ts = time.strftime("%H:%M:%S")
            print(f"[M2M] {ts} EMIT NOTIFY_WORKER_RETURNED worker={worker_id} -> {original_master_address}")
            writer.write(encode_line(notify))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        except Exception as e:
            print(f"[ERRO] NOTIFY_WORKER_RETURNED {worker_id} tentativa {attempt}/3: {e}")


async def maybe_release_temporary_worker(worker_id: str, worker_writer):
    async with workers_lock:
        original_master_address = temporary_workers.get(worker_id)
    if not original_master_address:
        return
    if not is_normalized(list(load_samples), RELEASE_THRESHOLD):
        return

    release = build_command_release(new_request_id(), original_master_address)
    ts = time.strftime("%H:%M:%S")
    print(f"[M2M] {ts} EMIT COMMAND_RELEASE worker={worker_id}")
    try:
        notify_task = asyncio.create_task(
            notify_worker_returned_to_master(worker_id, original_master_address)
        )
        worker_writer.write(encode_line(release))
        await worker_writer.drain()
        await notify_task
        async with workers_lock:
            temporary_workers.pop(worker_id, None)
            if worker_id in connected_workers:
                connected_workers[worker_id]["temporary"] = False
        print(f"[EMPRESTIMO] Ciclo encerrado: devolução de {worker_id} para {original_master_address}")
        log_worker_counts("Devolução concluída")
    except Exception as e:
        print(f"[ERRO] Falha ao liberar worker temporário {worker_id}: {e}")


def calc_workers_needed(current_load: int) -> int:
    excess = max(0, current_load - CAPACITY)
    if excess == 0:
        return 0
    return max(1, math.ceil(excess / 10))


async def request_help_from_neighbor(neighbor_master_id: str, address: str) -> bool:
    request_id = new_request_id()
    writer = None
    ts = time.strftime("%H:%M:%S")
    try:
        async with queue_lock:
            current_load = len(task_queue)
        workers_needed = calc_workers_needed(current_load)

        host, port_str = address.rsplit(":", 1)
        reader, writer = await asyncio.open_connection(host, int(port_str))
        request_help = build_request_help(
            request_id, MASTER_ID, current_load, CAPACITY, workers_needed
        )
        print(
            f"[M2M] {ts} EMIT REQUEST_HELP -> {neighbor_master_id} "
            f"REQUEST_ID={request_id} LOAD={current_load} NEEDED={workers_needed}"
        )
        writer.write(encode_line(request_help))
        await writer.drain()

        data = await asyncio.wait_for(reader.readline(), timeout=5)
        if not data:
            print(f"[M2M] Timeout sem resposta de {neighbor_master_id} REQUEST_ID={request_id}")
            return False

        response = json.loads(data.decode().strip())
        rtype = get_message_type(response)
        resp_id = response.get("REQUEST_ID")
        if resp_id != request_id:
            print(f"[M2M] REQUEST_ID divergente: enviado={request_id} recebido={resp_id}")
            return False

        print(f"[M2M] RECV {rtype} de {neighbor_master_id} REQUEST_ID={request_id}")
        if rtype == "RESPONSE_ACCEPTED":
            offered = response.get("PAYLOAD", {}).get("WORKERS_OFFERED", 0)
            print(f"[M2M] Ajuda aceita WORKERS_OFFERED={offered}")
            return True
        if rtype == "RESPONSE_REJECTED":
            reason = response.get("PAYLOAD", {}).get("REASON", "UNKNOWN")
            print(f"[M2M] Ajuda rejeitada REASON={reason}")
        return False
    except asyncio.TimeoutError:
        print(f"[M2M] Timeout 5s aguardando {neighbor_master_id} REQUEST_ID={request_id}")
        return False
    except Exception as e:
        print(f"[M2M] Erro REQUEST_HELP {neighbor_master_id}: {e}")
        return False
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


async def saturation_monitor():
    global help_in_flight, last_help_attempt
    while True:
        await asyncio.sleep(SATURATION_CHECK_INTERVAL)
        async with queue_lock:
            current_load = len(task_queue)
        load_samples.append(current_load)

        if current_load <= CAPACITY:
            continue

        now = time.monotonic()
        if help_in_flight or (now - last_help_attempt) < HELP_COOLDOWN_SECONDS:
            continue

        if not neighbor_masters:
            print("[M2M] Saturado mas sem NEIGHBOR_MASTERS configurados")
            continue

        help_in_flight = True
        last_help_attempt = now
        print(f"[M2M] Saturação detectada: load={current_load} capacity={CAPACITY}")

        accepted = False
        for neighbor_id, address in neighbor_masters.items():
            if await request_help_from_neighbor(neighbor_id, address):
                accepted = True
                break

        if not accepted:
            print("[M2M] Nenhum vizinho aceitou o pedido de ajuda")
        help_in_flight = False


async def tratar_m2m(payload: dict, reader, writer, addr) -> bool:
    msg_type = get_message_type(payload)
    ts = time.strftime("%H:%M:%S")

    if msg_type == "REQUEST_HELP":
        if not validate_envelope(payload) or not validate_payload(
            payload.get("PAYLOAD", {}),
            {"MASTER_ID", "CURRENT_LOAD", "CAPACITY", "WORKERS_NEEDED"},
        ):
            print(f"[ERRO] REQUEST_HELP inválido de {addr}")
            return True

        request_id = payload["REQUEST_ID"]
        print(f"[M2M] {ts} RECV REQUEST_HELP REQUEST_ID={request_id} de {addr}")
        decision = await async_decide_help_response(payload["PAYLOAD"])
        if decision["ACCEPTED"]:
            response = build_response_accepted(request_id, decision["WORKER_DETAILS"])
            writer.write(encode_line(response))
            await writer.drain()
            print(f"[M2M] {ts} EMIT RESPONSE_ACCEPTED REQUEST_ID={request_id}")
            await send_redirect_commands(
                decision["WORKER_DETAILS"], decision["NEW_MASTER_ADDRESS"]
            )
        else:
            response = build_response_rejected(request_id, decision["REASON"])
            writer.write(encode_line(response))
            await writer.drain()
            print(f"[M2M] {ts} EMIT RESPONSE_REJECTED REQUEST_ID={request_id} REASON={decision['REASON']}")
        return True

    if msg_type == "NOTIFY_WORKER_RETURNED":
        if not validate_envelope(payload):
            print(f"[ERRO] NOTIFY_WORKER_RETURNED inválido de {addr}")
            return True
        worker_id = payload.get("PAYLOAD", {}).get("WORKER_ID")
        print(f"[M2M] {ts} RECV NOTIFY_WORKER_RETURNED worker={worker_id} REQUEST_ID={payload.get('REQUEST_ID')}")
        async with workers_lock:
            if worker_id in connected_workers:
                connected_workers[worker_id]["redirected"] = False
                connected_workers[worker_id]["busy"] = False
        log_worker_counts("Worker devolvido notificado")
        return True

    print(f"[M2M] Tipo desconhecido ignorado: {msg_type} de {addr}")
    return True


async def tratar_sprint02(payload: dict, reader, writer, addr) -> bool:
    msg_type = get_message_type(payload)

    if msg_type == "REGISTER_TEMPORARY_WORKER":
        if not validate_envelope(payload) or not validate_payload(
            payload.get("PAYLOAD", {}),
            {"WORKER_ID", "ORIGINAL_MASTER_ADDRESS"},
        ):
            print(f"[ERRO] REGISTER_TEMPORARY_WORKER inválido de {addr}")
            return True
        p = payload["PAYLOAD"]
        worker_id = p["WORKER_ID"]
        original = p["ORIGINAL_MASTER_ADDRESS"]
        print(
            f"[EMPRESTIMO] Registro temporário worker={worker_id} origem={original} "
            f"REQUEST_ID={payload.get('REQUEST_ID')}"
        )
        await register_worker_connection(
            worker_id, reader, writer, addr, temporary=True, original_master_address=original
        )
        return True

    if payload.get("WORKER") == "ALIVE":
        if not validar_payload(payload, {"WORKER", "WORKER_UUID"}):
            print(f"[ERRO] Payload ALIVE inválido de {addr}")
            return True

        worker_uuid = payload["WORKER_UUID"]
        server_uuid_field = payload.get("SERVER_UUID")
        is_remote = bool(server_uuid_field and server_uuid_field != SERVER_UUID)

        async with workers_lock:
            existing = connected_workers.get(worker_uuid)
            if not existing or existing.get("writer") is not writer:
                connected_workers[worker_uuid] = {
                    "reader": reader,
                    "writer": writer,
                    "address": peer_to_address(addr),
                    "temporary": is_remote,
                    "busy": False,
                    "peer": addr,
                }
                if is_remote and server_uuid_field:
                    for nid, naddr in neighbor_masters.items():
                        if nid == server_uuid_field or server_uuid_field in naddr:
                            temporary_workers[worker_uuid] = naddr
                            break
                    if worker_uuid not in temporary_workers:
                        temporary_workers[worker_uuid] = server_uuid_field

        async with queue_lock:
            if task_queue:
                user_name = task_queue.popleft()
                resposta = {"TASK": "QUERY", "USER": user_name}
                async with workers_lock:
                    if worker_uuid in connected_workers:
                        connected_workers[worker_uuid]["busy"] = True
                print(
                    f"[TASK DISTRIBUIDA] Worker {'REMOTO' if is_remote else 'LOCAL'} "
                    f"- {addr} - USER: {user_name}"
                )
            else:
                resposta = {"TASK": "NO_TASK"}
                print(f"[NO TASK] Worker {'REMOTO' if is_remote else 'LOCAL'} - {addr}")

        writer.write(encode_line(resposta))
        await writer.drain()
        return True

    if payload.get("STATUS") in ("OK", "NOK") and payload.get("TASK") == "QUERY":
        if not validar_payload(payload, {"STATUS", "TASK", "WORKER_UUID"}):
            print(f"[ERRO] Payload de resultado inválido de {addr}")
            return True

        worker_uuid = payload.get("WORKER_UUID", "unknown")
        is_borrowed = worker_uuid in temporary_workers
        print(
            f"[RESULTADO] Worker {worker_uuid} STATUS={payload.get('STATUS')} "
            f"{'(emprestado)' if is_borrowed else ''}"
        )

        async with workers_lock:
            if worker_uuid in connected_workers:
                connected_workers[worker_uuid]["busy"] = False

        ack = {"STATUS": "ACK", "WORKER_UUID": worker_uuid}
        writer.write(encode_line(ack))
        await writer.drain()
        print(f"[ACK] Enviado para {worker_uuid}")

        await maybe_release_temporary_worker(worker_uuid, writer)
        return True

    return False


async def tratar_conexao(reader, writer):
    addr = writer.get_extra_info("peername")
    worker_id_for_cleanup = None
    print(f"[ASYNC] Conexão iniciada com {addr}")

    try:
        while True:
            data = await reader.readline()
            if not data:
                break

            mensagem = data.decode().strip()
            if not mensagem:
                continue

            try:
                payload = json.loads(mensagem)
            except json.JSONDecodeError as e:
                print(f"[ERRO] JSON inválido de {addr}: {e}")
                continue

            if payload.get("WORKER_UUID"):
                worker_id_for_cleanup = payload["WORKER_UUID"]
            elif payload.get("PAYLOAD", {}).get("WORKER_ID"):
                worker_id_for_cleanup = payload["PAYLOAD"]["WORKER_ID"]

            if is_m2m_envelope(payload):
                handled = await tratar_m2m(payload, reader, writer, addr)
                if handled:
                    continue

            if not await tratar_sprint02(payload, reader, writer, addr):
                print(f"[ERRO] Payload não tratado de {addr}: {payload}")

    except Exception as e:
        print(f"[ERRO] Falha com {addr}: {e}")
    finally:
        if worker_id_for_cleanup:
            async with workers_lock:
                meta = connected_workers.get(worker_id_for_cleanup, {})
                redirected = meta.get("redirected")
            if not redirected:
                await unregister_worker(worker_id_for_cleanup)
        print(f"[ASYNC] Fechando conexão com {addr}")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def enqueue_task(user_name):
    async with queue_lock:
        task_queue.append(user_name)
        print(f"[FILA] Tarefa adicionada: {user_name} | Total: {len(task_queue)}")


async def delete_task():
    async with queue_lock:
        if task_queue:
            removed = task_queue.popleft()
            print(f"[FILA] Tarefa removida: {removed} | Total: {len(task_queue)}")
        else:
            print("[FILA] Vazia - nada para remover")


async def clear_tasks():
    async with queue_lock:
        quantidade = len(task_queue)
        task_queue.clear()
        print(f"[FILA] Limpa. {quantidade} tarefa(s) removida(s).")


async def list_tasks():
    async with queue_lock:
        if task_queue:
            print(f"[FILA] {len(task_queue)} tarefa(s): {list(task_queue)}")
        else:
            print("[FILA] Vazia")


async def iniciar_master():
    read_master_config()
    loop = asyncio.get_running_loop()
    input_thread = __import__("threading").Thread(target=input_task_cli, args=(loop,), daemon=True)
    input_thread.start()
    asyncio.create_task(saturation_monitor())

    module_env = os.path.join(os.path.dirname(__file__), "..", ".env")
    workspace_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    num = read_num_tasks_from_env(module_env) or read_num_tasks_from_env(workspace_env)
    if num is None and NUM_TASKS > 0:
        num = NUM_TASKS
    if num and num > 0:
        print(f"[STARTUP] Populando fila com {num} tarefas")
        for i in range(1, num + 1):
            await enqueue_task(f"user_{i}")

    server = await asyncio.start_server(tratar_conexao, HOST, PORT)
    print(f"Master {SERVER_UUID} (id={MASTER_ID}) ativo em {HOST}:{PORT}")
    print(f"[CONFIG] MASTER_LISTEN_ADDRESS={MASTER_LISTEN_ADDRESS} CAPACITY={CAPACITY} RELEASE={RELEASE_THRESHOLD}")
    if neighbor_masters:
        print(f"[CONFIG] Vizinhos: {neighbor_masters}")
    print(
        "[INFO] CLI: add_task <user>, delete_task, clear, stop, list"
    )
    log_worker_counts("Inicialização")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(iniciar_master())
    except KeyboardInterrupt:
        print("\n[SERVIDOR] Encerrando...")
