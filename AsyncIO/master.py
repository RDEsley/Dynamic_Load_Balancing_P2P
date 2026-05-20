import asyncio
import json
import os
import uuid
from collections import deque

HOST = '10.62.217.31'
PORT = 8000
SERVER_UUID = "Master_3"
MASTER_ID = "A"
CAPACITY = 100
NORMALIZED_THRESHOLD = 80
NUM_TASKS = 0

task_queue = deque()
queue_lock = asyncio.Lock()
accepting_tasks = True
VALID_REASONS = {"HIGH_LOAD", "NO_WORKERS_AVAILABLE", "REFUSED"}
connected_workers = {}
temporary_workers = {}
load_samples = deque(maxlen=10)
neighbor_masters = {}


def validar_payload(payload, campos_obrigatorios):
    if not isinstance(payload, dict):
        return False
    return all(campo in payload for campo in campos_obrigatorios)


def build_response_rejected(request_id: str, reason: str) -> dict:
    if reason not in VALID_REASONS:
        reason = "REFUSED"
    return {
        "TYPE": "RESPONSE_REJECTED",
        "REQUEST_ID": request_id,
        "PAYLOAD": {"REASON": reason},
    }


def build_response_accepted(request_id: str, worker_details: list[dict]) -> dict:
    normalized_details = []
    for detail in worker_details:
        worker_id = detail.get("ID") or detail.get("WORKER_ID")
        address = detail.get("ADDRESS")
        if worker_id and address:
            normalized_details.append({"ID": worker_id, "ADDRESS": address})

    return {
        "TYPE": "RESPONSE_ACCEPTED",
        "REQUEST_ID": request_id,
        "PAYLOAD": {
            "WORKERS_OFFERED": len(normalized_details),
            "WORKER_DETAILS": normalized_details,
        },
    }


def build_command_release(request_id: str, original_master_address: str) -> dict:
    return {
        "TYPE": "COMMAND_RELEASE",
        "REQUEST_ID": request_id,
        "PAYLOAD": {"ORIGINAL_MASTER_ADDRESS": original_master_address},
    }


def build_notify_worker_returned(request_id: str, worker_id: str) -> dict:
    return {
        "TYPE": "NOTIFY_WORKER_RETURNED",
        "REQUEST_ID": request_id,
        "PAYLOAD": {"WORKER_ID": worker_id},
    }


def is_normalized(load_samples: list[int], threshold: int) -> bool:
    if len(load_samples) < 3:
        return False
    return all(sample < threshold for sample in load_samples[-3:])


def decide_help_response(req_payload: dict) -> dict:
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
    except Exception:
        return {
            "ACCEPTED": False,
            "REASON": "REFUSED",
            "WORKER_DETAILS": [],
            "NEW_MASTER_ADDRESS": None,
        }
    available = []
    for worker_id, metadata in connected_workers.items():
        if not metadata.get("temporary") and metadata.get("address"):
            available.append({"ID": worker_id, "ADDRESS": metadata["address"]})

    if len(available) < needed or needed <= 0:
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


def read_master_config():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key == "NEIGHBOR_MASTERS":
                    for item in value.split(","):
                        if "=" in item:
                            m_id, address = item.split("=", 1)
                            if m_id.strip() and address.strip():
                                neighbor_masters[m_id.strip()] = address.strip()
                elif key == "NUM_TASKS":
                    try:
                        global NUM_TASKS
                        NUM_TASKS = int(value)
                    except Exception:
                        NUM_TASKS = 0
    except Exception:
        pass


async def build_task_response(addr, is_remote=False):
    async with queue_lock:
        if task_queue:
            user_name = task_queue.popleft()
            response = {"TASK": "QUERY", "USER": user_name}
            print(f"[TASK DISTRIBUIDA] Worker {'REMOTO' if is_remote else 'LOCAL'} - {addr} - USER: {user_name}")
            return response
        print(f"[NO TASK] Worker {'REMOTO' if is_remote else 'LOCAL'} - {addr}")
        return {"TASK": "NO_TASK"}


async def send_redirect_commands(worker_details: list[dict], new_master_address: str):
    for detail in worker_details:
        worker_id = detail.get("ID")
        metadata = connected_workers.get(worker_id, {})
        worker_writer = metadata.get("writer")
        if not worker_writer:
            continue

        command_redirect = {
            "TYPE": "COMMAND_REDIRECT",
            "REQUEST_ID": str(uuid.uuid4()).upper(),
            "PAYLOAD": {"NEW_MASTER_ADDRESS": new_master_address},
        }
        try:
            worker_writer.write((json.dumps(command_redirect) + "\n").encode())
            await worker_writer.drain()
        except Exception as e:
            print(f"[ERRO] Falha ao redirecionar worker {worker_id}: {e}")


async def notify_worker_returned(worker_id: str, original_master_address: str):
    for attempt in range(1, 4):
        try:
            host, port_str = original_master_address.rsplit(":", 1)
            _reader, writer = await asyncio.open_connection(host, int(port_str))
            notify = build_notify_worker_returned(str(uuid.uuid4()).upper(), worker_id)
            writer.write((json.dumps(notify) + "\n").encode())
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        except Exception as e:
            print(f"[ERRO] Falha em NOTIFY_WORKER_RETURNED para {worker_id} (tentativa {attempt}/3): {e}")
    print(f"[ERRO] NOTIFY_WORKER_RETURNED não resolvido para {worker_id} após 3 tentativas")


