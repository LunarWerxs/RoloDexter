"""Cross-language differential sweep: generated inputs, not curated ones.

``parity_probe.py`` pins behavior on cases a human chose.  That is the right
shape for a CI gate, and it is also its blind spot: it can only catch a
divergence somebody already thought of.  This walks a generated corpus - every
canonical field crossed with a broad value list, header variants, phone
functions across regions, result helpers, and all 40 generated languages -
through both implementations and diffs the results.

It is not wired into CI.  Some divergences are inherited rather than fixable:
the two packages wrap different phone libraries (``phonenumbers`` vs
``libphonenumber-js``), which disagree on inputs that are not phone numbers.
Those live in ``parity_sweep_baseline.json`` so that a *new* divergence still
fails the run.  Read the baseline as a list of accepted differences - shrinking
it is progress; growing it needs a reason in the commit message.

    python scripts/parity_sweep.py                    # fails on new divergence
    python scripts/parity_sweep.py --update-baseline  # after a deliberate change
    python scripts/parity_sweep.py --show phones      # print examples

The JS half runs from ``packages/js/dist``, so build it first.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
JS_SWEEP = Path(__file__).with_name("parity_sweep_js.mjs")
BASELINE = Path(__file__).with_name("parity_sweep_baseline.json")

sys.path.insert(0, str(ROOT / "src"))

# parity_sweep_values sits beside this file, which is sys.path[0] when this
# runs as a script. The value corpus lives there because it is the only part
# that needs invisible and control characters, and it builds them with chr()
# so neither file holds a literal NUL, ESC or BOM.
import rolodexter as r  # noqa: E402
from parity_sweep_values import VALUES  # noqa: E402

REGIONS = [None, "US", "GB", "DE", "AU", "IN", "BR", "JP", "ZZ", "", "us"]

NAME_FIELDS = {"first_name", "last_name", "full_name", "middle_name", "nickname", "prefix", "suffix"}
PHONE_FIELDS = {"phone", "mobile", "work_phone", "home_phone", "fax", "whatsapp"}

HEADER_ROOTS = [
    "fname", "first name", "First_Name", "FirstName", "first-name", "given name",
    "surname", "last name", "LastName", "family name", "full name", "name",
    "email", "e-mail", "E_Mail", "emailAddress", "email address", "mail",
    "phone", "Phone Number", "mobile", "cell", "telephone", "tel", "work phone",
    "company", "Compny", "organisation", "organization", "employer", "biz",
    "title", "job title", "position", "role", "address", "address 1", "street",
    "city", "town", "state", "province", "zip", "postal code", "postcode",
    "country", "birthday", "dob", "date of birth", "website", "url", "linkedin",
    "twitter", "notes", "comments", "tags", "labels", "source", "owner",
    "created", "created at", "updated", "score", "revenue", "currency",
    "Mystery", "Column X", "", " ", "__proto__", "constructor", "id",
    "primary_phone_id", "contact_email_id", "website_id", "email_ref",
    "owner_id", "shipping_company_id", "cust_plz", "nom", "prenom", "correo",
    "telefono", "empresa", "firma", "vorname", "nachname", "e-post",
]

FIXTURES: list[dict[str, Any]] = [
    {"fname": "Ada", "surname": "Lovelace", "mobile": "(202) 555-0143"},
    {"person": {"fname": "Ada", "contact": {"email": "a@b.co"}}},
    {"E-Mail": "a@x.com", "E-Mail__2": "b@x.com"},
    {"E-Mail": "", "E-Mail__2": "bob@y.co.uk"},
    {"tags": "alpha,beta", "labels": ["beta", "gamma"]},
    {"__proto__": "x", "fname": "Ada"},
    {"notes": "reach me at +1 202 555 0143 or ada@example.com"},
    {"phone": "not a phone"},
    {"Mystery": "202-555-0143", "Column X": "K1A 0B1"},
    {"birthday": "03/04/2024", "created": "2024/3/5"},
    {"full_name": "maria dos santos", "Compny": "Acme"},
    {},
    {"": ""},
    {"a": {"b": {"c": {"d": "deep"}}}},
    {"phone": ["+1 202 555 0143", "202.555.0143"]},
]


def canonical_fields() -> list[str]:
    return sorted(
        getattr(r.CanonicalField, name)
        for name in dir(r.CanonicalField)
        if name.isupper() and not name.startswith("_")
    )


def header_variants(root: str) -> list[str]:
    """Mutate a header the way a real export would."""
    out = {root, root.upper(), root.lower(), root.title()}
    out.add(root.replace(" ", "_"))
    out.add(root.replace(" ", "-"))
    out.add(root.replace(" ", ""))
    out.add(f"  {root}  ")
    out.add(f"contact_{root}")
    out.add(f"{root}_1")
    out.add(f"{root}__2")
    out.add(f"*{root}")
    return sorted(out)


def _build_normalize_corpus() -> list[dict[str, Any]]:
    normalize = [
        {"id": f"nv|{field}|{index}", "field": field, "value": value}
        for field in canonical_fields()
        for index, value in enumerate(VALUES)
    ]
    # Region is only supposed to matter for phone-shaped fields. Prove it
    # rather than assume it.
    phoneish = [v for v in VALUES if isinstance(v, str) and any(c.isdigit() for c in v)]
    normalize.extend(
        {
            "id": f"nvr|{field}|{region}|{index}",
            "field": field,
            "value": value,
            "default_region": region,
        }
        for field in (*sorted(PHONE_FIELDS), "unknown", "notes")
        for region in REGIONS
        for index, value in enumerate(phoneish)
    )
    return normalize


def _all_headers() -> list[str]:
    all_headers: list[str] = []
    for root in HEADER_ROOTS:
        all_headers.extend(header_variants(root))
    return all_headers


def _build_schema_corpus(all_headers: list[str]) -> list[dict[str, Any]]:
    unique_headers = sorted(set(all_headers))

    schemas: list[dict[str, Any]] = [
        {"id": f"sch|{index}", "headers": [header]}
        for index, header in enumerate(unique_headers)
    ]
    # Whole-sheet plans, where collisions and ordering decide the outcome.
    schemas.extend(
        {"id": f"schmulti|{size}|{start}", "headers": all_headers[start : start + size]}
        for size in (2, 3, 5, 8)
        for start in range(0, len(all_headers) - size, 37)
    )
    schemas.extend(
        {
            "id": f"schthresh|{threshold}",
            "headers": ["Compny", "fname", "Mystery", "e-mail"],
            "mapper_options": {"confidence_threshold": threshold},
        }
        for threshold in (0.0, 0.5, 0.8, 0.95, 0.99, 1.0)
    )
    return schemas


def _build_payload_corpus(all_headers: list[str]) -> list[dict[str, Any]]:
    unique_headers = sorted(set(all_headers))

    payloads: list[dict[str, Any]] = [
        {"id": f"pl|{hindex}|{vindex}", "payload": {header: value}}
        for hindex, header in enumerate(unique_headers[::3])
        for vindex, value in enumerate(VALUES[::4])
    ]
    option_sets = [{}, {"depth": 1}, {"depth": 2}, {"depth": 3}, {"extract_embedded_phones": True}]
    mapper_sets = [
        {},
        {"strict": True},
        {"normalize": False},
        {"confidence_threshold": 0.95},
        {"default_region": "GB"},
    ]
    payloads.extend(
        {
            "id": f"plopt|{findex}|{oindex}|{mindex}",
            "payload": fixture,
            "options": options,
            "mapper_options": mapper_options,
        }
        for findex, fixture in enumerate(FIXTURES)
        for oindex, options in enumerate(option_sets)
        for mindex, mapper_options in enumerate(mapper_sets)
    )
    return payloads


def _build_phone_corpus() -> list[dict[str, Any]]:
    phone_values = [v for v in VALUES if isinstance(v, str)] + [None, 123, True, [], {}]
    phones: list[dict[str, Any]] = [
        {"id": f"ph|{fn}|{region}|{index}", "fn": fn, "value": value, "default_region": region}
        for fn in ("parse", "format_e164", "format_international", "format_national", "is_valid", "number_type")
        for region in REGIONS
        for index, value in enumerate(phone_values)
    ]
    pairs = ["+1 202 555 0143", "2025550143", "202-555-0143", "+44 20 7946 0958", "", "junk", "555-0143"]
    phones.extend(
        {
            "id": f"phmatch|{a_index}|{b_index}|{region}",
            "fn": "is_number_match",
            "a": a,
            "b": b,
            "default_region": region,
        }
        for (a_index, a), (b_index, b) in itertools.product(enumerate(pairs), repeat=2)
        for region in (None, "US", "GB")
    )
    matcher_texts = [
        "call +1 202 555 0143 now",
        "two: +1 202 555 0143 and +44 20 7946 0958",
        "none here at all",
        "+1 202 555 0143+1 202 555 0199",
        "ext: +1 202 555 0143 ext. 99 end",
        "é +1 202 555 0143 é",
        "1234567890 9876543210 5551234567",
    ]
    phones.extend(
        {
            "id": f"phmatcher|{index}|{region}|{max_matches}",
            "fn": "matcher",
            "value": text,
            "default_region": region,
            "max_matches": max_matches,
        }
        for index, text in enumerate(matcher_texts)
        for region in (None, "US", "GB")
        for max_matches in (None, 0, 1, 2, 5)
    )
    return phones


def _build_object_corpus() -> list[dict[str, Any]]:
    objects = [
        {"id": f"obj|{index}", "payload": fixture}
        for index, fixture in enumerate(FIXTURES)
    ]
    objects.extend(
        {"id": f"objemb|{index}", "payload": fixture, "options": {"extract_embedded_phones": True}}
        for index, fixture in enumerate(FIXTURES)
    )
    return objects


def _build_language_corpus() -> list[dict[str, Any]]:
    return [{"id": f"lang|{code}", "lang_code": code} for code in sorted(r.SUPPORTED_LANGUAGES)]


def build_corpus() -> dict[str, list[dict[str, Any]]]:
    all_headers = _all_headers()
    return {
        "normalize": _build_normalize_corpus(),
        "schemas": _build_schema_corpus(all_headers),
        "payloads": _build_payload_corpus(all_headers),
        "phones": _build_phone_corpus(),
        "objects": _build_object_corpus(),
        "languages": _build_language_corpus(),
    }


# ── Canonical result shapes ───────────────────────────────────────────


def decode(value: Any) -> Any:
    """Rehydrate the typed markers the corpus uses for non-JSON scalars."""
    if isinstance(value, dict) and "$" in value:
        tag = value["$"]
        if tag == "float":
            return float(value["v"])
        if tag == "nan":
            return float("nan")
        if tag == "inf":
            return float("inf")
        if tag == "ninf":
            return float("-inf")
        raise ValueError(f"unknown marker {tag}")
    if isinstance(value, dict):
        return {key: decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


def num(value: float | bool) -> str:
    """Canonical text for a number, so 1 and 1.0 cannot look different."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return "<nan>"
        if math.isinf(value):
            return "<inf>" if value > 0 else "<-inf>"
        if value.is_integer() and abs(value) < 1e21:
            return str(int(value))
        return repr(value)
    return str(value)


