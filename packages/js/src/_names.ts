// Personal-name casing, particles, titles and part extraction.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { pyCollapseSpace, pySplitSpace, pyStrip } from "./_pycompat.js";


function titleWord(word: string): string {
  if (!word) {
    return word;
  }
  const lower = word.toLowerCase();
  if (/^\d+(st|nd|rd|th)$/.test(lower)) {
    return lower;
  }
  if (lower.startsWith("mc") && lower.length > 2) {
    return `Mc${lower[2]?.toUpperCase() ?? ""}${lower.slice(3)}`;
  }
  return `${lower.slice(0, 1).toUpperCase()}${lower.slice(1)}`;
}

// A mixed-case word with a capital after its first letter was cased on
// purpose: "DeAngelo", "LaToya", "eBay". All-upper, all-lower and
// conventionally-cased words carry no such signal. Unicode-aware, like
// Python's str.isupper(), which is the same test on the Python side.
function hasDeliberateCapital(word: string): boolean {
  return word !== word.toUpperCase() && word !== word.toLowerCase() && /\p{Lu}/u.test(word.slice(1));
}

// US states, DC and territories, then Canadian provinces and territories.
// Owned here, not in _geo.ts, because the place casing below needs it;
// _geo.ts imports it as its state-code table. Same set as _REGION_CODES in
// src/rolodexter/_text.py.
const REGION_CODES: ReadonlySet<string> = new Set([
  "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI",
  "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI",
  "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC",
  "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
  "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR", "VI", "GU", "AS",
  "MP", "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE",
  "QC", "SK", "YT",
]);

// Words written in capitals wherever they stand in an all-caps place value:
// compass points, post-office and military mail words, and country
// abbreviations. Region codes are kept upper too, but only where a region
// code stands (see regionPosition), so "LA JOLLA" still reads "La Jolla".
const ALWAYS_UPPER: ReadonlySet<string> = new Set([
  "N", "S", "E", "W", "NE", "NW", "SE", "SW",
  "PO", "APO", "FPO", "DC", "USA", "US", "UK",
]);

/** Python's `str.isupper()`: has a cased letter and no lowercase one. */
function isAllCaps(text: string): boolean {
  return text === text.toUpperCase() && text !== text.toLowerCase();
}

/** True where a region code stands: after a comma or before a postcode. */
function regionPosition(words: string[], index: number): boolean {
  if (index > 0 && (words[index - 1] ?? "").endsWith(",")) {
    return true;
  }
  return index + 1 < words.length && /[0-9]/.test(words[index + 1] ?? "");
}

/** True when an all-caps place value should keep words[index] as written. */
function keepUpperInCaps(words: string[], index: number): boolean {
  const word = words[index] ?? "";
  const key = word.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
  if (/^\d+(st|nd|rd|th)$/.test(key.toLowerCase())) {
    return false;
  }
  if (/[0-9]/.test(word)) {
    return true;
  }
  if (ALWAYS_UPPER.has(key)) {
    return true;
  }
  return REGION_CODES.has(key) && regionPosition(words, index);
}

/**
 * Title-case a place value (address, city, state) without mangling it.
 * Mirrors _smart_titlecase in src/rolodexter/_text.py: a value that mixes
 * case keeps its all-caps words and words holding a digit as written ("IL",
 * "NW", "PO", "USA", "4B"); an all-caps value is re-cased word by word except
 * compass points, PO/APO/FPO, USA/US/UK/DC, words holding a digit, and a
 * region code where a region code stands.
 */
function smartTitleCase(value: string): string {
  const shouting = isAllCaps(value);
  const words = pySplitSpace(value);
  return words
    .map((word, index) => {
      if (hasDeliberateCapital(word)) {
        return word;
      }
      if (shouting ? keepUpperInCaps(words, index) : isAllCaps(word) || /[0-9]/.test(word)) {
        return word;
      }
      if (word.includes("'")) {
        const [first = "", ...rest] = word.split("'");
        return [titleWord(first), ...rest.map((part) => (part.length > 1 ? titleWord(part) : part.toLowerCase()))].join("'");
      }
      return titleWord(word);
    })
    .join(" ");
}

