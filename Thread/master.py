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

def input_task_cli():
    """Thread para adicionar tarefas à fila via input CLI (não bloqueia o servidor)"""
    while True:
        try:
            # Aguarda input do usuário
            user_input = input("[MASTER CLI] Digite 'add_task <user_name>' ou 'list': ")
            
            if user_input.startswith("add_task "):
                # Extrai o nome do usuário
                user_name = user_input.replace("add_task ", "").strip()
                if user_name:
                    with queue_lock:
                        task_queue.append(user_name)
                        print(f"[TASK ADICIONADA] {user_name} - Fila agora tem {len(task_queue)} tarefa(s)")
                else:
                    print("[ERRO] Digite: add_task <user_name>")
            
            elif user_input == "list":
                with queue_lock:
                    if task_queue:
                        print(f"[FILA] {len(task_queue)} tarefa(s): {list(task_queue)}")
                    else:
                        print("[FILA] Vazia")
            
            else:
                print("[ERRO] Comando inválido. Use 'add_task <user_name>' ou 'list'")
        
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
                
                # Lógica de Resposta - Novo formato com fila (Tarefa 03)
                if payload.get("WORKER") == "ALIVE":
                    # Detecta se é Worker local ou remoto
                    is_remote = "SERVER_UUID" in payload
                    
                    # Acessa fila de tarefas (thread-safe)
                    with queue_lock:
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
                    
                    # Envia resposta com o delimitador \n [cite: 67]
                    conn.sendall((json.dumps(resposta) + "\n").encode('utf-8'))
        
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