async def maybe_release_temporary_worker(worker_id: str, worker_writer):
    original_master_address = temporary_workers.get(worker_id)
    if not original_master_address:
        return
    if not is_normalized(list(load_samples), NORMALIZED_THRESHOLD):
        return

    release = build_command_release(str(uuid.uuid4()).upper(), original_master_address)
    try:
        notify_task = asyncio.create_task(notify_worker_returned(worker_id, original_master_address))
        worker_writer.write((json.dumps(release) + "\n").encode())
        await worker_writer.drain()
        await notify_task
        temporary_workers.pop(worker_id, None)
    except Exception as e:
        print(f"[ERRO] Falha ao liberar worker temporário {worker_id}: {e}")


async def request_help_from_neighbor(neighbor_master_id: str, address: str):
    request_id = str(uuid.uuid4()).upper()
    writer = None
    try:
        host, port_str = address.rsplit(":", 1)
        reader, writer = await asyncio.open_connection(host, int(port_str))
        request_help = {
            "TYPE": "REQUEST_HELP",
            "REQUEST_ID": request_id,
            "PAYLOAD": {
                "MASTER_ID": MASTER_ID,
                "CURRENT_LOAD": len(task_queue),
                "CAPACITY": CAPACITY,
                "WORKERS_NEEDED": 1,
            },
        }
        writer.write((json.dumps(request_help) + "\n").encode())
        await writer.drain()

        data = await asyncio.wait_for(reader.readline(), timeout=5)
        if not data:
            print(f"[M2M] Sem resposta de {neighbor_master_id} REQUEST_ID={request_id}")
        else:
            response = json.loads(data.decode().strip())
            rtype = response.get("TYPE")
            if response.get("REQUEST_ID") != request_id:
                print(f"[M2M] REQUEST_ID divergente de {neighbor_master_id}: enviado={request_id} recebido={response.get('REQUEST_ID')}")
            elif rtype == "RESPONSE_ACCEPTED":
                offered = response.get("PAYLOAD", {}).get("WORKERS_OFFERED", 0)
                print(f"[M2M] Ajuda aceita por {neighbor_master_id} REQUEST_ID={request_id} WORKERS_OFFERED={offered}")
            elif rtype == "RESPONSE_REJECTED":
                reason = response.get("PAYLOAD", {}).get("REASON", "UNKNOWN")
                print(f"[M2M] Ajuda rejeitada por {neighbor_master_id} REQUEST_ID={request_id} REASON={reason}")

    except Exception as e:
        print(f"[M2M] Erro em REQUEST_HELP para {neighbor_master_id} ({address}) REQUEST_ID={request_id}: {e}")
    finally:
        if writer:
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


async def tratar_worker(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"[ASYNC] Conexão iniciada com {addr}")

    try:
        while True:
            data = await reader.readline()
            if not data:
                break

            mensagem = data.decode().strip()
            if not mensagem:
                continue

            payload = json.loads(mensagem)

            if payload.get("WORKER") == "ALIVE":
                if not validar_payload(payload, {"WORKER", "WORKER_UUID"}):
                    print(f"[ERRO] Payload ALIVE inválido ignorado de {addr}")
                    continue

                is_remote = payload.get("SERVER_UUID") != SERVER_UUID

                async with queue_lock:
                    if task_queue:
                        user_name = task_queue.popleft()
                        resposta = {
                            "TASK": "QUERY",
                            "USER": user_name
                        }
                        print(f"[TASK DISTRIBUIDA] Worker {'REMOTO' if is_remote else 'LOCAL'} - {addr} - USER: {user_name}")
                    else:
                        resposta = {
                            "TASK": "NO_TASK"
                        }
                        print(f"[NO TASK] Worker {'REMOTO' if is_remote else 'LOCAL'} - {addr}")

                writer.write((json.dumps(resposta) + "\n").encode())
                await writer.drain()

            elif payload.get("STATUS") in ("OK", "NOK") and payload.get("TASK") == "QUERY":
                if not validar_payload(payload, {"STATUS", "TASK", "WORKER_UUID"}):
                    print(f"[ERRO] Payload inválido de resultado ignorado de {addr}")
                    continue

                worker_uuid = payload.get("WORKER_UUID", "unknown")
                print(f"[RESULTADO] Worker {worker_uuid} respondeu com STATUS={payload.get('STATUS')}")

                ack = {
                    "STATUS": "ACK",
                    "WORKER_UUID": worker_uuid
                }
                writer.write((json.dumps(ack) + "\n").encode())
                await writer.drain()
                print(f"[ACK] Enviado para {worker_uuid}")
            else:
                print(f"[ERRO] Payload desconhecido ou incompleto ignorado de {addr}: {payload}")

    except Exception as e:
        print(f"[ERRO] Falha com {addr}: {e}")
    finally:
        print(f"[ASYNC] Fechando conexão com {addr}")
        writer.close()
        await writer.wait_closed()

async def iniciar_master():
    read_master_config()
    loop = asyncio.get_running_loop()
    input_thread = __import__("threading").Thread(target=input_task_cli, args=(loop,), daemon=True)
    input_thread.start()
    asyncio.create_task(saturation_monitor())
    # initialize artificial tasks from .env NUM_TASKS
    if NUM_TASKS and NUM_TASKS > 0:
        for i in range(NUM_TASKS):
            await enqueue_task(f"auto_user_{i+1}")

    server = await asyncio.start_server(tratar_worker, HOST, PORT)
    print(f"Master {SERVER_UUID} (AsyncIO) ativo em {HOST}:{PORT}")
    print("[INFO] Digite 'add_task <user_name>' para adicionar tarefas, 'delete_task' para remover a primeira, 'clear' para limpar, 'stop' para parar novas entradas e 'list' para listar")

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(iniciar_master())
    except KeyboardInterrupt:
        print("\n[SERVIDOR] Encerrando...")