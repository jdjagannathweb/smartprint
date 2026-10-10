let currentShop = null;
let currentJob = null;
let selectedColorMode = "bw";
let selectedCopies = 1;
let isCustomPages = false;
let statusPollingInterval = null;

document.addEventListener("DOMContentLoaded", async () => {
  await initShop();
  setupDragAndDrop();
});

function getSlugFromPath() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  if (parts.length >= 2 && parts[0] === "s") {
    return parts[1];
  }
  // Check URL search params ?shop=...
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("shop")) {
    return urlParams.get("shop");
  }
  return "smart-print";
}

async function initShop() {
  const slug = getSlugFromPath();
  try {
    const res = await fetch(`/api/customer/shop/${slug}`);
    if (!res.ok) {
      showInactiveShop("ଏହି ଦୋକାନ ମିଳିଲା ନାହିଁ। ଦୟାକରି ଲିଙ୍କ୍ ଯାଞ୍ଚ କରନ୍ତୁ।");
      return;
    }
    const data = await res.json();
    currentShop = data;

    if (!data.is_active || !data.subscription_valid) {
      showInactiveShop("ଏହି ଦୋକାନର ଅନଲାଇନ୍ ସେବା ସାମୟିକ ଭାବେ ବନ୍ଦ ଅଛି କିମ୍ବା ସବସ୍କ୍ରିପସନ୍ ସମାପ୍ତ ହୋଇଛି।");
      return;
    }

    // Populate UI
    document.getElementById("headerShopName").textContent = data.shop_name;
    document.getElementById("rateBwDisplay").textContent = `₹${parseFloat(data.rate_bw).toFixed(2)}`;
    document.getElementById("rateColorDisplay").textContent = `₹${parseFloat(data.rate_color).toFixed(2)}`;
    document.getElementById("cfgBwRateLabel").textContent = `₹${parseFloat(data.rate_bw).toFixed(2)} / ପେଜ୍`;
    document.getElementById("cfgColorRateLabel").textContent = `₹${parseFloat(data.rate_color).toFixed(2)} / ପେଜ୍`;

    // Shop custom standee QR if exists
    if (data.shop_qr_image) {
      document.getElementById("shopStandeeImg").src = data.shop_qr_image;
      document.getElementById("shopStandeeContainer").style.display = "block";
    }

  } catch (err) {
    console.error("Shop init error:", err);
    showInactiveShop("ସର୍ଭର ସହିତ ସଂଯୋଗ ହୋଇପାରିଲା ନାହିଁ।");
  }
}

function showInactiveShop(msg) {
  document.getElementById("customerAppBody").style.display = "none";
  const alertCard = document.getElementById("shopInactiveCard");
  alertCard.style.display = "block";
  if (msg) alertCard.querySelector("p").textContent = msg;
}

function setupDragAndDrop() {
  const dropzone = document.getElementById("dropzone");
  if (!dropzone) return;

  ["dragenter", "dragover"].forEach(evt => {
    dropzone.addEventListener(evt, e => {
      e.preventDefault();
      dropzone.style.borderColor = "var(--primary)";
      dropzone.style.background = "#e0f2fe";
    });
  });

  ["dragleave", "drop"].forEach(evt => {
    dropzone.addEventListener(evt, e => {
      e.preventDefault();
      dropzone.style.borderColor = "#93c5fd";
      dropzone.style.background = "var(--primary-light)";
    });
  });

  dropzone.addEventListener("drop", e => {
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });
}

async function handleFileSelected(file) {
  if (!file) return;
  if (!currentShop) {
    alert("ଦୋକାନ ସୂଚନା ଲୋଡ୍ ହୋଇନାହିଁ। ଦୟାକରି ପୃଷ୍ଠା ରିଫ୍ରେସ୍ କରନ୍ତୁ।");
    return;
  }

  document.getElementById("dropzone").style.display = "none";
  document.getElementById("uploadProgress").style.display = "block";

  const formData = new FormData();
  formData.append("shop_id", currentShop.shop_id);
  formData.append("file", file);

  try {
    const res = await fetch("/api/customer/upload", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "ଫାଇଲ୍ ଅପଲୋଡ୍ ବିଫଳ ହେଲା!");
    }

    currentJob = data.job || data;
    if (!currentJob) throw new Error("Job data not found in response");

    // Transition to Step 2
    document.getElementById("cfgFileName").textContent = currentJob.original_name || "Document";
    document.getElementById("cfgTotalPages").textContent = currentJob.total_pages || 1;

    selectedCopies = 1;
    selectedColorMode = "bw";
    isCustomPages = false;
    document.getElementById("copiesDisplay").textContent = "1";
    document.getElementById("customPageInputBox").style.display = "none";
    document.getElementById("btnAllPages").className = "btn btn-sm btn-primary";
    document.getElementById("btnCustomPages").className = "btn btn-sm btn-outline";
    document.getElementById("modeBw").className = "mode-card selected";
    document.getElementById("modeColor").className = "mode-card";

    calculateTotal();

    setStep(2);
  } catch (err) {
    alert("ଭୁଲ୍: " + err.message);
    resetFlow();
  }
}

