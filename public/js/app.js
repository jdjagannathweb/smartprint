let currentJob = null;
let currentSettings = {
  shop_name: "ସ୍ମାର୍ଟ ପ୍ରିଣ୍ଟ ପଏଣ୍ଟ",
  rate_bw: 2.0,
  rate_color: 10.0,
  currency: "₹"
};

let selectedColorMode = "bw";
let selectedCopies = 1;
let isCustomPages = false;
let statusPollingInterval = null;

// Initialization
document.addEventListener("DOMContentLoaded", async () => {
  await fetchSettings();
  setupDragAndDrop();
});

async function fetchSettings() {
  try {
    const res = await fetch("/api/settings");
    if (res.ok) {
      currentSettings = await res.json();
      document.getElementById("headerShopName").textContent = currentSettings.shop_name || "ସ୍ମାର୍ଟ ପ୍ରିଣ୍ଟ ପଏଣ୍ଟ";
      document.getElementById("rateBwDisplay").textContent = `₹${currentSettings.rate_bw.toFixed(2)} / ପେଜ୍`;
      document.getElementById("rateColorDisplay").textContent = `₹${currentSettings.rate_color.toFixed(2)} / ପେଜ୍`;
    }
  } catch (err) {
    console.error("Error loading settings:", err);
  }
}

// Drag & Drop Setup
function setupDragAndDrop() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");

  ["dragenter", "dragover"].forEach(event => {
    dropzone.addEventListener(event, (e) => {
      e.preventDefault();
      dropzone.style.borderColor = "var(--primary)";
      dropzone.style.background = "#e0f2fe";
    });
  });

  ["dragleave", "drop"].forEach(event => {
    dropzone.addEventListener(event, (e) => {
      e.preventDefault();
      dropzone.style.borderColor = "#93c5fd";
      dropzone.style.background = "var(--primary-light)";
    });
  });

  dropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
  });
}

// Upload Handling
async function handleFileUpload(file) {
  const progress = document.getElementById("uploadProgress");
  progress.style.display = "block";

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      alert("ଅପଲୋଡ୍ ତ୍ରୁଟି: " + (err.detail || "ଫାଇଲ୍ ପ୍ରୋସେସ୍ ହୋଇପାରିଲା ନାହିଁ"));
      progress.style.display = "none";
      return;
    }

    currentJob = await res.json();
    progress.style.display = "none";
    showConfigureStep();
  } catch (err) {
    alert("ଅପଲୋଡ୍ ବିଫଳ ହେଲା: " + err.message);
    progress.style.display = "none";
  }
}

function showConfigureStep() {
  document.getElementById("viewUpload").style.display = "none";
  document.getElementById("viewConfigure").style.display = "block";
  setStepActive(2);

  document.getElementById("docFileName").textContent = currentJob.original_name;
  document.getElementById("docTotalPages").textContent = `ମୋଟ ପେଜ୍: ${currentJob.total_pages}`;
  selectedCopies = 1;
  selectedColorMode = "bw";
  isCustomPages = false;
  document.getElementById("copiesDisplay").textContent = "1";
  document.querySelector('input[name="pageChoice"][value="all"]').checked = true;
  document.getElementById("customPageBox").style.display = "none";
  document.getElementById("customPageInput").value = "";

  selectColorMode("bw");
}

function setStepActive(stepNum) {
  for (let i = 1; i <= 4; i++) {
    const el = document.getElementById(`stepIndicator${i}`);
    el.classList.remove("active", "completed");
    if (i < stepNum) el.classList.add("completed");
    if (i === stepNum) el.classList.add("active");
  }
}

function selectColorMode(mode) {
  selectedColorMode = mode;
  document.getElementById("optBw").classList.toggle("selected", mode === "bw");
  document.getElementById("optColor").classList.toggle("selected", mode === "color");
  updatePricing();
}

