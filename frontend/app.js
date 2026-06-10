/**
 * app.js — Frontend logic for Azure AI Content Understanding
 * 
 * Handles:
 *   - Drag & drop file upload
 *   - Pipeline progress animation
 *   - API communication (live & demo mode)
 *   - Dynamic result rendering with confidence visualization
 *   - Smooth scroll navigation
 */

// ═══════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════

const CATEGORY_ICONS = {
    invoice:          '📋',
    bank_statement:   '🏦',
    medical_report:   '🏥',
    loan_application: '📝',
    kyc_document:     '🪪',
    purchase_order:   '📦',
    contract:         '📃',
    unknown:          '📄',
};

const CATEGORY_LABELS = {
    invoice:          'Invoice',
    bank_statement:   'Bank Statement',
    medical_report:   'Medical Report',
    loan_application: 'Loan Application',
    kyc_document:     'KYC Document',
    purchase_order:   'Purchase Order',
    contract:         'Contract',
    unknown:          'Unknown',
};


// ═══════════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════════

let selectedFile = null;
let isProcessing = false;


// ═══════════════════════════════════════════════════════════════════
// DOM REFS
// ═══════════════════════════════════════════════════════════════════

const uploadZone       = document.getElementById('upload-zone');
const fileInput        = document.getElementById('file-input');
const filePreview      = document.getElementById('file-preview');
const filePreviewName  = document.getElementById('file-preview-name');
const filePreviewSize  = document.getElementById('file-preview-size');
const filePreviewIcon  = document.getElementById('file-preview-icon');
const fileRemoveBtn    = document.getElementById('file-remove-btn');
const analyzeBtn       = document.getElementById('analyze-btn');
const demoBtn          = document.getElementById('demo-btn');
const demoBtn2         = document.getElementById('demo-btn-2');
const pipelineSection  = document.getElementById('pipeline-section');
const resultsSection   = document.getElementById('results-section');
const pipelineStatus   = document.getElementById('pipeline-status-text');


// ═══════════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════════

window.addEventListener('scroll', () => {
    const nav = document.getElementById('nav');
    nav.classList.toggle('scrolled', window.scrollY > 50);

    // Update active link
    const sections = ['hero', 'upload-section', 'architecture', 'categories'];
    const links = document.querySelectorAll('.nav-link');
    
    let current = '';
    for (const id of sections) {
        const section = document.getElementById(id);
        if (section && section.offsetTop - 200 <= window.scrollY) {
            current = id;
        }
    }
    
    links.forEach(link => {
        link.classList.toggle('active', link.getAttribute('href') === `#${current}`);
    });
});


// ═══════════════════════════════════════════════════════════════════
// FILE UPLOAD
// ═══════════════════════════════════════════════════════════════════

// Click to upload
uploadZone.addEventListener('click', () => fileInput.click());

// Drag & drop events
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('drag-over');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('drag-over');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length) {
        handleFile(fileInput.files[0]);
    }
});

fileRemoveBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    clearFile();
});


function handleFile(file) {
    const validTypes = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    
    if (!validTypes.includes(ext)) {
        showToast('Unsupported file type. Please use PDF, PNG, JPG, TIFF, or BMP.', 'error');
        return;
    }

    selectedFile = file;
    
    // Show preview
    uploadZone.style.display = 'none';
    filePreview.style.display = 'flex';
    filePreviewName.textContent = file.name;
    filePreviewSize.textContent = formatFileSize(file.size);
    filePreviewIcon.textContent = ext === '.pdf' ? '📄' : '🖼️';
    
    analyzeBtn.disabled = false;
}

function clearFile() {
    selectedFile = null;
    fileInput.value = '';
    uploadZone.style.display = 'block';
    filePreview.style.display = 'none';
    analyzeBtn.disabled = true;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + sizes[i];
}


// ═══════════════════════════════════════════════════════════════════
// ANALYZE ACTIONS
// ═══════════════════════════════════════════════════════════════════

analyzeBtn.addEventListener('click', () => {
    if (!selectedFile || isProcessing) return;
    startLiveAnalysis();
});

demoBtn.addEventListener('click', startDemoMode);
demoBtn2.addEventListener('click', startDemoMode);