function nameTitleCase(value: string): string {
  return pySplitSpace(value)
    .map((word) => {
      // A mixed-case word with a capital after the first letter is left
      // exactly as it arrived: "DeAngelo", "LaToya", "eBay". A source that
      // took the trouble to case a name is a better authority on it than a
      // rule is. All-upper and all-lower words are re-cased from rules, so
      // "DEANGELO" and "deangelo" both become "Deangelo". Since 2.12.0 the
      // Python package applies the same rule (it restores these capitals
      // after nameparser has flattened them; the decision and its trade-off
      // are written on _restore_deliberate_capitals in
      // src/rolodexter/_normalizers.py).
      if (hasDeliberateCapital(word)) {
        return word;
      }
      if (word.includes("'")) {
        const [first = "", ...rest] = word.split("'");
        return [titleWord(first), ...rest.map((part) => (part.length > 1 ? titleWord(part) : part.toLowerCase()))].join("'");
      }
      return titleWord(word);
    })
    .join(" ");
}

// Kept in step with Python's nameparser prefix set plus core.py's
// _EXTRA_PREFIXES. "dos", "den" and "della" were missing, which made
// "maria dos santos" capitalize as "Maria Dos Santos" in JS and
// "Maria dos Santos" in Python for the same input.
const NAME_PARTICLES = new Set([
  "aan",
  "abu",
  "aen",
  "af",
  "al",
  "auf",
  "av",
  "bar",
  "bat",
  "bin",
  "bint",
  "bon",
  "da",
  "dal",
  "das",
  "de",
  "degli",
  "dei",
  "del",
  "dela",
  "della",
  "delle",
  "delli",
  "dello",
  "dem",
  "den",
  "der",
  "des",
  "di",
  "do",
  "dos",
  "du",
  "el",
  "freiherr",
  "freiherrin",
  "heer",
  "het",
  "ibn",
  "la",
  "le",
  "mac",
  "mc",
  "op",
  "san",
  "santa",
  "st",
  "ste",
  "te",
  "ten",
  "ter",
  "tho",
  "thoe",
  "van",
  "vande",
  "vander",
  "vd",
  "vel",
  "vom",
  "von",
  "zu",
  "zum",
  "zur",
]);

const NAME_TITLES = new Map([
  ["capt", "Capt"],
  ["capt.", "Capt."],
  ["dr", "Dr"],
  ["dr.", "Dr."],
  ["hon", "Hon"],
  ["hon.", "Hon."],
  ["mr", "Mr"],
  ["mr.", "Mr."],
  ["mrs", "Mrs"],
  ["mrs.", "Mrs."],
  ["ms", "Ms"],
  ["ms.", "Ms."],
  ["miss", "Miss"],
  ["dame", "Dame"],
  ["prof", "Prof"],
  ["prof.", "Prof."],
  ["rev", "Rev"],
  ["rev.", "Rev."],
  ["sir", "Sir"],
  ["mx", "Mx"],
  ["st", "St"],
  ["st.", "St."],
]);

const NAME_SUFFIXES = new Map([
  ["jr", "Jr"],
  ["jr.", "Jr."],
  ["md", "M.D."],
  ["m.d.", "M.D."],
  ["cpa", "CPA"],
  ["sr", "Sr"],
  ["sr.", "Sr."],
  ["ii", "II"],
  ["iii", "III"],
  ["iv", "IV"],
  ["v", "V"],
  ["phd", "Ph.D."],
  ["ph.d.", "Ph.D."],
]);

// Names that begin "Mac"/"Mc" but are not Mac-names, so an all-caps or
// all-lower spelling is not re-cased to "MacHado". Same list as
// _NOT_MAC_NAMES in src/rolodexter/_normalizers.py. Real Mac-names
// ("Macaulay", "Macdonald") stay out so the rule still applies to them.
const NOT_MAC_NAMES: ReadonlySet<string> = new Set([
  "macaluso", "macario", "macarena", "macchia", "macchio", "mace",
  "maceda", "macedo", "macedonio", "macek", "macey", "macha",
  "machado", "machen", "machiavelli", "machin", "macho", "machowski",
  "machuca", "macias", "maciej", "maciejewski", "maciel", "mack",
  "mackenzie", "mackey", "mackie", "mackiewicz", "mackin", "macklin",
  "mackowiak", "macon", "macri", "macy",
]);

