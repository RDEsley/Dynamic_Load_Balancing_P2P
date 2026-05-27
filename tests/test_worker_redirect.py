import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "AsyncIO"))

import protocol  # noqa: E402
from worker import build_alive_payload, parse_host_port  # noqa: E402


class TestWorkerHeartbeat(unittest.TestCase):
    def test_build_heartbeat_request(self):
        msg = protocol.build_heartbeat_request("Master_A")
        self.assertEqual(msg, {"SERVER_UUID": "Master_A", "TASK": "HEARTBEAT"})


class TestWorkerRedirect(unittest.TestCase):
    def test_build_register_temporary_worker_payload(self):
        msg = protocol.build_register_temporary_worker(
            "REQ-REDIRECT-1",
            "B1",
            "192.168.0.1:8001",
        )
        self.assertEqual(msg["TYPE"], "REGISTER_TEMPORARY_WORKER")
        self.assertEqual(msg["REQUEST_ID"], "REQ-REDIRECT-1")
        self.assertEqual(msg["PAYLOAD"]["WORKER_ID"], "B1")
        self.assertEqual(msg["PAYLOAD"]["ORIGINAL_MASTER_ADDRESS"], "192.168.0.1:8001")

    def test_alive_local_without_server_uuid(self):
        payload = build_alive_payload(False, None)
        self.assertEqual(payload["WORKER"], "ALIVE")
        self.assertNotIn("SERVER_UUID", payload)

    def test_alive_borrowed_with_server_uuid(self):
        payload = build_alive_payload(True, "Master_B")
        self.assertEqual(payload["SERVER_UUID"], "Master_B")

    def test_parse_host_port(self):
        host, port = parse_host_port("10.62.217.31:8000")
        self.assertEqual(host, "10.62.217.31")
        self.assertEqual(port, 8000)


