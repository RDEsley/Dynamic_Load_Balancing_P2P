import asyncio
import json
import random

HOST = '10.62.217.31'
PORT = 8000
SERVER_UUID = "Master_3"
WORKER_UUID = "Worker_1"  # Hardcoded - Único para este worker
INTERVALO = 30 # Segundos entre verificações

async def enviar_heartbeat():
    while True:
        try:
            # Abre a conexão TCP
            reader, writer = await asyncio.open_connection(HOST, PORT)
            
            # Novo Payload - WORKER alive signal
            payload = {
                "WORKER": "ALIVE",
                "WORKER_UUID": WORKER_UUID,
                "SERVER_UUID": SERVER_UUID
            }
            
            # Log do payload antes de enviar
            print(f"[LOG] Enviando payload: {json.dumps(payload)}")
            
            writer.write((json.dumps(payload) + "\n").encode())
            await writer.drain()

            # Aguarda a resposta do Master
            data = await asyncio.wait_for(reader.readline(), timeout=5)
            if data:
                res = json.loads(data.decode().strip())
                print(f"[LOG] Resposta do Master: {json.dumps(res)}")

                if res.get("TASK") == "QUERY":
                    if random.random() < 0.5:
                        print(f"[TASK] Worker ocupado, recusando tarefa para USER={res.get('USER')}")
                        resultado = {
                            "STATUS": "NOK",
                            "TASK": "QUERY",
                            "WORKER_UUID": WORKER_UUID
                        }
                    else:
                        print(f"[TASK] Processando tarefa para USER={res.get('USER')}")
                        try:
                            await asyncio.sleep(1)
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

                    writer.write((json.dumps(resultado) + "\n").encode())
                    await writer.drain()

                    ack_data = await asyncio.wait_for(reader.readline(), timeout=5)
                    if ack_data:
                        ack = json.loads(ack_data.decode().strip())
                        print(f"[LOG] ACK do Master: {json.dumps(ack)}")
                elif res.get("TASK") == "NO_TASK":
                    print("[INFO] Nenhuma tarefa disponível no momento")
                else:
                    print(f"[LOG] Resposta desconhecida do Master: {json.dumps(res)}")

            writer.close()
            await writer.wait_closed()

        except asyncio.TimeoutError:
            print("[LOG] Status: OFFLINE - timeout de 5 segundos excedido - Tentando Reconectar")
        except Exception as e:
            # Caso o Master esteja offline
            print(f"[LOG] Status: OFFLINE - {str(e)} - Tentando Reconectar")

        # Pausa assíncrona (não bloqueia o loop)
        await asyncio.sleep(INTERVALO)

if __name__ == "__main__":
    print("Iniciando Worker (AsyncIO)...")
    try:
        asyncio.run(enviar_heartbeat())
    except KeyboardInterrupt:
        print("\n[WORKER] Encerrando...")