def simplify(value: Any) -> Any:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, (bool, int, float)):
        return {"n": num(value)}
    if isinstance(value, (list, tuple)):
        return [simplify(item) for item in value]
    if isinstance(value, dict):
        return {key: simplify(item) for key, item in sorted(value.items())}
    name = type(value).__name__
    if name == "MappingResult":
        return {
            "normalized": simplify(value.normalized),
            "unmapped": simplify(value.unmapped),
            "field_matches": simplify(list(value.field_matches)),
            "warnings": [str(warning) for warning in value.warnings],
        }
    if name == "FieldMatch":
        return {
            "original": value.original,
            "canonical": simplify(value.canonical),
            "confidence": simplify(value.confidence),
            "strategy": value.strategy,
            "service": simplify(value.service),
            "is_matched": simplify(value.is_matched),
        }
    if name == "MappingSchema":
        return {
            "matches": simplify(value.matches),
            "default_region": simplify(value.default_region),
            "column_map": simplify(value.column_map()),
            "to_dict": simplify(value.to_dict()),
        }
    if name == "PhoneNumber":
        return {
            "calling_code": simplify(value.calling_code),
            "national_number": simplify(value.national_number),
            "extension": simplify(value.extension),
            "raw": simplify(value.raw),
            "e164": simplify(value.e164),
            "is_possible": simplify(value.is_possible),
            "is_valid": simplify(value.is_valid),
            "country_codes": simplify(list(value.country_codes)),
        }
    if name == "PhoneNumberMatch":
        return {
            "start": simplify(value.start),
            "end": simplify(value.end),
            "raw_string": value.raw_string,
            "number": simplify(value.number),
        }
    return {"repr": repr(value)}


