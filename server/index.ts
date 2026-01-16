import { spawn } from "child_process";

console.log("Starting Python Flask app...");

// Spawn the python process
const pythonProcess = spawn("python3", ["main.py"], { stdio: "inherit" });

pythonProcess.on("close", (code) => {
  console.log(`Python process exited with code ${code}`);
  process.exit(code ?? 0);
});

// Handle termination signals
process.on("SIGTERM", () => {
  pythonProcess.kill("SIGTERM");
});

process.on("SIGINT", () => {
  pythonProcess.kill("SIGINT");
});
