import { describe, expect, it } from "vitest";
import { traceFileUrl } from "../js/traceFileUrl";

describe("local trace file URLs", () => {
  it.each([null, "", "relative.json", "host.example/trace.json", "//host/share/trace.json",
    "\\\\host\\share\\trace.json", "https://host/trace.json", "file:///tmp/trace.json",
    "C:relative.json", "/tmp/bad\0.json"])("rejects non-local or non-absolute path %s", path => {
    expect(() => traceFileUrl(path)).toThrow("absolute local file path");
  });
  it.each([
    ["/tmp/a #?%é.json", "file:///tmp/a%20%23%3F%25%C3%A9.json"],
    ["/tmp/back\\slash.json", "file:///tmp/back%5Cslash.json"],
    ["C:\\Users\\person\\a #?.json", "file:///C:/Users/person/a%20%23%3F.json"],
    ["D:/temp/trace.json", "file:///D:/temp/trace.json"],
    ["/tmp/%2f%2fhost.json", "file:///tmp/%252f%252fhost.json"],
    ["/\\host/share.json", "file:///%5Chost/share.json"],
  ])("encodes %s without creating a host or query", (path, expected) => {
    const actual = traceFileUrl(path), url = new URL(actual);
    expect(actual).toBe(expected);
    expect(url.protocol).toBe("file:");
    expect(url.host).toBe("");
    expect(url.search).toBe("");
    expect(url.hash).toBe("");
  });
});
