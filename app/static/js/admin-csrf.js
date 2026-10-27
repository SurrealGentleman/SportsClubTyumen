/* SQLAdmin uses jQuery AJAX for individual and bulk deletion. */
(() => {
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  if (!token) return;
  window.jQuery?.ajaxPrefilter((options, originalOptions, xhr) => {
    const target = new URL(options.url, window.location.href);
    if (target.origin === window.location.origin &&
        !/^(GET|HEAD|OPTIONS)$/i.test(options.type || 'GET')) {
      xhr.setRequestHeader('X-CSRF-Token', token);
    }
  });
  // SQLAdmin's CSV import uses fetch rather than jQuery.
  const originalFetch = window.fetch;
  window.fetch = function (input, init) {
    const request = new Request(input, init);
    if (new URL(request.url).origin === window.location.origin &&
        !/^(GET|HEAD|OPTIONS)$/i.test(request.method)) {
      request.headers.set('X-CSRF-Token', token);
    }
    return originalFetch.call(window, request);
  };
})();
