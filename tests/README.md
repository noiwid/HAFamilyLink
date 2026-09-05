# Integration tests

The test suite uses Home Assistant fixtures, mocks, and deliberately fake
credentials. It must not connect to Google or a real Home Assistant instance.

Run the latest stable Home Assistant test suite:

```bash
python -m pip install -r requirements-test-homeassistant.txt
python -m pytest --disable-socket --allow-unix-socket tests/custom_components/familylink
```

CI also runs the same suite against the declared minimum Home Assistant version
using `requirements-test-homeassistant-minimum.txt`. The historical test harness
wheel is extracted separately because its metadata references an unavailable
development-only mypy build; all runtime test dependencies are pinned explicitly
and checked with `pip check` before the suite runs.

To reproduce the minimum-version job, download the
`pytest-homeassistant-custom-component==0.13.111` wheel with `--no-deps`, extract
it into a temporary directory, add that directory to `PYTHONPATH`, and run the
same pytest command. The wheel metadata then registers its plugin automatically.
