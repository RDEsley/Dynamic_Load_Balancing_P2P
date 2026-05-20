import asyncio
import json
import os
import random

from protocol import (
    build_register_temporary_worker,
    encode_line,
    get_message_type,
    new_request_id,
)

HOST = "127.0.0.1"
PORT = 8000
ORIGINAL_MASTER_ID = "B"
WORKER_UUID = "Worker_1"
INTERVALO_NO_TASK = 5
READ_TIMEOUT = 5


def read_worker_config():
    global HOST, PORT, ORIGINAL_MASTER_ID, WORKER_UUID
    paths = [
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
    ]
    for env_path in paths:
        if not os.path.exists(env_path):
            continue
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip()
                    if key in ("WORKER_HOST", "MASTER_HOST", "HOST"):
                        HOST = value
                    elif key == "PORT":
                        PORT = int(value)
                    elif key == "WORKER_UUID":
                        WORKER_UUID = value
                    elif key == "ORIGINAL_MASTER_ID":
                        ORIGINAL_MASTER_ID = value
        except OSError:
            pass


def parse_host_port(address: str) -> tuple[str, int]:
    host, port_str = address.rsplit(":", 1)
    return host, int(port_str)


def build_alive_payload(borrowed: bool, original_master_id: str | None) -> dict:
    payload = {"WORKER": "ALIVE", "WORKER_UUID": WORKER_UUID}
    if borrowed and original_master_id:
        payload["SERVER_UUID"] = original_master_id
    return payload


async def process_query(reader, writer, res: dict) -> None:
    if random.random() < 0.5:
        print(f"[TASK] Worker ocupado, recusando USER={res.get('USER')}")
        resultado = {"STATUS": "NOK", "TASK": "QUERY", "WORKER_UUID": WORKER_UUID}
    else:
        print(f"[TASK] Processando USER={res.get('USER')}")
        await asyncio.sleep(0.1)
        resultado = {"STATUS": "OK", "TASK": "QUERY", "WORKER_UUID": WORKER_UUID}

    writer.write(encode_line(resultado))
    await writer.drain()
    ack_data = await asyncio.wait_for(reader.readline(), timeout=READ_TIMEOUT)
    if ack_data:
        print(f"[LOG] ACK: {ack_data.decode().strip()}")


async def connect_and_register(
    new_host: str,
    new_port: int,
    original_address: str,
) -> tuple:
    reader, writer = await asyncio.open_connection(new_host, new_port)
    register_msg = build_register_temporary_worker(
        new_request_id(),
        WORKER_UUID,
        original_address,
    )
    writer.write(encode_line(register_msg))
    await writer.drain()
    print(f"[WORKER] REGISTER_TEMPORARY_WORKER enviado (origem={original_address})")
    return reader, writer


async def run_session(host: str, port: int, borrowed: bool, original_master_id: str | None):
    reader, writer = await asyncio.open_connection(host, port)
    try:
        alive = build_alive_payload(borrowed, original_master_id)
        print(f"[LOG] Conectado {host}:{port} -> {json.dumps(alive)}")
        writer.write(encode_line(alive))
        await writer.drain()

        while True:
            try:
                data = await asyncio.wait_for(reader.readline(), timeout=READ_TIMEOUT)
            except asyncio.TimeoutError:
                if borrowed:
                    raise ConnectionError("Master emprestador indisponível (CT08)")
                writer.write(encode_line(build_alive_payload(borrowed, original_master_id)))
                await writer.drain()
                continue

            if not data:
                break

            res = json.loads(data.decode().strip())
            msg_type = get_message_type(res)

            if msg_type == "COMMAND_REDIRECT":
                redirect_address = res.get("PAYLOAD", {}).get("NEW_MASTER_ADDRESS")
                if not redirect_address:
                    print("[WORKER] COMMAND_REDIRECT inválido")
                    continue
                original_address = f"{host}:{port}"
                writer.close()
                await writer.wait_closed()
                host, port = parse_host_port(redirect_address)
                print(f"[WORKER] Redirecionando {original_address} -> {redirect_address}")
                reader, writer = await connect_and_register(host, port, original_address)
                borrowed = True
                original_master_id = ORIGINAL_MASTER_ID
                writer.write(encode_line(build_alive_payload(borrowed, original_master_id)))
                await writer.drain()
                continue

            if msg_type == "COMMAND_RELEASE":
                release_addr = res.get("PAYLOAD", {}).get("ORIGINAL_MASTER_ADDRESS")
                print(f"[WORKER] COMMAND_RELEASE -> {release_addr}")
                writer.close()
                await writer.wait_closed()
                if release_addr:
                    rh, rp = parse_host_port(release_addr)
                    await run_session(rh, rp, False, None)
                return

            if res.get("TASK") == "QUERY":
                await process_query(reader, writer, res)
                writer.write(encode_line(build_alive_payload(borrowed, original_master_id)))
                await writer.drain()
            elif res.get("TASK") == "NO_TASK":
                await asyncio.sleep(INTERVALO_NO_TASK)
                writer.write(encode_line(build_alive_payload(borrowed, original_master_id)))
                await writer.drain()
            else:
                print(f"[LOG] Mensagem: {json.dumps(res)}")

    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def run_worker():
    read_worker_config()
    while True:
        try:
            await run_session(HOST, PORT, False, None)
        except (ConnectionError, asyncio.TimeoutError, OSError) as e:
            print(f"[LOG] OFFLINE: {e} — reconectando em {INTERVALO_NO_TASK}s")
            await asyncio.sleep(INTERVALO_NO_TASK)
        except Exception as e:
            print(f"[LOG] Erro: {e}")
            await asyncio.sleep(INTERVALO_NO_TASK)


if __name__ == "__main__":
    print("Iniciando Worker (AsyncIO) — conexão persistente...")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("\n[WORKER] Encerrando...")
