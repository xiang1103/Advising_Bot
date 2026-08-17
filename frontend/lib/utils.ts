/* utility functions used */
import { Thread, Message } from "@/lib/types";
export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}


export const PLACEHOLDERS = [
  "What's my graduation requirement?",
  "What classes to take?",
  "What is the meaning of life?",
  "What is the best class to take?",
  "How to cook a delicious schedule?",
]; 

export const initialMessagesByThread:Record<string, Message[]>= {
  "thread-1": [
    {
      role: "assistant",
      content:
        "I can help map the CSE sequence, identify prerequisite chains, and point to the bulletin source that supports each recommendation.",
    },
    {
      role: "user",
      content: "What should I take before CSE 216?",
    },
  ],
  "thread-2": [
    {
      role: "assistant",
      content:
        "Send me the course code and institution, and I’ll help translate it into the likely advising outcome.",
    },
  ],
  "thread-3": [
    {
      role: "assistant",
      content:
        "Ask about SBC categories, bulletin policies, or graduation requirements and I’ll keep the answer grounded in university sources.",
    },
  ],
}; 

export const threads: Thread[] = [
  {
    id: "thread-1",
    title: "CSE major planning",
  },
  {
    id: "thread-2",
    title: "Transfer credits",
  },
  {
    id: "thread-3",
    title: "General education",
  },
]; 