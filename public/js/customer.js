let currentShop = null;
let currentJob = null;
let selectedColorMode = "bw";
let selectedPrintSide = "single";
let selectedCopies = 1;
let isCustomPages = false;
let statusPollingInterval = null;
let paytmPollInterval = null;
let phonepePollInterval = null;
let smbupiPollInterval = null;
let unifiedStatusPollInterval = null;

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
    const rateBw = parseFloat(data.rate_bw || 2.0).toFixed(2);
    const rateDbBw = parseFloat(data.rate_double_bw || 3.0).toFixed(2);
    const rateCol = parseFloat(data.rate_color || 10.0).toFixed(2);
    const rateDbCol = parseFloat(data.rate_double_color || 15.0).toFixed(2);

    document.getElementById("rateBwDisplay").textContent = `₹${rateBw} (୨-ପାଖ: ₹${rateDbBw}/କାଗଜ)`;
    document.getElementById("rateColorDisplay").textContent = `₹${rateCol} (୨-ପାଖ: ₹${rateDbCol}/କାଗଜ)`;
    document.getElementById("cfgBwRateLabel").textContent = `₹${rateBw} / ପେଜ୍`;
    document.getElementById("cfgColorRateLabel").textContent = `₹${rateCol} / ପେଜ୍`;
    updateSideRateHints();

    // Shop custom standee QR if exists
    if (data.shop_qr_image) {
      document.getElementById("shopStandeeImg").src = data.shop_qr_image;
      document.getElementById("shopStandeeContainer").style.display = "block";
    }

    // Check if customer returning from payment gateway with ?job=JOB-XXXX
    const urlParams = new URLSearchParams(window.location.search);
    const returnJobId = urlParams.get("job");
    if (returnJobId) {
      await resumeJobPaymentStatus(returnJobId);
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
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesSelected(e.dataTransfer.files);
    }
  });
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text).replace(/[&<>"']/g, m => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[m]);
}

function renderFilesList(filesInfo, originalName) {
  const container = document.getElementById("filesListContainer");
  const countBadge = document.getElementById("filesCountBadge");
  if (!container) return;

  let list = Array.isArray(filesInfo) && filesInfo.length > 0 ? filesInfo : [];
  if (list.length === 0 && originalName) {
    list = [{ name: originalName, pages: currentJob?.total_pages || 1, type: "pdf" }];
  }

  if (countBadge) countBadge.textContent = list.length;

  if (list.length === 0) {
    container.innerHTML = `<div style="font-size:0.8rem;color:#94a3b8;padding:6px;text-align:center;">କୌଣସି ଫାଇଲ୍ ଯୋଡ଼ା ହୋଇନାହିଁ</div>`;
    return;
  }

  container.innerHTML = list.map((f, idx) => {
    const isImg = f.type === "image" || /\.(jpe?g|png|webp|bmp)$/i.test(f.name);
    const icon = isImg ? "🖼️" : "📄";
    const pagesText = (f.pages || 1) + " ପେଜ୍";
    return `
      <div style="display:flex;align-items:center;justify-content:space-between;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:6px 10px;font-size:0.82rem;">
        <div style="display:flex;align-items:center;gap:8px;overflow:hidden;flex:1;min-width:0;">
          <span style="font-size:1.1rem;flex-shrink:0;">${icon}</span>
          <span style="font-weight:600;color:#1e293b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(f.name)}">
            ${escapeHtml(f.name)}
          </span>
        </div>
        <span style="background:#f1f5f9;color:#0284c7;font-weight:700;font-size:0.76rem;padding:2px 8px;border-radius:999px;white-space:nowrap;margin-left:8px;flex-shrink:0;">
          ${pagesText}
        </span>
      </div>
    `;
  }).join("");
}

async function handleFilesSelected(files) {
  if (!files || files.length === 0) return;
  if (!currentShop) {
    alert("ଦୋକାନ ସୂଚନା ଲୋଡ୍ ହୋଇନାହିଁ। ଦୟାକରି ପୃଷ୍ଠା ରିଫ୍ରେସ୍ କରନ୍ତୁ।");
    return;
  }

  document.getElementById("dropzone").style.display = "none";
  document.getElementById("uploadProgress").style.display = "block";

  const formData = new FormData();
  formData.append("shop_id", currentShop.shop_id);
  for (let i = 0; i < files.length; i++) {
    formData.append("files", files[i]);
  }

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

    const filesInfo = data.files_info || currentJob.files_info || [];
    renderFilesList(filesInfo, currentJob.original_name);

    selectedCopies = 1;
    selectedColorMode = "bw";
    selectedPrintSide = "single";
    isCustomPages = false;
    document.getElementById("copiesDisplay").textContent = "1";
    document.getElementById("customPageInputBox").style.display = "none";
    document.getElementById("btnAllPages").className = "btn btn-sm btn-primary";
    document.getElementById("btnCustomPages").className = "btn btn-sm btn-outline";
    document.getElementById("modeBw").className = "mode-card selected";
    document.getElementById("modeColor").className = "mode-card";
    const sideS = document.getElementById("sideSingle");
    if (sideS) sideS.className = "mode-card selected";
    const sideD = document.getElementById("sideDouble");
    if (sideD) sideD.className = "mode-card";

    calculateTotal();
    setStep(2);
  } catch (err) {
    alert("ଭୁଲ୍: " + err.message);
    resetFlow();
  }
}

