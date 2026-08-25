/* 
stores the different types for displaying messages at front end 
*/


type Thread = {
    id: string; // unique id for the given thread (stored in the database). Start as string because JS can't generate uuid
    title: string;  // title of the thread (summarized)
  };

type Message = {
role: "advising_bot" | "user";
content: string;
pending?: boolean; // assistant bubble awaiting/streaming its first tokens
};

export type {Thread, Message}; 