/* Larry David Video Finder — shared client logic for both pages. */
(function () {
  "use strict";

  var STORAGE_KEY = "mpv2.savedVideos";

  /* ---------- localStorage helpers ---------- */

  function getSaved() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr : [];
    } catch (e) {
      return [];
    }
  }

  function setSaved(list) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    updateBadge();
  }

  function isSaved(id) {
    return getSaved().some(function (v) { return v.video_id === id; });
  }

  function saveVideo(video) {
    var list = getSaved();
    if (!list.some(function (v) { return v.video_id === video.video_id; })) {
      list.push(video);
      setSaved(list);
    }
  }

  function removeVideo(id) {
    setSaved(getSaved().filter(function (v) { return v.video_id !== id; }));
  }

  function updateBadge() {
    var badge = document.getElementById("savedBadge");
    if (!badge) return;
    var n = getSaved().length;
    badge.textContent = n ? String(n) : "";
    badge.setAttribute("data-count", String(n));
  }

  /* ---------- rendering ---------- */

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function thumbUrl(id) {
    return "https://i.ytimg.com/vi/" + encodeURIComponent(id) + "/hqdefault.jpg";
  }

  function metaLine(video) {
    var bits = [];
    if (video.channel) bits.push(escapeHtml(video.channel));
    var sub = [];
    if (video.views) sub.push(escapeHtml(video.views));
    if (video.published) sub.push(escapeHtml(video.published));
    var html = "";
    if (bits.length) html += '<div class="card-meta">' + bits.join("") + "</div>";
    if (sub.length) html += '<div class="card-meta">' + sub.join(" • ") + "</div>";
    return html;
  }

  // mode: "find" (Save/Saved toggle) or "saved" (Remove)
  function cardEl(video, mode) {
    var card = document.createElement("div");
    card.className = "card";
    card.setAttribute("data-id", video.video_id);

    var url = video.url || ("https://www.youtube.com/watch?v=" + video.video_id);
    var dur = video.duration && video.duration !== "N/A"
      ? '<span class="dur">' + escapeHtml(video.duration) + "</span>" : "";

    var actions;
    if (mode === "saved") {
      actions =
        '<a class="btn" href="' + escapeHtml(url) + '" target="_blank" rel="noopener">Watch</a>' +
        '<button class="btn btn-danger" data-action="remove">Remove</button>';
    } else {
      var saved = isSaved(video.video_id);
      actions =
        '<a class="btn" href="' + escapeHtml(url) + '" target="_blank" rel="noopener">Watch</a>' +
        '<button class="btn ' + (saved ? "btn-saved" : "") + '" data-action="save"' +
        (saved ? " disabled" : "") + ">" + (saved ? "Saved ✓" : "Save") + "</button>";
    }

    card.innerHTML =
      '<a class="thumb" href="' + escapeHtml(url) + '" target="_blank" rel="noopener">' +
        '<img loading="lazy" src="' + thumbUrl(video.video_id) + '" alt="" ' +
        'onerror="this.style.display=\'none\'" />' + dur +
      "</a>" +
      '<div class="card-body">' +
        '<a class="card-title" href="' + escapeHtml(url) + '" target="_blank" rel="noopener">' +
          escapeHtml(video.title || "(untitled)") + "</a>" +
        metaLine(video) +
        '<div class="card-actions">' + actions + "</div>" +
      "</div>";

    // Wire the action button.
    var btn = card.querySelector("[data-action]");
    if (btn) {
      btn.addEventListener("click", function () {
        var action = btn.getAttribute("data-action");
        if (action === "save") {
          saveVideo(video);
          btn.textContent = "Saved ✓";
          btn.classList.add("btn-saved");
          btn.disabled = true;
        } else if (action === "remove") {
          removeVideo(video.video_id);
          card.remove();
          renderSavedEmptyState();
        }
      });
    }

    return card;
  }

  /* ---------- Find page ---------- */

  function show(id, on) {
    var el = document.getElementById(id);
    if (el) el.classList.toggle("hidden", !on);
  }

  function initFindPage() {
    var form = document.getElementById("searchForm");
    var results = document.getElementById("results");
    var btn = document.getElementById("searchBtn");

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var query = document.getElementById("query").value;
      var max = document.getElementById("max").value || "15";
      var onlyLD = document.getElementById("onlyLD").checked;

      results.innerHTML = "";
      show("toolbar", false);
      show("empty", false);
      show("error", false);
      show("loading", true);
      btn.disabled = true;

      var qs = "?q=" + encodeURIComponent(query) +
        "&max=" + encodeURIComponent(max) +
        "&filter=" + (onlyLD ? "1" : "0");

      fetch("/api/search" + qs)
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (res) {
          show("loading", false);
          btn.disabled = false;
          var data = res.data || {};
          if (!res.ok || data.ok === false) {
            var err = document.getElementById("error");
            err.textContent = "⚠️ " + (data.error || "Search failed. Please try again.");
            show("error", true);
            return;
          }
          var videos = data.videos || [];
          if (!videos.length) {
            show("empty", true);
            return;
          }
          document.getElementById("resultCount").textContent =
            videos.length + " video" + (videos.length === 1 ? "" : "s");
          show("toolbar", true);
          videos.forEach(function (v) { results.appendChild(cardEl(v, "find")); });
        })
        .catch(function (e) {
          show("loading", false);
          btn.disabled = false;
          var err = document.getElementById("error");
          err.textContent = "⚠️ Network error: " + e.message;
          show("error", true);
        });
    });
  }

  /* ---------- Saved page ---------- */

  function renderSavedEmptyState() {
    var grid = document.getElementById("savedGrid");
    var empty = document.getElementById("emptySaved");
    var count = document.getElementById("savedCount");
    if (!grid) return;
    var n = grid.children.length;
    if (empty) empty.classList.toggle("hidden", n > 0);
    if (count) count.textContent = n ? n + " saved" : "";
  }

  function initSavedPage() {
    var grid = document.getElementById("savedGrid");
    var list = getSaved();
    list.forEach(function (v) { grid.appendChild(cardEl(v, "saved")); });
    renderSavedEmptyState();

    var clear = document.getElementById("clearAll");
    clear.addEventListener("click", function () {
      if (!getSaved().length) return;
      if (confirm("Remove all saved videos?")) {
        setSaved([]);
        grid.innerHTML = "";
        renderSavedEmptyState();
      }
    });
  }

  /* ---------- boot ---------- */

  document.addEventListener("DOMContentLoaded", function () {
    updateBadge();
    var page = document.body.getAttribute("data-page");
    if (page === "find") initFindPage();
    else if (page === "saved") initSavedPage();
  });
})();
