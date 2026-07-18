"use client";

import { useMemo, useState } from "react";
import {
  BookOpen,
  ChevronRight,
  FileText,
  GraduationCap,
  MessagesSquare,
  Plus,
  Search,
  ShieldCheck,
} from "lucide-react";
import { AIChatInput } from "@/components/ui/ai-chat-input";
import { MarkdownMessage } from "@/components/ui/markdown-message";
import {Session, Message} from "@/lib/types";

const sessions: Session[] = [
  {
    id: "session-1",
    title: "CSE major planning",
    updatedAt: "2m ago",
    summary: "Prereqs, electives, and next steps for the CS track.",
  },
  {
    id: "session-2",
    title: "Transfer credits",
    updatedAt: "18m ago",
    summary: "How outside courses map to SBC requirements.",
  },
  {
    id: "session-3",
    title: "General education",
    updatedAt: "Yesterday",
    summary: "HUM, SNW, and SBC learning goal questions.",
  },
];

const initialMessagesBySession: Record<string, Message[]> = {
  "session-1": [
    {
      id: "m1",
      role: "assistant",
      content:
        "I can help map the CSE sequence, identify prerequisite chains, and point to the bulletin source that supports each recommendation.",
    },
    {
      id: "m2",
      role: "user",
      content: "What should I take before CSE 216?",
    },
  ],
  "session-2": [
    {
      id: "m1",
      role: "assistant",
      content:
        "Send me the course code and institution, and I’ll help translate it into the likely advising outcome.",
    },
  ],
  "session-3": [
    {
      id: "m1",
      role: "assistant",
      content:
        "Ask about SBC categories, bulletin policies, or graduation requirements and I’ll keep the answer grounded in university sources.",
    },
  ],
};

const createSessionId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `session-${crypto.randomUUID()}`;
  }

  return `session-${Date.now()}`;
};

const createNewSession = (): Session => ({
  id: createSessionId(),
  title: "New session",
  updatedAt: "Just now",
  summary: "Start a new advising conversation.",
});

// three jumping dots shown inside an assistant bubble while awaiting the first tokens
const TypingDots = () => (
  <div className="flex items-center gap-1 py-1">
    <span className="typing-dot" style={{ animationDelay: "0ms" }} />
    <span className="typing-dot" style={{ animationDelay: "150ms" }} />
    <span className="typing-dot" style={{ animationDelay: "300ms" }} />
  </div>
);

