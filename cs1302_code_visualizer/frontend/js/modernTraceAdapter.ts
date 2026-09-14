/**
 * @fileoverview Modern Trace Format Adapter.
 * Converts code-tracer modern JSON format into the OPT execution visualizer trace format.
 */

/**
 * Represents a local variable in modern trace format.
 */
export interface ModernLocal {
  name: string;
  type?: string;
  value: unknown;
  final?: boolean;
}

/**
 * Represents a call stack frame in modern trace format.
 */
export interface ModernFrame {
  methodName: string;
  line: number;
  isHighlighted?: boolean;
  locals?: ModernLocal[];
}

/**
 * Represents an instance field in modern trace format.
 */
export interface ModernField {
  name: string;
  type?: string;
  value: unknown;
  final?: boolean;
}

/**
 * Represents a heap object in modern trace format.
 */
export interface ModernHeapObject {
  id: number | string;
  type?: string;
  kind?: "object" | "array" | "string" | "primitive" | "color" | string;
  fields?: ModernField[];
  elements?: unknown[];
  value?: unknown;
}

/**
 * Represents a static class group in modern trace format.
 */
export interface ModernStaticGroup {
  className: string;
  fields?: ModernField[];
}

/**
 * Represents a single execution step in modern trace format.
 */
export interface ModernStep {
  step?: number;
  line: number;
  event?: string;
  method?: string;
  callStack?: ModernFrame[];
  statics?: ModernStaticGroup[];
  heap?: Record<string, ModernHeapObject>;
  stdout?: string;
  stderr?: string;
}

/**
 * Root trace payload in modern trace format.
 */
export interface ModernTrace {
  code: string;
  format?: string;
  steps?: ModernStep[];
  breakpoints?: Record<string, ModernStep | ModernStep[]>;
  stdin?: string;
}

/**
 * Type guard checking if input trace payload follows the modern format.
 * @param trace Input trace object.
 * @return True if trace matches modern format.
 */
export function isModernTrace(trace: unknown): trace is ModernTrace {
  if (!trace || typeof trace !== "object") {
    return false;
  }
  const t = trace as Record<string, unknown>;
  if (t["format"] === "modern") {
    return true;
  }
  if (Array.isArray(t["steps"]) && !Array.isArray(t["trace"])) {
    return true;
  }
  if (
    t["breakpoints"] &&
    typeof t["breakpoints"] === "object" &&
    !Array.isArray(t["trace"])
  ) {
    return true;
  }
  return false;
}

/**
 * Encodes a modern value into an OPT value representation.
 * @param val The value to encode.
 * @return The OPT-encoded value.
 */
export function encodeValue(val: unknown): unknown {
  if (val === null || val === undefined) {
    return null;
  }
  if (typeof val === "object") {
    const v = val as Record<string, unknown>;
    if ("ref" in v) {
      if (v["ref"] === null || v["ref"] === undefined) {
        return null;
      }
      return ["REF", v["ref"]];
    }
  }
  return val;
}

/**
 * Converts a modern trace payload into an OPT trace payload.
 * @param modernTrace Modern trace payload.
 * @return OPT compatible trace object.
 */
