"use client";

import { useEffect, useState } from "react";
import { Box, VStack, HStack, Text, Flex, Spinner, Badge } from "@chakra-ui/react";
import {
  fetchPlanningRuns,
  fetchPlanningRun,
  type PlanningRunSummary,
  type PlanningRunDetail,
  type PlanningStep,
} from "@/lib/api";
import { CompassIcon, ChevronRightIcon } from "@/components/icons";

/** Each graph node's role, so the timeline reads as a conversation between agents. */
const NODE_META: Record<string, { label: string; role: string }> = {
  load_context: { label: "Context loader", role: "Pulls preferences, past trips and saved places from memory" },
  classify_intent: { label: "Orchestrator", role: "Decides whether this is a full plan, a revision, or needs clarification" },
  clarify: { label: "Clarifier", role: "Asks the user for missing information" },
  build_brief: { label: "Brief builder", role: "Turns the request into a structured brief the researchers share" },
  activities_researcher: { label: "Activities researcher", role: "Finds things to do" },
  food_researcher: { label: "Food researcher", role: "Finds places to eat and drink" },
  logistics_researcher: { label: "Logistics researcher", role: "Transport, timing and getting around" },
  accommodation_researcher: { label: "Accommodation researcher", role: "Where to stay" },
  optimizer: { label: "Optimizer", role: "Clusters everything geographically into days" },
  critic: { label: "Critic", role: "Scores the draft and raises issues" },
  targeted_revision: { label: "Reviser", role: "Re-runs only the domains the critic objected to" },
  assemble_reply: { label: "Reply assembler", role: "Writes the final response to the user" },
  persist_itinerary: { label: "Persister", role: "Saves the itinerary to the trip" },
};

function meta(node: string) {
  return NODE_META[node] ?? { label: node, role: "" };
}

function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

