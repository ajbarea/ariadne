/* Scroll-reveal for landing page sections and hero-page body class.
   Re-entrant so Material's instant navigation can rebind cleanly. */
(function () {
  var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Signal to CSS that JS is running so progressive-enhancement rules can apply. */
  document.documentElement.classList.add("js-ready");

  var revealObserver = null;

  function setupReveal() {
    if (revealObserver) {
      revealObserver.disconnect();
      revealObserver = null;
    }

    var hasHero = !!document.querySelector(".hero");
    if (hasHero) {
      document.documentElement.classList.add("hero-page");
      document.body.classList.add("hero-page");
    } else {
      /* Strip lingering hero-page styling from a prior instant-navigation. */
      document.documentElement.classList.remove("hero-page");
      document.body.classList.remove("hero-page");
    }

    var sections = document.querySelectorAll(".landing-section");
    if (!sections.length) return;

    sections.forEach(function (section) {
      section.classList.remove("visible");
    });

    if (prefersReducedMotion) {
      sections.forEach(function (section) {
        section.classList.add("visible");
      });
      return;
    }

    revealObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 }
    );

    sections.forEach(function (section) {
      revealObserver.observe(section);
    });
  }

  /* Material theme's instant navigation uses the document$ RxJS observable */
  if (typeof document$ !== "undefined") {
    document$.subscribe(setupReveal);
  } else {
    document.addEventListener("DOMContentLoaded", setupReveal);
  }
})();
