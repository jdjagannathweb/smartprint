let currentShopId = localStorage.getItem("current_shop_id") || "SHP-818D63";
let currentShop = null;
let availablePrinters = [];
let knownClaimedJobIds = new Set();
let audioContext = null;
let selectedModalPlan = "plan2";

document.addEventListener("DOMContentLoaded", async () => {
  // If not in localStorage, default or redirect
  if (!localStorage.getItem("current_shop_id")) {
    localStorage.setItem("current_shop_id", currentShopId);
  }

  await loadShopDetails();
  await loadPrinters();
  await loadJobsTable();

  // Polling every 3s
  setInterval(loadJobsTable, 3000);
});

function playNotificationChime() {
  try {
    if (!audioContext) {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    const osc = audioContext.createOscillator();
    const gain = audioContext.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(587.33, audioContext.currentTime); // D5
    osc.frequency.setValueAtTime(880.00, audioContext.currentTime + 0.15); // A5
    gain.gain.setValueAtTime(0.3, audioContext.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
    osc.connect(gain);
    gain.connect(audioContext.destination);
    osc.start();
    osc.stop(audioContext.currentTime + 0.5);
  } catch (e) {
    console.log("Audio alert suppressed or not allowed yet:", e);
  }
}

function switchTab(tabId) {
  document.querySelectorAll(".nav-tab").forEach(tab => tab.classList.remove("active"));
  document.querySelectorAll("main > section").forEach(sec => sec.style.display = "none");

  const targetSec = document.getElementById(`tab-${tabId}`);
  if (targetSec) targetSec.style.display = "block";

  const btn = Array.from(document.querySelectorAll(".nav-tab")).find(b => b.getAttribute("onclick")?.includes(tabId));
  if (btn) btn.classList.add("active");
}

function handleLogout() {
  localStorage.removeItem("current_shop_id");
  localStorage.removeItem("current_shop_name");
  window.location.href = "/login";
}

async function loadShopDetails() {
  try {
    const res = await fetch(`/api/shop/${currentShopId}`);
    if (!res.ok) {
      if (res.status === 404) {
        localStorage.removeItem("current_shop_id");
        window.location.href = "/login";
        return;
      }
      throw new Error("Failed to load shop details");
    }
    const shop = await res.json();
    currentShop = shop;

    // Header updates
    document.getElementById("topShopName").textContent = shop.shop_name;
    document.getElementById("topOwnerName").textContent = `ମାଲିକ: ${shop.owner_name} (${shop.mobile})`;

    // Customer Portal links
    const custLink = document.getElementById("customerPortalLink");
    custLink.href = shop.customer_url;
    document.getElementById("standeeUrlText").textContent = shop.customer_url;
    document.getElementById("standeeQrImg").src = shop.counter_qr;
    document.getElementById("standeeShopTitle").textContent = shop.shop_name;

    // Connector Download Button
    document.getElementById("btnDownloadConnector").href = `/api/connector/download-launcher/${shop.shop_id}`;

    // Pricing
    document.getElementById("rateBwInput").value = shop.rate_bw || 2.0;
    document.getElementById("rateColorInput").value = shop.rate_color || 10.0;

    // UPI
    document.getElementById("upiIdInput").value = shop.upi_id || "";
    if (shop.shop_qr_image) {
      document.getElementById("customQrPreviewBox").style.display = "block";
      document.getElementById("customQrPreview").src = shop.shop_qr_image;
    } else {
      document.getElementById("customQrPreviewBox").style.display = "none";
    }

    // Subscription & Validity
    const daysLeft = shop.days_left !== undefined ? shop.days_left : 180;
    const isValid = shop.is_valid;
    const pill = document.getElementById("validityPill");
    const warningBanner = document.getElementById("expiryWarningBanner");

    if (!isValid || daysLeft <= 0) {
      pill.className = "sub-pill sub-pill-expired";
      pill.innerHTML = `⚠️ ସମୟ ସମାପ୍ତ (୦ ଦିନ) | ଏବେ ରିନ୍ୟୁ କରନ୍ତୁ`;
      warningBanner.style.display = "block";
      document.getElementById("expiryBannerText").textContent = "ଆପଣଙ୍କ ସବସ୍କ୍ରିପସନ୍ ସମାପ୍ତ ହୋଇଯାଇଛି। ଗ୍ରାହକ ଅର୍ଡର୍ ଗ୍ରହଣ କରିବା ପାଇଁ ରିନ୍ୟୁ କରନ୍ତୁ।";
    } else if (daysLeft <= 7) {
      pill.className = "sub-pill sub-pill-warning";
      pill.innerHTML = `⚠️ ବାକି: ${daysLeft} ଦିନ | ରିନ୍ୟୁ କରନ୍ତୁ`;
      warningBanner.style.display = "block";
      document.getElementById("expiryBannerText").textContent = `ଆପଣଙ୍କ ପ୍ଲାନ୍ ଆଉ ମାତ୍ର ${daysLeft} ଦିନ ପରେ ସରିଯିବ। ଦୟାକରି ସମୟ ଥାଉ ଥାଉ ରିନ୍ୟୁ କରନ୍ତୁ।`;
    } else {
      pill.className = "sub-pill sub-pill-active";
      pill.innerHTML = `🌟 ବାକି: ${daysLeft} ଦିନ (୬ ମାସ ଫ୍ରି ଟ୍ରାଏଲ୍)`;
      warningBanner.style.display = "none";
    }

    // Subscription Tab display
    document.getElementById("tabPlanStatusBadge").textContent = isValid ? "ସକ୍ରିୟ (Active)" : "ସମାପ୍ତ (Expired)";
    document.getElementById("tabPlanStatusBadge").className = isValid ? "sub-pill sub-pill-active" : "sub-pill sub-pill-expired";
    document.getElementById("currDaysLeft").textContent = `${daysLeft} ଦିନ`;
    document.getElementById("currExpiryDate").textContent = shop.subscription_expires_at || "N/A";

    // 2 Plans Display
    if (shop.saas_plans) {
      const p1 = shop.saas_plans.plan1;
      const p2 = shop.saas_plans.plan2;
      document.getElementById("dispPlan1Name").textContent = p1.name;
      document.getElementById("dispPlan1Price").textContent = `₹${p1.price}`;
      document.getElementById("dispPlan2Name").textContent = p2.name;
      document.getElementById("dispPlan2Price").textContent = `₹${p2.price}`;

      document.getElementById("modalTabPlan1").textContent = `${p1.name} (₹${p1.price})`;
      document.getElementById("modalTabPlan2").textContent = `${p2.name} (₹${p2.price})`;
      document.getElementById("modalUpiIdText").textContent = shop.saas_plans.superadmin_upi_id;
    }

  } catch (err) {
    console.error("Error loading shop details:", err);
  }
}

async function loadPrinters() {
  try {
    const res = await fetch("/api/printers");
    if (res.ok) {
      const data = await res.json();
      availablePrinters = data.printers || [];
      const select = document.getElementById("printerSelect");
      select.innerHTML = '<option value="">(ସିଷ୍ଟମ୍ ଡିଫଲ୍ଟ ପ୍ରିଣ୍ଟର୍)</option>';

      availablePrinters.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p;
        opt.textContent = p;
        if (currentShop && currentShop.selected_printer === p) {
          opt.selected = true;
        }
        select.appendChild(opt);
      });
    }
  } catch (err) {
    console.error("Error loading printers:", err);
  }
}

