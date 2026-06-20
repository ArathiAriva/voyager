"use client";

import { Box, Flex, Text, VStack, Icon } from "@chakra-ui/react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { label: "Chat", href: "/chat", icon: "💬" },
  { label: "Trips", href: "/trips", icon: "🗺️" },
  { label: "Memories", href: "/memories", icon: "🧠" },
  { label: "Settings", href: "/settings", icon: "⚙️" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <Box
      as="nav"
      w="64"
      minH="100vh"
      bg="gray.900"
      color="white"
      px={4}
      py={8}
      flexShrink={0}
    >
      <Box mb={10} px={2}>
        <Text fontSize="2xl" fontWeight="bold" letterSpacing="tight">
          ✈️ Voyager
        </Text>
        <Text fontSize="xs" color="gray.400" mt={1}>
          AI Travel Companion
        </Text>
      </Box>

      <VStack align="stretch" gap={1}>
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} style={{ textDecoration: "none" }}>
              <Flex
                align="center"
                gap={3}
                px={3}
                py={2.5}
                borderRadius="md"
                bg={isActive ? "blue.600" : "transparent"}
                color={isActive ? "white" : "gray.300"}
                _hover={{ bg: isActive ? "blue.600" : "gray.700", color: "white" }}
                transition="all 0.15s"
                cursor="pointer"
              >
                <Text fontSize="lg">{item.icon}</Text>
                <Text fontSize="sm" fontWeight={isActive ? "semibold" : "normal"}>
                  {item.label}
                </Text>
              </Flex>
            </Link>
          );
        })}
      </VStack>
    </Box>
  );
}
