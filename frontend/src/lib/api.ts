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