export default function Page() {
  // hard coded variables for starters
  const [sessionList, setSessionList] = useState<Session[]>(sessions);
  const [messagesBySession, setMessagesBySession] = useState<
    Record<string, Message[]>
  >(initialMessagesBySession);

  // auto set the first session ID
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // define the current session
  const activeSession = useMemo(
    () =>
      sessionList.find((session) => session.id === activeSessionId),
    [activeSessionId, sessionList],
  );

  const activeMessages = activeSessionId ? messagesBySession[activeSessionId] ?? [] : [];

  const startNewSession = (): Session => {
    const newSession = createNewSession();

    setSessionList((currentSessions) => [newSession, ...currentSessions]);
    setMessagesBySession((currentMessages) => ({
      ...currentMessages,
      [newSession.id]: [],
    }));
    setActiveSessionId(newSession.id);

    return newSession;
  };

  const handleNewSession = () => {
    startNewSession();
  };

  /**
   * Send question to generate response and store into db
   * @param text - input question from user
   */
  const handleSend = async (text: string) => {
    const sessionId = activeSessionId ?? startNewSession().id;
    const isFirstMessage = (messagesBySession[sessionId] ?? []).length === 0;

    if (isFirstMessage) {
      setSessionList((currentSessions) =>
        currentSessions.map((session) =>
          session.id === sessionId
            ? { ...session, title: text.trim().slice(0, 25) }
            : session,
        ),
      );
    }

    const assistantId = `${Date.now()}-assistant`;

    const userMessage: Message = {
      id: `${Date.now()}-user`,
      role: "user",
      content: text,
    };

    // append the user's message plus an empty, pending assistant bubble (the
    // typing dots) so the UI reacts instantly before any tokens arrive.
    const assistantPlaceholder: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      pending: true,
    };

    setMessagesBySession((currentMessages) => ({
      ...currentMessages,
      [sessionId]: [
        ...(currentMessages[sessionId] ?? []),
        userMessage,
        assistantPlaceholder,
      ],
    }));

    // apply an update to the pending assistant message (matched by id) in place.
    const updateAssistant = (updater: (message: Message) => Message) => {
      setMessagesBySession((currentMessages) => ({
        ...currentMessages,
        [sessionId]: (currentMessages[sessionId] ?? []).map((message) =>
          message.id === assistantId ? updater(message) : message,
        ),
      }));
    };

    try {
      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId,
          message: text,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error("Failed to get a response from the backend");
      }

      // stream the reply, appending each chunk into the assistant bubble.
      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        if (!chunk) continue;

        updateAssistant((message) => ({
          ...message,
          content: message.content + chunk,
          pending: false,
        }));
      }

      // clear the pending flag in case the stream produced zero chunks.
      updateAssistant((message) => ({ ...message, pending: false }));
    } catch (error) {
      updateAssistant((message) => ({
        ...message,
        content: "Advising Bot failed to generate response. Please try again!",
        pending: false,
      }));
    }
  };

  return (
    <main className="h-screen w-screen overflow-hidden bg-slate-950">

      <div className="flex h-full w-full overflow-hidden bg-white">
        <aside className="hidden w-[320px] shrink-0 border-r border-slate-800 sidebar-bg px-5 py-6 text-slate-50 md:flex md:flex-col">

          {/* create the side bar on the side */}
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-400 text-slate-950">
              <GraduationCap className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm uppercase tracking-[0.3em] text-slate-400">
                Advising Bot
              </p>
            </div>
          </div>


          <button
            className="mt-6 flex items-center justify-center gap-2 rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-slate-100"
            onClick={handleNewSession}
            type="button"
          >
            <Plus className="h-4 w-4" />
            New session
          </button>

          {/* displays all sessions on the left side  */}
          <div className="mt-6 flex-1 overflow-y-auto pr-1">
            <div className="space-y-3">
              {sessionList.map((session) => {
                const isActive = session.id === activeSessionId;
                return (
                  <button
                    key={session.id}
                    onClick={() => setActiveSessionId(session.id)}
                    className={`w-full rounded-3xl border p-4 text-left transition ${
                      isActive
                        ? "border-amber-300 bg-white text-slate-950"
                        : "border-white/10 bg-white/5 text-slate-200 hover:bg-white/10"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-semibold">{session.title}</p>
                      </div>
                      <ChevronRight className="h-4 w-4 shrink-0 opacity-70" />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </aside>

        <section className="flex min-w-0 flex-1 flex-col bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.92))]">

          {/* Header of the page  */}
          <header className="flex items-center justify-center border-b border-slate-200/80 px-5 py-4 md:px-8">
            <div>
              <h2 className="mt-1 text-2xl  text-slate-950 text-center">
                {activeSession?.title ?? "New Chat"}
              </h2>
            </div>
          </header>

          {/* main chat display  */}
          <div className="flex-1 overflow-y-auto px-5 py-6 md:px-8">
            <div className="h-full space-y-4">
                {activeMessages.length > 0 ? (
                  activeMessages.map((message) => (
                    <div
                      key={message.id}
                      className={`flex ${
                        message.role === "assistant"
                          ? "justify-start"
                          : "justify-end"
                      }`}
                    >
                      <div
                        className={`rounded-3xl border px-5 py-4 text-sm leading-6 shadow-sm break-words ${
                          message.role === "assistant"
                            ? "max-w-xl border-slate-200 bg-white text-slate-800"
                            : "max-w-2xl border-slate-950 user-response-bg text-white"
                        }`}
                      >
                        <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.05em] opacity-60">
                          {message.role === "assistant" ? (
                            <BookOpen className="h-3.5 w-3.5" />
                          ) : (
                            <FileText className="h-3.5 w-3.5" />
                          )}
                          {message.role === "assistant"
                            ? "Advising Bot"
                            : message.role}
                        </div>
                        {message.role === "assistant" ? (
                          message.pending && message.content === "" ? (
                            <TypingDots />
                          ) : (
                            <MarkdownMessage content={message.content} />
                          )
                        ) : (
                          message.content
                        )}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
                    <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-400 text-slate-950">
                      <MessagesSquare className="h-6 w-6" />
                    </div>
                    <div>
                      <h3 className="text-xl font-semibold text-slate-950">
                        Welcome to Advising Bot
                      </h3>
                      <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
                        Ask about course prerequisites, degree progress, or transfer
                        credits. Your first message starts a new session.
                      </p>
                    </div>
                  </div>
                )}
            </div>
          </div>

          {/* topic suggestions for chat  */}
          <div className="border-t border-slate-200/80 px-5 pt-5 pb-8 md:px-8">
            <div className="mb-4 flex flex-wrap gap-2 text-xs text-slate-500">
              <span className="rounded-full bg-slate-100 px-3 py-1">
                Course prereqs
              </span>
              <span className="rounded-full bg-slate-100 px-3 py-1">
                Degree progress
              </span>
              <span className="rounded-full bg-slate-100 px-3 py-1">
                Transfer credit
              </span>
              <span className="rounded-full bg-slate-100 px-3 py-1">
                SBC advice
              </span>
            </div>
            <AIChatInput onSend={handleSend} />
          </div>

        </section>
      </div>

    </main>
  );
}
