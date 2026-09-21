"""샘플 데이터로 전체 학습을 한 번 돌려 본다 (사내 시스템 없이).

    cd /path/to/MICO_Web
    python3 -m nAPC.mico_train.run_sample
    python3 -m nAPC.mico_train.run_sample --dry-run      # 데이터 경로만
    python3 -m nAPC.mico_train.run_sample --rr-para PAD

`algorithm_new/merge_df_sample.csv` 를 DataLake/DataHub 대역으로 써서
payload -> merge_df -> 실제 학습 파이프라인(Common.Module._run_pipeline) 까지 탄다.

MongoDB 가 없으므로 결과 저장과 Offset/Alarm 은 끝까지 가지 못한다(아래 참고).
데이터가 흘러 학습 모듈이 실제로 도는지 확인하는 용도다.
"""

import argparse
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='데이터만 모으고 학습은 안 함')
    ap.add_argument('--rr-para', default='PAD',
                    help="RR_Para (HEAD/PAD/DISK/DRESSER_CUTTING_RATE). "
                         "빈 값이면 REMOVAL_RATE 가 UnboundLocalError 를 낸다")
    ap.add_argument('--days', type=int, default=30)
    ap.add_argument('--show-results', action='store_true', help='학습 결과 한 건씩 출력')
    args = ap.parse_args([] if 'ipykernel' in sys.modules else None)

    root = str(Path(__file__).parents[2])
    for p in (root, str(Path(root) / 'algorithm_new')):
        if p not in sys.path:
            sys.path.insert(0, p)

    from nAPC.mico_train import run_training
    from nAPC.mico_train.sample_provider import SampleProvider, payload_from_sample

    payload = payload_from_sample(days=args.days)
    for r in payload['rows']:
        r['RR_Para'] = args.rr_para

    print(f'Set-up {len(payload["rows"])}행 | recipe: '
          f'{[r["Recipe_ID"] for r in payload["rows"]]}\n')

    res = run_training(payload, provider=SampleProvider(), dry_run=args.dry_run)

    print('\n반환값:')
    for r in res:
        print(f'  {r["key"]:<24} {r["status"]:<10} {r["rows"]}행')

    if not args.dry_run:
        # 학습 결과는 반환되지 않고 컬렉션에 쌓인다 (로컬은 인메모리 Mock)
        import Common.MongoDB_Control as mc
        print('\n학습 결과 (컬렉션):')
        for coll, recs in mc._STORE.items():
            print(f'  {coll}: {len(recs)}건')
            if recs and args.show_results:
                import json
                print(json.dumps(recs[0], ensure_ascii=False, indent=4, default=str))


if __name__ == '__main__':
    main()
