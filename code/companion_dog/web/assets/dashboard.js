const els = {
  deviceHost: document.getElementById("deviceHost"),
  video: document.getElementById("videoFeed"),
  modeLabel: document.getElementById("modeLabel"),
  followLabel: document.getElementById("followLabel"),
  confidenceLabel: document.getElementById("confidenceLabel"),
  distanceLabel: document.getElementById("distanceLabel"),
  targetStatus: document.getElementById("targetStatus"),
  statusList: {
    targetVisible: document.getElementById("targetVisible"),
    lastTargetTime: document.getElementById("lastTargetTime"),
    safetyDistance: document.getElementById("safetyDistance"),
    cliffStatus: document.getElementById("cliffStatus"),
    fpsLabel: document.getElementById("fpsLabel"),
    lastMessage: document.getElementById("lastMessage"),
  },
  connectionBadge: document.getElementById("connectionBadge"),
  logList: document.getElementById("logList"),
  autoScroll: document.getElementById("autoScroll"),
  clearLog: document.getElementById("clearLog"),
  refreshBtn: document.getElementById("refreshStatus"),
  testBtn: document.getElementById("testConnection"),
  saveBtn: document.getElementById("saveConfig"),
  stateOverlay: document.getElementById("stateOverlay"),
  speedSlider: document.getElementById("speedSlider"),
  durationSlider: document.getElementById("durationSlider"),
  speedValue: document.getElementById("speedValue"),
  durationValue: document.getElementById("durationValue"),
  autoRecordToggle: document.getElementById("autoRecordToggle"),
  autoRecordInterval: document.getElementById("autoRecordInterval"),
  autoRecordStatus: document.getElementById("autoRecordStatus"),
  applyAutoRecord: document.getElementById("applyAutoRecord"),
  autoRecordLast: document.getElementById("autoRecordLast"),
};

const AUTO_RECORD_INTERVAL = {
  min: 1,
  max: 100,
  defaultMinutes: 3,
};

const STORAGE_KEY = "petFollowerDashboard";
let config = {
  deviceAddress: "",
};
let pollTimer = null;
let eventSource = null;
let resolvedBaseUrl = "";

function clampAutoRecordInterval(value) {
  const numericValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numericValue)) {
    return AUTO_RECORD_INTERVAL.defaultMinutes;
  }
  const rounded = Math.round(numericValue);
  return Math.min(AUTO_RECORD_INTERVAL.max, Math.max(AUTO_RECORD_INTERVAL.min, rounded));
}

function readAutoRecordInterval(reportError = false) {
  if (!els.autoRecordInterval) return null;
  const raw = (els.autoRecordInterval.value || "").trim();
  const rangeMessage = `Enter a whole number between ${AUTO_RECORD_INTERVAL.min} and ${AUTO_RECORD_INTERVAL.max}`;
  if (!raw) {
    els.autoRecordInterval.setCustomValidity("Interval is required");
    if (reportError) els.autoRecordInterval.reportValidity();
    return null;
  }
  if (!/^\d+$/.test(raw)) {
    els.autoRecordInterval.setCustomValidity(rangeMessage);
    if (reportError) els.autoRecordInterval.reportValidity();
    return null;
  }
  const minutes = Number(raw);
  if (minutes < AUTO_RECORD_INTERVAL.min || minutes > AUTO_RECORD_INTERVAL.max) {
    els.autoRecordInterval.setCustomValidity(rangeMessage);
    if (reportError) els.autoRecordInterval.reportValidity();
    return null;
  }
  els.autoRecordInterval.setCustomValidity("");
  return minutes;
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
        // ignore invalid stored url
      }
    }
    
    // Ensure the config object reflects the auto-detected or updated value
    if (els.deviceHost.value !== (config.deviceAddress || "")) {
       config.deviceAddress = els.deviceHost.value;
    }
  }
  updateResolvedBaseUrl();
  setVideoSrc();
}

function saveConfig() {
  config.deviceAddress = els.deviceHost.value.trim();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  updateResolvedBaseUrl();
  if (!resolvedBaseUrl) {
    logEvent("warn", "Please enter a valid PiCar-X host or IP");
    return;
  }
  logEvent("system", `Target device: ${resolvedBaseUrl}`);
  setVideoSrc();
  connectStreams();
}

function setVideoSrc() {
  if (resolvedBaseUrl) {
    els.video.src = `${resolvedBaseUrl}/stream.mjpg`;
    els.video.alt = "pet follower live stream";
  } else {
    els.video.removeAttribute("src");
    els.video.alt = "Video stream not configured";
  }
}

function setConnectionState(state, message = "") {
  els.connectionBadge.textContent = state === "online" ? "Online" : "Offline";
  els.connectionBadge.classList.toggle("online", state === "online");
  els.connectionBadge.classList.toggle("offline", state === "offline");
  if (message) {
    els.targetStatus.textContent = message;
  }
}

