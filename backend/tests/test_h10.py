"""回归：落盘成功的读数不得再按"整理中"口径从总览藏起。

- GET /api/readings 必须返回全部已落盘行，含最新一笔
- 连着快交时，每一笔落盘成功后都立刻在总览可见
- 复核员（reader）保持只读：可 GET，POST 一律 403 且不写库
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt

from api import app as app_module
from api.app import create_reading, list_readings

BASE_TIME = datetime(2026, 10, 3, 8, 0, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, store):
        self._store = store
        self._result = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("insert"):
            span_code, microstrain, username = params
            row = {
                "id": max((r["id"] for r in self._store), default=0) + 1,
                "span_code": span_code,
                "microstrain": microstrain,
                "verdict": None,
                "reason": None,
                "status": "pending",
                "created_by": username,
                "created_at": BASE_TIME,
                "processed_at": None,
            }
            # 与 ORDER BY id DESC 一致：最新行排在最前
            self._store.insert(0, row)
            self._result = [row]
        else:
            self._result = list(self._store)

    async def fetchall(self):
        return self._result

    async def fetchone(self):
        return self._result[0] if self._result else None


class FakeConnection:
    def __init__(self, store):
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def cursor(self):
        return FakeCursor(self._store)

    async def commit(self):
        return None


class FakePool:
    def __init__(self, store):
        self.store = store

    def connection(self):
        return FakeConnection(self.store)


def make_request(pool, token=None, body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return SimpleNamespace(
        app=SimpleNamespace(ctx=SimpleNamespace(pool=pool)),
        headers=headers,
        json=body,
    )


def make_token(username, role):
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    return jwt.encode(
        {"sub": username, "role": role, "exp": exp},
        app_module.SECRET,
        algorithm="HS256",
    )


def payload_of(response):
    return json.loads(response.body)


def seed_rows():
    return [
        {
            "id": 2,
            "span_code": "支座S2",
            "microstrain": 40.0,
            "verdict": "越界",
            "reason": "微应变低于 80 με 设计下限",
            "status": "done",
            "created_by": "surveyor",
            "created_at": BASE_TIME,
            "processed_at": BASE_TIME,
        },
        {
            "id": 1,
            "span_code": "跨中S1",
            "microstrain": 150.0,
            "verdict": "合格",
            "reason": "微应变处于 80～220 με 设计允许范围内",
            "status": "done",
            "created_by": "surveyor",
            "created_at": BASE_TIME,
            "processed_at": BASE_TIME,
        },
    ]


def test_newest_persisted_row_stays_in_overview():
    pool = FakePool(seed_rows())
    token = make_token("surveyor", "writer")

    async def flow():
        created = await create_reading(
            make_request(pool, token, {"span_code": "跨中S3", "microstrain": 120.0})
        )
        assert created.status == 201
        return await list_readings(make_request(pool, token))

    response = asyncio.run(flow())
    assert response.status == 200
    ids = [row["id"] for row in payload_of(response)]
    assert ids == [3, 2, 1]  # 最新一笔落盘后必须留在总览，不得被藏


def test_rapid_successive_submissions_all_stay_visible():
    pool = FakePool(seed_rows())
    token = make_token("surveyor", "writer")

    async def flow():
        expected = 2
        for i in range(3):
            created = await create_reading(
                make_request(
                    pool, token, {"span_code": f"连续梁L{i}", "microstrain": 90.0 + i}
                )
            )
            assert created.status == 201
            expected += 1
            listed = await list_readings(make_request(pool, token))
            rows = payload_of(listed)
            # 每一笔落盘成功后都立刻可见，且最新一笔排在最前
            assert len(rows) == expected
            assert rows[0]["span_code"] == f"连续梁L{i}"

    asyncio.run(flow())


def test_reviewer_stays_read_only():
    pool = FakePool(seed_rows())
    token = make_token("reviewer", "reader")

    async def flow():
        listed = await list_readings(make_request(pool, token))
        assert listed.status == 200
        assert len(payload_of(listed)) == 2
        denied = await create_reading(
            make_request(pool, token, {"span_code": "跨中S9", "microstrain": 100.0})
        )
        assert denied.status == 403

    asyncio.run(flow())
    assert len(pool.store) == 2  # 只读：复核员提交不得落库


def test_anonymous_gets_401():
    pool = FakePool(seed_rows())

    async def flow():
        return await list_readings(make_request(pool))

    response = asyncio.run(flow())
    assert response.status == 401
