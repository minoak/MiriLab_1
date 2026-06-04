# -*- coding: utf-8 -*-
"""데이터셋 컬럼 스키마만 미리 받아 저장 (RAG 준비작업).

nvidia/Nemotron-Personas-Korea 의 첫 parquet 샤드 **푸터(footer)만** 읽어
컬럼 목록·타입·행수를 얻는다. 전체(2GB) 다운로드 없이 메타데이터만 가져온다
(footer 는 수 KB). 결과는 data/dataset_schema.json 에 저장 → 오프라인에서
RAG 인덱싱·검색 키 설계의 출발점으로 재사용한다.

실행:  python _fetch_schema.py   (프로젝트 루트에서)
"""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_HF_REPO = "nvidia/Nemotron-Personas-Korea"
_OUT = "data/dataset_schema.json"


def fetch_schema() -> dict:
    """첫 parquet 샤드의 footer 만 읽어 컬럼 스키마를 반환한다(전체 다운로드 X)."""
    from huggingface_hub import HfFileSystem, list_repo_files
    import pyarrow.parquet as pq

    files = list_repo_files(_HF_REPO, repo_type="dataset")
    parquet_files = sorted(f for f in files if f.endswith(".parquet"))
    if not parquet_files:
        raise RuntimeError("parquet 파일을 찾지 못했습니다.")
    target = parquet_files[0]

    fs = HfFileSystem()
    with fs.open(f"datasets/{_HF_REPO}/{target}", "rb") as fh:
        pf = pq.ParquetFile(fh)            # 접근 시 footer(metadata)만 읽음
        schema = pf.schema_arrow
        nrows = pf.metadata.num_rows
        ngroups = pf.metadata.num_row_groups

    cols = [
        {"name": schema.field(i).name, "type": str(schema.field(i).type)}
        for i in range(len(schema))
    ]
    return {
        "repo": _HF_REPO,
        "parquet_file": target,
        "num_parquet_shards": len(parquet_files),
        "num_rows_in_shard": nrows,
        "num_row_groups": ngroups,
        "num_columns": len(cols),
        "columns": cols,
        "note": "footer-only read (no full download). first shard schema. RAG 준비용.",
    }


def main():
    info = fetch_schema()
    with open(_OUT, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(f"OK — {_OUT} 저장")
    print(f"샤드: {info['num_parquet_shards']}개 · 첫 샤드 행수: {info['num_rows_in_shard']:,}")
    print(f"컬럼 {info['num_columns']}개:")
    for c in info["columns"]:
        print(f"  - {c['name']}  ({c['type']})")


if __name__ == "__main__":
    main()
