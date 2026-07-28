/* utility functions used */
import { Session, Message } from "@/lib/types";
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

export const initialMessagesBySession:Record<string, Message[]>= {
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

export const sessions: Session[] = [
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