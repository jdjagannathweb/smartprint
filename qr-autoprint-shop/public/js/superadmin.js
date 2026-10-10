let currentPin = sessionStorage.getItem("superadmin_pin") || "";

document.addEventListener("DOMContentLoaded", async () => {
  if (currentPin) {
    await verifyAndLoad();
  }
});

function switchSaTab(tabId) {
  document.querySelectorAll(".sa-tab").forEach(tab => tab.classList.remove("active"));
  document.querySelectorAll(".sa-content > section").forEach(sec => sec.style.display = "none");

  const targetSec = document.getElementById(`sa-tab-${tabId}`);
  if (targetSec) targetSec.style.display = "block";

  const btn = Array.from(document.querySelectorAll(".sa-tab")).find(b => b.getAttribute("onclick")?.includes(tabId));
  if (btn) btn.classList.add("active");
}

async function handleSuperAdminLogin(e) {
  e.preventDefault();
  const pin = document.getElementById("inputMasterPin").value.trim();
  const btn = document.getElementById("btnPinSubmit");
  const errBox = document.getElementById("pinError");
  errBox.style.display = "none";

  btn.disabled = true;
  btn.textContent = "⏳ ଯାଞ୍ଚ ହେଉଛି...";

  try {
    const res = await fetch("/api/superadmin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin: pin })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "ଭୁଲ୍ Master PIN!");

    currentPin = pin;
    sessionStorage.setItem("superadmin_pin", pin);
    document.getElementById("masterPinModal").style.display = "none";

    await loadSuperAdminData();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.style.display = "block";
    btn.disabled = false;
    btn.textContent = "🔓 ଅନଲକ୍ କରନ୍ତୁ";
  }
}

function handleSuperAdminLogout() {
  sessionStorage.removeItem("superadmin_pin");
  window.location.reload();
}

async function verifyAndLoad() {
  try {
    const res = await fetch(`/api/superadmin/overview?pin=${encodeURIComponent(currentPin)}`);
    if (res.ok) {
      document.getElementById("masterPinModal").style.display = "none";
      await loadSuperAdminData();
    } else {
      sessionStorage.removeItem("superadmin_pin");
      currentPin = "";
      document.getElementById("masterPinModal").style.display = "flex";
    }
  } catch (err) {
    document.getElementById("masterPinModal").style.display = "flex";
  }
}

async function loadSuperAdminData() {
  if (!currentPin) return;

  try {
    const res = await fetch(`/api/superadmin/overview?pin=${encodeURIComponent(currentPin)}`);
    if (!res.ok) throw new Error("Unauthorized");
    const data = await res.json();

    const overview = data.overview || {};
    const shops = data.shops || [];
    const settings = data.settings || {};

    // KPIs
    document.getElementById("kpiTotalShops").textContent = overview.total_shops || 0;
    document.getElementById("kpiActiveShops").textContent = overview.active_shops || 0;
    document.getElementById("kpiExpiredShops").textContent = overview.expired_shops || 0;
    document.getElementById("kpiTotalJobs").textContent = overview.total_jobs || 0;
    document.getElementById("kpiTotalPages").textContent = overview.total_pages || 0;

    // Table
    const tbody = document.getElementById("membersTableBody");
    if (shops.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 30px; color: #94a3b8;">କୌଣସି ଦୋକାନୀ ସଦସ୍ୟ ନାହାନ୍ତି।</td></tr>`;
      return;
    }

    tbody.innerHTML = shops.map(s => {
      const isValid = s.is_valid;
      const daysLeft = s.days_left !== undefined ? s.days_left : 0;
      const statusBadge = isValid 
        ? `<span class="badge-active">✅ ସକ୍ରିୟ (${daysLeft} ଦିନ)</span>` 
        : `<span class="badge-expired">⚠️ ସମାପ୍ତ (୦ ଦିନ)</span>`;

      const workActivity = `
        <div style="font-weight: 700; color: #fff;">${s.job_count || 0} ଟି ପ୍ରିଣ୍ଟ୍ ଅର୍ଡର୍</div>
        <div style="font-size: 0.8rem; color: #94a3b8;">${s.total_pages_printed || 0} ପେଜ୍ ପ୍ରିଣ୍ଟ୍</div>
      `;

      return `
        <tr>
          <td>
            <div style="font-weight: 700; color: #fff; font-size: 0.95rem;">${escapeHtml(s.shop_name)}</div>
            <div style="font-size: 0.8rem; color: #94a3b8;">ମାଲିକ: ${escapeHtml(s.owner_name)} (${s.shop_id})</div>
          </td>
          <td><b>${s.mobile}</b></td>
          <td>
            <a href="/s/${s.slug}" target="_blank" style="color: #38bdf8; text-decoration: none; font-weight: 600;">
              /s/${s.slug} ↗
            </a>
          </td>
          <td>${workActivity}</td>
          <td>${statusBadge}</td>
          <td style="font-size: 0.82rem; color: #cbd5e1;">${s.subscription_expires_at || "N/A"}</td>
          <td>
            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
              <button class="btn btn-sm" style="background: #059669; color: #fff; font-size: 0.75rem; padding: 6px 10px;" onclick="extendShopPlan('${s.shop_id}', 180)">
                +୬ ମାସ (+180d)
              </button>
              <button class="btn btn-sm" style="background: #0284c7; color: #fff; font-size: 0.75rem; padding: 6px 10px;" onclick="extendShopPlan('${s.shop_id}', 365)">
                +୧ ବର୍ଷ (+365d)
              </button>
              <button class="btn btn-sm" style="background: ${s.is_active ? '#dc2626' : '#16a34a'}; color: #fff; font-size: 0.75rem; padding: 6px 8px;" onclick="toggleShop('${s.shop_id}')">
                ${s.is_active ? 'ବନ୍ଦ' : 'ଚାଲୁ'}
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join("");

    // Populate Settings Tab Form
    document.getElementById("cfgPlan1Name").value = settings.plan1_name || "୬ ମାସ ପ୍ଲାନ୍ (6 Months Plan)";
    document.getElementById("cfgPlan1Days").value = settings.plan1_days || "180";
    document.getElementById("cfgPlan1Price").value = settings.plan1_price || "499";

    document.getElementById("cfgPlan2Name").value = settings.plan2_name || "୧ ବର୍ଷ ପ୍ଲାନ୍ (1 Year Plan - Best Value)";
    document.getElementById("cfgPlan2Days").value = settings.plan2_days || "365";
    document.getElementById("cfgPlan2Price").value = settings.plan2_price || "899";

    document.getElementById("cfgSuperAdminUpi").value = settings.superadmin_upi_id || "9937037131@ybl";
    document.getElementById("cfgSuperAdminUpiName").value = settings.superadmin_upi_name || "Smart Print Platform";
    document.getElementById("cfgFreeTrialDays").value = settings.free_trial_days || "180";

  } catch (err) {
    console.error("Super Admin load error:", err);
  }
}

async function extendShopPlan(shopId, days) {
  const planLabel = days >= 365 ? "୧ ବର୍ଷ" : "୬ ମାସ";
  if (!confirm(`ଆପଣ ଏହି ଦୋକାନର ସବସ୍କ୍ରିପସନ୍ +${planLabel} (${days} ଦିନ) ବଢ଼ାଇବାକୁ ଚାହାନ୍ତି କି?`)) return;

  try {
    const res = await fetch("/api/superadmin/extend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pin: currentPin,
        shop_id: shopId,
        days: days
      })
    });
    const data = await res.json();
    if (data.success) {
      alert(`✅ ସଫଳତାର ସହ +${planLabel} ବଢ଼ାଗଲା! ନୂଆ Expiry: ${data.new_expiry}`);
      await loadSuperAdminData();
    } else {
      alert("ବିଫଳ: " + (data.detail || ""));
    }
  } catch (err) {
    alert("Error extending plan: " + err.message);
  }
}

async function toggleShop(shopId) {
  try {
    const res = await fetch("/api/superadmin/toggle-shop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin: currentPin, shop_id: shopId })
    });
    if (res.ok) {
      await loadSuperAdminData();
    }
  } catch (err) {
    alert("Error toggling shop status: " + err.message);
  }
}

async function handleSaveSaasSettings(e) {
  e.preventDefault();

  const payload = {
    pin: currentPin,
    plan1_name: document.getElementById("cfgPlan1Name").value.trim(),
    plan1_days: parseInt(document.getElementById("cfgPlan1Days").value, 10),
    plan1_price: parseFloat(document.getElementById("cfgPlan1Price").value),
    plan2_name: document.getElementById("cfgPlan2Name").value.trim(),
    plan2_days: parseInt(document.getElementById("cfgPlan2Days").value, 10),
    plan2_price: parseFloat(document.getElementById("cfgPlan2Price").value),
    superadmin_upi_id: document.getElementById("cfgSuperAdminUpi").value.trim(),
    superadmin_upi_name: document.getElementById("cfgSuperAdminUpiName").value.trim(),
    free_trial_days: parseInt(document.getElementById("cfgFreeTrialDays").value, 10),
    new_master_pin: document.getElementById("cfgNewMasterPin").value.trim() || null
  };

  try {
    const res = await fetch("/api/superadmin/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      alert("✅ ସମସ୍ତ SaaS ୨ ଟି ପ୍ଲାନ୍ ଏବଂ UPI ସେଟିଙ୍ଗ୍ ସଫଳତାର ସହ ସେଭ୍ ହେଲା!");
      if (payload.new_master_pin) {
        currentPin = payload.new_master_pin;
        sessionStorage.setItem("superadmin_pin", currentPin);
      }
      await loadSuperAdminData();
    } else {
      const err = await res.json();
      alert("ଭୁଲ୍: " + (err.detail || "Settings save failed"));
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

function escapeHtml(text) {
  if (!text) return "";
  return text.replace(/[&<>"']/g, function(m) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[m];
  });
}
