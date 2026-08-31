// Client-side calls against the backend's /threads routes.
import type { Thread } from "@/lib/types";

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
