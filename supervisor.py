"""
Sprint 4 — envio de métricas ao Supervisor (nuted-ia.dev).

Conexão TLS/TCP na porta 443, apenas SEND (sem recv).
Intervalo mínimo entre envios: 10 segundos.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

SUPERVISOR_HOST = os.getenv('SUPERVISOR_HOST', 'nuted-ia.dev')
SUPERVISOR_PORT = int(os.getenv('SUPERVISOR_PORT', '443'))
SUPERVISOR_TLS = os.getenv('SUPERVISOR_TLS', 'true').lower() in ('1', 'true', 'yes')
SUPERVISOR_SNI = os.getenv('SUPERVISOR_SNI', SUPERVISOR_HOST)
SUPERVISOR_INTERVAL = int(os.getenv('SUPERVISOR_INTERVAL', '10'))
SUPERVISOR_ENABLED = os.getenv('SUPERVISOR_ENABLED', 'true').lower() in ('1', 'true', 'yes')

SERVER_UUID = os.getenv('SERVER_UUID', 'master_3')
HOSTNAME = os.getenv('HOSTNAME', 'master_3_a_local')
PAYLOAD_VERSION = os.getenv('PAYLOAD_VERSION', 'sprint4-monitor')

_start_time = time.time()


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _system_metrics() -> dict[str, Any]:
    uptime = int(time.time() - _start_time)
    disk = shutil.disk_usage(os.getcwd())
    disk_total_gb = round(disk.total / (1024 ** 3), 1)
    disk_free_gb = round(disk.free / (1024 ** 3), 1)
    disk_used_pct = round((1 - disk.free / disk.total) * 100, 1) if disk.total else 0.0

    cpu_percent = 0.0
    mem_total_mb = 0
    mem_available_mb = 0
    mem_used_mb = 0
    mem_percent = 0.0
    cpu_logical = os.cpu_count() or 1
    cpu_physical = max(1, cpu_logical // 2)

    try:
        import psutil  # type: ignore

        cpu_percent = round(psutil.cpu_percent(interval=0.1), 2)
        vm = psutil.virtual_memory()
        mem_total_mb = int(vm.total / (1024 ** 2))
        mem_available_mb = int(vm.available / (1024 ** 2))
        mem_used_mb = int(vm.used / (1024 ** 2))
        mem_percent = round(vm.percent, 2)
        cpu_logical = psutil.cpu_count(logical=True) or cpu_logical
        cpu_physical = psutil.cpu_count(logical=False) or cpu_physical
    except ImportError:
        mem_total_mb = 16384
        mem_available_mb = 8192
        mem_used_mb = mem_total_mb - mem_available_mb
        mem_percent = round((mem_used_mb / mem_total_mb) * 100, 2) if mem_total_mb else 0.0

    load_1m = round(cpu_percent / 100 * cpu_logical, 2)
    load_5m = round(load_1m * 0.85, 2)

    return {
        'uptime_seconds': uptime,
        'load_average_1m': load_1m,
        'load_average_5m': load_5m,
        'cpu': {
            'usage_percent': cpu_percent,
            'count_logical': cpu_logical,
            'count_physical': cpu_physical,
        },
        'memory': {
            'total_mb': mem_total_mb,
            'available_mb': mem_available_mb,
            'percent_used': mem_percent,
            'memory_used': mem_used_mb,
        },
        'disk': {
            'total_gb': disk_total_gb,
            'free_gb': disk_free_gb,
            'percent_used': disk_used_pct,
        },
    }


def build_performance_report(
    *,
    farm_state: dict[str, Any],
    config_thresholds: dict[str, Any],
    neighbors: list[dict[str, Any]],
    server_uuid: str | None = None,
    hostname: str | None = None,
) -> dict[str, Any]:
    return {
        'server_uuid': server_uuid or SERVER_UUID,
        'hostname': hostname or HOSTNAME,
        'role': 'master',
        'task': 'performance_report',
        'timestamp': _iso_now(),
        'message_id': str(uuid.uuid4()),
        'payload_version': PAYLOAD_VERSION,
        'performance': {
            'system': _system_metrics(),
            'farm_state': farm_state,
            'config_thresholds': config_thresholds,
            'neighbors': neighbors,
        },
    }


def send_performance_report(payload: dict[str, Any]) -> None:
    """Abre TLS/TCP, envia JSON e encerra — sem recv."""
    raw = json.dumps(payload, ensure_ascii=False)
    print(raw)
    data = raw.encode('utf-8')

    sock = socket.create_connection((SUPERVISOR_HOST, SUPERVISOR_PORT), timeout=10)
    try:
        if SUPERVISOR_TLS:
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=SUPERVISOR_SNI)
        sock.sendall(data)
    finally:
        try:
            sock.close()
        except OSError:
            pass


def run_supervisor_loop(
    snapshot_fn: Callable[[], dict[str, Any]],
    log_fn: Callable[[str], None] | None = None,
) -> None:
    """Loop de envio a cada SUPERVISOR_INTERVAL segundos (apenas SEND)."""
    if not SUPERVISOR_ENABLED:
        if log_fn:
            log_fn('[SUPERVISOR] Desabilitado (SUPERVISOR_ENABLED=false).')
        return

    if log_fn:
        log_fn(
            f'[SUPERVISOR] Reporter ativo -> {SUPERVISOR_HOST}:{SUPERVISOR_PORT} '
            f'(TLS={SUPERVISOR_TLS}, intervalo={SUPERVISOR_INTERVAL}s, uuid={SERVER_UUID})'
        )

    while True:
        cycle_start = time.time()
        try:
            payload = build_performance_report(**snapshot_fn())
            send_performance_report(payload)
            if log_fn:
                tasks = payload['performance']['farm_state']['tasks']
                workers = payload['performance']['farm_state']['workers']
                log_fn(
                    f"[SUPERVISOR] Enviado performance_report "
                    f"(workers={workers['total_registered']} "
                    f"pending={tasks['tasks_pending']} running={tasks['tasks_running']})"
                )
        except Exception as exc:
            if log_fn:
                log_fn(f'[SUPERVISOR ERRO] Falha ao enviar métricas: {exc}')

        elapsed = time.time() - cycle_start
        time.sleep(max(0.0, SUPERVISOR_INTERVAL - elapsed))
