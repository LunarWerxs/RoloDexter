# RoloDexter - Pricing

RoloDexter is free and open-source software, licensed under the **MIT License**.

## Cost to use

| Item | Cost |
| --- | --- |
| Python package (`pip install rolodexter`) | $0 |
| JavaScript/TypeScript package (`npm install rolodexter`) | $0 |
| License | MIT, free for commercial and personal use |
| Core matching & normalization | $0, runs entirely locally, no API key, no network call |
| CLI (`rolodexter map`, `profile`, `explain`, `fields`) | $0 |
| Optional extras (`fuzzy`, `pandas`, `i18n-generate`, `all`) | $0 |

## Bring-your-own-API-key costs

**None.** RoloDexter does not call any third-party paid API and does not
require an API key for its core function. The only network activity is
optional and self-contained: generating alias caches for the 39 non-English
languages fetches data once per language, then caches it locally so no
further network access is needed for that language. There is no metered
service, no RoloDexter-hosted backend, and no usage-based billing anywhere
in the product.

The only real "cost" is the compute you already have: RoloDexter runs inside
your own Python or Node process, so it inherits whatever hosting or CI you
already pay for, nothing separate to provision for RoloDexter itself.

## Paid tier

There is no paid tier, no seat pricing, no usage cap, and no enterprise
edition. Every feature described on the product page (the four-layer
matching pipeline, confidence scoring, value normalization, batch and
streaming processing, pandas DataFrame support, the CLI, schema
compile-once, and 40-language alias generation) ships in the open-source
package at v2.12.0.

## Support

Support is community-based: file an issue on GitHub. There is no paid
support contract.

## Links

- License (full text): https://github.com/LunarWerxs/RoloDexter/blob/main/LICENSE
- Source: https://github.com/LunarWerxs/RoloDexter
- PyPI: https://pypi.org/project/rolodexter/
- npm: https://www.npmjs.com/package/rolodexter
- Home: https://rolodexter.lunarwerx.com/

Last updated: 2026-08-23
