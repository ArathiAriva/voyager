"use client";

import { useEffect, useState } from "react";
import { Box, VStack, HStack, Text, Grid, Spinner, Flex, Button } from "@chakra-ui/react";
import {
  fetchRetrievalSummary,
  fetchRecentRetrievals,
  type RetrievalSummary,
  type RetrievalCall,
  type RetrievalCollectionStats,
} from "@/lib/api";
import { CompassIcon } from "@/components/icons";

const WINDOWS = [7, 30, 90] as const;

/**
 * Thresholds turn a number into a judgement. Without them the page is a wall of
 * decimals and the reader has to remember what "good" looks like per metric --
 * which is how B-6 (Rome plans retrieving Lisbon places) stayed live for months.
 *
 * Distances are all-MiniLM-L6-v2 L2 and mirror the per-collection retrieval
 * floors in backend/app/memory.py: at the floor, results are being dropped.
 */
const DISTANCE_FLOOR: Record<string, number> = {
  semantic: 1.3,
  episodic: 1.3,
  journals: 1.45,
  saved_places: 1.75,
};

type Tone = "good" | "warn" | "bad" | "neutral";

const TONE_COLOR: Record<Tone, string> = {
  good: "green.400",
  warn: "orange.400",
  bad: "red.400",
  neutral: "text.dim",
};

function rateTone(rate: number | null, warn: number, bad: number): Tone {
  if (rate == null) return "neutral";
  if (rate >= bad) return "bad";
  if (rate >= warn) return "warn";
  return "good";
}

function distanceTone(distance: number | null, collection: string): Tone {
  if (distance == null) return "neutral";
  const floor = DISTANCE_FLOOR[collection];
  if (!floor) return "neutral";
  if (distance >= floor) return "bad";
  if (distance >= floor * 0.85) return "warn";
  return "good";
}