function setStep(stepNum) {
  document.getElementById("stepUpload").style.display = stepNum === 1 ? "block" : "none";
  document.getElementById("stepConfig").style.display = stepNum === 2 ? "block" : "none";
  document.getElementById("stepPayment").style.display = stepNum === 3 ? "block" : "none";
  document.getElementById("stepWaiting").style.display = stepNum === 4 ? "block" : "none";

  for (let i = 1; i <= 4; i++) {
    const ind = document.getElementById(`stepIndicator${i}`);
    if (i < stepNum) {
      ind.className = "step-item completed";
    } else if (i === stepNum) {
      ind.className = "step-item active";
    } else {
      ind.className = "step-item";
    }
  }
}

function setColorMode(mode) {
  selectedColorMode = mode;
  document.getElementById("modeBw").className = mode === "bw" ? "mode-card selected" : "mode-card";
  document.getElementById("modeColor").className = mode === "color" ? "mode-card selected" : "mode-card";
  calculateTotal();
}

function changeCopies(delta) {
  selectedCopies = Math.max(1, selectedCopies + delta);
  document.getElementById("copiesDisplay").textContent = selectedCopies;
  calculateTotal();
}

function setPageMode(mode) {
  isCustomPages = (mode === "custom");
  document.getElementById("btnAllPages").className = !isCustomPages ? "btn btn-sm btn-primary" : "btn btn-sm btn-outline";
  document.getElementById("btnCustomPages").className = isCustomPages ? "btn btn-sm btn-primary" : "btn btn-sm btn-outline";
  document.getElementById("customPageInputBox").style.display = isCustomPages ? "block" : "none";
  calculateTotal();
}

function getCalculatedPages() {
  if (!currentJob) return 1;
  if (!isCustomPages) return currentJob.total_pages;

  const rangeStr = document.getElementById("customPageInput").value.trim();
  if (!rangeStr) return currentJob.total_pages;

  try {
    const parts = rangeStr.split(",");
    const set = new Set();
    for (const part of parts) {
      if (part.includes("-")) {
        const [start, end] = part.split("-").map(n => parseInt(n.trim(), 10));
        if (!isNaN(start) && !isNaN(end)) {
          for (let p = Math.max(1, start); p <= Math.min(currentJob.total_pages, end); p++) {
            set.add(p);
          }
        }
      } else {
        const p = parseInt(part.trim(), 10);
        if (!isNaN(p) && p >= 1 && p <= currentJob.total_pages) {
          set.add(p);
        }
      }
    }
    return set.size > 0 ? set.size : currentJob.total_pages;
  } catch (e) {
    return currentJob.total_pages;
  }
}

function calculateTotal() {
  if (!currentJob || !currentShop) return;
  const numPages = getCalculatedPages();
  const rate = selectedColorMode === "color" ? parseFloat(currentShop.rate_color) : parseFloat(currentShop.rate_bw);
  const total = numPages * selectedCopies * rate;

  document.getElementById("sumPrintPages").textContent = `${numPages} ପେଜ୍`;
  document.getElementById("sumCopies").textContent = `${selectedCopies} କପି`;
  document.getElementById("sumRate").textContent = `₹${rate.toFixed(2)}`;
  document.getElementById("sumTotal").textContent = `₹${total.toFixed(2)}`;
}

