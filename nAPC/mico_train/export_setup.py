"""[web 에서 실행] Set-up 을 payload JSON 으로 뽑는다. Django 가 필요하다.

    cd /path/to/MICO_Web
    python3 -m nAPC.mico_train.export_setup --family DRAM --oper-desc "M1 CU CMP"
    python3 -m nAPC.mico_train.export_setup --family DRAM --oper-desc "M1 CU CMP" \
        --out payload_dram_m1cu.json --days 30

뽑은 JSON 을 학습 컨테이너에 넘기면(엔드포인트 호출이든 스케줄 실행이든)
컨테이너는 web DB 없이 그대로 학습한다.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def _django_setup():
    """Django 를 여기서만 띄운다 (컨테이너 경로에는 영향 없음)."""
    root = str(Path(__file__).parents[2])      # MICO_Web/
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--family', required=True, help='DRAM 또는 NAND')
    ap.add_argument('--oper-desc', required=True, help='공정 이름 (예: "M1 CU CMP")')
    ap.add_argument('--days', type=int, default=30, help='DataLake 조회 기간 (기본 30)')
    ap.add_argument('--out', help='저장할 파일. 없으면 화면에 출력')
    if 'ipykernel' in sys.modules:
        args = ap.parse_args([])
    else:
        args, _ = ap.parse_known_args()

    _django_setup()
    from nAPC.mico_train.setup_payload import build_payload

    payload = build_payload(args.family, args.oper_desc, days=args.days)
    text    = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(text, encoding='utf-8')
        print(f'{args.out} 저장 — Set-up {len(payload["rows"])}행')
        keys = sorted({f'{r["Lot_Code"]}_{r["Oper_Code"]}_{r["Fab"]}' for r in payload['rows']})
        for k in keys:
            print(f'  - {k}')
    else:
        print(text)


if __name__ == '__main__':
    main()
