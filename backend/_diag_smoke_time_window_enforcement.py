"""Deprecated diagnostic script.

This diagnostic was term-scoped and is incompatible with the academic-year-only
model.
"""


def main() -> int:
    raise SystemExit(
        "Deprecated: this diagnostic was term-scoped and does not apply to the academic-year-only model."
    )


if __name__ == "__main__":
    raise SystemExit(main())
