import socket
import json
import time

HOST = '10.62.217.31'
PORT = 8000
SERVER_UUID = "Master_3"
WORKER_UUID = "Worker_1"  # Hardcoded - Único para este worker

def is_remote_worker():
    """Verifica se o Worker está em IP diferente do Master"""
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        return local_ip != HOST
    except:
        return False

def enviar_heartbeat():
    while True:
        try:
            # Tenta estabelecer conexão TCP (Tarefa 01) [cite: 66, 79]
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5) # Timeout para evitar travamentos
            s.connect((HOST, PORT))
            
            # Novo Payload - WORKER alive signal (Tarefa 02) [cite: 70]
            payload = {
                "WORKER": "ALIVE",
                "WORKER_UUID": WORKER_UUID
            }
            
            # Adiciona SERVER_UUID se for Worker remoto
            if is_remote_worker():
                payload["SERVER_UUID"] = SERVER_UUID
            
            # Log do payload antes de enviar
            print(f"[LOG] Enviando payload: {json.dumps(payload)}")
            
            # Envio com delimitador \n [cite: 67]
            s.sendall((json.dumps(payload) + "\n").encode('utf-8'))
            
            # Aguarda resposta
            data = s.recv(1024).decode('utf-8')
            if data:
                res = json.loads(data.strip())
                print(f"[LOG] Resposta do Master: {json.dumps(res)}") # DoD Sucesso [cite: 81, 94]
                
                if res.get("TASK") == "QUERY":
                    user = res.get("USER")
                    print(f"[TASK] Executando tarefa para: {user}")
                    try:
                        time.sleep(1)
                        resultado = {
                            "STATUS": "OK",
                            "TASK": "QUERY",
                            "WORKER_UUID": WORKER_UUID
                        }
                    except Exception:
                        resultado = {
                            "STATUS": "NOK",
                            "TASK": "QUERY",
                            "WORKER_UUID": WORKER_UUID
                        }

                    s.sendall((json.dumps(resultado) + "\n").encode('utf-8'))

                    ack_data = s.recv(1024).decode('utf-8')
                    if ack_data:
                        ack = json.loads(ack_data.strip())
                        print(f"[LOG] ACK do Master: {json.dumps(ack)}")
                elif res.get("TASK") == "NO_TASK":
                    print(f"[INFO] Nenhuma tarefa disponível no momento")
            
            s.close()
        except (ConnectionRefusedError, socket.timeout, Exception) as e:
            print(f"[LOG] Status: OFFLINE - {str(e)} - Tentando Reconectar") # DoD Falha [cite: 97]
        
        # Intervalo entre verificações (Tarefa 04) [cite: 76]
        time.sleep(30)

if __name__ == "__main__":
    print("Iniciando Worker (Thread)...")
    enviar_heartbeat()
