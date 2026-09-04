"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Box, Flex, Grid, Text, VStack, HStack, Badge, Spinner,
  Button, Input, Textarea, Select, Portal, createListCollection,
} from "@chakra-ui/react";
import { fetchTrips, createTrip, deleteTrip, type Trip, type TripCreate } from "@/lib/api";
import { useConfirm } from "@/components/confirm-dialog";

const STATUS_OPTIONS = createListCollection({
  items: [
    { label: "Past", value: "past" },
    { label: "Upcoming", value: "upcoming" },
  ],
});

const EMOJI_OPTIONS = ["🧭","🏖️","🏔️","🗺️","🏯","🌮","🌊","🌍","🏕️","🚂","🛳️","🗼"];

const EMPTY_FORM: TripCreate = {
  destination: "",
  dates: "",
  status: "upcoming",
  emoji: "🧭",
  summary: "",
  tags: [],
};

export default function TripsPage() {
  const router = useRouter();
  const { confirm, dialog } = useConfirm();
  const [trips, setTrips] = useState<Trip[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<TripCreate>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    fetchTrips()
      .then(setTrips)
      .catch(() => setError("Couldn't load trips. Is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  async function handleCreate() {
    if (!form.destination.trim() || !form.dates.trim()) return;
    setSaving(true);
    try {
      const trip = await createTrip(form);
      setTrips((prev) => [trip, ...prev]);
      setShowModal(false);
      setForm(EMPTY_FORM);
    } catch {
      setError("Failed to create trip.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    const trip = trips.find((t) => t.id === id);
    const ok = await confirm({
      title: "Delete this trip?",
      body: `${trip?.destination ?? "This trip"} will be removed, along with its journal entries and saved places. This cannot be undone.`,
      confirmLabel: "Delete trip",
    });
    if (!ok) return;
    setDeletingId(id);
    try {
      await deleteTrip(id);
      setTrips((prev) => prev.filter((t) => t.id !== id));
    } catch {
      setError("Failed to delete trip.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <Box p={10}>
      {dialog}
      <VStack align="start" gap={8} w="full">
        <HStack justify="space-between" w="full" align="end">
          <Box>
            <Text fontSize="xs" fontWeight="600" letterSpacing="0.1em" textTransform="uppercase" color="text.secondary" mb={2}>Your journeys</Text>
            <Text fontSize="3xl" fontWeight="800" letterSpacing="-0.03em" lineHeight="1.1">Trips</Text>
          </Box>
          <Box
            as="button"
            onClick={() => setShowModal(true)}
            px={5}
            py={2.5}
            bg="accent.active"
            color="bg.page"
            borderRadius="full"
            fontSize="sm"
            fontWeight="700"
            _hover={{ opacity: 0.88 }}
            transition="opacity 0.15s"
          >
            + New trip
          </Box>
        </HStack>

        {loading && (
          <Flex align="center" gap={2} color="text.secondary">
            <Spinner size="sm" />
            <Text fontSize="sm">Loading trips...</Text>
          </Flex>
        )}

        {error && (
          <Box w="full" p={4} bg="red.50" borderRadius="lg" border="1px solid" borderColor="red.200">
            <Text fontSize="sm" color="red.600">{error}</Text>
          </Box>
        )}

        {!loading && !error && (
          <Grid templateColumns="repeat(auto-fill, minmax(300px, 1fr))" gap={4} w="full">
            {trips.map((trip) => (
              <Box
                key={trip.id}
                bg="bg.surface"
                borderRadius="2xl"
                p={6}
                boxShadow={trip.status === "active" ? "0 0 0 2px var(--chakra-colors-green-500), 0 4px 24px rgba(0,0,0,0.22)" : "0 4px 24px rgba(0,0,0,0.22)"}
                border="none"
                _hover={{ boxShadow: trip.status === "active" ? "0 0 0 2px var(--chakra-colors-green-400), 0 8px 32px rgba(0,0,0,0.32)" : "0 8px 32px rgba(0,0,0,0.32)", transform: "translateY(-2px)" }}
                transition="all 0.2s"
                cursor="pointer"
                position="relative"
                onClick={() => router.push(`/trips/${trip.id}`)}
              >
                <HStack justify="space-between" mb={4}>
                  <Text fontSize="3xl">{trip.emoji}</Text>
                  <HStack gap={2}>
                    <Badge
                      colorPalette={trip.status === "active" ? "green" : trip.status === "upcoming" ? "blue" : "gray"}
                      borderRadius="full"
                      px={3}
                      py={1}
                      fontSize="xs"
                      fontWeight="600"
                      textTransform="uppercase"
                      letterSpacing="0.05em"
                    >
                      {trip.status === "active" ? "🟢 Active" : trip.status}
                    </Badge>
                    <Button
                      size="xs"
                      variant="ghost"
                      color="text.secondary"
                      _hover={{ color: "red.400", bg: "transparent" }}
                      onClick={(e) => handleDelete(e, trip.id)}
                      loading={deletingId === trip.id}
                      aria-label="Delete trip"
                      px={1}
                    >
                      ✕
                    </Button>
                  </HStack>
                </HStack>
                <Text fontWeight="800" fontSize="xl" letterSpacing="-0.02em" lineHeight="1.2" mb={1}>{trip.destination}</Text>
                <Text fontSize="xs" color="text.secondary" mb={2} fontWeight="500" letterSpacing="0.03em">{trip.dates}</Text>
                <Text fontSize="sm" color="text.secondary" lineHeight="1.65">{trip.summary}</Text>
                {trip.tags && trip.tags.length > 0 && (
                  <HStack mt={4} gap={1.5} flexWrap="wrap">
                    {trip.tags.map((tag) => (
                      <Box key={tag} px={2.5} py={0.5} borderRadius="full" border="1px solid" borderColor="border.muted" fontSize="xs" color="text.secondary" fontWeight="500">
                        {tag}
                      </Box>
                    ))}
                  </HStack>
                )}
              </Box>
            ))}

            <Box
              bg="transparent"
              borderRadius="2xl"
              p={6}
              border="2px dashed"
              borderColor="border.muted"
              display="flex"
              alignItems="center"
              justifyContent="center"
              cursor="pointer"
              _hover={{ borderColor: "accent.active" }}
              transition="all 0.2s"
              minH="180px"
              onClick={() => setShowModal(true)}
            >
              <VStack gap={2} color="text.secondary">
                <Text fontSize="2xl" lineHeight="1">+</Text>
                <Text fontSize="sm" fontWeight="500" letterSpacing="0.02em">Add a trip</Text>
              </VStack>
            </Box>
          </Grid>
        )}
      </VStack>

      {/* Create trip modal */}
      {showModal && (
        <Portal>
          <Box
            position="fixed" inset={0} bg="blackAlpha.600" zIndex={100}
            display="flex" alignItems="center" justifyContent="center"
            onClick={() => setShowModal(false)}
          >
            <Box
              bg="bg.surface" borderRadius="2xl" p={8} w="full" maxW="480px" mx={4}
              boxShadow="2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <Text fontSize="xl" fontWeight="bold" mb={6}>New trip</Text>

              <VStack gap={4} align="stretch">
                {/* Emoji picker */}
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={2} color="text.secondary">Emoji</Text>
                  <HStack gap={2} flexWrap="wrap">
                    {EMOJI_OPTIONS.map((e) => (
                      <Box
                        key={e}
                        fontSize="xl"
                        cursor="pointer"
                        p={1}
                        borderRadius="md"
                        bg={form.emoji === e ? "accent.activeBg" : "transparent"}
                        border="2px solid"
                        borderColor={form.emoji === e ? "accent.active" : "transparent"}
                        onClick={() => setForm((f) => ({ ...f, emoji: e }))}
                      >
                        {e}
                      </Box>
                    ))}
                  </HStack>
                </Box>

                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Destination *</Text>
                  <Input
                    placeholder="e.g. Kyoto, Japan"
                    value={form.destination}
                    onChange={(e) => setForm((f) => ({ ...f, destination: e.target.value }))}
                  />
                </Box>

                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Dates *</Text>
                  <Input
                    placeholder="e.g. March 2025 or Apr 10–17 2025"
                    value={form.dates}
                    onChange={(e) => setForm((f) => ({ ...f, dates: e.target.value }))}
                  />
                </Box>

                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Status</Text>
                  <HStack gap={3}>
                    {(["upcoming", "active", "past"] as const).map((s) => (
                      <Button
                        key={s}
                        size="sm"
                        variant={form.status === s ? "solid" : "outline"}
                        colorPalette={form.status === s ? (s === "active" ? "green" : "blue") : "gray"}
                        onClick={() => setForm((f) => ({ ...f, status: s }))}
                      >
                        {s === "upcoming" ? "Upcoming" : s === "active" ? "🟢 Active" : "Past"}
                      </Button>
                    ))}
                  </HStack>
                </Box>

                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="text.secondary">Summary</Text>
                  <Textarea
                    placeholder="A short description of the trip..."
                    value={form.summary}
                    onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))}
                    rows={3}
                  />
                </Box>

                <HStack justify="flex-end" gap={3} pt={2}>
                  <Button variant="ghost" onClick={() => { setShowModal(false); setForm(EMPTY_FORM); }}>
                    Cancel
                  </Button>
                  <Button
                    colorPalette="blue"
                    loading={saving}
                    disabled={!form.destination.trim() || !form.dates.trim()}
                    onClick={handleCreate}
                  >
                    Create trip
                  </Button>
                </HStack>
              </VStack>
            </Box>
          </Box>
        </Portal>
      )}
    </Box>
  );
}
