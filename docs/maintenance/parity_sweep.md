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

37,705 cases. Four classes have been closed; four remain, and the accepted
list stands at 1,220.

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

**Lookup tables that answered for keys nobody put in them** (2026-09-01),
4 cases. The read-side twin of the `__proto__` column bug above. A plain
JavaScript object inherits `Object.prototype`, so `COUNTRY_NAMES["constructor"]`
is the `Object` *function* and `COUNTRY_NAMES["__proto__"]` is
`Object.prototype`: a contact whose country column read `constructor`
normalized to a function, and one reading `__proto__` to an object, from an API
typed to return a string. A Python `dict` has no inherited members, so the same
rows stayed strings, a type confusion in one package and a cross-language
divergence at the same time. `JSON.stringify` drops a function silently, so the
field simply vanished from `to_dict()` output rather than failing loudly.

Only member names that survive the lookup's own `.toLowerCase()` could collide,
which is why `__proto__` and `constructor` leaked and `toString` did not, too
fine a distinction to leave as the reason it is safe, so the three geo tables
are now built with `Object.create(null)` and the reads are safe by
construction. The same `in` operator was gating language codes, so
`generate_language("constructor")` passed the "is it supported" check and then
died destructuring `Object.prototype` as a `[code, name]` pair; those gates use
`Object.hasOwn` now. Pinned by mirrored tests in both languages and six cases
in the CI probe, each proven to fail against the previous build.

This class was found while re-verifying the encoding fix above, not by the
sweep's own summary, which had it filed under "remaining string-normalizer
edges, all on values that are not what the field is for", a label that reads as
*accepted and understood* and was hiding a genuine defect. A baselined
divergence is a deferred question, not an answered one, and a category label is
a claim about the cases in it that nobody had checked.

**A deliberate inner capital in a name** (2026-09-02), 149 cases: 49 direct
and 100 payload results downstream of them. JavaScript kept `DeAngelo`,
`LaToya`, `DiCaprio` and `JoAnne` as they arrived; Python lowercased the whole
string before handing it to nameparser and returned `Deangelo`, `Latoya`,
`Dicaprio`, `Joanne`. This one was a product decision rather than a bug, and
it sat in the table as such through two rounds of this work.

The decision is to keep the capital, in both packages. Three facts settled it.
Python's own `AddressNormalizer` already read an inner capital as "cased on
purpose" (`123 iPhone Way` has had a test since it stopped using
`str.title()`), so the name normalizer disagreed with its own sibling, not
just with the other language. Nothing in
either package compares normalized names for equality: the CLI's `--dedupe`
keys are emails, phones and source IDs, so the canonicalization that flattening
bought had no consumer. And nameparser's documented default is to leave a
mixed-case name alone; the `.lower()` that flattened it was this package's
override, not the library's behavior. A source system that took the trouble to
write `DeAngelo` is a better authority on that name than a casing rule is.

Python restores the capitals after nameparser has run, matching by lowercase
form because nameparser reorders `Smith, DeAngelo` to `DeAngelo Smith` and
consumes the comma. A piece is restored only where nameparser applied its
generic rule; a particle it lowercased, a suffix it expanded to `Ph.D.` or a
Mac-name it built are left as it made them, which is also what the JavaScript
port does. The JavaScript test was ASCII-only (`[A-Z]`) and is `\p{Lu}` now,
so `DeÁngelo` is kept in both. Pinned by mirrored tests in both languages and
four cases in the CI probe; the Python tests were run against the previous
implementation first, and eight of the fifteen fail there.

The old "name casing rules" label covered three unrelated causes, so the sweep
now files them separately. The inner-capital class should read zero from here
on, and a case landing in it again is a regression on one side rather than a
preference.

