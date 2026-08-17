"use client";

import { useMemo, useRef, useState } from "react";
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
import {Thread, Message} from "@/lib/types";
import {initialMessagesByThread, threads} from "@/lib/utils"; 



const createThreadId = () => {
    return crypto.randomUUID(); 
};

const createNewThread = (): Thread => ({
  id: createThreadId(),
  title: "New thread",

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
  const [threadList, setThreadList] = useState<Thread[]>(threads);
  const [messagesByThread, setMessagesByThread] = useState<
    Record<string, Message[]>
  >(initialMessagesByThread);

  // auto set the first thread ID
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);

  // drives the disabled state of the input while a reply is streaming.
  // the ref is the actual guard: setState is batched, so a second keypress in
  // the same tick would still read the stale `false` from isStreaming.
  const [isStreaming, setIsStreaming] = useState(false);
  const streamingRef = useRef(false);

  // define the current thread
  const activeThread = useMemo(
    () =>
      threadList.find((thread) => thread.id === activeThreadId),
    [activeThreadId, threadList],
  );

  const activeMessages = activeThreadId ? messagesByThread[activeThreadId] ?? [] : [];

  const startNewThread = (): Thread => {
    const newThread = createNewThread();

    setThreadList((currentThreads) => [newThread, ...currentThreads]);
    setMessagesByThread((currentMessages) => ({
      ...currentMessages,
      [newThread.id]: [],
    }));
    setActiveThreadId(newThread.id);

    return newThread;
  };

  const handleNewThread = () => {
    startNewThread();
  };

  /**
   * Send question to generate response and store into db
   * @param text - input question from user
   */
  const handleSend = async (text: string) => {
    // avoids double clicking enter when a first response is sent 
    if (streamingRef.current) return;
    streamingRef.current = true;
    setIsStreaming(true);

    const thread = activeThread ?? startNewThread();
    const threadId = thread.id; 
    const isFirstMessage = (messagesByThread[threadId] ?? []).length === 0;

    // retrieve the title. If thread already exists, we pass empty title to avoid updating/checking title 
    const title = isFirstMessage ? text.trim().slice(0,25) : "";  

    // update the title 
    if (isFirstMessage) {
      setThreadList((currentThreads) =>
        currentThreads.map((t)=> (t.id === threadId ? {...t, title}:t)),  // rebuild the object title if it's the same id 
      );
    }

    // position the assistant bubble will occupy once both messages are appended.
    // messages are only ever appended, so this index stays valid for the whole stream.
    const assistantIndex = (messagesByThread[threadId] ?? []).length + 1;

    const userMessage: Message = {
      role: "user",
      content: text,
    };

    // append the user's message plus an empty, pending assistant bubble (the
    // typing dots) so the UI reacts instantly before any tokens arrive.
    const assistantPlaceholder: Message = {
      role: "assistant",
      content: "",
      pending: true,
    };

    setMessagesByThread((currentMessages) => ({
      ...currentMessages,
      [threadId]: [
        ...(currentMessages[threadId] ?? []),
        userMessage,
        assistantPlaceholder,
      ],
    }));

    // apply an update to the pending assistant message (matched by position) in place.
    const updateAssistant = (updater: (message: Message) => Message) => {
      setMessagesByThread((currentMessages) => ({
        ...currentMessages,
        [threadId]: (currentMessages[threadId] ?? []).map((message, index) =>
          index === assistantIndex ? updater(message) : message,
        ),
      }));
    };

    // calling backend function for response back 
    try {
      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          thread_id: threadId,
          thread_title: title, 
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
      console.error("Chat request failed: ", error)
      updateAssistant((message) => ({
        ...message,
        content: message.content 
                  ? message.content + "\n\n_[Response interrupted. Please try again.]_"
                  : "Advising Bot failed to generate response. Please try again!",
        pending: false,
      }));
    } finally {
      // re-enable the input on both the success and failure paths
      streamingRef.current = false;
      setIsStreaming(false);
    }
  };

  return (
    <main className="h-screen w-screen overflow-hidden bg-slate-950">

      <div className="flex h-full w-full overflow-hidden bg-white">
        <aside className="hidden w-[320px] shrink-0 border-r border-slate-800 sidebar-bg px-5 py-6 text-slate-50 md:flex md:flex-col">

          {/* logo — click to return to the home page */}
          <button
            type="button"
            onClick={() => setActiveThreadId(null)}
            className="flex items-center gap-3 rounded-2xl text-left transition hover:opacity-80"
            title="Go to home page"
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-400 text-slate-950">
              <GraduationCap className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm uppercase tracking-[0.3em] text-slate-400">
                Advising Bot
              </p>
            </div>
          </button>


          <button
            className="mt-6 flex items-center justify-center gap-2 rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-slate-100"
            onClick={handleNewThread}
            type="button"
          >
            <Plus className="h-4 w-4" />
            New thread
          </button>

          {/* displays all threads on the left side  */}
          <div className="mt-6 flex-1 overflow-y-auto pr-1">
            <div className="space-y-3">
              {threadList.map((thread) => {
                const isActive = thread.id === activeThreadId;
                return (
                  <button
                    key={thread.id}
                    onClick={() => setActiveThreadId(thread.id)}
                    className={`w-full rounded-3xl border p-4 text-left transition ${
                      isActive
                        ? "border-amber-300 bg-white text-slate-950"
                        : "border-white/10 bg-white/5 text-slate-200 hover:bg-white/10"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-semibold">{thread.title}</p>
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
                {activeThread?.title ?? "New Chat"}
              </h2>
            </div>
          </header>

          {/* main chat display  */}
          <div className="flex-1 overflow-y-auto px-5 py-6 md:px-8">
            <div className="h-full space-y-4">
                {activeMessages.length > 0 ? (
                  activeMessages.map((message, index) => (
                    <div
                      // safe as a key: messages are append-only, never reordered or removed
                      key={index}
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
                        credits. Your first message starts a new thread.
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
            <AIChatInput onSend={handleSend} disabled={isStreaming} />
          </div>

        </section>
      </div>

    </main>
  );
}