def capture(fn: Any) -> Any:
    try:
        return {"ok": simplify(fn())}
    except Exception as exc:  # the error IS the observation here
        return {"err": type(exc).__name__, "msg": str(exc)}


def phone_case(item: dict[str, Any]) -> Any:
    fn = item["fn"]
    value = decode(item.get("value"))
    region = item.get("default_region")
    if fn == "parse":
        return r.parse(value, region)
    if fn == "format_e164":
        return r.format_e164(value, region)
    # These three take a parsed PhoneNumber, not a raw string.
    if fn == "format_international":
        return r.format_international(r.parse(value, region))
    if fn == "format_national":
        return r.format_national(r.parse(value, region))
    if fn == "number_type":
        return r.number_type(r.parse(value, region))
    if fn == "is_valid":
        return r.is_valid(value, region)
    if fn == "is_number_match":
        return r.is_number_match(item["a"], item["b"], region)
    if fn == "matcher":
        return list(
            r.PhoneNumberMatcher(value, default_region=region, max_matches=item.get("max_matches"))
        )
    raise ValueError(f"unknown phone fn {fn}")


def result_helpers(item: dict[str, Any]) -> dict[str, Any]:
    result = r.ContactMapper().map_payload(decode(item["payload"]), **item.get("options", {}))
    return {
        "matched_count": result.matched_count,
        "unmatched_count": result.unmatched_count,
        "match_rate": result.match_rate,
        "dict": result.to_dict(),
        "explain": result.explain(),
        "all_emails": result.get_all_emails(),
        "all_phones": result.get_all_phones(),
        "identity_keys": result.get_identity_keys(),
        "get_match_fname": result.get_match("fname"),
        "get_match_missing": result.get_match("nope"),
    }


