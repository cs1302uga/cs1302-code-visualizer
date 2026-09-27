/** Sanitize legacy HTML fragments before they reach the live renderer DOM. */
import DOMPurify from "dompurify";

export function safeMarkup(value: any): any {
  // Template contents are inert and preserve table fragments such as <tr>/<td>.
  // Return nodes, not reserialized HTML, to avoid changing parsing contexts.
  const template = document.createElement("template");
  template.innerHTML = String(value);
  return DOMPurify.sanitize(template.content, {
    RETURN_DOM_FRAGMENT: true,
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["style", "img"],
  });
}

/** HTML setters (including D3) require a string rather than a DOM fragment. */
export function safeHtml(value: any): any {
  if (typeof value === "function") {
    return function (this: unknown, ...args: unknown[]) {
      return safeHtml(value.apply(this, args));
    };
  }
  return DOMPurify.sanitize(String(value), {
    USE_PROFILES: { html: true }, FORBID_TAGS: ["style", "img"],
  });
}
