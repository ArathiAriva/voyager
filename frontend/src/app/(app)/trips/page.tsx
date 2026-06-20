"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Box, Flex, Grid, Text, VStack, HStack, Badge, Spinner,
  Button, Input, Textarea, Select, Portal, createListCollection,
} from "@chakra-ui/react";
import { fetchTrips, createTrip, deleteTrip, type Trip, type TripCreate } from "@/lib/api";

const STATUS_OPTIONS = createListCollection({
  items: [
    { label: "Past", value: "past" },
    { label: "Upcoming", value: "upcoming" },
  ],
});

const EMOJI_OPTIONS = ["✈️","🏖️","🏔️","🗺️","🏯","🌮","🌊","🌍","🏕️","🚂","🛳️","🗼"];

const EMPTY_FORM: TripCreate = {
  destination: "",
  dates: "",
  status: "upcoming",
  emoji: "✈️",
  summary: "",
  tags: [],
};

export default function TripsPage() {
  const router = useRouter();
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
    <Box p={8}>
      <VStack align="start" gap={6} w="full">
        <HStack justify="space-between" w="full">
          <Box>
            <Text fontSize="2xl" fontWeight="bold">Your Trips</Text>
            <Text color="gray.500" fontSize="sm">Every journey, remembered.</Text>
          </Box>
          <Button colorPalette="blue" size="sm" onClick={() => setShowModal(true)}>
            + New trip
          </Button>
        </HStack>

        {loading && (
          <Flex align="center" gap={2} color="gray.400">
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
                bg="white"
                borderRadius="xl"
                p={5}
                boxShadow="sm"
                border="1px solid"
                borderColor="gray.100"
                _hover={{ boxShadow: "md", borderColor: "blue.100" }}
                transition="all 0.15s"
                cursor="pointer"
                position="relative"
                onClick={() => router.push(`/trips/${trip.id}`)}
              >
                <HStack justify="space-between" mb={3}>
                  <Text fontSize="2xl">{trip.emoji}</Text>
                  <HStack gap={2}>
                    <Badge
                      colorPalette={trip.status === "upcoming" ? "blue" : "gray"}
                      borderRadius="full"
                      px={2}
                    >
                      {trip.status}
                    </Badge>
                    <Button
                      size="xs"
                      variant="ghost"
                      color="gray.400"
                      _hover={{ color: "red.500", bg: "red.50" }}
                      onClick={(e) => handleDelete(e, trip.id)}
                      loading={deletingId === trip.id}
                      aria-label="Delete trip"
                      px={1}
                    >
                      ✕
                    </Button>
                  </HStack>
                </HStack>
                <Text fontWeight="semibold" fontSize="lg">{trip.destination}</Text>
                <Text fontSize="sm" color="gray.400" mb={2}>{trip.dates}</Text>
                <Text fontSize="sm" color="gray.600" lineHeight="tall">{trip.summary}</Text>
                {trip.tags && trip.tags.length > 0 && (
                  <HStack mt={3} gap={1} flexWrap="wrap">
                    {trip.tags.map((tag) => (
                      <Badge key={tag} size="sm" variant="subtle" colorPalette="gray">{tag}</Badge>
                    ))}
                  </HStack>
                )}
              </Box>
            ))}

            <Box
              bg="gray.50"
              borderRadius="xl"
              p={5}
              border="2px dashed"
              borderColor="gray.200"
              display="flex"
              alignItems="center"
              justifyContent="center"
              cursor="pointer"
              _hover={{ borderColor: "blue.300", bg: "blue.50" }}
              transition="all 0.15s"
              minH="160px"
              onClick={() => setShowModal(true)}
            >
              <VStack gap={1} color="gray.400">
                <Text fontSize="2xl">+</Text>
                <Text fontSize="sm">Add a trip</Text>
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
              bg="white" borderRadius="2xl" p={8} w="full" maxW="480px" mx={4}
              boxShadow="2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <Text fontSize="xl" fontWeight="bold" mb={6}>New trip</Text>

              <VStack gap={4} align="stretch">
                {/* Emoji picker */}
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={2} color="gray.600">Emoji</Text>
                  <HStack gap={2} flexWrap="wrap">
                    {EMOJI_OPTIONS.map((e) => (
                      <Box
                        key={e}
                        fontSize="xl"
                        cursor="pointer"
                        p={1}
                        borderRadius="md"
                        bg={form.emoji === e ? "blue.50" : "transparent"}
                        border="2px solid"
                        borderColor={form.emoji === e ? "blue.300" : "transparent"}
                        onClick={() => setForm((f) => ({ ...f, emoji: e }))}
                      >
                        {e}
                      </Box>
                    ))}
                  </HStack>
                </Box>

                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="gray.600">Destination *</Text>
                  <Input
                    placeholder="e.g. Kyoto, Japan"
                    value={form.destination}
                    onChange={(e) => setForm((f) => ({ ...f, destination: e.target.value }))}
                  />
                </Box>

                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="gray.600">Dates *</Text>
                  <Input
                    placeholder="e.g. March 2025 or Apr 10–17 2025"
                    value={form.dates}
                    onChange={(e) => setForm((f) => ({ ...f, dates: e.target.value }))}
                  />
                </Box>

                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="gray.600">Status</Text>
                  <HStack gap={3}>
                    {(["upcoming", "past"] as const).map((s) => (
                      <Button
                        key={s}
                        size="sm"
                        variant={form.status === s ? "solid" : "outline"}
                        colorPalette={form.status === s ? "blue" : "gray"}
                        onClick={() => setForm((f) => ({ ...f, status: s }))}
                      >
                        {s === "upcoming" ? "Upcoming" : "Past"}
                      </Button>
                    ))}
                  </HStack>
                </Box>

                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={1} color="gray.600">Summary</Text>
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