async function savePrinterChoice() {
  const printer = document.getElementById("printerSelect").value;
  try {
    const res = await fetch(`/api/shop/${currentShopId}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shop_name: currentShop.shop_name,
        owner_name: currentShop.owner_name,
        upi_id: currentShop.upi_id,
        rate_bw: currentShop.rate_bw,
        rate_color: currentShop.rate_color,
        selected_printer: printer
      })
    });
    if (res.ok) {
      alert("✅ ପ୍ରିଣ୍ଟର୍ ସଫଳତାର ସହ ସେଭ୍ ହେଲା!");
      await loadShopDetails();
    }
  } catch (err) {
    alert("ଭୁଲ୍: ପ୍ରିଣ୍ଟର୍ ସେଭ୍ ହୋଇପାରିଲା ନାହିଁ।");
  }
}

async function triggerTestPrint() {
  try {
    const res = await fetch("/api/test-print", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ printer_name: currentShop?.selected_printer || "" })
    });
    const data = await res.json();
    if (data.success) {
      alert("✅ ଟେଷ୍ଟ୍ ପେଜ୍ ପ୍ରିଣ୍ଟ୍ କମାଣ୍ଡ୍ ସଫଳତାର ସହ ପଠାଗଲା!");
    } else {
      alert("❌ ଟେଷ୍ଟ୍ ପ୍ରିଣ୍ଟ୍ ବିଫଳ: " + (data.error || ""));
    }
  } catch (e) {
    alert("❌ ଟେଷ୍ଟ୍ ପ୍ରିଣ୍ଟ୍ ବିଫଳ: " + e.message);
  }
}

async function loadJobsTable() {
  if (!currentShopId) return;
  try {
    const res = await fetch(`/api/shop/${currentShopId}/jobs`);
    if (!res.ok) return;

    const data = await res.json();
    const jobs = data.jobs || [];
    const stats = data.stats || {};

    // Update stats cards
    document.getElementById("statRevenue").textContent = `₹${(stats.today_revenue || 0).toFixed(2)}`;
    document.getElementById("statClaimed").textContent = stats.claimed_count || 0;
    document.getElementById("statPrinted").textContent = stats.printed_count || 0;
    document.getElementById("statTotalJobs").textContent = stats.total_jobs || 0;
    document.getElementById("currPrintCount").textContent = `${stats.printed_count || 0} ଟି ସଫଳ ପ୍ରିଣ୍ଟ୍`;

    // Audio chime for new claimed jobs
    const currentClaimed = jobs.filter(j => j.payment_status === "claimed");
    let hasNewClaimed = false;
    currentClaimed.forEach(j => {
      if (!knownClaimedJobIds.has(j.id)) {
        hasNewClaimed = true;
        knownClaimedJobIds.add(j.id);
      }
    });
    if (hasNewClaimed) {
      playNotificationChime();
    }

    const tbody = document.getElementById("jobsTableBody");
    if (jobs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 30px;">କୌଣସି ଅର୍ଡର୍ ମିଳିନାହିଁ</td></tr>`;
      return;
    }

    tbody.innerHTML = jobs.map(j => {
      const isClaimed = j.payment_status === "claimed";
      const isPaid = j.payment_status === "paid";
      const isPrinted = j.print_status === "printed";

      let payBadge = "";
      if (isPaid) {
        payBadge = `<span class="status-badge badge-success">✅ Paid</span>`;
      } else if (isClaimed) {
        payBadge = `<span class="status-badge badge-warning pulse-badge">🔔 ଯାଞ୍ଚ କରନ୍ତୁ</span>`;
      } else {
        payBadge = `<span class="status-badge badge-pending">⏳ ବାକି ଅଛି</span>`;
      }

      let printBadge = "";
      if (isPrinted) {
        printBadge = `<span class="status-badge badge-success">🖨️ ସଫଳ</span>`;
      } else if (j.print_status === "printing") {
        printBadge = `<span class="status-badge badge-warning">⏳ ପ୍ରିଣ୍ଟ୍ ହେଉଛି</span>`;
      } else if (j.print_status === "failed") {
        printBadge = `<span class="status-badge badge-danger">❌ ବିଫଳ</span>`;
      } else {
        printBadge = `<span class="status-badge badge-pending">ଅପେକ୍ଷା</span>`;
      }

      let actionHtml = "";
      if (isClaimed) {
        actionHtml = `
          <div style="display: flex; gap: 6px;">
            <button class="btn btn-sm btn-success" style="font-weight: 700;" onclick="approveJob('${j.id}')">
              ✅ ମିଳିଲା & ପ୍ରିଣ୍ଟ୍
            </button>
            <button class="btn btn-sm btn-outline" style="color: #ef4444; border-color: #ef4444;" onclick="rejectJob('${j.id}')">
              ❌ ବାତିଲ୍
            </button>
          </div>
        `;
      } else if (isPaid && isPrinted) {
        actionHtml = `
          <button class="btn btn-sm btn-outline" onclick="reprintJob('${j.id}')">
            🖨️ ପୁନଃ ପ୍ରିଣ୍ଟ୍
          </button>
        `;
      } else {
        actionHtml = `<span style="color: var(--text-muted); font-size: 0.8rem;">-</span>`;
      }

      const rowClass = isClaimed ? "row-claimed" : "";

      return `
        <tr class="${rowClass}">
          <td style="font-size: 0.82rem; color: var(--text-muted);">${j.created_at ? j.created_at.substring(11, 16) : "-"}</td>
          <td><b>${escapeHtml(j.original_name)}</b></td>
          <td>${j.num_pages_to_print} ପେଜ୍ (${j.copies} କପି)</td>
          <td>${j.color_mode === "color" ? "🎨 ରଙ୍ଗୀନ" : "⬛ କଳା-ଧଳା"}</td>
          <td style="font-weight: 700; color: #0284c7;">₹${(j.total_amount || 0).toFixed(2)}</td>
          <td>${payBadge}</td>
          <td>${printBadge}</td>
          <td>${actionHtml}</td>
        </tr>
      `;
    }).join("");

  } catch (err) {
    console.error("Error loading jobs:", err);
  }
}