function handleFileSelected(file) {
  if (file) handleFilesSelected([file]);
}

async function handleAddMoreFiles(files) {
  if (!files || files.length === 0 || !currentJob) return;

  const countBadge = document.getElementById("filesCountBadge");
  const origBadgeText = countBadge ? countBadge.textContent : "";
  if (countBadge) countBadge.textContent = "⏳...";

  const formData = new FormData();
  for (let i = 0; i < files.length; i++) {
    formData.append("files", files[i]);
  }

  try {
    const res = await fetch(`/api/customer/jobs/${currentJob.id}/add-files`, {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "ଆଉ ଏକ ଫାଇଲ୍ ଯୋଡ଼ିବା ବିଫଳ ହେଲା!");
    }

    currentJob = Object.assign({}, currentJob, data.job || {}, data);
    document.getElementById("cfgFileName").textContent = currentJob.original_name || "Documents";
    document.getElementById("cfgTotalPages").textContent = currentJob.total_pages || 1;

    const filesInfo = data.files_info || currentJob.files_info || [];
    renderFilesList(filesInfo, currentJob.original_name);

    calculateTotal();
  } catch (err) {
    alert("ଭୁଲ୍: " + err.message);
    if (countBadge) countBadge.textContent = origBadgeText;
  } finally {
    const fileAddInput = document.getElementById("fileInputAddMore");
    if (fileAddInput) fileAddInput.value = "";
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

function updateSideRateHints() {
  if (!currentShop) return;
  const isColor = selectedColorMode === "color";
  const rateSingle = isColor ? parseFloat(currentShop.rate_color || 10.0) : parseFloat(currentShop.rate_bw || 2.0);
  const rateDouble = isColor ? parseFloat(currentShop.rate_double_color || (rateSingle * 1.5)) : parseFloat(currentShop.rate_double_bw || 3.0);
  
  const hintSingle = document.getElementById("sideSingleRateHint");
  if (hintSingle) hintSingle.textContent = `₹${rateSingle.toFixed(2)} / ପେଜ୍ (୧ ପୃଷ୍ଠା/କାଗଜ)`;
  const hintDouble = document.getElementById("sideDoubleRateHint");
  if (hintDouble) hintDouble.textContent = `₹${rateDouble.toFixed(2)} / କାଗଜ (୨ ପୃଷ୍ଠା/Duplex)`;
}

function setColorMode(mode) {
  selectedColorMode = mode;
  document.getElementById("modeBw").className = mode === "bw" ? "mode-card selected" : "mode-card";
  document.getElementById("modeColor").className = mode === "color" ? "mode-card selected" : "mode-card";
  updateSideRateHints();
  calculateTotal();
}

function setPrintSide(side) {
  selectedPrintSide = side;
  const sideS = document.getElementById("sideSingle");
  if (sideS) sideS.className = side === "single" ? "mode-card selected" : "mode-card";
  const sideD = document.getElementById("sideDouble");
  if (sideD) sideD.className = side === "double" ? "mode-card selected" : "mode-card";
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
  const isColor = selectedColorMode === "color";
  const rateSingle = isColor ? parseFloat(currentShop.rate_color || 10.0) : parseFloat(currentShop.rate_bw || 2.0);
  const rateDouble = isColor ? parseFloat(currentShop.rate_double_color || (rateSingle * 1.5)) : parseFloat(currentShop.rate_double_bw || 3.0);

  const isDouble = selectedPrintSide === "double";
  let total = 0;
  if (isDouble) {
    const doubleSheets = Math.floor(numPages / 2);
    const singleSheets = numPages % 2;
    total = ((doubleSheets * rateDouble) + (singleSheets * rateSingle)) * selectedCopies;
  } else {
    total = numPages * selectedCopies * rateSingle;
  }

  const sheetsPerCopy = isDouble ? Math.ceil(numPages / 2) : numPages;
  const totalSheets = sheetsPerCopy * selectedCopies;

  document.getElementById("sumPrintPages").textContent = `${numPages} ପେଜ୍`;
  const printSideEl = document.getElementById("sumPrintSide");
  if (printSideEl) {
    printSideEl.textContent = isDouble ? "ଉଭୟ ପାଖ (Double Sided)" : "ଗୋଟିଏ ପାଖ (1-Side)";
  }
  const sheetsEl = document.getElementById("sumSheets");
  if (sheetsEl) {
    sheetsEl.textContent = `${totalSheets} ଟି କାଗଜ ${isDouble ? "(ଉଭୟ ପାଖ)" : ""}`;
  }
  document.getElementById("sumCopies").textContent = `${selectedCopies} କପି`;
  const sumRateEl = document.getElementById("sumRate");
  if (sumRateEl) {
    sumRateEl.textContent = isDouble ? `₹${rateDouble.toFixed(2)} / କାଗଜ (୨-ପାଖ)` : `₹${rateSingle.toFixed(2)} / ପେଜ୍`;
  }
  document.getElementById("sumTotal").textContent = `₹${total.toFixed(2)}`;
}

function buildUpiIntentUri(job, shop) {
  if (job && job.upi_intent && String(job.upi_intent).startsWith("upi://")) {
    return job.upi_intent;
  }
  if (job && job.upi_uri && String(job.upi_uri).startsWith("upi://")) {
    return job.upi_uri;
  }
  const vpa = job?.upi_id || shop?.upi_id || shop?.paytm_vpa || "";
  if (!vpa) return "";
  const name = encodeURIComponent(shop?.shop_name || "SmartPrint");
  const amt = parseFloat(job?.total_amount || 0).toFixed(2);
  const note = encodeURIComponent(`Print #${(job?.id || '').slice(-6)}`);
  return `upi://pay?pa=${encodeURIComponent(vpa)}&pn=${name}&am=${amt}&cu=INR&tn=${note}&tr=${encodeURIComponent(job?.id || '')}`;
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
        print_side: selectedPrintSide,
        selected_pages: rangeStr || "all",
        page_range: rangeStr || "all"
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error configuring job");

    // Robust merge: ensure all URLs, flags, and QR codes from data and data.job are preserved!
    currentJob = Object.assign({}, currentJob, data.job || {}, data);

    // Show Step 3
    const totalAmt = parseFloat(currentJob.total_amount || 0).toFixed(2);
    document.getElementById("payAmountDisplay").textContent = `₹${totalAmt}`;
    
    // SMB UPI (Universal Gateway)
    const isSmbUpi = Boolean(currentJob.is_smbupi_auto && (currentJob.smbupi_pay_url || currentJob.smbupi_upi_url));
    const smbupiBox = document.getElementById("smbupiAutoDetectBox");
    const btnSmbUpi = document.getElementById("btnSmbUpiPay");

    if (smbupiBox) {
      smbupiBox.style.display = isSmbUpi ? "block" : "none";
    }
    if (btnSmbUpi) {
      btnSmbUpi.href = currentJob.smbupi_payment_url || currentJob.smbupi_upi_url || "#";
      btnSmbUpi.target = "_blank";
    }

    // QR image with foolproof fallback
    let qrSrc = currentJob.qr_code || currentJob.qr_code_base64 || data.qr_code || data.qr_code_base64 || "";
    if (!qrSrc && currentJob.upi_uri) {
      qrSrc = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(currentJob.upi_uri)}`;
    }
    const qrImg = document.getElementById("payQrImage");
    if (qrImg && qrSrc) {
      qrImg.src = qrSrc;
      qrImg.style.display = "inline-block";
    }
    
    // Shop custom standee QR (ONLY display if NOT using auto gateway)
    const standeeImg = currentJob.shop_qr_image || currentShop?.shop_qr_image;
    if (standeeImg && !isSmbUpi) {
      document.getElementById("shopStandeeImg").src = standeeImg;
      document.getElementById("shopStandeeContainer").style.display = "block";
    } else {
      document.getElementById("shopStandeeContainer").style.display = "none";
    }

    const upiVpa = currentJob.upi_id || currentShop?.upi_id || "";
    const vpaBox = document.getElementById("upiCopyBox");
    const vpaText = document.getElementById("textUpiVpa");
    if (upiVpa) {
      vpaText.textContent = upiVpa;
      vpaBox.style.display = "flex";
    } else {
      vpaBox.style.display = "none";
    }

    // Configure direct UPI links and intent queries
    const upiUri = buildUpiIntentUri(currentJob, currentShop);
    const rawQuery = upiUri.includes("?") ? upiUri.split("?")[1] : "";

    const directUpiBtn = document.getElementById("directUpiPayLink");
    const phonepeBtn = document.getElementById("quickPhonepeLink");
    const gpayBtn = document.getElementById("quickGpayLink");
    const paytmBtn = document.getElementById("quickPaytmLink");

    if (directUpiBtn) {
      directUpiBtn.href = upiUri || (currentJob.smbupi_payment_url || currentJob.smbupi_upi_url || "#");
      directUpiBtn.onclick = null;
    }
    if (phonepeBtn) {
      phonepeBtn.href = rawQuery ? `phonepe://pay?${rawQuery}` : (upiUri || "#");
      phonepeBtn.onclick = null;
    }
    if (gpayBtn) {
      gpayBtn.href = rawQuery ? `gpay://upi/pay?${rawQuery}` : (upiUri || "#");
      gpayBtn.onclick = null;
    }
    if (paytmBtn) {
      paytmBtn.href = rawQuery ? `paytmmp://pay?${rawQuery}` : (upiUri || "#");
      paytmBtn.onclick = null;
    }

    // PhonePe Standard Checkout
    const isPhonePe = Boolean(currentJob.is_phonepe_auto && currentJob.phonepe_pay_url);
    const phonepeBox = document.getElementById("phonepeAutoDetectBox");
    const btnPhonePe = document.getElementById("btnPhonePePay");
    if (phonepeBox) {
      phonepeBox.style.display = isPhonePe ? "block" : "none";
    }
    if (btnPhonePe && currentJob.phonepe_pay_url) {
      btnPhonePe.href = currentJob.phonepe_pay_url;
      btnPhonePe.target = "_blank";
    }

    // Paytm Business
    const isPaytm = Boolean(currentJob.is_paytm_auto);
    const paytmBox = document.getElementById("paytmAutoDetectBox");
    if (paytmBox) {
      paytmBox.style.display = isPaytm ? "block" : "none";
    }

    // START AUTO-VERIFICATION SERVICES IMMEDIATELY
    if (isSmbUpi) {
      startSmbUpiAutoVerification(currentJob.id);
    }
    if (isPaytm) {
      startPaytmAutoVerification(currentJob.id);
    }
    if (isPhonePe) {
      startPhonePeAutoVerification(currentJob.id);
    }

    startUnifiedStatusPolling(currentJob.id);

    setStep(3);

    // On mobile devices, show friendly guide banner
    const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    const redirectNotice = document.getElementById("autoRedirectNotice");
    if (redirectNotice) {
      redirectNotice.style.display = isMobileDevice ? "block" : "none";
    }

  } catch (err) {
    alert("ଭୁଲ୍: " + err.message);
  }
}

