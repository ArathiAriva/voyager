"use client";

import { Box, Flex, Text, VStack } from "@chakra-ui/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ChatIcon, MapIcon, BrainIcon, ChartIcon, TraceIcon, SettingsIcon, CompassIcon, SearchIcon,
} from "@/components/icons";

const navItems = [
  { label: "Chats", href: "/chats", Icon: ChatIcon },
  { label: "Trips", href: "/trips", Icon: MapIcon },
  { label: "Memories", href: "/memories", Icon: BrainIcon },
  { label: "Usage", href: "/usage", Icon: ChartIcon },
  { label: "Retrieval", href: "/retrieval", Icon: SearchIcon },
  { label: "Traces", href: "/planning", Icon: TraceIcon },
  { label: "Settings", href: "/settings", Icon: SettingsIcon },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();

  return (
    <Box
      as="nav"
      w={collapsed ? "16" : "72"}
      bg="bg.subtle"
      color="text.primary"
      py={10}
      flexShrink={0}
      borderRight="1px solid"
      borderColor="border.default"
      display="flex"
      flexDirection="column"
      transition="width 0.22s cubic-bezier(0.4,0,0.2,1)"
      overflow="hidden"
      position="sticky"
      top={0}
      h="100vh"
      alignSelf="flex-start"
    >
      {/* Logo + toggle.
          Collapsed, this stacks: the compass sits on the nav icons' centre line and
          the toggle goes directly beneath it. Side by side, the two squeeze into the
          64px rail and neither lands on the axis the nav icons share below. */}
      <Box
        mb={10}
        px={collapsed ? 0 : 6}
        display="flex"
        flexDirection={collapsed ? "column" : "row"}
        alignItems="center"
        gap={collapsed ? 3 : 0}
        justifyContent={collapsed ? "center" : "space-between"}
      >
        {!collapsed && (
          <Box>
            <Text fontSize="xl" fontWeight="800" letterSpacing="-0.04em" lineHeight="1" whiteSpace="nowrap">
              Voyager
            </Text>
            <Text fontSize="xs" color="text.dim" mt={1.5} letterSpacing="0.08em" textTransform="uppercase" fontWeight="500" whiteSpace="nowrap">
              AI Travel Companion
            </Text>
          </Box>
        )}

        {collapsed && (
          <Box color="text.bright"><CompassIcon size={22} /></Box>
        )}

        <Box
          as="button"
          onClick={onToggle}
          ml={collapsed ? 0 : 2}
          w={7}
          h={7}
          display="flex"
          alignItems="center"
          justifyContent="center"
          borderRadius="md"
          color="text.dim"
          _hover={{ color: "text.bright", bg: "bg.muted" }}
          transition="all 0.15s"
          flexShrink={0}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          >
            {collapsed ? (
              /* right-pointing chevrons (expand) */
              <>
                <polyline points="5,3 10,8 5,13" />
                <polyline points="9,3 14,8 9,13" />
              </>
            ) : (
              /* left-pointing chevrons (collapse) */
              <>
                <polyline points="11,3 6,8 11,13" />
                <polyline points="7,3 2,8 7,13" />
              </>
            )}
          </svg>
        </Box>
      </Box>

      {/* Nav */}
      <VStack align="stretch" gap={0} flex={1}>
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} style={{ textDecoration: "none" }}>
              <Flex
                align="center"
                gap={collapsed ? 0 : 3}
                px={collapsed ? 0 : 4}
                py={3.5}
                position="relative"
                justifyContent={collapsed ? "center" : "flex-start"}
                borderLeft={collapsed ? "none" : "2px solid"}
                borderColor={!collapsed && isActive ? "accent.active" : "transparent"}
                color={isActive ? "text.bright" : "text.dim"}
                _hover={{ color: "text.bright", borderColor: collapsed ? "transparent" : "border.muted" }}
                transition="all 0.15s"
                cursor="pointer"
                title={collapsed ? item.label : undefined}
              >
                {/* Active indicator for collapsed mode */}
                {collapsed && isActive && (
                  <Box
                    position="absolute"
                    left={0}
                    top="50%"
                    transform="translateY(-50%)"
                    w="2px"
                    h="60%"
                    bg="accent.active"
                    borderRadius="full"
                  />
                )}
                <Box display="flex" alignItems="center" flexShrink={0}><item.Icon /></Box>
                {!collapsed && (
                  <Text
                    fontSize="sm"
                    fontWeight={isActive ? "700" : "400"}
                    letterSpacing={isActive ? "-0.01em" : "0"}
                    whiteSpace="nowrap"
                  >
                    {item.label}
                  </Text>
                )}
              </Flex>
            </Link>
          );
        })}
      </VStack>
    </Box>
  );
}
