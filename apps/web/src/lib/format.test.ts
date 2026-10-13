import { describe, expect, it } from "vitest";

import { duration, relativeTime, shortId } from "./format";

describe("format", () => {
  const now = Date.parse("2026-10-12T12:00:00Z");
  it("formats relative times", () => {
    expect(relativeTime("2026-10-12T11:59:30Z", now)).toBe("30s ago");
    expect(relativeTime("2026-10-12T12:05:00Z", now)).toBe("in 5m");
    expect(relativeTime("2026-10-10T12:00:00Z", now)).toBe("2d ago");
    expect(relativeTime(null, now)).toBe("—");
  });
  it("formats durations", () => {
    expect(duration("2026-10-12T12:00:00Z", "2026-10-12T12:00:02.4Z")).toBe("2.4s");
    expect(duration("2026-10-12T12:00:00Z", "2026-10-12T12:03:10Z")).toBe("3m 10s");
    expect(duration(null, null)).toBe("—");
  });
  it("shortens ids", () => {
    expect(shortId("0190a000-0000-7000-8000-00000000abcd")).toBe("0000abcd");
  });
});
