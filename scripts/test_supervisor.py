"""Envia um único performance_report ao supervisor (teste seguro, sem loop)."""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from supervisor import build_performance_report, send_performance_report


def main():
    parser = argparse.ArgumentParser(description='Teste único de envio ao nuted-ia.dev')
    parser.add_argument('--dry-run', action='store_true', help='Mostra JSON sem enviar')
    args = parser.parse_args()

    payload = build_performance_report(
        farm_state={
            'workers': {
                'total_registered': 2,
                'workers_utilization': 1,
                'workers_alive': 2,
                'workers_idle': 1,
                'workers_borrowed': 0,
                'workers_received': 0,
                'workers_failed': 0,
                'workers_home': 2,
                'workers_available_capacity': 1,
                'borrowed_workers': [],
            },
            'tasks': {
                'tasks_pending': 3,
                'tasks_running': 1,
                'tasks_completed': 10,
                'tasks_failed': 0,
                'oldest_task_age_s': 5,
            },
        },
        config_thresholds={
            'max_task': 100,
            'warn_cpu_percent': 85,
            'warn_memory_percent': 85,
            'release_task': 60,
        },
        neighbors=[],
    )

    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if args.dry_run:
        print('\n[dry-run] Nenhum pacote enviado.')
        return

    send_performance_report(payload)
    print('\n[ok] performance_report enviado para nuted-ia.dev:443 (sem aguardar resposta).')


if __name__ == '__main__':
    main()
