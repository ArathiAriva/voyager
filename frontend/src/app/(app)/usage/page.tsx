"use client";

import { useEffect, useState } from "react";
import { Box, VStack, HStack, Text, Grid, Spinner, Flex, Button } from "@chakra-ui/react";
import {
  fetchUsageSummary,
  fetchRecentUsage,
  type UsageSummary,
  type UsageCall,
  type UsageBreakdownRow,
} from "@/lib/api";
import { ChartIcon } from "@/components/icons";

const WINDOWS = [7, 30, 90] as const;

function fmtCost(v: number | null | undefined): string {
  if (v == null) return "—";
  return v < 0.01 ? `$${v.toFixed(5)}` : `$${v.toFixed(2)}`;
}

function fmtTokens(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return String(v);
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Box bg="bg.surface" borderRadius="2xl" p={5} boxShadow="0 4px 20px rgba(0,0,0,0.2)">
      <Text fontSize="xs" fontWeight="600" letterSpacing="0.08em" textTransform="uppercase" color="text.secondary" mb={1}>
        {label}
      </Text>
      <Text fontSize="2xl" fontWeight="800" letterSpacing="-0.02em">{value}</Text>
    </Box>
  );
}

function BreakdownTable({ title, rows, maxCost }: { title: string; rows: UsageBreakdownRow[]; maxCost: number }) {
  return (
    <VStack align="stretch" gap={3} w="full">
      <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
        {title}
      </Text>
      <Box bg="bg.surface" borderRadius="2xl" p={5} boxShadow="0 4px 20px rgba(0,0,0,0.2)">
        {rows.length === 0 && <Text fontSize="sm" color="text.secondary">No data in this window.</Text>}
        <VStack align="stretch" gap={3}>
          {rows.map((r) => (
            <Box key={r.key}>
              <HStack justify="space-between" mb={1}>
                <Text fontSize="sm" color="text.dim" fontFamily={title === "By model" ? "mono" : undefined}>
                  {r.key}
                </Text>
                <HStack gap={4}>
                  <Text fontSize="xs" color="text.secondary">{r.calls} calls</Text>
                  <Text fontSize="xs" color="text.secondary">{fmtTokens(r.total_tokens)} tok</Text>
                  <Text fontSize="sm" fontWeight="600" minW="16" textAlign="right">{fmtCost(r.cost_usd)}</Text>
                </HStack>
              </HStack>
              <Box h="1.5" bg="bg.subtle" borderRadius="full" overflow="hidden">
                <Box
                  h="full"
                  bg="teal.500"
                  borderRadius="full"
                  w={`${maxCost > 0 ? Math.max(2, (r.cost_usd / maxCost) * 100) : 2}%`}
                />
              </Box>
            </Box>
          ))}
        </VStack>
      </Box>
    </VStack>
  );
}

export default function UsagePage() {
  const [days, setDays] = useState<number>(30);
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [recent, setRecent] = useState<UsageCall[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchUsageSummary(days), fetchRecentUsage(25)])
      .then(([s, r]) => {
        setSummary(s);
        setRecent(r);
        setError(null);
      })
      .catch(() => setError("Couldn't load usage data. Is the backend running?"))
      .finally(() => setLoading(false));
  }, [days]);

  const maxCost = summary
    ? Math.max(
        ...summary.by_model.map((r) => r.cost_usd),
        ...summary.by_context.map((r) => r.cost_usd),
        ...summary.by_day.map((r) => r.cost_usd),
        0,
      )
    : 0;

  const isEmpty = summary && summary.totals.calls === 0;

  return (
    <Box p={10}>
      <VStack align="start" gap={8} w="full">
        <Flex w="full" justify="space-between" align="end" wrap="wrap" gap={4}>
          <Box>
            <Text fontSize="xs" fontWeight="600" letterSpacing="0.1em" textTransform="uppercase" color="text.secondary" mb={2}>
              LLM spend & tokens
            </Text>
            <Text fontSize="3xl" fontWeight="800" letterSpacing="-0.03em" lineHeight="1.1">Usage</Text>
          </Box>
          <HStack gap={2}>
            {WINDOWS.map((w) => (
              <Button
                key={w}
                size="xs"
                variant={days === w ? "solid" : "outline"}
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
            <Text fontSize="sm">Loading usage...</Text>
          </Flex>
        )}

        {error && (
          <Box w="full" p={4} bg="red.950" borderRadius="lg" border="1px solid" borderColor="red.800">
            <Text fontSize="sm" color="red.600">{error}</Text>
          </Box>
        )}

        {isEmpty && !loading && (
          <Box py={16} w="full" textAlign="center" color="text.secondary">
            <Box color="text.muted" display="flex" justifyContent="center" mb={3}><ChartIcon size={26} /></Box>
            <Text fontSize="sm" fontWeight="medium">No LLM calls recorded yet.</Text>
            <Text fontSize="sm" mt={1}>Chat with Voyager or plan a trip and usage will show up here.</Text>
          </Box>
        )}

        {summary && !isEmpty && (
          <>
            <Grid templateColumns="repeat(auto-fill, minmax(180px, 1fr))" gap={3} w="full">
              <StatCard label={`Cost (${summary.window_days}d)`} value={fmtCost(summary.totals.cost_usd)} />
              <StatCard label="LLM calls" value={String(summary.totals.calls)} />
              <StatCard label="Prompt tokens" value={fmtTokens(summary.totals.prompt_tokens)} />
              <StatCard label="Completion tokens" value={fmtTokens(summary.totals.completion_tokens)} />
            </Grid>

            <Grid templateColumns={{ base: "1fr", lg: "1fr 1fr" }} gap={8} w="full">
              <BreakdownTable title="By context" rows={summary.by_context} maxCost={maxCost} />
              <BreakdownTable title="By model" rows={summary.by_model} maxCost={maxCost} />
            </Grid>

            <BreakdownTable title="By day" rows={summary.by_day} maxCost={maxCost} />

            <VStack align="stretch" gap={3} w="full">
              <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
                Recent calls
              </Text>
              <Box bg="bg.surface" borderRadius="2xl" p={5} boxShadow="0 4px 20px rgba(0,0,0,0.2)" overflowX="auto">
                <VStack align="stretch" gap={2}>
                  {recent.map((c, i) => (
                    <HStack key={i} justify="space-between" fontSize="xs" gap={4} py={1} borderBottom={i < recent.length - 1 ? "1px solid" : "none"} borderColor="border.default">
                      <Text color="text.secondary" minW="32" flexShrink={0}>
                        {new Date(c.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                      </Text>
                      <Text color="text.dim" flexShrink={0}>{c.context}</Text>
                      <Text color="text.secondary" fontFamily="mono" truncate flex="1">{c.model}</Text>
                      <Text color="text.secondary" flexShrink={0}>{fmtTokens(c.prompt_tokens)}→{fmtTokens(c.completion_tokens)}</Text>
                      <Text fontWeight="600" flexShrink={0} minW="16" textAlign="right">{fmtCost(c.cost_usd)}</Text>
                    </HStack>
                  ))}
                </VStack>
              </Box>
            </VStack>
          </>
        )}
      </VStack>
    </Box>
  );
}
