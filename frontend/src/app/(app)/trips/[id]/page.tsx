"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Box, Flex, HStack, VStack, Text, Badge, Button, Textarea, Input,
  Spinner, Portal, Tabs,
} from "@chakra-ui/react";
import { ChevronLeftIcon, PencilIcon } from "@/components/icons";
import { useConfirm } from "@/components/confirm-dialog";
import {
  fetchTrip, fetchJournalEntries, createJournalEntry, deleteJournalEntry,
  fetchContent, addContent, deleteContent, updateTrip,
  fetchPlaces, createPlace, deletePlace,
  type Trip, type JournalEntry, type ConnectedContent, type TripUpdate, type ItineraryDay,
  type SavedPlace, type PlaceCategory, PLACE_CATEGORIES,
} from "@/lib/api";

type Tab = "journal" | "itinerary" | "places" | "content";

const TABS: { value: Tab; label: string }[] = [
  { value: "journal", label: "Journal" },
  { value: "itinerary", label: "Itinerary" },
  { value: "places", label: "Places" },
  { value: "content", label: "Connected" },
];

/** Count pill shown on each tab. Muted normally, accent-tinted when its tab is active. */
function TabCount({ n, active }: { n: number; active: boolean }) {
  return (
    <Badge
      size="sm"
      borderRadius="full"
      px={1.5}
      minW="18px"
      justifyContent="center"
      fontVariantNumeric="tabular-nums"
      bg={active ? "accent.activeBg" : "bg.muted"}
      color={active ? "accent.active" : "text.secondary"}
    >
      {n}
    </Badge>
  );
}

