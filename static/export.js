window.addEventListener("DOMContentLoaded", async () => {
  const dropdown = document.getElementById("storeDropdown");

  // ===== ADD THIS HELPER FUNCTION =====
async function translateWithMethod(text, method, targetLang, prompt, fieldType) {
  try {
    const res = await fetch('/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        method,
        target_language: targetLang,
        custom_prompt: prompt,
        field_type: fieldType
      })
    });
    
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Translation failed');
    return data.translated_text;
  } catch (error) {
    console.error(`${method} translation error:`, error);
    return text; // Return original on error
  }
}

  try {
    const res = await fetch("/get_stores");
    const stores = await res.json();

    dropdown.innerHTML = '<option value="" disabled selected>Select Store</option>';
    stores.forEach(store => {
      const option = document.createElement("option");
      option.value = store.value;
      option.textContent = `${store.label} (${store.value})`;
      dropdown.appendChild(option);
    });
  } catch (err) {
    console.error("❌ Failed to load stores:", err);
    dropdown.innerHTML = '<option value="">⚠️ Could not load stores</option>';
  }

  // ✅ Move this inside
// ✅ Update this section to handle both ChatGPT and DeepSeek
const methodFields = [
  { methodId: "title_method", containerId: "title_prompt_container" },
  { methodId: "desc_method", containerId: "desc_prompt_container" },
  { methodId: "variant_method", containerId: "variant_prompt_container" },
];

methodFields.forEach(({ methodId, containerId }) => {
  const select = document.getElementById(methodId);
  const container = document.getElementById(containerId);

  if (!select || !container) return;

  select.addEventListener("change", () => {
    // Show for both ChatGPT and DeepSeek
    container.style.display = (select.value === "chatgpt" || select.value === "deepseek") ? "block" : "none";
  });

  // Show on initial load if either is selected
  container.style.display = (select.value === "chatgpt" || select.value === "deepseek") ? "block" : "none";
});

const cloneBtnContainer = document.getElementById("cloneButtonContainer");
const translateBtnContainer = document.getElementById("translateButtonContainer");

const cloneBtn = document.getElementById("cloneBtn");
const translateBtn = document.getElementById("translateBtn");

let salesSheetCreated = false;
let productsCloned = false;


let lastPayload = null;

const exportForm = document.getElementById("exportForm");
const resultEl = document.getElementById("exportResult");
const loadingEl = document.getElementById("loading");
const reviewBox = document.getElementById("reviewSheetContainer");
const sheetLinkEl = document.getElementById("sheetReviewLink");
const continueBtn = document.getElementById("continueExportBtn");
const generateSheetBtn = document.getElementById("generateSheetBtn");
const sheetStatusEl = document.getElementById("sheetStatus");

// Step 1: Generate sheet only (via Export Form)
exportForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  console.log("✅ Form submitted handler triggered");

  // 🧠 Read values directly to be safe
  const startInput = document.getElementById("start_date").value;
  const endInput = document.getElementById("end_date").value;
  const minSales = document.getElementById("min_sales").value;
  const store = document.getElementById("storeDropdown").value;
  const language = document.getElementById("language").value;

  const titleMethod = document.getElementById("title_method").value;
  const descMethod = document.getElementById("desc_method").value;
  const variantMethod = document.getElementById("variant_method").value;
  
  const payload = {
    start_date: startInput,
    end_date: endInput,
    min_sales: minSales,
    store: store,
    language: language,
    title_method: titleMethod,
    desc_method: descMethod,
    variant_method: variantMethod,
    title_prompt: (titleMethod === "chatgpt" || titleMethod === "deepseek") 
    ? (document.getElementById("title_prompt")?.value || "") 
    : "",
  desc_prompt: (descMethod === "chatgpt" || descMethod === "deepseek")
    ? (document.getElementById("desc_prompt")?.value || "")
    : "",
  variant_prompt: (variantMethod === "chatgpt" || variantMethod === "deepseek")
    ? (document.getElementById("variant_prompt")?.value || "")
    : ""
};
  

  console.log("📤 Payload (from inputs):", payload);

  if (!payload.start_date || !payload.end_date) {
    resultEl.innerHTML = `<div style="color:red;"><strong>Error:</strong> Missing start or end date.</div>`;
    console.error("🔴 Missing start or end date.");
    return;
  }

  lastPayload = { ...payload };

  // Show loading
  // Show loading state
