const els = {
  deviceHost: document.getElementById("deviceHost"),
  testBtn: document.getElementById("testConnection"),
  saveBtn: document.getElementById("saveConfig"),
  connectionBadge: document.getElementById("connectionBadge"),
  analysisMeta: document.getElementById("analysisMeta"),
  consoleBody: document.getElementById("robotConsole"),
  consoleReload: document.getElementById("consoleReload"),
  consoleAutoScroll: document.getElementById("consoleAutoScroll"),
  emotionIndicator: document.getElementById("emotionIndicator"),
  emotionHeadline: document.getElementById("emotionHeadline"),
  emotionDetails: document.getElementById("emotionDetails"),
  emotionMood: document.getElementById("emotionMood"),
  emotionEnergy: document.getElementById("emotionEnergy"),
  emotionAdvice: document.getElementById("emotionAdvice"),
};

const STORAGE_KEY = "petFollowerDashboard";
let config = { deviceAddress: "" };
let resolvedBaseUrl = "";
let consolePollTimer = null;
let emotionPollTimer = null;
const CONSOLE_POLL_INTERVAL = 10000;
const EMOTION_POLL_INTERVAL = 20000;

function init() {
  loadConfig();
  setupConfigButtons();
  setupConsole();
  setupEmotionInsights();
  if (resolvedBaseUrl) {
    refreshStatus();
  } else {
    setConnectionState("offline", "Enter the device address");
    renderEmotionInsight(null, "Waiting for device connection");
  }
}

function loadConfig() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      config = { ...config, ...JSON.parse(saved) };
    }
  } catch (err) {
    console.warn("Failed to parse saved config", err);
  }
  if (els.deviceHost) {
    els.deviceHost.value = config.deviceAddress || "";
    
    if (window.location.protocol.startsWith("http")) {
      const current = window.location.origin;
      const stored = els.deviceHost.value;
      
      if (!stored) {
        els.deviceHost.value = current;
      } else {
        try {
          const currentUrl = new URL(current);
          let storedUrlStr = stored;
          if (!/^https?:\/\//i.test(storedUrlStr)) storedUrlStr = `http://${storedUrlStr}`;
          const storedUrl = new URL(storedUrlStr);
          if (!storedUrl.port) storedUrl.port = "8000";
          
          if (currentUrl.hostname === storedUrl.hostname && currentUrl.port !== storedUrl.port) {
             console.log("Auto-updating host port to match current page origin");
             els.deviceHost.value = current;
          }
        } catch (e) {
          // ignore
        }
      }
      
      // Ensure config reflects the auto-detected value
      if (els.deviceHost.value !== (config.deviceAddress || "")) {
         config.deviceAddress = els.deviceHost.value;
      }
    }
  }
  updateResolvedBaseUrl();
}

function saveConfig() {
  config.deviceAddress = (els.deviceHost?.value || "").trim();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  updateResolvedBaseUrl();
  if (!resolvedBaseUrl) {
    setConnectionState("offline", "Please enter a valid PiCar-X host");
    renderEmotionInsight(null, "Enter the device address");
    return;
  }
  refreshStatus(true);
  loadLocalConsoleLog();
  loadEmotionInsight();
}

function setupConfigButtons() {
  if (els.saveBtn) {
    els.saveBtn.addEventListener("click", saveConfig);
  }
  if (els.testBtn) {
    els.testBtn.addEventListener("click", () => refreshStatus(true));
  }
}

