// Renders the published TypeScript API surface as text for scripts/api_snapshot.py.
//
// WHY: the npm package's exports can drift (a removed method, a re-shaped
// option interface, a renamed CanonicalField member) without any test
// noticing, because the tests exercise behavior, not shape. This walks the
// three package entry points with the TypeScript checker, straight from
// src/ (no build needed), and prints one JSON document on stdout:
//
//   { "modules": { "<module>": { "<export>": { "text", "refs", "members" } } },
//     "types":   { "<local declaration>": { "text", "refs", "members" } } }
//
// "text" is the export's declaration as a reader sees it, "members" its
// public members one line each, and "refs" identifiers a const's initializer
// reaches that its declared type hides (CanonicalField's member values live
// in CANONICAL_FIELD_MEMBERS, not in the CanonicalFieldEnum type). The Python
// driver hashes, diffs and writes the goldens, so both languages share one
// verdict logic.
import path from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";

const PACKAGE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC_DIR = path.join(PACKAGE_ROOT, "src").replace(/\\/g, "/");

// package.json "exports" subpath -> the Python module it mirrors, so the two
// halves of the snapshot line up name for name.
const ENTRIES = {
  rolodexter: "public.ts",
  "rolodexter.core": "core.ts",
  "rolodexter.i18n": "i18n.ts",
};

const FLAGS = ts.TypeFormatFlags.NoTruncation;
// The package version is a string literal type; every release would read as
// an API change. Its shape (a string) is the API, its value is not.
const VERSION_EXPORTS = new Set(["__version__", "version"]);
const MAX_INITIALIZER_CHARS = 160;
const printer = ts.createPrinter({ removeComments: true });

function loadProgram() {
  const configPath = path.join(PACKAGE_ROOT, "tsconfig.json");
  const config = ts.readConfigFile(configPath, ts.sys.readFile);
  if (config.error) throw new Error(ts.flattenDiagnosticMessageText(config.error.messageText, "\n"));
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, PACKAGE_ROOT);
  const roots = Object.values(ENTRIES).map((file) => path.join(PACKAGE_ROOT, "src", file));
  return ts.createProgram(roots, { ...parsed.options, noEmit: true });
}

const program = loadProgram();
const checker = program.getTypeChecker();

function isLocalFile(sourceFile) {
  return sourceFile.fileName.replace(/\\/g, "/").startsWith(`${SRC_DIR}/`);
}

