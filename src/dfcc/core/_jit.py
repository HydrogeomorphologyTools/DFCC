"""Numba shim: uses numba when present (cached), plain Python otherwise."""
try:
    import numba as _nb
    HAVE_NUMBA = True

    def njit(*a, **k):
        k.setdefault("cache", True)
        if len(a) == 1 and callable(a[0]):
            return _nb.njit(cache=True)(a[0])
        return _nb.njit(*a, **k)
except ImportError:  # pragma: no cover
    HAVE_NUMBA = False

    def njit(*a, **k):
        if len(a) == 1 and callable(a[0]):
            return a[0]
        return lambda f: f