function triggerPayApp(target, event) {
  if (event && event.preventDefault) event.preventDefault();
  if (!currentJob) return;

  const upiUri = buildUpiIntentUri(currentJob, currentShop);
  const rawQuery = upiUri.includes("?") ? upiUri.split("?")[1] : "";

  if (target === "smbupi_upi" || target === "smbupi") {
    const upiPayUrl = currentJob.smbupi_payment_url || currentJob.smbupi_upi_url;
    if (upiPayUrl) window.open(upiPayUrl, "_blank");
    return;
  }

  if (target === "phonepe") {
    const targetUrl = rawQuery ? `phonepe://pay?${rawQuery}` : upiUri;
    if (targetUrl) window.location.href = targetUrl;
    return;
  }

  if (target === "gpay") {
    const targetUrl = rawQuery ? `gpay://upi/pay?${rawQuery}` : upiUri;
    if (targetUrl) window.location.href = targetUrl;
    return;
  }

  if (target === "paytm") {
    const targetUrl = rawQuery ? `paytmmp://pay?${rawQuery}` : upiUri;
    if (targetUrl) window.location.href = targetUrl;
    return;
  }

  // Universal fallback
  if (upiUri) {
    window.location.href = upiUri;
  } else if (currentJob.smbupi_payment_url || currentJob.smbupi_upi_url) {
    window.open(currentJob.smbupi_payment_url || currentJob.smbupi_upi_url, "_blank");
  } else {
    alert("UPI Payment ଲିଙ୍କ୍ ପ୍ରସ୍ତୁତ ହୋଇପାରିଲା ନାହିଁ। ଦୟାକରି QR କୋଡ୍ ସ୍କାନ୍ କରନ୍ତୁ କିମ୍ବା UPI ID କପି କରନ୍ତୁ।");
  }
}