async function approveJob(jobId) {
  try {
    const res = await fetch(`/api/shop/${currentShopId}/jobs/${jobId}/approve`, { method: "POST" });
    const data = await res.json();
    if (data.success) {
      await loadJobsTable();
    } else {
      alert("ଅନୁମୋଦନ ବିଫଳ: " + (data.detail || ""));
    }
  } catch (err) {
    alert("Error approving job: " + err.message);
  }
}

async function rejectJob(jobId) {
  if (!confirm("ଆପଣ ନିଶ୍ଚିତ ଏହି ଅର୍ଡର୍ ବାତିଲ୍ କରିବାକୁ ଚାହାନ୍ତି କି?")) return;
  try {
    const res = await fetch(`/api/shop/${currentShopId}/jobs/${jobId}/reject`, { method: "POST" });
    await loadJobsTable();
  } catch (err) {
    alert("Error rejecting job: " + err.message);
  }
}

async function reprintJob(jobId) {
  if (!confirm("ଏହି ଫାଇଲ୍ ପୁନର୍ବାର ପ୍ରିଣ୍ଟ୍ କରିବେ କି?")) return;
  try {
    await fetch(`/api/shop/${currentShopId}/jobs/${jobId}/reprint`, { method: "POST" });
    await loadJobsTable();
  } catch (err) {
    alert("Error reprinting job: " + err.message);
  }
}

