import fs from "node:fs/promises";
import path from "node:path";
import { WebSocketServer, WebSocket } from "ws";
import {
  formatInboundMessage,
  parseOutboundMessage,
  formatStatus,
  formatQrEvent,
} from "./protocol.js";

export class ZaloBridgeServer {
  constructor(options = {}) {
    this.port = Number(options.port || process.env.PORT || 3002);
    this.host = options.host || process.env.HOST || "127.0.0.1";
    this.token = options.token || process.env.BRIDGE_TOKEN || "";
    this.sessionPath =
      options.sessionPath || process.env.SESSION_PATH || "./session.json";
    this.wss = null;
    this.clients = new Set();
    this.zaloApi = null;
    this.loginState = "idle";
  }

  async start() {
    this.wss = new WebSocketServer({ host: this.host, port: this.port });

    this.wss.on("connection", (ws) => {
      let authenticated = !this.token;

      ws.on("message", async (raw) => {
        try {
          const data = JSON.parse(raw.toString());

          if (data.type === "auth") {
            if (this.token && data.token !== this.token) {
              ws.send(
                JSON.stringify({ type: "auth_error", message: "Invalid token" })
              );
              ws.close(4401, "Unauthorized");
              return;
            }
            authenticated = true;
            ws.send(JSON.stringify({ type: "auth_ok" }));
            this.sendCurrentStatus(ws);
            return;
          }

          if (!authenticated) {
            ws.send(
              JSON.stringify({
                type: "auth_error",
                message: "Not authenticated",
              })
            );
            ws.close(4401, "Unauthorized");
            return;
          }

          await this.handleClientMessage(ws, data);
        } catch (err) {
          console.error("Error processing client message:", err);
        }
      });

      ws.on("close", () => {
        this.clients.delete(ws);
      });

      this.clients.add(ws);
    });

    console.log(`Zalo Bridge running on ws://${this.host}:${this.port}`);
  }

  sendCurrentStatus(ws) {
    if (this.zaloApi) {
      ws.send(
        JSON.stringify(
          formatStatus("connected", {
            userId: this.zaloApi.getContext?.()?.uid,
          })
        )
      );
    } else {
      ws.send(JSON.stringify(formatStatus("ready_for_login")));
    }
  }

  broadcast(payload) {
    const raw = JSON.stringify(payload);
    for (const ws of this.clients) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(raw);
      }
    }
  }

  async handleClientMessage(ws, data) {
    if (data.type === "send") {
      const parsed = parseOutboundMessage(data);
      if (!this.zaloApi) {
        throw new Error("Zalo API not logged in");
      }
      const threadType = parsed.thread_type === "group" ? 1 : 0;
      await this.zaloApi.sendMessage(
        {
          msg: parsed.text,
          quote: parsed.quote_id ? { msgId: parsed.quote_id } : undefined,
        },
        parsed.thread_id,
        threadType
      );
    } else if (data.type === "start_qr_login") {
      await this.startQrLogin();
    }
  }

  async loadSavedSession() {
    try {
      const raw = await fs.readFile(this.sessionPath, "utf-8");
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  async saveSession(credentials) {
    try {
      await fs.mkdir(path.dirname(path.resolve(this.sessionPath)), {
        recursive: true,
      });
      await fs.writeFile(
        this.sessionPath,
        JSON.stringify(credentials, null, 2),
        "utf-8"
      );
    } catch (err) {
      console.error("Failed to save session:", err);
    }
  }

  async initZalo() {
    try {
      const { Zalo } = await import("zca-js");
      const credentials = await this.loadSavedSession();
      const zalo = new Zalo();

      if (credentials) {
        console.log("Found existing credentials, logging in via cookies...");
        this.zaloApi = await zalo.login(credentials);
        this.bindListener(this.zaloApi);
        this.broadcast(
          formatStatus("connected", {
            userId: this.zaloApi.getContext?.()?.uid,
          })
        );
      } else {
        this.broadcast(formatStatus("ready_for_login"));
      }
    } catch (err) {
      console.error("Failed to initialize Zalo session:", err);
      this.broadcast(formatStatus("disconnected", { message: err.message }));
    }
  }

  async startQrLogin() {
    if (this.loginState === "logging_in") return;
    this.loginState = "logging_in";

    try {
      const { Zalo } = await import("zca-js");
      const zalo = new Zalo();

      this.zaloApi = await zalo.loginQR(
        {},
        (event) => {
          if (event.type === 0) {
            // QRCodeGenerated
            this.broadcast(
              formatQrEvent("qr_generated", {
                qrDataUrl: event.data.image,
                token: event.data.token,
              })
            );
          } else if (event.type === 2) {
            // QRCodeScanned
            this.broadcast(
              formatQrEvent("qr_scanned", {
                displayName: event.data.display_name,
                avatar: event.data.avatar,
              })
            );
          } else if (event.type === 4) {
            // GotLoginInfo
            this.saveSession(event.data);
          }
        }
      );

      this.bindListener(this.zaloApi);
      this.loginState = "idle";
      this.broadcast(
        formatStatus("connected", {
          userId: this.zaloApi.getContext?.()?.uid,
        })
      );
    } catch (err) {
      this.loginState = "idle";
      this.broadcast(formatStatus("disconnected", { message: err.message }));
    }
  }

  bindListener(api) {
    if (!api?.listener) return;

    api.listener.on("message", (msg) => {
      this.broadcast(formatInboundMessage(msg));
    });

    api.listener.on("closed", (code, reason) => {
      if (code === 3000 || code === 3003) {
        this.broadcast(formatStatus("duplicate_connection"));
      } else {
        this.broadcast(formatStatus("disconnected", { message: reason }));
      }
    });

    api.listener.start();
  }

  async stop() {
    for (const ws of this.clients) {
      ws.close();
    }
    this.clients.clear();
    if (this.wss) {
      await new Promise((resolve) => this.wss.close(resolve));
      this.wss = null;
    }
  }
}

// Auto-run if executed directly
if (process.argv[1] === import.meta.filename) {
  const server = new ZaloBridgeServer();
  await server.start();
  await server.initZalo();
}
