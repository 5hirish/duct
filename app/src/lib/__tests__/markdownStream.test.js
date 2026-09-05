import { describe, expect, it } from "vitest";
import { healTail, splitSettled } from "../markdownStream";

describe("splitSettled", () => {
  it("settles everything before the last blank line and keeps the rest live", () => {
    const text = "# Title\n\nFirst paragraph.\n\nSecond para";
    expect(splitSettled(text)).toEqual({ settled: "# Title\n\nFirst paragraph.\n\n", tail: "Second para" });
  });

  it("never splits inside a code fence, and never leaves an empty tail", () => {
    const text = "Intro\n\n```js\nconst a = 1;\n\nconst b = 2;";
    expect(splitSettled(text)).toEqual({ settled: "Intro\n\n", tail: "```js\nconst a = 1;\n\nconst b = 2;" });
    expect(splitSettled("one\n\n")).toEqual({ settled: "", tail: "one\n\n" });
    expect(splitSettled("")).toEqual({ settled: "", tail: "" });
  });

  it("the two halves concatenate back to the source", () => {
    const text = "a\n\nb\n\n| x | y |\n|---|---|\n| 1 |";
    const { settled, tail } = splitSettled(text);
    expect(settled + tail).toBe(text);
  });
});

describe("healTail", () => {
  it("closes an open fence and touches nothing inside it", () => {
    expect(healTail("```py\nprint(**")).toBe("```py\nprint(**\n```");
  });

  it("closes unbalanced emphasis and inline code", () => {
    expect(healTail("This is **bold and *italic")).toBe("This is **bold and *italic*" + "**");
    expect(healTail("Run `npm test")).toBe("Run `npm test`");
    expect(healTail("Escaped \\* star")).toBe("Escaped \\* star");
  });

  it("shows a link's text while its target is still arriving", () => {
    expect(healTail("See [the docs](https://exa")).toBe("See the docs");
    expect(healTail("See [the do")).toBe("See the do");
  });

  it("drops a table's partial last row so the columns do not jump", () => {
    expect(healTail("| a | b |\n|---|---|\n| 1 | 2 |\n| 3 |")).toBe("| a | b |\n|---|---|\n| 1 | 2 |\n");
    expect(healTail("| a | b |\n|---|---|\n| 1 | 2 |")).toBe("| a | b |\n|---|---|\n| 1 | 2 |");
  });
});
