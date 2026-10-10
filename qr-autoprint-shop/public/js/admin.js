let currentSettings = {};
let availablePrinters = [];
let knownClaimedJobIds = new Set();
let audioContext = null;

document.addEventListener("DOMContentLoaded", async () => {
  await loadNetworkInfo();
  await loadPrinters();
  await loadSettings();
  await loadJobsTable();

  // Auto-refresh jobs table every 3 seconds for instant updates
  setInterval(loadJobsTable, 3000);
  // Auto-refresh network info every 5 seconds to catch tunnel URL
  setInterval(loadNetworkInfo, 5000);
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
    console.log("Audio not allowed yet or supported", e);
  }
}

function switchTab(tabId) {
  document.querySelectorAll(".nav-tab").forEach(tab => tab.classList.remove("active"));
  document.querySelectorAll("main > section").forEach(sec => sec.style.display = "none");

  const targetSec = document.getElementById(`tab-${tabId}`);
  if (targetSec) targetSec.style.display = "block";

  event.target.classList.add("active");
}

async function loadNetworkInfo() {
  try {
    const res = await fetch("/api/network-info");
    if (res.ok) {
      const data = await res.json();
      
      if (data.public_url) {
        document.getElementById("publicUrlBadge").textContent = `🌐 4G/5G ଲିଙ୍କ୍: ${data.public_url}`;
        document.getElementById("publicUrlBadge").style.display = "inline-block";
      } else {
        document.getElementById("publicUrlBadge").textContent = "🌐 4G/5G ଲିଙ୍କ୍ ସଂଯୋଗ ହେଉଛି...";
      }

      document.getElementById("lanIpBadge").textContent = `📶 Wi-Fi: ${data.local_url}`;
      document.getElementById("standeeQrImg").src = data.counter_qr;
      document.getElementById("standeeUrlText").textContent = data.customer_url;
    }
  } catch (err) {
    console.error("Network info error:", err);
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
        opt.value = p.name;
        opt.textContent = p.name + (p.default ? " [ସିଷ୍ଟମ୍ ଡିଫଲ୍ଟ]" : "");
        select.appendChild(opt);
      });
    }
  } catch (err) {
    console.error("Printer list error:", err);
  }
}

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    if (res.ok) {
      currentSettings = await res.json();

      document.getElementById("topShopName").textContent = currentSettings.shop_name || "ସ୍ମାର୍ଟ ପ୍ରିଣ୍ଟ ପଏଣ୍ଟ";
      document.getElementById("standeeShopTitle").textContent = currentSettings.shop_name || "ସ୍ମାର୍ଟ ପ୍ରିଣ୍ଟ ପଏଣ୍ଟ";

      document.getElementById("shopNameInput").value = currentSettings.shop_name || "";
      document.getElementById("upiIdInput").value = currentSettings.upi_id || "";
      document.getElementById("rateBwInput").value = currentSettings.rate_bw || 2.0;
      document.getElementById("rateColorInput").value = currentSettings.rate_color || 10.0;
      document.getElementById("autoPrintToggle").checked = !!currentSettings.auto_print;

      if (currentSettings.selected_printer) {
        document.getElementById("printerSelect").value = currentSettings.selected_printer;
      }

      // Check for custom shop QR image
      if (currentSettings.shop_qr_image) {
        document.getElementById("shopQrPreviewImg").src = currentSettings.shop_qr_image;
        document.getElementById("shopQrPreviewContainer").style.display = "block";
        document.getElementById("btnRemoveShopQr").style.display = "inline-block";
      } else {
        document.getElementById("shopQrPreviewContainer").style.display = "none";
        document.getElementById("btnRemoveShopQr").style.display = "none";
      }
    }
  } catch (err) {
    console.error("Settings load error:", err);
  }
}

function appendHandle(handle) {
  const input = document.getElementById("upiIdInput");
  let val = input.value.trim();
  if (val.includes("@")) {
    val = val.split("@")[0];
  }
  input.value = val + handle;
}

async function uploadShopQrFile(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/settings/upload-qr", {
      method: "POST",
      body: formData
    });

    if (res.ok) {
      alert("✅ ଆପଣଙ୍କ ଦୋକାନର ଅସଲ QR କୋଡ୍ ସଫଳତାର ସହ ଅପଲୋଡ୍ ହେଲା!\nଏବେ ଗ୍ରାହକ ଏହି QR କୋଡ୍ ସ୍କାନ୍ କରି ସିଧାସଳଖ ପେ କରିପାରିବେ।");
      await loadSettings();
    } else {
      alert("ଅପଲୋଡ୍ ବିଫଳ ହେଲା");
    }
  } catch (e) {
    alert("ତ୍ରୁଟି: " + e.message);
  }
}