async function resumeJobPaymentStatus(jobId) {
  try {
    // If returning from SMB Gateway redirect (callback), check verification immediately
    const urlParams = new URLSearchParams(window.location.search);
    const hasPaidParam = urlParams.has("smbpaid") || urlParams.has("paid");
    if (hasPaidParam) {
      try {
        const verifyRes = await fetch(`/api/customer/jobs/${jobId}/check-smbupi-status`, {
          method: "POST"
        });
        if (verifyRes.ok) {
          const verifyData = await verifyRes.json();
          if (verifyData.status === "success" || verifyData.success || (verifyData.job && verifyData.job.payment_status === "paid")) {
            currentJob = verifyData.job || currentJob;
            setStep(4);
            document.getElementById("waitingTitle").textContent = "⚡ ପେମେଣ୍ଟ୍ ସଫଳ (Verified)!";
            document.getElementById("waitingDesc").textContent = "SMB UPI ରୁ ପେମେଣ୍ଟ୍ କନଫର୍ମ ହୋଇଛି! ପ୍ରିଣ୍ଟର୍ ରୁ କାଗଜ ବାହାରୁଛି...";
            startPollingPrintStatus();
            return;
          }
        }
      } catch (checkErr) {
        console.warn("Immediate gateway return check:", checkErr);
      }
    }

    const res = await fetch(`/api/customer/jobs/${jobId}/status`);
    if (!res.ok) return;
    const job = await res.json();
    currentJob = job;

    if (job.payment_status === "paid" || job.print_status === "printed" || job.print_status === "printing") {
      setStep(4);
      document.getElementById("waitingTitle").textContent = "⚡ ପେମେଣ୍ଟ୍ ସଫଳ (Verified)!";
      document.getElementById("waitingDesc").textContent = "ପେମେଣ୍ଟ୍ କନଫର୍ମ ହୋଇଛି! ପ୍ରିଣ୍ଟର୍ ରୁ କାଗଜ ବାହାରୁଛି...";
      startPollingPrintStatus();
    } else {
      if (job.is_smbupi_auto || job.payment_method === "smbupi") {
        startSmbUpiAutoVerification(job.id);
      }
      if (job.is_phonepe_auto || job.payment_method === "phonepe") {
        startPhonePeAutoVerification(job.id);
      }
      if (job.is_paytm_auto || job.payment_method === "paytm_qr") {
        startPaytmAutoVerification(job.id);
      }
      startUnifiedStatusPolling(job.id);
      setStep(3);
    }
  } catch (e) {
    console.error("Error resuming job payment status:", e);
  }
}