def language(item: dict[str, Any]) -> dict[str, Any]:
    data = dict(r.generate_language(item["lang_code"]))
    # Stamped per run, so it is noise here rather than behavior.
    data.pop("generated_at", None)
    return data


def python_results(corpus: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    out["normalize"] = {
        item["id"]: capture(
            lambda item=item: r.normalize_value(
                item["field"], decode(item.get("value")), default_region=item.get("default_region")
            )
        )
        for item in corpus["normalize"]
    }
    out["schemas"] = {
        item["id"]: capture(
            lambda item=item: r.ContactMapper(**item.get("mapper_options", {})).compile_schema(
                item["headers"]
            )
        )
        for item in corpus["schemas"]
    }
    out["payloads"] = {
        item["id"]: capture(
            lambda item=item: r.ContactMapper(**item.get("mapper_options", {})).map_payload(
                decode(item["payload"]), **item.get("options", {})
            )
        )
        for item in corpus["payloads"]
    }
    out["phones"] = {item["id"]: capture(lambda item=item: phone_case(item)) for item in corpus["phones"]}
    out["objects"] = {item["id"]: capture(lambda item=item: result_helpers(item)) for item in corpus["objects"]}
    out["languages"] = {item["id"]: capture(lambda item=item: language(item)) for item in corpus["languages"]}
    return out


def js_results(corpus: dict[str, list[dict[str, Any]]], out_path: Path) -> dict[str, dict[str, Any]]:
    subprocess.run(
        [_node(), str(JS_SWEEP), str(out_path)],
        input=json.dumps(corpus),
        text=True,
        # Pinned for the same reason as in parity_probe.py, and pinned even
        # though json.dumps escapes to ASCII by default: this corpus is mostly
        # invisible and control characters, so the day someone passes
        # ensure_ascii=False the platform default would quietly mangle the
        # inputs on Windows and the sweep would compare the wrong values.
        encoding="utf-8",
        check=True,
        cwd=ROOT,
    )
    return json.loads(out_path.read_text(encoding="utf-8"))


def _node() -> str:
    return "node"


# ── Classification ────────────────────────────────────────────────────

PHONE_LIBS = "phone libraries disagree on inputs that are not phone numbers"
# Name divergences are split three ways because one label ("name casing
# rules") hid three different causes, one of which was a decision waiting to
# be taken.  It was taken in 2.12.0 - both packages now keep a deliberate
# inner capital ("DeAngelo") - so NAME_INNER_CAPITAL should read zero, and a
# case landing there again is a regression on one side, not a preference.
NAME_INNER_CAPITAL = "name: deliberate inner capital dropped by one side"
# Python's str.upper()/title() and JavaScript's String.toUpperCase() disagree
# on a few code points: U+00DF title-cases to "Ss" in Python and "SS" in
# JavaScript, U+01C5 (Dz with caron, a titlecase letter) to itself and to
# U+01C4, and Python's title() treats any non-letter as a word boundary.
NAME_UNICODE = "name: Unicode case mapping differs between the runtimes"
# URLs, emails, addresses and separator-joined tokens that landed in a name
# field.  nameparser cases every \w+ run ("Https://Example.com/Path"), the
# JavaScript port cases whitespace-separated words ("Https://example.com/path"),
# and the two parse commas and emoji differently.  Neither output is a name;
# closing this class means agreeing on how to case a value that is not what
# the field is for, which is not worth a behavior change to either package.
NAME_NOT_A_NAME = "name: non-name text in a name field (URL, email, address, separators)"
BOM = "JS trim() strips U+FEFF, Python strip() does not"
FUZZY = "fuzzy header tie-break on headers that match nothing"
DOWNSTREAM = "payload result, downstream of a normalizer or matcher"


def _has_inner_capital(value: str) -> bool:
    return any(
        not word.isupper() and not word.islower() and any(c.isupper() for c in word[1:])
        for word in value.split()
    )


def classify(section: str, item: dict[str, Any]) -> str:
    if section == "phones":
        return PHONE_LIBS
    if section == "schemas":
        return FUZZY
    if section == "normalize":
        # The whitespace test belongs to this branch only. Tested first, it
        # claimed every payload that merely CARRIED a byte-order mark - five
        # cases whose real disagreement was which field the header resolved to.
        if chr(0xFEFF) in json.dumps(item, ensure_ascii=False):
            return BOM
        if item["field"] in PHONE_FIELDS:
            return PHONE_LIBS
        if item["field"] in NAME_FIELDS:
            value = item["value"] if isinstance(item["value"], str) else ""
            if _has_inner_capital(value):
                return NAME_INNER_CAPITAL
            if not value.isascii():
                return NAME_UNICODE
            return NAME_NOT_A_NAME
        return "other string normalizer"
    if section == "payloads":
        return DOWNSTREAM
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-baseline", action="store_true", help="record today's divergences as accepted")
    parser.add_argument("--show", metavar="SECTION", help="print example diffs from one section")
    args = parser.parse_args()

    corpus = build_corpus()
    scratch = ROOT / "packages" / "js" / "dist" / ".parity-sweep-js.json"
    scratch.parent.mkdir(parents=True, exist_ok=True)
    python_side = python_results(corpus)
    js_side = js_results(corpus, scratch)
    scratch.unlink(missing_ok=True)

    index = {item["id"]: (section, item) for section, items in corpus.items() for item in items}
    diverging: list[str] = []
    for section in python_side:
        if python_side[section].keys() != js_side[section].keys():
            print(f"corpus mismatch in {section}: the two runs saw different cases", file=sys.stderr)
            return 2
        diverging.extend(
            f"{section}/{case_id}"
            for case_id, value in python_side[section].items()
            if value != js_side[section][case_id]
        )

    if args.update_baseline:
        BASELINE.write_text(
            json.dumps(
                {
                    "note": (
                        "Accepted cross-language divergences, by case id. Shrinking this "
                        "list is progress; growing it needs a reason in the commit message. "
                        "Regenerate with: python scripts/parity_sweep.py --update-baseline"
                    ),
                    "cases": sorted(diverging),
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"baseline updated: {len(diverging)} accepted divergences")
        return 0

    accepted = set(json.loads(BASELINE.read_text(encoding="utf-8"))["cases"]) if BASELINE.exists() else set()
    new = sorted(set(diverging) - accepted)
    fixed = sorted(accepted - set(diverging))

    total = sum(len(items) for items in corpus.values())
    print(f"{total} cases, {len(diverging)} diverging ({len(accepted)} accepted)")

    counts: dict[str, int] = {}
    for entry in diverging:
        section, case_id = entry.split("/", 1)
        label = classify(section, index[case_id][1])
        counts[label] = counts.get(label, 0) + 1
    for label, count in sorted(counts.items(), key=lambda pair: -pair[1]):
        print(f"  {count:>5}  {label}")

    if args.show:
        shown = 0
        for entry in diverging:
            section, case_id = entry.split("/", 1)
            if section != args.show:
                continue
            # Escaped to ASCII, deliberately.  This printed raw until 2.11.1 and
            # died with UnicodeEncodeError on a cp1252 console - the tool you
            # reach for *after* the gate reports a divergence, crashing on
            # exactly the non-English cases it exists to explain.  Escaping also
            # beats a UTF-8 console here: most of this corpus is invisible, and
            # a U+200B rendered as nothing looks identical to a U+FEFF rendered
            # as nothing, which is the same defect as mojibake, only quieter.
            print(f"\n-- {case_id}")
            print(f"   in : {json.dumps(index[case_id][1])[:200]}")
            print(f"   py : {json.dumps(python_side[section][case_id])[:200]}")
            print(f"   js : {json.dumps(js_side[section][case_id])[:200]}")
            shown += 1
            if shown >= 10:
                break

    if fixed:
        print(f"\n{len(fixed)} baselined divergence(s) now agree - rerun with --update-baseline:")
        for entry in fixed[:10]:
            print(f"  {entry}")
    if new:
        print(f"\n{len(new)} NEW divergence(s):")
        for entry in new[:20]:
            print(f"  {entry}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
