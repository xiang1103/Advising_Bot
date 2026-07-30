/* 
stores the different types for displaying messages at front end 
*/

type Thread = {
    id: string; // unique id for the given thread (stored in the database)
    title: string;  // title of the thread (summarized)
    updatedAt: string;
    summary: string;
  };

type Message = {
id: string;
role: "assistant" | "user";
content: string;
pending?: boolean; // assistant bubble awaiting/streaming its first tokens
};

export type {Thread, Message}; 