async function removeShopQr() {
  if (!confirm("କ'ଣ ଆପଣ ଅପଲୋଡ୍ କରିଥିବା QR କୋଡ୍ ହଟାଇବାକୁ ଚାହାଁନ୍ତି?")) return;

  try {
    const res = await fetch("/api/settings/remove-qr", { method: "DELETE" });
    if (res.ok) {
      alert("ଅପଲୋଡ୍ ହୋଇଥିବା QR ହଟାଇ ଦିଆଗଲା। ଏବେ ଡାଇନାମିକ୍ QR କାମ କରିବ।");
      await loadSettings();
    }
  } catch (e) {
    alert("ତ୍ରୁଟି: " + e.message);
  }
}

async function loadJobsTable() {
  try {
    const res = await fetch("/api/admin/jobs");
    if (!res.ok) return;

    const data = await res.json();
    const stats = data.stats;
    const jobs = data.jobs || [];

    // Check for new claimed payments to ring chime
    let newClaimFound = false;
    jobs.forEach(j => {
      if (j.payment_status === "claimed" && !knownClaimedJobIds.has(j.id)) {
        newClaimFound = true;
        knownClaimedJobIds.add(j.id);
      }
    });
    if (newClaimFound) {
      playNotificationChime();
    }

    // Update Stats
    document.getElementById("statRevenue").textContent = `₹${stats.total_revenue.toFixed(2)}`;
    document.getElementById("statTotalJobs").textContent = stats.total_jobs;
    document.getElementById("statPrinted").textContent = stats.total_printed;
    document.getElementById("statClaimed").textContent = stats.total_claimed || 0;

    // Render Table
    const tbody = document.getElementById("jobsTableBody");
    if (jobs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" style="text-align:center; color:#94a3b8; padding:24px;">ବର୍ତ୍ତମାନ କୌଣସି ପ୍ରିଣ୍ଟ୍ ଅର୍ଡର୍ ନାହିଁ।</td></tr>';
      return;
    }

    tbody.innerHTML = jobs.map(job => {
      const isClaimed = job.payment_status === "claimed";
      const isPaid = job.payment_status === "paid";
      const isRejected = job.payment_status === "rejected";

      let payBadge = '<span class="badge" style="background:#f1f5f9; color:#64748b;">ଅପେକ୍ଷାରେ</span>';
      let rowClass = "";
      let actionButtons = "";

      if (isClaimed) {
        rowClass = "class=\"row-claimed\"";
        payBadge = '<span class="badge badge-warning pulse-badge" style="background:#fef08a; color:#854d0e; font-weight:800; border:1px solid #eab308;">🔔 ଗ୍ରାହକ ପେ କରିଛନ୍ତି</span>';
        actionButtons = `
          <button class="btn btn-sm btn-success" style="font-weight:700;" onclick="merchantApprove('${job.id}', ${job.total_amount})">
            ✅ ପେମେଣ୍ଟ୍ ମିଳିଲା & ପ୍ରିଣ୍ଟ୍
          </button>
          <button class="btn btn-sm btn-danger" style="padding:4px 8px;" onclick="merchantReject('${job.id}')">
            ❌ ମିଳିନାହିଁ
          </button>
        `;
      } else if (isPaid) {
        payBadge = '<span class="badge badge-success">ପେଡ୍ (Paid)</span>';
        actionButtons = `
          <button class="btn btn-sm btn-primary" onclick="printJobNow('${job.id}')">
            🖨️ ${job.print_status === 'printed' ? 'ପୁନଃ ପ୍ରିଣ୍ଟ୍' : 'ପ୍ରିଣ୍ଟ୍ କରନ୍ତୁ'}
          </button>
          <button class="btn btn-sm btn-danger" style="padding:4px 8px;" onclick="deleteJob('${job.id}')">
            🗑️
          </button>
        `;
      } else if (isRejected) {
        payBadge = '<span class="badge badge-danger">ବାତିଲ୍ (Rejected)</span>';
        actionButtons = `
          <button class="btn btn-sm btn-success" onclick="merchantApprove('${job.id}', ${job.total_amount})">
            ✅ ପୁନଃ ଯାଞ୍ଚ & ପ୍ରିଣ୍ଟ୍
          </button>
          <button class="btn btn-sm btn-danger" style="padding:4px 8px;" onclick="deleteJob('${job.id}')">
            🗑️
          </button>
        `;
      } else {
        // Pending
        actionButtons = `
          <button class="btn btn-sm btn-success" onclick="merchantApprove('${job.id}', ${job.total_amount})">
            ✅ ନଗଦ ନେଇ ପ୍ରିଣ୍ଟ୍
          </button>
          <button class="btn btn-sm btn-danger" style="padding:4px 8px;" onclick="deleteJob('${job.id}')">
            🗑️
          </button>
        `;
      }

      let printBadge = '<span class="badge badge-warning">ଅପେକ୍ଷାରେ</span>';
      if (job.print_status === "printed") printBadge = '<span class="badge badge-success">ପ୍ରିଣ୍ଟ୍ ହେଲା</span>';
      else if (job.print_status === "printing") printBadge = '<span class="badge badge-info">ପ୍ରିଣ୍ଟିଂ...</span>';
      else if (job.print_status === "failed") printBadge = `<span class="badge badge-danger" title="${job.print_error || ''}">ବିଫଳ</span>`;
      else if (job.print_status === "waiting_merchant") printBadge = '<span class="badge" style="background:#e0f2fe; color:#0369a1;">ଅନୁମୋଦନ ଅପେକ୍ଷା</span>';

      return `
        <tr ${rowClass}>
          <td style="font-size: 0.78rem; color: #64748b;">${job.created_at || ''}</td>
          <td><strong>#${job.id}</strong></td>
          <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${job.original_name}">${job.original_name}</td>
          <td>${job.num_pages_to_print || job.total_pages}</td>
          <td>${job.copies || 1}</td>
          <td>${job.color_mode === 'color' ? '🎨 ରଙ୍ଗୀନ' : '📄 B&W'}</td>
          <td style="font-weight:800; font-size: 0.95rem; color: #0f172a;">₹${(job.total_amount || 0).toFixed(2)}</td>
          <td>${payBadge}</td>
          <td>${printBadge}</td>
          <td>
            <div style="display: flex; gap: 4px; align-items: center; flex-wrap: wrap;">
              ${actionButtons}
            </div>
          </td>
        </tr>
      `;
    }).join("");

  } catch (err) {
    console.error("Error loading jobs:", err);
  }
}

