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
            # Lê até o delimitador \n definido no protocolo
            data = await reader.readline()
            if not data:
                break

            mensagem = data.decode().strip()
            if mensagem:
                payload = json.loads(mensagem)
                
                # Lógica de Heartbeat - Novo formato
                if payload.get("WORKER") == "ALIVE":
                    # Detecta se é Worker local ou remoto
                    is_remote = "SERVER_UUID" in payload
                    user_name = "Julia" if is_remote else "Michel"
                    
                    resposta = {
                        "TASK": "QUERY",
                        "USER": user_name
                    }
                    
                    # Envia a resposta com \n
                    print(f"[HEARTBEAT] Worker {'REMOTO' if is_remote else 'LOCAL'} - {addr}")
                    print(f"[HEARTBEAT] Respondendo com USER: {user_name}")
                    writer.write((json.dumps(resposta) + "\n").encode())
                    await writer.drain()

    except Exception as e:
        print(f"[ERRO] Falha com {addr}: {e}")
    finally:
        print(f"[ASYNC] Fechando conexão com {addr}")
        writer.close()
        await writer.wait_closed()

async def iniciar_master():
    # Configura o Master como servidor
    server = await asyncio.start_server(tratar_worker, HOST, PORT)
    print(f"Master {SERVER_UUID} (AsyncIO) ativo em {HOST}:{PORT}")

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(iniciar_master())
    except KeyboardInterrupt:
        print("\n[SERVIDOR] Encerrando...")