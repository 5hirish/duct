"use client";

import { useEffect, useRef, useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
import { streamInsightChat } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { useInsightContext } from "./InsightContext";

export default function ChatSidebar() {
  const { t } = useLingui();
  const { chatPayload } = useInsightContext();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit(event) {
    event.preventDefault();
    const userMessage = input.trim();
    if (!userMessage || streaming || !chatPayload) return;

    setInput("");
    setError(null);

    const history = [...messages];
    const nextMessages = [...history, { role: "user", content: userMessage }];
    setMessages([...nextMessages, { role: "assistant", content: "" }]);
    setStreaming(true);

    await streamInsightChat({
      chatPayload,
      messages: history,
      message: userMessage,
      onToken: (token) => {
        setMessages((prev) => {
          if (!prev.length) return prev;
          const updated = [...prev];
          const lastIndex = updated.length - 1;
          updated[lastIndex] = {
            role: "assistant",
            content: `${updated[lastIndex].content}${token}`,
          };
          return updated;
        });
      },
      onDone: () => setStreaming(false),
      onError: (msg) => {
        setError(msg);
        setStreaming(false);
        setMessages((prev) => {
          if (!prev.length) return prev;
          const last = prev[prev.length - 1];
          if (last.role === "assistant" && !last.content.trim()) {
            return prev.slice(0, -1);
          }
          return prev;
        });
      },
    });
  }

  if (!chatPayload) return null;

  const accountName = chatPayload.account?.name || t`your account`;
  return (
    <div className="chat-sidebar">
      <div className="chat-sidebar-header">
        <p className="chat-sidebar-title"><Trans>Ask about this insight</Trans></p>
        <p className="app-subtle chat-sidebar-hint">
          <Trans>Grounded in the data from {accountName}</Trans>
        </p>
      </div>

      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <p className="app-subtle">
              <Trans>
                Ask a question about the data, like &quot;Which campaign wastes the most spend?&quot; or
                &quot;Why is CPA high on mobile?&quot;
              </Trans>
            </p>
          </div>
        ) : null}
        {messages.map((msg, index) => (
          <div key={`${msg.role}-${index}`} className={`chat-message chat-message--${msg.role}`}>
            <p className="chat-message-content">{msg.content}</p>
          </div>
        ))}
        {error ? <p className="chat-error app-subtle"><Trans>Error: {error}</Trans></p> : null}
        <div ref={bottomRef} />
      </div>

      <form className="chat-input-row" onSubmit={handleSubmit}>
        <Input
          className="flex-1"
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={t`Ask a question...`}
          disabled={streaming}
          autoComplete="off"
        />
        <Button
          type="submit"
          size="sm"
          className="rounded-3xl px-4"
          disabled={streaming || !input.trim()}
        >
          {streaming ? "..." : t`Send`}
        </Button>
      </form>
    </div>
  );
}
