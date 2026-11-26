# Contributing

Thanks for helping improve SatPI.

## Setup

```bash
pip install -e ".[dev]"
pre-commit install
make test        # pytest, core path (no torch/GDAL needed)
make lint
```

## Pull requests

- Keep changes focused; include tests for new behavior.
- `ruff check src tests` and `pytest` must pass. CI runs both on Python 3.11 and 3.12.
- Never commit data, model checkpoints, credentials, or document files
  (PDF, Word, PowerPoint, Excel). `.gitignore` blocks the common formats;
  check `git status` before committing.

## Adding a data source

Every source must be licensed for the use you intend and credited.

1. Read the provider's license or terms of use.
2. Add the ingestor (register a new `kind`, see `docs/ADAPTING.md`).
3. Add a row to **Section 2** and an entry to **Section 4** of
   [`DATA_SOURCES.md`](DATA_SOURCES.md): provider, license, required
   attribution and citation, caveats, and a link to the terms.
4. If attribution is mandatory, add it to the block in Section 3 and to `NOTICE`.

`tests/test_data_sources.py` fails if a configured or registered kind is
missing from `DATA_SOURCES.md`.

Do not add sources whose terms forbid redistribution of derived products, or
commercial sources, without discussing it in an issue first.

## Licensing of contributions

By contributing you agree that your contribution is licensed under the
Apache License 2.0, as stated in section 5 of the license.
