interface Token {
  text: string;
  start: number;
  end: number;
}

/**
 * Format type positions in a generated SAM implementation, preserving its body.
 * Unsupported signatures are displayed unchanged rather than guessed at.
 */
export function formatLambdaSignature(
  implementation: string,
  formatType: (type: string) => string,
): string {
  // The tracer generates resolved types and names, without declaration modifiers
  // or annotations. A block's leading comment can appear between ')' and '{'.
  // Lex comment trivia before finding the body, retaining every original offset.
  const tokenPattern = /\s+|\/\*[\s\S]*?\*\/|\/\/[^\r\n]*|[\p{L}\p{Nl}\p{Sc}\p{Pc}][\p{L}\p{Nl}\p{Sc}\p{Pc}\p{Nd}\p{Mc}\p{Mn}\p{Cf}]*|[<>,.?()[\]]|\{/uy;
  const tokens: Token[] = [];
  const comments: number[] = [];
  let cursor = 0;
  while (cursor < implementation.length) {
    tokenPattern.lastIndex = cursor;
    const match = tokenPattern.exec(implementation);
    if (!match) return implementation;
    const text = match[0];
    if (text === "{") break;
    if (text.startsWith("/")) {
      comments.push(cursor);
    } else if (text.trim()) {
      tokens.push({ text, start: cursor, end: tokenPattern.lastIndex });
    }
    cursor = tokenPattern.lastIndex;
  }
  if (implementation[cursor] !== "{") return implementation;

  let position = 0;
  const take = (text: string): boolean => {
    if (tokens[position]?.text !== text) return false;
    position++;
    return true;
  };
  const identifier = (): boolean => {
    const token = tokens[position];
    if (!token || /^[<>,.?()[\]]$/.test(token.text)) return false;
    position++;
    return true;
  };

  const typeArguments = (depth: number): boolean => {
    if (!take("<")) return true;
    do {
      if (take("?")) {
        if ((take("extends") || take("super")) && !type(depth + 1)) return false;
      } else if (!type(depth + 1)) {
        return false;
      }
    } while (take(","));
    return take(">");
  };
  const type = (depth = 0): boolean => {
    // Untrusted legacy traces can contain arbitrary text, including very deep
    // nesting. Leave those strings unchanged without exhausting the JS stack.
    if (depth > 64 || !identifier() || !typeArguments(depth)) return false;
    while (take(".")) {
      if (!identifier() || !typeArguments(depth)) return false;
    }
    while (take("[")) {
      if (!take("]")) return false;
    }
    return true;
  };

  const spans: { start: number; end: number }[] = [];
  let commentPosition = 0;
  const signatureType = (): boolean => {
    const start = tokens[position]?.start;
    if (start === undefined || !type()) return false;
    const end = tokens[position - 1].end;
    while (comments[commentPosition] < start) commentPosition++;
    // Resolved generated types contain no comments. Preserve unsupported legacy
    // type text unchanged rather than passing an embedded comment to formatType.
    if (comments[commentPosition] < end) return false;
    spans.push({ start, end });
    return true;
  };

  if (!signatureType() || !identifier() || !take("(")) return implementation;
  if (!take(")")) {
    do {
      if (!signatureType() || !identifier()) return implementation;
    } while (take(","));
    if (!take(")")) return implementation;
  }
  if (position !== tokens.length) return implementation;

  let result = "";
  let previousEnd = 0;
  for (const { start, end } of spans) {
    result += implementation.slice(previousEnd, start);
    result += formatType(implementation.slice(start, end));
    previousEnd = end;
  }
  return result + implementation.slice(previousEnd);
}
