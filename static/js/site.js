(() => {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => { if (entry.isIntersecting) entry.target.classList.add('is-visible'); });
  }, { threshold: 0.12 });
  document.querySelectorAll('[data-reveal]').forEach((el) => observer.observe(el));
  const tilt = document.querySelector('[data-tilt]');
  if (tilt && matchMedia('(pointer:fine)').matches) {
    tilt.addEventListener('mousemove', (e) => {
      const r = tilt.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - .5;
      const y = (e.clientY - r.top) / r.height - .5;
      tilt.style.transform = `perspective(1200px) rotateX(${-y * 2.2}deg) rotateY(${x * 3.2}deg)`;
    });
    tilt.addEventListener('mouseleave', () => { tilt.style.transform = ''; });
  }
})();
