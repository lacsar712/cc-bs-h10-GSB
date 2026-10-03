"""回归测试：落盘成功的读数必须出现在列表里（含连着快交的最新一笔），复核员保持只读。"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt

from api.app import SECRET, create_reading, list_readings


def _token(sub="reviewer", role="reader"):
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    return jwt.encode({"sub": sub, "role": role, "exp": exp}, SECRET, algorithm="HS256")


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *_args, **_kwargs):
        return None

    async def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def cursor(self):
        return _Cursor(self._rows)


class _Pool:
    def __init__(self, rows):
        self._rows = rows

    def connection(self):
        return _Conn(self._rows)


def _request(pool=None, token=None, body=None):
    return SimpleNamespace(
        app=SimpleNamespace(ctx=SimpleNamespace(pool=pool)),
        headers={"Authorization": f"Bearer {token}"} if token else {},
        json=body,
    )


def _row(reading_id, **overrides):
    row = {
        "id": reading_id,
        "span_code": f"跨中S{reading_id}",
        "microstrain": 150.0,
        "verdict": "合格",
        "reason": "微应变处于 80～220 με 设计允许范围内",
        "status": "done",
        "created_by": "surveyor",
        "created_at": None,
        "processed_at": None,
    }
    row.update(overrides)
    return row


def test_list_returns_every_persisted_row_including_newest():
    # 连着快交三笔，ORDER BY id DESC 后最新一笔排在 rows[0]，也不得被藏掉
    rows = [_row(3), _row(2), _row(1)]
    request = _request(pool=_Pool(rows), token=_token())
    response = asyncio.run(list_readings(request))
    assert response.status == 200
    payload = json.loads(response.body)
    assert [r["id"] for r in payload] == [3, 2, 1]


def test_list_requires_login():
    response = asyncio.run(list_readings(_request(pool=_Pool([]))))
    assert response.status == 401


def test_reviewer_stays_read_only():
    request = _request(
        pool=_Pool([]),
        token=_token(sub="reviewer", role="reader"),
        body={"span_code": "跨中S9", "microstrain": 120.0},
    )
    response = asyncio.run(create_reading(request))
    assert response.status == 403