async function savePricing() {
  const rateBw = parseFloat(document.getElementById("rateBwInput").value);
  const rateColor = parseFloat(document.getElementById("rateColorInput").value);

  if (isNaN(rateBw) || isNaN(rateColor) || rateBw <= 0 || rateColor <= 0) {
    alert("ଦୟାକରି ସଠିକ୍ ଦର ଦିଅନ୍ତୁ!");
    return;
  }

  try {
    const res = await fetch(`/api/shop/${currentShopId}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shop_name: currentShop.shop_name,
        owner_name: currentShop.owner_name,
        upi_id: currentShop.upi_id,
        rate_bw: rateBw,
        rate_color: rateColor,
        selected_printer: currentShop.selected_printer || ""
      })
    });
    if (res.ok) {
      alert("✅ ଦର ସଫଳତାର ସହ ସେଭ୍ ହେଲା!");
      await loadShopDetails();
    }
  } catch (err) {
    alert("Error saving pricing: " + err.message);
  }
}

async function saveUpiId() {
  const upiId = document.getElementById("upiIdInput").value.trim();
  if (!upiId) {
    alert("ଦୟାକରି ସଠିକ୍ UPI ID ଦିଅନ୍ତୁ!");
    return;
  }

  try {
    const res = await fetch(`/api/shop/${currentShopId}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shop_name: currentShop.shop_name,
        owner_name: currentShop.owner_name,
        upi_id: upiId,
        rate_bw: currentShop.rate_bw,
        rate_color: currentShop.rate_color,
        selected_printer: currentShop.selected_printer || ""
      })
    });
    if (res.ok) {
      alert("✅ UPI ID ସଫଳତାର ସହ ସେଭ୍ ହେଲା!");
      await loadShopDetails();
    }
  } catch (err) {
    alert("Error saving UPI ID: " + err.message);
  }
}

