"use client";

import { useState } from "react";
import { Flex } from "@chakra-ui/react";
import { Sidebar } from "@/components/sidebar";
import { UnlockGate } from "@/components/unlock-gate";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <UnlockGate>
      <Flex minH="100vh">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
        <Flex flex={1} direction="column" bg="bg.page" color="text.primary" overflow="auto">
          {children}
        </Flex>
      </Flex>
    </UnlockGate>
  );
}
