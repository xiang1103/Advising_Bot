"use client";

import * as React from "react";
import { useState, useEffect, useRef } from "react";
import { Lightbulb, Mic, Globe, Paperclip, Send } from "lucide-react";
import { AnimatePresence, motion, type Variants } from "motion/react";

const PLACEHOLDERS = [
  "Generate a course schedule",
  "Create a new project with Next.js",
  "What is the meaning of life?",
  "What is the best class to take?",
  "How to cook a delicious schedule?",
];

type AIChatInputProps = {
  onSend: (text: string) => Promise<void>;
};

const AIChatInput = ({ onSend }: AIChatInputProps) => {
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [showPlaceholder, setShowPlaceholder] = useState(true);
  const [isActive, setIsActive] = useState(false);
  const [thinkActive, setThinkActive] = useState(false);
  const [deepSearchActive, setDeepSearchActive] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isActive || inputValue) return;

    const interval = setInterval(() => {
      setShowPlaceholder(false);
      setTimeout(() => {
        setPlaceholderIndex((prev) => (prev + 1) % PLACEHOLDERS.length);
        setShowPlaceholder(true);
      }, 400);
    }, 3000);

    return () => clearInterval(interval);
  }, [isActive, inputValue]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(event.target as Node)
      ) {
        if (!inputValue) setIsActive(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [inputValue]);

  const handleActivate = () => setIsActive(true);

  const containerVariants: Variants = {
    collapsed: {
      height: 68,
      boxShadow: "none",
      transition: { type: "spring" as const, stiffness: 120, damping: 18 },
    },
    expanded: {
      height: 128,
      boxShadow: "none",
      transition: { type: "spring" as const, stiffness: 120, damping: 18 },
    },
  };

  const placeholderContainerVariants = {
    initial: {},
    animate: { transition: { staggerChildren: 0.025 } },
    exit: { transition: { staggerChildren: 0.015, staggerDirection: -1 } },
  };

  const letterVariants: Variants = {
    initial: {
      opacity: 0,
      filter: "blur(12px)",
      y: 10,
    },
    animate: {
      opacity: 1,
      filter: "blur(0px)",
      y: 0,
      transition: {
        opacity: { duration: 0.25 },
        filter: { duration: 0.4 },
        y: { type: "spring" as const, stiffness: 80, damping: 20 },
      },
    },
    exit: {
      opacity: 0,
      filter: "blur(12px)",
      y: -10,
      transition: {
        opacity: { duration: 0.2 },
        filter: { duration: 0.3 },
        y: { type: "spring" as const, stiffness: 80, damping: 20 },
      },
    },
  };

  const handleSend = async () => {
    const text = inputValue.trim();

    if (!text) return;

    await onSend(text);
    setInputValue("");
    setIsActive(false);
  };

  return (
    <div className="w-full text-black">
      <motion.div
        ref={wrapperRef}
        className="w-full"
        variants={containerVariants}
        animate={isActive || inputValue ? "expanded" : "collapsed"}
        initial="collapsed"
        style={{
          overflow: "hidden",
          borderRadius: 0,
          background: "transparent",
        }}
        onClick={handleActivate}
        onSubmit={handleSend}
      >
        <div className="flex h-full w-full flex-col items-stretch">
          <div className="flex w-full items-center gap-2 border border-slate-200 bg-white px-3 py-3">
            <button
              className="rounded-full p-3 transition hover:bg-gray-100"
              title="Attach file"
              type="button"
              tabIndex={-1}
            >
              <Paperclip size={20} />
            </button>

            <div className="relative flex-1">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                className="w-full rounded-md border-0 bg-transparent py-2 text-base font-normal outline-none focus:outline-none focus:ring-0"
                style={{ position: "relative", zIndex: 1 }}
                onFocus={handleActivate}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                  e.preventDefault();
                  void handleSend();
                  }
                }}
              />
              <div className="pointer-events-none absolute left-0 top-0 flex h-full w-full items-center px-3 py-2">
                <AnimatePresence mode="wait">
                  {showPlaceholder && !isActive && !inputValue && (
                    <motion.span
                      key={placeholderIndex}
                      className="pointer-events-none absolute left-0 top-1/2 -translate-y-1/2 select-none text-gray-400"
                      style={{
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        zIndex: 0,
                      }}
                      variants={placeholderContainerVariants}
                      initial="initial"
                      animate="animate"
                      exit="exit"
                    >
                      {PLACEHOLDERS[placeholderIndex]
                        .split("")
                        .map((char, i) => (
                          <motion.span
                            key={i}
                            variants={letterVariants}
                            style={{ display: "inline-block" }}
                          >
                            {char === " " ? "\u00A0" : char}
                          </motion.span>
                        ))}
                    </motion.span>
                  )}
                </AnimatePresence>
              </div>
            </div>

            <button
              className="rounded-full p-3 transition hover:bg-gray-100"
              title="Voice input"
              type="button"
              tabIndex={-1}
            >
              <Mic size={20} />
            </button>
            <button
              className="flex items-center justify-center rounded-full bg-black p-3 font-medium text-white transition hover:bg-zinc-700"
              title="Send"
              type="button"
              tabIndex={-1}
              onClick={() => {
                void handleSend();
              }}
            >
              <Send size={18} />
            </button>
          </div>

          <motion.div
            className="flex w-full items-center justify-start px-4 text-sm"
            variants={{
              hidden: {
                opacity: 0,
                y: 20,
                pointerEvents: "none" as const,
                transition: { duration: 0.25 },
              },
              visible: {
                opacity: 1,
                y: 0,
                pointerEvents: "auto" as const,
                transition: { duration: 0.35, delay: 0.08 },
              },
            }}
            initial="hidden"
            animate={isActive || inputValue ? "visible" : "hidden"}
            style={{ marginTop: 8 }}
          >
            <div className="flex items-center gap-3">
              <button
                className={`group flex items-center gap-1 rounded-full px-4 py-2 font-medium transition-all ${
                  thinkActive
                    ? "bg-blue-600/10 outline outline-blue-600/60 text-blue-950"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
                title="Think"
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setThinkActive((a) => !a);
                }}
              >
                <Lightbulb
                  className="transition-all group-hover:fill-yellow-300"
                  size={18}
                />
                Think
              </button>

              <motion.button
                className={`flex items-center justify-start overflow-hidden whitespace-nowrap rounded-full py-2 pl-[9px] pr-4 font-medium transition ${
                  deepSearchActive
                    ? "bg-blue-600/10 outline outline-blue-600/60 text-blue-950"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
                title="Deep Search"
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setDeepSearchActive((a) => !a);
                }}
                initial={false}
                animate={{
                  width: deepSearchActive ? 125 : 36,
                  paddingLeft: deepSearchActive ? 8 : 9,
                }}
              >
                <div className="flex-1">
                  <Globe size={18} />
                </div>
                <motion.span
                  className="pb-[2px]"
                  initial={false}
                  animate={{
                    opacity: deepSearchActive ? 1 : 0,
                  }}
                >
                  Deep Search
                </motion.span>
              </motion.button>
            </div>
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
};

export { AIChatInput };
