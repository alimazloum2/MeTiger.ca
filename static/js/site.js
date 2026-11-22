/* metiger.ca — small progressive-enhancement script. No framework, no build.
   1) mobile menu toggle  2) quote form submit (fetch -> /send_message)
   3) hide the mobile action bar while the quote form is on screen
   4) reveal-on-scroll for the coverage section
   5) on a computer, a phone link opens a small "Call MeTiger" box instead of
      handing the click to the operating system (same as metiger.us) */
(function () {
  "use strict";

  // 1) Mobile menu
  var toggle = document.querySelector(".site-header .menu-toggle");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // 2) Quote form
  var form = document.querySelector("form[data-quote-form]");
  if (form) {
    var status = form.querySelector(".form-status");
    var fallback = form.querySelector(".form-fallback");
    var button = form.querySelector('button[type="submit"]');
    var started = form.querySelector('input[name="started_at"]');
    var sending = false;

    // Cached HTML can carry a stale timestamp; the server only needs "open >= 3s".
    if (started) started.value = Math.floor(Date.now() / 1000).toString();

    var say = function (ok, text) {
      status.hidden = false;
      status.setAttribute("data-ok", ok ? "true" : "false");
      status.textContent = text;
      if (fallback) fallback.hidden = ok;
    };
    var mark = function (el, bad) {
      if (!el) return;
      if (bad) el.setAttribute("aria-invalid", "true");
      else el.removeAttribute("aria-invalid");
    };

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (sending) return;
      var name = form.elements["name"];
      var email = form.elements["email"];
      var link = form.elements["plan_link"];
      var message = form.elements["message"];
      var consent = form.elements["consent"];

      var nameOk = name.value.trim().length > 1;
      var emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim());
      var msgOk = message.value.trim().length > 5 || link.value.trim().length > 5;
      mark(name, !nameOk);
      mark(email, !emailOk);
      mark(message, !msgOk);

      if (!nameOk) return say(false, "Please enter your name."), name.focus();
      if (!emailOk) return say(false, "Enter a valid work email."), email.focus();
      if (!msgOk) return say(false, "Add a drawing link or a short message about the project."), message.focus();
      if (!consent.checked) return say(false, "Please tick the box so we can reply to you."), consent.focus();

      sending = true;
      var label = button.textContent;
      button.disabled = true;
      button.textContent = "Sending…";
      fetch(form.getAttribute("action"), { method: "POST", body: new FormData(form) })
        .then(function (resp) {
          return resp.json().then(function (data) { return { resp: resp, data: data }; });
        })
        .then(function (r) {
          if (r.data && r.data.success) {
            say(true, r.data.message || "Thanks — we'll review your request and get back to you.");
            form.reset();
            if (started) started.value = Math.floor(Date.now() / 1000).toString();
          } else {
            say(false, (r.data && r.data.message) || "Something went wrong. Please try again.");
          }
        })
        .catch(function () {
          say(false, "The form could not be sent.");
        })
        .then(function () {
          sending = false;
          button.disabled = false;
          button.textContent = label;
          if (window.turnstile) { try { window.turnstile.reset(); } catch (_) {} }
        });
    });

    // 3) Mobile action bar steps aside while the form itself is visible.
    var bar = document.querySelector(".mobile-cta-bar");
    if (bar && "IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        bar.classList.toggle("is-hidden", entries[0].isIntersecting);
      }, { threshold: 0.15 }).observe(form);
    }
  }

  // 4) Reveal-on-scroll
  var reveals = document.querySelectorAll(".reveal");
  if (reveals.length) {
    var reduced = window.matchMedia("(prefers-reduced-motion:reduce)").matches;
    if (!reduced && "IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) {
        es.forEach(function (en) {
          if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
        });
      }, { threshold: 0.12 });
      reveals.forEach(function (el) { io.observe(el); });
    } else {
      reveals.forEach(function (el) { el.classList.add("in"); });
    }
  }

  // 5) Call box on computers. Phones and tablets keep the normal dial link.
  var touch = /Android|iPhone|iPad|iPod|Mobi/i.test(navigator.userAgent) ||
    (window.matchMedia && window.matchMedia("(any-pointer: coarse)").matches);
  if (!touch && typeof HTMLDialogElement !== "undefined") {
    var NUMBER = "+1 (838) 638-4437";
    var dialog = null;
    var callBox = function () {
      if (dialog) return dialog;
      dialog = document.createElement("dialog");
      dialog.className = "call-dialog";
      dialog.setAttribute("aria-labelledby", "call-dialog-title");
      dialog.innerHTML =
        '<h2 id="call-dialog-title">Call MeTiger</h2>' +
        '<p class="call-number"><a href="tel:+18386384437">' + NUMBER + "</a></p>" +
        '<p class="call-note">An AI assistant answers and takes your project details and bid date. An estimator follows up by email or phone.</p>' +
        '<div class="call-actions"><button type="button" class="cta call-copy">Copy number</button>' +
        '<button type="button" class="cta call-close">Close</button></div>';
      document.body.appendChild(dialog);
      dialog.querySelector(".call-close").addEventListener("click", function () { dialog.close(); });
      var copy = dialog.querySelector(".call-copy");
      copy.addEventListener("click", function () {
        if (!navigator.clipboard) return;
        navigator.clipboard.writeText(NUMBER).then(function () {
          copy.textContent = "Copied";
          window.setTimeout(function () { copy.textContent = "Copy number"; }, 2000);
        }).catch(function () {});
      });
      dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
      return dialog;
    };
    document.addEventListener("click", function (e) {
      var link = e.target.closest ? e.target.closest('a[href^="tel:"]') : null;
      if (!link || link.closest("dialog")) return;
      e.preventDefault();
      callBox().showModal();
    });
  }
})();
