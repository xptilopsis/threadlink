"""D12-R2：`validate_seed` 的 trace_link evidence **闭包断言** + **定向破坏**（注入坏 type/坏 id → fail）。

分层：**T3 craft**（纯数据校验，无 Django / 无 DB / 无 LLM）。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate_seed  # noqa: E402

SEED = ROOT / "fixtures" / "demo_seed.json"


def _data():
    return json.loads(SEED.read_text(encoding="utf-8"))


def test_seed_evidence_closure_ok():
    # fixtures 当前应全量合规（39 条 len=1、type 白名单、id 可解析）
    assert validate_seed.Validator(_data()).run() == []


def test_seed_evidence_covered_39():
    data = _data()
    tl = data["trace_links"]
    assert len(tl) == 39
    assert all(len(row.get("evidence", [])) == 1 for row in tl)


def test_seed_break_bad_type():
    data = _data()
    data["trace_links"][0]["evidence"] = [{"type": "bogus", "id": "DOC-001"}]
    errors = validate_seed.Validator(data).run()
    assert any("evidence.type" in err for err in errors)


def test_seed_break_bad_id():
    data = _data()
    data["trace_links"][0]["evidence"] = [{"type": "document", "id": "DOC-999"}]
    errors = validate_seed.Validator(data).run()
    assert any("DOC-999" in err for err in errors)


def test_seed_break_len_not_one():
    data = _data()
    data["trace_links"][0]["evidence"] = []
    errors = validate_seed.Validator(data).run()
    assert any("长度 1" in err for err in errors)