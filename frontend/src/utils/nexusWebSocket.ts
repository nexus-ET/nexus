import { getStoredToken, resolveWebSocketUrl } from './api';

export interface NexusSocketHandle {
  close: () => void;
  send: (payload: unknown) => void;
  readonly socket: WebSocket | null;
}

export interface NexusSocketListener {
  onOpen?: () => void;
  onClose?: () => void;
  onMessage?: (event: MessageEvent) => void;
  reconnectMs?: number;
}

const WS_CONNECTING = 0;
const WS_OPEN = 1;
const WS_CLOSING = 2;

const RECONNECT_BASE_MS = 3_000;
const RECONNECT_MAX_MS = 60_000;

/** Avoid calling WebSocket.close() while CONNECTING (noisy in React Strict Mode). */
const safeCloseSocket = (ws: WebSocket) => {
  if (ws.readyState === WS_OPEN) {
    ws.close();
    return;
  }
  if (ws.readyState === WS_CONNECTING) {
    ws.addEventListener('open', () => ws.close(), { once: true });
  }
};

class NexusWebSocketManager {
  private socket: WebSocket | null = null;
  private listeners = new Map<symbol, NexusSocketListener>();
  private subscriberCount = 0;
  private reconnectTimer: number | null = null;
  private idleCloseTimer: number | null = null;
  private intentionalClose = false;
  private reconnectMs = RECONNECT_BASE_MS;
  private reconnectAttempt = 0;

  subscribe(listener: NexusSocketListener = {}): NexusSocketHandle {
    const id = Symbol();
    this.listeners.set(id, listener);
    this.subscriberCount += 1;
    if (listener.reconnectMs != null) {
      this.reconnectMs = listener.reconnectMs;
    }
    this.cancelIdleClose();
    this.ensureConnected();

    if (this.socket?.readyState === WS_OPEN) {
      window.queueMicrotask(() => listener.onOpen?.());
    }

    return {
      close: () => {
        if (!this.listeners.has(id)) return;
        this.listeners.delete(id);
        this.subscriberCount = Math.max(0, this.subscriberCount - 1);
        this.scheduleIdleClose();
      },
      send: payload => this.send(payload),
      get socket() {
        return nexusWebSocketManager.getSocket();
      },
    };
  }

  getSocket(): WebSocket | null {
    return this.socket;
  }

  private cancelIdleClose() {
    if (this.idleCloseTimer != null) {
      window.clearTimeout(this.idleCloseTimer);
      this.idleCloseTimer = null;
    }
  }

  private scheduleIdleClose() {
    if (this.subscriberCount > 0) return;
    this.cancelIdleClose();
    // Brief delay survives React Strict Mode unmount/remount in development.
    this.idleCloseTimer = window.setTimeout(() => {
      if (this.subscriberCount === 0) {
        this.disconnect();
      }
    }, 250);
  }

  private clearReconnect() {
    if (this.reconnectTimer != null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private detachHandlers(ws: WebSocket) {
    ws.onopen = null;
    ws.onclose = null;
    ws.onerror = null;
    ws.onmessage = null;
  }

  private notifyOpen() {
    this.listeners.forEach(listener => listener.onOpen?.());
  }

  private notifyClose() {
    this.listeners.forEach(listener => listener.onClose?.());
  }

  private notifyMessage(event: MessageEvent) {
    this.listeners.forEach(listener => listener.onMessage?.(event));
  }

  private disconnect() {
    this.intentionalClose = true;
    this.clearReconnect();
    this.reconnectAttempt = 0;
    const ws = this.socket;
    this.socket = null;
    if (!ws) return;
    this.detachHandlers(ws);
    safeCloseSocket(ws);
  }

  private scheduleReconnect() {
    if (this.intentionalClose || this.subscriberCount <= 0) return;
    this.clearReconnect();
    const exp = Math.min(
      RECONNECT_MAX_MS,
      this.reconnectMs * 2 ** Math.min(this.reconnectAttempt, 5)
    );
    const jitter = Math.floor(Math.random() * 400);
    this.reconnectAttempt += 1;
    this.reconnectTimer = window.setTimeout(() => this.ensureConnected(), exp + jitter);
  }

  private ensureConnected() {
    if (!getStoredToken()) return;

    const state = this.socket?.readyState;
    if (state === WS_CONNECTING || state === WS_OPEN || state === WS_CLOSING) {
      return;
    }

    this.intentionalClose = false;
    this.clearReconnect();

    const ws = new WebSocket(resolveWebSocketUrl());
    this.socket = ws;

    ws.onopen = () => {
      if (this.socket !== ws) return;
      this.reconnectAttempt = 0;
      this.notifyOpen();
    };

    ws.onclose = () => {
      if (this.socket !== ws) return;
      this.socket = null;
      this.notifyClose();
      this.scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose follows; do not call ws.close() while CONNECTING.
    };

    ws.onmessage = event => {
      if (this.socket !== ws) return;
      this.notifyMessage(event);
    };
  }

  private send(payload: unknown) {
    if (this.socket?.readyState !== WS_OPEN) return;
    this.socket.send(typeof payload === 'string' ? payload : JSON.stringify(payload));
  }
}

const nexusWebSocketManager = new NexusWebSocketManager();

export const connectNexusWebSocket = (
  options: NexusSocketListener = {}
): NexusSocketHandle => nexusWebSocketManager.subscribe(options);