// A type printed without an enclosing scope can come out as
// import("<absolute path>").Name; the path is machine-specific, the name is not.
function clean(text) {
  return text.replace(/import\("[^"]*"\)\./g, "").replace(/\s+/g, " ").trim();
}

function print(node) {
  return clean(printer.printNode(ts.EmitHint.Unspecified, node, node.getSourceFile()));
}

function typeText(type) {
  return clean(checker.typeToString(type, undefined, FLAGS));
}

function signatureText(signature, kind = ts.SignatureKind.Call) {
  return clean(checker.signatureToString(signature, undefined, FLAGS, kind));
}

function isHiddenMember(symbol) {
  const name = symbol.getName();
  if (name.startsWith("_") || name.startsWith("#") || name === "prototype") return true;
  // Tuple indices (__all__[3]) shift whenever a name is added; the tuple's
  // own type text already lists every element in order.
  if (/^\d+$/.test(name)) return true;
  return (symbol.declarations ?? []).some((decl) => {
    const flags = ts.getCombinedModifierFlags(decl);
    if (flags & (ts.ModifierFlags.Private | ts.ModifierFlags.Protected)) return true;
    // stripInternal drops these from the published .d.ts, so they are not API.
    return ts.getJSDocTags(decl).some((tag) => tag.tagName.text === "internal");
  });
}

// A member belongs to this package's API when it is declared here, or is
// synthesized from a local mapped type (Record<CanonicalFieldName, ...>).
// Members inherited from the standard library (Error.stack, Array.map) are not.
function isOwnMember(symbol) {
  const decls = symbol.declarations ?? [];
  return decls.length === 0 || decls.some((decl) => isLocalFile(decl.getSourceFile()));
}

function memberLine(symbol, prefix = "") {
  const name = symbol.getName();
  const type = checker.getTypeOfSymbol(symbol);
  if (symbol.flags & ts.SymbolFlags.Method) {
    return type
      .getCallSignatures()
      .map((signature) => `${prefix}${name}${signatureText(signature)}`)
      .join("\n");
  }
  const optional = symbol.flags & ts.SymbolFlags.Optional ? "?" : "";
  // Members seen through a mapped type (Readonly<...>) keep their source
  // declarations but no valueDeclaration.
  const decl = symbol.valueDeclaration ?? symbol.declarations?.[0];
  const readonly =
    (decl && ts.getCombinedModifierFlags(decl) & ts.ModifierFlags.Readonly) ||
    (symbol.flags & ts.SymbolFlags.GetAccessor && !(symbol.flags & ts.SymbolFlags.SetAccessor))
      ? "readonly "
      : "";
  let line = `${prefix}${readonly}${name}${optional}: ${typeText(type)}`;
  // A declared type often cannot tell two values apart (every CanonicalField
  // member is a CanonicalFieldMember); a short initializer can.
  const initializer = decl && (ts.isPropertyAssignment(decl) || ts.isPropertyDeclaration(decl)) ? decl.initializer : undefined;
  if (initializer && !ts.isFunctionLike(initializer)) {
    const shown = print(initializer);
    if (shown.length <= MAX_INITIALIZER_CHARS) line += ` = ${shown}`;
  }
  return line;
}

function collectMembers(symbols, prefix = "") {
  const members = {};
  for (const symbol of symbols) {
    if (isHiddenMember(symbol) || !isOwnMember(symbol)) continue;
    members[symbol.getName()] = memberLine(symbol, prefix);
  }
  return members;
}

function initializerRefs(decl) {
  const refs = new Set();
  const initializer = decl && ts.isVariableDeclaration(decl) ? decl.initializer : undefined;
  if (!initializer) return [];
  const visit = (node) => {
    if (ts.isIdentifier(node)) refs.add(node.text);
    ts.forEachChild(node, visit);
  };
  visit(initializer);
  return [...refs].sort();
}

function heritage(decl) {
  const clauses = decl.heritageClauses ?? [];
  return clauses.length ? ` ${clauses.map(print).join(" ")}` : "";
}

function sortedObject(entries) {
  return Object.fromEntries(Object.entries(entries).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
}

function render(symbol, exportName) {
  const decl = symbol.valueDeclaration ?? symbol.declarations?.[0];
  const lines = [];
  let members = {};
  let refs = [];
  if (symbol.flags & ts.SymbolFlags.Class) {
    lines.push(`class ${exportName}${heritage(decl)}`);
    const staticType = checker.getTypeOfSymbol(symbol);
    for (const signature of staticType.getConstructSignatures()) {
      lines.push(`  constructor${signatureText(signature)}`);
    }
    const statics = collectMembers(checker.getPropertiesOfType(staticType), "static ");
    const instance = collectMembers(checker.getPropertiesOfType(checker.getDeclaredTypeOfSymbol(symbol)));
    members = { ...Object.fromEntries(Object.entries(statics).map(([k, v]) => [`static ${k}`, v])), ...instance };
  } else if (symbol.flags & (ts.SymbolFlags.Interface | ts.SymbolFlags.TypeAlias)) {
    // Type declarations have no bodies, so the printed source is the API.
    for (const declaration of symbol.declarations ?? []) lines.push(print(declaration));
    if (symbol.flags & ts.SymbolFlags.Interface) {
      members = collectMembers(checker.getPropertiesOfType(checker.getDeclaredTypeOfSymbol(symbol)));
    }
  } else if (symbol.flags & ts.SymbolFlags.Function) {
    for (const signature of checker.getTypeOfSymbol(symbol).getCallSignatures()) {
      lines.push(`function ${exportName}${signatureText(signature)}`);
    }
  } else {
    const type = checker.getTypeOfSymbol(symbol);
    const kind = symbol.flags & ts.SymbolFlags.Enum ? "enum" : "const";
    if (VERSION_EXPORTS.has(exportName)) {
      lines.push(`${kind} ${exportName}: ${typeText(checker.getBaseTypeOfLiteralType(type))}`);
    } else {
      lines.push(`${kind} ${exportName}: ${typeText(type)}`);
      members = collectMembers(checker.getPropertiesOfType(type));
      refs = initializerRefs(decl);
    }
  }
  members = sortedObject(members);
  for (const line of Object.values(members)) lines.push(...line.split("\n").map((text) => `  ${text}`));
  return { text: lines.join("\n"), refs, members };
}

function resolve(symbol) {
  return symbol.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(symbol) : symbol;
}

const modules = {};
for (const [moduleName, file] of Object.entries(ENTRIES)) {
  const sourceFile = program.getSourceFile(path.join(PACKAGE_ROOT, "src", file));
  if (!sourceFile) throw new Error(`entry point not found: src/${file}`);
  const exports = {};
  for (const exported of checker.getExportsOfModule(checker.getSymbolAtLocation(sourceFile))) {
    exports[exported.getName()] = render(resolve(exported), exported.getName());
  }
  modules[moduleName] = sortedObject(exports);
}

// Every top-level declaration in src/, exported or not: the driver follows an
// export's text into these to hash the types it depends on.
const types = {};
for (const sourceFile of program.getSourceFiles()) {
  if (!isLocalFile(sourceFile)) continue;
  for (const statement of sourceFile.statements) {
    const names = ts.isVariableStatement(statement)
      ? statement.declarationList.declarations.map((decl) => decl.name)
      : [statement.name];
    for (const nameNode of names) {
      if (!nameNode || !ts.isIdentifier(nameNode)) continue;
      if (
        !ts.isVariableStatement(statement) &&
        !ts.isClassDeclaration(statement) &&
        !ts.isInterfaceDeclaration(statement) &&
        !ts.isTypeAliasDeclaration(statement) &&
        !ts.isEnumDeclaration(statement)
      ) {
        continue;
      }
      const symbol = checker.getSymbolAtLocation(nameNode);
      if (!symbol || types[nameNode.text]) continue;
      types[nameNode.text] = render(symbol, nameNode.text);
    }
  }
}

process.stdout.write(`${JSON.stringify({ modules, types: sortedObject(types) })}\n`);
