/* Fit the provider's minimum-width checkbox without clipping its iframe. */
document.querySelectorAll('.registration-captcha').forEach((container) => {
  const widget = container.querySelector('.smart-captcha');
  if (!widget) return;

  const fit = () => {
    const available = container.clientWidth;
    if (!available) return;
    // Measure the unscaled widget again when the screen or provider DOM changes.
    widget.style.zoom = '1';
    widget.style.width = '100%';
    const width = Math.max(300, widget.scrollWidth);
    const scale = Math.min(1, available / width);
    widget.style.width = scale < 1 ? `${width}px` : '100%';
    widget.style.zoom = String(scale);
  };

  fit();
  // Only child changes: observing our own style writes would cause a loop.
  new MutationObserver(fit).observe(widget, {childList: true, subtree: true});
  if ('ResizeObserver' in window) {
    new ResizeObserver(fit).observe(container);
  } else {
    window.addEventListener('resize', fit);
  }
});