async function proceedToPayment() {
  if (!currentJob) return;

  const numPages = getCalculatedPages();
  const rangeStr = isCustomPages ? document.getElementById("customPageInput").value.trim() : "";

  try {
    const res = await fetch(`/api/customer/jobs/${currentJob.id}/configure`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        color_mode: selectedColorMode,
        copies: selectedCopies,
        selected_pages: rangeStr || "all",
        page_range: rangeStr || "all"
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error configuring job");

    currentJob = data.job || data;

    // Show Step 3
    const totalAmt = parseFloat(currentJob.total_amount || 0).toFixed(2);
    document.getElementById("payAmountDisplay").textContent = `₹${totalAmt}`;
    
    // QR image
    const qrSrc = currentJob.qr_code || currentJob.qr_code_base64 || "";
    if (qrSrc) {
      document.getElementById("payQrImage").src = qrSrc;
    }
    
    // Shop custom standee QR if uploaded
    const standeeImg = currentJob.shop_qr_image || currentShop?.shop_qr_image;
    if (standeeImg) {
      document.getElementById("shopStandeeImg").src = standeeImg;
      document.getElementById("shopStandeeContainer").style.display = "block";
    } else {
      document.getElementById("shopStandeeContainer").style.display = "none";
    }

    if (currentJob.upi_uri) {
      document.getElementById("directUpiPayLink").href = currentJob.upi_uri;
      document.getElementById("directUpiPayLink").style.display = "inline-block";
    } else {
      document.getElementById("directUpiPayLink").style.display = "none";
    }

    setStep(3);
  } catch (err) {
    alert("ଭୁଲ୍: " + err.message);
  }
}

async function claimPaymentDone() {
  if (!currentJob) return;
  const btn = document.getElementById("btnClaimPaid");
  btn.disabled = true;
  btn.textContent = "⏳ ଯାଞ୍ଚ ଅନୁରୋଧ ପଠାଯାଉଛି...";

  try {
    const res = await fetch(`/api/customer/jobs/${currentJob.id}/pay-claimed`, {
      method: "POST"
    });
    if (!res.ok) throw new Error("Claim failed");

    setStep(4);
    startPollingPrintStatus();
  } catch (err) {
    alert("ଭୁଲ୍: " + err.message);
    btn.disabled = false;
    btn.textContent = "✅ ମୁଁ ପେମେଣ୍ଟ୍ କରିସାରିଛି (Payment Done)";
  }
}

function startPollingPrintStatus() {
  if (statusPollingInterval) clearInterval(statusPollingInterval);

  statusPollingInterval = setInterval(async () => {
    if (!currentJob) return;
    try {
      const res = await fetch(`/api/customer/jobs/${currentJob.id}/status`);
      if (res.ok) {
        const job = await res.json();
        if (job.print_status === "printed") {
          clearInterval(statusPollingInterval);
          document.getElementById("waitingIcon").style.display = "none";
          document.getElementById("waitingTitle").style.display = "none";
          document.getElementById("waitingDesc").style.display = "none";
          document.getElementById("printSuccessArea").style.display = "block";
        } else if (job.payment_status === "paid" && job.print_status === "printing") {
          document.getElementById("waitingTitle").textContent = "🖨️ ପ୍ରିଣ୍ଟ୍ ହେଉଛି...";
          document.getElementById("waitingDesc").textContent = "ଦୋକାନୀ ଅନୁମୋଦନ କରିଛନ୍ତି! ପ୍ରିଣ୍ଟର୍ ରୁ କାଗଜ ବାହାରୁଛି...";
        }
      }
    } catch (e) {
      console.log("Polling error:", e);
    }
  }, 2000);
}

function resetFlow() {
  if (statusPollingInterval) clearInterval(statusPollingInterval);
  currentJob = null;
  document.getElementById("fileInput").value = "";
  document.getElementById("dropzone").style.display = "block";
  document.getElementById("uploadProgress").style.display = "none";
  document.getElementById("printSuccessArea").style.display = "none";
  document.getElementById("waitingIcon").style.display = "block";
  document.getElementById("waitingTitle").style.display = "block";
  document.getElementById("waitingTitle").textContent = "ଦୋକାନୀ ଯାଞ୍ଚ କରୁଛନ୍ତି...";
  document.getElementById("waitingDesc").style.display = "block";
  document.getElementById("waitingDesc").textContent = "ଆପଣଙ୍କ ପେମେଣ୍ଟ୍ ସୂଚନା ଦୋକାନୀଙ୍କ ଡ୍ୟାସବୋର୍ଡରେ ଦେଖାଯାଉଛି। ସେ ଯାଞ୍ଚ କରି କନଫର୍ମ କଲେ ପ୍ରିଣ୍ଟର୍ ରୁ କାଗଜ ବାହାରିବ।";
  setStep(1);
}
