"use client";

import { useEffect, useState, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { request } from "@/lib/request";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const mdComponents = {
  p: (props: any) => <p className="my-1" {...props} />,
  ul: (props: any) => <ul className="list-disc ml-5 my-1 space-y-0.5" {...props} />,
  ol: (props: any) => <ol className="list-decimal ml-5 my-1 space-y-0.5" {...props} />,
  li: (props: any) => <li className="leading-relaxed" {...props} />,
  strong: (props: any) => <strong className="font-semibold" {...props} />,
  em: (props: any) => <em className="italic" {...props} />,
  code: ({ inline, ...props }: any) =>
    inline ? (
      <code className="px-1 py-0.5 rounded bg-background/60 text-[0.9em]" {...props} />
    ) : (
      <code className="block p-2 rounded bg-background/60 text-[0.9em] overflow-x-auto" {...props} />
    ),
  pre: (props: any) => <pre className="my-2 rounded bg-background/60 overflow-x-auto" {...props} />,
  h1: (props: any) => <h2 className="text-base font-bold mt-2 mb-1" {...props} />,
  h2: (props: any) => <h3 className="text-sm font-bold mt-2 mb-1" {...props} />,
  h3: (props: any) => <h4 className="text-sm font-semibold mt-1 mb-1" {...props} />,
  blockquote: (props: any) => <blockquote className="border-l-2 pl-3 my-1 opacity-80" {...props} />,
  table: (props: any) => <table className="border-collapse my-2 text-xs" {...props} />,
  th: (props: any) => <th className="border px-2 py-1 bg-background/40 font-semibold" {...props} />,
  td: (props: any) => <td className="border px-2 py-1" {...props} />,
  a: (props: any) => <a className="underline text-primary" target="_blank" rel="noreferrer" {...props} />,
};

type Message = {
  role: "user" | "assistant";
  content: string;
  ttft?: number;      // time-to-first-token (ms)
  duration?: number;  // total time (ms)
};

export default function ChatPage() {
  const { isCheckingAuth } = useAuthGuard(["admin"]);
  const [models, setModels] = useState<{ id: string }[]>([]);
  const [model, setModel] = useState("AI Agent");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [elapsed, setElapsed] = useState(0); // ms, live counter while streaming
  const bottomRef = useRef<HTMLDivElement>(null);
  const startTimeRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    request.get("/v1/models").then((d: any) => {
      const list = d.data?.data || d.data || [];
      setModels(list.map((m: any) => ({ id: m.id })));
    }).catch(() => {});
  }, []);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // Live timer while streaming
  useEffect(() => {
    if (streaming) {
      setElapsed(0);
      timerRef.current = setInterval(() => {
        setElapsed(Date.now() - startTimeRef.current);
      }, 100);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [streaming]);

  const send = async () => {
    if (!input.trim() || streaming) return;
    const userMsg = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: userMsg }]);
    setStreaming(true);
    startTimeRef.current = Date.now();

    try {
      const { getStoredAuthKey } = await import("@/store/auth");
      let authKey = await getStoredAuthKey();
      if (!authKey) {
        try { authKey = localStorage.getItem("chatgpt2api_auth_key") || ""; } catch(e) {}
      }
      console.log("Chat: authKey available:", !!authKey, "length:", authKey.length);
      if (!authKey) {
        setMessages(prev => [...prev, { role: "assistant", content: "Lỗi: Chưa đăng nhập. Vui lòng refresh trang và đăng nhập lại." }]);
        setStreaming(false);
        return;
      }
      const resp = await fetch("/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": authKey ? `Bearer ${authKey}` : "" },
        body: JSON.stringify({
          model, stream: true,
          messages: [...messages, { role: "user", content: userMsg }].map(m => ({ role: m.role, content: m.content })),
        }),
      });

      const reader = resp.body?.getReader();
      if (!reader) { setStreaming(false); return; }

      let assistantContent = "";
      let ttft: number | undefined;
      setMessages(prev => [...prev, { role: "assistant", content: "" }]);

      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value);
        const lines = text.split("\n").filter(l => l.startsWith("data: "));
        for (const line of lines) {
          const data = line.slice(6);
          if (data === "[DONE]") continue;
          try {
            const json = JSON.parse(data);
            const delta = json.choices?.[0]?.delta?.content;
            if (delta) {
              if (ttft === undefined) ttft = Date.now() - startTimeRef.current;
              assistantContent += delta;
              setMessages(prev => {
                const copy = [...prev];
                copy[copy.length - 1] = { role: "assistant", content: assistantContent };
                return copy;
              });
            }
          } catch (e) {}
        }
      }

      // Stamp final timing on last message
      const totalMs = Date.now() - startTimeRef.current;
      setMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1] = { role: "assistant", content: assistantContent, ttft, duration: totalMs };
        return copy;
      });

    } catch (e) {
      setMessages(prev => [...prev, { role: "assistant", content: "Lỗi kết nối." }]);
    }
    setStreaming(false);
  };

  if (isCheckingAuth) return <div className="p-6 text-muted-foreground">Đang tải...</div>;

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] p-4 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-lg font-bold">Chat</h1>
        <select value={model} onChange={e => setModel(e.target.value)}
          className="px-3 py-1.5 rounded-lg border bg-background text-sm">
          {models.map(m => <option key={m.id} value={m.id}>{m.id}</option>)}
        </select>
        <Button variant="outline" size="sm" onClick={() => setMessages([])}>Xóa</Button>
        {streaming && (
          <span className="ml-auto text-xs text-muted-foreground tabular-nums animate-pulse">
            ⏱ {(elapsed / 1000).toFixed(1)}s...
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 mb-4">
        {messages.length === 0 && (
          <div className="text-center text-muted-foreground mt-20">
            Chọn model, nhập câu hỏi để test MCP + search.
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
            <div className={`max-w-[80%] px-4 py-2 rounded-xl ${
              m.role === "user"
                ? "bg-primary text-primary-foreground whitespace-pre-wrap"
                : "bg-muted text-foreground"
            }`}>
              {m.role === "assistant" ? (
                m.content ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                    {m.content}
                  </ReactMarkdown>
                ) : (
                  streaming && i === messages.length - 1 ? "▊" : ""
                )
              ) : (
                m.content
              )}
            </div>
            {m.role === "assistant" && m.duration !== undefined && (
              <div className="flex gap-2 mt-1 px-1 text-[11px] text-muted-foreground/60">
                <span title="Tổng thời gian phản hồi">⏱ {(m.duration / 1000).toFixed(2)}s</span>
                {m.ttft !== undefined && (
                  <span title="Thời gian đến chữ đầu tiên (TTFT)">⚡ TTFT {(m.ttft / 1000).toFixed(2)}s</span>
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="flex gap-2">
        <Input value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && send()}
          placeholder="Hỏi gì đó..." disabled={streaming} />
        <Button onClick={send} disabled={streaming || !input.trim()}>
          {streaming ? "..." : "Gửi"}
        </Button>
      </div>
    </div>
  );
}
