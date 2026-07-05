import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  fetchConversations,
  createConversation,
  fetchConversation,
  deleteConversation,
  fetchTrips,
} from "../lib/api";

const mockConversationSummary = {
  id: "conv-1",
  title: "New conversation",
  created_at: "2026-06-17T00:00:00Z",
  updated_at: "2026-06-17T00:00:00Z",
};

const mockConversation = {
  ...mockConversationSummary,
  messages: [],
};

const mockMessage = {
  id: "msg-1",
  role: "assistant",
  content: "Hello!",
  created_at: "2026-06-17T00:00:00Z",
};

const mockTrip = {
  id: "trip-1",
  destination: "Tokyo, Japan",
  dates: "March 2026",
  status: "upcoming",
  emoji: "🗼",
  summary: "Cherry blossom trip",
};

function mockFetch(data: unknown, ok = true, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValueOnce({
    ok,
    status,
    json: async () => data,
  } as Response);
}

beforeEach(() => vi.restoreAllMocks());

// ── fetchConversations ────────────────────────────────────────────────────────

describe("fetchConversations", () => {
  it("returns list on success", async () => {
    mockFetch([mockConversationSummary]);
    const result = await fetchConversations();
    expect(result).toEqual([mockConversationSummary]);
  });

  it("throws on non-ok response", async () => {
    mockFetch(null, false, 500);
    await expect(fetchConversations()).rejects.toThrow("Conversations API error: 500");
  });
});

// ── createConversation ────────────────────────────────────────────────────────

describe("createConversation", () => {
  it("returns new conversation on success", async () => {
    mockFetch(mockConversationSummary);
    const result = await createConversation();
    expect(result.id).toBe("conv-1");
    expect(result.title).toBe("New conversation");
  });

  it("throws on non-ok response", async () => {
    mockFetch(null, false, 500);
    await expect(createConversation()).rejects.toThrow("Create conversation error: 500");
  });
});

// ── fetchConversation ─────────────────────────────────────────────────────────

describe("fetchConversation", () => {
  it("returns conversation with messages", async () => {
    mockFetch(mockConversation);
    const result = await fetchConversation("conv-1");
    expect(result.id).toBe("conv-1");
    expect(result.messages).toEqual([]);
  });

  it("throws on 404", async () => {
    mockFetch(null, false, 404);
    await expect(fetchConversation("missing")).rejects.toThrow("Conversation API error: 404");
  });
});

// ── deleteConversation ────────────────────────────────────────────────────────

describe("deleteConversation", () => {
  it("resolves without error on success", async () => {
    mockFetch(null, true, 204);
    await expect(deleteConversation("conv-1")).resolves.toBeUndefined();
  });

  it("throws on non-ok response", async () => {
    mockFetch(null, false, 404);
    await expect(deleteConversation("missing")).rejects.toThrow("Delete conversation error: 404");
  });
});

// ── fetchTrips ────────────────────────────────────────────────────────────────

describe("fetchTrips", () => {
  it("returns list of trips on success", async () => {
    mockFetch([mockTrip]);
    const result = await fetchTrips();
    expect(result).toHaveLength(1);
    expect(result[0].destination).toBe("Tokyo, Japan");
  });

  it("throws on non-ok response", async () => {
    mockFetch(null, false, 500);
    await expect(fetchTrips()).rejects.toThrow("Trips API error: 500");
  });
});
