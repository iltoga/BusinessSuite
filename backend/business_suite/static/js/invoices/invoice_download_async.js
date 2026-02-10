/* Invoice async PDF download with progress bar */
(function () {
  "use strict";

  function getCsrfToken() {
    var name = "csrftoken=";
    var decodedCookie = decodeURIComponent(document.cookie || "");
    var cookies = decodedCookie.split(";");
    for (var i = 0; i < cookies.length; i++) {
      var cookie = cookies[i].trim();
      if (cookie.indexOf(name) === 0) {
        return cookie.substring(name.length, cookie.length);
      }
    }
    return "";
  }

  function setProgress(container, progress, message) {
    var progressWrapper = container.querySelector(
      "[data-invoice-download-progress]",
    );
    var progressBar = container.querySelector("[data-invoice-download-bar]");
    var progressText = container.querySelector("[data-invoice-download-text]");
    if (!progressWrapper || !progressBar || !progressText) return;

    progressWrapper.classList.remove("d-none");
    progressBar.style.width = progress + "%";
    if (message) {
      progressText.textContent = message;
    }
  }

  function setError(container, message) {
    setProgress(container, 100, message || "Download failed");
    var progressBar = container.querySelector("[data-invoice-download-bar]");
    if (progressBar) {
      progressBar.classList.add("bg-danger");
    }
  }

  function startDownload(container) {
    var startUrl = container.dataset.startUrl;
    if (!startUrl || container.dataset.loading === "true") return;

    container.dataset.loading = "true";
    setProgress(container, 5, "Starting PDF generation...");

    fetch(startUrl, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ format: "pdf" }),
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Failed to start download");
        }
        return response.json();
      })
      .then(function (payload) {
        if (!payload || !payload.stream_url) {
          throw new Error("Missing stream URL");
        }
        var streamUrl = payload.stream_url;
        var downloadUrl = payload.download_url;

        var eventSource = new EventSource(streamUrl);
        eventSource.addEventListener("start", function (event) {
          try {
            var data = JSON.parse(event.data || "{}");
            setProgress(
              container,
              data.progress || 5,
              data.message || "Starting PDF generation...",
            );
          } catch (e) {
            setProgress(container, 5, "Starting PDF generation...");
          }
        });

        eventSource.addEventListener("progress", function (event) {
          try {
            var data = JSON.parse(event.data || "{}");
            var progress =
              typeof data.progress === "number" ? data.progress : 0;
            setProgress(container, progress, "Generating PDF...");
          } catch (e) {
            setProgress(container, 50, "Generating PDF...");
          }
        });

        eventSource.addEventListener("complete", function (event) {
          eventSource.close();
          setProgress(container, 100, "Download starting...");
          container.dataset.loading = "false";
          if (downloadUrl) {
            window.location.assign(downloadUrl);
          }
          // Hide progress bar after a short delay
          setTimeout(function () {
            var progressWrapper = container.querySelector(
              "[data-invoice-download-progress]",
            );
            if (progressWrapper) {
              progressWrapper.classList.add("d-none");
            }
          }, 2000);
        });

        eventSource.addEventListener("error", function (event) {
          eventSource.close();
          setError(container, "PDF generation failed");
          container.dataset.loading = "false";
          // Hide error after a delay
          setTimeout(function () {
            var progressWrapper = container.querySelector(
              "[data-invoice-download-progress]",
            );
            if (progressWrapper) {
              progressWrapper.classList.add("d-none");
            }
          }, 5000);
        });
      })
      .catch(function (error) {
        setError(container, error.message || "Download failed");
        container.dataset.loading = "false";
      });
  }

  function bindContainer(container) {
    var pdfButton = container.querySelector("[data-invoice-download-pdf]");
    if (!pdfButton) return;

    pdfButton.addEventListener("click", function (event) {
      event.preventDefault();
      startDownload(container);
    });
  }

  function init() {
    var containers = document.querySelectorAll(
      "[data-invoice-download-container]",
    );
    containers.forEach(function (container) {
      bindContainer(container);
    });
  }

  if (document.readyState !== "loading") {
    init();
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