function fmtWhen(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function StepRow({ step, isLast }: { step: PlanningStep; isLast: boolean }) {
  const [open, setOpen] = useState(false);
  const m = meta(step.node);
  const failed = Boolean(step.error);

  return (
    <HStack align="stretch" gap={0} w="full">
      {/* rail */}
      <Flex direction="column" align="center" w="28px" flexShrink={0}>
        <Box
          w="10px" h="10px" borderRadius="full" mt="14px" flexShrink={0}
          bg={failed ? "red.500" : "accent.active"}
        />
        {!isLast && <Box w="2px" flex={1} bg="border.default" mt={1} />}
      </Flex>

      <Box flex={1} pb={3} minW={0}>
        <Box
          as="button"
          onClick={() => setOpen((v) => !v)}
          w="full"
          textAlign="left"
          bg="bg.surface"
          borderRadius="xl"
          border="1px solid"
          borderColor={failed ? "red.500" : "border.default"}
          px={4}
          py={3}
          cursor="pointer"
          _hover={{ borderColor: failed ? "red.400" : "border.muted" }}
          transition="border-color 0.12s"
        >
          <HStack justify="space-between" gap={3} align="start">
            <HStack gap={2.5} align="start" minW={0}>
              <Box minW={0}>
                <HStack gap={2} flexWrap="wrap">
                  <Text fontSize="sm" fontWeight="600">{m.label}</Text>
                  <Text fontSize="xs" color="text.muted" fontFamily="mono">{step.node}</Text>
                </HStack>
                <Text fontSize="xs" color="text.secondary" mt={0.5}>
                  {step.error ? step.error : step.summary || m.role}
                </Text>
              </Box>
            </HStack>
            <HStack gap={2} flexShrink={0}>
              <Text fontSize="xs" color="text.muted" fontVariantNumeric="tabular-nums">
                {fmtDuration(step.duration_ms)}
              </Text>
              <Text fontSize="xs" color="text.muted">{open ? "▾" : "▸"}</Text>
            </HStack>
          </HStack>
        </Box>

        {open && (
          <Box
            mt={1.5} bg="bg.subtle" borderRadius="lg" border="1px solid"
            borderColor="border.default" p={3} overflowX="auto"
          >
            <Text fontSize="xs" color="text.muted" mb={2}>
              What this agent handed to the next
            </Text>
            <Box as="pre" fontSize="xs" fontFamily="mono" color="text.dim" whiteSpace="pre-wrap" wordBreak="break-word">
              {JSON.stringify(step.output, null, 2)}
            </Box>
          </Box>
        )}
      </Box>
    </HStack>
  );
}

export default function PlanningPage() {
  const [runs, setRuns] = useState<PlanningRunSummary[]>([]);
  const [selected, setSelected] = useState<PlanningRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingRun, setLoadingRun] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchPlanningRuns()
      .then((rs) => {
        setRuns(rs);
        if (rs.length > 0) return fetchPlanningRun(rs[0].id).then(setSelected);
      })
      .catch(() => setError("Couldn't load planning runs. Is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  async function open(id: string) {
    setLoadingRun(true);
    try {
      setSelected(await fetchPlanningRun(id));
    } catch {
      setError("Couldn't load that run.");
    } finally {
      setLoadingRun(false);
    }
  }

  if (loading) {
    return <Flex justify="center" py={20}><Spinner /></Flex>;
  }

  return (
    <Box p={10} maxW="1100px">
      <VStack align="stretch" gap={7}>
        <Box>
          <Text fontSize="xs" fontWeight="600" letterSpacing="0.1em" textTransform="uppercase" color="text.secondary" mb={2}>
            Developer
          </Text>
          <Text fontSize="3xl" fontWeight="800" letterSpacing="-0.03em" lineHeight="1.1">
            Agent traces
          </Text>
          <Text fontSize="sm" color="text.secondary" mt={2} maxW="60ch">
            Every multi-agent planning run, and what each agent handed the next.
            Pick a run on the left to see its timeline, then click any step for that
            agent&rsquo;s full output.
          </Text>
        </Box>

        {error && <Text fontSize="sm" color="red.400">{error}</Text>}

        {runs.length === 0 ? (
          <Box py={12} textAlign="center" border="1px dashed" borderColor="border.muted" borderRadius="xl">
            <Box color="text.muted" display="flex" justifyContent="center" mb={2}><CompassIcon size={26} /></Box>
            <Text fontSize="sm" fontWeight="600">No planning runs yet</Text>
            <Text fontSize="xs" color="text.secondary" mt={1} maxW="46ch" mx="auto">
              Ask Voyager to plan a trip — something like &ldquo;plan my 3 days in Lisbon&rdquo;.
              Only the multi-agent planner is traced; plain chat messages are not.
            </Text>
          </Box>
        ) : (
          // Side-by-side from `md` rather than `lg`: with the page capped at 1100px
          // and p={10} padding, the lg breakpoint (1024px) meant most laptop windows
          // fell back to the stacked layout, where the run list and the timeline read
          // as one continuous list of cards.
          <Flex gap={6} align="start" direction={{ base: "column", md: "row" }}>
            {/* run list */}
            <VStack align="stretch" gap={2} w={{ base: "full", md: "280px", lg: "300px" }} flexShrink={0}>
              {/* Headings matter more than they look here: below the lg breakpoint the
                  two columns stack, so without them the run list and the timeline read
                  as one continuous list of cards and nothing says the first group is
                  clickable. */}
              <HStack justify="space-between" align="baseline" mb={1}>
                <Text fontSize="xs" fontWeight="700" letterSpacing="0.08em" textTransform="uppercase" color="text.secondary">
                  Runs
                </Text>
                <Text fontSize="xs" color="text.muted">
                  {runs.length} {runs.length === 1 ? "run" : "runs"} · select one
                </Text>
              </HStack>
              {runs.map((r) => {
                const active = selected?.id === r.id;
                return (
                  <Box
                    key={r.id}
                    as="button"
                    onClick={() => open(r.id)}
                    textAlign="left"
                    bg={active ? "accent.activeBg" : "bg.surface"}
                    borderRadius="xl"
                    border="1px solid"
                    borderColor={active ? "accent.active" : "border.default"}
                    px={4} py={3} cursor="pointer"
                    _hover={{ borderColor: active ? "accent.active" : "border.muted" }}
                    transition="border-color 0.12s"
                  >
                    <HStack justify="space-between" gap={2} mb={1}>
                      <HStack gap={1.5} minW={0} flex={1}>
                        {active && (
                          <Box color="accent.active" flexShrink={0} aria-hidden="true">
                            <ChevronRightIcon size={12} />
                          </Box>
                        )}
                        <Text fontSize="sm" fontWeight="600" lineClamp={1}>
                          {r.destination ?? "Unknown destination"}
                        </Text>
                      </HStack>
                      {r.status === "failed" ? (
                        <Badge size="sm" colorPalette="red" borderRadius="full">failed</Badge>
                      ) : r.critic_score != null ? (
                        <Badge size="sm" colorPalette="gray" borderRadius="full">{r.critic_score}/5</Badge>
                      ) : null}
                    </HStack>
                    <Text fontSize="xs" color="text.secondary" lineClamp={2}>{r.user_message}</Text>
                    <HStack gap={2} mt={1.5}>
                      <Text fontSize="xs" color="text.muted">{fmtWhen(r.created_at)}</Text>
                      <Text fontSize="xs" color="text.muted">·</Text>
                      <Text fontSize="xs" color="text.muted">{r.step_count} steps</Text>
                      <Text fontSize="xs" color="text.muted">·</Text>
                      <Text fontSize="xs" color="text.muted">{fmtDuration(r.duration_ms)}</Text>
                    </HStack>
                  </Box>
                );
              })}
            </VStack>

            {/* timeline */}
            <Box flex={1} minW={0} w="full">
              <HStack justify="space-between" align="baseline" mb={3}>
                <Text fontSize="xs" fontWeight="700" letterSpacing="0.08em" textTransform="uppercase" color="text.secondary">
                  Timeline
                </Text>
                {selected && (
                  <Text fontSize="xs" color="text.muted" lineClamp={1}>
                    {selected.destination ?? "Unknown destination"} · {fmtWhen(selected.created_at)}
                  </Text>
                )}
              </HStack>
              {loadingRun ? (
                <Flex justify="center" py={16}><Spinner size="sm" /></Flex>
              ) : selected ? (
                <VStack align="stretch" gap={4}>
                  <Box bg="bg.surface" borderRadius="2xl" p={5} border="1px solid" borderColor="border.default">
                    <Text fontSize="sm" fontWeight="600" mb={1}>{selected.user_message}</Text>
                    <HStack gap={3} flexWrap="wrap" mt={2}>
                      {[
                        ["Destination", selected.destination ?? "—"],
                        ["Intent", selected.intent ?? "—"],
                        ["Critic", selected.critic_score != null ? `${selected.critic_score}/5` : "—"],
                        ["Revisions", String(selected.revision_count)],
                        ["Total", fmtDuration(selected.duration_ms)],
                      ].map(([label, value]) => (
                        <Box key={label}>
                          <Text fontSize="xs" color="text.muted" textTransform="uppercase" letterSpacing="0.06em">{label}</Text>
                          <Text fontSize="sm" fontWeight="600">{value}</Text>
                        </Box>
                      ))}
                    </HStack>
                    {selected.error && (
                      <Text fontSize="xs" color="red.400" mt={3}>{selected.error}</Text>
                    )}
                  </Box>

                  <VStack align="stretch" gap={0}>
                    {selected.steps.map((s, i) => (
                      <StepRow key={s.seq} step={s} isLast={i === selected.steps.length - 1} />
                    ))}
                  </VStack>
                </VStack>
              ) : (
                <Text fontSize="sm" color="text.secondary">Select a run to see its timeline.</Text>
              )}
            </Box>
          </Flex>
        )}
      </VStack>
    </Box>
  );
}