function startUnifiedStatusPolling(jobId) {
  if (unifiedStatusPollInterval) clearInterval(unifiedStatusPollInterval);

  unifiedStatusPollInterval = setInterval(async () => {
    if (!currentJob || currentJob.id !== jobId) {
      clearInterval(unifiedStatusPollInterval);
      unifiedStatusPollInterval = null;
      return;
    }

    try {
      const res = await fetch(`/api/customer/jobs/${jobId}/status`);
      if (!res.ok) return;
      const job = await res.json();
      if (job.payment_status === "paid" || job.print_status === "printing" || job.print_status === "printed") {
        clearInterval(unifiedStatusPollInterval);
        unifiedStatusPollInterval = null;
        if (smbupiPollInterval) { clearInterval(smbupiPollInterval); smbupiPollInterval = null; }
        if (paytmPollInterval) { clearInterval(paytmPollInterval); paytmPollInterval = null; }
        if (phonepePollInterval) { clearInterval(phonepePollInterval); phonepePollInterval = null; }

        currentJob = job;
        setStep(4);
        document.getElementById("waitingTitle").textContent = "⚡ ପେମେଣ୍ଟ୍ ସଫଳ (Verified)!";
        document.getElementById("waitingDesc").textContent = "ପେମେଣ୍ଟ୍ କନଫର୍ମ ହୋଇଛି! ପ୍ରିଣ୍ଟର୍ ରୁ କାଗଜ ବାହାରୁଛି...";
        startPollingPrintStatus();
      }
    } catch (e) {
      console.log("Unified status polling error:", e);
    }
  }, 2500);
}

