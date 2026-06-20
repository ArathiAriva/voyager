const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  content: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Trip {
  id: string;
  destination: string;
  dates: string;
  status: "past" | "upcoming";
  emoji: string;
  summary: string;
  cover_photo_url?: string | null;
  tags: string[];
}

export interface TripCreate {
  destination: string;
  dates: string;
  status: "past" | "upcoming";
  emoji: string;
  summary?: string;
  tags?: string[];
}

export interface JournalEntry {
  id: string;
  trip_id: string;
  date: string;
  body: string;
  source: "app" | "telegram" | "email";
}

export interface JournalEntryCreate {
  date: string;
  body: string;
  source?: "app" | "telegram" | "email";
}

export interface ConnectedContent {
  id: string;
  trip_id: string;
  url: string;
  type: "album" | "instagram" | "tiktok" | "blog" | "other";
  title?: string | null;
  thumbnail_url?: string | null;
  captured_at?: string | null;
}

export async function fetchConversations(): Promise<ConversationSummary[]> {
  const res = await fetch(`${BASE_URL}/api/conversations`);
  if (!res.ok) throw new Error(`Conversations API error: ${res.status}`);
  return res.json() as Promise<ConversationSummary[]>;
}

export async function createConversation(): Promise<ConversationSummary> {
  const res = await fetch(`${BASE_URL}/api/conversations`, { method: "POST" });
  if (!res.ok) throw new Error(`Create conversation error: ${res.status}`);
  return res.json() as Promise<ConversationSummary>;
}

export async function fetchConversation(id: string): Promise<Conversation> {
  const res = await fetch(`${BASE_URL}/api/conversations/${id}`);
  if (!res.ok) throw new Error(`Conversation API error: ${res.status}`);
  return res.json() as Promise<Conversation>;
}

export async function sendMessage(conversationId: string, content: string): Promise<Message> {
  const res = await fetch(`${BASE_URL}/api/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error(`Send message error: ${res.status}`);
  return res.json() as Promise<Message>;
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/conversations/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete conversation error: ${res.status}`);
}

export async function fetchTrips(): Promise<Trip[]> {
  const res = await fetch(`${BASE_URL}/api/trips`);
  if (!res.ok) throw new Error(`Trips API error: ${res.status}`);
  return res.json() as Promise<Trip[]>;
}

export async function fetchTrip(id: string): Promise<Trip> {
  const res = await fetch(`${BASE_URL}/api/trips/${id}`);
  if (!res.ok) throw new Error(`Trip API error: ${res.status}`);
  return res.json() as Promise<Trip>;
}

export async function createTrip(body: TripCreate): Promise<Trip> {
  const res = await fetch(`${BASE_URL}/api/trips`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Create trip error: ${res.status}`);
  return res.json() as Promise<Trip>;
}

export async function deleteTrip(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/trips/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete trip error: ${res.status}`);
}

// ── Journal ──────────────────────────────────────────────────────────────────

export async function fetchJournalEntries(tripId: string): Promise<JournalEntry[]> {
  const res = await fetch(`${BASE_URL}/api/trips/${tripId}/journal`);
  if (!res.ok) throw new Error(`Journal API error: ${res.status}`);
  return res.json() as Promise<JournalEntry[]>;
}

export async function createJournalEntry(tripId: string, body: JournalEntryCreate): Promise<JournalEntry> {
  const res = await fetch(`${BASE_URL}/api/trips/${tripId}/journal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Create journal entry error: ${res.status}`);
  return res.json() as Promise<JournalEntry>;
}

export async function deleteJournalEntry(tripId: string, entryId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/trips/${tripId}/journal/${entryId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete journal entry error: ${res.status}`);
}

// ── Connected content ─────────────────────────────────────────────────────────

export async function fetchContent(tripId: string): Promise<ConnectedContent[]> {
  const res = await fetch(`${BASE_URL}/api/trips/${tripId}/content`);
  if (!res.ok) throw new Error(`Content API error: ${res.status}`);
  return res.json() as Promise<ConnectedContent[]>;
}

export async function addContent(tripId: string, url: string, type: ConnectedContent["type"]): Promise<ConnectedContent> {
  const res = await fetch(`${BASE_URL}/api/trips/${tripId}/content`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, type }),
  });
  if (!res.ok) throw new Error(`Add content error: ${res.status}`);
  return res.json() as Promise<ConnectedContent>;
}

export async function deleteContent(tripId: string, contentId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/trips/${tripId}/content/${contentId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete content error: ${res.status}`);
}

// ── Memories ──────────────────────────────────────────────────────────────────

export interface Memories {
  episodes: string[];
  preferences: string[];
}

export async function fetchMemories(): Promise<Memories> {
  const res = await fetch(`${BASE_URL}/api/memories`);
  if (!res.ok) throw new Error(`Memories API error: ${res.status}`);
  return res.json() as Promise<Memories>;
}
