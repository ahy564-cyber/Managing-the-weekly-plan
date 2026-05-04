// This project uses Flask + SQLAlchemy. No Drizzle ORM is used.
// Plain TypeScript types for the Node.js proxy layer only.

export type User = {
  id: string;
  username: string;
  password: string;
};

export type InsertUser = {
  username: string;
  password: string;
};
