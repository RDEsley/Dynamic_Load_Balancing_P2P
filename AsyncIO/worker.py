import asyncio
import json
import socket

HOST = '192.168.0.45'
PORT = 8000
SERVER_UUID = "Master_3"
WORKER_UUID = "Worker_1"  # Hardcoded - Único para este worker
INTERVALO = 30 # Segundos entre verificações [cite: 76]

def is_remote_worker():
    """Verifica se o Worker está em IP diferente do Master"""
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        return local_ip != HOST
    except:
        return False

async def enviar_heartbeat():
    while True:
        try:
            # Abre a conexão TCP (Tarefa 01) [cite: 66, 79]
            reader, writer = await asyncio.open_connection(HOST, PORT)
            
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
            
            writer.write((json.dumps(payload) + "\n").encode())
            await writer.drain()

            # Aguarda a resposta do Master
            data = await reader.readline()
            if data:
                res = json.loads(data.decode().strip())
                print(f"[LOG] Resposta do Master: {json.dumps(res)}")
                
                # Processa resposta conforme o tipo de tarefa
                if res.get("TASK") == "QUERY":
                    user = res.get("USER")
                    print(f"[TASK] Executando tarefa para: {user}")
                elif res.get("TASK") == "NO_TASK":
                    print(f"[INFO] Nenhuma tarefa disponível no momento")

            writer.close()
            await writer.wait_closed()

        except Exception as e:
            # Caso o Master esteja offline (Tarefa 04) [cite: 97]
            print(f"[LOG] Status: OFFLINE - {str(e)} - Tentando Reconectar")

        # Pausa assíncrona (não bloqueia o loop) [cite: 88]
        await asyncio.sleep(INTERVALO)

if __name__ == "__main__":
    print("Iniciando Worker (AsyncIO)...")
    try:
        asyncio.run(enviar_heartbeat())
    except KeyboardInterrupt:
        print("\n[WORKER] Encerrando...")
