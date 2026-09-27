// Shared by every sister docs site. The canonical copy is in techne
// (plugins/techne/skills/docs-site/templates/shared/); edit it there and run the
// docs-site sync, never in a site. Site-specific effects go in their own file.
//
// Marks pages that open with a `.hero` (`hero-page` on <html> and <body>) and
// reveals each `.landing-section` as it scrolls into view. The CSS keeps sections
// visible until `js-ready` is set, so a reader without JavaScript sees the whole
// page; reduced motion shows every section at once. Re-entrant: instant navigation
// swaps the page without a load, so each run tears down the previous observer.
(function () {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.documentElement.classList.add("js-ready");
  let observer = null;

  function init() {
    if (observer) {
      observer.disconnect();
      observer = null;
    }

    const hero = document.querySelector(".hero") !== null;
    document.documentElement.classList.toggle("hero-page", hero);
    document.body.classList.toggle("hero-page", hero);

    const sections = document.querySelectorAll(".landing-section");
    if (!sections.length) return;

    if (reduceMotion || !("IntersectionObserver" in window)) {
      sections.forEach((s) => s.classList.add("visible"));
      return;
    }

    observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
    );
    sections.forEach((s) => {
      s.classList.remove("visible");
      observer.observe(s);
    });
  }

  if (window.document$ && typeof window.document$.subscribe === "function") {
    window.document$.subscribe(init);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