export default function TripDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const { confirm, dialog } = useConfirm();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [content, setContent] = useState<ConnectedContent[]>([]);
  const [tab, setTab] = useState<Tab>("journal");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit trip state
  const [showEditForm, setShowEditForm] = useState(false);
  const [editForm, setEditForm] = useState<TripUpdate>({});
  const [saving, setSaving] = useState(false);

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

  // Places state
  const [places, setPlaces] = useState<SavedPlace[]>([]);
  const [showPlaceForm, setShowPlaceForm] = useState(false);
  const [placeName, setPlaceName] = useState("");
  const [placeUrl, setPlaceUrl] = useState("");
  const [placeCategory, setPlaceCategory] = useState<PlaceCategory>("other");
  const [placeNotes, setPlaceNotes] = useState("");
  const [savingPlace, setSavingPlace] = useState(false);
  const [deletingPlaceId, setDeletingPlaceId] = useState<string | null>(null);
  const [selectedPlace, setSelectedPlace] = useState<SavedPlace | null>(null);

  useEffect(() => {
    Promise.all([fetchTrip(id), fetchJournalEntries(id), fetchContent(id), fetchPlaces(id)])
      .then(([t, j, c, p]) => { setTrip(t); setEntries(j); setContent(c); setPlaces(p); })
      .catch(() => setError("Couldn't load trip. Is the backend running?"))
      .finally(() => setLoading(false));
  }, [id]);

  function openEdit() {
    if (!trip) return;
    setEditForm({
      destination: trip.destination,
      dates: trip.dates,
      status: trip.status,
      emoji: trip.emoji,
      summary: trip.summary,
      tags: trip.tags ?? [],
    });
    setShowEditForm(true);
  }

  async function handleSaveEdit() {
    if (!trip) return;
    setSaving(true);
    try {
      const updated = await updateTrip(trip.id, editForm);
      setTrip(updated);
      setShowEditForm(false);
    } catch {
      setError("Failed to save changes.");
    } finally {
      setSaving(false);
    }
  }

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
    const ok = await confirm({
      title: "Delete this entry?",
      body: "This journal entry will be removed, along with the memories extracted from it. This cannot be undone.",
      confirmLabel: "Delete entry",
    });
    if (!ok) return;
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
    const ok = await confirm({
      title: "Remove this link?",
      body: "This link will be removed from the trip. This cannot be undone.",
      confirmLabel: "Remove link",
    });
    if (!ok) return;
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

  async function handleAddPlace() {
    if (!placeName.trim()) return;
    setSavingPlace(true);
    try {
      const place = await createPlace(id, {
        name: placeName,
        url: placeUrl.trim() || undefined,
        category: placeCategory,
        notes: placeNotes.trim() || undefined,
      });
      setPlaces((prev) => [place, ...prev]);
      setPlaceName("");
      setPlaceUrl("");
      setPlaceNotes("");
      setPlaceCategory("other");
      setShowPlaceForm(false);
    } catch {
      setError("Failed to save place.");
    } finally {
      setSavingPlace(false);
    }
  }

  async function handleDeletePlace(placeId: string) {
    const place = places.find((p) => p.id === placeId);
    const ok = await confirm({
      title: "Remove this place?",
      body: `${place?.name ?? "This place"} will be removed from the trip. This cannot be undone.`,
      confirmLabel: "Remove place",
    });
    if (!ok) return;
    setDeletingPlaceId(placeId);
    try {
      await deletePlace(id, placeId);
      setPlaces((prev) => prev.filter((p) => p.id !== placeId));
    } catch {
      setError("Failed to remove place.");
    } finally {
      setDeletingPlaceId(null);
    }
  }

  if (loading) {
    return (
      <Flex p={8} align="center" gap={2} color="text.secondary">
        <Spinner size="sm" />
        <Text fontSize="sm">Loading trip...</Text>
      </Flex>
    );
  }

  if (error || !trip) {
    return (
      <Box p={8}>
        <Text color="red.500">{error ?? "Trip not found."}</Text>
        <Button
          mt={4}
          size="sm"
          variant="ghost"
          color="text.secondary"
          onClick={() => router.push("/trips")}
          _hover={{ bg: "bg.muted", color: "text.primary" }}
        >
          <ChevronLeftIcon />
          Trips
        </Button>
      </Box>
    );
  }

  const counts: Record<Tab, number> = {
    journal: entries.length,
    itinerary: trip?.itinerary?.length ?? 0,
    places: places.length,
    content: content.length,
  };

  return (
    <Box p={8} maxW="860px">
      {dialog}
      {/* Header */}
      <HStack mb={4} gap={2} justify="space-between">
        <Button
          size="sm"
          variant="ghost"
          color="text.secondary"
          onClick={() => router.push("/trips")}
          _hover={{ bg: "bg.muted", color: "text.primary" }}
        >
          <ChevronLeftIcon />
          Trips
        </Button>
        {!showEditForm && (
          <Button
            size="sm"
            variant="outline"
            borderColor="border.muted"
            color="text.primary"
            onClick={openEdit}
            _hover={{ bg: "bg.muted", borderColor: "text.muted" }}
          >
            <PencilIcon />
            Edit trip
          </Button>
        )}
      </HStack>

      {showEditForm ? (
        <Box bg="bg.subtle" borderRadius="2xl" p={6} mb={6} border="1px solid" borderColor="border.default">
          <Text fontSize="lg" fontWeight="bold" mb={5}>Edit trip</Text>
          <VStack align="stretch" gap={4}>
            {/* Emoji */}
            <Box>
              <Text fontSize="sm" fontWeight="medium" mb={2} color="text.secondary">Emoji</Text>
              <HStack gap={2} flexWrap="wrap">
                {["🧭","🏖️","🏔️","🗺️","🏯","🌮","🌊","🌍","🏕️","🚂","🛳️","🗼"].map((e) => (
                  <Box
                    key={e}
                    fontSize="xl"
                    cursor="pointer"
                    p={1}
                    borderRadius="md"
                    bg={editForm.emoji === e ? "accent.activeBg" : "transparent"}
                    border="2px solid"
                    borderColor={editForm.emoji === e ? "accent.active" : "transparent"}
                    onClick={() => setEditForm((f) => ({ ...f, emoji: e }))}
                  >
                    {e}
                  </Box>
                ))}
              </HStack>
            </Box>
            <Box>
              <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Destination</Text>
              <Input
                value={editForm.destination ?? ""}
                onChange={(e) => setEditForm((f) => ({ ...f, destination: e.target.value }))}
              />
            </Box>
            <Box>
              <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Dates</Text>
              <Input
                value={editForm.dates ?? ""}
                onChange={(e) => setEditForm((f) => ({ ...f, dates: e.target.value }))}
              />
            </Box>
            <Box>
              <Text fontSize="sm" fontWeight="medium" mb={2} color="text.secondary">Status</Text>
              <HStack gap={3}>
                {(["upcoming", "active", "past"] as const).map((s) => (
                  <Button
                    key={s}
                    size="sm"
                    variant={editForm.status === s ? "solid" : "outline"}
                    colorPalette={editForm.status === s ? (s === "active" ? "green" : "blue") : "gray"}
                    onClick={() => setEditForm((f) => ({ ...f, status: s }))}
                  >
                    {s === "upcoming" ? "Upcoming" : s === "active" ? "🟢 Active" : "Past"}
                  </Button>
                ))}
              </HStack>
            </Box>
            <Box>
              <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Summary</Text>
              <Textarea
                value={editForm.summary ?? ""}
                onChange={(e) => setEditForm((f) => ({ ...f, summary: e.target.value }))}
                rows={3}
              />
            </Box>
            <Box>
              <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Tags (comma-separated)</Text>
              <Input
                value={(editForm.tags ?? []).join(", ")}
                onChange={(e) => setEditForm((f) => ({
                  ...f,
                  tags: e.target.value.split(",").map((t) => t.trim()).filter(Boolean),
                }))}
                placeholder="e.g. solo, food, hiking"
              />
            </Box>
            <HStack justify="flex-end" gap={3} pt={1}>
              <Button variant="ghost" onClick={() => setShowEditForm(false)}>Cancel</Button>
              <Button
                colorPalette="blue"
                loading={saving}
                disabled={!editForm.destination?.trim() || !editForm.dates?.trim()}
                onClick={handleSaveEdit}
              >
                Save changes
              </Button>
            </HStack>
          </VStack>
        </Box>
      ) : (
        <HStack mb={6} gap={4} align="start">
          <Text fontSize="4xl">{trip.emoji}</Text>
          <Box flex={1}>
            <HStack gap={3} align="center">
              <Text fontSize="2xl" fontWeight="bold">{trip.destination}</Text>
              <Badge
                colorPalette={trip.status === "active" ? "green" : trip.status === "upcoming" ? "blue" : "gray"}
                borderRadius="full"
                px={2}
              >
                {trip.status === "active" ? "🟢 Active" : trip.status}
              </Badge>
            </HStack>
            <Text fontSize="sm" color="text.secondary">{trip.dates}</Text>
            {trip.summary && <Text fontSize="sm" color="text.secondary" mt={1}>{trip.summary}</Text>}
            {trip.tags && trip.tags.length > 0 && (
              <HStack mt={2} gap={1} flexWrap="wrap">
                {trip.tags.map((tag) => (
                  <Badge key={tag} size="sm" variant="subtle" colorPalette="gray">{tag}</Badge>
                ))}
              </HStack>
            )}
          </Box>
        </HStack>
      )}

      {/* Tabs */}
      <Tabs.Root
        value={tab}
        onValueChange={(e) => setTab(e.value as Tab)}
        variant="line"
        colorPalette="blue"
        mb={6}
      >
        <Tabs.List>
          {TABS.map((t) => (
            <Tabs.Trigger key={t.value} value={t.value} gap={2}>
              {t.label}
              <TabCount n={counts[t.value]} active={tab === t.value} />
            </Tabs.Trigger>
          ))}
        </Tabs.List>
      </Tabs.Root>

      {/* Journal tab */}
      {tab === "journal" && (
        <VStack align="stretch" gap={4}>
          <HStack justify="space-between">
            <Text fontSize="sm" color="text.muted">
              {entries.length === 0 ? "" : `${entries.length} entr${entries.length === 1 ? "y" : "ies"}`}
            </Text>
            <Button size="sm" colorPalette="blue" variant="outline" onClick={() => setShowEntryForm((v) => !v)}>
              {showEntryForm ? "Cancel" : "+ Add entry"}
            </Button>
          </HStack>

          {showEntryForm && (
            <Box bg="bg.subtle" borderRadius="xl" p={5} border="1px solid" borderColor="border.default">
              <VStack align="stretch" gap={3}>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Date</Text>
                  <Input
                    type="date"
                    value={entryDate}
                    onChange={(e) => setEntryDate(e.target.value)}
                    maxW="200px"
                  />
                </Box>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Entry</Text>
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
            <Box py={12} textAlign="center" color="text.secondary">
              <Text fontSize="3xl" mb={2}>📓</Text>
              <Text fontSize="sm">Start writing about your trip.</Text>
            </Box>
          )}

          {entries.map((entry) => (
            <Box
              key={entry.id}
              bg="bg.surface"
              borderRadius="xl"
              p={5}
              border="1px solid"
              borderColor="border.default"
              boxShadow="sm"
            >
              <HStack justify="space-between" mb={3}>
                <HStack gap={2}>
                  <Text fontSize="sm" fontWeight="semibold" color="text.bright">
                    {new Date(entry.date + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" })}
                  </Text>
                  {entry.source !== "app" && (
                    <Badge size="sm" variant="subtle" colorPalette="purple">{entry.source}</Badge>
                  )}
                </HStack>
                <Button
                  size="xs"
                  variant="ghost"
                  color="text.dim"
                  _hover={{ color: "red.400" }}
                  loading={deletingEntryId === entry.id}
                  onClick={() => handleDeleteEntry(entry.id)}
                  aria-label="Delete entry"
                >
                  ✕
                </Button>
              </HStack>
              <Text fontSize="sm" color="text.dim" whiteSpace="pre-wrap" lineHeight="tall">
                {entry.body}
              </Text>
            </Box>
          ))}
        </VStack>
      )}

      {/* Itinerary tab */}
      {tab === "itinerary" && (
        <VStack align="stretch" gap={4}>
          {(!trip.itinerary || trip.itinerary.length === 0) ? (
            <Box py={12} textAlign="center" color="text.secondary">
              <Text fontSize="3xl" mb={3}>🗺️</Text>
              <Text fontSize="sm" mb={4}>No itinerary yet.</Text>
              <Box
                bg="bg.subtle"
                border="1px solid"
                borderColor="border.default"
                borderRadius="xl"
                p={5}
                maxW="420px"
                mx="auto"
                textAlign="left"
              >
                <Text fontSize="sm" fontWeight="semibold" mb={2} color="text.bright">
                  Ask Voyager to plan this trip
                </Text>
                <Text fontSize="xs" color="text.secondary" lineHeight="tall">
                  Go to chat and say something like:{" "}
                  <Text as="span" fontStyle="italic" color="text.dim">
                    &ldquo;Plan my itinerary for {trip.destination}&rdquo;
                  </Text>
                  {" "}and Voyager will build and save a day-by-day plan here.
                </Text>
              </Box>
            </Box>
          ) : (
            <VStack align="stretch" gap={3}>
              {trip.itinerary.map((day: ItineraryDay) => (
                <Box
                  key={day.day}
                  bg="bg.surface"
                  borderRadius="xl"
                  border="1px solid"
                  borderColor="border.default"
                  boxShadow="sm"
                  overflow="hidden"
                >
                  <HStack
                    px={5}
                    py={3}
                    bg="bg.subtle"
                    borderBottom="1px solid"
                    borderColor="border.default"
                    gap={3}
                  >
                    <Box
                      w={7}
                      h={7}
                      borderRadius="full"
                      bg="blue.500"
                      display="flex"
                      alignItems="center"
                      justifyContent="center"
                      flexShrink={0}
                    >
                      <Text fontSize="xs" fontWeight="bold" color="white">{day.day}</Text>
                    </Box>
                    <Box flex={1}>
                      {day.title && (
                        <Text fontSize="sm" fontWeight="semibold" color="text.bright">{day.title}</Text>
                      )}
                      {day.date && (
                        <Text fontSize="xs" color="text.secondary">
                          {new Date(day.date + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}
                        </Text>
                      )}
                    </Box>
                  </HStack>
                  <Box px={5} py={4}>
                    <Text fontSize="sm" color="text.dim" whiteSpace="pre-wrap" lineHeight="tall">
                      {day.plan}
                    </Text>
                  </Box>
                </Box>
              ))}
            </VStack>
          )}
        </VStack>
      )}

      {/* Places tab */}
      {tab === "places" && (
        <VStack align="stretch" gap={4}>
          <HStack justify="space-between">
            <Text fontSize="sm" color="text.muted">
              {places.length === 0 ? "" : `${places.length} place${places.length === 1 ? "" : "s"}`}
            </Text>
            <Button size="sm" colorPalette="blue" variant="outline" onClick={() => setShowPlaceForm((v) => !v)}>
              {showPlaceForm ? "Cancel" : "+ Add place"}
            </Button>
          </HStack>

          {showPlaceForm && (
            <Box bg="bg.subtle" borderRadius="xl" p={5} border="1px solid" borderColor="border.default">
              <VStack align="stretch" gap={3}>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Name</Text>
                  <Input
                    placeholder="e.g. Ichiran Ramen Shinjuku"
                    value={placeName}
                    onChange={(e) => setPlaceName(e.target.value)}
                    autoFocus
                  />
                </Box>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">URL (optional)</Text>
                  <Input
                    placeholder="https://maps.google.com/..."
                    value={placeUrl}
                    onChange={(e) => setPlaceUrl(e.target.value)}
                  />
                  <Text fontSize="xs" color="text.dim" mt={1}>Paste a link and Voyager will fetch details automatically.</Text>
                </Box>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={2} color="text.secondary">Category</Text>
                  <HStack gap={2} flexWrap="wrap">
                    {PLACE_CATEGORIES.map((cat) => (
                      <Button
                        key={cat}
                        size="xs"
                        variant={placeCategory === cat ? "solid" : "outline"}
                        colorPalette={placeCategory === cat ? "blue" : "gray"}
                        onClick={() => setPlaceCategory(cat)}
                      >
                        {cat}
                      </Button>
                    ))}
                  </HStack>
                </Box>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Notes (optional)</Text>
                  <Textarea
                    placeholder="Why you want to visit, what it's known for..."
                    value={placeNotes}
                    onChange={(e) => setPlaceNotes(e.target.value)}
                    rows={2}
                  />
                </Box>
                <HStack justify="flex-end">
                  <Button
                    size="sm"
                    colorPalette="blue"
                    loading={savingPlace}
                    disabled={!placeName.trim()}
                    onClick={handleAddPlace}
                  >
                    Save place
                  </Button>
                </HStack>
              </VStack>
            </Box>
          )}

          {places.length === 0 && !showPlaceForm && (
            <Box py={12} textAlign="center" color="text.secondary">
              <Text fontSize="3xl" mb={2}>📍</Text>
              <Text fontSize="sm" mb={1}>Save restaurants, hotels, and spots to visit.</Text>
              <Text fontSize="xs" color="text.dim">You can also ask Voyager in chat to save places for you.</Text>
            </Box>
          )}

          <Flex gap={4} flexWrap="wrap">
            {places.map((place) => {
              const categoryEmoji: Record<string, string> = {
                restaurant: "🍽️", cafe: "☕", bar: "🍸", hotel: "🏨",
                "street food": "🍢", neighbourhood: "🏘️", attraction: "🎭", shop: "🛍️", beach: "🏖️", other: "📍",
              };
              const emoji = categoryEmoji[place.category] ?? "📍";
              return (
                <Box
                  key={place.id}
                  bg="bg.surface"
                  borderRadius="xl"
                  border="1px solid"
                  borderColor="border.default"
                  boxShadow="sm"
                  overflow="hidden"
                  w="220px"
                  position="relative"
                  cursor="pointer"
                  _hover={{ boxShadow: "md", borderColor: "blue.400" }}
                  transition="all 0.15s"
                  onClick={() => setSelectedPlace(place)}
                >
                  {place.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={place.thumbnail_url}
                      alt={place.name}
                      style={{ width: "100%", height: "120px", objectFit: "cover" }}
                    />
                  ) : (
                    <Flex h="120px" align="center" justify="center" bg="bg.subtle" fontSize="3xl">
                      {emoji}
                    </Flex>
                  )}
                  <Box p={3}>
                    <HStack justify="space-between" align="start" mb={1}>
                      <Text fontSize="sm" fontWeight="semibold" color="text.bright" lineClamp={2} flex={1}>
                        {place.name}
                      </Text>
                      {place.enrichment_status === "pending" && (
                        <Spinner size="xs" color="blue.400" flexShrink={0} />
                      )}
                    </HStack>
                    <Badge size="xs" variant="subtle" colorPalette="gray" mb={1}>{place.category}</Badge>
                    {place.address && (
                      <Text fontSize="xs" color="text.secondary" lineClamp={1}>{place.address}</Text>
                    )}
                    {place.summary ? (
                      <Text fontSize="xs" color="text.dim" mt={1} lineClamp={3}>{place.summary}</Text>
                    ) : place.notes ? (
                      <Text fontSize="xs" color="text.dim" mt={1} fontStyle="italic" lineClamp={3}>{place.notes}</Text>
                    ) : place.enrichment_status === "pending" ? (
                      <Text fontSize="xs" color="text.dim" mt={1}>Fetching details...</Text>
                    ) : null}
                  </Box>
                  <HStack justify="space-between" px={3} pb={3}>
                    {place.url ? (
                      <Button size="xs" variant="ghost" color="blue.400" px={0} onClick={(e) => { e.stopPropagation(); window.open(place.url!, "_blank"); }}>
                        Open ↗
                      </Button>
                    ) : <Box />}
                    <Button
                      size="xs"
                      variant="ghost"
                      color="text.dim"
                      _hover={{ color: "red.400" }}
                      loading={deletingPlaceId === place.id}
                      onClick={(e) => { e.stopPropagation(); handleDeletePlace(place.id); }}
                      aria-label="Remove place"
                    >
                      ✕
                    </Button>
                  </HStack>
                </Box>
              );
            })}
          </Flex>
        </VStack>
      )}

      {/* Connected content tab */}
      {tab === "content" && (
        <VStack align="stretch" gap={4}>
          <HStack justify="space-between">
            <Text fontSize="sm" color="text.muted">
              {content.length === 0 ? "" : `${content.length} link${content.length === 1 ? "" : "s"}`}
            </Text>
            <Button size="sm" colorPalette="blue" variant="outline" onClick={() => setShowContentForm((v) => !v)}>
              {showContentForm ? "Cancel" : "+ Add link"}
            </Button>
          </HStack>

          {showContentForm && (
            <Box bg="bg.subtle" borderRadius="xl" p={5} border="1px solid" borderColor="border.default">
              <VStack align="stretch" gap={3}>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">URL</Text>
                  <Input
                    placeholder="https://photos.google.com/album/..."
                    value={contentUrl}
                    onChange={(e) => setContentUrl(e.target.value)}
                    autoFocus
                  />
                </Box>
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Type</Text>
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
            <Box py={12} textAlign="center" color="text.secondary">
              <Text fontSize="3xl" mb={2}>🔗</Text>
              <Text fontSize="sm">Connect photos, posts, and links from this trip.</Text>
            </Box>
          )}

          <Flex gap={4} flexWrap="wrap">
            {content.map((item) => (
              <Box
                key={item.id}
                bg="bg.surface"
                borderRadius="xl"
                border="1px solid"
                borderColor="border.default"
                boxShadow="sm"
                overflow="hidden"
                w="200px"
                position="relative"
                _hover={{ boxShadow: "md" }}
                transition="all 0.15s"
              >
                {item.thumbnail_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={item.thumbnail_url}
                    alt={item.title ?? ""}
                    style={{ width: "100%", height: "120px", objectFit: "cover" }}
                  />
                ) : (
                  <Flex h="120px" align="center" justify="center" bg="bg.subtle" fontSize="3xl">
                    {item.type === "album" ? "📷" : item.type === "instagram" ? "📸" : item.type === "tiktok" ? "🎵" : item.type === "blog" ? "📝" : "🔗"}
                  </Flex>
                )}
                <Box p={3}>
                  <Text fontSize="xs" fontWeight="semibold" color="text.bright" lineClamp={2}>
                    {item.title ?? new URL(item.url).hostname}
                  </Text>
                  <Text fontSize="xs" color="text.secondary" mt={0.5} lineClamp={1}>
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
                    color="text.dim"
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
      {/* Place detail modal */}
      {selectedPlace && (
        <Portal>
          <Box
            position="fixed" inset={0} bg="blackAlpha.600" zIndex={100}
            display="flex" alignItems="center" justifyContent="center"
            onClick={() => setSelectedPlace(null)}
          >
            <Box
              bg="bg.surface" borderRadius="2xl" w="full" maxW="520px" mx={4}
              boxShadow="2xl" overflow="hidden"
              onClick={(e) => e.stopPropagation()}
            >
              {selectedPlace.thumbnail_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={selectedPlace.thumbnail_url}
                  alt={selectedPlace.name}
                  style={{ width: "100%", height: "200px", objectFit: "cover" }}
                />
              ) : (
                <Flex h="140px" align="center" justify="center" bg="bg.subtle" fontSize="5xl">
                  {({
                    restaurant: "🍽️", cafe: "☕", bar: "🍸", hotel: "🏨",
                    "street food": "🍢", neighbourhood: "🏘️", attraction: "🎭", shop: "🛍️", beach: "🏖️", other: "📍",
                  } as Record<string, string>)[selectedPlace.category] ?? "📍"}
                </Flex>
              )}
              <Box p={6}>
                <HStack justify="space-between" align="start" mb={2}>
                  <Text fontSize="xl" fontWeight="bold" color="text.bright" flex={1}>{selectedPlace.name}</Text>
                  <Button size="xs" variant="ghost" color="text.dim" onClick={() => setSelectedPlace(null)}>✕</Button>
                </HStack>
                <HStack gap={2} mb={3}>
                  <Badge size="sm" variant="subtle" colorPalette="blue">{selectedPlace.category}</Badge>
                  {selectedPlace.enrichment_status === "pending" && (
                    <HStack gap={1}><Spinner size="xs" color="blue.400" /><Text fontSize="xs" color="text.dim">Fetching details...</Text></HStack>
                  )}
                </HStack>
                {selectedPlace.address && (
                  <Text fontSize="sm" color="text.secondary" mb={3}>📍 {selectedPlace.address}</Text>
                )}
                {selectedPlace.summary && (
                  <Text fontSize="sm" color="text.dim" lineHeight="tall" mb={3}>{selectedPlace.summary}</Text>
                )}
                {selectedPlace.notes && (
                  <Box bg="bg.subtle" borderRadius="lg" p={3} mb={3}>
                    <Text fontSize="xs" fontWeight="semibold" color="text.secondary" mb={1}>Your notes</Text>
                    <Text fontSize="sm" color="text.dim" fontStyle="italic" lineHeight="tall">{selectedPlace.notes}</Text>
                  </Box>
                )}
                <HStack justify="space-between" pt={1}>
                  {selectedPlace.url ? (
                    <Button size="sm" colorPalette="blue" variant="outline" onClick={() => window.open(selectedPlace.url!, "_blank")}>
                      Open link ↗
                    </Button>
                  ) : <Box />}
                  <Button
                    size="sm" variant="ghost" color="text.dim" _hover={{ color: "red.400" }}
                    loading={deletingPlaceId === selectedPlace.id}
                    onClick={async () => { await handleDeletePlace(selectedPlace.id); setSelectedPlace(null); }}
                  >
                    Delete
                  </Button>
                </HStack>
              </Box>
            </Box>
          </Box>
        </Portal>
      )}
    </Box>
  );
}