async function fetchStatus(showToast = false) {
  if (!resolvedBaseUrl) {
    if (showToast) logEvent("warn", "Enter the PiCar-X API address first");
    return null;
  }
  try {
    const resp = await fetch(`${resolvedBaseUrl}/api/status`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    updateStatusUI(data);
    setConnectionState("online", "Syncing live data");
    if (showToast) logEvent("system", "Status refreshed");
    return data;
  } catch (err) {
    setConnectionState("offline", "Unable to reach PiCar-X");
    logEvent("error", `Failed to fetch status: ${err.message}`);
    return null;
  }
}

function updateStatusUI(payload = {}) {
  const mode = payload.mode || payload.state || "-";
  const detection = payload.detection || {};
  const safety = payload.safety || {};
  const motion = payload.motion || {};

  els.modeLabel.textContent = mode;
  const visible = detection.target_visible ?? payload.target_visible;
  els.followLabel.textContent = visible ? "Following target" : "No target";
  els.confidenceLabel.textContent = detection.confidence
    ? `${(detection.confidence * 100).toFixed(1)}%`
    : "-";
  const distance = detection.approx_distance_cm ?? payload.distance_cm;
  els.distanceLabel.textContent = distance ? `${distance.toFixed(1)} cm` : "-";
  els.targetStatus.textContent = payload.message || payload.note || "";

  els.statusList.targetVisible.textContent = visible ? "Yes" : "No";
  els.statusList.lastTargetTime.textContent = formatRelativeTime(
    detection.updated_at || payload.last_detection
  );
  const dist = safety.distance_cm ?? payload.obstacle_distance;
  els.statusList.safetyDistance.textContent = typeof dist === "number" ? `${dist} cm` : "Unknown";
  const cliff = safety.cliff_detected ?? false;
  els.statusList.cliffStatus.textContent = cliff ? "Warning" : "Normal";
  els.statusList.cliffStatus.style.color = cliff ? "var(--danger)" : "var(--muted)";
  const fps = payload.fps ?? payload.camera_fps;
  els.statusList.fpsLabel.textContent = fps ? fps.toFixed(1) : "-";
  const msg = payload.last_log || payload.message || "-";
  els.statusList.lastMessage.textContent = msg;
  if (payload.auto_recording) {
    updateAutoRecordUI(payload.auto_recording);
  }

  if (motion.safe_to_move === false) {
    els.stateOverlay.dataset.blocked = "true";
  } else {
    delete els.stateOverlay.dataset.blocked;
  }
}

function formatRelativeTime(value) {
  if (!value) return "-";
  try {
    const ts = typeof value === "number" ? value * 1000 : Date.parse(value);
    if (Number.isNaN(ts)) return value;
    const diff = Date.now() - ts;
    if (diff < 5000) return "just now";
    if (diff < 60000) return `${Math.round(diff / 1000)} sec ago`;
    if (diff < 3600000) return `${Math.round(diff / 60000)} min ago`;
    return new Date(ts).toLocaleTimeString();
  } catch (err) {
    return value;
  }
}

async function sendAction(action, extra = {}) {
  if (!resolvedBaseUrl) {
    logEvent("warn", "API address not configured");
    return false;
  }
  try {
    const resp = await fetch(`${resolvedBaseUrl}/api/commands`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, ...extra }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (data.status) logEvent("system", data.status);
    if (data.state) updateStatusUI(data.state);
    return true;
  } catch (err) {
    logEvent("error", `Action ${action} failed: ${err.message}`);
    return false;
  }
}

function setButtonActive(btn) {
  if (!btn || !btn.dataset || !btn.dataset.group) return;
  const group = btn.dataset.group;
  document.querySelectorAll(`[data-group="${group}"]`).forEach((el) => {
    el.classList.remove("is-active");
  });
  btn.classList.add("is-active");
}

function applyDefaultActiveStates() {
  document.querySelectorAll("[data-default-active]").forEach((btn) => {
    setButtonActive(btn);
  });
}

function setupButtons() {
  document.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const action = btn.dataset.action;
      if (!action) return;
      setButtonActive(btn);
      if (action === "snapshot") {
        sendAction("capture_frame");
      } else if (action === "search") {
        sendAction("force_search");
      } else if (action === "record_video") {
        const duration = Number(btn.dataset.duration || 10);
        logEvent("system", `Recording video for ${duration} seconds...`);
        const ok = await sendAction("record_video", { duration });
        if (ok) {
          logEvent("system", "Recording finished");
        } else {
          logEvent("warn", "Recording failed");
        }
      } else if (action === "mark") {
        sendAction("mark_event", { note: prompt("Enter event note", "") });
      } else {
        sendAction(action);
      }
    });
  });

  document.querySelectorAll("[data-drive]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const direction = btn.dataset.drive;
      setButtonActive(btn);
      const payload = {
        direction,
        speed: Number(els.speedSlider.value),
        duration: Number(els.durationSlider.value),
      };
      sendAction("manual_drive", payload);
    });
  });
}

