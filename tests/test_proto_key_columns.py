"""A column literally named ``__proto__`` is data, everywhere.

Python's dict has no special key, so these all pass here and always did.  They
exist because the JavaScript package must behave the same, and there a plain
``obj[key] = value`` treats ``"__proto__"`` as the prototype setter: the value
is dropped and the object's prototype is replaced with caller-supplied data.
``map_payload`` was hardened against that; ``compile_schema`` and everything
built from it were not, so eight entry points silently lost the column in one
language and kept it in the other.  These are the Python half of the contract,
mirrored one-for-one by ``packages/js/test/mapper.test.ts``.
"""

from __future__ import annotations

from rolodexter import ContactMapper, MappingSchema

KEY = "__proto__"


def row() -> dict[str, str]:
    return {KEY: "kept", "fname": "Ada"}


class TestProtoKeyInPayloads:
    def test_map_payload_keeps_it_unmapped(self) -> None:
        result = ContactMapper().map_payload(row())
        assert result.unmapped == {KEY: "kept"}
        assert result.to_dict()["unmapped"] == {KEY: "kept"}

    def test_map_batch_and_stream_keep_it(self) -> None:
        assert ContactMapper().map_batch([row()])[0].unmapped == {KEY: "kept"}
        streamed = next(iter(ContactMapper().map_stream([row()])))
        assert streamed.unmapped == {KEY: "kept"}

    def test_it_survives_as_a_canonical_field_too(self) -> None:
        mapper = ContactMapper(overrides={"weird": KEY})
        assert mapper.map_payload({"weird": "v"}).normalized == {KEY: "v"}


class TestProtoKeyInSchemas:
    def test_compile_schema_keeps_the_header(self) -> None:
        schema = ContactMapper().compile_schema([KEY, "fname"])
        assert sorted(schema.matches) == [KEY, "fname"]
        assert schema.unmatched_headers() == [KEY]

    def test_a_matched_proto_header_reaches_column_map(self) -> None:
        schema = ContactMapper(overrides={KEY: "email"}).compile_schema([KEY, "fname"])
        assert schema.column_map() == {KEY: "email", "fname": "first_name"}

    def test_the_lockfile_records_it(self) -> None:
        # to_dict is the mapping lockfile: a column missing from it is a column
        # that routes differently on the next run.
        schema = ContactMapper().compile_schema([KEY, "fname"])
        assert sorted(schema.to_dict()["columns"]) == [KEY, "fname"]

    def test_the_lockfile_round_trips(self) -> None:
        schema = ContactMapper().compile_schema([KEY, "fname"])
        restored = MappingSchema.from_dict(schema.to_dict(), ContactMapper())
        assert sorted(restored.matches) == [KEY, "fname"]

    def test_apply_keeps_the_column(self) -> None:
        schema = ContactMapper().compile_schema([KEY, "fname"])
        assert schema.apply(row()).unmapped == {KEY: "kept"}

    def test_seeded_header_cache_keeps_it(self) -> None:
        mapper = ContactMapper()
        schema = mapper.compile_schema([KEY, "fname"])
        mapper.seed_header_cache(dict(schema.matches))
        assert mapper.map_payload(row()).unmapped == {KEY: "kept"}