// nameparser's Mac/Mc shape: "mac" or "mc" and at least two more letters.
const MAC_NAME_RE = /^(ma?c)[\p{L}\p{N}_]{2,}/iu;

function capitalizeLower(lower: string): string {
  return `${lower.slice(0, 1).toUpperCase()}${lower.slice(1)}`;
}

// `followed` is true when another name word comes after this one: a particle
// is lowercased only inside a name ("Jean le Pen"), never as its last word
// ("Jennifer Le", "Michael Do").
function nameWord(word: string, index = 0, followed = false): string {
  const lower = word.toLowerCase();
  if (index > 0 && lower === "and") {
    return "and";
  }
  if (NAME_TITLES.has(lower)) {
    return NAME_TITLES.get(lower) ?? word;
  }
  if (NAME_SUFFIXES.has(lower)) {
    return NAME_SUFFIXES.get(lower) ?? word;
  }
  if (index > 0 && followed && NAME_PARTICLES.has(lower)) {
    return lower;
  }
  if (word.includes("@")) {
    return word.split("@").map((part) => nameWord(part, index, followed)).join("@");
  }
  // Split on the hyphen BEFORE the Mac rule, so each half is cased on its
  // own. The rule used to run first and lowercased everything after "Mac",
  // hyphen included: "MacIntyre-Smith" came back "MacIntyre-smith" while
  // Python, whose nameparser cases each word run separately, kept "Smith".
  if (word.includes("-")) {
    return word.split("-").map((part) => nameWord(part, index, followed)).join("-");
  }
  // The Mac/Mc rule ("mcdonald" -> "McDonald", "MACARTHUR" -> "MacArthur")
  // re-cases only a word that arrived without casing of its own and is not a
  // known non-Mac name. "Machado" and "Mcdonald" as written keep the plain
  // spelling; a deliberately cased one ("MacArthur") is the source's call.
  const mac = MAC_NAME_RE.exec(word);
  if (mac) {
    const uncased = word === word.toUpperCase() || word === word.toLowerCase();
    if (uncased && !NOT_MAC_NAMES.has(lower)) {
      const cut = mac[1]?.length ?? 0;
      return `${capitalizeLower(lower.slice(0, cut))}${capitalizeLower(lower.slice(cut))}`;
    }
    return hasDeliberateCapital(word) ? word : capitalizeLower(lower);
  }
  return nameTitleCase(word);
}

function nameWords(words: string[]): string {
  return words.map((word, index) => nameWord(word, index, index < words.length - 1)).join(" ");
}

function smartNameCase(value: string): string {
  return nameWords(pySplitSpace(value));
}

function splitNameNickname(value: string): { text: string; nickname: string } {
  let nickname = "";
  const text = value
    .replace(/(?:"([^"]+)"|\(([^)]+)\))/g, (_match, quoted: string | undefined, parenthesized: string | undefined) => {
      if (!nickname) {
        nickname = pyStrip(quoted ?? parenthesized ?? "");
      }
      return " ";
    });
  return { text: pyStrip(pyCollapseSpace(text)), nickname };
}

function normalizeName(value: string): string {
  const { text, nickname } = splitNameNickname(pyStrip(value));
  let normalized = text ? smartNameCase(text) : "";
  if (/^the\s+hon\.\s+/i.test(text)) {
    normalized = normalized.replace(/^The\s+Hon\.\s+/, "the Hon. ");
  } else if (/^the\s+hon\s+/i.test(text)) {
    normalized = normalized.replace(/^The\s+Hon\s+/, "the Hon ");
  } else if (/^the\s+honorable\s+/i.test(text)) {
    normalized = normalized.replace(/^The\s+Honorable\s+/, "the Honorable ");
  } else if (text.includes(",")) {
    const parsed = parseNameParts(text, "");
    const words = [parsed.title, parsed.first, parsed.middle, parsed.last, parsed.suffix]
      .filter(Boolean)
      .flatMap((part) => pySplitSpace(part));
    normalized = nameWords(words);
  }
  if (!nickname) {
    return normalized || value;
  }
  const normalizedNickname = nickname.toLowerCase();
  return normalized ? `${normalized} (${normalizedNickname})` : `(${normalizedNickname})`;
}