class TestWorkerHandlesRedirectAfterNoTask(unittest.IsolatedAsyncioTestCase):
    """
    Regressão CT04: o Master B aceita o pedido REQUEST_HELP e dispara
    COMMAND_REDIRECT logo após o NO_TASK enviado ao worker emprestado.
    O worker DEVE processar o COMMAND_REDIRECT e conectar no Master A,
    enviando REGISTER_TEMPORARY_WORKER.

    Bug original: o HEARTBEAT periódico dentro do branch NO_TASK consumia
    o COMMAND_REDIRECT do buffer TCP e o redirecionamento era silenciosamente
    perdido, dando a impressão que o worker do peer estava sendo "morto".
    """

    async def test_worker_processes_redirect_buffered_after_no_task(self):
        import worker as w

        w.WORKER_UUID = "WB_TEST"
        w.ORIGINAL_MASTER_ID = "B"
        w.MASTER_SERVER_UUID = "Master_B"
        w.INTERVALO_NO_TASK = 0.05
        w.READ_TIMEOUT = 1

        register_received = asyncio.Event()
        captured = {}

        async def fake_master_a(reader, writer):
            try:
                data = await reader.readline()
                if data:
                    captured["register"] = json.loads(data.decode().strip())
                    register_received.set()
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        srv_a = await asyncio.start_server(fake_master_a, "127.0.0.1", 0)
        port_a = srv_a.sockets[0].getsockname()[1]

        async def fake_master_b(reader, writer):
            try:
                heartbeat_line = await reader.readline()
                hb = json.loads(heartbeat_line.decode().strip())
                self.assertEqual(hb.get("TASK"), "HEARTBEAT")
                writer.write(protocol.encode_line(
                    {"SERVER_UUID": "Master_B", "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}
                ))
                await writer.drain()

                alive_line = await reader.readline()
                alive = json.loads(alive_line.decode().strip())
                self.assertEqual(alive.get("WORKER"), "ALIVE")

                # PDF flow: B responde NO_TASK; em seguida o REQUEST_HELP de A é
                # aceito e B emite COMMAND_REDIRECT na mesma conexão worker.
                writer.write(protocol.encode_line({"TASK": "NO_TASK"}))
                await writer.drain()
                redirect = protocol.build_command_redirect(
                    "REQ-REDIRECT-TEST", f"127.0.0.1:{port_a}"
                )
                writer.write(protocol.encode_line(redirect))
                await writer.drain()

                # Mantém a conexão aberta até o worker desconectar.
                try:
                    await asyncio.wait_for(reader.read(), timeout=3)
                except (asyncio.TimeoutError, Exception):
                    pass
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        srv_b = await asyncio.start_server(fake_master_b, "127.0.0.1", 0)
        port_b = srv_b.sockets[0].getsockname()[1]

        worker_task = asyncio.create_task(
            w.run_session("127.0.0.1", port_b, False, None)
        )
        try:
            await asyncio.wait_for(register_received.wait(), timeout=5)
        finally:
            worker_task.cancel()
            try:
                await worker_task
            except (asyncio.CancelledError, Exception):
                pass
            srv_a.close()
            await srv_a.wait_closed()
            srv_b.close()
            await srv_b.wait_closed()

        msg = captured.get("register")
        self.assertIsNotNone(msg, "Master A não recebeu REGISTER_TEMPORARY_WORKER")
        self.assertEqual(msg["TYPE"], "REGISTER_TEMPORARY_WORKER")
        self.assertEqual(msg["PAYLOAD"]["WORKER_ID"], "WB_TEST")
        self.assertEqual(
            msg["PAYLOAD"]["ORIGINAL_MASTER_ADDRESS"],
            f"127.0.0.1:{port_b}",
        )


class TestWorkerReleaseAndReturn(unittest.IsolatedAsyncioTestCase):
    """
    PDF §2.5 / CT06: Após COMMAND_RELEASE, o Worker REAL (worker.py) deve
    fechar a sessão com o Master atual e reabrir conexão com o Master de
    origem indicado em ORIGINAL_MASTER_ADDRESS, retomando o ciclo Sprint 02
    (HEARTBEAT inicial + ALIVE).
    """

    async def test_worker_reconnects_to_original_master_after_release(self):
        """Ciclo completo: B → redirect → A → release → B (reconexão)."""
        import worker as w

        w.WORKER_UUID = "W_RELEASE"
        w.ORIGINAL_MASTER_ID = "B"
        w.MASTER_SERVER_UUID = "Master_B"
        w.INTERVALO_NO_TASK = 0.05
        w.HEARTBEAT_INTERVAL = 5
        w.READ_TIMEOUT = 1

        b_state = {"connections": 0, "second_alive": None}
        return_received = asyncio.Event()

        async def fake_master_a(reader, writer):
            try:
                first = await asyncio.wait_for(reader.readline(), timeout=3)
                if not first:
                    return
                register = json.loads(first.decode().strip())
                self.assertEqual(register.get("TYPE"), "REGISTER_TEMPORARY_WORKER")
                original_addr = register["PAYLOAD"]["ORIGINAL_MASTER_ADDRESS"]

                second = await asyncio.wait_for(reader.readline(), timeout=3)
                self.assertIsNotNone(second)
                alive_remote = json.loads(second.decode().strip())
                self.assertEqual(alive_remote.get("WORKER"), "ALIVE")
                self.assertIn("SERVER_UUID", alive_remote,
                              "Worker emprestado precisa enviar SERVER_UUID no ALIVE")

                writer.write(protocol.encode_line({"TASK": "NO_TASK"}))
                await writer.drain()
                await asyncio.sleep(0.1)

                release = protocol.build_command_release(
                    "REQ-REL-E2E", original_addr
                )
                writer.write(protocol.encode_line(release))
                await writer.drain()
                try:
                    await asyncio.wait_for(reader.read(), timeout=2)
                except (asyncio.TimeoutError, Exception):
                    pass
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        srv_a = await asyncio.start_server(fake_master_a, "127.0.0.1", 0)
        port_a = srv_a.sockets[0].getsockname()[1]

        async def fake_master_b(reader, writer):
            b_state["connections"] += 1
            this_conn = b_state["connections"]
            try:
                hb_line = await asyncio.wait_for(reader.readline(), timeout=3)
                if not hb_line:
                    return
                hb = json.loads(hb_line.decode().strip())
                self.assertEqual(hb.get("TASK"), "HEARTBEAT")
                writer.write(protocol.encode_line(
                    {"SERVER_UUID": "Master_B", "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}
                ))
                await writer.drain()

                alive_line = await asyncio.wait_for(reader.readline(), timeout=3)
                if not alive_line:
                    return
                alive = json.loads(alive_line.decode().strip())

                if this_conn == 1:
                    writer.write(protocol.encode_line({"TASK": "NO_TASK"}))
                    await writer.drain()
                    redirect = protocol.build_command_redirect(
                        "REQ-RED-E2E", f"127.0.0.1:{port_a}"
                    )
                    writer.write(protocol.encode_line(redirect))
                    await writer.drain()
                    try:
                        await asyncio.wait_for(reader.read(), timeout=3)
                    except (asyncio.TimeoutError, Exception):
                        pass
                else:
                    b_state["second_alive"] = alive
                    return_received.set()
                    writer.write(protocol.encode_line({"TASK": "NO_TASK"}))
                    await writer.drain()
                    try:
                        await asyncio.wait_for(reader.read(), timeout=2)
                    except (asyncio.TimeoutError, Exception):
                        pass
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        srv_b = await asyncio.start_server(fake_master_b, "127.0.0.1", 0)
        port_b = srv_b.sockets[0].getsockname()[1]

        worker_task = asyncio.create_task(
            w.run_session("127.0.0.1", port_b, False, None)
        )
        try:
            await asyncio.wait_for(return_received.wait(), timeout=10)
        finally:
            worker_task.cancel()
            try:
                await worker_task
            except (asyncio.CancelledError, Exception):
                pass
            srv_a.close()
            await srv_a.wait_closed()
            srv_b.close()
            await srv_b.wait_closed()

        self.assertGreaterEqual(b_state["connections"], 2,
                                "Worker deveria abrir 2 conexões com B (inicial e após release)")
        second_alive = b_state["second_alive"]
        self.assertIsNotNone(second_alive,
                             "Worker não reconectou no Master B após COMMAND_RELEASE")
        self.assertEqual(second_alive.get("WORKER"), "ALIVE")
        self.assertEqual(second_alive.get("WORKER_UUID"), "W_RELEASE")
        self.assertNotIn("SERVER_UUID", second_alive,
                         "Após retorno, ALIVE não deve conter SERVER_UUID (worker local)")


class TestWorkerPeriodicHeartbeat(unittest.IsolatedAsyncioTestCase):
    """
    PDF Sprint 1 Tarefa 04: "Criar um loop no Worker para repetir essa
    verificação em intervalos regulares (ex: a cada 10 segundos)".
    """

    async def test_periodic_heartbeat_fires_and_does_not_block_redirect(self):
        import worker as w

        w.WORKER_UUID = "WB_HB"
        w.ORIGINAL_MASTER_ID = "B"
        w.MASTER_SERVER_UUID = "Master_B"
        w.INTERVALO_NO_TASK = 0.05
        w.HEARTBEAT_INTERVAL = 0.2
        w.READ_TIMEOUT = 1

        register_received = asyncio.Event()
        heartbeats_seen = []
        send_redirect_after = asyncio.Event()

        async def fake_master_a(reader, writer):
            try:
                data = await reader.readline()
                if data:
                    register_received.set()
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        srv_a = await asyncio.start_server(fake_master_a, "127.0.0.1", 0)
        port_a = srv_a.sockets[0].getsockname()[1]

        async def fake_master_b(reader, writer):
            try:
                # Handshake Sprint 1
                first_hb = json.loads((await reader.readline()).decode().strip())
                self.assertEqual(first_hb.get("TASK"), "HEARTBEAT")
                heartbeats_seen.append(first_hb)
                writer.write(protocol.encode_line(
                    {"SERVER_UUID": "Master_B", "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}
                ))
                await writer.drain()

                # ALIVE inicial Sprint 2
                alive = json.loads((await reader.readline()).decode().strip())
                self.assertEqual(alive.get("WORKER"), "ALIVE")
                writer.write(protocol.encode_line({"TASK": "NO_TASK"}))
                await writer.drain()

                # Loop de leitura: contabiliza HEARTBEATs periódicos e ALIVE,
                # respondendo cada um adequadamente. Após pelo menos 2
                # heartbeats periódicos, dispara COMMAND_REDIRECT.
                while True:
                    line = await asyncio.wait_for(reader.readline(), timeout=3)
                    if not line:
                        break
                    msg = json.loads(line.decode().strip())
                    if msg.get("TASK") == "HEARTBEAT":
                        heartbeats_seen.append(msg)
                        writer.write(protocol.encode_line(
                            {"SERVER_UUID": "Master_B", "TASK": "HEARTBEAT",
                             "RESPONSE": "ALIVE"}
                        ))
                        await writer.drain()
                        # Após o 2º heartbeat periódico (3 com o inicial),
                        # dispara o redirect para verificar que o worker
                        # ainda processa COMMAND_REDIRECT corretamente.
                        if len(heartbeats_seen) >= 3 and not send_redirect_after.is_set():
                            send_redirect_after.set()
                            redirect = protocol.build_command_redirect(
                                "REQ-REDIRECT-HB", f"127.0.0.1:{port_a}"
                            )
                            writer.write(protocol.encode_line(redirect))
                            await writer.drain()
                    elif msg.get("WORKER") == "ALIVE":
                        writer.write(protocol.encode_line({"TASK": "NO_TASK"}))
                        await writer.drain()
            except (asyncio.TimeoutError, Exception):
                pass
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        srv_b = await asyncio.start_server(fake_master_b, "127.0.0.1", 0)
        port_b = srv_b.sockets[0].getsockname()[1]

        worker_task = asyncio.create_task(
            w.run_session("127.0.0.1", port_b, False, None)
        )
        try:
            await asyncio.wait_for(register_received.wait(), timeout=5)
        finally:
            worker_task.cancel()
            try:
                await worker_task
            except (asyncio.CancelledError, Exception):
                pass
            srv_a.close()
            await srv_a.wait_closed()
            srv_b.close()
            await srv_b.wait_closed()

        # Pelo menos: 1 handshake + 2 periódicos
        self.assertGreaterEqual(
            len(heartbeats_seen), 3,
            f"Esperado >=3 HEARTBEATs (1 handshake + 2 periódicos); recebeu {len(heartbeats_seen)}"
        )
        for hb in heartbeats_seen:
            self.assertEqual(hb.get("TASK"), "HEARTBEAT")
            self.assertEqual(hb.get("SERVER_UUID"), "Master_B")


if __name__ == "__main__":
    unittest.main()
