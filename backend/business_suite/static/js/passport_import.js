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
      credentials: "same-origin",
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

  function normalizeStatusUrl(url) {
    if (!url || typeof url !== "string") {
      return url;
    }
    try {
      var resolved = new URL(url, window.location.origin);
      if (
        window.location.protocol === "https:" &&
        resolved.protocol === "http:"
      ) {
        resolved.protocol = "https:";
      }
      if (resolved.origin !== window.location.origin) {
        return (
          window.location.origin +
          resolved.pathname +
          resolved.search +
          resolved.hash
        );
      }
      return resolved.toString();
    } catch (e) {
      return url;
    }
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

  // Helper to get a value from either camelCase or snake_case property
  function getMrzValue(mrz, camelKey, snakeKey) {
    if (mrz[camelKey] !== undefined) return mrz[camelKey];
    if (snakeKey && mrz[snakeKey] !== undefined) return mrz[snakeKey];
    return undefined;
  }

  function handleResponse(config, data) {
    // Check for both mrzData (camelCase) and mrz_data (snake_case)
    var mrz = data && (data.mrzData || data.mrz_data);
    if (!mrz) {
      return;
    }

    assignFieldValue(config.firstNameId, mrz.names);
    assignFieldValue(config.lastNameId, mrz.surname);
    assignFieldValue(config.genderId, mrz.sex);
    var titleVal = mrz.sex === "M" ? "Mr" : mrz.sex === "F" ? "Ms" : "";
    if (titleVal) {
      assignFieldValue(config.titleId, titleVal);
    }
    assignFieldValue(config.nationalityId, mrz.nationality);

    // Date of birth - check both camelCase and snake_case
    var dob = getMrzValue(
      mrz,
      "dateOfBirthYyyyMmDd",
      "date_of_birth_yyyy_mm_dd",
    );
    assignFieldValue(config.birthdateId, dob, "date");

    assignFieldValue(config.passportNumberId, mrz.number);

    // Expiration date - check both camelCase and snake_case
    var expDate = getMrzValue(
      mrz,
      "expirationDateYyyyMmDd",
      "expiration_date_yyyy_mm_dd",
    );
    assignFieldValue(config.passportExpirationId, expDate, "date");

    // Issue date - check multiple possible field names in both cases
    var issueDate =
      getMrzValue(mrz, "passportIssueDate", "passport_issue_date") ||
      getMrzValue(mrz, "issueDateYyyyMmDd", "issue_date_yyyy_mm_dd");
    if (issueDate) {
      assignFieldValue(config.passportIssueId, issueDate, "date");
    }

    // Birth place - check both cases
    var birthPlace = getMrzValue(mrz, "birthPlace", "birth_place");
    if (birthPlace) {
      assignFieldValue(config.birthPlaceId, birthPlace);
    }

    // Address abroad - check both cases
    var addressAbroad = getMrzValue(mrz, "addressAbroad", "address_abroad");
    if (addressAbroad) {
      assignFieldValue(config.addressAbroadId, addressAbroad);
    }

    // Check extraction method - both cases
    var extractionMethod = getMrzValue(
      mrz,
      "extractionMethod",
      "extraction_method",
    );
    if (
      extractionMethod === "hybrid_mrz_ai" ||
      extractionMethod === "hybridMrzAi" ||
      extractionMethod === "ai_only"
    ) {
      var confidence = getMrzValue(
        mrz,
        "aiConfidenceScore",
        "ai_confidence_score",
      );
      if (confidence !== undefined) {
        console.log(
          "AI-enhanced extraction completed. Confidence:",
          confidence,
        );
      }
    }

    // Log all extracted MRZ data as JSON for debugging
    try {
      console.log("Extracted Passport data:", JSON.stringify(mrz, null, 2));
    } catch (e) {
      console.warn("Failed to stringify MRZ data:", e);
    }

    // Return mismatch info for UI handling - check both cases
    return {
      hasMismatches:
        getMrzValue(mrz, "hasMismatches", "has_mismatches") || false,
      fieldMismatches:
        getMrzValue(mrz, "fieldMismatches", "field_mismatches") || [],
      mismatchSummary:
        getMrzValue(mrz, "mismatchSummary", "mismatch_summary") || "",
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
        credentials: "same-origin",
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
            var status = data && data.status ? data.status.toLowerCase() : "";
            if (status === "completed") {
              onComplete(data);
              return;
            }
            if (status === "failed") {
              onError({ message: data.error || "OCR failed" });
              return;
            }
            var progressMsg = "Processing...";
            if (typeof data.progress === "number") {
              progressMsg = "Processing... " + data.progress + "%";
            }
            if (successMsg) successMsg.textContent = progressMsg;
            if (buttonText) buttonText.textContent = progressMsg;
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
        // Log received data for debugging
        console.log("OCR handleSuccess called with data:", data);

        // If we still have a "queued" or "processing" status here, it means something called handleSuccess too early
        var status = data && data.status ? data.status.toLowerCase() : "";
        if (
          data &&
          (status === "queued" ||
            status === "processing" ||
            status === "pending")
        ) {
          console.warn(
            "handleSuccess called while job still in progress:",
            status,
          );
          return;
        }

        toggleElement(spinner, false, "class");
        if (button) button.disabled = false;
        if (buttonText) buttonText.textContent = "Import";

        // Check for both mrzData (camelCase) and mrz_data (snake_case)
        var mrz = data && (data.mrzData || data.mrz_data);
        if (!mrz) {
          console.error("OCR completed but mrz_data/mrzData is missing:", data);
          if (errorMsg)
            errorMsg.textContent = "OCR completed but no data was extracted.";
          toggleElement(errorEl, true);
          toggleElement(successEl, false);
          return;
        }

        var successText = "Data successfully imported via OCR!";
        var hasMismatches = false;
        var mismatchDetails = "";

        // Check extraction method - both camelCase and snake_case
        var extractionMethod = getMrzValue(
          mrz,
          "extractionMethod",
          "extraction_method",
        );
        if (
          extractionMethod === "hybrid_mrz_ai" ||
          extractionMethod === "hybridMrzAi" ||
          extractionMethod === "ai_only"
        ) {
          var confidence =
            getMrzValue(mrz, "aiConfidenceScore", "ai_confidence_score") || 0;

          if (extractionMethod === "ai_only") {
            successText =
              "Data imported via AI (Passport OCR failed, confidence: " +
              (confidence * 100).toFixed(0) +
              "%)";
          } else {
            successText =
              "Data imported via OCR + AI (confidence: " +
              (confidence * 100).toFixed(0) +
              "%)";
          }

          // Check for field mismatches - both cases
          var hasMismatchesFlag = getMrzValue(
            mrz,
            "hasMismatches",
            "has_mismatches",
          );
          var fieldMismatches = getMrzValue(
            mrz,
            "fieldMismatches",
            "field_mismatches",
          );
          if (hasMismatchesFlag && fieldMismatches) {
            hasMismatches = true;
            var mismatchLines = [];
            for (var i = 0; i < fieldMismatches.length; i++) {
              var m = fieldMismatches[i];
              // Handle both camelCase and snake_case in mismatch object
              var mField = m.field;
              var mAiValue = m.aiValue || m.ai_value;
              var mMrzValue = m.mrzValue || m.mrz_value;
              mismatchLines.push(
                mField + ': AI="' + mAiValue + '" vs MRZ="' + mMrzValue + '"',
              );
            }
            mismatchDetails = mismatchLines.join("; ");
            console.warn("Field mismatches detected:", mismatchDetails);
          }
        }

        // Check AI warning - both cases
        var aiWarning = data.aiWarning || data.ai_warning;
        if (aiWarning) {
          successText =
            "Data imported via OCR (AI validation failed: " + aiWarning + ")";
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
        // Check both camelCase and snake_case for image preview
        var previewUrl = data.previewUrl || data.preview_url;
        var previewImage = data.b64ResizedImage || data.b64_resized_image;
        if (previewEl && previewUrl) {
          previewEl.src = previewUrl;
          previewEl.classList.remove("d-none");
        } else if (previewImage && previewEl) {
          previewEl.src = "data:image/jpeg;base64," + previewImage;
          previewEl.classList.remove("d-none");
        }
      }

      apiCall(
        "POST",
        config.ocrUrl,
        formData,
        function (data) {
          console.log("OCR POST response received:", data);
          var status = data && data.status ? data.status.toLowerCase() : "";
          var statusUrl = (data && (data.status_url || data.statusUrl)) || "";
          if (
            data &&
            (status === "queued" ||
              status === "processing" ||
              status === "pending") &&
            statusUrl
          ) {
            if (buttonText) buttonText.textContent = "Queued...";
            var normalizedStatusUrl = normalizeStatusUrl(statusUrl);
            console.log("OCR status URL:", normalizedStatusUrl);
            pollOcrStatus(
              normalizedStatusUrl,
              function (result) {
                console.log("OCR polling completed:", result);
                handleSuccess(result);
              },
              function (error) {
                console.error("OCR polling failed:", error);
                toggleElement(spinner, false, "class");
                if (button) button.disabled = false;
                if (buttonText) buttonText.textContent = "Import";
                if (errorMsg)
                  errorMsg.textContent =
                    (error && error.message) || "OCR failed";
                toggleElement(errorEl, true);
                toggleElement(successEl, false);
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
