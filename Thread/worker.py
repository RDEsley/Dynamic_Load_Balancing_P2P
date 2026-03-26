import socket
import json
import time

HOST = '10.62.217.31'
PORT = 8000
SERVER_UUID = "Master_3"

def enviar_heartbeat():
    while True:
        try:
            # Tenta estabelecer conexão TCP (Tarefa 01) [cite: 66, 79]
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5) # Timeout para evitar travamentos
            s.connect((HOST, PORT))
            
            # Payload Oficial (Tarefa 02) [cite: 70]
            payload = {
                "SERVER_UUID": SERVER_UUID,
                "TASK": "HEARTBEAT"
            }
            
            # Envio com delimitador \n [cite: 67]
            s.sendall((json.dumps(payload) + "\n").encode('utf-8'))
            
            # Aguarda resposta
            data = s.recv(1024).decode('utf-8')
            if data:
                res = json.loads(data.strip())
                if res.get("RESPONSE") == "ALIVE":
                    print(f"[LOG] Status: ALIVE") # DoD Sucesso [cite: 81, 94]
            
            s.close()
        except (ConnectionRefusedError, socket.timeout, Exception):
            print("[LOG] Status: OFFLINE - Tentando Reconectar") # DoD Falha [cite: 97]
        
        # Intervalo entre verificações (Tarefa 04) [cite: 76]
        time.sleep(30)

if __name__ == "__main__":
    print("Iniciando Worker...")
    enviar_heartbeat()