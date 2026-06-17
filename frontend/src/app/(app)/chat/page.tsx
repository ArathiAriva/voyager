"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Box, Flex, Text, Input, VStack, HStack, Spinner } from "@chakra-ui/react";
import ReactMarkdown from "react-markdown";
import {
  fetchConversations,
  fetchConversation,
  createConversation,
  sendMessage,
  deleteConversation,
  type ConversationSummary,
  type Message,
} from "@/lib/api";

export default function ChatPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchConversations().then(setConversations).catch(console.error);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const openConversation = useCallback(async (id: string) => {
    setActiveId(id);
    setLoadingConversation(true);
    try {
      const conv = await fetchConversation(id);
      setMessages(conv.messages);
    } catch {
      setMessages([]);
    } finally {
      setLoadingConversation(false);
    }
  }, []);

  async function handleNewChat() {
    const conv = await createConversation();
    setConversations((prev) => [conv, ...prev]);
    setActiveId(conv.id);
    setMessages([]);
  }

  async function handleDelete(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    await deleteConversation(id);
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (activeId === id) {
      setActiveId(null);
      setMessages([]);
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || loading || !activeId) return;

    const optimisticUser: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);
    setInput("");
    setLoading(true);

    try {
      const reply = await sendMessage(activeId, text);
      setMessages((prev) => [...prev, reply]);
      // Update title in sidebar (auto-titled after first message)
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId ? { ...c, title: text.slice(0, 60) + (text.length > 60 ? "…" : ""), updated_at: new Date().toISOString() } : c
        )
      );
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "Something went wrong. Is the backend running?",
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Flex h="100vh">
      {/* Sidebar */}
      <Flex
        direction="column"
        w="260px"
        flexShrink={0}
        borderRight="1px solid"
        borderColor="gray.200"
        bg="gray.50"
      >
        <Box px={3} py={4} borderBottom="1px solid" borderColor="gray.200">
          <Box
            as="button"
            onClick={handleNewChat}
            w="full"
            py={2}
            px={3}
            bg="blue.500"
            color="white"
            borderRadius="lg"
            fontSize="sm"
            fontWeight="medium"
            textAlign="left"
            _hover={{ bg: "blue.600" }}
            display="flex"
            alignItems="center"
            gap={2}
          >
            <Text>+ New chat</Text>
          </Box>
        </Box>

        <VStack flex={1} overflowY="auto" gap={0} align="stretch" py={2}>
          {conversations.length === 0 && (
            <Text fontSize="xs" color="gray.400" px={3} py={2}>
              No conversations yet
            </Text>
          )}
          {conversations.map((conv) => (
            <Box
              key={conv.id}
              px={3}
              py={2}
              cursor="pointer"
              bg={activeId === conv.id ? "blue.50" : "transparent"}
              borderLeft="3px solid"
              borderColor={activeId === conv.id ? "blue.500" : "transparent"}
              _hover={{ bg: activeId === conv.id ? "blue.50" : "gray.100" }}
              onClick={() => openConversation(conv.id)}
              role="group"
              position="relative"
            >
              <Text fontSize="sm" fontWeight={activeId === conv.id ? "medium" : "normal"} color="gray.800" pr={5} overflow="hidden" textOverflow="ellipsis" whiteSpace="nowrap">
                {conv.title}
              </Text>
              <Text fontSize="xs" color="gray.400" mt={0.5}>
                {new Date(conv.updated_at).toLocaleDateString()}
              </Text>
              <Box
                as="button"
                position="absolute"
                right={2}
                top="50%"
                transform="translateY(-50%)"
                opacity={0}
                _groupHover={{ opacity: 1 }}
                onClick={(e: React.MouseEvent) => handleDelete(conv.id, e)}
                color="gray.400"
                _hover={{ color: "red.500" }}
                fontSize="sm"
                lineHeight={1}
              >
                ×
              </Box>
            </Box>
          ))}
        </VStack>
      </Flex>

      {/* Chat area */}
      <Flex direction="column" flex={1} minW={0}>
        <Box px={6} py={4} borderBottom="1px solid" borderColor="gray.200" bg="white">
          <Text fontSize="lg" fontWeight="semibold">
            Chat with Voyager
          </Text>
          <Text fontSize="sm" color="gray.500">
            Your AI travel companion
          </Text>
        </Box>

        <VStack flex={1} overflowY="auto" px={6} py={4} align="stretch" gap={4}>
          {!activeId && (
            <Flex h="full" align="center" justify="center">
              <Box textAlign="center">
                <Text fontSize="2xl" mb={2}>✈️</Text>
                <Text color="gray.500" fontSize="sm">Start a new chat or pick one from the left</Text>
              </Box>
            </Flex>
          )}

          {activeId && loadingConversation && (
            <Flex justify="center" pt={8}>
              <Spinner color="blue.400" />
            </Flex>
          )}

          {activeId && !loadingConversation && messages.length === 0 && (
            <Flex h="full" align="center" justify="center">
              <Box textAlign="center">
                <Text fontSize="2xl" mb={2}>✈️</Text>
                <Text color="gray.500" fontSize="sm">Where are we going? Ask me anything about a destination.</Text>
              </Box>
            </Flex>
          )}

          {messages.map((msg) => (
            <Flex
              key={msg.id}
              justify={msg.role === "user" ? "flex-end" : "flex-start"}
              align="flex-end"
              gap={2}
            >
              {msg.role === "assistant" && (
                <Box
                  w={8}
                  h={8}
                  borderRadius="full"
                  bg="blue.500"
                  display="flex"
                  alignItems="center"
                  justifyContent="center"
                  flexShrink={0}
                >
                  <Text fontSize="sm">✈️</Text>
                </Box>
              )}
              <Box
                maxW="70%"
                px={4}
                py={3}
                borderRadius="xl"
                bg={msg.role === "user" ? "blue.500" : "white"}
                color={msg.role === "user" ? "white" : "gray.800"}
                boxShadow="sm"
                borderBottomRightRadius={msg.role === "user" ? "sm" : "xl"}
                borderBottomLeftRadius={msg.role === "assistant" ? "sm" : "xl"}
              >
                {msg.role === "user" ? (
                  <Text fontSize="sm" lineHeight="tall">
                    {msg.content}
                  </Text>
                ) : (
                  <Box fontSize="sm" lineHeight="tall" className="markdown">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </Box>
                )}
              </Box>
            </Flex>
          ))}

          {loading && (
            <Flex align="flex-end" gap={2}>
              <Box
                w={8}
                h={8}
                borderRadius="full"
                bg="blue.500"
                display="flex"
                alignItems="center"
                justifyContent="center"
                flexShrink={0}
              >
                <Text fontSize="sm">✈️</Text>
              </Box>
              <Box bg="white" px={4} py={3} borderRadius="xl" boxShadow="sm">
                <Spinner size="sm" color="blue.400" />
              </Box>
            </Flex>
          )}

          <div ref={bottomRef} />
        </VStack>

        <Box px={6} py={4} borderTop="1px solid" borderColor="gray.200" bg="white">
          <HStack gap={2}>
            <Input
              placeholder={activeId ? "Ask about a destination, plan a trip…" : "Start a new chat to begin"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              borderRadius="full"
              bg="gray.50"
              disabled={loading || !activeId}
              _focus={{ bg: "white", borderColor: "blue.400" }}
            />
            <Box
              as="button"
              onClick={handleSend}
              bg={loading || !activeId ? "gray.300" : "blue.500"}
              color="white"
              borderRadius="full"
              w={10}
              h={10}
              display="flex"
              alignItems="center"
              justifyContent="center"
              _hover={{ bg: loading || !activeId ? "gray.300" : "blue.600" }}
              flexShrink={0}
              cursor={loading || !activeId ? "not-allowed" : "pointer"}
            >
              ↑
            </Box>
          </HStack>
        </Box>
      </Flex>
    </Flex>
  );
}
