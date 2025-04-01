////////////////////////////////////////////////////////////////////////////////
// Fetch and display Shopify collections and products dynamically
////////////////////////////////////////////////////////////////////////////////

const API_BASE_URL = `${window.location.protocol}//${window.location.host}`;

console.log("Using API_BASE_URL:", API_BASE_URL);

// Ensure script runs when page loads
document.addEventListener("DOMContentLoaded", () => {
    fetchCollections();
    initializeMethodHandlers();
});

function initializeMethodHandlers() {
    document.querySelectorAll('.field-method').forEach(select => {
        select.addEventListener('change', function () {
            document.querySelectorAll('.field-method').forEach(otherSelect => {
                const container = otherSelect.closest('.mb-3').querySelector('.method-prompt');
                const value = otherSelect.value;
                const isAI = ['deepseek', 'chatgpt'].includes(value);
                container.style.display = isAI ? 'block' : 'none';
            });
        });
    });
}

// Fetch collections from API and populate dropdown
function fetchCollections() {
    console.log("Fetching collections from backend...");

    fetch(`${API_BASE_URL}/get_collections`)
        .then(response => {
            if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);
            return response.json();
        })
        .then(data => {
            console.log("Fetched collections:", data);
            const dropdown = document.getElementById("collectionDropdown");

            if (!dropdown) {
                console.error("Error: Collection dropdown not found!");
                return;
            }

            // Reset dropdown content
            dropdown.innerHTML = '<option value="" disabled selected>Select a collection</option>';

            if (data.collections.length > 0) {
                data.collections.forEach(col => {
                    let opt = document.createElement("option");
                    opt.value = col.id;
                    opt.textContent = col.title;
                    dropdown.appendChild(opt);
                });
                console.log("Dropdown updated successfully.");
            } else {
                dropdown.innerHTML = "<option>No collections found</option>";
            }
        })
        .catch(error => console.error("Error fetching collections:", error));
}
// Fetch products by collection
window.fetchProductsByCollection = function () {
  const collectionId = document.getElementById("collectionDropdown")?.value;
  if (!collectionId) {
      alert("Please select a collection first.");
      return;
  }

  console.log(`Fetching products for collection ID: ${collectionId}`);

  fetch(`${API_BASE_URL}/fetch_products_by_collection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ collection_id: collectionId })
  })
      .then(response => {
          if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);
          return response.json();
      })
      .then(data => {
          console.log("Fetched products:", data);

          if (data.success && data.products && data.products.length > 0) {
              window.allLoadedProducts = data.products;
              displayProducts(data.products); // Display all products
              document.getElementById("collectionInfo").innerText =
                  `Loaded ${data.products.length} products from "${data.collection_name}".`;
          } else {
              alert(data.error || "No products found in this collection.");
              console.warn("No products found in the selected collection.");
          }
      })
      .catch(error => console.error("Error fetching products:", error));
};

// Display all fetched products dynamically
function displayProducts(products) {
  console.log("Displaying products:", products);

  const productContainer = document.getElementById("testProductInfo");
  const singleProductCard = document.getElementById("singleProductCard");
  const fieldsCard = document.getElementById("fieldsCard");

  if (!productContainer) {
    console.error("Error: Product container (testProductInfo) not found!");
    return;
  }
  // Show the product card and translation options
  singleProductCard.style.display = "block";
  fieldsCard.style.display = "block";

  productContainer.innerHTML = ""; // Clear previous content

  if (!products || products.length === 0) {
    productContainer.innerHTML = "<p>No products found.</p>";
    console.warn("No products available to display.");
    return;
  }

  // Only show the first product
  const product = products[0];
  console.log("Rendering test product:", product.title);

  // Convert product.body_html to actual HTML
  let productDescription = new DOMParser().parseFromString(product.body_html || "", "text/html").body;
  let cleanedDescription = productDescription.innerHTML || "<p>No description available.</p>";

  // Build a final HTML snippet
  let finalHtml = `
    <h4>${product.title}</h4>
    <div>${cleanedDescription}</div>
  `;

  // If you have images, insert the first two images at the end
  if (product.images && product.images.length > 0) {
    let image1 = product.images[0].src;
    finalHtml += `
      <div style="margin-top:1em;">
        <img src="${image1}" style="width:480px; max-width:100%;"/>
      </div>`;
    if (product.images.length > 1) {
      let image2 = product.images[1].src;
      finalHtml += `
        <div style="margin-top:1em;">
          <img src="${image2}" style="width:480px; max-width:100%;"/>
        </div>`;
    }
  }

  // Create the product card and inject finalHtml
  const productCard = document.createElement("div");
  productCard.classList.add("product-card");
  productCard.innerHTML = finalHtml;

  productContainer.appendChild(productCard);
}

// Get selected translation fields and their methods
function getSelectedFieldsAndMethods() {
    const selectedFields = {};

    // Title field
    if (document.getElementById("titleField").checked) {
        selectedFields.title = {
            method: document.getElementById("titleMethod").value,
            prompt: document.getElementById("titlePrompt").value
        };
    }

    // Description field
    if (document.getElementById("descField").checked) {
        selectedFields.body_html = {
            method: document.getElementById("descMethod").value,
            prompt: document.getElementById("descPrompt").value
        };
    }

    // Variants field
    if (document.getElementById("variantsField")?.checked) {
        selectedFields.variant_options = {
            method: document.getElementById("variantsMethod").value,
            prompt: document.getElementById("variantsPrompt").value
        };
    }

    console.log("Selected Fields:", selectedFields);
    return selectedFields;
}

// Get selected translation method
// Get selected translation method
function testRunTranslation() {
  console.log("🚀 Running Test Translation...");

  const selectedFieldsAndMethods = getSelectedFieldsAndMethods();
  console.log("🔍 Selected Fields & Methods:", selectedFieldsAndMethods);
  const testProductOutput = document.getElementById("testRunOutput");
  const targetLanguage = document.getElementById("targetLanguage").value;

  if (!window.allLoadedProducts?.[0]?.id) {
      testProductOutput.innerHTML = "<p class='text-danger'>⚠️ No test product loaded. Please select a collection first.</p>";
      console.error("❌ No test product found.");
      return;
  }

  // Disable buttons to prevent duplicate requests
  document.querySelectorAll("button").forEach(btn => btn.disabled = true);

  const requestBody = {
      product_id: window.allLoadedProducts[0].id,
      fields: Object.keys(selectedFieldsAndMethods),
      field_methods: selectedFieldsAndMethods,
      source_language: "auto",
      target_language: targetLanguage,
  };

  console.log("📤 Sending Translation Request:", requestBody);

  fetch("/translate_test_product", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody)
  })
  .then(response => {
      console.log("📥 Received response object:", response);
      if (!response.ok) {
          throw new Error(`❌ HTTP Error: ${response.status} - ${response.statusText}`);
      }
      return response.json();
  })
  .then(data => {
      console.log("📥 Received Translation Response:", data);

      if (data.success) {
          let translatedOutput = `<h5>✅ Translated Product:</h5>`;

          // ✅ Show translated title
          if (data.translated_title) {
              console.log("✅ Translated Title:", data.translated_title);
              translatedOutput += `<p><strong>Title:</strong> ${data.translated_title}</p>`;
          }

          if (data.translated_description) {
            console.log("✅ Translated Description:", data.translated_description);
            translatedOutput += `<div>${data.translated_description}</div>`;
        }

          // ✅ Process the translated description
          let translatedDescription = data.translated_description || "";
          let parser = new DOMParser();
          let doc = parser.parseFromString(translatedDescription, "text/html");

          // ✅ Fetch product images
          const testProduct = window.allLoadedProducts[0];
          let firstImg = testProduct?.images?.[0]?.src || "";
          let secondImg = testProduct?.images?.[1]?.src || "";

          // ✅ Insert first image after introduction
          let firstParagraph = doc.querySelector("p");
          if (firstImg && firstParagraph) {
              let imgElement = document.createElement("div");
              imgElement.innerHTML = `<img src="${firstImg}" style="width:480px; max-width:100%; margin-top:1em;"/>`;
              firstParagraph.insertAdjacentElement("afterend", imgElement);
          }

          // ✅ Insert second image after bullet points
          let bulletList = doc.querySelector("ul");
          if (secondImg && bulletList) {
              let imgElement = document.createElement("div");
              imgElement.innerHTML = `<img src="${secondImg}" style="width:480px; max-width:100%; margin-top:1em;"/>`;
              bulletList.insertAdjacentElement("afterend", imgElement);
          }

          // ✅ Convert back to HTML string
          translatedOutput += `<div>${doc.body.innerHTML}</div>`;

          // ✅ Display translated variant options
          if (data.translated_options && data.translated_options.length > 0) {
              translatedOutput += `<h5>🛍️ Translated Variants:</h5><ul>`;
              data.translated_options.forEach(option => {
                  let optionValues = option.values?.join(", ") || "N/A";
                  translatedOutput += `<li><strong>${option.name}:</strong> ${optionValues}</li>`;
              });
              translatedOutput += `</ul>`;
          }

          // ✅ Display final output
          testProductOutput.innerHTML = translatedOutput;
      } else {
          testProductOutput.innerHTML = `<p class='text-danger'>❌ Translation failed: ${data.error || "Unknown error."}</p>`;
      }
  })
  .catch(error => {
      console.error("❌ API Request Failed:", error);
      testProductOutput.innerHTML = `<p class='text-danger'>❌ Error contacting the translation API: ${error.message}</p>`;
  })
  .finally(() => {
      // Re-enable buttons after completion
      document.querySelectorAll("button").forEach(btn => btn.disabled = false);
  });
}

function runAllProducts() {
    const selectedFields = getSelectedFieldsAndMethods();
    const fieldMethods = Object.fromEntries(
        Object.entries(selectedFields).map(([field, config]) => [field, config.method])
    );

    console.log("Running bulk translation...", selectedFields);

    if (Object.keys(selectedFields).length === 0) {
        alert("Please select at least one field to translate.");
        return;
    }

    // Show progress UI
    const progressContainer = document.getElementById("bulkProgressContainer");
    const progressBar = document.getElementById("bulkProgressBar");
    const progressLabel = document.getElementById("bulkProgressLabel");
    progressContainer.style.display = "block";
    progressBar.style.width = "0%";
    progressLabel.innerText = "0%";

   // Start progress polling
   function checkBulkProgress() {
    fetch(`${API_BASE_URL}/translation_progress`)
        .then(response => response.json())
        .then(data => {
            const percent = Math.round((data.completed / data.total) * 100);
            progressBar.style.width = `${percent}%`;
            progressLabel.innerText = `${percent}%`;

            if (percent < 100) {
                setTimeout(checkBulkProgress, 1000);
            } else {
                progressLabel.innerText = "✅ Done!";
            }
        })
        .catch(console.error);
}

    // Prepare prompts
    const prompts = Object.fromEntries(
        Object.entries(selectedFields).map(([field, config]) => [field, config.prompt])
    );
  
    fetch(`${API_BASE_URL}/translate_collection_fields`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            collection_id: document.getElementById("collectionDropdown").value,
            fields: Object.keys(selectedFields),
            field_methods: fieldMethods,
            target_language: document.getElementById("targetLanguage").value,
            prompts: prompts
        })
    })
    .then(res => res.json())
    .then(data => {
        if (!data.success) {
            throw new Error(data.error || "Unknown error");
        }
        console.log("Bulk translation completed:", data);
    })
    .catch(error => {
        console.error("Bulk translation error:", error);
        alert(`❌ Error: ${error.message}`);
    });
}

////////////////////////////////////////////////////////////////////////////////
// Buyer Persona Prompts & Custom ChatGPT Prompts
////////////////////////////////////////////////////////////////////////////////

document.addEventListener("DOMContentLoaded", function () {
    // Persona button handler
    document.querySelectorAll(".persona-btn").forEach(button => {
        button.addEventListener("click", function () {
            const selectedPrompt = this.dataset.prompt;
            const targetField = this.dataset.field; // Assume buttons have data-field attribute
            
            if (targetField === 'title') {
                document.getElementById("titlePrompt").value = selectedPrompt;
            } 
            else if (targetField === 'desc') {
                document.getElementById("descPrompt").value = selectedPrompt;
            }
            else if (targetField === 'variants') {
                document.getElementById("variantsPrompt").value = selectedPrompt;
            }

            console.log("Applied persona prompt to", targetField);
        });
    });
});

    // Show/hide custom prompt fields when ChatGPT is selected
    function toggleCustomPromptFields() {
        let titleMethod = document.getElementById("titleMethod").value;
        let descMethod = document.getElementById("descMethod").value;

        document.getElementById("titlePromptContainer").style.display = (titleMethod === "chatgpt") ? "block" : "none";
        document.getElementById("descPromptContainer").style.display = (descMethod === "chatgpt") ? "block" : "none";
    }

    // Attach event listeners to translation method dropdowns
    document.getElementById("titleMethod").addEventListener("change", toggleCustomPromptFields);
    document.getElementById("descMethod").addEventListener("change", toggleCustomPromptFields);

    // Function to handle persona button clicks
    document.querySelectorAll(".persona-btn").forEach(button => {
        button.addEventListener("click", function () {
            let selectedPrompt = this.getAttribute("data-prompt");
            
            // Check which field is set to ChatGPT and update the relevant prompt box
            if (document.getElementById("titleMethod").value === "chatgpt") {
                document.getElementById("titlePrompt").value = selectedPrompt;
            }
            if (document.getElementById("descMethod").value === "chatgpt") {
                document.getElementById("descPrompt").value = selectedPrompt;
            }

            console.log("✅ Persona Prompt Applied:", selectedPrompt);
        });
    });

  toggleCustomPromptFields();
 // Add this closing parenthesis and semicolon