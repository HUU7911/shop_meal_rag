import pytest

from app.core.errors import RateLimited
from app.core.rate_limit import RateLimiter


class FakePipeline:
    def __init__(self, redis):
        self.r, self.ops = redis, []

    def incr(self, key):
        self.ops.append(("incr", key))

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))

    async def execute(self):
        if self.r.fail:
            raise ConnectionError("redis down")
        out = []
        for op in self.ops:
            if op[0] == "incr":
                self.r.data[op[1]] = self.r.data.get(op[1], 0) + 1
                out.append(self.r.data[op[1]])
            else:
                self.r.ttls[op[1]] = op[2]
                out.append(True)
        return out


class FakeRedis:
    def __init__(self, fail=False):
        self.data, self.ttls, self.fail = {}, {}, fail

    def pipeline(self, transaction=True):
        return FakePipeline(self)


async def test_allows_up_to_limit_then_blocks_with_retry_after():
    limiter = RateLimiter(FakeRedis(), 2, clock=lambda: 1_000_000 + 10)   # giây thứ 10 của phút
    await limiter.check("u:1")
    await limiter.check("u:1")
    with pytest.raises(RateLimited) as exc:
        await limiter.check("u:1")
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) == 60 - (1_000_010 % 60)


async def test_identities_are_independent_and_window_resets():
    now = [1_000_000.0]
    redis = FakeRedis()
    limiter = RateLimiter(redis, 1, clock=lambda: now[0])
    await limiter.check("u:1")
    await limiter.check("u:2")                 # khác identity: không bị ảnh hưởng
    with pytest.raises(RateLimited):
        await limiter.check("u:1")
    now[0] += 60                               # sang phút mới
    await limiter.check("u:1")


async def test_every_counter_gets_a_ttl():
    redis = FakeRedis()
    await RateLimiter(redis, 5, clock=lambda: 120.0).check("ip:1.2.3.4")
    assert redis.ttls and all(ttl > 0 for ttl in redis.ttls.values())


async def test_fail_open_when_redis_down():
    limiter = RateLimiter(FakeRedis(fail=True), 1)
    for _ in range(5):
        await limiter.check("u:1")             # không raise


async def test_disabled_when_limit_zero_or_no_redis():
    await RateLimiter(FakeRedis(), 0).check("u:1")
    await RateLimiter(None, 5).check("u:1")
