"use client";

import { useEffect, useState } from "react";
import { Box, Button, HStack, Text, Portal } from "@chakra-ui/react";
import { fetchTrips, type Trip } from "@/lib/api";
import { MapIcon, CheckIcon } from "@/components/icons";

/**
 * Picks which trip a conversation is about, or none.
 *
 * "No specific trip" is deliberately the first option and one click away. Real
 * conversation titles include "What is the best time of year to visit Japan?" and
 * "Which was my most reflective trip?" — unscoped and cross-trip are first-class
 * uses, so scoping must never feel mandatory. See docs/trip-scoped-chats.md.
 *
 * A live trip is preselected when one exists: mid-trip, nearly every chat is about
 * that trip.
 */
export function TripScopePicker({
  value,
  onChange,
  trips: providedTrips,
  size = "sm",
  label = "Trip",
}: {
  value: string | null;
  onChange: (tripId: string | null) => void;
  trips?: Trip[];
  size?: "xs" | "sm";
  label?: string;
}) {
  // Only fetched when the caller does not already have the list. Copying
  // `providedTrips` into state would mirror a prop the parent already owns,
  // which is the cascading-render pattern the react-hooks rule flags.
  const [fetched, setFetched] = useState<Trip[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (providedTrips) return;
    let ignore = false;
    fetchTrips()
      .then((t) => { if (!ignore) setFetched(t); })
      .catch(() => { if (!ignore) setFetched([]); });
    return () => { ignore = true; };
  }, [providedTrips]);

  const trips = providedTrips ?? fetched;
  const selected = trips.find((t) => t.id === value) ?? null;

  return (
    <Box position="relative">
      <Button
        size={size}
        variant="ghost"
        gap={1.5}
        color={selected ? "text.bright" : "text.secondary"}
        onClick={() => setOpen((v) => !v)}
        aria-label={label}
      >
        <MapIcon size={13} />
        <Text fontSize="xs" lineClamp={1} maxW="180px">
          {selected ? selected.destination : "No specific trip"}
        </Text>
      </Button>

      {open && (
        <Portal>
          {/* Click-away layer. A dropdown that only closes via its own control
              strands the user if they click elsewhere first. */}
          <Box position="fixed" inset={0} zIndex={1400} onClick={() => setOpen(false)} />
        </Portal>
      )}

      {open && (
        <Box
          position="absolute"
          top="calc(100% + 4px)"
          left={0}
          zIndex={1500}
          minW="240px"
          maxH="320px"
          overflowY="auto"
          bg="bg.surface"
          borderRadius="xl"
          border="1px solid"
          borderColor="border.default"
          boxShadow="0 8px 32px rgba(0,0,0,0.32)"
          py={1}
        >
          <Option
            active={value === null}
            onClick={() => { onChange(null); setOpen(false); }}
          >
            <Text fontSize="sm" color="text.secondary">No specific trip</Text>
          </Option>

          {trips.length > 0 && (
            <Box h="1px" bg="border.default" my={1} />
          )}

          {trips.map((trip) => (
            <Option
              key={trip.id}
              active={value === trip.id}
              onClick={() => { onChange(trip.id); setOpen(false); }}
            >
              <HStack gap={2} minW={0}>
                <Text fontSize="sm">{trip.emoji}</Text>
                <Box minW={0}>
                  <Text fontSize="sm" lineClamp={1}>{trip.destination}</Text>
                  <Text fontSize="10px" color="text.secondary" lineClamp={1}>
                    {trip.is_live
                      ? `Happening now${trip.live_day ? ` · day ${trip.live_day}` : ""}`
                      : trip.dates}
                  </Text>
                </Box>
              </HStack>
            </Option>
          ))}

          {trips.length === 0 && (
            <Box px={3} py={2}>
              <Text fontSize="xs" color="text.secondary">No trips yet.</Text>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}

function Option({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <HStack
      as="button"
      w="full"
      px={3}
      py={2}
      gap={2}
      justify="space-between"
      cursor="pointer"
      textAlign="left"
      bg={active ? "accent.activeBg" : "transparent"}
      _hover={{ bg: active ? "accent.activeBg" : "bg.subtle" }}
      onClick={onClick}
    >
      <Box minW={0} flex={1}>{children}</Box>
      {active && <Box color="accent.active" flexShrink={0}><CheckIcon size={12} /></Box>}
    </HStack>
  );
}

/** Compact read-only badge for a conversation row. */
export function TripScopeBadge({ trip }: { trip: Trip | undefined }) {
  if (!trip) return null;
  return (
    <HStack
      gap={1}
      px={2}
      py="1px"
      borderRadius="full"
      bg={trip.is_live ? "green.950" : "bg.muted"}
      flexShrink={0}
    >
      <Text fontSize="10px">{trip.emoji}</Text>
      <Text
        fontSize="10px"
        fontWeight="600"
        color={trip.is_live ? "green.400" : "text.secondary"}
        lineClamp={1}
        maxW="120px"
      >
        {trip.destination}
      </Text>
    </HStack>
  );
}
