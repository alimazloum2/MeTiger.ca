/* metiger.ca — corner chat assistant. The conversation lives only in this
   browser tab (sessionStorage) and is sent to /api/chat with each message.
   Replies are inserted as plain text, never as HTML. */
(function () {
  "use strict";
  var root = document.querySelector("[data-chat]");
  if (!root) return;
  var endpoint = root.getAttribute("data-endpoint");
  var launch = root.querySelector(".mt-chat-launch");
  var panel = root.querySelector(".mt-chat-panel");
  var closeBtn = root.querySelector(".mt-chat-close");
  var log = root.querySelector(".mt-chat-log");
  var form = root.querySelector(".mt-chat-form");
  var input = root.querySelector("textarea");
  var trap = root.querySelector(".mt-chat-hp");
  var send = root.querySelector(".mt-chat-send");
  var starters = root.querySelector(".mt-chat-starters");
  var KEY = "mt-chat-v1";
  var MAX_TURNS = 16;
  var history = [];
  // A random id for this tab's conversation, so the questions in it can be
  // shown together on the admin page. It says nothing about who the visitor is.
  var cid = "";
  try {
    cid = sessionStorage.getItem(KEY + "-id") || "";
    if (!/^[a-f0-9]{24}$/.test(cid)) {
      var bytes = new Uint8Array(12);
      (window.crypto || window.msCrypto).getRandomValues(bytes);
      cid = Array.prototype.map.call(bytes, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
      sessionStorage.setItem(KEY + "-id", cid);
    }
  } catch (_) {}
  var busy = false;

  function store() {
    try { sessionStorage.setItem(KEY, JSON.stringify(history.slice(-MAX_TURNS))); } catch (_) {}
  }
  function bubble(role, text, extra) {
    var p = document.createElement("p");
    p.className = "mt-chat-msg " + (role === "user" ? "mt-chat-user" : "mt-chat-bot") + (extra ? " " + extra : "");
    p.textContent = text;
    if (starters && role === "user") starters.hidden = true;
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
    return p;
  }
  try {
    var saved = JSON.parse(sessionStorage.getItem(KEY) || "[]");
    if (Array.isArray(saved)) {
      saved.forEach(function (m) {
        if (m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string") {
          history.push({ role: m.role, content: m.content });
          bubble(m.role, m.content);
        }
      });
    }
  } catch (_) {}

  function open(yes) {
    panel.hidden = !yes;
    launch.setAttribute("aria-expanded", yes ? "true" : "false");
    root.classList.toggle("is-open", yes);
    if (yes) { log.scrollTop = log.scrollHeight; input.focus(); } else { launch.focus(); }
  }
  if (starters) {
    starters.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b || busy) return;
      input.value = b.textContent;
      form.requestSubmit ? form.requestSubmit() : send.click();
    });
  }
  launch.addEventListener("click", function () { open(panel.hidden); });
  closeBtn.addEventListener("click", function () { open(false); });
  root.addEventListener("keydown", function (e) { if (e.key === "Escape" && !panel.hidden) open(false); });

  input.addEventListener("input", function () {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit ? form.requestSubmit() : send.click(); }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (busy || !text) return;
    busy = true;
    send.disabled = true;
    history.push({ role: "user", content: text });
    bubble("user", text);
    input.value = "";
    input.style.height = "auto";
    var wait = bubble("assistant", "…", "mt-chat-wait");
    var failed = function (message) {
      history.pop();                       // let the visitor try the same question again
      wait.classList.remove("mt-chat-wait");
      wait.classList.add("mt-chat-error");
      wait.textContent = message || "The assistant is not available right now. Please use the quote form or email info@metiger.ca.";
    };
    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history.slice(-MAX_TURNS), website: trap.value, cid: cid })
    })
      .then(function (resp) {
        if (resp.status === 429) return { ok: false, message: "That's a lot of questions in a short time. Please wait a minute, or use the quote form." };
        return resp.json();
      })
      .then(function (r) {
        if (r && r.ok && typeof r.reply === "string") {
          wait.classList.remove("mt-chat-wait");
          wait.textContent = r.reply;
          history.push({ role: "assistant", content: r.reply });
          store();
        } else {
          failed(r && r.message);
        }
      })
      .catch(function () { failed(); })
      .then(function () {
        busy = false;
        send.disabled = false;
        log.scrollTop = log.scrollHeight;
        if (!panel.hidden) input.focus();
      });
  });
})();
