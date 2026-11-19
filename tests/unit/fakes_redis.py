"""Redis giả (in-memory) hỗ trợ đúng các lệnh mà HistoryService/RateLimiter dùng."""


class FakePipeline:
    def __init__(self, redis):
        self.r, self.ops = redis, []

    def __getattr__(self, name):
        def record(*args):
            self.ops.append((name, args))
            return self
        return record

    async def execute(self):
        self.r._check()
        out = []
        for name, args in self.ops:
            out.append(getattr(self.r, "_" + name)(*args))
        return out


class FakeRedis:
    def __init__(self, fail: bool = False):
        self.data: dict[str, object] = {}
        self.ttls: dict[str, int] = {}
        self.fail = fail

    def _check(self):
        if self.fail:
            raise ConnectionError("redis down")

    def pipeline(self, transaction: bool = True):
        return FakePipeline(self)

    # --- lệnh dùng trong pipeline (đồng bộ) ---
    def _incr(self, key):
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    def _expire(self, key, ttl):
        self.ttls[key] = ttl
        return True

    def _delete(self, key):
        return 1 if self.data.pop(key, None) is not None else 0

    def _rpush(self, key, *values):
        self.data.setdefault(key, []).extend(values)
        return len(self.data[key])

    def _ltrim(self, key, start, stop):
        lst = self.data.get(key, [])
        n = len(lst)
        start = max(n + start, 0) if start < 0 else start
        stop = n + stop if stop < 0 else stop
        self.data[key] = lst[start: stop + 1]
        return True

    # --- lệnh gọi trực tiếp (async) ---
    async def lrange(self, key, start, stop):
        self._check()
        lst = list(self.data.get(key, []))
        return lst if stop == -1 else lst[start: stop + 1]

    async def exists(self, key):
        self._check()
        return 1 if key in self.data else 0

    async def delete(self, key):
        self._check()
        return self._delete(key)

    async def ping(self):
        self._check()
        return True
