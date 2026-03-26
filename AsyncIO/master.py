import asyncio
import json

HOST = '10.62.217.31'
PORT = 8000
SERVER_UUID = "Master_3"

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
                
                # Lógica de Heartbeat (Tarefa 03) [cite: 71, 72]
                if payload.get("TASK") == "HEARTBEAT":
                    resposta = {
                        "SERVER_UUID": SERVER_UUID,
                        "TASK": "HEARTBEAT",
                        "RESPONSE": "ALIVE"
                    }
                    # Envia a resposta com \n [cite: 73]
                    writer.write((json.dumps(resposta) + "\n").encode())
                    await writer.drain()
                    print(f"[HEARTBEAT] Respondido para {addr}")

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

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(iniciar_master())
    except KeyboardInterrupt:
        print("\n[SERVIDOR] Encerrando...")