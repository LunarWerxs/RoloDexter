# The cross-language parity sweep

`scripts/parity_probe.py` and `scripts/cli_parity_probe.py` are the CI gates.
They pin behavior on cases a human chose, which is the right shape for a gate
and is also their blind spot: they can only catch a divergence somebody already
thought of.

`scripts/parity_sweep.py` is the other half. It generates a corpus - every
canonical field crossed with a broad value list, header variants, phone
functions across every region, result helpers, and all 40 generated languages -
and runs the whole thing through both implementations.

```bash
cd packages/js && npm run build && cd ../..   # the JS half runs from dist/
python scripts/parity_sweep.py                # exits 1 on a NEW divergence
python scripts/parity_sweep.py --show phones  # print examples from one section
python scripts/parity_sweep.py --update-baseline
```

It takes about 45 seconds and is **not wired into CI**, because some of what it
finds is inherited rather than fixable. Those cases are recorded in
`scripts/parity_sweep_baseline.json` so a *new* divergence still fails the run.
Read that file as a list of accepted differences: shrinking it is progress, and
growing it needs a reason in the commit message.

## What it found on the first run, 2026-09-01

37,705 cases. Eight entry points lost a column literally named `__proto__` in
JavaScript while Python kept it - fixed, and now pinned by unit tests in both
languages plus five cases in the CI probe. What remains is four classes of
known divergence, none of them a small fix:

| cases | class |
| --- | --- |
| 634 | The two packages wrap different phone libraries. `phonenumbers` is Google's full port; `libphonenumber-js` is a smaller reimplementation. They agree on phone numbers and disagree on inputs that are not: `"Apt 4B"` parses to `+6127842` under a default region of `AU` in JavaScript and to nothing in Python. Every such case is `is_valid: false`. |
| 530 | Payload results downstream of the two classes below. |
| 175 | Name casing. JavaScript preserves deliberate inner capitals, so `DeAngelo`, `LaToya`, `DiCaprio` and `JoAnne` survive; Python's nameparser lowercases first and returns `Deangelo`, `Latoya`, `Dicaprio`, `Joanne`. Python is destroying real names here, so matching JavaScript to Python would make the library worse - which makes this a release decision, not a cleanup. Unicode case mapping differs too: `ß` title-cases to `Ss` in Python and `SS` in JavaScript. |
| 158 | `U+FEFF` is whitespace to JavaScript's `String.prototype.trim()` and is not to Python's `str.strip()`. A value that is only a BOM normalizes to `""` in JavaScript and stays as-is in Python, and a BOM-prefixed header - what Excel writes - resolves at confidence 1.0/`exact` in JavaScript against 0.95/`normalized` in Python. Both still route the column correctly; only a `confidence_threshold` above 0.95 tells them apart. |
| 25 | Fuzzy header tie-breaks, on headers that match nothing in particular. Real headers agree exactly: `contact_email`, `contact_phone`, `contact_name`, `contact_company` and `contact_first_name` all resolve identically at 1.0. The disagreements are headers like `contact_Mystery`, where both languages score 0.7 and pick different winners. |

All 40 generated languages, and every result-helper case, agree exactly.
