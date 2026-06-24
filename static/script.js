// Frontend Logic for AssetGrab
document.addEventListener("DOMContentLoaded", () => {
    // Helper to safely render icons without crashing if CDN is blocked or offline
    function refreshIcons() {
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }
    refreshIcons();

    // Elements
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const engineSelect = document.getElementById("engine-select");
    const formatSelect = document.getElementById("format-select");
    const sizeSlider = document.getElementById("size-slider");
    const sizeVal = document.getElementById("size-val");
    const dedupToggle = document.getElementById("dedup-toggle");

    const emptyState = document.getElementById("empty-state");
    const loadingState = document.getElementById("loading-state");
    const galleryState = document.getElementById("gallery-state");
    const galleryMeta = document.getElementById("gallery-meta");
    const imageGrid = document.getElementById("image-grid");
    const btnOpenFolder = document.getElementById("btn-open-folder");
    const galleryPathRow = document.getElementById("gallery-path-row");
    const galleryPathText = document.getElementById("gallery-path-text");
    const btnCopyPath = document.getElementById("btn-copy-path");

    // Modal Elements
    const previewModal = document.getElementById("preview-modal");
    const modalImage = document.getElementById("modal-image");
    const modalFilename = document.getElementById("modal-filename");
    const modalDimensions = document.getElementById("modal-dimensions");
    const modalFilesize = document.getElementById("modal-filesize");
    const modalDownload = document.getElementById("modal-download");
    const modalCloseBtn = document.getElementById("modal-close-btn");

    let currentFolderPath = ""; // Holds the local path of the current extraction run

    // Update Slider Value Label
    sizeSlider.addEventListener("input", (e) => {
        const val = e.target.value;
        if (val >= 1000) {
            sizeVal.textContent = `${(val / 1000).toFixed(0)} KB`;
        } else {
            sizeVal.textContent = `${val} B`;
        }
    });

    // Dropzone Events
    dropzone.addEventListener("click", () => fileInput.click());

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) {
            processFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            processFile(e.target.files[0]);
        }
    });

    // API Upload and Processing
    async function processFile(file) {
        // Toggle view states
        emptyState.classList.add("hidden");
        galleryState.classList.add("hidden");
        loadingState.classList.remove("hidden");

        const formData = new FormData();
        formData.append("file", file);
        formData.append("engine", engineSelect.value);
        formData.append("min_size", sizeSlider.value);
        formData.append("format", formatSelect.value);
        formData.append("deduplicate", dedupToggle.checked);

        try {
            const response = await fetch("/api/extract", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "Failed to extract images");
            }

            const data = await response.json();
            displayGallery(data);
        } catch (error) {
            alert(`Error: ${error.message}`);
            loadingState.classList.add("hidden");
            emptyState.classList.remove("hidden");
        }
    }

    // Display Extracted Images
    function displayGallery(result) {
        currentFolderPath = result.folder_path;
        galleryPathText.textContent = currentFolderPath;
        galleryPathRow.classList.remove("hidden");
        imageGrid.innerHTML = "";

        if (result.images.length === 0) {
            galleryMeta.textContent = "0 Images Extracted";
            imageGrid.innerHTML = `
                <div class="glass-card" style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-secondary);">
                    No images match the criteria (might be filtered by minimum size or duplicates).
                </div>
            `;
        } else {
            galleryMeta.textContent = `${result.images.length} Images Extracted`;

            result.images.forEach(img => {
                const card = document.createElement("div");
                card.className = "img-card";
                
                // Construct file sizes in KB
                const sizeKB = (img.size / 1024).toFixed(1);
                
                card.innerHTML = `
                    <div class="img-container">
                        <img src="${img.url}" alt="${img.name}">
                        <div class="img-meta-hover">
                            <span class="preview-badge"><i data-lucide="eye"></i> View Detail</span>
                        </div>
                    </div>
                    <div class="img-details">
                        <div class="img-name" title="${img.name}">${img.name}</div>
                        <div class="img-submeta">
                            <span>${img.dimensions || 'N/A'}</span>
                            <span>${sizeKB} KB</span>
                        </div>
                    </div>
                `;

                // Handle Card Click
                card.addEventListener("click", () => {
                    openPreview(img);
                });

                imageGrid.appendChild(card);
            });

            // Re-render lucide icons in the dynamically created cards
            refreshIcons();
        }

        loadingState.classList.add("hidden");
        galleryState.classList.remove("hidden");
    }

    // Open Folder in Windows Explorer
    btnOpenFolder.addEventListener("click", async () => {
        if (!currentFolderPath) return;
        try {
            const res = await fetch("/api/open-folder", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ folder_path: currentFolderPath })
            });
            if (!res.ok) {
                throw new Error("Unable to open folder");
            }
        } catch (error) {
            alert(`Unable to open folder in explorer: ${error.message}`);
        }
    });

    // Copy Path to Clipboard
    btnCopyPath.addEventListener("click", () => {
        navigator.clipboard.writeText(currentFolderPath).then(() => {
            const icon = btnCopyPath.querySelector("i");
            if (icon) {
                icon.setAttribute("data-lucide", "check");
                refreshIcons();
                setTimeout(() => {
                    icon.setAttribute("data-lucide", "copy");
                    refreshIcons();
                }, 1500);
            }
        }).catch(err => {
            console.error("Could not copy path: ", err);
        });
    });

    // Preview Modal Logic
    function openPreview(img) {
        modalImage.src = img.url;
        modalFilename.textContent = img.name;
        modalDimensions.innerHTML = `<i data-lucide="maximize-2"></i> ${img.dimensions || 'Dimensions: N/A'}`;
        modalFilesize.innerHTML = `<i data-lucide="database"></i> ${(img.size / 1024).toFixed(1)} KB`;
        modalDownload.href = img.url;
        modalDownload.setAttribute("download", img.name);
        
        previewModal.classList.remove("hidden");
        refreshIcons(); // Refresh icons inside modal
    }

    function closePreview() {
        previewModal.classList.add("hidden");
        modalImage.src = "";
    }

    modalCloseBtn.addEventListener("click", closePreview);
    previewModal.querySelector(".modal-backdrop").addEventListener("click", closePreview);

    // Esc key close listener
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !previewModal.classList.contains("hidden")) {
            closePreview();
        }
    });
});
