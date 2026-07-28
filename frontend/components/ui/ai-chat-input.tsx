"use client";

import * as React from "react";
import { useState, useEffect, useRef } from "react";
import { Mic, Paperclip, Send } from "lucide-react";
import { AnimatePresence, motion, type Variants } from "motion/react";
import { PLACEHOLDERS } from "@/lib/utils";

type AIChatInputProps = {
  onSend: (text: string) => Promise<void>;
};

const AIChatInput = ({ onSend }: AIChatInputProps) => {
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [showPlaceholder, setShowPlaceholder] = useState(true);
  const [isActive, setIsActive] = useState(false);
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
    // remove front and trailing spaces
    const text = inputValue.trimEnd().trimStart();

    if (!text) return;

    // clear the input immediately so it doesn't linger while awaiting the backend
    setInputValue("");
    setIsActive(false);
    await onSend(text);
  };

  return (
    <div className="w-full text-black">
      <motion.div
        ref={wrapperRef}
        className="w-full"
        variants={containerVariants}
        animate="collapsed"
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
        </div>
      </motion.div>
    </div>
  );
};

export { AIChatInput };
