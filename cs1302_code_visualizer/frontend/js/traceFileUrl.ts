/** Convert an operator-selected absolute path to a local file URL, never a host. */
export function traceFileUrl(value: string | null): string {
  if (!value || value.includes("\0")) throw new Error("tracePath must be an absolute local file path");
  const path = /^[a-z]:[\\/]/i.test(value) ? "/" + value.replace(/\\/g, "/") : value;
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new Error("tracePath must be an absolute local file path");
  }
  const url = new URL("file:///");
  // Encode filenames, including URL delimiters and backslashes in POSIX paths.
  url.pathname = path.split("/").map((part, index) =>
    index === 1 && /^[a-z]:$/i.test(part) ? part : encodeURIComponent(part)).join("/");
  return url.href;
}
