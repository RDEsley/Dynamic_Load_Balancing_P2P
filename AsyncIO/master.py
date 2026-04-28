import asyncio
import json
import threading
from collections import deque

HOST = '192.168.0.45'
PORT = 8000
SERVER_UUID = "Master_3"

# Fila global de tarefas (FIFO)
task_queue = deque()
queue_lock = asyncio.Lock()  # Lock para acesso thread-safe

async def input_task_thread():
    """Thread para adicionar tarefas à fila via input CLI (não bloqueia o servidor)"""
    loop = asyncio.get_event_loop()
    while True:
        try:
            # Aguarda input do usuário
            user_input = await loop.run_in_executor(None, input, "[MASTER CLI] Digite 'add_task <user_name>' ou 'list': ")
            
            if user_input.startswith("add_task "):
                # Extrai o nome do usuário
                user_name = user_input.replace("add_task ", "").strip()
                if user_name:
                    async with queue_lock:
                        task_queue.append(user_name)
                        print(f"[TASK ADICIONADA] {user_name} - Fila agora tem {len(task_queue)} tarefa(s)")
                else:
                    print("[ERRO] Digite: add_task <user_name>")
            
            elif user_input == "list":
                async with queue_lock:
                    if task_queue:
                        print(f"[FILA] {len(task_queue)} tarefa(s): {list(task_queue)}")
                    else:
                        print("[FILA] Vazia")
            
            else:
                print("[ERRO] Comando inválido. Use 'add_task <user_name>' ou 'list'")
        
        except Exception as e:
            print(f"[ERRO CLI] {str(e)}")

async def tratar_worker(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"[ASYNC] Conexão iniciada com {addr}")

    try:
        while True:
            # Lê até o delimitador \n definido no protocolo [cite: 39, 67]
            data = await reader.readline()
            if not data:
                break

            mensagem = data.decode().strip()
            if mensagem:
                payload = json.loads(mensagem)
                
                # Lógica de Heartbeat - Novo formato com fila (Tarefa 03) [cite: 71, 72]
                if payload.get("WORKER") == "ALIVE":
                    # Detecta se é Worker local ou remoto
                    is_remote = "SERVER_UUID" in payload
                    
                    # Acessa fila de tarefas (thread-safe)
                    async with queue_lock:
                        if task_queue:
                            # Se há tarefas, remove e envia a primeira (FIFO)
                            user_name = task_queue.popleft()
                            resposta = {
                                "TASK": "QUERY",
                                "USER": user_name
                            }
                            print(f"[TASK DISTRIBUIDA] Worker {'REMOTO' if is_remote else 'LOCAL'} - {addr} - USER: {user_name}")
                        else:
                            # Se não há tarefas
                            resposta = {
                                "TASK": "NO_TASK"
                            }
                            print(f"[NO TASK] Worker {'REMOTO' if is_remote else 'LOCAL'} - {addr}")
                    
                    # Envia a resposta com \n [cite: 73]
                    writer.write((json.dumps(resposta) + "\n").encode())
                    await writer.drain()

    except Exception as e:
        print(f"[ERRO] Falha com {addr}: {e}")
    finally:
        print(f"[ASYNC] Fechando conexão com {addr}")
        writer.close()
        await writer.wait_closed()

async def iniciar_master():
    # Configura o Master como servidor (Tarefa 01) [cite: 65]
    server = await asyncio.start_server(tratar_worker, HOST, PORT)
    print(f"Master {SERVER_UUID} (AsyncIO) ativo em {HOST}:{PORT}")
    print(f"[INFO] Digite 'add_task <user_name>' para adicionar tarefas à fila")
    
    # Inicia thread para input CLI (não bloqueia o servidor)
    input_thread = threading.Thread(target=lambda: asyncio.run(input_task_thread()), daemon=True)
    input_thread.start()

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(iniciar_master())
    except KeyboardInterrupt:
        print("\n[SERVIDOR] Encerrando...")