function startSmbUpiAutoVerification(jobId) {
  if (smbupiPollInterval) clearInterval(smbupiPollInterval);

  const checkStatus = async () => {
    if (!currentJob || currentJob.id !== jobId) {
      clearInterval(smbupiPollInterval);
      smbupiPollInterval = null;
      return;
    }

    try {
      const res = await fetch(`/api/customer/jobs/${jobId}/check-smbupi-status`, {
        method: "POST"
      });
      if (!res.ok) return;

      const data = await res.json();
      if (data.status === "success" || data.success || (data.job && data.job.payment_status === "paid")) {
        clearInterval(smbupiPollInterval);
        smbupiPollInterval = null;
        if (unifiedStatusPollInterval) { clearInterval(unifiedStatusPollInterval); unifiedStatusPollInterval = null; }

        currentJob = data.job || currentJob;

        // Auto transition to Step 4
        setStep(4);
        document.getElementById("waitingTitle").textContent = "⚡ SMB UPI ପେମେଣ୍ଟ୍ ସଫଳ (0% Verified)!";
        document.getElementById("waitingDesc").textContent = "UPI ପେମେଣ୍ଟ୍ କନଫର୍ମ ହୋଇଛି! ପ୍ରିଣ୍ଟର୍ ରୁ କାଗଜ ବାହାରୁଛି...";
        startPollingPrintStatus();
      }
    } catch (err) {
      console.log("SMB UPI auto-verification polling error:", err);
    }
  };

  // Immediate check
  checkStatus();
  // Poll every 2500ms
  smbupiPollInterval = setInterval(checkStatus, 2500);
}

function startPhonePeAutoVerification(jobId) {
  if (phonepePollInterval) clearInterval(phonepePollInterval);

  const checkStatus = async () => {
    if (!currentJob || currentJob.id !== jobId) {
      clearInterval(phonepePollInterval);
      phonepePollInterval = null;
      return;
    }

    try {
      const res = await fetch(`/api/customer/jobs/${jobId}/check-phonepe-status`, {
        method: "POST"
      });
      if (!res.ok) return;

      const data = await res.json();
      if (data.status === "COMPLETED" || (data.job && data.job.payment_status === "paid")) {
        clearInterval(phonepePollInterval);
        phonepePollInterval = null;
        if (unifiedStatusPollInterval) { clearInterval(unifiedStatusPollInterval); unifiedStatusPollInterval = null; }

        currentJob = data.job || currentJob;

        // Auto transition to Step 4
        setStep(4);
        document.getElementById("waitingTitle").textContent = "⚡ PhonePe ପେମେଣ୍ଟ୍ ସଫଳ (Verified)!";
        document.getElementById("waitingDesc").textContent = "PhonePe Standard Checkout ରୁ ପେମେଣ୍ଟ୍ କନଫର୍ମ ହୋଇଛି! ପ୍ରିଣ୍ଟର୍ ରୁ କାଗଜ ବାହାରୁଛି...";
        startPollingPrintStatus();
      }
    } catch (err) {
      console.log("PhonePe auto-verification polling error:", err);
    }
  };

  checkStatus();
  phonepePollInterval = setInterval(checkStatus, 2500);
}

