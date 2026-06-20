"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Box, Flex, HStack, VStack, Text, Badge, Button, Textarea, Input,
  Spinner, Portal, Select, createListCollection,
} from "@chakra-ui/react";
import {
  fetchTrip, fetchJournalEntries, createJournalEntry, deleteJournalEntry,
  fetchContent, addContent, deleteContent,
  type Trip, type JournalEntry, type ConnectedContent,
} from "@/lib/api";

type Tab = "journal" | "content";

const CONTENT_TYPE_OPTIONS = createListCollection({
  items: [
    { label: "Photo album", value: "album" },
    { label: "Instagram", value: "instagram" },
    { label: "TikTok", value: "tiktok" },
    { label: "Blog", value: "blog" },
    { label: "Other", value: "other" },
  ],
});

export default function TripDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [trip, setTrip] = useState<Trip | null>(null);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [content, setContent] = useState<ConnectedContent[]>([]);
  const [tab, setTab] = useState<Tab>("journal");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Journal form state
  const [showEntryForm, setShowEntryForm] = useState(false);
  const [entryDate, setEntryDate] = useState(new Date().toISOString().slice(0, 10));
  const [entryBody, setEntryBody] = useState("");
  const [savingEntry, setSavingEntry] = useState(false);
  const [deletingEntryId, setDeletingEntryId] = useState<string | null>(null);

  // Content form state
  const [showContentForm, setShowContentForm] = useState(false);
  const [contentUrl, setContentUrl] = useState("");
  const [contentType, setContentType] = useState<ConnectedContent["type"]>("other");
  const [savingContent, setSavingContent] = useState(false);
  const [deletingContentId, setDeletingContentId] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchTrip(id), fetchJournalEntries(id), fetchContent(id)])
      .then(([t, j, c]) => { setTrip(t); setEntries(j); setContent(c); })
      .catch(() => setError("Couldn't load trip. Is the backend running?"))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleAddEntry() {
    if (!entryBody.trim()) return;
    setSavingEntry(true);
    try {
      const entry = await createJournalEntry(id, { date: entryDate, body: entryBody });
      setEntries((prev) => [entry, ...prev]);
      setEntryBody("");
      setShowEntryForm(false);
    } catch {
      setError("Failed to save entry.");
    } finally {
      setSavingEntry(false);
    }
  }

  async function handleDeleteEntry(entryId: string) {
    setDeletingEntryId(entryId);
    try {
      await deleteJournalEntry(id, entryId);
      setEntries((prev) => prev.filter((e) => e.id !== entryId));
    } catch {
      setError("Failed to delete entry.");
    } finally {
      setDeletingEntryId(null);
    }
  }

  async function handleAddContent() {
    if (!contentUrl.trim()) return;
    setSavingContent(true);
    try {
      const item = await addContent(id, contentUrl, contentType);
      setContent((prev) => [item, ...prev]);
      setContentUrl("");
      setShowContentForm(false);
    } catch {
      setError("Failed to add link.");
    } finally {
      setSavingContent(false);
    }
  }

  async function handleDeleteContent(contentId: string) {
    setDeletingContentId(contentId);
    try {
      await deleteContent(id, contentId);
      setContent((prev) => prev.filter((c) => c.id !== contentId));
    } catch {
      setError("Failed to remove link.");
    } finally {
      setDeletingContentId(null);
    }
  }

  if (loading) {
    return (
      <Flex p={8} align="center" gap={2} color="gray.400">
        <Spinner size="sm" />
        <Text fontSize="sm">Loading trip...</Text>
      </Flex>
    );
  }

  if (error || !trip) {
    return (
      <Box p={8}>
        <Text color="red.500">{error ?? "Trip not found."}</Text>
        <Button mt={4} size="sm" variant="ghost" onClick={() => router.push("/trips")}>← Back to trips</Button>
      </Box>
    );
  }

  return (
    <Box p={8} maxW="860px">
      {/* Header */}
      <HStack mb={2} gap={2}>
        <Button size="xs" variant="ghost" color="gray.400" onClick={() => router.push("/trips")}>
          ← Trips
        </Button>
      </HStack>

      <HStack mb={6} gap={4} align="start">
        <Text fontSize="4xl">{trip.emoji}</Text>
        <Box flex={1}>
          <HStack gap={3} align="center">
            <Text fontSize="2xl" fontWeight="bold">{trip.destination}</Text>
            <Badge colorPalette={trip.status === "upcoming" ? "blue" : "gray"} borderRadius="full" px={2}>
              {trip.status}
            </Badge>
          </HStack>
          <Text fontSize="sm" color="gray.400">{trip.dates}</Text>
          {trip.summary && <Text fontSize="sm" color="gray.600" mt={1}>{trip.summary}</Text>}
          {trip.tags && trip.tags.length > 0 && (
            <HStack mt={2} gap={1} flexWrap="wrap">
              {trip.tags.map((tag) => (
                <Badge key={tag} size="sm" variant="subtle" colorPalette="gray">{tag}</Badge>
              ))}
            </HStack>
          )}
        </Box>
      </HStack>

      {/* Tabs */}
      <HStack mb={6} borderBottom="2px solid" borderColor="gray.100" gap={0}>
        {(["journal", "content"] as Tab[]).map((t) => (
          <Button
            key={t}
            variant="ghost"
            size="sm"
            px={4}
            pb={3}
            borderRadius={0}
            borderBottom="2px solid"
            borderColor={tab === t ? "blue.500" : "transparent"}
            color={tab === t ? "blue.600" : "gray.500"}
            fontWeight={tab === t ? "semibold" : "normal"}
            _hover={{ color: "blue.600", bg: "transparent" }}
            onClick={() => setTab(t)}
          >
            {t === "journal" ? "📓 Journal" : "🔗 Connected"}
          </Button>
        ))}
      </HStack>

      {/* Journal tab */}
      {tab === "journal" && (
        <VStack align="stretch" gap={4}>
          <HStack justify="space-between">
            <Text fontSize="sm" color="gray.500">
              {entries.length === 0 ? "No entries yet." : `${entries.length} entr${entries.length === 1 ? "y" : "ies"}`}
            </Text>
            <Button size="sm" colorPalette="blue" variant="outline" onClick={() => setShowEntryForm((v) => !v)}>
              {showEntryForm ? "Cancel" : "+ Add entry"}
            </Button>
          </HStack>

          {showEntryForm && (
            <Box bg="gray.50" borderRadius="xl" p={5} border="1px solid" borderColor="gray.200">
              <VStack align="stretch" gap={3}>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="gray.600">Date</Text>
                  <Input
                    type="date"
                    value={entryDate}
                    onChange={(e) => setEntryDate(e.target.value)}
                    maxW="200px"
                  />
                </Box>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="gray.600">Entry</Text>
                  <Textarea
                    placeholder="What happened today? What did you discover, feel, or want to remember?"
                    value={entryBody}
                    onChange={(e) => setEntryBody(e.target.value)}
                    rows={5}
                    autoFocus
                  />
                </Box>
                <HStack justify="flex-end">
                  <Button
                    size="sm"
                    colorPalette="blue"
                    loading={savingEntry}
                    disabled={!entryBody.trim()}
                    onClick={handleAddEntry}
                  >
                    Save entry
                  </Button>
                </HStack>
              </VStack>
            </Box>
          )}

          {entries.length === 0 && !showEntryForm && (
            <Box py={12} textAlign="center" color="gray.400">
              <Text fontSize="3xl" mb={2}>📓</Text>
              <Text fontSize="sm">Start writing about your trip.</Text>
            </Box>
          )}

          {entries.map((entry) => (
            <Box
              key={entry.id}
              bg="white"
              borderRadius="xl"
              p={5}
              border="1px solid"
              borderColor="gray.100"
              boxShadow="sm"
            >
              <HStack justify="space-between" mb={3}>
                <HStack gap={2}>
                  <Text fontSize="sm" fontWeight="semibold" color="gray.700">
                    {new Date(entry.date + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" })}
                  </Text>
                  {entry.source !== "app" && (
                    <Badge size="sm" variant="subtle" colorPalette="purple">{entry.source}</Badge>
                  )}
                </HStack>
                <Button
                  size="xs"
                  variant="ghost"
                  color="gray.300"
                  _hover={{ color: "red.400" }}
                  loading={deletingEntryId === entry.id}
                  onClick={() => handleDeleteEntry(entry.id)}
                  aria-label="Delete entry"
                >
                  ✕
                </Button>
              </HStack>
              <Text fontSize="sm" color="gray.700" whiteSpace="pre-wrap" lineHeight="tall">
                {entry.body}
              </Text>
            </Box>
          ))}
        </VStack>
      )}

      {/* Connected content tab */}
      {tab === "content" && (
        <VStack align="stretch" gap={4}>
          <HStack justify="space-between">
            <Text fontSize="sm" color="gray.500">
              {content.length === 0 ? "No links yet." : `${content.length} link${content.length === 1 ? "" : "s"}`}
            </Text>
            <Button size="sm" colorPalette="blue" variant="outline" onClick={() => setShowContentForm((v) => !v)}>
              {showContentForm ? "Cancel" : "+ Add link"}
            </Button>
          </HStack>

          {showContentForm && (
            <Box bg="gray.50" borderRadius="xl" p={5} border="1px solid" borderColor="gray.200">
              <VStack align="stretch" gap={3}>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="gray.600">URL</Text>
                  <Input
                    placeholder="https://photos.google.com/album/..."
                    value={contentUrl}
                    onChange={(e) => setContentUrl(e.target.value)}
                    autoFocus
                  />
                </Box>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="gray.600">Type</Text>
                  <HStack gap={2} flexWrap="wrap">
                    {(["album", "instagram", "tiktok", "blog", "other"] as const).map((t) => (
                      <Button
                        key={t}
                        size="sm"
                        variant={contentType === t ? "solid" : "outline"}
                        colorPalette={contentType === t ? "blue" : "gray"}
                        onClick={() => setContentType(t)}
                      >
                        {t === "album" ? "📷 Album" : t === "instagram" ? "📸 Instagram" : t === "tiktok" ? "🎵 TikTok" : t === "blog" ? "📝 Blog" : "🔗 Other"}
                      </Button>
                    ))}
                  </HStack>
                </Box>
                <HStack justify="flex-end">
                  <Button
                    size="sm"
                    colorPalette="blue"
                    loading={savingContent}
                    disabled={!contentUrl.trim()}
                    onClick={handleAddContent}
                  >
                    Add link
                  </Button>
                </HStack>
              </VStack>
            </Box>
          )}

          {content.length === 0 && !showContentForm && (
            <Box py={12} textAlign="center" color="gray.400">
              <Text fontSize="3xl" mb={2}>🔗</Text>
              <Text fontSize="sm">Connect photos, posts, and links from this trip.</Text>
            </Box>
          )}

          <Flex gap={4} flexWrap="wrap">
            {content.map((item) => (
              <Box
                key={item.id}
                bg="white"
                borderRadius="xl"
                border="1px solid"
                borderColor="gray.100"
                boxShadow="sm"
                overflow="hidden"
                w="200px"
                position="relative"
                _hover={{ boxShadow: "md" }}
                transition="all 0.15s"
              >
                {item.thumbnail_url ? (
                  <Box
                    as="img"
                    src={item.thumbnail_url}
                    alt={item.title ?? ""}
                    w="full"
                    h="120px"
                    objectFit="cover"
                  />
                ) : (
                  <Flex h="120px" align="center" justify="center" bg="gray.50" fontSize="3xl">
                    {item.type === "album" ? "📷" : item.type === "instagram" ? "📸" : item.type === "tiktok" ? "🎵" : item.type === "blog" ? "📝" : "🔗"}
                  </Flex>
                )}
                <Box p={3}>
                  <Text fontSize="xs" fontWeight="semibold" color="gray.700" noOfLines={2} lineClamp={2}>
                    {item.title ?? new URL(item.url).hostname}
                  </Text>
                  <Text fontSize="xs" color="gray.400" mt={0.5} noOfLines={1} lineClamp={1}>
                    {item.type}
                  </Text>
                </Box>
                <HStack justify="space-between" px={3} pb={3}>
                  <Button
                    size="xs"
                    variant="ghost"
                    color="blue.400"
                    px={0}
                    onClick={() => window.open(item.url, "_blank")}
                  >
                    Open ↗
                  </Button>
                  <Button
                    size="xs"
                    variant="ghost"
                    color="gray.300"
                    _hover={{ color: "red.400" }}
                    loading={deletingContentId === item.id}
                    onClick={() => handleDeleteContent(item.id)}
                    aria-label="Remove link"
                  >
                    ✕
                  </Button>
                </HStack>
              </Box>
            ))}
          </Flex>
        </VStack>
      )}
    </Box>
  );
}