function consumeNameTitles(parts: string[]): string {
  const titles: string[] = [];
  if (
    parts.length >= 2 &&
    parts[0]?.toLowerCase() === "the" &&
    ["hon", "hon.", "honorable"].includes(parts[1]?.toLowerCase() ?? "")
  ) {
    titles.push(parts.shift() ?? "");
    titles.push(parts.shift() ?? "");
    return titles.join(" ");
  }
  if (
    parts.length >= 2 &&
    parts[0]?.toLowerCase() === "his" &&
    parts[1]?.toLowerCase() === "excellency"
  ) {
    titles.push(parts.shift() ?? "");
    titles.push(parts.shift() ?? "");
    return titles.join(" ");
  }
  if (
    parts.length >= 3 &&
    ["mr", "mr."].includes(parts[0]?.toLowerCase() ?? "") &&
    parts[1]?.toLowerCase() === "and" &&
    ["mrs", "mrs."].includes(parts[2]?.toLowerCase() ?? "")
  ) {
    titles.push(parts.shift() ?? "");
    titles.push(parts.shift() ?? "");
    titles.push(parts.shift() ?? "");
    return titles.join(" ");
  }
  while (parts.length > 0 && NAME_TITLES.has((parts[0] ?? "").toLowerCase())) {
    titles.push(parts.shift() ?? "");
  }
  return titles.join(" ");
}

function consumeNameSuffix(parts: string[]): string {
  if (parts.length === 0) {
    return "";
  }
  const lastLower = (parts.at(-1) ?? "").toLowerCase();
  if (!NAME_SUFFIXES.has(lastLower)) {
    return "";
  }
  return parts.pop() ?? "";
}

function parseNameParts(text: string, nickname: string): Record<string, string> {
  const commaIndex = text.indexOf(",");
  if (commaIndex !== -1) {
    let last = pyStrip(text.slice(0, commaIndex));
    const parts = pySplitSpace(pyStrip(text.slice(commaIndex + 1))).filter(Boolean).map((part) => part.replace(/,$/, ""));

    if (parts.length > 0 && parts.every((part) => NAME_SUFFIXES.has(part.toLowerCase()))) {
      const parsed = parseNameParts(last, nickname);
      parsed.suffix = parts.join(" ");
      return parsed;
    }

    const lastParts = pySplitSpace(last).filter(Boolean);
    const lastSuffix = consumeNameSuffix(lastParts);
    last = lastParts.join(" ");
    const title = consumeNameTitles(parts);
    const suffix = consumeNameSuffix(parts) || lastSuffix;
    return {
      title,
      first: parts[0] ?? "",
      middle: parts.slice(1).join(" "),
      last,
      suffix,
      nickname,
    };
  }

  const parts = pySplitSpace(text).filter(Boolean);
  const title = consumeNameTitles(parts);
  const suffix = consumeNameSuffix(parts);
  let first = parts[0] ?? "";
  let middle = "";
  let last = "";
  if (parts.length > 1) {
    const particleStart = parts.findIndex((part, index) => index > 0 && NAME_PARTICLES.has(part.toLowerCase()));
    if (particleStart > 0) {
      first = parts[0] ?? "";
      middle = parts.slice(1, particleStart).join(" ");
      last = parts.slice(particleStart).join(" ");
    } else {
      middle = parts.length > 2 ? parts.slice(1, -1).join(" ") : "";
      last = parts.at(-1) ?? "";
    }
  }
  if (parts.length === 1 && ["st", "st."].includes(title.toLowerCase())) {
    first = "";
    last = parts[0] ?? "";
  }

  return {
    title,
    first,
    middle,
    last,
    suffix,
    nickname,
  };
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { REGION_CODES, normalizeName, parseNameParts, smartTitleCase, splitNameNickname };
