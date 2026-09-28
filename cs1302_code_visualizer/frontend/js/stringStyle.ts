/** String presentation is derived from an identity-preserving trace. */
export type StringStyle = "compact" | "default" | "inline";

export function validateStringStyle(style: unknown = "default"): StringStyle {
  if (style !== "compact" && style !== "default" && style !== "inline") {
    throw new Error("stringStyle must be 'compact', 'default', or 'inline'");
  }
  return style;
}

export function stringValue(object: any): string | undefined {
  if (object?.[0] === "INSTANCE" && /^(java\.lang\.)?String$/.test(object[1]) &&
      object[2]?.[0] === "___NO_LABEL!___" && typeof object[2][1] === "string") {
    return object[2][1];
  }
  if (object?.[0] === "HEAP_PRIMITIVE" && /^(java\.lang\.)?String$/.test(object[1]) &&
      typeof object[2] === "string") return object[2];
  return undefined;
}

/** Clone first: style changes and renderer postprocessing never alter caller data. */
export function prepareStringTrace(trace: any, style: StringStyle): any {
  const result = JSON.parse(JSON.stringify(trace), (_key, value) =>
    value && typeof value === "object" && !Array.isArray(value)
      ? Object.assign(Object.create(null), value) : value);
  for (const step of result.trace ?? []) {
    const strings = new Map<string, string>();
    for (const [id, object] of Object.entries(step.heap ?? {})) {
      const value = stringValue(object);
      if (value !== undefined) strings.set(id, value);
    }
    const value = (v: any): any => {
      if (typeof v === "string" && style !== "inline") {
        throw new Error("This trace contains inlined strings without reference identities. " +
          "Regenerate it with inline_strings=False, or render with string_style='inline'.");
      }
      if (Array.isArray(v) && v[0] === "REF" && strings.has(String(v[1])) && style !== "default") {
        return style === "inline" ? strings.get(String(v[1])) : ["STRING_REF", v[1], strings.get(String(v[1]))];
      }
      return v;
    };
    for (const frame of step.stack_to_render ?? []) {
      for (const name of Object.keys(frame.encoded_locals ?? {})) frame.encoded_locals[name] = value(frame.encoded_locals[name]);
    }
    for (const name of Object.keys(step.globals ?? {})) step.globals[name] = value(step.globals[name]);
    for (const [id, object] of Object.entries(step.heap ?? {}) as [string, any][]) {
      if (strings.has(id)) {
        if (style !== "default") delete step.heap[id];
        continue;
      }
      if (["LIST", "TUPLE", "SET", "STACK", "QUEUE"].includes(object[0])) {
        for (let i = 1; i < object.length; i++) object[i] = value(object[i]);
      } else if (["INSTANCE", "CLASS", "DICT"].includes(object[0])) {
        const start = object[0] === "DICT" ? 1 : object[0] === "CLASS" ? 3 : 2;
        for (let i = start; i < object.length; i++) {
          if (!Array.isArray(object[i])) continue;
          if (object[0] === "DICT") object[i][0] = value(object[i][0]);
          object[i][1] = value(object[i][1]);
        }
      }
    }
  }
  return result;
}
