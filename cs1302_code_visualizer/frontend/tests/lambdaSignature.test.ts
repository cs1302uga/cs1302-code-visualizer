import { describe, expect, it, vi } from "vitest";
import { formatLambdaSignature } from "../js/lambdaSignature";

const stripPackages = (type: string) => type.split("java.lang.").join("").split("java.util.").join("");

describe("generated lambda signature formatting", () => {
  it("formats return and parameter types through the supplied type formatter", () => {
    const format = vi.fn(stripPackages);
    const code = "java.lang.Integer apply(java.lang.Integer x) {\n    return x * 2;\n}";
    expect(formatLambdaSignature(code, format)).toBe("Integer apply(Integer x) {\n    return x * 2;\n}");
    expect(format.mock.calls).toEqual([["java.lang.Integer"], ["java.lang.Integer"]]);
  });

  it("handles nested generic commas, wildcard bounds, member types and arrays", () => {
    const result = formatLambdaSignature(
      "java.util.Map<java.lang.String, java.util.List<? extends java.lang.Number[]>>[] apply(" +
      "java.util.Map<java.lang.String, ? super java.lang.Integer[]>[] values, " +
      "example.Outer<java.lang.String>.Inner<java.lang.Integer>[][] other) { return null; }",
      stripPackages,
    );
    expect(result).toBe(
      "Map<String, List<? extends Number[]>>[] apply(" +
      "Map<String, ? super Integer[]>[] values, " +
      "example.Outer<String>.Inner<Integer>[][] other) { return null; }",
    );
  });

  it.each([
    ["java.lang.String get() { return null; }", "String get() { return null; }"],
    ["void accept(int x, boolean b) { }", "void accept(int x, boolean b) { }"],
    ["int[] apply(int[] values) { return values; }", "int[] apply(int[] values) { return values; }"],
    ["java.util.List<?> get() { return null; }", "List<?> get() { return null; }"],
  ])("preserves complete zero-parameter and primitive signatures: %s", (code, expected) => {
    expect(formatLambdaSignature(code, stripPackages)).toBe(expected);
  });

  it("preserves signature whitespace and Unicode names", () => {
    const code = "\n java.util.List< java.lang.String [ ] > [ ]\n μετατροπή(\n\tjava.lang.String[][] 名称\n)\n{ return null; }";
    expect(formatLambdaSignature(code, stripPackages)).toBe(
      "\n List< String [ ] > [ ]\n μετατροπή(\n\tString[][] 名称\n)\n{ return null; }",
    );
  });

  it("changes only type spans even when a prefix also occurs in names and the body", () => {
    const body = '{\n    // java.lang.Model must remain qualified\n' +
      '    /* Model and java.lang.String */\n' +
      '    String text = "java.lang.Model <script>alert(1)</script>";\n' +
      '    java.lang.Model value = java.lang.Model.create();\n' +
      '    return nested -> { return java.lang.Model.create(); };\n}';
    const code = `java.lang.Model convertModel(java.lang.Model Model) ${body}`;
    expect(formatLambdaSignature(code, type => stripPackages(type).split("Model").join("Item"))).toBe(
      `Item convertModel(Item Model) ${body}`,
    );
  });

  it("formats the generated signature when a lambda block has a preceding comment", () => {
    const body = ' /* java.lang. before block */\n{\n    return java.lang.String.valueOf(x);\n}';
    const code = `java.lang.String apply(java.lang.Integer x)${body}`;
    expect(formatLambdaSignature(code, stripPackages)).toBe(`String apply(Integer x)${body}`);
  });

  it.each(["/* java.lang. { } */\n", "// java.lang. { }\r\n", "// java.lang. { }\r"])(
    "skips braces inside comment trivia without changing it: %s", comment => {
      const code = `${comment}java.lang.String get() ${comment}{ return "java.lang."; }`;
      expect(formatLambdaSignature(code, stripPackages)).toBe(
        `${comment}String get() ${comment}{ return "java.lang."; }`,
      );
    },
  );

  it("preserves comments beside method and parameter names", () => {
    const code = "java.lang.String /* java.lang. */ apply(java.lang.Integer /* java.lang. */ x) { return null; }";
    expect(formatLambdaSignature(code, stripPackages)).toBe(
      "String /* java.lang. */ apply(Integer /* java.lang. */ x) { return null; }",
    );
  });

  it.each([
    "",
    "x -> x + 1",
    "java.lang.String get()",
    "java.lang.String get( { return null; }",
    "java.lang.String get(java.lang.String) { return null; }",
    "java.lang.String get(java.lang.String x,) { return null; }",
    "java.lang.String get(java.util.List<java.lang.String x) { return null; }",
    "java.lang.String get(java.lang.String x[) { return null; }",
    "java.lang.String get() throws Exception { return null; }",
    '@Example("java.lang.String") java.lang.String get() { return null; }',
    "public java.lang.String get() { return null; }",
    "/* java.lang.String java.lang.String get() { return null; }",
    "java.lang.String get() /* java.lang.String { return null; }",
    "java.util.List</* java.lang. */ java.lang.String> get() { return null; }",
    "java.lang./* java.lang. */String get() { return null; }",
  ])("leaves unsupported or incomplete signatures unchanged: %s", code => {
    const format = vi.fn(stripPackages);
    expect(formatLambdaSignature(code, format)).toBe(code);
    expect(format).not.toHaveBeenCalled();
  });

  it("leaves excessively nested untrusted signatures unchanged", () => {
    const code = `${"java.util.List<".repeat(1000)}java.lang.String${">".repeat(1000)} get() { return null; }`;
    expect(formatLambdaSignature(code, stripPackages)).toBe(code);
  });
});
