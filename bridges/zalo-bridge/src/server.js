import fs from "node:fs/promises";
import path from "node:path";
import { WebSocketServer, WebSocket } from "ws";
import {
  formatInboundMessage,
  parseOutboundMessage,
  parseTypingMessage,
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
    this.currentQrData = null;
    this.currentLoginActions = null;
    this.recentMessages = new Map();
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

      let quote = undefined;
      if (parsed.quote_id) {
        const cached = this.recentMessages.get(String(parsed.quote_id));
        if (cached) {
          quote = {
            content: typeof cached.content === "string" ? cached.content : "",
            msgType: cached.msgType || "webchat",
            propertyExt: cached.propertyExt || {},
            uidFrom: String(cached.uidFrom || cached.fromUid || ""),
            msgId: String(cached.msgId || parsed.quote_id),
            cliMsgId: String(cached.cliMsgId || cached.msgId || parsed.quote_id),
            ts: Number(cached.ts || Date.now()),
            ttl: Number(cached.ttl || 0),
          };
        } else if (threadType === 0) {
          // Direct 1:1 message quote only requires msgId
          quote = { msgId: parsed.quote_id };
        }
      }

      const messagePayload = {
        msg: parsed.text,
      };
      if (quote) {
        messagePayload.quote = quote;
      }
      if (parsed.styles && parsed.styles.length > 0) {
        messagePayload.styles = parsed.styles;
      }

      try {
        await this.zaloApi.sendMessage(
          messagePayload,
          parsed.thread_id,
          threadType
        );
      } catch (err) {
        if (messagePayload.quote) {
          console.warn(
            `[ZaloBridge] Send with quote failed for ${parsed.thread_id}, retrying without quote:`,
            err?.message || err
          );
          delete messagePayload.quote;
          await this.zaloApi.sendMessage(
            messagePayload,
            parsed.thread_id,
            threadType
          );
        } else {
          throw err;
        }
      }
    } else if (data.type === "typing") {
      const parsed = parseTypingMessage(data);
      if (!this.zaloApi) return;
      const threadType = parsed.thread_type === "group" ? 1 : 0;
      try {
        await this.zaloApi.sendTypingEvent(parsed.thread_id, threadType);
      } catch (err) {
        console.debug(`Typing indicator failed for ${parsed.thread_id}:`, err?.message || err);
      }
    } else if (data.type === "start_qr_login") {
      if (this.currentQrData) {
        ws.send(
          JSON.stringify(formatQrEvent("qr_generated", this.currentQrData))
        );
      }
      if (this.loginState !== "logging_in" || data.force) {
        await this.startQrLogin(Boolean(data.force));
      }
    } else if (data.type === "get_status" || data.type === "status") {
      this.sendCurrentStatus(ws);
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

  async startQrLogin(force = false) {
    if (this.loginState === "logging_in" && !force) {
      if (this.currentQrData) {
        this.broadcast(formatQrEvent("qr_generated", this.currentQrData));
      }
      return;
    }
    if (this.currentLoginActions?.abort) {
      try {
        this.currentLoginActions.abort();
      } catch {}
      this.currentLoginActions = null;
    }
    this.loginState = "logging_in";
    this.currentQrData = null;

    try {
      const { Zalo } = await import("zca-js");
      const zalo = new Zalo();

      this.zaloApi = await zalo.loginQR(
        {},
        (event) => {
          this.currentLoginActions = event.actions;
          if (event.type === 0) {
            // QRCodeGenerated
            const rawImage = event.data.image || "";
            const qrDataUrl = rawImage.startsWith("data:image/")
              ? rawImage
              : rawImage
                ? `data:image/png;base64,${rawImage}`
                : "";
            this.currentQrData = {
              qrDataUrl,
              code: event.data.code,
              token: event.data.token,
            };
            this.broadcast(
              formatQrEvent("qr_generated", this.currentQrData)
            );
          } else if (event.type === 1) {
            // QRCodeExpired
            this.currentQrData = null;
            this.currentLoginActions = null;
            this.loginState = "idle";
            this.broadcast(formatQrEvent("qr_expired"));
            event.actions?.abort?.();
          } else if (event.type === 2) {
            // QRCodeScanned
            this.broadcast(
              formatQrEvent("qr_scanned", {
                displayName: event.data.display_name,
                avatar: event.data.avatar,
              })
            );
          } else if (event.type === 3) {
            // QRCodeDeclined
            this.currentQrData = null;
            this.currentLoginActions = null;
            this.loginState = "idle";
            this.broadcast(formatQrEvent("qr_declined"));
            event.actions?.abort?.();
          } else if (event.type === 4) {
            // GotLoginInfo
            this.saveSession(event.data);
          }
        }
      );

      this.bindListener(this.zaloApi);
      this.loginState = "idle";
      this.currentQrData = null;
      this.currentLoginActions = null;
      this.broadcast(
        formatStatus("connected", {
          userId: this.zaloApi.getContext?.()?.uid,
        })
      );
    } catch (err) {
      this.loginState = "idle";
      this.currentQrData = null;
      this.currentLoginActions = null;
      this.broadcast(formatStatus("disconnected", { message: err.message }));
    }
  }

  bindListener(api) {
    if (!api?.listener) return;

    api.listener.on("message", (msg) => {
      if (msg?.data?.msgId) {
        this.recentMessages.set(String(msg.data.msgId), msg.data);
        if (this.recentMessages.size > 1000) {
          const firstKey = this.recentMessages.keys().next().value;
          this.recentMessages.delete(firstKey);
        }
      }
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
