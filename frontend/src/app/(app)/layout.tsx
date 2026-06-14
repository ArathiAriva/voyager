import { Flex } from "@chakra-ui/react";
import { Sidebar } from "@/components/sidebar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Flex minH="100vh">
      <Sidebar />
      <Flex flex={1} direction="column" bg="gray.50" overflow="auto">
        {children}
      </Flex>
    </Flex>
  );
}
