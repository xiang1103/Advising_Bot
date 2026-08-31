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