function startPaytmAutoVerification(jobId) {
  if (paytmPollInterval) clearInterval(paytmPollInterval);

  const checkStatus = async () => {
    if (!currentJob || currentJob.id !== jobId) {
      clearInterval(paytmPollInterval);
      paytmPollInterval = null;
      return;
    }

    try {
      const res = await fetch(`/api/customer/jobs/${jobId}/check-paytm-status`, {
        method: "POST"
      });
      if (!res.ok) return;

      const data = await res.json();
      if (data.status === "TXN_SUCCESS" || (data.job && data.job.payment_status === "paid")) {
        clearInterval(paytmPollInterval);
        paytmPollInterval = null;
        if (unifiedStatusPollInterval) { clearInterval(unifiedStatusPollInterval); unifiedStatusPollInterval = null; }

        currentJob = data.job || currentJob;

        // Auto transition to Step 4
        setStep(4);
        document.getElementById("waitingTitle").textContent = "⚡ ପେମେଣ୍ଟ୍ ସଫଳ (0% Fee Verified)!";
        document.getElementById("waitingDesc").textContent = "Paytm Business ସାହାଯ୍ୟରେ ପେମେଣ୍ଟ୍ କନଫର୍ମ ହୋଇଛି! ପ୍ରିଣ୍ଟର୍ ରୁ କାଗଜ ବାହାରୁଛି...";
        startPollingPrintStatus();
      }
    } catch (err) {
      console.log("Paytm auto-verification polling error:", err);
    }
  };

  checkStatus();
  paytmPollInterval = setInterval(checkStatus, 2500);
}

function copyUpiId() {
  const upi = currentJob?.upi_id || currentShop?.upi_id || "";
  if (!upi) return;
  navigator.clipboard.writeText(upi).then(() => {
    alert(`✅ UPI ID (${upi}) କପି ହୋଇଗଲା!\nଆପଣଙ୍କ PhonePe କିମ୍ବା Google Pay ରେ Paste କରି ପେମେଣ୍ଟ୍ କରନ୍ତୁ।`);
  }).catch(() => {
    prompt("ଏହି UPI ID କପି କରନ୍ତୁ:", upi);
  });
}

