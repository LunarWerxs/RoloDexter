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

## What it has found so far

37,705 cases. Two classes have been closed; four remain.

### Closed

**A column literally named `__proto__`** (2026-09-01). In JavaScript
`obj[key] = value` treats that key as the prototype setter, so eight entry
points silently lost the column while Python kept it - including `to_dict()`,
the mapping lockfile whose whole job is reproducible routing. Fixed, and pinned
by tests in both languages plus five cases in the CI probe.

**What counts as whitespace** (2026-09-01), 153 cases. Python's `str.strip()`
and JavaScript's `trim()` disagree in both directions: `trim()` strips U+FEFF
and Python does not, Python strips U+001C-001F and U+0085 and `trim()` does
not. A UTF-8 CSV puts a byte-order mark on its first field, so this reached
ordinary data - the same column normalized to `""` in one package and kept its
mark in the other, and a BOM-prefixed header (what Excel writes) resolved at
1.0/`exact` in JavaScript against 0.95/`normalized` in Python, so a confidence
threshold above 0.95 kept the column in one and dropped it in the other. The
JavaScript side now strips, splits and collapses on Python's 29-code-point
whitespace set, derived from CPython rather than typed by hand.

Two smaller things fell out of the same work. `pyRepr` now escapes
non-printable characters the way Python's `repr()` does, so a warning quoting a
value that holds a control character reads the same in both packages. And
`parity_probe.py` was decoding the JS side's output with the platform default
encoding, which is cp1252 on Windows - it reported mojibake mismatches locally
and, worse, could have hidden a real one. Both probes now pin UTF-8.

### Open

| cases | class |
| --- | --- |
| 634 | The two packages wrap different phone libraries. `phonenumbers` is Google's full port; `libphonenumber-js` is a smaller reimplementation. They agree on phone numbers and disagree on inputs that are not: `"Apt 4B"` parses to `+6127842` under a default region of `AU` in JavaScript and to nothing in Python. Every such case is `is_valid: false`. Closing this means changing which library one side uses, or refusing to normalize a value the library calls invalid - a behavior change for everyone, not a bug fix. |
| 535 | Payload results downstream of the classes above and below. |
| 175 | Name casing, and it needs a product decision rather than an engineering one. JavaScript preserves deliberate inner capitals, so `DeAngelo`, `LaToya`, `DiCaprio` and `JoAnne` survive; Python's nameparser lowercases first and returns `Deangelo`, `Latoya`, `Dicaprio`, `Joanne`. **Python is the side destroying real names**, so matching JavaScript to Python would make the library worse, and changing Python changes output for every existing user of a very common field. Unicode case mapping differs too (`ß` title-cases to `Ss` in Python and `SS` in JavaScript), as does what counts as a word boundary: Python's `str.title()` treats any non-letter as one, so `a<zero-width space>b` capitalizes both halves in Python and only the first in JavaScript. |
| 25 | Fuzzy header tie-breaks, on headers that match nothing in particular. Real headers agree exactly: `contact_email`, `contact_phone`, `contact_name`, `contact_company` and `contact_first_name` all resolve identically at 1.0. The disagreements are headers like `contact_Mystery`, where both languages score 0.7 and pick different winners. |
| 4 | Remaining string-normalizer edges, all on values that are not what the field is for. |

All 40 generated languages, and every result-helper case, agree exactly.
