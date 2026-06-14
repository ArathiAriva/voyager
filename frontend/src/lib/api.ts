const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Role = "user" | "assistant";

export interface Message {
  role: Role;
  content: string;
}

export interface Trip {
  id: string;
  destination: string;
  dates: string;
  status: "past" | "upcoming";
  emoji: string;
  summary: string;
}

export async function sendChat(messages: Message[]): Promise<Message> {
  const res = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error(`Chat API error: ${res.status}`);
  const data = await res.json();
  return data.message as Message;
}

export async function fetchTrips(): Promise<Trip[]> {
  const res = await fetch(`${BASE_URL}/api/trips`);
  if (!res.ok) throw new Error(`Trips API error: ${res.status}`);
  return res.json() as Promise<Trip[]>;
}
