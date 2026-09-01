// Python-parity errors, reprs and argument checks.
// Extracted verbatim from index.ts, which re-exports every public name here.



function pyRepr(value: unknown): string {
  if (typeof value === "string") {
    return pythonStringLiteral(value);
  }
  return pythonLiteral(value);
}

function pyString(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  return pythonLiteral(value);
}

function pythonPositionalTypeError(callable: string, expected: number, given: number): TypeError {
  const expectedWord = expected === 1 ? "argument" : "arguments";
  const givenVerb = given === 1 ? "was" : "were";
  return new TypeError(`${callable}() takes ${expected} positional ${expectedWord} but ${given} ${givenVerb} given`);
}

function pythonRangePositionalTypeError(callable: string, minExpected: number, maxExpected: number, given: number): TypeError {
  return new TypeError(`${callable}() takes from ${minExpected} to ${maxExpected} positional arguments but ${given} were given`);
}

function pythonMissingRequiredArg(callable: string, argName: string): TypeError {
  return new TypeError(`${callable}() missing 1 required positional argument: '${argName}'`);
}

function pythonMissingRequiredArgs(callable: string, argNames: string[]): TypeError {
  const quoted = argNames.map((argName) => `'${argName}'`);
  const joined = quoted.length === 2
    ? `${quoted[0]} and ${quoted[1]}`
    : `${quoted.slice(0, -1).join(", ")}, and ${quoted.at(-1)}`;
  return new TypeError(`${callable}() missing ${argNames.length} required positional arguments: ${joined}`);
}

function pythonLiteral(value: unknown): string {
  if (value === null) {
    return "None";
  }
  if (value === undefined) {
    return "None";
  }
  if (value === true) {
    return "True";
  }
  if (value === false) {
    return "False";
  }
  if (typeof value === "string") {
    return pythonStringLiteral(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => pythonLiteral(item)).join(", ")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>).map(([key, item]) => `${pythonLiteral(key)}: ${pythonLiteral(item)}`).join(", ")}}`;
  }
  return String(value);
}

function pythonStringLiteral(value: string): string {
  const quote = value.includes("'") && !value.includes("\"") ? "\"" : "'";
  const escaped = value
    .replace(/\\/g, "\\\\")
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t")
    .replace(new RegExp(quote, "g"), `\\${quote}`);
  return `${quote}${escaped}${quote}`;
}

function pythonTypeName(value: unknown): string {
  if (value === null || value === undefined) {
    return "NoneType";
  }
  if (Array.isArray(value)) {
    return "list";
  }
  if (typeof value === "boolean") {
    return "bool";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? "int" : "float";
  }
  if (typeof value === "string") {
    return "str";
  }
  if (typeof value === "object") {
    return "dict";
  }
  return typeof value;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function assertPythonMethodOptions(
  callable: string,
  requiredArgName: string,
  argLength: number,
  options: unknown,
): asserts options is Record<string, unknown> | undefined {
  if (argLength < 1) {
    throw pythonMissingRequiredArg(callable, requiredArgName);
  }
  if (argLength > 2 || (argLength === 2 && options !== undefined && !isPlainObject(options))) {
    throw pythonPositionalTypeError(callable, 2, argLength + 1);
  }
}

function assertPythonOptionsKeys(callable: string, options: Record<string, unknown> | undefined, allowed: Set<string>): void {
  if (!options) {
    return;
  }
  for (const key of Object.keys(options)) {
    if (!allowed.has(key)) {
      throw new TypeError(`${callable}() got an unexpected keyword argument '${key}'`);
    }
  }
}

function assertMappingPayload(payload: unknown): asserts payload is Record<string, unknown> {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw attributeError(`'${pythonTypeName(payload)}' object has no attribute 'items'`);
  }
}

function assertValueNormalizerArity(
  callable: string,
  argLength: number,
  expected: number,
  valueArgName = "value",
): void {
  if (argLength < 1) {
    throw pythonMissingRequiredArg(callable, valueArgName);
  }
  if (argLength > 1) {
    throw pythonPositionalTypeError(callable, expected, argLength + (expected - 1));
  }
}

function lockPythonFrozenFields(target: object, fields: string[]): void {
  for (const field of fields) {
    const value = (target as Record<string, unknown>)[field];
    Object.defineProperty(target, field, {
      configurable: false,
      enumerable: true,
      get() {
        return value;
      },
      set() {
        const error = new TypeError(`cannot assign to field '${field}'`);
        error.name = "FrozenInstanceError";
        throw error;
      },
    });
  }
  Object.preventExtensions(target);
}

function validateConfidenceThreshold(value: number): number {
  const threshold = Number(value);
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) {
    throw valueError("confidence_threshold must be between 0.0 and 1.0");
  }
  return threshold;
}

function emitRolodexterWarning(message: string): void {
  if (typeof process === "undefined" || typeof process.emit !== "function") {
    return;
  }
  const warning = new Error(message);
  warning.name = "RolodexterWarning";
  process.emit("rolodexterWarning" as "warning", warning);
}

function emitRolodexterWarnings(warnings: readonly string[]): void {
  for (const warning of warnings) {
    emitRolodexterWarning(warning);
  }
}

function valueError(message: string): Error {
  const error = new Error(message);
  error.name = "ValueError";
  return error;
}

function attributeError(message: string): Error {
  const error = new Error(message);
  error.name = "AttributeError";
  return error;
}

function pythonIncludes(values: unknown[], item: unknown): boolean {
  return values.some((value) => pythonEquals(value, item));
}

function pythonEquals(left: unknown, right: unknown): boolean {
  if (left === right) {
    return true;
  }
  if (left === null || left === undefined || right === null || right === undefined) {
    return left == null && right == null;
  }
  if (
    (typeof left === "boolean" && typeof right === "number") ||
    (typeof left === "number" && typeof right === "boolean")
  ) {
    return Number(left) === Number(right);
  }
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((item, index) => pythonEquals(item, right[index]));
  }
  if (typeof left === "object" && typeof right === "object") {
    const leftEntries = Object.entries(left as Record<string, unknown>);
    const rightRecord = right as Record<string, unknown>;
    return leftEntries.length === Object.keys(rightRecord).length &&
      leftEntries.every(([key, value]) => Object.prototype.hasOwnProperty.call(rightRecord, key) && pythonEquals(value, rightRecord[key]));
  }
  return false;
}


// A key literally named "__proto__" hits the prototype setter on a plain
// object: `target[key] = value` drops the value and replaces the object's
// prototype with caller-supplied data, so later lookups on it can return
// injected values. Python's dict has no such key, so every place that copies a
// user-supplied header, column or canonical name into a plain object is a
// place where one language silently loses a column and the other keeps it.
// Defining it as an own property preserves the data, matches Python, and
// leaves the prototype alone - while keeping a normal object literal so
// deepStrictEqual and spread still behave.
function setOwnProperty(target: Record<string, unknown>, key: string, value: unknown): void {
  if (key === "__proto__") {
    Object.defineProperty(target, key, {
      value,
      writable: true,
      enumerable: true,
      configurable: true,
    });
    return;
  }
  target[key] = value;
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { assertMappingPayload, assertPythonMethodOptions, assertPythonOptionsKeys, assertValueNormalizerArity, attributeError, emitRolodexterWarning, emitRolodexterWarnings, isPlainObject, lockPythonFrozenFields, pyRepr, pyString, pythonEquals, pythonIncludes, pythonLiteral, pythonMissingRequiredArg, pythonMissingRequiredArgs, pythonPositionalTypeError, pythonRangePositionalTypeError, pythonTypeName, setOwnProperty, validateConfidenceThreshold, valueError };