async function startLiveAnalysis() {
    isProcessing = true;
    analyzeBtn.disabled = true;
    analyzeBtn.innerHTML = '<div class="spinner"></div> Analyzing...';

    showPipeline();
    
    try {
        // Step 1: Upload
        await animatePipelineStep('step-upload', 'conn-1', 'Uploading file...');
        
        const formData = new FormData();
        formData.append('file', selectedFile);
        
        // Step 2: Classify
        await animatePipelineStep('step-classify', 'conn-2', 'Classifying document types...');
        
        // Step 3: Segment
        await animatePipelineStep('step-segment', 'conn-3', 'Splitting into segments...');
        
        // Step 4: Extract
        pipelineStatus.textContent = 'Extracting fields... (this may take 30-60 seconds)';
        setStepActive('step-extract');
        
        const response = await fetch('/api/analyze', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Analysis failed');
        }

        const data = await response.json();
        
        setStepComplete('step-extract');
        pipelineStatus.textContent = 'Processing complete!';
        
        await sleep(500);
        renderResults(data);

    } catch (err) {
        pipelineStatus.textContent = `Error: ${err.message}`;
        pipelineStatus.style.color = 'var(--accent-red)';
        showToast(err.message, 'error');
    } finally {
        isProcessing = false;
        analyzeBtn.disabled = false;
        analyzeBtn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            Analyze Document`;
    }
}


async function startDemoMode() {
    if (isProcessing) return;
    isProcessing = true;

    showPipeline();

    try {
        // Animate pipeline steps with delays
        await animatePipelineStep('step-upload', 'conn-1', 'Loading sample data...');
        await animatePipelineStep('step-classify', 'conn-2', 'Classification complete (demo)');
        await animatePipelineStep('step-segment', 'conn-3', 'Segments identified (demo)');
        
        pipelineStatus.textContent = 'Loading extracted fields...';
        setStepActive('step-extract');

        const response = await fetch('/api/demo-results');
        if (!response.ok) {
            throw new Error('Demo data not available. Please run the pipeline once first.');
        }

        const data = await response.json();

        setStepComplete('step-extract');
        pipelineStatus.textContent = 'Demo data loaded successfully!';

        await sleep(400);
        renderResults(data);

    } catch (err) {
        pipelineStatus.textContent = `Error: ${err.message}`;
        pipelineStatus.style.color = 'var(--accent-red)';
        showToast(err.message, 'error');
    } finally {
        isProcessing = false;
    }
}


// ═══════════════════════════════════════════════════════════════════
// PIPELINE ANIMATION
// ═══════════════════════════════════════════════════════════════════

function showPipeline() {
    pipelineSection.style.display = 'block';
    resultsSection.style.display = 'none';
    pipelineStatus.style.color = '';
    
    // Reset all steps
    document.querySelectorAll('.pipeline-step').forEach(s => {
        s.classList.remove('active', 'complete');
    });
    document.querySelectorAll('.pipeline-connector').forEach(c => {
        c.classList.remove('active');
    });

    // Scroll to pipeline
    pipelineSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function setStepActive(stepId) {
    const step = document.getElementById(stepId);
    step.classList.remove('complete');
    step.classList.add('active');
}

function setStepComplete(stepId) {
    const step = document.getElementById(stepId);
    step.classList.remove('active');
    step.classList.add('complete');
}

async function animatePipelineStep(stepId, connId, message) {
    pipelineStatus.textContent = message;
    setStepActive(stepId);
    await sleep(600);
    setStepComplete(stepId);
    if (connId) {
        document.getElementById(connId).classList.add('active');
    }
    await sleep(300);
}


// ═══════════════════════════════════════════════════════════════════
// RESULTS RENDERING
// ═══════════════════════════════════════════════════════════════════

function renderResults(data) {
    resultsSection.style.display = 'block';

    // Parse fields from demo data format
    const segments = parseSegments(data);

    // Update subtitle
    document.getElementById('results-subtitle').textContent = 
        `${data.file} — ${data.mode === 'demo' ? 'Demo results' : 'Live analysis'}`;

    // Compute summary stats
    let totalFields = 0;
    let totalConfidence = 0;
    let confidenceCount = 0;

    segments.forEach(seg => {
        totalFields += seg.fields.length;
        seg.fields.forEach(f => {
            if (f.confidence > 0) {
                totalConfidence += f.confidence;
                confidenceCount++;
            }
        });
    });

    const avgConf = confidenceCount > 0 ? (totalConfidence / confidenceCount * 100) : 0;

    // Animate summary numbers
    animateCounter('summary-segments', data.total_segments);
    animateCounter('summary-fields', totalFields);
    document.getElementById('summary-confidence').textContent = `${avgConf.toFixed(0)}%`;
    document.getElementById('summary-time').textContent = `${data.processing_time || 0}s`;

    // Render segment cards
    const container = document.getElementById('segments-container');
    container.innerHTML = '';

    segments.forEach((seg, idx) => {
        const card = createSegmentCard(seg, idx);
        container.appendChild(card);
    });

    // Scroll to results
    setTimeout(() => {
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 200);
}


function parseSegments(data) {
    /**
     * Parse segments from either demo or live API response.
     * Demo mode has `fields_text` strings; live mode has structured `fields`.
     */
    return data.segments.map(seg => {
        let fields = [];

        // If we already have structured fields, use them
        if (seg.fields && Array.isArray(seg.fields)) {
            fields = seg.fields;
        }
        // Parse from fields_text (demo mode)
        else if (seg.fields_text) {
            fields = parseFieldsText(seg.fields_text);
        }
        // Parse from extracted_fields JSON (demo mode, nested)
        else if (seg.extracted_fields) {
            fields = parseExtractedFields(seg.extracted_fields);
        }

        return {
            segment: seg.segment,
            category: seg.category,
            pages: seg.pages,
            analyzer: seg.analyzer_used,
            fields: fields,
        };
    });
}


function parseFieldsText(text) {
    /**
     * Parse the plain-text field output format:
     *   fieldName : value (0.xxx)
     */
    const fields = [];
    const lines = text.split('\n');
    
    for (const line of lines) {
        const match = line.match(/^(.+?)\s*:\s*(.+?)\s*\((\d+\.\d+)\)\s*$/);
        if (match) {
            const name = match[1].trim();
            let value = match[2].trim();
            const confidence = parseFloat(match[3]);

            // Skip header lines
            if (name.startsWith('Segment ')) continue;

            fields.push({ name, value, confidence });
        }
    }
    return fields;
}


function parseExtractedFields(result) {
    /**
     * Parse the nested JSON format from the API result.
     * Recursively flattens arrays and objects.
     */
    const fields = [];

    // Navigate through Azure SDK response structure
    let fieldsDict = {};
    
    if (result.contents && result.contents[0]) {
        fieldsDict = result.contents[0].fields || {};
    } else if (result.result && result.result.contents && result.result.contents[0]) {
        fieldsDict = result.result.contents[0].fields || {};
    }

    function extractFields(dict, prefix) {
        for (const [name, data] of Object.entries(dict)) {
            if (typeof data !== 'object' || data === null) continue;

            const fullName = prefix ? `${prefix}${name}` : name;

            // Array of objects
            if (data.type === 'array' && data.valueArray) {
                data.valueArray.forEach((item, idx) => {
                    if (item.valueObject) {
                        extractFields(item.valueObject, `${fullName}[${idx + 1}].`);
                    }
                });
                continue;
            }

            // Nested object
            if (data.type === 'object' && data.valueObject) {
                extractFields(data.valueObject, `${fullName}.`);
                continue;
            }

            // Scalar value
            let value = data.valueString || data.valueNumber || data.valueDate || data.valueBoolean;
            if (value === undefined || value === null) value = '(not found)';

            fields.push({
                name: fullName,
                value: String(value),
                confidence: data.confidence || 0,
            });
        }
    }

    extractFields(fieldsDict, '');
    return fields;
}


function createSegmentCard(seg, idx) {
    const card = document.createElement('div');
    card.className = 'segment-card';
    card.style.animationDelay = `${idx * 0.1}s`;

    const icon = CATEGORY_ICONS[seg.category] || CATEGORY_ICONS.unknown;
    const label = CATEGORY_LABELS[seg.category] || seg.category;
    const badgeClass = `badge-${seg.category}`;

    // Calculate average confidence for this segment
    let avgConf = 0;
    if (seg.fields.length > 0) {
        const total = seg.fields.reduce((sum, f) => sum + f.confidence, 0);
        avgConf = total / seg.fields.length;
    }
    const confPercent = Math.round(avgConf * 100);
    const confColor = getConfidenceColor(avgConf);
    
    // SVG ring circumference for confidence
    const circumference = 2 * Math.PI * 17; // r=17
    const offset = circumference - (avgConf * circumference);

    card.innerHTML = `
        <div class="segment-card-header" onclick="toggleSegment(this)">
            <div class="segment-card-number">${seg.segment}</div>
            <div class="segment-card-info">
                <div class="segment-card-category">
                    ${icon} ${label}
                    <span class="segment-card-badge ${badgeClass}">${seg.category}</span>
                </div>
                <div class="segment-card-meta">
                    <span>Pages ${seg.pages}</span>
                    <span>•</span>
                    <span>${seg.fields.length} fields</span>
                    ${seg.analyzer ? `<span>•</span><span>${seg.analyzer}</span>` : ''}
                </div>
            </div>
            <div class="segment-card-confidence">
                <div class="confidence-ring">
                    <svg viewBox="0 0 40 40">
                        <circle class="confidence-ring-bg" cx="20" cy="20" r="17"/>
                        <circle class="confidence-ring-fill" cx="20" cy="20" r="17"
                            stroke="${confColor}"
                            stroke-dasharray="${circumference}"
                            stroke-dashoffset="${offset}"/>
                    </svg>
                    <div class="confidence-ring-text" style="color:${confColor}">${confPercent}%</div>
                </div>
            </div>
            <div class="segment-card-toggle">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </div>
        </div>
        <div class="segment-card-body">
            <div class="segment-card-body-inner">
                ${createFieldsTable(seg.fields)}
            </div>
        </div>
    `;

    return card;
}


function createFieldsTable(fields) {
    if (!fields.length) {
        return '<p style="color: var(--text-muted); font-style: italic;">No fields extracted</p>';
    }

    let rows = '';
    for (const f of fields) {
        const confLevel = getConfidenceLevel(f.confidence);
        const confPercent = Math.round(f.confidence * 100);
        const isNotFound = f.value === '(not found)';
        
        rows += `
        <tr>
            <td><span class="field-name">${escapeHtml(f.name)}</span></td>
            <td><span class="field-value ${isNotFound ? 'not-found' : ''}">${escapeHtml(f.value)}</span></td>
            <td class="confidence-bar-cell">
                <div class="confidence-bar-wrapper">
                    <div class="confidence-bar">
                        <div class="confidence-bar-fill ${confLevel}" style="width: ${confPercent}%"></div>
                    </div>
                    <span class="confidence-text ${confLevel}">${(f.confidence).toFixed(3)}</span>
                </div>
            </td>
        </tr>`;
    }

    return `
    <table class="fields-table">
        <thead>
            <tr>
                <th>Field</th>
                <th>Value</th>
                <th>Confidence</th>
            </tr>
        </thead>
        <tbody>${rows}</tbody>
    </table>`;
}


// ═══════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════

function getConfidenceLevel(confidence) {
    if (confidence >= 0.8) return 'high';
    if (confidence >= 0.5) return 'medium';
    return 'low';
}

function getConfidenceColor(confidence) {
    if (confidence >= 0.8) return '#34d399';   // green
    if (confidence >= 0.5) return '#fbbf24';   // yellow
    return '#ef4444';                           // red
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function animateCounter(elementId, target) {
    const el = document.getElementById(elementId);
    const duration = 1000;
    const steps = 30;
    const increment = target / steps;
    let current = 0;
    const interval = duration / steps;

    const timer = setInterval(() => {
        current += increment;
        if (current >= target) {
            el.textContent = target;
            clearInterval(timer);
        } else {
            el.textContent = Math.floor(current);
        }
    }, interval);
}

function showToast(message, type = 'info') {
    // Create a simple toast notification
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        bottom: 30px;
        right: 30px;
        padding: 16px 24px;
        background: ${type === 'error' ? 'rgba(239, 68, 68, 0.9)' : 'rgba(79, 110, 247, 0.9)'};
        color: white;
        border-radius: 12px;
        font-size: 0.9rem;
        font-weight: 500;
        z-index: 10000;
        backdrop-filter: blur(10px);
        box-shadow: 0 8px 30px rgba(0,0,0,0.3);
        animation: fadeInUp 0.3s ease-out;
        max-width: 400px;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}


// Global function for segment card toggle (called from onclick)
window.toggleSegment = function(header) {
    const card = header.closest('.segment-card');
    card.classList.toggle('expanded');
};


// ═══════════════════════════════════════════════════════════════════
// SMOOTH SCROLL FOR CTA
// ═══════════════════════════════════════════════════════════════════

document.getElementById('hero-cta').addEventListener('click', (e) => {
    e.preventDefault();
    document.getElementById('upload-section').scrollIntoView({ behavior: 'smooth' });
});


// ═══════════════════════════════════════════════════════════════════
// INTERSECTION OBSERVER FOR ANIMATIONS
// ═══════════════════════════════════════════════════════════════════

const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.animationPlayState = 'running';
        }
    });
}, observerOptions);

// Observe elements that should animate on scroll
document.querySelectorAll('.category-card, .arch-feature, .arch-card').forEach(el => {
    observer.observe(el);
});