// Merchant Confirms Payment -> Triggers Print!
async function merchantApprove(jobId, amount) {
  const msg = amount 
    ? `କ'ଣ ଆପଣ ₹${amount.toFixed(2)} ପେମେଣ୍ଟ୍ ପ୍ରାପ୍ତ ହୋଇଥିବା ନିଶ୍ଚିତ କରି ପ୍ରିଣ୍ଟ୍ କାଢ଼ିବାକୁ ଚାହାଁନ୍ତି?`
    : "କ'ଣ ଆପଣ ପେମେଣ୍ଟ୍ କନଫର୍ମ କରି ପ୍ରିଣ୍ଟ୍ କରିବାକୁ ଚାହାଁନ୍ତି?";

  if (!confirm(msg)) return;

  try {
    const res = await fetch(`/api/jobs/${jobId}/merchant-approve`, { method: "POST" });
    if (res.ok) {
      alert("✅ ପେମେଣ୍ଟ୍ କନଫର୍ମ ହେଲା ଏବଂ ପ୍ରିଣ୍ଟର୍ କୁ କମାଣ୍ଡ୍ ପଠାଗଲା!");
      loadJobsTable();
    } else {
      alert("ପ୍ରିଣ୍ଟ୍ ଆରମ୍ଭ କରିବାରେ ବିଫଳ ହେଲା");
    }
  } catch (err) {
    alert("ତ୍ରୁଟି: " + err.message);
  }
}

// Merchant Rejects Payment
async function merchantReject(jobId) {
  if (!confirm("କ'ଣ ପେମେଣ୍ଟ୍ ପ୍ରାପ୍ତ ହୋଇନାହିଁ ବୋଲି ମାର୍କ କରିବାକୁ ଚାହାଁନ୍ତି?")) return;

  try {
    const res = await fetch(`/api/jobs/${jobId}/merchant-reject`, { method: "POST" });
    if (res.ok) {
      alert("⚠️ ପେମେଣ୍ଟ୍ ପ୍ରତ୍ୟାଖ୍ୟାନ (Reject) କରାଗଲା।");
      loadJobsTable();
    }
  } catch (err) {
    alert("ତ୍ରୁଟି: " + err.message);
  }
}

