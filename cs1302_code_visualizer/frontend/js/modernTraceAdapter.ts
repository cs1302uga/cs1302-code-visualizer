/**
 * Modern Trace Format Adapter
 *
 * Converts code-tracer modern JSON format (format: "modern", "steps": [...], or "breakpoints": {...})
 * into the OPT execution visualizer trace format expected by pytutor.ts.
 */

export interface ModernLocal {
  name: string;
  type?: string;
  value: any;
  final?: boolean;
}

export interface ModernFrame {
  methodName: string;
  line: number;
  isHighlighted?: boolean;
  locals?: ModernLocal[];
}

export interface ModernField {
  name: string;
  type?: string;
  value: any;
  final?: boolean;
}

export interface ModernHeapObject {
  id: number | string;
  type?: string;
  kind?: "object" | "array" | "string" | "primitive" | string;
  fields?: ModernField[];
  elements?: any[];
  value?: any;
}

export interface ModernStaticGroup {
  className: string;
  fields?: ModernField[];
}

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

export interface ModernTrace {
  code: string;
  format?: string;
  steps?: ModernStep[];
  breakpoints?: Record<string, ModernStep | ModernStep[]>;
  stdin?: string;
}

/**
 * Checks if a given trace object is in the modern trace format.
 */
export function isModernTrace(trace: any): boolean {
  if (!trace || typeof trace !== "object") {
    return false;
  }
  if (trace.format === "modern") {
    return true;
  }
  if (Array.isArray(trace.steps) && !Array.isArray(trace.trace)) {
    return true;
  }
  if (
    trace.breakpoints &&
    typeof trace.breakpoints === "object" &&
    !Array.isArray(trace.trace)
  ) {
    return true;
  }
  return false;
}

/**
 * Encodes a modern value into an OPT value representation.
 */
export function encodeValue(val: any): any {
  if (val === null || val === undefined) {
    return null;
  }
  if (typeof val === "object") {
    if ("ref" in val) {
      if (val.ref === null || val.ref === undefined) {
        return null;
      }
      return ["REF", val.ref];
    }
  }
  return val;
}

/**
 * Converts a modern trace payload into an OPT trace payload.
 */
export function convertModernTraceToOpt(modernTrace: ModernTrace): any {
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
        modernSteps.push(bpVal);
      }
    });
  }

  const optTrace = modernSteps.map((step) => {
    const optStep: any = {
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
        const encoded_locals: Record<string, any> = {};
        const locals_attrs: Record<string, any> = {};
        const ordered_varnames: string[] = [];

        if (Array.isArray(frame.locals)) {
          frame.locals.forEach((loc) => {
            ordered_varnames.push(loc.name);
            encoded_locals[loc.name] = encodeValue(loc.value);
            locals_attrs[loc.name] = {
              type: loc.type,
              final: loc.final ?? false,
            };
          });
        }

        optStep.stack_to_render.push({
          func_name: `${frame.methodName}:${frame.line}`,
          line: frame.line,
          is_highlighted:
            frame.isHighlighted ?? (frameIdx === step.callStack.length - 1),
          is_zombie: false,
          is_parent: false,
          frame_id: frameIdx,
          unique_hash: `${frame.methodName}:${frame.line}:${frameIdx}`,
          parent_frame_id_list: [],
          encoded_locals: encoded_locals,
          locals_attrs: locals_attrs,
          ordered_varnames: ordered_varnames,
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
            optStep.ordered_globals.push(globalKey);
            optStep.globals[globalKey] = encodeValue(f.value);
            optStep.globals_attrs[globalKey] = {
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
          optStep.heap[idStr] = heapObj;
          return;
        }

        const kind = heapObj.kind;
        const objType = heapObj.type || "Object";

        if (kind === "array" && Array.isArray(heapObj.elements)) {
          optStep.heap[idStr] = ["LIST", ...heapObj.elements.map(encodeValue)];
          optStep.heap_attrs[idStr] = { type: objType };
        } else if (kind === "string") {
          optStep.heap[idStr] = [
            "INSTANCE",
            "String",
            ["___NO_LABEL!___", heapObj.value ?? ""],
          ];
          optStep.heap_attrs[idStr] = { type: "java.lang.String" };
        } else if (kind === "object" && Array.isArray(heapObj.fields)) {
          const fieldEntries = heapObj.fields.map((f) => [
            f.name,
            encodeValue(f.value),
          ]);
          optStep.heap[idStr] = ["INSTANCE", objType, ...fieldEntries];
          optStep.heap_attrs[idStr] = { type: objType };
        } else if (kind === "primitive") {
          optStep.heap[idStr] = [
            "INSTANCE",
            objType,
            ["value", encodeValue(heapObj.value)],
          ];
          optStep.heap_attrs[idStr] = { type: objType };
        } else if (Array.isArray(heapObj as any)) {
          optStep.heap[idStr] = heapObj;
        } else {
          const fields = heapObj.fields
            ? heapObj.fields.map((f) => [f.name, encodeValue(f.value)])
            : [];
          optStep.heap[idStr] = ["INSTANCE", objType, ...fields];
          optStep.heap_attrs[idStr] = { type: objType };
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
