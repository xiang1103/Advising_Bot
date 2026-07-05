/* 
stores the different types for displaying messages at front end 
*/

type Session = {
    id: string; // unique id for the given session (stored in the database)
    title: string;  // title of the session (summarized)
    updatedAt: string;
    summary: string;
  };

type Message = {
id: string;
role: "assistant" | "user";
content: string;
};

export type {Session, Message}; 