import asyncio
import json

HOST = '10.62.217.31'
PORT = 8000
SERVER_UUID = "Master_3"
INTERVALO = 30 # Segundos entre verificações [cite: 76]

async def enviar_heartbeat():
    while True:
        try:
            # Abre a conexão TCP (Tarefa 01) [cite: 66, 79]
            reader, writer = await asyncio.open_connection(HOST, PORT)
            
            # Payload de envio (Tarefa 02) [cite: 70]
            payload = {
                "SERVER_UUID": SERVER_UUID,
                "TASK": "HEARTBEAT"
            }
            
            writer.write((json.dumps(payload) + "\n").encode())
            await writer.drain()

            # Aguarda a resposta do Master
            data = await reader.readline()
            if data:
                res = json.loads(data.decode().strip())
                if res.get("RESPONSE") == "ALIVE":
                    print(f"[LOG] Status: ALIVE")

            writer.close()
            await writer.wait_closed()

        except Exception:
            # Caso o Master esteja offline (Tarefa 04) [cite: 97]
            print("[LOG] Status: OFFLINE - Tentando Reconectar")

        # Pausa assíncrona (não bloqueia o loop) [cite: 88]
        await asyncio.sleep(INTERVALO)

if __name__ == "__main__":
    print("Iniciando Worker (AsyncIO)...")
    try:
        asyncio.run(enviar_heartbeat())
    except KeyboardInterrupt:
        print("\n[WORKER] Encerrando...")