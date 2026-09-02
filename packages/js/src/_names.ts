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

function smartTitleCase(value: string): string {
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
      // src/rolodexter/_normalizers.py). The test is Unicode-aware, as
      // Python's str.isupper() is, so "DeÁngelo" is kept in both packages.
      if (word !== word.toUpperCase() && word !== word.toLowerCase() && /\p{Lu}/u.test(word.slice(1))) {
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
  ["m.d.", "M.d."],
  ["cpa", "Cpa"],
  ["sr", "Sr"],
  ["sr.", "Sr."],
  ["ii", "II"],
  ["iii", "III"],
  ["iv", "IV"],
  ["v", "V"],
  ["phd", "Ph.D."],
  ["ph.d.", "Ph.d."],
]);

function nameWord(word: string, index = 0): string {
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
  if (index > 0 && NAME_PARTICLES.has(lower)) {
    return lower;
  }
  if (word.includes("@")) {
    return word.split("@").map((part) => nameWord(part, index)).join("@");
  }
  if (lower.startsWith("mac") && lower.length > 3) {
    return `Mac${lower[3]?.toUpperCase() ?? ""}${lower.slice(4)}`;
  }
  if (word.includes("-")) {
    return word.split("-").map((part) => nameWord(part, index)).join("-");
  }
  return smartTitleCase(word);
}

function smartNameCase(value: string): string {
  return pySplitSpace(value).map((word, index) => nameWord(word, index)).join(" ");
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
    const components = [parsed.title, parsed.first, parsed.middle, parsed.last, parsed.suffix]
      .filter(Boolean)
      .map((part, index) => pySplitSpace(part).map((word, wordIndex) => nameWord(word, index + wordIndex)).join(" "));
    normalized = components.join(" ");
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
export { normalizeName, parseNameParts, smartTitleCase, splitNameNickname };
