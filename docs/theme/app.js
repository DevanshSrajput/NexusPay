/* NexusPay Docs — progressive enhancement: theme, SPA nav, scrollspy, copy. */
(function () {
  "use strict";

  /* ── Theme ─────────────────────────────────────────────────────────── */
  var root = document.documentElement;
  function applyTheme(t) {
    root.setAttribute("data-theme", t);
    try { localStorage.setItem("np-theme", t); } catch (e) {}
  }
  (function initTheme() {
    var saved;
    try { saved = localStorage.getItem("np-theme"); } catch (e) {}
    if (!saved) {
      saved = window.matchMedia &&
        window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    }
    root.setAttribute("data-theme", saved);
  })();

  /* ── Copy buttons on code blocks ───────────────────────────────────── */
  var COPY_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
  var CHECK_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
  function addCopyButtons(scope) {
    var blocks = scope.querySelectorAll(".doc pre, .doc .codehilite");
    blocks.forEach(function (block) {
      if (block.querySelector(".copy-btn")) return;
      var btn = document.createElement("button");
      btn.className = "copy-btn";
      btn.type = "button";
      btn.setAttribute("aria-label", "Copy code");
      btn.innerHTML = COPY_SVG;
      btn.addEventListener("click", function () {
        var code = block.querySelector("code") || block.querySelector("pre") || block;
        navigator.clipboard.writeText(code.innerText.replace(/\n$/, "")).then(function () {
          btn.innerHTML = CHECK_SVG; btn.classList.add("copied");
          setTimeout(function () { btn.innerHTML = COPY_SVG; btn.classList.remove("copied"); }, 1600);
        });
      });
      block.appendChild(btn);
    });
  }

  /* ── TOC scrollspy ─────────────────────────────────────────────────── */
  var spy = null;
  function initScrollSpy() {
    if (spy) { spy.disconnect(); spy = null; }
    var links = Array.prototype.slice.call(document.querySelectorAll(".toc a[href^='#']"));
    if (!links.length) return;
    var map = {};
    links.forEach(function (a) {
      var id = decodeURIComponent(a.getAttribute("href").slice(1));
      var el = document.getElementById(id);
      if (el) map[id] = a;
    });
    spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          links.forEach(function (a) { a.classList.remove("active"); });
          var a = map[en.target.id];
          if (a) a.classList.add("active");
        }
      });
    }, { rootMargin: "-70px 0px -70% 0px", threshold: 0 });
    Object.keys(map).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) spy.observe(el);
    });
  }

  /* ── Enhance a freshly-rendered page ───────────────────────────────── */
  function enhance() {
    addCopyButtons(document);
    initScrollSpy();
    var doc = document.querySelector(".doc");
    if (doc) {
      doc.classList.remove("animate");
      void doc.offsetWidth;       // restart entrance animation
      doc.classList.add("animate");
    }
  }

  /* ── SPA router ────────────────────────────────────────────────────── */
  function samePage(href) { return href.split("#")[0] === location.href.split("#")[0]; }

  function swapTo(url, push) {
    fetch(url, { headers: { "X-Requested-With": "spa" } })
      .then(function (r) { return r.text(); })
      .then(function (htmlText) {
        var parsed = new DOMParser().parseFromString(htmlText, "text/html");
        var nextShell = parsed.querySelector(".shell");
        var curShell = document.querySelector(".shell");
        if (!nextShell || !curShell) { location.href = url; return; }
        curShell.replaceWith(nextShell);
        document.title = parsed.title;
        var desc = parsed.querySelector('meta[name="description"]');
        var curDesc = document.querySelector('meta[name="description"]');
        if (desc && curDesc) curDesc.setAttribute("content", desc.getAttribute("content"));
        if (push) history.pushState({ spa: true }, "", url);
        updateActiveNav();
        enhance();
        var hash = url.indexOf("#") > -1 ? url.slice(url.indexOf("#") + 1) : "";
        if (hash) {
          var t = document.getElementById(decodeURIComponent(hash));
          if (t) t.scrollIntoView();
        } else {
          window.scrollTo(0, 0);
        }
        document.body.classList.remove("nav-open");
      })
      .catch(function () { location.href = url; });
  }

  function updateActiveNav() {
    var here = location.pathname.replace(/index\.html$/, "").replace(/\/$/, "");
    document.querySelectorAll(".sidebar nav a, .topnav a").forEach(function (a) {
      var u;
      try { u = new URL(a.href); } catch (e) { return; }
      if (a.getAttribute("href").indexOf("#") === 0) return;
      var there = u.pathname.replace(/index\.html$/, "").replace(/\/$/, "");
      var match = there === here;
      a.classList.toggle("active", match && a.closest(".sidebar"));
      if (a.closest(".topnav")) { if (match) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); }
    });
  }

  document.addEventListener("click", function (e) {
    // theme toggle
    var tg = e.target.closest("#theme-btn");
    if (tg) { applyTheme(root.getAttribute("data-theme") === "light" ? "dark" : "light"); return; }
    // mobile menu
    var mb = e.target.closest("#menu-btn");
    if (mb) { document.body.classList.toggle("nav-open"); return; }
    if (e.target.closest(".sidebar-scrim")) { document.body.classList.remove("nav-open"); return; }

    // SPA link interception
    var a = e.target.closest("a");
    if (!a) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    if (a.target === "_blank" || a.hasAttribute("download") || a.dataset.noSpa !== undefined) return;
    var href = a.getAttribute("href");
    if (!href || href.indexOf("#") === 0) return;            // in-page anchor: native
    var url;
    try { url = new URL(a.href); } catch (err) { return; }
    if (url.origin !== location.origin) return;               // external
    if (!/\.html$|\/$/.test(url.pathname)) return;            // not a doc page (e.g. .md)
    e.preventDefault();
    if (samePage(a.href) && url.hash) {
      var t = document.getElementById(decodeURIComponent(url.hash.slice(1)));
      if (t) { history.pushState({ spa: true }, "", a.href); t.scrollIntoView(); }
      return;
    }
    swapTo(a.href, true);
  });

  window.addEventListener("popstate", function () { swapTo(location.href, false); });

  /* ── Boot ──────────────────────────────────────────────────────────── */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { enhance(); updateActiveNav(); });
  } else { enhance(); updateActiveNav(); }
})();
