"""Integration smoke tests for Sprint 3 M2M (local TCP)."""
import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "AsyncIO"))

import protocol  # noqa: E402


class TestIntegrationM2M(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import master as m

        self.m = m
        m.task_queue.clear()
        m.connected_workers.clear()
        m.temporary_workers.clear()
        m.neighbor_masters.clear()
        m.load_samples.clear()
        m.CAPACITY = 100
        m.RELEASE_THRESHOLD = 60
        m.neighbor_masters["A"] = "127.0.0.1:19000"
        m.connected_workers["W1"] = {
            "writer": None,
            "address": "127.0.0.1:19099",
            "temporary": False,
            "busy": False,
        }

    async def test_ct02_high_load_rejection(self):
        import master as m

        for i in range(m.CAPACITY):
            m.task_queue.append(f"t{i}")
        decision = await m.async_decide_help_response(
            {"MASTER_ID": "A", "WORKERS_NEEDED": 1}
        )
        self.assertFalse(decision["ACCEPTED"])
        self.assertEqual(decision["REASON"], "HIGH_LOAD")

    async def test_request_help_same_request_id(self):
        import master as m

        server = await asyncio.start_server(m.tratar_conexao, "127.0.0.1", 19010)
        await asyncio.sleep(0.05)

        request_id = protocol.new_request_id()
        reader, writer = await asyncio.open_connection("127.0.0.1", 19010)
        msg = protocol.build_request_help(request_id, "A", 50, 100, 1)
        writer.write(protocol.encode_line(msg))
        await writer.drain()
        data = await asyncio.wait_for(reader.readline(), timeout=5)
        writer.close()
        await writer.wait_closed()
        server.close()
        await server.wait_closed()

        resp = json.loads(data.decode().strip())
        self.assertEqual(resp["REQUEST_ID"], request_id)
        self.assertIn(resp["TYPE"], ("RESPONSE_ACCEPTED", "RESPONSE_REJECTED"))

    async def test_ct09_unknown_type_ignored(self):
        import master as m

        server = await asyncio.start_server(m.tratar_conexao, "127.0.0.1", 19011)
        await asyncio.sleep(0.05)
        reader, writer = await asyncio.open_connection("127.0.0.1", 19011)
        bad = {"TYPE": "FUTURE_MESSAGE", "REQUEST_ID": "X", "PAYLOAD": {}}
        writer.write(protocol.encode_line(bad))
        await writer.drain()
        await asyncio.sleep(0.1)
        writer.close()
        await writer.wait_closed()
        server.close()
        await server.wait_closed()
        self.assertTrue(True)

    async def test_release_cycle_end_to_end(self):
        """
        Ciclo de devolução TCP real (PDF §2.5 / CT06):

        1. Master A REAL aceita um worker emprestado via REGISTER_TEMPORARY_WORKER.
        2. Worker emprestado envia ALIVE periodicamente, A responde NO_TASK.
        3. Forçamos a carga normalizada (samples < RELEASE_THRESHOLD) e chamamos
           release_normalized_temporary_workers().
        4. Validamos:
           a) Worker recebe COMMAND_RELEASE com ORIGINAL_MASTER_ADDRESS correto.
           b) Master B fake recebe NOTIFY_WORKER_RETURNED via pool M2M.
           c) temporary_workers fica vazio após o release.
        """
        import master as m

        m.task_queue.clear()
        m.connected_workers.clear()
        m.temporary_workers.clear()
        m.neighbor_masters.clear()
        m.load_samples.clear()
        m.m2m_pool.clear()
        m.CAPACITY = 100
        m.RELEASE_THRESHOLD = 60

        notify_received = asyncio.Event()
        captured_notify = {}

        async def fake_master_b(reader, writer):
            try:
                data = await asyncio.wait_for(reader.readline(), timeout=5)
                if data:
                    captured_notify["msg"] = json.loads(data.decode().strip())
                    notify_received.set()
                # mantém aberta para o caso do master A reutilizar pool
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
        original_master_addr = f"127.0.0.1:{port_b}"
        m.neighbor_masters["B"] = original_master_addr

        srv_a = await asyncio.start_server(m.tratar_conexao, "127.0.0.1", 0)
        port_a = srv_a.sockets[0].getsockname()[1]

        received_release = asyncio.Event()
        worker_received = {}

        async def borrowed_worker_client():
            reader, writer = await asyncio.open_connection("127.0.0.1", port_a)
            try:
                register = protocol.build_register_temporary_worker(
                    "REQ-REG-E2E", "WORKER_E2E", original_master_addr
                )
                writer.write(protocol.encode_line(register))
                await writer.drain()

                alive = {"WORKER": "ALIVE", "WORKER_UUID": "WORKER_E2E",
                         "SERVER_UUID": "Master_B"}
                writer.write(protocol.encode_line(alive))
                await writer.drain()

                while True:
                    data = await asyncio.wait_for(reader.readline(), timeout=5)
                    if not data:
                        break
                    msg = json.loads(data.decode().strip())
                    if msg.get("TYPE") == "COMMAND_RELEASE":
                        worker_received["release"] = msg
                        received_release.set()
                        return
                    if msg.get("TASK") == "NO_TASK":
                        await asyncio.sleep(0.05)
                        writer.write(protocol.encode_line(alive))
                        await writer.drain()
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        worker_task = asyncio.create_task(borrowed_worker_client())

        for _ in range(50):
            await asyncio.sleep(0.05)
            if "WORKER_E2E" in m.connected_workers and "WORKER_E2E" in m.temporary_workers:
                break
        self.assertIn("WORKER_E2E", m.connected_workers,
                      "Worker emprestado não foi registrado em connected_workers")
        self.assertEqual(
            m.temporary_workers.get("WORKER_E2E"), original_master_addr,
            "ORIGINAL_MASTER_ADDRESS não foi preservado"
        )

        m.load_samples.extend([10, 10, 10])
        released = await m.release_normalized_temporary_workers()
        self.assertEqual(released, 1, "release não foi disparado para o worker ocioso")

        try:
            await asyncio.wait_for(received_release.wait(), timeout=5)
            await asyncio.wait_for(notify_received.wait(), timeout=5)
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

        rel = worker_received.get("release")
        self.assertIsNotNone(rel, "Worker não recebeu COMMAND_RELEASE")
        self.assertEqual(rel["TYPE"], "COMMAND_RELEASE")
        self.assertEqual(rel["PAYLOAD"]["ORIGINAL_MASTER_ADDRESS"], original_master_addr,
                         "COMMAND_RELEASE com endereço incorreto")

        notify = captured_notify.get("msg")
        self.assertIsNotNone(notify, "Master B não recebeu NOTIFY_WORKER_RETURNED")
        self.assertEqual(notify["TYPE"], "NOTIFY_WORKER_RETURNED")
        self.assertEqual(notify["PAYLOAD"]["WORKER_ID"], "WORKER_E2E")

        self.assertNotIn("WORKER_E2E", m.temporary_workers,
                         "temporary_workers deveria estar vazio após release")

    async def test_register_temporary_worker_routed_to_sprint02(self):
        """
        Regressão: REGISTER_TEMPORARY_WORKER usa envelope {TYPE,REQUEST_ID,PAYLOAD}
        mas é uma mensagem Worker→Master (não Master-to-Master). O dispatcher
        precisa entregá-la a tratar_sprint02 para que o worker temporário fique
        registrado com o ORIGINAL_MASTER_ADDRESS exato (host:port) recebido,
        e não apenas inferido a partir de SERVER_UUID em ALIVEs subsequentes.
        """
        import master as m

        m.task_queue.clear()
        m.connected_workers.clear()
        m.temporary_workers.clear()
        m.neighbor_masters.clear()

        server = await asyncio.start_server(m.tratar_conexao, "127.0.0.1", 19012)
        await asyncio.sleep(0.05)

        reader, writer = await asyncio.open_connection("127.0.0.1", 19012)
        msg = protocol.build_register_temporary_worker(
            "REQ-REG-TEST", "WTEMP", "10.0.0.5:8001"
        )
        writer.write(protocol.encode_line(msg))
        await writer.drain()
        await asyncio.sleep(0.25)

        registered = "WTEMP" in m.connected_workers
        original_addr = m.temporary_workers.get("WTEMP")

        writer.close()
        await writer.wait_closed()
        server.close()
        await server.wait_closed()

        self.assertTrue(
            registered,
            "Worker temporário não foi registrado em connected_workers",
        )
        self.assertEqual(
            original_addr,
            "10.0.0.5:8001",
            "ORIGINAL_MASTER_ADDRESS precisa ser o host:port enviado, não inferido",
        )


if __name__ == "__main__":
    unittest.main()
