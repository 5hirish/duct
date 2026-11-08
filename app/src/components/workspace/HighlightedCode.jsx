"use client";

import SyntaxHighlighter from "react-syntax-highlighter/dist/esm/prism-light";
import js from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import markup from "react-syntax-highlighter/dist/esm/languages/prism/markup";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import css from "react-syntax-highlighter/dist/esm/languages/prism/css";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript";

SyntaxHighlighter.registerLanguage("javascript", js);
SyntaxHighlighter.registerLanguage("js", js);
SyntaxHighlighter.registerLanguage("jsx", js);
SyntaxHighlighter.registerLanguage("html", markup);
SyntaxHighlighter.registerLanguage("xml", markup);
SyntaxHighlighter.registerLanguage("json", json);
SyntaxHighlighter.registerLanguage("css", css);
SyntaxHighlighter.registerLanguage("bash", bash);
SyntaxHighlighter.registerLanguage("sh", bash);
SyntaxHighlighter.registerLanguage("shell", bash);
SyntaxHighlighter.registerLanguage("python", python);
SyntaxHighlighter.registerLanguage("py", python);
SyntaxHighlighter.registerLanguage("typescript", typescript);
SyntaxHighlighter.registerLanguage("ts", typescript);

/**
 * The highlighter itself, in its own module so `CodeBlock` can load it on the
 * first code block instead of with every agent workspace. Imported by file
 * path, never from the package root or `styles/prism`: that index re-exports
 * all ~45 Prism themes, and importing one theme from it shipped every one
 * (~66 KB compressed on every chat route).
 */
export default function HighlightedCode({ language, code, style, customStyle }) {
  return (
    <SyntaxHighlighter language={language || "text"} style={style} customStyle={customStyle} wrapLongLines>
      {code}
    </SyntaxHighlighter>
  );
}