function togglePageRange(isCustom) {
  isCustomPages = isCustom;
  document.getElementById("customPageBox").style.display = isCustom ? "block" : "none";
  updatePricing();
}

function changeCopies(delta) {
  selectedCopies = Math.max(1, selectedCopies + delta);
  document.getElementById("copiesDisplay").textContent = selectedCopies;
  updatePricing();
}

function calculateActivePages() {
  if (!currentJob) return 1;
  if (!isCustomPages) return currentJob.total_pages;

  const raw = document.getElementById("customPageInput").value.trim();
  if (!raw) return currentJob.total_pages;

  let count = 0;
  const parts = raw.split(",");
  const visited = new Set();

  for (let part of parts) {
    part = part.trim();
    if (part.includes("-")) {
      const [start, end] = part.split("-").map(n => parseInt(n.trim(), 10));
      if (!isNaN(start) && !isNaN(end)) {
        const s = Math.max(1, Math.min(start, end));
        const e = Math.min(currentJob.total_pages, Math.max(start, end));
        for (let i = s; i <= e; i++) visited.add(i);
      }
    } else {
      const p = parseInt(part, 10);
      if (!isNaN(p) && p >= 1 && p <= currentJob.total_pages) {
        visited.add(p);
      }
    }
  }
  return visited.size || currentJob.total_pages;
}

function updatePricing() {
  if (!currentJob) return;

  const rate = selectedColorMode === "color" ? currentSettings.rate_color : currentSettings.rate_bw;
  const pages = calculateActivePages();
  const total = (pages * selectedCopies * rate).toFixed(2);

  document.getElementById("billPages").textContent = `${pages} ପେଜ୍`;
  document.getElementById("billCopies").textContent = selectedCopies;
  document.getElementById("billRate").textContent = `₹${rate.toFixed(2)}`;
  document.getElementById("billTotal").textContent = `₹${total}`;
  document.getElementById("payBtnAmount").textContent = `₹${total}`;
}

// Proceed to Payment
async function proceedToPayment() {
  const selectedPagesStr = isCustomPages ? (document.getElementById("customPageInput").value.trim() || "all") : "all";

  try {
    const res = await fetch(`/api/jobs/${currentJob.id}/configure`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        copies: selectedCopies,
        color_mode: selectedColorMode,
        selected_pages: selectedPagesStr
      })
    });

    if (!res.ok) {
      alert("କନଫିଗରେସନ୍ ସେଭ୍ ହୋଇପାରିଲା ନାହିଁ");
      return;
    }

    currentJob = await res.json();

    // Show Payment View
    document.getElementById("viewConfigure").style.display = "none";
    document.getElementById("viewPayment").style.display = "block";
    setStepActive(3);

    document.getElementById("payOrderId").textContent = `#${currentJob.id}`;
    document.getElementById("payAmountDisplay").textContent = `₹${currentJob.total_amount.toFixed(2)}`;
    
    // Check if shop has uploaded custom Official Standee QR code image
    if (currentJob.shop_qr_image) {
      document.getElementById("upiQrImg").src = currentJob.shop_qr_image;
    } else {
      document.getElementById("upiQrImg").src = currentJob.qr_code;
    }

    // Set UPI ID for copy box
    const upiId = currentJob.upi_id || currentSettings.upi_id || "9937037131@ybl";
    document.getElementById("displayUpiId").textContent = upiId;

    // Direct UPI App Deep Link
    const upiLink = document.getElementById("btnUpiApp");
    if (currentJob.upi_uri) {
      upiLink.href = currentJob.upi_uri;
      upiLink.style.display = "block";
    } else {
      upiLink.style.display = "none";
    }

  } catch (err) {
    alert("ପେମେଣ୍ଟ୍ ସ୍କ୍ରିନ୍ ଖୋଲିବାରେ ବିଫଳ: " + err.message);
  }
}