async function claimPaymentDone() {
  if (!currentJob) return;

  const btn = document.getElementById("btnClaimPaid");
  btn.disabled = true;
  btn.textContent = "⏳ ଯାଞ୍ଚ ହେଉଛି (Verifying Payment)...";

  try {
    const res = await fetch(`/api/customer/jobs/${currentJob.id}/pay-claimed`, {
      method: "POST"
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Claim failed");

    // If backend auto-verified via SMB UPI or Paytm:
    if (data.verified || data.auto_printed || (data.job && data.job.payment_status === "paid")) {
      currentJob = data.job || currentJob;
      setStep(4);
      document.getElementById("waitingTitle").textContent = "⚡ ପେମେଣ୍ଟ୍ ସଫଳ (Verified)!";
      document.getElementById("waitingDesc").textContent = "ପେମେଣ୍ଟ୍ କନଫର୍ମ ହୋଇଛି! ପ୍ରିଣ୍ଟର୍ ରୁ କାଗଜ ବାହାରୁଛି...";
      startPollingPrintStatus();
      return;
    }

    // Otherwise show waiting for merchant confirmation, while keeping gateway polls active
    setStep(4);
    document.getElementById("waitingTitle").textContent = "⏳ ଦୋକାନୀ ଯାଞ୍ଚ କରୁଛନ୍ତି...";
    document.getElementById("waitingDesc").textContent = "ଆପଣଙ୍କ ପେମେଣ୍ଟ୍ ସୂଚନା ଦୋକାନୀଙ୍କ ଡ୍ୟାସବୋର୍ଡକୁ ପଠାଗଲା। କନଫର୍ମ ହେବା ମାତ୍ରେ କାଗଜ ପ୍ରିଣ୍ଟ୍ ବାହାରିବ।";
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
        currentJob = job;
        if (job.print_status === "printed") {
          clearInterval(statusPollingInterval);
          statusPollingInterval = null;
          document.getElementById("waitingIcon").style.display = "none";
          document.getElementById("waitingTitle").style.display = "none";
          document.getElementById("waitingDesc").style.display = "none";
          document.getElementById("printSuccessArea").style.display = "block";
        } else if (job.payment_status === "paid" && (job.print_status === "printing" || job.print_status === "queued")) {
          document.getElementById("waitingTitle").textContent = "🖨️ ପ୍ରିଣ୍ଟ୍ ହେଉଛି...";
          document.getElementById("waitingDesc").textContent = "ପେମେଣ୍ଟ୍ କନଫର୍ମ ହୋଇଛି! ପ୍ରିଣ୍ଟର୍ ରୁ କାଗଜ ବାହାରୁଛି...";
        }
      }
    } catch (e) {
      console.log("Polling error:", e);
    }
  }, 2000);
}

function resetFlow() {
  if (statusPollingInterval) { clearInterval(statusPollingInterval); statusPollingInterval = null; }
  if (paytmPollInterval) { clearInterval(paytmPollInterval); paytmPollInterval = null; }
  if (phonepePollInterval) { clearInterval(phonepePollInterval); phonepePollInterval = null; }
  if (smbupiPollInterval) { clearInterval(smbupiPollInterval); smbupiPollInterval = null; }
  if (unifiedStatusPollInterval) { clearInterval(unifiedStatusPollInterval); unifiedStatusPollInterval = null; }

  currentJob = null;
  const fileInput = document.getElementById("fileInput");
  if (fileInput) fileInput.value = "";
  const fileInputAddMore = document.getElementById("fileInputAddMore");
  if (fileInputAddMore) fileInputAddMore.value = "";

  const filesListContainer = document.getElementById("filesListContainer");
  if (filesListContainer) filesListContainer.innerHTML = "";
  const filesCountBadge = document.getElementById("filesCountBadge");
  if (filesCountBadge) filesCountBadge.textContent = "1";

  document.getElementById("dropzone").style.display = "block";
  document.getElementById("uploadProgress").style.display = "none";
  document.getElementById("printSuccessArea").style.display = "none";
  document.getElementById("waitingIcon").style.display = "block";
  document.getElementById("waitingTitle").style.display = "block";
  document.getElementById("waitingTitle").textContent = "ଦୋକାନୀ ଯାଞ୍ଚ କରୁଛନ୍ତି...";
  document.getElementById("waitingDesc").style.display = "block";
  document.getElementById("waitingDesc").textContent = "ଆପଣଙ୍କ ପେମେଣ୍ଟ୍ ସୂଚନା ଦୋକାନୀଙ୍କ ଡ୍ୟାସବୋର୍ଡରେ ଦେଖାଯାଉଛି। ସେ ଯାଞ୍ଚ କରି କନଫର୍ମ କଲେ ପ୍ରିଣ୍ଟର୍ ରୁ କାଗଜ ବାହାରିବ।";

  const btnClaim = document.getElementById("btnClaimPaid");
  if (btnClaim) {
    btnClaim.disabled = false;
    btnClaim.textContent = "✅ ମୁଁ ପେମେଣ୍ଟ୍ କରିସାରିଛି (Payment Done)";
  }

  setStep(1);
}

function downloadPayQr() {
  const qrImg = document.getElementById("payQrImage");
  if (!qrImg || !qrImg.src) {
    alert("⚠️ QR କୋଡ୍ ଲୋଡ୍ ହୋଇନାହିଁ!");
    return;
  }
  const link = document.createElement("a");
  link.href = qrImg.src;
  link.download = `SmartPrint-Payment-${currentJob?.id || "order"}.png`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