async function uploadStandeeImage() {
  const fileInput = document.getElementById("standeeFileInput");
  if (!fileInput.files || !fileInput.files[0]) {
    alert("ଦୟାକରି ପ୍ରଥମେ ଗୋଟିଏ ଫଟୋ ବାଛନ୍ତୁ!");
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  try {
    const res = await fetch(`/api/shop/${currentShopId}/upload-qr`, {
      method: "POST",
      body: formData
    });
    if (res.ok) {
      alert("✅ କାଉଣ୍ଟର୍ ଷ୍ଟାଣ୍ଡି ଫଟୋ ସଫଳତାର ସହ ଅପଲୋଡ୍ ହେଲା!");
      await loadShopDetails();
    }
  } catch (err) {
    alert("Error uploading standee photo: " + err.message);
  }
}

// Renewal Modal Helpers
function openRenewalModal() {
  document.getElementById("renewalModal").style.display = "flex";
  setModalPlan(selectedModalPlan);
}

function closeRenewalModal() {
  document.getElementById("renewalModal").style.display = "none";
}

function selectPlanForRenewal(planKey) {
  selectedModalPlan = planKey;
  openRenewalModal();
}

function setModalPlan(planKey) {
  selectedModalPlan = planKey;
  const p1Btn = document.getElementById("modalTabPlan1");
  const p2Btn = document.getElementById("modalTabPlan2");
  const p1 = currentShop?.saas_plans?.plan1 || { price: 499, name: "୬ ମାସ" };
  const p2 = currentShop?.saas_plans?.plan2 || { price: 899, name: "୧ ବର୍ଷ" };
  const adminUpi = currentShop?.saas_plans?.superadmin_upi_id || "9937037131@ybl";

  let price = 899;
  let planName = "୧ ବର୍ଷ";
  if (planKey === "plan1") {
    p1Btn.className = "btn btn-sm btn-primary";
    p2Btn.className = "btn btn-sm btn-outline";
    price = p1.price;
    planName = p1.name;
  } else {
    p2Btn.className = "btn btn-sm btn-primary";
    p1Btn.className = "btn btn-sm btn-outline";
    price = p2.price;
    planName = p2.name;
  }

  document.getElementById("modalAmountDisplay").textContent = `ଦେୟ ରାଶି: ₹${price} (${planName})`;

  // Generate Admin UPI QR using generic URI generator
  const upiUri = `upi://pay?pa=${encodeURIComponent(adminUpi)}&pn=SmartPrintAdmin&am=${price}&cu=INR&tn=Renewal_${currentShopId}_${planKey}`;
  const qrApiUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(upiUri)}`;
  document.getElementById("superadminQrImg").src = qrApiUrl;
}

async function submitRenewalRequest() {
  const txnId = document.getElementById("renewalTxnInput").value.trim();
  if (!txnId) {
    alert("ଦୟାକରି ଆପଣଙ୍କ Payment Transaction ID / UTR ନମ୍ବର ଦିଅନ୍ତୁ!");
    return;
  }

  alert("✅ ଆପଣଙ୍କ ପେମେଣ୍ଟ୍ ସୂଚନା ସୁପର୍ ଆଡମିନ୍ ଙ୍କ ପାଖକୁ ପଠାଗଲା। ଯାଞ୍ଚ କରିବା ପରେ ଆପଣଙ୍କ ପ୍ଲାନ୍ ସକ୍ରିୟ ହୋଇଯିବ। ଧନ୍ୟବାଦ!");
  closeRenewalModal();
}

function escapeHtml(text) {
  if (!text) return "";
  return text.replace(/[&<>"']/g, function(m) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[m];
  });
}
