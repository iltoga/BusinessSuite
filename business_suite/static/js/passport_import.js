/* Passport import UI behavior
   Extracted from customers/templates/customers/partials/passport_import_section.html
   Exposes initPassportImport(container) to initialize a given container element
   and automatically initializes all containers with data-passport-import="true".
*/
(function () {
  "use strict";

  function fetchJson(url, onSuccess, onError) {
    if (typeof restApiCall === "function") {
      restApiCall("GET", url, null, onSuccess, onError);
      return;
    }
    fetch(url, {
      method: "GET",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (err) {
            throw err;
          });
        }
        return response.json();
      })
      .then(onSuccess)
      .catch(function (err) {
        onError(err || { message: "Request failed" });
      });
  }

  function assignFieldValue(fieldId, value, inputType) {
    if (!value || !fieldId) {
      return;
    }
    if (typeof window.setFormFieldValue === "function") {
      window.setFormFieldValue(fieldId, value, inputType);
      return;
    }
    var field = document.getElementById(fieldId);
    if (field) {
      field.value = value;
      field.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function toggleElement(el, show, className) {
    if (!el) {
      return;
    }
    if (className === "hidden") {
      el.style.display = show ? "" : "none";
      return;
    }
    el.classList[show ? "remove" : "add"]("d-none");
  }

  function handleResponse(config, data) {
    if (!data || !data.mrz_data) {
      return;
    }
    var mrz = data.mrz_data;

    assignFieldValue(config.firstNameId, mrz.names);
    assignFieldValue(config.lastNameId, mrz.surname);
    assignFieldValue(config.genderId, mrz.sex);
    var titleVal = mrz.sex === "M" ? "Mr" : mrz.sex === "F" ? "Ms" : "";
    if (titleVal) {
      assignFieldValue(config.titleId, titleVal);
    }
    assignFieldValue(config.nationalityId, mrz.nationality);
    assignFieldValue(config.birthdateId, mrz.date_of_birth_yyyy_mm_dd, "date");
    assignFieldValue(config.passportNumberId, mrz.number);
    assignFieldValue(
      config.passportExpirationId,
      mrz.expiration_date_yyyy_mm_dd,
      "date",
    );

    if (mrz.passport_issue_date) {
      assignFieldValue(config.passportIssueId, mrz.passport_issue_date, "date");
    } else if (mrz.issue_date_yyyy_mm_dd) {
      assignFieldValue(
        config.passportIssueId,
        mrz.issue_date_yyyy_mm_dd,
        "date",
      );
    }

    if (mrz.birth_place) {
      assignFieldValue(config.birthPlaceId, mrz.birth_place);
    }
    if (mrz.address_abroad) {
      assignFieldValue(config.addressAbroadId, mrz.address_abroad);
    }

    // Log extracted data for debugging
    if (mrz.extraction_method === "hybrid_mrz_ai") {
      if (mrz.ai_confidence_score !== undefined) {
        console.log(
          "AI-enhanced extraction completed. Confidence:",
          mrz.ai_confidence_score,
        );
      }
      // Log all extracted MRZ data as JSON
      try {
        console.log("Extracted MRZ data:", JSON.stringify(mrz, null, 2));
      } catch (e) {
        console.warn("Failed to stringify MRZ data:", e);
      }
    }

    // Return mismatch info for UI handling
    return {
      hasMismatches: mrz.has_mismatches || false,
      fieldMismatches: mrz.field_mismatches || [],
      mismatchSummary: mrz.mismatch_summary || "",
    };
  }

  function initPassportImport(container) {
    if (!container || container.dataset.passportInitialized === "true") {
      return;
    }
    container.dataset.passportInitialized = "true";
    var config = {
      firstNameId: container.dataset.firstNameId,
      lastNameId: container.dataset.lastNameId,
      genderId: container.dataset.genderId,
      titleId: container.dataset.titleId,
      nationalityId: container.dataset.nationalityId,
      birthdateId: container.dataset.birthdateId,
      birthPlaceId: container.dataset.birthPlaceId,
      passportNumberId: container.dataset.passportNumberId,
      passportIssueId: container.dataset.passportIssueId,
      passportExpirationId: container.dataset.passportExpirationId,
      addressAbroadId: container.dataset.addressAbroadId,
      customerTypeSelector: container.dataset.customerTypeSelector,
      ocrUrl: container.dataset.ocrUrl || "/api/ocr/check/",
    };

    var button = container.querySelector(
      '[data-role="passport-import-button"]',
    );
    var buttonText = button
      ? button.querySelector('[data-role="button-text"]')
      : null;
    var spinner = container.querySelector(
      '[data-role="passport-import-spinner"]',
    );
    var errorEl = container.querySelector(
      '[data-role="passport-import-error"]',
    );
    var errorMsg = errorEl
      ? errorEl.querySelector('[data-role="error-message"]')
      : null;
    var successEl = container.querySelector(
      '[data-role="passport-import-success"]',
    );
    var successMsg = successEl
      ? successEl.querySelector('[data-role="success-message"]')
      : null;
    var previewEl = container.querySelector(
      '[data-role="passport-import-preview"]',
    );
    var fileInput = container.querySelector('input[type="file"]');
    var clipboardArea = container.querySelector(
      '[data-role="passport-clipboard-area"]',
    );
    var clipboardPreview = container.querySelector(
      '[data-role="passport-clipboard-preview"]',
    );
    var clipboardStatus = container.querySelector(
      '[data-role="passport-clipboard-status"]',
    );
    var useAiToggle = container.querySelector('[data-role="use-ai-toggle"]');

    function isValidSelector(selector) {
      if (!selector || typeof selector !== "string") return false;
      var s = selector.trim();
      if (!s) return false;
      var leftBrackets = (s.match(/\[/g) || []).length;
      var rightBrackets = (s.match(/\]/g) || []).length;
      if (leftBrackets !== rightBrackets) return false;
      var doubleQuotes = (s.match(/"/g) || []).length;
      var singleQuotes = (s.match(/'/g) || []).length;
      if (doubleQuotes % 2 !== 0 || singleQuotes % 2 !== 0) return false;
      return true;
    }

    function isPersonCustomer() {
      if (!config.customerTypeSelector || config.customerTypeSelector === "") {
        return true;
      }
      var selector = config.customerTypeSelector;
      if (!isValidSelector(selector)) {
        // Selector looks malformed (e.g. 'input[name='). Don't block import, just treat as person customer.
        return true;
      }
      try {
        var el = document.querySelector(selector);
        if (!el) {
          return true;
        }
        if (el.tagName === "SELECT") {
          return el.value !== "company";
        }
        if (el.type === "radio") {
          var checked = document.querySelector(selector + ":checked");
          return !checked || checked.value !== "company";
        }
      } catch (e) {
        // Avoid logging the full SyntaxError which may be noisy. Log a debug message only.
        if (
          typeof console !== "undefined" &&
          typeof console.debug === "function"
        ) {
          console.debug("Invalid customerTypeSelector:", selector);
        }
      }
      return true;
    }

    function isAiEnabled() {
      return useAiToggle && useAiToggle.checked;
    }

    function apiCall(method, url, formData, onSuccess, onError) {
      if (typeof restApiCall === "function") {
        restApiCall(method, url, formData, onSuccess, onError);
        return;
      }
      fetch(url, {
        method: method,
        body: formData,
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then(function (response) {
          if (!response.ok) {
            return response.json().then(function (err) {
              throw err;
            });
          }
          return response.json();
        })
        .then(onSuccess)
        .catch(function (err) {
          onError(err || { message: "Request failed" });
        });
    }

    function pollOcrStatus(statusUrl, onComplete, onError) {
      var attempts = 0;
      var maxAttempts = 90;
      var intervalMs = 2000;

      function poll() {
        attempts += 1;
        fetchJson(
          statusUrl,
          function (data) {
            if (data.status === "completed") {
              onComplete(data);
              return;
            }
            if (data.status === "failed") {
              onError({ message: data.error || "OCR failed" });
              return;
            }
            var progressMsg = "Processing...";
            if (typeof data.progress === "number") {
              progressMsg = "Processing... " + data.progress + "%";
            }
            if (successMsg) successMsg.textContent = progressMsg;
            if (successEl) {
              successEl.classList.remove("alert-warning");
              successEl.classList.add("alert-info");
              toggleElement(successEl, true);
            }
            if (attempts < maxAttempts) {
              setTimeout(poll, intervalMs);
            } else {
              onError({ message: "OCR processing timed out" });
            }
          },
          function (error) {
            onError(error || { message: "OCR status check failed" });
          },
        );
      }

      poll();
    }

    function startUpload(file) {
      if (!file) {
        if (errorMsg) errorMsg.textContent = "No file selected!";
        toggleElement(errorEl, true);
        return;
      }
      toggleElement(errorEl, false);
      toggleElement(successEl, false);
      toggleElement(spinner, true, "class");
      if (button) button.disabled = true;

      var useAi = isAiEnabled();
      var processingText = useAi ? "Processing with AI..." : "Processing...";
      if (buttonText) buttonText.textContent = processingText;

      var formData = new FormData();
      formData.append("file", file);
      formData.append("doc_type", "passport");
      formData.append("img_preview", true);
      formData.append("resize", true);
      formData.append("width", 500);
      formData.append("save_session", true); // Save file and MRZ data to session for customer creation
      if (useAi) {
        formData.append("use_ai", "true");
      }

      function handleSuccess(data) {
        toggleElement(spinner, false, "class");
        if (button) button.disabled = false;
        if (buttonText) buttonText.textContent = "Import";

        var successText = "Data successfully imported via OCR!";
        var hasMismatches = false;
        var mismatchDetails = "";

        if (
          data &&
          data.mrz_data &&
          data.mrz_data.extraction_method === "hybrid_mrz_ai"
        ) {
          var confidence = data.mrz_data.ai_confidence_score || 0;
          successText =
            "Data imported via OCR + AI (confidence: " +
            (confidence * 100).toFixed(0) +
            "%)";

          // Check for field mismatches
          if (data.mrz_data.has_mismatches && data.mrz_data.field_mismatches) {
            hasMismatches = true;
            var mismatches = data.mrz_data.field_mismatches;
            var mismatchLines = [];
            for (var i = 0; i < mismatches.length; i++) {
              var m = mismatches[i];
              mismatchLines.push(
                m.field +
                  ': AI="' +
                  m.ai_value +
                  '" vs MRZ="' +
                  m.mrz_value +
                  '"',
              );
            }
            mismatchDetails = mismatchLines.join("; ");
            console.warn("Field mismatches detected:", mismatchDetails);
          }
        }

        if (data && data.ai_warning) {
          successText =
            "Data imported via OCR (AI validation failed: " +
            data.ai_warning +
            ")";
          if (successMsg) successMsg.textContent = successText;
          if (successEl) successEl.classList.remove("alert-info");
          if (successEl) successEl.classList.remove("alert-success");
          if (successEl) successEl.classList.add("alert-warning");
          toggleElement(successEl, true);
        } else if (hasMismatches) {
          // Show warning with mismatch details
          successText +=
            ". ⚠️ Field mismatches (AI values used): " + mismatchDetails;
          if (successMsg) successMsg.textContent = successText;
          if (successEl) successEl.classList.remove("alert-info");
          if (successEl) successEl.classList.remove("alert-success");
          if (successEl) successEl.classList.add("alert-warning");
          toggleElement(successEl, true);
        } else {
          if (successMsg) successMsg.textContent = successText;
          if (successEl) successEl.classList.remove("alert-info");
          if (successEl) successEl.classList.remove("alert-warning");
          if (successEl) successEl.classList.add("alert-success");
          toggleElement(successEl, true);
        }

        handleResponse(config, data);
        if (data && data.b64_resized_image && previewEl) {
          previewEl.src = "data:image/jpeg;base64," + data.b64_resized_image;
          previewEl.classList.remove("d-none");
        }
      }

      apiCall(
        "POST",
        config.ocrUrl,
        formData,
        function (data) {
          if (
            data &&
            (data.status === "queued" || data.status === "processing") &&
            data.status_url
          ) {
            if (buttonText) buttonText.textContent = "Queued...";
            pollOcrStatus(
              data.status_url,
              function (result) {
                handleSuccess(result);
              },
              function (error) {
                toggleElement(spinner, false, "class");
                if (button) button.disabled = false;
                if (buttonText) buttonText.textContent = "Import";
                if (errorMsg)
                  errorMsg.textContent =
                    (error && error.message) || "OCR failed";
                toggleElement(errorEl, true);
              },
            );
            return;
          }
          handleSuccess(data);
        },
        function (error) {
          toggleElement(spinner, false, "class");
          if (button) button.disabled = false;
          if (buttonText) buttonText.textContent = "Import";
          if (errorMsg)
            errorMsg.textContent =
              (error && error.message) ||
              (error && error.error) ||
              "Upload failed";
          toggleElement(errorEl, true);
        },
      );
    }

    if (button) {
      button.addEventListener("click", function () {
        if (!isPersonCustomer()) {
          alert("Passport import is only available for person customers.");
          return;
        }
        if (!fileInput || !fileInput.files || !fileInput.files[0]) {
          if (errorMsg) errorMsg.textContent = "No file selected!";
          toggleElement(errorEl, true);
          return;
        }
        startUpload(fileInput.files[0]);
      });
    }

    if (clipboardArea) {
      clipboardArea.addEventListener("paste", function (e) {
        if (!isPersonCustomer()) {
          alert("Passport import is only available for person customers.");
          e.preventDefault();
          return;
        }
        var items = (
          e.clipboardData ||
          (e.originalEvent && e.originalEvent.clipboardData)
        ).items;
        if (!items) {
          return;
        }
        for (var i = 0; i < items.length; i++) {
          if (items[i].type && items[i].type.indexOf("image") !== -1) {
            var file = items[i].getAsFile();
            var reader = new FileReader();
            reader.onload = function (evt) {
              if (clipboardPreview) {
                clipboardPreview.src = evt.target.result;
                clipboardPreview.style.display = "block";
              }
            };
            reader.readAsDataURL(file);
            if (clipboardStatus) {
              clipboardStatus.innerHTML =
                '<span class="spinner-border spinner-border-sm"></span> Uploading...';
            }
            startUpload(file);
            if (clipboardStatus) {
              clipboardStatus.innerHTML =
                '<span class="text-success">Image uploaded and processed!</span>';
            }
            e.preventDefault();
            break;
          }
        }
      });
    }
  }

  function ready(fn) {
    if (document.readyState !== "loading") {
      fn();
    } else if (document.addEventListener) {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      document.attachEvent("onreadystatechange", function () {
        if (document.readyState === "complete") fn();
      });
    }
  }

  ready(function () {
    var containers = document.querySelectorAll('[data-passport-import="true"]');
    for (var i = 0; i < containers.length; i++) {
      try {
        initPassportImport(containers[i]);
      } catch (e) {
        console.error("initPassportImport error", e);
      }
    }
  });

  // Expose for manual initialization
  window.initPassportImport = initPassportImport;
})();
