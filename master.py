import socket
import threading
import json

HOST = '10.62.217.31'
PORT = 8000
SERVER_UUID = "Master_3"

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
                
                # Lógica de Resposta (Tarefa 03)
                if payload.get("TASK") == "HEARTBEAT":
                    resposta = {
                        "SERVER_UUID": SERVER_UUID,
                        "TASK": "HEARTBEAT",
                        "RESPONSE": "ALIVE"
                    }
                    # Envia resposta com o delimitador \n [cite: 67]
                    conn.sendall((json.dumps(resposta) + "\n").encode('utf-8'))
                    print(f"[HEARTBEAT] Respondido para {addr}")
        
    except Exception as e:
        print(f"[ERRO] Falha com {addr}: {e}")
    finally:
        conn.close()

def iniciar_servidor():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(100)
    print(f"Master {SERVER_UUID} ativo em {HOST}:{PORT}")

    while True:
        conn, addr = s.accept()
        # Uso de Threads para não bloquear o Master (Tarefa 04) [cite: 75]
        threading.Thread(target=tratar_cliente, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    try:
        iniciar_servidor()
    except KeyboardInterrupt:
        print("\n[SERVIDOR] Encerrando...")