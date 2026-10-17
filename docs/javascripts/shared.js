// Shared by every sister docs site. The canonical copy is in techne
// (plugins/techne/skills/docs-site/templates/shared/); edit it there and run the
// docs-site sync, never in a site. overrides/main.html loads it.
//
// Two behaviors every page gets:
// - a header button that hides the navigation and table of contents, remembered per
//   reader; overrides/main.html sets data-sidebars before first paint, so a hidden
//   state does not flash the panels in;
// - a table wider than its column becomes a labelled region that takes keyboard
//   focus, so it can be scrolled.
(function () {
  "use strict";
  var KEY = "zensical-sidebars";
  var root = document.documentElement;

  function hidden() {
    return root.getAttribute("data-sidebars") === "hidden";
  }

  function remember(value) {
    try {
      if (value) localStorage.setItem(KEY, value);
      else localStorage.removeItem(KEY);
    } catch (e) {
      /* storage blocked: the toggle still works for this page */
    }
  }

  // A fixed label, with aria-pressed carrying the state (ARIA toggle button pattern).
  function label(button) {
    button.setAttribute("aria-pressed", hidden() ? "true" : "false");
    button.setAttribute("aria-label", "Hide side panels");
    button.title = "Hide side panels";
  }

  function mount() {
    if (document.querySelector(".sidebars-toggle")) return;
    var inner = document.querySelector(".md-header__inner");
    if (!inner) {
      // No header to hold the button: never leave the panels hidden with no way back.
      root.removeAttribute("data-sidebars");
      return;
    }
    var anchor = inner.querySelector(".md-search") || inner.querySelector(".md-header__source");
    var button = document.createElement("button");
    button.type = "button";
    button.className = "sidebars-toggle md-header__button";
    button.innerHTML =
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 4h18a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zm1 2v12h4V6H4zm6 0v12h6V6h-6zm8 0v12h2V6h-2z"/></svg>';
    button.addEventListener("click", function () {
      if (hidden()) {
        root.removeAttribute("data-sidebars");
        remember(null);
      } else {
        root.setAttribute("data-sidebars", "hidden");
        remember("hidden");
      }
      label(button);
    });
    label(button);
    if (anchor) anchor.parentNode.insertBefore(button, anchor);
    else inner.appendChild(button);
  }

  // Each word of inline code in a table goes in a .nobr span, so the line can break
  // at a space and never inside a word. The text, and so copy and paste, is unchanged.
  function wordSpans() {
    var codes = document.querySelectorAll(".md-typeset table:not([class]) :not(pre) > code");
    for (var i = 0; i < codes.length; i++) {
      var code = codes[i];
      if (code.classList.contains("words") || code.children.length) continue;
      var parts = code.textContent.split(/(\s+)/);
      if (parts.length < 2) continue;
      code.textContent = "";
      for (var j = 0; j < parts.length; j++) {
        if (!parts[j]) continue;
        if (/^\s+$/.test(parts[j])) {
          code.appendChild(document.createTextNode(parts[j]));
        } else {
          var span = document.createElement("span");
          span.className = "nobr";
          span.textContent = parts[j];
          code.appendChild(span);
        }
      }
      code.classList.add("words");
    }
  }

  // Zensical's script wraps each table in .md-typeset__scrollwrap, the box that scrolls.
  // A ResizeObserver on the box and its table re-checks it when either changes width:
  // a window resize, the side panels toggling, or web fonts arriving.
  var names = new WeakMap();
  var observer =
    "ResizeObserver" in window
      ? new ResizeObserver(function (entries) {
          for (var i = 0; i < entries.length; i++) {
            var box = entries[i].target.closest(".md-typeset__scrollwrap");
            if (box) region(box);
          }
        })
      : null;

  function region(box) {
    if (box.scrollWidth > box.clientWidth + 1) {
      box.setAttribute("tabindex", "0");
      box.setAttribute("role", "region");
      box.setAttribute("aria-label", names.get(box) || "Table");
    } else {
      box.removeAttribute("tabindex");
      box.removeAttribute("role");
      box.removeAttribute("aria-label");
    }
  }

  function focusableTables() {
    if (observer) observer.disconnect();
    var boxes = document.querySelectorAll(".md-typeset__scrollwrap");
    nameTables(boxes);
    for (var i = 0; i < boxes.length; i++) {
      region(boxes[i]);
      if (observer) {
        observer.observe(boxes[i]);
        if (boxes[i].firstElementChild) observer.observe(boxes[i].firstElementChild);
      }
    }
  }

  // A table's name: its caption, else the nearest heading before it in the article
  // (inside an admonition or tab too), numbered when one heading holds several tables.
  function nameTables(boxes) {
    var counts = new Map();
    var base = [];
    for (var i = 0; i < boxes.length; i++) {
      var caption = boxes[i].querySelector("caption");
      var name = caption ? caption.textContent.trim() : headingBefore(boxes[i]);
      base.push(name);
      counts.set(name, (counts.get(name) || 0) + 1);
    }
    var seen = new Map();
    for (var j = 0; j < boxes.length; j++) {
      var k = (seen.get(base[j]) || 0) + 1;
      seen.set(base[j], k);
      names.set(boxes[j], counts.get(base[j]) > 1 ? base[j] + " " + k : base[j]);
    }
  }

  function headingBefore(box) {
    var article = box.closest("article") || document.body;
    var headings = article.querySelectorAll("h1, h2, h3, h4, h5, h6");
    var heading = null;
    for (var i = 0; i < headings.length; i++) {
      if (headings[i].compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING) {
        heading = headings[i];
      }
    }
    if (!heading) return "Table";
    var copy = heading.cloneNode(true);
    var link = copy.querySelector(".headerlink");
    if (link) link.remove();
    return copy.textContent.trim() + " table";
  }

  function init() {
    mount();
    wordSpans();
    focusableTables();
  }

  if (document.fonts && document.fonts.ready) document.fonts.ready.then(focusableTables);

  if (!observer) window.addEventListener("resize", focusableTables);
  if (window.document$ && typeof window.document$.subscribe === "function") {
    window.document$.subscribe(init);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