The 2.12.0 pre-release review then attacked the rule with a 300-name
adversarial corpus and found two places the two packages still parted:
Python did not restore a capital that nameparser had cased by its
per-run-around-an-apostrophe rule (`O'DeAngelo` came back `O'Deangelo`) or its
Mc/Mac rule (`McDeAngelo` came back `McDeangelo`), and JavaScript's Mac rule
ran before its hyphen split and lowercased the second half of
`MacIntyre-Smith`. Both are closed: Python restores wherever nameparser
capitalized, and only leaves alone a particle nameparser lowercased on purpose
or a suffix it expanded; JavaScript splits on the hyphen first and lets a
deliberately cased Mac-name stand. The sweep count did not move, because none
of those shapes were in its value list; the curated probe now carries five of
them so CI does. The sweep did catch the one thing the tightened Python rule
briefly broke - `0x1F`, a token nameparser cannot case at all, which the rule
"restore where nameparser capitalized" wrongly left as `0x1f` - which is the
sweep doing precisely the job it exists for.

### Open

| cases | class |
| --- | --- |
| 634 | The two packages wrap different phone libraries. `phonenumbers` is Google's full port; `libphonenumber-js` is a smaller reimplementation. They agree on phone numbers and disagree on inputs that are not: `"Apt 4B"` parses to `+6127842` under a default region of `AU` in JavaScript and to nothing in Python. Every such case is `is_valid: false`. Closing this means changing which library one side uses, or refusing to normalize a value the library calls invalid - a behavior change for everyone, not a bug fix. |
| 435 | Payload results downstream of the classes above and below. |
| 98 | Non-name text in a name field: URLs, emails, addresses and separator-joined tokens. nameparser cases every `\w+` run, so `https://example.com/path` becomes `Https://Example.com/Path` and `alpha;beta` becomes `Alpha;Beta`; the JavaScript port cases whitespace-separated words and returns `Https://example.com/path` and `Alpha;beta`. The two also parse a run of commas and drop an emoji differently. Neither output is a name, and closing this means agreeing on how to case a value that is not what the field is for, which is not worth a behavior change to either package. It is listed separately so it can no longer hide a real name behind a garbage one. |
| 28 | Unicode case mapping, where the two runtimes disagree on a handful of code points: `ß` title-cases to `Ss` in Python and `SS` in JavaScript; `ǅ` (U+01C5, a titlecase letter) stays itself in Python and becomes `Ǆ` in JavaScript; `İstanbul` lowercases to `i̇stanbul` and re-cases differently. Python's `str.title()` also treats any non-letter as a word boundary, so `a<zero-width space>b` capitalizes both halves in Python and only the first in JavaScript. |
| 25 | Fuzzy header tie-breaks, on headers that match nothing in particular. Real headers agree exactly: `contact_email`, `contact_phone`, `contact_name`, `contact_company` and `contact_first_name` all resolve identically at 1.0. The disagreements are headers like `contact_Mystery`, where both languages score 0.7 and pick different winners. |

All 40 generated languages, and every result-helper case, agree exactly.

## Proving the gate can see what it compares

A parity gate that cannot represent a value is not comparing it, and it reports
green either way. The probes decoded the JavaScript subprocess with the
platform default encoding until 2.11.2, which is cp1252 on Windows and UTF-8 on
the Linux CI runner, so every non-ASCII comparison was mojibake locally and
nobody noticed, because the runner was fine and every curated case was ASCII.
The dangerous half is not the false red it produced; it is that the same
mangling can make a real mismatch compare equal.

So "0 mismatches" only means something once three separate things are true, and
each is worth re-establishing rather than assuming after any change to how the
two sides talk to each other:

1. **Fidelity.** The exact code points the JavaScript side sends arrive intact,
   verified per code point rather than by eye. U+FEFF must still be U+FEFF, not
   the three characters cp1252 turns it into.
2. **The bug was real.** Decoding the same run with the platform default still
   mangles those code points on this machine, and manufactures mismatches the
   pinned encoding does not. A fix whose absence changes nothing was not a fix.
3. **Red is reachable.** A deliberately injected non-ASCII divergence, U+FEFF
   swapped for U+200B, is detected and reported. Both characters are invisible,
   so this is precisely the mismatch a mangled transport would swallow.

The reporting path has to survive it too. `--show` printed raw and died with
`UnicodeEncodeError` on a cp1252 console, so the tool you reach for *after* the
gate flags something crashed on exactly the non-English cases it exists to
explain. It escapes to ASCII now, which also beats a UTF-8 console here: most
of this corpus is invisible characters, and a U+200B rendered as nothing looks
identical to a U+FEFF rendered as nothing.
