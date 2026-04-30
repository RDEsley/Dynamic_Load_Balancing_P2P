import asyncio
import json
from collections import deque

HOST = '10.62.217.31'
PORT = 8000
SERVER_UUID = "Master_3"

task_queue = deque()
queue_lock = asyncio.Lock()
accepting_tasks = True


def validar_payload(payload, campos_obrigatorios):
    if not isinstance(payload, dict):
        return False
    return all(campo in payload for campo in campos_obrigatorios)


def input_task_cli(loop):
    """Thread de apoio para enfileirar e remover tarefas de teste sem bloquear o servidor."""
    global accepting_tasks
    while True:
        try:
            user_input = input("[MASTER CLI] Digite 'add_task <user_name>', 'delete_task', 'clear', 'stop' ou 'list': ")

            if user_input.startswith("add_task "):
                if not accepting_tasks:
                    print("[FILA] Entrada de tasks desativada. Use 'stop' ou reinicie o Master para habilitar novamente.")
                    continue

                user_name = user_input.replace("add_task ", "", 1).strip()
                if user_name:
                    asyncio.run_coroutine_threadsafe(enqueue_task(user_name), loop)
                    print(f"[TASK ADICIONADA] {user_name}")
                else:
                    print("[ERRO] Digite: add_task <user_name>")
            elif user_input == "delete_task":
                asyncio.run_coroutine_threadsafe(delete_task(), loop)
            elif user_input == "clear":
                asyncio.run_coroutine_threadsafe(clear_tasks(), loop)
            elif user_input == "stop":
                accepting_tasks = False
                print("[FILA] Entrada de novas tasks desativada. Tasks pendentes continuam até serem consumidas.")
            elif user_input == "list":
                asyncio.run_coroutine_threadsafe(list_tasks(), loop)
            else:
                print("[ERRO] Comando inválido. Use 'add_task <user_name>', 'delete_task', 'clear', 'stop' ou 'list'")
        except Exception as e:
            print(f"[ERRO CLI] {str(e)}")


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
    loop = asyncio.get_running_loop()
    input_thread = __import__("threading").Thread(target=input_task_cli, args=(loop,), daemon=True)
    input_thread.start()

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