function copyUpiId() {
  const upiId = document.getElementById("displayUpiId").textContent.trim();
  if (navigator.clipboard) {
    navigator.clipboard.writeText(upiId).then(() => {
      alert("✅ UPI ID କପି ହେଲା: " + upiId + "\nଆପଣଙ୍କ Google Pay / PhonePe ରେ ପେଷ୍ଟ୍ କରି ପେମେଣ୍ଟ୍ କରନ୍ତୁ।");
    });
  } else {
    alert("UPI ID: " + upiId);
  }
}

function backToConfigure() {
  document.getElementById("viewPayment").style.display = "none";
  document.getElementById("viewConfigure").style.display = "block";
  setStepActive(2);
}

// Customer declares payment sent -> NOTIFIES MERCHANT (DOES NOT PRINT DIRECTLY!)
async function confirmPayment() {
  if (!currentJob) return;

  try {
    const res = await fetch(`/api/jobs/${currentJob.id}/customer-paid`, {
      method: "POST"
    });

    if (!res.ok) {
      alert("ପେମେଣ୍ଟ୍ ସୂଚନା ପଠାଇବାରେ ବିଫଳ ହେଲା");
      return;
    }

    const data = await res.json();
    currentJob = data.job;

    // Show Status View -> Waiting for merchant approval
    document.getElementById("viewPayment").style.display = "none";
    document.getElementById("viewStatus").style.display = "block";
    setStepActive(4);

    document.getElementById("statusOrderId").textContent = `#${currentJob.id}`;
    document.getElementById("statusWaitingMerchant").style.display = "block";
    document.getElementById("statusPrinting").style.display = "none";
    document.getElementById("statusDone").style.display = "none";
    document.getElementById("statusRejected").style.display = "none";
    document.getElementById("statusError").style.display = "none";

    startStatusPolling();
  } catch (err) {
    alert("ତ୍ରୁଟି: " + err.message);
  }
}

function startStatusPolling() {
  if (statusPollingInterval) clearInterval(statusPollingInterval);

  statusPollingInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/jobs/${currentJob.id}`);
      if (res.ok) {
        const job = await res.json();
        currentJob = job;

        if (job.payment_status === "claimed") {
          document.getElementById("statusWaitingMerchant").style.display = "block";
          document.getElementById("statusPrinting").style.display = "none";
          document.getElementById("statusDone").style.display = "none";
        } else if (job.payment_status === "paid") {
          document.getElementById("statusWaitingMerchant").style.display = "none";
          
          if (job.print_status === "printed") {
            clearInterval(statusPollingInterval);
            document.getElementById("statusPrinting").style.display = "none";
            document.getElementById("statusDone").style.display = "block";
          } else if (job.print_status === "failed") {
            clearInterval(statusPollingInterval);
            document.getElementById("statusPrinting").style.display = "none";
            document.getElementById("statusError").style.display = "block";
            document.getElementById("statusErrorMessage").textContent = job.print_error || "ପ୍ରିଣ୍ଟର୍ ସହ ସଂଯୋଗ ହୋଇପାରିଲା ନାହିଁ";
          } else {
            document.getElementById("statusPrinting").style.display = "block";
          }
        } else if (job.payment_status === "rejected") {
          clearInterval(statusPollingInterval);
          document.getElementById("statusWaitingMerchant").style.display = "none";
          document.getElementById("statusPrinting").style.display = "none";
          document.getElementById("statusRejected").style.display = "block";
        }
      }
    } catch (e) {
      console.error("Polling error:", e);
    }
  }, 1500);
}

function resetToUpload() {
  if (statusPollingInterval) clearInterval(statusPollingInterval);
  currentJob = null;
  document.getElementById("fileInput").value = "";
  document.getElementById("viewStatus").style.display = "none";
  document.getElementById("viewConfigure").style.display = "none";
  document.getElementById("viewPayment").style.display = "none";
  document.getElementById("viewUpload").style.display = "block";
  setStepActive(1);
}