export function convertModernTraceToOpt(modernTrace: ModernTrace): Record<string, unknown> {
  const code = modernTrace.code || "";
  let modernSteps: ModernStep[] = [];

  if (Array.isArray(modernTrace.steps)) {
    modernSteps = modernTrace.steps;
  } else if (
    modernTrace.breakpoints &&
    typeof modernTrace.breakpoints === "object"
  ) {
    Object.values(modernTrace.breakpoints).forEach((bpVal) => {
      if (Array.isArray(bpVal)) {
        modernSteps.push(...bpVal);
      } else if (bpVal && typeof bpVal === "object") {
        modernSteps.push(bpVal as ModernStep);
      }
    });
  }

  const optTrace = modernSteps.map((step) => {
    const optStep: Record<string, any> = {
      event: step.event || "step_line",
      line: step.line,
      func_name: step.method || "main",
      stdout: step.stdout ?? "",
      stderr: step.stderr ?? "",
      file: null,
      stack_to_render: [],
      globals: {},
      globals_attrs: {},
      ordered_globals: [],
      heap: {},
      heap_attrs: {},
    };

    // 1. Convert call stack
    if (Array.isArray(step.callStack)) {
      step.callStack.forEach((frame, frameIdx) => {
        const encodedLocals: Record<string, unknown> = {};
        const localsAttrs: Record<string, unknown> = {};
        const orderedVarnames: string[] = [];

        if (Array.isArray(frame.locals)) {
          frame.locals.forEach((loc) => {
            orderedVarnames.push(loc.name);
            encodedLocals[loc.name] = encodeValue(loc.value);
            localsAttrs[loc.name] = {
              type: loc.type,
              final: loc.final ?? false,
            };
          });
        }

        optStep["stack_to_render"].push({
          func_name: `${frame.methodName}:${frame.line}`,
          line: frame.line,
          is_highlighted:
            frame.isHighlighted ?? (frameIdx === step.callStack!.length - 1),
          is_zombie: false,
          is_parent: false,
          frame_id: frameIdx,
          unique_hash: `${frame.methodName}:${frame.line}:${frameIdx}`,
          parent_frame_id_list: [],
          encoded_locals: encodedLocals,
          locals_attrs: localsAttrs,
          ordered_varnames: orderedVarnames,
          file: null,
        });
      });
    }

    // 2. Convert statics to globals
    if (Array.isArray(step.statics)) {
      step.statics.forEach((staticGroup) => {
        const rawName = staticGroup.className || "";
        const className = rawName.split(".").pop() || rawName;
        if (Array.isArray(staticGroup.fields)) {
          staticGroup.fields.forEach((f) => {
            const globalKey = className ? `${className}.${f.name}` : f.name;
            optStep["ordered_globals"].push(globalKey);
            optStep["globals"][globalKey] = encodeValue(f.value);
            optStep["globals_attrs"][globalKey] = {
              type: f.type,
              final: f.final ?? false,
            };
          });
        }
      });
    }

    // 3. Convert heap
    if (step.heap && typeof step.heap === "object") {
      Object.entries(step.heap).forEach(([idStr, heapObj]) => {
        if (!heapObj || typeof heapObj !== "object") {
          optStep["heap"][idStr] = heapObj;
          return;
        }

        const kind = heapObj.kind;
        const objType = heapObj.type || "Object";

        if (kind === "array" && Array.isArray(heapObj.elements)) {
          optStep["heap"][idStr] = ["LIST", ...heapObj.elements.map(encodeValue)];
          optStep["heap_attrs"][idStr] = { type: objType };
        } else if (kind === "string") {
          optStep["heap"][idStr] = [
            "INSTANCE",
            "String",
            ["___NO_LABEL!___", heapObj.value ?? ""],
          ];
          optStep["heap_attrs"][idStr] = { type: "java.lang.String" };
        } else if (kind === "object" && Array.isArray(heapObj.fields)) {
          const fieldEntries = heapObj.fields.map((f) => [
            f.name,
            encodeValue(f.value),
          ]);
          optStep["heap"][idStr] = ["INSTANCE", objType, ...fieldEntries];
          optStep["heap_attrs"][idStr] = { type: objType };
        } else if (kind === "primitive") {
          optStep["heap"][idStr] = [
            "INSTANCE",
            objType,
            ["value", encodeValue(heapObj.value)],
          ];
          optStep["heap_attrs"][idStr] = { type: objType };
        } else if (kind === "color") {
          optStep["heap"][idStr] = [
            "COLOR",
            objType,
            typeof heapObj.value === "string" ? heapObj.value : "",
          ];
          optStep["heap_attrs"][idStr] = { type: objType };
        } else if (Array.isArray(heapObj as unknown)) {
          optStep["heap"][idStr] = heapObj;
        } else {
          const fields = heapObj.fields
            ? heapObj.fields.map((f) => [f.name, encodeValue(f.value)])
            : [];
          optStep["heap"][idStr] = ["INSTANCE", objType, ...fields];
          optStep["heap_attrs"][idStr] = { type: objType };
        }
      });
    }

    return optStep;
  });

  return {
    code: code,
    trace: optTrace,
    userlog: "",
    stdin: modernTrace.stdin ?? "",
  };
}
