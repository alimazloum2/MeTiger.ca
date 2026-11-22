/* metiger.ca admin — insert a photo into the article text.
   Uploads the picture, then writes ![caption](address) as its own paragraph
   at the cursor, with the caption selected so it can be typed over. */
(function () {
  "use strict";
  var body = document.getElementById("body");
  var button = document.getElementById("photo-button");
  var input = document.getElementById("photo-input");
  var status = document.getElementById("photo-status");
  var script = document.currentScript;
  if (!body || !button || !input || !script) return;
  var uploadUrl = script.getAttribute("data-upload-url");
  var csrf = document.querySelector('input[name="csrf"]').value;
  var CAPTION = "Describe the photo";
  var busy = false;

  function say(text, bad) {
    status.textContent = text;
    status.classList.toggle("validation", !!bad);
  }

  function insert(url) {
    var at = body.selectionStart || 0;
    var before = body.value.slice(0, at).replace(/\s+$/, "");
    var after = body.value.slice(body.selectionEnd || at).replace(/^\s+/, "");
    var lead = before ? before + "\n\n" : "";
    var line = "![" + CAPTION + "](" + url + ")";
    body.value = lead + line + (after ? "\n\n" + after : "\n");
    body.focus();
    body.setSelectionRange(lead.length + 2, lead.length + 2 + CAPTION.length);
  }

  function upload(file) {
    if (busy || !file) return;
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return say("Use a JPG, PNG or WebP picture.", true);
    busy = true;
    button.disabled = true;
    say("Uploading…");
    var data = new FormData();
    data.append("csrf", csrf);
    data.append("photo", file);
    fetch(uploadUrl, { method: "POST", body: data, credentials: "same-origin" })
      .then(function (resp) { return resp.json(); })
      .then(function (r) {
        if (r && r.ok) {
          insert(r.url);
          say("Photo added. Type a caption over the highlighted words, then press Save.");
        } else {
          say((r && r.message) || "The photo could not be uploaded.", true);
        }
      })
      .catch(function () { say("The photo could not be uploaded. Check that you are still logged in.", true); })
      .then(function () { busy = false; button.disabled = false; input.value = ""; });
  }

  button.addEventListener("click", function () { input.click(); });
  input.addEventListener("change", function () { upload(input.files[0]); });

  body.addEventListener("dragover", function (e) {
    if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, "Files") !== -1) e.preventDefault();
  });
  body.addEventListener("drop", function (e) {
    var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) { e.preventDefault(); upload(file); }
  });
  body.addEventListener("paste", function (e) {
    var file = e.clipboardData && e.clipboardData.files && e.clipboardData.files[0];
    if (file) { e.preventDefault(); upload(file); }
  });
})();