const pct = (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(0)}%`);
const num = (v: number | null, digits = 2) => (v == null ? "—" : v.toFixed(digits));

function Metric({
  label,
  value,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: string;
  tone?: Tone;
  hint?: string;
}) {
  return (
    <Box>
      <Text fontSize="10px" fontWeight="700" letterSpacing="0.08em" textTransform="uppercase" color="text.secondary">
        {label}
      </Text>
      <Text fontSize="lg" fontWeight="700" letterSpacing="-0.02em" color={TONE_COLOR[tone]} lineHeight="1.3">
        {value}
      </Text>
      {hint && <Text fontSize="10px" color="text.secondary" mt={0.5}>{hint}</Text>}
    </Box>
  );
}

function CollectionCard({ name, stats }: { name: string; stats: RetrievalCollectionStats }) {
  const floor = DISTANCE_FLOOR[name];
  return (
    <Box bg="bg.surface" borderRadius="2xl" p={5} boxShadow="0 4px 20px rgba(0,0,0,0.2)">
      <HStack justify="space-between" mb={4}>
        <Text fontSize="sm" fontWeight="700" fontFamily="mono">{name}</Text>
        <Text fontSize="xs" color="text.secondary">{stats.searches} searches</Text>
      </HStack>
      <Grid templateColumns="repeat(auto-fit, minmax(96px, 1fr))" gap={4}>
        <Metric
          label="Zero rate"
          value={pct(stats.zero_rate)}
          tone={rateTone(stats.zero_rate, 0.15, 0.35)}
          hint="found nothing"
        />
        <Metric
          label="Best dist p50"
          value={num(stats.best_distance_p50)}
          tone={distanceTone(stats.best_distance_p50, name)}
          hint={floor ? `floor ${floor}` : undefined}
        />
        <Metric
          label="Best dist p90"
          value={num(stats.best_distance_p90)}
          tone={distanceTone(stats.best_distance_p90, name)}
        />
        <Metric
          label="Saturation"
          value={pct(stats.saturation_rate)}
          tone={rateTone(stats.saturation_rate, 0.6, 0.85)}
          hint="hit the limit"
        />
        <Metric label="Avg returned" value={num(stats.avg_returned, 1)} />
        <Metric
          label="Filtered zero"
          value={pct(stats.filtered_zero_rate)}
          tone={rateTone(stats.filtered_zero_rate, 0.2, 0.4)}
          hint={`${stats.filtered_searches} filtered`}
        />
        <Metric label="Latency p50" value={stats.latency_ms_p50 == null ? "—" : `${num(stats.latency_ms_p50, 0)}ms`} />
      </Grid>
    </Box>
  );
}

export default function RetrievalPage() {
  const [summary, setSummary] = useState<RetrievalSummary | null>(null);
  const [recent, setRecent] = useState<RetrievalCall[]>([]);
  const [days, setDays] = useState<number>(30);
  const [zeroOnly, setZeroOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // The fetch is kicked off from the effect without a synchronous setState in the
  // effect body -- setting `loading` there triggers a cascading render, which the
  // react-hooks lint rule flags. `ignore` drops the result of a request whose
  // inputs changed while it was in flight, so a slow 90d fetch cannot overwrite a
  // faster 7d one that the user asked for afterwards.
  useEffect(() => {
    let ignore = false;
    Promise.all([fetchRetrievalSummary(days), fetchRecentRetrievals({ limit: 50, zeroOnly })])
      .then(([s, r]) => {
        if (ignore) return;
        setSummary(s);
        setRecent(r);
        setError(null);
      })
      .catch(() => {
        if (!ignore) setError("Couldn't load retrieval data. Is the backend running?");
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => { ignore = true; };
  }, [days, zeroOnly]);

  const collections = Object.entries(summary?.collections ?? {});
  const callers = Object.entries(summary?.callers ?? {});
  const isEmpty = summary != null && summary.total_searches === 0;

  return (
    <Box p={10}>
      <VStack align="start" gap={8} w="full">
        <Flex justify="space-between" align="end" w="full" gap={4} wrap="wrap">
          <Box>
            <Text fontSize="xs" fontWeight="600" letterSpacing="0.1em" textTransform="uppercase" color="text.secondary" mb={2}>
              Is the retriever finding the right things
            </Text>
            <Text fontSize="3xl" fontWeight="800" letterSpacing="-0.03em" lineHeight="1.1">Retrieval</Text>
          </Box>
          <HStack gap={2}>
            {WINDOWS.map((w) => (
              <Button
                key={w}
                size="xs"
                variant={days === w ? "solid" : "ghost"}
                colorPalette={days === w ? "blue" : "gray"}
                onClick={() => setDays(w)}
              >
                {w}d
              </Button>
            ))}
          </HStack>
        </Flex>

        {loading && (
          <Flex align="center" gap={2} color="text.secondary">
            <Spinner size="sm" />
            <Text fontSize="sm">Loading retrieval data…</Text>
          </Flex>
        )}

        {error && (
          <Box w="full" p={4} bg="red.950" borderRadius="lg" border="1px solid" borderColor="red.800">
            <Text fontSize="sm" color="red.600">{error}</Text>
          </Box>
        )}

        {isEmpty && (
          <Box py={16} w="full" textAlign="center" color="text.secondary">
            <Box color="text.muted" display="flex" justifyContent="center" mb={3}><CompassIcon size={26} /></Box>
            <Text fontSize="sm" fontWeight="medium">No searches logged in this window.</Text>
            <Text fontSize="sm" mt={1}>
              Every memory, journal, and saved-place search is recorded here. Chat with
              Voyager or plan a trip and the numbers will fill in.
            </Text>
          </Box>
        )}

        {summary && !isEmpty && (
          <>
            <Text fontSize="sm" color="text.secondary">
              {summary.total_searches} searches in the last {summary.days} days.
              Distances are L2 on all-MiniLM-L6-v2 — lower is a closer match, and the
              floor is where results start being dropped.
            </Text>

            <VStack align="stretch" gap={3} w="full">
              <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
                By collection
              </Text>
              <Grid templateColumns="repeat(auto-fill, minmax(380px, 1fr))" gap={3} w="full">
                {collections.map(([name, stats]) => (
                  <CollectionCard key={name} name={name} stats={stats} />
                ))}
              </Grid>
            </VStack>

            {callers.length > 0 && (
              <VStack align="stretch" gap={3} w="full">
                <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
                  By caller
                </Text>
                <Box bg="bg.surface" borderRadius="2xl" p={5} boxShadow="0 4px 20px rgba(0,0,0,0.2)">
                  <VStack align="stretch" gap={3}>
                    {callers.map(([caller, stats]) => (
                      <HStack key={caller} justify="space-between">
                        <Text fontSize="sm" color="text.dim" fontFamily="mono">{caller}</Text>
                        <HStack gap={4}>
                          <Text fontSize="xs" color="text.secondary">{stats.searches} searches</Text>
                          <Text
                            fontSize="sm"
                            fontWeight="600"
                            minW="12"
                            textAlign="right"
                            color={TONE_COLOR[rateTone(stats.zero_rate, 0.15, 0.35)]}
                          >
                            {pct(stats.zero_rate)}
                          </Text>
                        </HStack>
                      </HStack>
                    ))}
                  </VStack>
                  <Text fontSize="10px" color="text.secondary" mt={3}>
                    Zero rate per call site — which part of the app is searching and coming back empty.
                  </Text>
                </Box>
              </VStack>
            )}
          </>
        )}

        {summary && (
          <VStack align="stretch" gap={3} w="full">
            <Flex justify="space-between" align="center" wrap="wrap" gap={2}>
              <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
                Recent searches
              </Text>
              <Button
                size="xs"
                variant={zeroOnly ? "solid" : "ghost"}
                colorPalette={zeroOnly ? "orange" : "gray"}
                onClick={() => setZeroOnly((v) => !v)}
              >
                {zeroOnly ? "Showing zero-result only" : "Zero-result only"}
              </Button>
            </Flex>
            <Box bg="bg.surface" borderRadius="2xl" p={5} boxShadow="0 4px 20px rgba(0,0,0,0.2)" overflowX="auto">
              {recent.length === 0 ? (
                <Text fontSize="sm" color="text.secondary">
                  {zeroOnly ? "No zero-result searches — that's the good outcome." : "No searches logged yet."}
                </Text>
              ) : (
                <VStack align="stretch" gap={2} minW="640px">
                  {recent.map((call) => (
                    <Box key={call.id} py={2} borderBottom="1px solid" borderColor="border.default" _last={{ borderBottom: "none" }}>
                      <HStack justify="space-between" align="start" gap={4}>
                        <Box flex="1" minW={0}>
                          <Text fontSize="sm" color="text.dim" lineClamp={1}>{call.query || "—"}</Text>
                          <HStack gap={3} mt={1}>
                            <Text fontSize="10px" color="text.secondary" fontFamily="mono">{call.collection}</Text>
                            <Text fontSize="10px" color="text.secondary" fontFamily="mono">{call.caller}</Text>
                            {call.filters && Object.values(call.filters).some((v) => v != null) && (
                              <Text fontSize="10px" color="text.secondary">
                                filtered: {Object.entries(call.filters)
                                  .filter(([, v]) => v != null)
                                  .map(([k, v]) => `${k}=${v}`)
                                  .join(", ")}
                              </Text>
                            )}
                          </HStack>
                        </Box>
                        <HStack gap={4} flexShrink={0}>
                          <Text
                            fontSize="xs"
                            fontWeight="600"
                            color={call.n_returned === 0 ? TONE_COLOR.bad : "text.secondary"}
                          >
                            {call.n_returned}/{call.n_requested}
                          </Text>
                          <Text
                            fontSize="xs"
                            minW="10"
                            textAlign="right"
                            color={TONE_COLOR[distanceTone(call.best_distance, call.collection)]}
                          >
                            {num(call.best_distance)}
                          </Text>
                        </HStack>
                      </HStack>
                    </Box>
                  ))}
                </VStack>
              )}
            </Box>
          </VStack>
        )}
      </VStack>
    </Box>
  );
}