async function refreshStatus(showToast = false) {
  if (!resolvedBaseUrl) {
    if (showToast) {
      setConnectionState("offline", "Enter the PiCar-X API address first");
    }
    return;
  }
  try {
    const resp = await fetch(`${resolvedBaseUrl}/api/status`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const message = data.message || "Connected";
    setConnectionState("online", message);
  } catch (err) {
    setConnectionState("offline", `Unable to reach PiCar-X (${err.message})`);
  }
}

function setConnectionState(state, message = "") {
  if (!els.connectionBadge) return;
  const text = state === "online" ? "Online" : "Offline";
  els.connectionBadge.textContent = text;
  els.connectionBadge.classList.toggle("online", state === "online");
  els.connectionBadge.classList.toggle("offline", state === "offline");
  if (message) {
    setAnalysisMeta(message);
  }
}

function setupConsole() {
  if (!els.consoleBody) return;
  if (els.consoleReload) {
    els.consoleReload.addEventListener("click", () => {
      loadLocalConsoleLog();
    });
  }
  loadLocalConsoleLog();
  startConsolePolling();
}

function startConsolePolling() {
  if (consolePollTimer) clearInterval(consolePollTimer);
  consolePollTimer = setInterval(() => {
    loadLocalConsoleLog();
  }, CONSOLE_POLL_INTERVAL);
}

async function loadLocalConsoleLog() {
  if (!els.consoleBody) return;
  if (!resolvedBaseUrl) {
    renderConsoleLog([
      {
        ts: "",
        level: "error",
        source: "console",
        msg: "API address not configured",
      },
    ]);
    return;
  }
  try {
    const resp = await fetch(`${resolvedBaseUrl}/api/gcp-log`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (data.status === "ok") {
      let entries = data.entries || [];
      if (!entries.length && data.content) {
        const lines = data.content.split(/\r?\n/).filter((line) => line.trim().length > 0);
        for (const line of lines) {
          try {
            entries.push(JSON.parse(line));
          } catch (err) {
            entries.push({
              ts: "",
              level: "error",
              source: "console",
              msg: "Invalid JSONL line",
              extra: { line },
            });
          }
        }
      }
      renderConsoleLog(entries);
    } else {
      throw new Error(data.error || "Unknown error");
    }
  } catch (err) {
    renderConsoleLog([
      {
        ts: "",
        level: "error",
        source: "console",
        msg: `Failed to load log from GCP: ${err.message}`,
      },
    ]);
  }
}

function setupEmotionInsights() {
  loadEmotionInsight();
  startEmotionPolling();
}

function startEmotionPolling() {
  if (emotionPollTimer) clearInterval(emotionPollTimer);
  emotionPollTimer = setInterval(() => {
    loadEmotionInsight();
  }, EMOTION_POLL_INTERVAL);
}

async function loadEmotionInsight() {
  if (!els.emotionHeadline) return;
  if (!resolvedBaseUrl) {
    renderEmotionInsight(null, "Enter the device address");
    return;
  }
  try {
    const resp = await fetch(`${resolvedBaseUrl}/api/emotion-insight`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (data.status === "ok" && data.analysis) {
      renderEmotionInsight(data.analysis);
    } else {
      throw new Error(data.error || "No analysis data");
    }
  } catch (err) {
    renderEmotionInsight(null, `Emotion service unavailable: ${err.message}`);
  }
}

function renderEmotionInsight(analysis, metaMessage = "") {
  const fallback = {
    headline: "Insights coming soon",
    details: "Connect your PiCar-X to start collecting emotion analytics.",
    mood: "Unknown",
    energy: "-",
    advice: "Check back later",
    indicator: "idle",
    confidence: null,
    updated_at: null,
  };
  const normalized = analysis && typeof analysis === "object" ? analysis : {};
  const payload = { ...fallback, ...normalized };
  if (els.emotionIndicator) {
    els.emotionIndicator.textContent = getEmotionIndicator(payload.indicator || payload.mood);
  }
  if (els.emotionHeadline) {
    els.emotionHeadline.textContent = payload.headline || fallback.headline;
  }
  if (els.emotionDetails) {
    els.emotionDetails.textContent = payload.details || fallback.details;
  }
  if (els.emotionMood) {
    els.emotionMood.textContent = payload.mood || fallback.mood;
  }
  if (els.emotionEnergy) {
    els.emotionEnergy.textContent = payload.energy || fallback.energy;
  }
  if (els.emotionAdvice) {
    els.emotionAdvice.textContent = payload.advice || fallback.advice;
  }

  if (analysis) {
    const updated = payload.updated_at || payload.timestamp || Date.now();
    const rel = formatRelativeTime(updated);
    const confidenceText = typeof payload.confidence === "number"
      ? ` • Confidence ${(payload.confidence * 100).toFixed(0)}%`
      : "";
    setAnalysisMeta(`Updated ${rel}${confidenceText}`.trim());
  } else if (metaMessage) {
    setAnalysisMeta(metaMessage);
  } else {
    setAnalysisMeta("Awaiting analysis data");
  }
}

function getEmotionIndicator(kind = "") {
  const value = String(kind).toLowerCase();
  if (value.includes("happy") || value.includes("play")) return "😄";
  if (value.includes("calm") || value.includes("relax")) return "😌";
  if (value.includes("alert")) return "🧐";
  if (value.includes("stressed") || value.includes("anx")) return "😣";
  if (value.includes("sleep")) return "😴";
  return "🙂";
}

function renderConsoleLog(entries) {
  const container = els.consoleBody;
  if (!container) return;
  container.innerHTML = "";

  entries.forEach((entry) => {
    const level = (entry.level || "info").toLowerCase();
    const card = document.createElement("div");
    card.className = `console-entry level-${level}`;

    const ts = entry.ts || entry.time || "";
    const source = entry.source || entry.component || (entry.extra && entry.extra.source) || "";
    const description = entry.description || entry.msg || entry.message || "";
    const extra = entry.extra && typeof entry.extra === "object" ? entry.extra : null;

    const header = document.createElement("div");
    header.className = "console-entry-header";

    const meta = document.createElement("div");
    meta.className = "console-entry-meta";

    if (ts) {
      const timeEl = document.createElement("span");
      timeEl.className = "console-entry-time";
      timeEl.textContent = ts;
      meta.appendChild(timeEl);
    }

    if (source) {
      const sourceEl = document.createElement("span");
      sourceEl.className = "console-entry-source";
      sourceEl.textContent = source;
      meta.appendChild(sourceEl);
    }

    const levelEl = document.createElement("span");
    levelEl.className = "console-entry-level";
    levelEl.textContent = level;

    header.appendChild(meta);
    header.appendChild(levelEl);

    const descEl = document.createElement("div");
    descEl.className = "console-entry-description";
    descEl.textContent = description;

    card.appendChild(header);
    card.appendChild(descEl);

    if (extra && Object.keys(extra).length > 0) {
      const tags = document.createElement("div");
      tags.className = "console-tags";
      Object.entries(extra).forEach(([key, value]) => {
        const tag = document.createElement("span");
        tag.className = "console-tag";
        tag.textContent = `${key}: ${value}`;
        tags.appendChild(tag);
      });
      card.appendChild(tags);
    }

    container.appendChild(card);
  });

  if (els.consoleAutoScroll && els.consoleAutoScroll.checked) {
    container.scrollTop = container.scrollHeight;
  }
}

function updateResolvedBaseUrl() {
  resolvedBaseUrl = normalizeBaseUrl(config.deviceAddress);
}

function normalizeBaseUrl(input) {
  if (!input) return "";
  let value = input.trim();
  if (!value) return "";
  if (!/^https?:\/\//i.test(value)) {
    value = `http://${value}`;
  }
  try {
    const url = new URL(value);
    if (!url.port) {
      url.port = "8000";
    }
    return url.origin;
  } catch (err) {
    console.warn(`Invalid address: ${input}`);
    return "";
  }
}

function setAnalysisMeta(text) {
  if (!els.analysisMeta) return;
  els.analysisMeta.textContent = text;
}

function formatRelativeTime(value) {
  if (!value) return "just now";
  let ts = value;
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    ts = Number.isNaN(parsed) ? Date.now() : parsed;
  } else if (typeof value === "number" && value < 1e12) {
    ts = value * 1000;
  }
  const diff = Date.now() - ts;
  if (diff < 0) return "just now";
  if (diff < 60000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3600000) return `${Math.round(diff / 60000)} min ago`;
  if (diff < 86400000) return `${Math.round(diff / 3600000)} h ago`;
  return new Date(ts).toLocaleString();
}

init();
