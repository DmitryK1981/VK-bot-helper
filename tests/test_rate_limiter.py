from services.rate_limiter import RateLimiter


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_blocks_after_limit_and_recovers():
    clock = Clock()
    rl = RateLimiter(3, 60, clock)
    assert [rl.acquire(1) for _ in range(3)] == [0, 0, 0]
    wait = rl.acquire(1)
    assert 59 < wait <= 60
    clock.t += 61
    assert rl.acquire(1) == 0


def test_limits_are_per_user():
    rl = RateLimiter(1, 60, Clock())
    assert rl.acquire(1) == 0
    assert rl.acquire(1) > 0
    assert rl.acquire(2) == 0


def test_rejected_requests_do_not_extend_window():
    clock = Clock()
    rl = RateLimiter(1, 10, clock)
    rl.acquire(1)
    clock.t += 5
    assert rl.acquire(1) > 0
    clock.t += 5.1
    assert rl.acquire(1) == 0
