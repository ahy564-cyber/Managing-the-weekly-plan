import { spawn } from "child_process";
import { createServer, request as httpRequest, IncomingMessage, ServerResponse } from "http";

const FLASK_PORT = 5001;

console.log("Starting Python Flask app...");

const pythonProcess = spawn("python3", ["main.py"], {
  stdio: "inherit",
  env: { ...process.env, FLASK_PORT: String(FLASK_PORT), PYTHONUNBUFFERED: "1" },
});

pythonProcess.on("close", (code) => {
  console.log(`Python process exited with code ${code}`);
  process.exit(code ?? 0);
});

process.on("SIGTERM", () => {
  pythonProcess.kill("SIGTERM");
});

process.on("SIGINT", () => {
  pythonProcess.kill("SIGINT");
});

function proxyRequest(clientReq: IncomingMessage, clientRes: ServerResponse) {
  const options = {
    hostname: "127.0.0.1",
    port: FLASK_PORT,
    path: clientReq.url,
    method: clientReq.method,
    headers: clientReq.headers,
  };

  const proxyReq = httpRequest(options, (proxyRes) => {
    clientRes.writeHead(proxyRes.statusCode || 500, proxyRes.headers);
    proxyRes.pipe(clientRes, { end: true });
  });

  proxyReq.on("error", () => {
    clientRes.writeHead(200);
    clientRes.end("<html><body><h1>Starting up...</h1><script>setTimeout(()=>location.reload(),2000)</script></body></html>");
  });

  clientReq.pipe(proxyReq, { end: true });
}

const server = createServer(proxyRequest);

server.listen(5000, "0.0.0.0", () => {
  console.log(`Proxy listening on http://0.0.0.0:5000`);
});
