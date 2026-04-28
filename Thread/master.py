import socket
import threading
import json
from collections import deque

HOST = '10.62.217.31'
PORT = 8000
SERVER_UUID = "Master_3"

# Fila global de tarefas (FIFO)
task_queue = deque()
queue_lock = threading.Lock()  # Lock para acesso thread-safe
accepting_tasks = True


def validar_payload(payload, campos_obrigatorios):
    if not isinstance(payload, dict):
        return False
    return all(campo in payload for campo in campos_obrigatorios)

def input_task_cli():
    """Thread para adicionar e remover tarefas da fila via input CLI (não bloqueia o servidor)"""
    global accepting_tasks
    while True:
        try:
            user_input = input("[MASTER CLI] Digite 'add_task <user_name>', 'delete_task', 'clear', 'stop' ou 'list': ")
            
            if user_input.startswith("add_task "):
                if not accepting_tasks:
                    print("[FILA] Entrada de tasks desativada. Use 'stop' ou reinicie o Master para habilitar novamente.")
                    continue

                user_name = user_input.replace("add_task ", "").strip()
                if user_name:
                    with queue_lock:
                        task_queue.append(user_name)
                        print(f"[TASK ADICIONADA] {user_name} - Fila agora tem {len(task_queue)} tarefa(s)")
                else:
                    print("[ERRO] Digite: add_task <user_name>")

            elif user_input == "delete_task":
                with queue_lock:
                    if task_queue:
                        removed = task_queue.popleft()
                        print(f"[TASK REMOVIDA] {removed} - Fila agora tem {len(task_queue)} tarefa(s)")
                    else:
                        print("[FILA] Vazia - nada para remover")

            elif user_input == "clear":
                with queue_lock:
                    quantidade = len(task_queue)
                    task_queue.clear()
                    print(f"[FILA] Limpa. {quantidade} tarefa(s) removida(s).")

            elif user_input == "stop":
                accepting_tasks = False
                print("[FILA] Entrada de novas tasks desativada. Tasks pendentes continuam até serem consumidas.")
            
            elif user_input == "list":
                with queue_lock:
                    if task_queue:
                        print(f"[FILA] {len(task_queue)} tarefa(s): {list(task_queue)}")
                    else:
                        print("[FILA] Vazia")
            
            else:
                print("[ERRO] Comando inválido. Use 'add_task <user_name>', 'delete_task', 'clear', 'stop' ou 'list'")
        
        except Exception as e:
            print(f"[ERRO CLI] {str(e)}")

def tratar_cliente(conn, addr):
    try:
        print(f"[THREAD] Conexão ativa com {addr}")
        # Buffer para acumular dados até encontrar o delimitador \n
        buffer = ""
        while True:
            data = conn.recv(1024).decode('utf-8')
            if not data: break
            
            buffer += data
            if "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                payload = json.loads(line)
                
                # Lógica de distribuição de tarefa (Master -> Worker)
                if payload.get("WORKER") == "ALIVE":
                    if not validar_payload(payload, {"WORKER", "WORKER_UUID"}):
                        print(f"[ERRO] Payload ALIVE inválido ignorado de {addr}")
                        continue

                    is_remote = "SERVER_UUID" in payload
                    
                    with queue_lock:
                        if task_queue:
                            user_name = task_queue.popleft()
                            resposta = {"TASK": "QUERY", "USER": user_name}
                            print(f"[TASK DISTRIBUIDA] Worker {'REMOTO' if is_remote else 'LOCAL'} - {addr} - USER: {user_name}")
                        else:
                            resposta = {"TASK": "NO_TASK"}
                            print(f"[NO TASK] Worker {'REMOTO' if is_remote else 'LOCAL'} - {addr}")
                    
                    conn.sendall((json.dumps(resposta) + "\n").encode('utf-8'))

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
                    conn.sendall((json.dumps(ack) + "\n").encode('utf-8'))
                    print(f"[ACK] Enviado para {worker_uuid}")
                else:
                    print(f"[ERRO] Payload desconhecido ou incompleto ignorado de {addr}: {payload}")
        
    except Exception as e:
        print(f"[ERRO] Falha com {addr}: {e}")
    finally:
        conn.close()

def iniciar_servidor():
    # Inicia thread para input CLI (não bloqueia o servidor)
    cli_thread = threading.Thread(target=input_task_cli, daemon=True)
    cli_thread.start()
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(100)
    print(f"Master {SERVER_UUID} ativo em {HOST}:{PORT}")
    print(f"[INFO] Digite 'add_task <user_name>' para adicionar tarefas à fila")

    while True:
        conn, addr = s.accept()
        # Uso de Threads para não bloquear o Master (Tarefa 04) [cite: 75]
        threading.Thread(target=tratar_cliente, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    try:
        iniciar_servidor()
    except KeyboardInterrupt:
        print("\n[SERVIDOR] Encerrando...")
