"use client";

import { LoaderCircle } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuthGuard } from "@/lib/use-auth-guard";

import { ChatPanel } from "./components/chat-panel";
import { PptPanel } from "./components/ppt-panel";
import { PsdPanel } from "./components/psd-panel";
import { SearchPanel } from "./components/search-panel";
import { SkillPanel } from "./components/skill-panel";

function buildTabs(t: TFunction) {
  return [
    { value: "skills", title: t("page.tabs.skills") },
    { value: "search", title: t("page.tabs.search") },
    { value: "ppt", title: t("pptPanel.title") },
    { value: "psd", title: t("psdPanel.title") },
    { value: "chat", title: t("chatPanel.title") },
  ];
}

export default function DebugPage() {
  const { t } = useTranslation("debug");
  const { isCheckingAuth, session } = useAuthGuard(["admin"]);
  const tabs = buildTabs(t);

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
