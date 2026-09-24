/** Presentation settings apply to Java arrays, independently of their references. */
export type ArrayOrientation = "horizontal" | "vertical";

export interface ArrayOrientationOptions {
  /** Base orientation; also the 1D orientation when alternation is enabled. */
  arrayOrientation?: ArrayOrientation;
  /** Flip the base for even-dimensional arrays. Defaults to false. */
  alternateArrayOrientations?: boolean;
  /** Heap object ID overrides, scoped to this visualizer and trace. */
  arrayOrientations?: Record<string, ArrayOrientation>;
}

function isOrientation(value: unknown): value is ArrayOrientation {
  return value === "horizontal" || value === "vertical";
}

/** Resolve from object metadata, never from graph depth or another object's override. */
export function resolveArrayOrientation(
  options: ArrayOrientationOptions,
  objectId: string | number,
  type: unknown,
): ArrayOrientation {
  const overrides = options.arrayOrientations;
  const override = overrides && Object.prototype.hasOwnProperty.call(overrides, objectId)
    ? overrides[objectId] : undefined;
  if (isOrientation(override)) return override;

  const base = isOrientation(options.arrayOrientation) ? options.arrayOrientation : "horizontal";
  const suffix = typeof type === "string" ? type.match(/(?:\[\])+$/)?.[0] : undefined;
  const dimensions = suffix ? suffix.length / 2 : 0;
  if (options.alternateArrayOrientations === true && dimensions > 0 && dimensions % 2 === 0) {
    return base === "horizontal" ? "vertical" : "horizontal";
  }
  return base;
}

/** Parse optional browser URL settings; invalid values fall back to defaults. */
export function arrayOrientationOptionsFromParams(params: URLSearchParams): ArrayOrientationOptions {
  const base = params.get("arrayOrientation");
  const result: ArrayOrientationOptions = {
    arrayOrientation: isOrientation(base) ? base : "horizontal",
    alternateArrayOrientations: params.get("alternateArrayOrientations")?.toLowerCase() === "true",
  };
  try {
    const overrides = JSON.parse(params.get("arrayOrientations") || "{}");
    if (overrides && typeof overrides === "object" && !Array.isArray(overrides)) {
      result.arrayOrientations = Object.fromEntries(
        Object.entries(overrides).filter(([, value]) => isOrientation(value)),
      ) as Record<string, ArrayOrientation>;
    }
  } catch {
    // Malformed optional JSON must not prevent a trace from rendering.
  }
  return result;
}