async function printJobNow(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/print-now`, { method: "POST" });
    if (res.ok) {
      alert("ପ୍ରିଣ୍ଟ୍ କମାଣ୍ଡ୍ ପ୍ରିଣ୍ଟର୍ କୁ ପଠାଯାଇଛି!");
      loadJobsTable();
    } else {
      alert("ପ୍ରିଣ୍ଟ୍ ଆରମ୍ଭ କରିବାରେ ବିଫଳ ହେଲା");
    }
  } catch (err) {
    alert("ତ୍ରୁଟି: " + err.message);
  }
}

async function deleteJob(jobId) {
  if (!confirm("କ'ଣ ଆପଣ ଏହି ଅର୍ଡରକୁ ତାଲିକାରୁ ହଟାଇବାକୁ ଚାହାଁନ୍ତି?")) return;
  try {
    const res = await fetch(`/api/admin/jobs/${jobId}`, { method: "DELETE" });
    if (res.ok) {
      loadJobsTable();
    }
  } catch (err) {
    alert("ତ୍ରୁଟି: " + err.message);
  }
}

async function savePricingSettings() {
  const pin = document.getElementById("pinPricingInput").value;
  if (!pin) {
    alert("ଦୟାକରି ଆଡମିନ୍ PIN ଦିଅନ୍ତୁ (ଡିଫଲ୍ଟ 1234)");
    return;
  }

  const payload = {
    shop_name: currentSettings.shop_name,
    upi_id: currentSettings.upi_id,
    rate_bw: parseFloat(document.getElementById("rateBwInput").value) || 2.0,
    rate_color: parseFloat(document.getElementById("rateColorInput").value) || 10.0,
    selected_printer: currentSettings.selected_printer || "",
    auto_print: currentSettings.auto_print !== undefined ? currentSettings.auto_print : true,
    admin_pin: pin
  };

  await sendSettingsUpdate(payload);
}

async function savePaymentSettings() {
  const pin = document.getElementById("pinPaymentInput").value;
  if (!pin) {
    alert("ଦୟାକରି ଆଡମିନ୍ PIN ଦିଅନ୍ତୁ (ଡିଫଲ୍ଟ 1234)");
    return;
  }

  const payload = {
    shop_name: document.getElementById("shopNameInput").value.trim() || currentSettings.shop_name,
    upi_id: document.getElementById("upiIdInput").value.trim(),
    rate_bw: currentSettings.rate_bw,
    rate_color: currentSettings.rate_color,
    selected_printer: currentSettings.selected_printer || "",
    auto_print: currentSettings.auto_print !== undefined ? currentSettings.auto_print : true,
    admin_pin: pin
  };

  await sendSettingsUpdate(payload);
}

async function savePrinterSettings() {
  const pin = document.getElementById("pinPrinterInput").value;
  if (!pin) {
    alert("ଦୟାକରି ଆଡମିନ୍ PIN ଦିଅନ୍ତୁ (ଡିଫଲ୍ଟ 1234)");
    return;
  }

  const payload = {
    shop_name: currentSettings.shop_name,
    upi_id: currentSettings.upi_id,
    rate_bw: currentSettings.rate_bw,
    rate_color: currentSettings.rate_color,
    selected_printer: document.getElementById("printerSelect").value,
    auto_print: document.getElementById("autoPrintToggle").checked,
    admin_pin: pin
  };

  await sendSettingsUpdate(payload);
}

async function sendSettingsUpdate(payload) {
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      alert("✅ ସେଟିଙ୍ଗ୍ ସଫଳତାର ସହ ସେଭ୍ ହେଲା!");
      await loadSettings();
    } else {
      const err = await res.json();
      alert("❌ ତ୍ରୁଟି: " + (err.detail || "ସେଭ୍ ହୋଇପାରିଲା ନାହିଁ"));
    }
  } catch (err) {
    alert("ନେଟୱାର୍କ ତ୍ରୁଟି: " + err.message);
  }
}

async function sendTestPrint() {
  const selected = document.getElementById("printerSelect").value;
  if (!confirm(`କ'ଣ ଆପଣ ${selected || 'ସିଷ୍ଟମ୍ ଡିଫଲ୍ଟ ପ୍ରିଣ୍ଟର୍'} ରେ ଟେଷ୍ଟ୍ ପେଜ୍ ପ୍ରିଣ୍ଟ୍ କରିବାକୁ ଚାହାଁନ୍ତି?`)) return;

  try {
    const res = await fetch("/api/test-print", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ printer_name: selected })
    });

    const data = await res.json();
    if (data.success) {
      alert("✅ ଟେଷ୍ଟ୍ ପ୍ରିଣ୍ଟ୍ କମାଣ୍ଡ୍ ପ୍ରିଣ୍ଟର୍ କୁ ପଠାଯାଇଛି!");
    } else {
      alert("⚠️ ପ୍ରିଣ୍ଟର୍ ତ୍ରୁଟି ଦେଲା: " + (data.error || "ପ୍ରିଣ୍ଟର୍ ଅନ୍ ଅଛି କି ନାହିଁ ଯାଞ୍ଚ କରନ୍ତୁ"));
    }
  } catch (err) {
    alert("ତ୍ରୁଟି: " + err.message);
  }
}
