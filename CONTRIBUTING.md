# Contributing

Create a focused branch, add tests for behavior changes, and run:

```bash
python -m pip install -e '.[dev]'
make check
```

Do not add Kubernetes write operations, Secret reads, undocumented HolmesGPT internals, or fabricated fallback diagnoses. Keep subprocess argument lists free of shell interpolation.