function setupSliders() {
  const sync = () => {
    els.speedValue.textContent = els.speedSlider.value;
    els.durationValue.textContent = Number(els.durationSlider.value).toFixed(1);
  };
  els.speedSlider.addEventListener("input", sync);
  els.durationSlider.addEventListener("input", sync);
  sync();
}

function setupAutoRecordControls() {
  if (!els.autoRecordInterval) return;
  els.autoRecordInterval.addEventListener("input", () => {
    readAutoRecordInterval(false);
  });
  readAutoRecordInterval(false);
  if (els.applyAutoRecord) {
    els.applyAutoRecord.addEventListener("click", () => {
      const minutes = readAutoRecordInterval(true);
      if (minutes === null) return;
      const enabled = !!(els.autoRecordToggle && els.autoRecordToggle.checked);
      sendAction("auto_recording", { enabled, interval: minutes * 60 });
    });
  }
}

function updateAutoRecordUI(info) {
  if (!els.autoRecordToggle || !els.autoRecordInterval) return;
  const intervalSeconds = info.interval ?? AUTO_RECORD_INTERVAL.defaultMinutes * 60;
  const minutes = clampAutoRecordInterval(intervalSeconds / 60);
  els.autoRecordToggle.checked = !!info.enabled;
  els.autoRecordInterval.value = String(minutes);
  els.autoRecordInterval.setCustomValidity("");
  let status = "Auto recording disabled";
  let lastText = "No clips yet";
  if (info.enabled) {
    const secondsUntil = info.seconds_until_next ?? 0;
    if (info.active) {
      status = "Recording clip...";
    } else if (!info.eligible) {
      const minutesLeft = secondsUntil / 60;
      status = `Ready in ${minutesLeft.toFixed(1)} min`;
    } else {
      status = "Ready to record on next detection";
    }
  }
  if (info.last_uploaded_at) {
    const lastDate = new Date(info.last_uploaded_at * 1000);
    const since = formatDurationSeconds(info.seconds_since_last);
    lastText = `Last clip: ${lastDate.toLocaleTimeString()}${since ? ` (${since} ago)` : ""}`;
  }
  if (els.autoRecordStatus) {
    els.autoRecordStatus.textContent = status;
  }
  if (els.autoRecordLast) {
    els.autoRecordLast.textContent = lastText;
  }
}

function logEvent(level, text) {
  const li = document.createElement("li");
  const time = document.createElement("time");
  time.dateTime = new Date().toISOString();
  time.textContent = new Date().toLocaleTimeString();
  const span = document.createElement("span");
  span.textContent = `[${level}] ${text}`;
  if (level === "error") {
    span.style.color = "var(--danger)";
  } else if (level === "warn") {
    span.style.color = "var(--warning)";
  }
  li.appendChild(time);
  li.appendChild(span);
  els.logList.prepend(li);
  const maxItems = 150;
  while (els.logList.children.length > maxItems) {
    els.logList.removeChild(els.logList.lastChild);
  }
  if (els.autoScroll.checked) {
    li.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function setupLogControls() {
  els.clearLog.addEventListener("click", () => {
    els.logList.innerHTML = "";
  });
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => {
    fetchStatus();
  }, 5000);
}

function connectEventStream() {
  if (!window.EventSource || !resolvedBaseUrl) return;
  if (eventSource) {
    eventSource.close();
  }
  eventSource = new EventSource(`${resolvedBaseUrl}/api/events`);
  eventSource.onmessage = (event) => {
    if (!event.data) return;
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "status") {
        updateStatusUI(payload.data);
      } else if (payload.type === "log") {
        logEvent(payload.level || "info", payload.message || "");
      }
    } catch (err) {
      console.warn("Failed to parse event", err);
    }
  };
  eventSource.onerror = () => {
    logEvent("warn", "Event stream interrupted, retrying in 5s");
    eventSource.close();
    setTimeout(connectEventStream, 5000);
  };
}

function connectStreams() {
  if (!resolvedBaseUrl) return;
  fetchStatus();
  startPolling();
  connectEventStream();
}

function setupConfigButtons() {
  els.saveBtn.addEventListener("click", saveConfig);
  els.testBtn.addEventListener("click", () => fetchStatus(true));
  els.refreshBtn.addEventListener("click", () => fetchStatus(true));
}


function init() {
  loadConfig();
  setupButtons();
  setupSliders();
  setupAutoRecordControls();
  setupLogControls();
  setupConfigButtons();
  applyDefaultActiveStates();
  if (resolvedBaseUrl) {
    connectStreams();
  } else {
    setConnectionState("offline", "Enter the device address");
  }
}

init();

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
    logEvent("warn", `Invalid address: ${input}`);
    return "";
  }
}

function formatDurationSeconds(seconds) {
  if (seconds == null || seconds < 0) return "";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}
