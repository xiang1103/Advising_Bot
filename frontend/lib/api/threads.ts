// Client-side calls against the backend's /threads routes.
import type { Thread, Message, ConversationBlock } from "@/lib/types";

// hard code the local host url 
const API_BASE_URL = "http://localhost:8000";

/**
fetches all the thread history 
 */
export async function fetchThreads(): Promise<Thread[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/threads`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (!response.ok) {
      console.error(`Failed to retrieve thread history: ${response.status}`);
      return [];
    }

    // the route serialises a JSON array: [{ id, title }, ...]
    return (await response.json()) as Thread[];
  } catch (error) {
    console.error("Thread history request failed: ", error);
    return [];
  }
}

// the backend sends ConversationBlock rows, which carry a db id the UI has no
// use for: streamed messages never have one, so it can't serve as a react key

/**
fetches the conversation history of a single thread.

returns null (not []) when the request fails: an empty array is a legitimate
answer for a thread nobody has written in yet, and the caller caches what it
gets back. Conflating the two would cache a failure and never retry it
 */
export async function fetchThreadMessages(
  threadId: string,
): Promise<Message[] | null> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/threads/${(threadId)}/messages`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
      },
    );

    if (!response.ok) {
      console.error(`Failed to retrieve conversation: ${response.status}`);
      return null;
    }

    const blocks = (await response.json()) as ConversationBlock[];
    return blocks.map(({ role, content }) => ({ role, content }));
  } catch (error) {
    console.error("Conversation request failed: ", error);
    return null;
  }
}
