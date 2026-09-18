"use client";

import { LoaderCircle } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/lib/i18n";
import { useAuthGuard } from "@/lib/use-auth-guard";

import { ChatPanel } from "./components/chat-panel";
import { PptPanel } from "./components/ppt-panel";
import { PsdPanel } from "./components/psd-panel";
import { SearchPanel } from "./components/search-panel";
import { SkillPanel } from "./components/skill-panel";

export default function DebugPage() {
  const { t } = useI18n();
  const { isCheckingAuth, session } = useAuthGuard(["admin"]);

  const tabs = [
    { value: "skills", title: t.debug.tabSkills },
    { value: "search", title: t.debug.tabSearch },
    { value: "ppt", title: t.debug.tabPpt },
    { value: "psd", title: t.debug.tabPsd },
    { value: "chat", title: t.debug.tabChat },
  ];

  if (isCheckingAuth || !session || session.role !== "admin") {
    return (
      <div className="flex min-h-[calc(100vh-49px)] items-center justify-center">
        <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <Tabs defaultValue="skills" className="mx-auto flex min-h-[calc(100vh-49px)] w-full max-w-[1600px] flex-col gap-4 px-4 pt-3 pb-6 md:px-8">
      <TabsList variant="line" className="w-full">
        {tabs.map(({ value, title }) => (
          <TabsTrigger key={value} value={value}>
            {title}
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent value="skills">
        <SkillPanel />
      </TabsContent>
      <TabsContent value="search" className="min-h-0">
        <SearchPanel />
      </TabsContent>
      <TabsContent value="ppt" className="min-h-0">
        <PptPanel />
      </TabsContent>
      <TabsContent value="psd" className="min-h-0">
        <PsdPanel />
      </TabsContent>
      <TabsContent value="chat" className="min-h-0">
        <ChatPanel />
      </TabsContent>
    </Tabs>
  );
}