resultEl.innerHTML = "";
loadingEl.style.display = "block";
reviewBox.style.display = "none";
cloneBtnContainer.style.display = "none";  // hide just in case

try {
  const res = await fetch("/run_export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, review_only: true })  // 🔁 Correct: for sales sheet only
  });

  const data = await res.json();
  console.log("🟢 Server Response (sales sheet):", data);

  if (!res.ok || !data.sheet_url) {
    throw new Error(data.error || "Failed to generate sales sheet.");
  }

  // ✅ Update UI
  sheetLinkEl.href = data.sheet_url;
  reviewBox.style.display = "block";
  resultEl.innerHTML = `<div style="color:green;"><strong>✅ Sales sheet created. Review before export.</strong></div>`;

  // ✅ Enable clone phase
  salesSheetCreated = true;
  cloneBtnContainer.style.display = "block";

} catch (err) {
  console.error("❌ Sheet Generation Error:", err);
  resultEl.innerHTML = `<div style="color:red;"><strong>Error:</strong> ${err.message}</div>`;
} finally {
  loadingEl.style.display = "none";
}

// Step 2: Continue full export
continueBtn.addEventListener("click", async () => {
  if (!lastPayload) return;

  resultEl.innerHTML = "";
  loadingEl.style.display = "block";

  try {
    const res = await fetch("/run_export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lastPayload)
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "Export failed.");
    }

    const count = data.products?.length || 0;
    resultEl.innerHTML = `<div style="color:green;"><strong>✅ ${count} products exported successfully.</strong></div>`;
  } catch (err) {
    resultEl.innerHTML = `<div style="color:red;"><strong>Error:</strong> ${err.message}</div>`;
  } finally {
    loadingEl.style.display = "none";
  }
});

cloneBtn?.addEventListener("click", async () => {
  if (!lastPayload || !salesSheetCreated) {
    alert("⚠️ Please generate the sales sheet first.");
    return;
  }

  resultEl.innerHTML = "";
  loadingEl.style.display = "block";
  cloneBtn.disabled = true;

  try {
    const res = await fetch("/run_export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...lastPayload,
        run_phase_1: true,
        run_phase_2: false
      })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Cloning failed.");

    resultEl.innerHTML = `<div style="color:green;"><strong>✅ Products cloned to target store.</strong></div>`;
    productsCloned = true;

    // ✅ Show translate button container
    translateBtnContainer.style.display = "block";
  } catch (err) {
    console.error("❌ Clone Error:", err);
    resultEl.innerHTML = `<div style="color:red;"><strong>Error:</strong> ${err.message}</div>`;
  } finally {
    loadingEl.style.display = "none";
    cloneBtn.disabled = false;
  }
});

// 🧬 Handle Clone Button

// 🌍 Handle Translate Button
// ===== REPLACE EXISTING TRANSLATE HANDLER =====
translateBtn?.addEventListener("click", async () => {
  if (!lastPayload || !productsCloned) {
    alert("⚠️ Please clone products first.");
    return;
  }

  resultEl.innerHTML = "";
  loadingEl.style.display = "block";
  translateBtn.disabled = true;

  try {
    const res = await fetch("/run_export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...lastPayload,
        run_phase_1: false,
        run_phase_2: true,
        translation_methods: {
          title: lastPayload.title_method,
          description: lastPayload.desc_method,
          variants: lastPayload.variant_method
        },
        prompts: {
          title: lastPayload.title_prompt,
          description: lastPayload.desc_prompt,
          variants: lastPayload.variant_prompt
        }
      })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Translation failed.");

    const count = data.products?.length || 0;
    resultEl.innerHTML = `<div style="color:green;"><strong>🌍 ${count} products translated and updated.</strong></div>`;
  } catch (err) {
    console.error("❌ Translate Error:", err);
    resultEl.innerHTML = `<div style="color:red;"><strong>Error:</strong> ${err.message}</div>`;
  } finally {
    loadingEl.style.display = "none";
    translateBtn.disabled = false;
  }
});
// ===== END UPDATED HANDLER =====
}); 
}); 